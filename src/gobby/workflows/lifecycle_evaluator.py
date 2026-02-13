"""
Lifecycle workflow evaluation for workflow engine.

Extracted from engine.py to reduce complexity.
Handles discovery and evaluation of lifecycle workflows and their triggers.
"""

import copy
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

from gobby.hooks.events import HookEvent, HookEventType, HookResponse
from gobby.workflows.definitions import WorkflowDefinition, WorkflowState
from gobby.workflows.unified_evaluator import _TRIGGER_KEY_MAP

if TYPE_CHECKING:
    from .actions import ActionExecutor
    from .evaluator import ConditionEvaluator
    from .loader import WorkflowLoader
    from .observers import ObserverEngine
    from .state_manager import WorkflowStateManager

logger = logging.getLogger(__name__)


def _compute_variable_diff(before: dict[str, Any] | None, after: dict[str, Any]) -> dict[str, Any]:
    """Compute which variables changed between before and after snapshots."""
    if before is None:
        return dict(after)
    return {k: v for k, v in after.items() if k not in before or before[k] != v}


# Maximum iterations to prevent infinite loops in trigger evaluation
MAX_TRIGGER_ITERATIONS = 10

# Variables to inherit from parent session
VARS_TO_INHERIT: list[str] = []

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


def _persist_state_changes(
    session_id: str,
    state: "WorkflowState",
    state_was_created: bool,
    vars_snapshot: dict[str, Any] | None,
    state_manager: "WorkflowStateManager",
    workflow: "WorkflowDefinition | None" = None,
) -> None:
    """Persist workflow state changes to the database.

    Handles both newly-created states and existing states (via atomic variable merge).
    Skips persistence for the synthetic "global" session ID.
    When workflow is None, skips the is_step_workflow check and always saves new states.
    """
    if session_id == "global":
        return

    if state_was_created:
        if workflow is not None:
            current_state = state_manager.get_state(session_id)
            is_step_workflow = (
                current_state is not None
                and current_state.workflow_name not in ("__lifecycle__", "__ended__")
                and current_state.workflow_name != workflow.name
            )
            if is_step_workflow:
                return
        state_manager.save_state(state)
    else:
        changed_vars = _compute_variable_diff(vars_snapshot, state.variables)
        if changed_vars:
            state_manager.merge_variables(session_id, changed_vars)


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
    trigger_name = _TRIGGER_KEY_MAP.get(event.event_type, f"on_{event.event_type.name.lower()}")

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

    # Evaluate top-level tool_rules on BEFORE_TOOL events (before triggers)
    has_tool_rules = event.event_type == HookEventType.BEFORE_TOOL and getattr(
        workflow, "tool_rules", None
    )

    if not triggers and not has_tool_rules:
        return HookResponse(decision="allow")

    logger.debug(
        f"Evaluating workflow '{workflow.name}': "
        f"{len(triggers)} trigger(s) for '{trigger_name}', "
        f"{len(workflow.tool_rules) if has_tool_rules else 0} tool_rule(s)"
    )

    # Get or create persisted state for action execution
    # This ensures variables like _injected_memory_ids persist across hook calls
    session_id = event.metadata.get("_platform_session_id") or "global"

    # Try to load existing state, or create new one
    # Track whether we created a new state to determine save behavior later
    existing_state = state_manager.get_state(session_id)
    state_was_created = existing_state is None
    state: WorkflowState = existing_state or WorkflowState(
        session_id=session_id,
        workflow_name=workflow.name,
        step="global",
        step_entered_at=datetime.now(UTC),
        step_action_count=0,
        total_action_count=0,
        observations=[],
        reflection_pending=False,
        context_injected=False,
        variables={},
        task_list=None,
        current_task_index=0,
        files_modified_this_task=0,
    )

    # Snapshot variables before evaluation so we can diff later
    # Use deepcopy to catch in-place mutations (e.g., list.append in track_schema_lookup)
    vars_snapshot = copy.deepcopy(state.variables) if not state_was_created else None

    # Merge context_data (workflow defaults) into state variables
    # Persisted state values take precedence over workflow defaults
    if context_data:
        state.variables = {**context_data, **state.variables}

    # Session variables (from session_variables table, written by MCP set_variable)
    # must override workflow_states.variables since MCP is the agent-facing API.
    _sv_override = context_data.get("_session_variables_override") if context_data else None
    if _sv_override:
        state.variables.update(_sv_override)

    action_ctx = ActionContext(
        session_id=session_id,
        state=state,
        db=action_executor.db,
        session_manager=action_executor.session_manager,
        template_engine=action_executor.template_engine,
        llm_service=action_executor.llm_service,
        transcript_processor=action_executor.transcript_processor,
        config=action_executor.config,
        tool_proxy_getter=action_executor.tool_proxy_getter,
        memory_manager=action_executor.memory_manager,
        memory_sync_manager=action_executor.memory_sync_manager,
        task_sync_manager=action_executor.task_sync_manager,
        session_task_manager=action_executor.session_task_manager,
        skill_manager=action_executor.skill_manager,
        event_data=event.data,  # Pass hook event data (prompt_text, etc.)
    )

    injected_context: list[str] = []
    system_message: str | None = None

    # Evaluate tool_rules before triggers (runs block_tools directly)
    if has_tool_rules:
        from gobby.workflows.enforcement.blocking import block_tools

        block_result = await block_tools(
            rules=workflow.tool_rules,
            event_data=event.data,
            workflow_state=state,
        )
        if block_result and block_result.get("decision") == "block":
            _persist_state_changes(
                session_id, state, state_was_created, vars_snapshot, state_manager, workflow
            )
            return HookResponse(
                decision="block",
                reason=block_result.get("reason", "Blocked by tool_rules"),
            )

    # Fetch session for condition evaluation (enables session.title checks)
    session = None
    if action_executor.session_manager:
        session = action_executor.session_manager.get(session_id)

    # Compute task_has_commits for condition evaluation (same logic as blocking.py)
    task_has_commits = False
    if action_executor.task_manager and state:
        claimed_task_id = state.variables.get("claimed_task_id")
        if claimed_task_id:
            try:
                task = action_executor.task_manager.get_task(claimed_task_id)
                task_has_commits = bool(task and task.commits)
            except (KeyError, AttributeError, ValueError) as e:
                logger.debug("Failed to check commits for task %s: %s", claimed_task_id, e)

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
                "task_has_commits": task_has_commits,
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
                    _persist_state_changes(
                        session_id, state, state_was_created, vars_snapshot, state_manager, workflow
                    )
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

    # Persist state changes (e.g., _injected_memory_ids from memory_recall_relevant,
    # unlocked_tools from track_schema_lookup)
    _persist_state_changes(
        session_id, state, state_was_created, vars_snapshot, state_manager, workflow
    )

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

    workflow = await loader.load_workflow(workflow_name, project_path=project_path)
    if not workflow:
        logger.warning(f"Workflow '{workflow_name}' not found in project_path={project_path}")
        return HookResponse(decision="allow")

    # Lifecycle triggers only apply to WorkflowDefinition, not PipelineDefinition
    if not isinstance(workflow, WorkflowDefinition):
        logger.debug(f"Workflow '{workflow_name}' is not a WorkflowDefinition, skipping triggers")
        return HookResponse(decision="allow")

    logger.debug(
        f"Workflow '{workflow_name}' loaded, triggers={list(workflow.triggers.keys()) if workflow.triggers else []}"
    )

    # Map hook event to trigger name (canonical name based on HookEventType)
    trigger_name = _TRIGGER_KEY_MAP.get(event.event_type, f"on_{event.event_type.name.lower()}")

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
    session_id = event.metadata.get("_platform_session_id") or "global"

    state = WorkflowState(
        session_id=session_id,
        workflow_name=workflow_name,
        step="global",
        step_entered_at=datetime.now(UTC),
        step_action_count=0,
        total_action_count=0,
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
        tool_proxy_getter=action_executor.tool_proxy_getter,
        memory_manager=action_executor.memory_manager,
        memory_sync_manager=action_executor.memory_sync_manager,
        task_sync_manager=action_executor.task_sync_manager,
        session_task_manager=action_executor.session_task_manager,
        skill_manager=action_executor.skill_manager,
        event_data=event.data,  # Pass hook event data (prompt_text, etc.)
    )

    injected_context: list[str] = []
    system_message: str | None = None

    # Fetch session for condition evaluation (enables session.title checks)
    session = None
    if action_executor.session_manager:
        session = action_executor.session_manager.get(session_id)

    # Compute task_has_commits for condition evaluation (same logic as blocking.py)
    task_has_commits = False
    if action_executor.task_manager and state:
        claimed_task_id = state.variables.get("claimed_task_id")
        if claimed_task_id:
            try:
                task = action_executor.task_manager.get_task(claimed_task_id)
                task_has_commits = bool(task and task.commits)
            except (KeyError, AttributeError, ValueError) as e:
                logger.debug("Failed to check commits for task %s: %s", claimed_task_id, e)

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
                "task_has_commits": task_has_commits,
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
    check_premature_stop_fn: Any,
    context_data: dict[str, Any] | None = None,
    observer_engine: "ObserverEngine | None" = None,
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
        check_premature_stop_fn: Async function to check premature stop
        context_data: Optional context data passed between actions
        observer_engine: Optional ObserverEngine for evaluating YAML/behavior observers

    Returns:
        Merged HookResponse with combined context and first non-allow decision.
    """

    # Use event.cwd (top-level attribute set by adapter) with fallback to event.data
    # This ensures consistent project_path across all calls, preventing duplicate
    # workflow discovery when cwd is in data but not on the event object
    project_path = event.cwd or (event.data.get("cwd") if event.data else None)

    # Discover all lifecycle workflows
    workflows = await loader.discover_lifecycle_workflows(project_path)

    if not workflows:
        logger.debug("No lifecycle workflows discovered")
        return HookResponse(decision="allow")

    # Filter by source if workflow specifies sources
    if event.source:
        source_val = event.source.value if hasattr(event.source, "value") else str(event.source)
        workflows = [
            w
            for w in workflows
            if not isinstance(w.definition, WorkflowDefinition)
            or (srcs := getattr(w.definition, "sources", None)) is None
            or source_val in srcs
        ]

    # Filter out disabled (on-demand) workflows - they only activate manually
    workflows = [
        w
        for w in workflows
        if not isinstance(w.definition, WorkflowDefinition) or w.definition.enabled
    ]

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

        # Also load session_variables table (written by MCP set_variable tool).
        # These must override workflow_states.variables because the MCP tool is
        # the agent-facing API and should be authoritative. We store them in a
        # special key so evaluate_workflow_triggers can apply them after the
        # state merge (which otherwise gives workflow_states priority).
        try:
            from gobby.workflows.state_manager import SessionVariableManager

            session_var_mgr = SessionVariableManager(state_manager.db)
            session_vars = session_var_mgr.get_variables(session_id)
            if session_vars:
                context_data.update(session_vars)
                context_data["_session_variables_override"] = session_vars
                logger.debug(
                    f"Loaded {len(session_vars)} session_variables for {session_id}: "
                    f"{list(session_vars.keys())}"
                )
        except (ImportError, KeyError, AttributeError) as e:
            # Recoverable: module not available, session not found, or
            # state_manager.db missing — skip session variable loading.
            logger.debug(f"Could not load session_variables: {e}")
        except Exception as e:
            logger.warning(
                f"Unexpected error loading session_variables for {session_id}: {e}",
                exc_info=True,
            )

        missing_lifecycle_vars = not lifecycle_state or not lifecycle_state.variables
        if missing_lifecycle_vars and event.event_type == HookEventType.SESSION_START:
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
    trigger_name = _TRIGGER_KEY_MAP.get(event.event_type, f"on_{event.event_type.name.lower()}")

    # Loop until no triggers fire (or max iterations)
    for iteration in range(MAX_TRIGGER_ITERATIONS):
        triggers_fired = False

        for discovered in workflows:
            workflow = discovered.definition

            # Skip PipelineDefinition - lifecycle triggers only for WorkflowDefinition
            if not isinstance(workflow, WorkflowDefinition):
                continue

            # Skip if this workflow+trigger has already been processed
            key = (workflow.name, trigger_name)
            if key in processed_triggers:
                continue

            # Merge workflow definition's default variables (lower priority than session state)
            # Precedence: session state > workflow YAML defaults
            # Update context_data directly so workflow variables propagate to response metadata
            context_data = {**workflow.variables, **context_data}

            response = await evaluate_workflow_triggers(
                workflow, event, context_data, state_manager, action_executor, evaluator
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

    # Evaluate observers for all lifecycle workflows
    if observer_engine is not None:
        event_type_str = event.event_type.name.lower()
        for discovered in workflows:
            workflow = discovered.definition
            if not isinstance(workflow, WorkflowDefinition):
                continue
            if not workflow.observers:
                continue

            obs_session_id = event.metadata.get("_platform_session_id")
            if not obs_session_id:
                continue

            existing_state = state_manager.get_state(obs_session_id)
            state_was_created = existing_state is None
            state = existing_state or WorkflowState(
                session_id=obs_session_id,
                workflow_name=workflow.name,
                step="global",
            )
            vars_snapshot = copy.deepcopy(state.variables) if not state_was_created else None

            await observer_engine.evaluate_observers(
                observers=workflow.observers,
                event_type=event_type_str,
                event_data=event.data or {},
                state=state,
                event=event,
                task_manager=getattr(action_executor, "task_manager", None),
                session_task_manager=getattr(action_executor, "session_task_manager", None),
            )

            _persist_state_changes(
                obs_session_id, state, state_was_created, vars_snapshot, state_manager
            )

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
