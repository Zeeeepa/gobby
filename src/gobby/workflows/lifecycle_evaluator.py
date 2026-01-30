"""
Lifecycle workflow evaluation for workflow engine.

Extracted from engine.py to reduce complexity.
Handles discovery and evaluation of lifecycle workflows and their triggers.
"""

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

from gobby.hooks.events import HookEvent, HookEventType, HookResponse

if TYPE_CHECKING:
    from .actions import ActionExecutor
    from .definitions import WorkflowDefinition, WorkflowState
    from .evaluator import ConditionEvaluator
    from .loader import WorkflowLoader
    from .state_manager import WorkflowStateManager

logger = logging.getLogger(__name__)

# Maximum iterations to prevent infinite loops in trigger evaluation
MAX_TRIGGER_ITERATIONS = 10

# Variables to inherit from parent session
VARS_TO_INHERIT = ["plan_mode"]

# Maps canonical trigger names to their legacy aliases for backward compatibility
TRIGGER_ALIASES: dict[str, list[str]] = {
    "on_before_agent": ["on_prompt_submit"],
    "on_before_tool": ["on_tool_call"],
    "on_after_tool": ["on_tool_result"],
}


def process_action_result(
    result: dict[str, Any],
    context_data: dict[str, Any],
    state: "WorkflowState",
    injected_context: list[str],
) -> str | None:
    """
    Process action execution result.

    Updates shared context and state variables.
    Handles inject_context, inject_message, and system_message.

    Args:
        result: The action execution result dictionary
        context_data: Shared context to update
        state: Workflow state to update
        injected_context: List to append injected content to

    Returns:
        New system_message if present, None otherwise
    """
    # Update shared context for chaining
    context_data.update(result)
    state.variables.update(result)

    if "inject_context" in result:
        msg = result["inject_context"]
        logger.debug(f"Found inject_context in result, length={len(msg)}")
        injected_context.append(msg)

    if "inject_message" in result:
        msg = result["inject_message"]
        logger.debug(f"Found inject_message in result, length={len(msg)}")
        injected_context.append(msg)

    return result.get("system_message")


async def evaluate_workflow_triggers(
    workflow: "WorkflowDefinition",
    event: HookEvent,
    context_data: dict[str, Any],
    state_manager: "WorkflowStateManager",
    action_executor: "ActionExecutor",
    evaluator: "ConditionEvaluator",
) -> HookResponse:
    """
    Evaluate triggers for a single workflow definition.

    Args:
        workflow: The workflow definition to evaluate
        event: The hook event
        context_data: Shared context for chaining (mutated by actions)
        state_manager: Workflow state manager
        action_executor: Action executor for running actions
        evaluator: Condition evaluator

    Returns:
        HookResponse from this workflow's triggers
    """
    from .actions import ActionContext
    from .definitions import WorkflowState

    # Map hook event to trigger name
    trigger_name = f"on_{event.event_type.name.lower()}"

    # Look up triggers - try canonical name first, then aliases
    triggers = []
    if workflow.triggers:
        triggers = workflow.triggers.get(trigger_name, [])
        if not triggers:
            aliases = TRIGGER_ALIASES.get(trigger_name, [])
            for alias in aliases:
                triggers = workflow.triggers.get(alias, [])
                if triggers:
                    break

    if not triggers:
        return HookResponse(decision="allow")

    logger.debug(
        f"Evaluating {len(triggers)} trigger(s) for '{trigger_name}' in workflow '{workflow.name}'"
    )

    # Get or create persisted state for action execution
    # This ensures variables like _injected_memory_ids persist across hook calls
    session_id = event.metadata.get("_platform_session_id") or "global"

    # Try to load existing state, or create new one
    state = state_manager.get_state(session_id)
    if state is None:
        state = WorkflowState(
            session_id=session_id,
            workflow_name=workflow.name,
            step="global",
            step_entered_at=datetime.now(UTC),
            step_action_count=0,
            total_action_count=0,
            artifacts=event.data.get("artifacts", {}) if event.data else {},
            observations=[],
            reflection_pending=False,
            context_injected=False,
            variables={},
            task_list=None,
            current_task_index=0,
            files_modified_this_task=0,
        )

    # Merge context_data into state variables (context_data has session vars from earlier load)
    if context_data:
        state.variables.update(context_data)

    action_ctx = ActionContext(
        session_id=session_id,
        state=state,
        db=action_executor.db,
        session_manager=action_executor.session_manager,
        template_engine=action_executor.template_engine,
        llm_service=action_executor.llm_service,
        transcript_processor=action_executor.transcript_processor,
        config=action_executor.config,
        mcp_manager=action_executor.mcp_manager,
        memory_manager=action_executor.memory_manager,
        memory_sync_manager=action_executor.memory_sync_manager,
        task_sync_manager=action_executor.task_sync_manager,
        session_task_manager=action_executor.session_task_manager,
        event_data=event.data,  # Pass hook event data (prompt_text, etc.)
    )

    injected_context: list[str] = []
    system_message: str | None = None

    # Fetch session for condition evaluation (enables session.title checks)
    session = None
    if action_executor.session_manager:
        session = action_executor.session_manager.get(session_id)

    for trigger in triggers:
        # Check 'when' condition if present
        when_condition = trigger.get("when")
        if when_condition:
            eval_ctx = {
                "event": event,
                "workflow_state": state,
                "handoff": context_data,
                "variables": state.variables,
                "session": session,
            }
            eval_ctx.update(context_data)
            eval_result = evaluator.evaluate(when_condition, eval_ctx)
            logger.debug(
                f"When condition '{when_condition}' evaluated to {eval_result}, "
                f"event.data.source={event.data.get('source') if event.data else None}"
            )
            if not eval_result:
                continue

        # Execute action
        action_type = trigger.get("action")
        if not action_type:
            continue

        logger.debug(f"Executing action '{action_type}' in workflow '{workflow.name}'")
        try:
            kwargs = trigger.copy()
            kwargs.pop("action", None)
            kwargs.pop("when", None)

            # Debug: log kwargs being passed to action
            if action_type == "inject_context":
                template_val = kwargs.get("template")
                logger.debug(
                    f"inject_context kwargs: source={kwargs.get('source')!r}, "
                    f"template_present={template_val is not None}, "
                    f"template_len={len(template_val) if template_val else 0}"
                )

            result = await action_executor.execute(action_type, action_ctx, **kwargs)
            logger.debug(
                f"Action '{action_type}' result: {type(result)}, keys={list(result.keys()) if isinstance(result, dict) else 'N/A'}"
            )

            if result and isinstance(result, dict):
                sys_msg = process_action_result(result, context_data, state, injected_context)
                if sys_msg:
                    system_message = sys_msg

                # Check for blocking decision from action
                if result.get("decision") == "block":
                    return HookResponse(
                        decision="block",
                        reason=result.get("reason", "Blocked by action"),
                        context="\n\n".join(injected_context) if injected_context else None,
                        system_message=system_message,
                    )

        except Exception as e:
            logger.error(
                f"Failed to execute action '{action_type}' in '{workflow.name}': {e}",
                exc_info=True,
            )

    # Persist state changes (e.g., _injected_memory_ids from memory_recall_relevant)
    # Only save if we have a real session ID (not "global" fallback)
    # The workflow_states table has a FK to sessions, so we can't save for non-existent sessions
    if session_id != "global":
        state_manager.save_state(state)

    final_context = "\n\n".join(injected_context) if injected_context else None
    logger.debug(
        f"_evaluate_workflow_triggers returning: context_len={len(final_context) if final_context else 0}, system_message={system_message is not None}"
    )
    return HookResponse(
        decision="allow",
        context=final_context,
        system_message=system_message,
    )


async def evaluate_lifecycle_triggers(
    workflow_name: str,
    event: HookEvent,
    loader: "WorkflowLoader",
    action_executor: "ActionExecutor",
    evaluator: "ConditionEvaluator",
    context_data: dict[str, Any] | None = None,
) -> HookResponse:
    """
    Evaluate triggers for a specific lifecycle workflow (e.g. session-handoff).
    Does not require an active session state.

    Args:
        workflow_name: Name of the workflow to evaluate
        event: The hook event
        loader: Workflow loader
        action_executor: Action executor for running actions
        evaluator: Condition evaluator
        context_data: Optional context data

    Returns:
        HookResponse from the workflow's triggers
    """
    from .actions import ActionContext
    from .definitions import WorkflowState

    # Get project path from event for project-specific workflow lookup
    project_path = event.data.get("cwd") if event.data else None
    logger.debug(
        f"evaluate_lifecycle_triggers: workflow={workflow_name}, project_path={project_path}"
    )

    workflow = loader.load_workflow(workflow_name, project_path=project_path)
    if not workflow:
        logger.warning(f"Workflow '{workflow_name}' not found in project_path={project_path}")
        return HookResponse(decision="allow")

    logger.debug(
        f"Workflow '{workflow_name}' loaded, triggers={list(workflow.triggers.keys()) if workflow.triggers else []}"
    )

    # Map hook event to trigger name (canonical name based on HookEventType)
    trigger_name = f"on_{event.event_type.name.lower()}"  # e.g. on_session_start, on_before_agent

    # Look up triggers - try canonical name first, then aliases
    triggers = []
    if workflow.triggers:
        triggers = workflow.triggers.get(trigger_name, [])
        # If no triggers found, check aliases (e.g., on_prompt_submit for on_before_agent)
        if not triggers:
            aliases = TRIGGER_ALIASES.get(trigger_name, [])
            for alias in aliases:
                triggers = workflow.triggers.get(alias, [])
                if triggers:
                    logger.debug(f"Using alias '{alias}' for trigger '{trigger_name}'")
                    break

    if not triggers:
        logger.debug(f"No triggers for '{trigger_name}' in workflow '{workflow_name}'")
        return HookResponse(decision="allow")

    logger.info(
        f"Executing lifecycle triggers for '{workflow_name}' on '{trigger_name}', count={len(triggers)}"
    )

    # Create a temporary/ephemeral context for execution
    # Create a dummy state for context - lifecycle workflows shouldn't depend on step state
    # but actions might need access to 'state.artifacts' or similar if provided
    session_id = event.metadata.get("_platform_session_id") or "global"

    state = WorkflowState(
        session_id=session_id,
        workflow_name=workflow_name,
        step="global",
        step_entered_at=datetime.now(UTC),
        step_action_count=0,
        total_action_count=0,
        artifacts=event.data.get("artifacts", {}),  # Pass artifacts if available
        observations=[],
        reflection_pending=False,
        context_injected=False,
        variables=context_data or {},  # Pass extra context as variables
        task_list=None,
        current_task_index=0,
        files_modified_this_task=0,
    )

    action_ctx = ActionContext(
        session_id=session_id,
        state=state,
        db=action_executor.db,
        session_manager=action_executor.session_manager,
        template_engine=action_executor.template_engine,
        llm_service=action_executor.llm_service,
        transcript_processor=action_executor.transcript_processor,
        config=action_executor.config,
        mcp_manager=action_executor.mcp_manager,
        memory_manager=action_executor.memory_manager,
        memory_sync_manager=action_executor.memory_sync_manager,
        task_sync_manager=action_executor.task_sync_manager,
        session_task_manager=action_executor.session_task_manager,
        event_data=event.data,  # Pass hook event data (prompt_text, etc.)
    )

    injected_context: list[str] = []
    system_message: str | None = None

    # Fetch session for condition evaluation (enables session.title checks)
    session = None
    if action_executor.session_manager:
        session = action_executor.session_manager.get(session_id)

    for trigger in triggers:
        # Check 'when' condition if present
        when_condition = trigger.get("when")
        if when_condition:
            eval_ctx = {
                "event": event,
                "workflow_state": state,
                "handoff": context_data or {},
                "variables": state.variables,
                "session": session,
            }
            if context_data:
                eval_ctx.update(context_data)
            eval_result = evaluator.evaluate(when_condition, eval_ctx)
            logger.debug(
                f"When condition '{when_condition}' evaluated to {eval_result}, event.data.reason={event.data.get('reason') if event.data else None}"
            )
            if not eval_result:
                continue

        # Execute action
        action_type = trigger.get("action")
        if not action_type:
            continue

        logger.info(f"Executing action '{action_type}' for trigger")
        try:
            # Pass triggers definition as kwargs
            kwargs = trigger.copy()
            kwargs.pop("action", None)
            kwargs.pop("when", None)

            result = await action_executor.execute(action_type, action_ctx, **kwargs)
            logger.debug(
                f"Action '{action_type}' returned: {type(result).__name__}, keys={list(result.keys()) if isinstance(result, dict) else 'N/A'}"
            )

            if result and isinstance(result, dict):
                if context_data is None:
                    context_data = {}

                sys_msg = process_action_result(result, context_data, state, injected_context)
                if sys_msg:
                    system_message = sys_msg

                # Check for blocking decision from action
                if result.get("decision") == "block":
                    return HookResponse(
                        decision="block",
                        reason=result.get("reason", "Blocked by action"),
                        context="\n\n".join(injected_context) if injected_context else None,
                        system_message=system_message,
                    )

        except Exception as e:
            logger.error(f"Failed to execute lifecycle action '{action_type}': {e}", exc_info=True)

    return HookResponse(
        decision="allow",
        context="\n\n".join(injected_context) if injected_context else None,
        system_message=system_message,
    )


async def evaluate_all_lifecycle_workflows(
    event: HookEvent,
    loader: "WorkflowLoader",
    state_manager: "WorkflowStateManager",
    action_executor: "ActionExecutor",
    evaluator: "ConditionEvaluator",
    detect_task_claim_fn: Any,
    detect_plan_mode_fn: Any,
    check_premature_stop_fn: Any,
    context_data: dict[str, Any] | None = None,
    detect_plan_mode_from_context_fn: Any | None = None,
) -> HookResponse:
    """
    Discover and evaluate all lifecycle workflows for the given event.

    Workflows are evaluated in order (project first by priority/alpha, then global).
    Loops until no more triggers fire (up to MAX_TRIGGER_ITERATIONS).

    Args:
        event: The hook event to evaluate
        loader: Workflow loader for discovering workflows
        state_manager: Workflow state manager
        action_executor: Action executor for running actions
        evaluator: Condition evaluator
        detect_task_claim_fn: Function to detect task claims
        detect_plan_mode_fn: Function to detect plan mode (from tool calls)
        check_premature_stop_fn: Async function to check premature stop
        context_data: Optional context data passed between actions
        detect_plan_mode_from_context_fn: Function to detect plan mode from system reminders

    Returns:
        Merged HookResponse with combined context and first non-allow decision.
    """
    from .definitions import WorkflowState

    # Use event.cwd (top-level attribute set by adapter) with fallback to event.data
    # This ensures consistent project_path across all calls, preventing duplicate
    # workflow discovery when cwd is in data but not on the event object
    project_path = event.cwd or (event.data.get("cwd") if event.data else None)

    # Discover all lifecycle workflows
    workflows = loader.discover_lifecycle_workflows(project_path)

    if not workflows:
        logger.debug("No lifecycle workflows discovered")
        return HookResponse(decision="allow")

    logger.debug(
        f"Discovered {len(workflows)} lifecycle workflow(s): {[w.name for w in workflows]}"
    )

    # Accumulate context from all workflows
    all_context: list[str] = []
    final_decision: Literal["allow", "deny", "ask", "block", "modify"] = "allow"
    final_reason: str | None = None
    final_system_message: str | None = None

    # Initialize shared context for chaining between workflows
    if context_data is None:
        context_data = {}

    # Load all session variables from persistent state
    # This enables:
    # - require_task_before_edit (task_claimed variable)
    # - require_task_complete (session_task variable)
    # - worktree detection (is_worktree variable)
    # - any other session-scoped variables set via gobby-workflows MCP tools
    session_id = event.metadata.get("_platform_session_id")
    if session_id:
        lifecycle_state = state_manager.get_state(session_id)
        if lifecycle_state and lifecycle_state.variables:
            context_data.update(lifecycle_state.variables)
            logger.debug(
                f"Loaded {len(lifecycle_state.variables)} session variable(s) "
                f"for {session_id}: {list(lifecycle_state.variables.keys())}"
            )
        elif event.event_type == HookEventType.SESSION_START:
            # New session - check if we should inherit from parent
            parent_id = event.metadata.get("_parent_session_id")
            if parent_id:
                parent_state = state_manager.get_state(parent_id)
                if parent_state and parent_state.variables:
                    # Inherit specific variables
                    inherited = {
                        k: v for k, v in parent_state.variables.items() if k in VARS_TO_INHERIT
                    }
                    if inherited:
                        context_data.update(inherited)
                        logger.info(
                            f"Session {session_id} inherited variables from {parent_id}: {inherited}"
                        )

    # Track which workflow+trigger combinations have already been processed
    # to prevent duplicate execution of the same trigger
    processed_triggers: set[tuple[str, str]] = set()
    trigger_name = f"on_{event.event_type.name.lower()}"

    # Loop until no triggers fire (or max iterations)
    for iteration in range(MAX_TRIGGER_ITERATIONS):
        triggers_fired = False

        for discovered in workflows:
            workflow = discovered.definition

            # Skip if this workflow+trigger has already been processed
            key = (workflow.name, trigger_name)
            if key in processed_triggers:
                continue

            # Merge workflow definition's default variables (lower priority than session state)
            # Precedence: session state > workflow YAML defaults
            workflow_context = {**workflow.variables, **context_data}

            response = await evaluate_workflow_triggers(
                workflow, event, workflow_context, state_manager, action_executor, evaluator
            )

            # Accumulate context
            if response.context:
                all_context.append(response.context)
                triggers_fired = True
                # Mark this workflow+trigger as processed
                processed_triggers.add(key)

            # Capture system_message (last one wins)
            if response.system_message:
                final_system_message = response.system_message

            # First non-allow decision wins
            if response.decision != "allow" and final_decision == "allow":
                final_decision = response.decision
                final_reason = response.reason

            # If blocked, stop immediately
            if response.decision == "block":
                logger.info(f"Workflow '{discovered.name}' blocked event: {response.reason}")
                return HookResponse(
                    decision="block",
                    reason=response.reason,
                    context="\n\n".join(all_context) if all_context else None,
                    system_message=final_system_message,
                )

        # If no triggers fired this iteration, we're done
        if not triggers_fired:
            logger.debug(f"No triggers fired in iteration {iteration + 1}, stopping")
            break

        logger.debug(f"Triggers fired in iteration {iteration + 1}, continuing")

    # Detect task claims for AFTER_TOOL events (session-scoped enforcement)
    # This enables require_task_before_edit to work with lifecycle workflows
    if event.event_type == HookEventType.AFTER_TOOL:
        session_id = event.metadata.get("_platform_session_id")
        if session_id:
            # Get or create a minimal state for tracking task_claimed
            state = state_manager.get_state(session_id)
            if state is None:
                state = WorkflowState(
                    session_id=session_id,
                    workflow_name="__lifecycle__",
                    step="",
                )
            detect_task_claim_fn(event, state)
            detect_plan_mode_fn(event, state)
            state_manager.save_state(state)

    # Detect plan mode from system reminders for BEFORE_AGENT events
    # This catches plan mode when user enters via UI (not via EnterPlanMode tool)
    if event.event_type == HookEventType.BEFORE_AGENT and detect_plan_mode_from_context_fn:
        session_id = event.metadata.get("_platform_session_id")
        if session_id:
            state = state_manager.get_state(session_id)
            if state is None:
                state = WorkflowState(
                    session_id=session_id,
                    workflow_name="__lifecycle__",
                    step="",
                )
            detect_plan_mode_from_context_fn(event, state)
            state_manager.save_state(state)

    # Check for premature stop in active step workflows on STOP events
    if event.event_type == HookEventType.STOP:
        premature_response = await check_premature_stop_fn(event, context_data)
        if premature_response:
            # Merge premature stop response with lifecycle response
            if premature_response.context:
                all_context.append(premature_response.context)
            if premature_response.decision != "allow":
                final_decision = premature_response.decision
                final_reason = premature_response.reason

    return HookResponse(
        decision=final_decision,
        reason=final_reason,
        context="\n\n".join(all_context) if all_context else None,
        system_message=final_system_message,
        metadata={
            "discovered_workflows": [
                {
                    "name": w.name,
                    "priority": w.priority,
                    "is_project": w.is_project,
                    "path": str(w.path),
                }
                for w in workflows
            ],
            "workflow_variables": context_data,
        },
    )
