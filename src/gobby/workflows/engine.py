import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

from gobby.hooks.events import HookEvent, HookEventType, HookResponse
from gobby.storage.workflow_audit import WorkflowAuditManager

from .definitions import WorkflowDefinition, WorkflowState
from .evaluator import ConditionEvaluator, check_approval_response
from .loader import WorkflowLoader
from .state_manager import WorkflowStateManager

if TYPE_CHECKING:
    from .actions import ActionExecutor

logger = logging.getLogger(__name__)


class WorkflowEngine:
    """
    Core engine for executing step-based workflows.
    """

    def __init__(
        self,
        loader: WorkflowLoader,
        state_manager: WorkflowStateManager,
        action_executor: "ActionExecutor",
        evaluator: ConditionEvaluator | None = None,
        audit_manager: WorkflowAuditManager | None = None,
    ):
        self.loader = loader
        self.state_manager = state_manager
        self.action_executor = action_executor
        self.evaluator = evaluator or ConditionEvaluator()
        self.audit_manager = audit_manager

    # Maps canonical trigger names to their legacy aliases for backward compatibility.
    TRIGGER_ALIASES: dict[str, list[str]] = {
        "on_before_agent": ["on_prompt_submit"],
        "on_before_tool": ["on_tool_call"],
        "on_after_tool": ["on_tool_result"],
    }

    async def handle_event(self, event: HookEvent) -> HookResponse:
        """
        Main entry point for hook events.
        """
        session_id = event.metadata.get("_platform_session_id")
        if not session_id:
            return HookResponse(decision="allow")  # No session, no workflow

        # 1. Load state
        state = self.state_manager.get_state(session_id)

        # 2. If no state, check triggers to start one (e.g. on_session_start)
        # Note: This logic might need to move to a specialized trigger handler
        # For now, simplistic check

        if not state:
            # TODO: Logic to load workflow?
            # For now, return allow
            return HookResponse(decision="allow")

        # Check if workflow is temporarily disabled (escape hatch)
        if state.disabled:
            logger.debug(
                f"Workflow '{state.workflow_name}' is disabled for session {session_id}. "
                f"Reason: {state.disabled_reason or 'No reason specified'}"
            )
            return HookResponse(decision="allow")

        # Stuck prevention: Check if step duration exceeding limit
        # This is a basic implementation of "Stuck Detection"
        if state.step_entered_at:
            logger.debug(f"step_entered_at type: {type(state.step_entered_at)}")
            logger.debug(f"step_entered_at value: {state.step_entered_at}")
            diff = datetime.now(UTC) - state.step_entered_at
            logger.debug(f"diff type: {type(diff)}, value: {diff}")
            duration = diff.total_seconds()
            logger.debug(f"duration type: {type(duration)}, value: {duration}")
            # Hardcoded limit for MVP: 30 minutes
            if duration > 1800:
                # Force transition to reflect if not already there
                if state.step != "reflect":
                    workflow = self.loader.load_workflow(state.workflow_name)
                    if workflow and workflow.get_step("reflect"):
                        await self.transition_to(state, "reflect", workflow)
                        return HookResponse(
                            decision="modify",
                            context="[System Alert] Step duration limit exceeded. Transitioning to 'reflect' step.",
                        )

        # 3. Load definition
        # Skip if this is a lifecycle-only state (used for task_claimed tracking)
        if state.workflow_name == "__lifecycle__":
            logger.debug(
                f"Skipping step workflow handling for lifecycle state in session {session_id}"
            )
            return HookResponse(decision="allow")

        workflow = self.loader.load_workflow(state.workflow_name)
        if not workflow:
            logger.error(f"Workflow '{state.workflow_name}' not found for session {session_id}")
            return HookResponse(decision="allow")

        # 4. Process event
        # Logic matches WORKFLOWS.md "Evaluation Flow"

        # Determine context for evaluation
        eval_context = {
            "event": event,
            "workflow_state": state,
            "session": {},  # TODO: Attach session info
            "tool_name": event.data.get("tool_name"),
            "tool_args": event.data.get("tool_args", {}),
        }

        current_step = workflow.get_step(state.step)
        if not current_step:
            logger.error(f"Step '{state.step}' not found in workflow '{workflow.name}'")
            return HookResponse(decision="allow")

        # Handle approval flow on user prompt submit
        if event.event_type == HookEventType.BEFORE_AGENT:
            approval_response = self._handle_approval_response(event, state, current_step)
            if approval_response:
                return approval_response

        # Check blocked tools
        if event.event_type == HookEventType.BEFORE_TOOL:
            # Block tool calls while waiting for approval
            if state.approval_pending:
                reason = "Waiting for user approval. Please respond with 'yes' or 'no'."
                self._log_tool_call(session_id, state.step, "unknown", "block", reason)
                return HookResponse(decision="block", reason=reason)
            tool_name = eval_context["tool_name"]

            # Check blocked list
            if tool_name in current_step.blocked_tools:
                reason = f"Tool '{tool_name}' is blocked in step '{state.step}'."
                self._log_tool_call(session_id, state.step, tool_name, "block", reason)
                return HookResponse(decision="block", reason=reason)

            # Check allowed list (if not "all")
            if current_step.allowed_tools != "all":
                if tool_name not in current_step.allowed_tools:
                    reason = f"Tool '{tool_name}' is not in allowed list for step '{state.step}'."
                    self._log_tool_call(session_id, state.step, tool_name, "block", reason)
                    return HookResponse(decision="block", reason=reason)

            # Check rules
            for rule in current_step.rules:
                if self.evaluator.evaluate(rule.when, eval_context):
                    if rule.action == "block":
                        reason = rule.message or "Blocked by workflow rule."
                        self._log_rule_eval(
                            session_id,
                            state.step,
                            rule.name or "unnamed",
                            rule.when,
                            "block",
                            reason,
                        )
                        return HookResponse(decision="block", reason=reason)
                    # Handle other actions like warn, require_approval

            # Log successful tool allow
            self._log_tool_call(session_id, state.step, tool_name, "allow")

        # Check transitions
        logger.debug("Checking transitions")
        for transition in current_step.transitions:
            if self.evaluator.evaluate(transition.when, eval_context):
                # Transition!
                await self.transition_to(state, transition.to, workflow)
                return HookResponse(
                    decision="modify", context=f"Transitioning to step: {transition.to}"
                )

        # Check exit conditions
        logger.debug("Checking exit conditions")
        if self.evaluator.check_exit_conditions(current_step.exit_conditions, state):
            # TODO: Determine next step or completion logic
            # For now, simplistic 'next step' if linear, or rely on transitions
            pass

        # Update stats (generic)
        if event.event_type == HookEventType.AFTER_TOOL:
            state.step_action_count += 1
            state.total_action_count += 1

            # Detect gobby-tasks calls for session-scoped task claiming
            self._detect_task_claim(event, state)

            self.state_manager.save_state(state)  # Persist updates

        return HookResponse(decision="allow")

    async def transition_to(
        self, state: WorkflowState, new_step_name: str, workflow: WorkflowDefinition
    ) -> None:
        """
        Execute transition logic.
        """
        old_step = workflow.get_step(state.step)
        new_step = workflow.get_step(new_step_name)

        if not new_step:
            logger.error(f"Cannot transition to unknown step '{new_step_name}'")
            return

        logger.info(
            f"Transitioning session {state.session_id} from '{state.step}' to '{new_step_name}'"
        )

        # Log the transition
        self._log_transition(state.session_id, state.step, new_step_name)

        # Execute on_exit of old step
        if old_step:
            await self._execute_actions(old_step.on_exit, state)

        # Update state
        state.step = new_step_name
        state.step_entered_at = datetime.now(UTC)
        state.step_action_count = 0
        state.context_injected = False  # Reset for new step context

        self.state_manager.save_state(state)

        # Execute on_enter of new step
        await self._execute_actions(new_step.on_enter, state)

    async def _execute_actions(self, actions: list[dict], state: WorkflowState) -> None:
        """
        Execute a list of actions.
        """
        from .actions import ActionContext

        context = ActionContext(
            session_id=state.session_id,
            state=state,
            db=self.action_executor.db,
            session_manager=self.action_executor.session_manager,
            template_engine=self.action_executor.template_engine,
            llm_service=self.action_executor.llm_service,
            transcript_processor=self.action_executor.transcript_processor,
            config=self.action_executor.config,
            mcp_manager=self.action_executor.mcp_manager,
            memory_manager=self.action_executor.memory_manager,
            skill_learner=self.action_executor.skill_learner,
            memory_sync_manager=self.action_executor.memory_sync_manager,
        )

        for action_def in actions:
            action_type = action_def.get("action")
            if not action_type:
                continue

            result = await self.action_executor.execute(action_type, context, **action_def)

            if result and "inject_context" in result:
                # Log context injection for now
                logger.info(f"Context injected: {result['inject_context'][:50]}...")

    def _handle_approval_response(
        self,
        event: HookEvent,
        state: WorkflowState,
        current_step: Any,
    ) -> HookResponse | None:
        """
        Handle user response to approval request.

        Called on BEFORE_AGENT events to check if user is responding to
        a pending approval request.

        Returns:
            HookResponse if approval was handled, None otherwise.
        """
        # Get user prompt from event
        prompt = event.data.get("prompt", "") if event.data else ""

        # Check if we're waiting for approval
        if state.approval_pending:
            response = check_approval_response(prompt)

            if response == "approved":
                # Mark approval granted
                condition_id = state.approval_condition_id
                approved_var = f"_approval_{condition_id}_granted"
                state.variables[approved_var] = True
                state.approval_pending = False
                state.approval_condition_id = None
                state.approval_prompt = None
                state.approval_requested_at = None
                self.state_manager.save_state(state)

                logger.info(f"User approved condition '{condition_id}' in step '{state.step}'")
                return HookResponse(
                    decision="allow",
                    context=f"✓ Approval granted for: {state.approval_prompt or 'action'}",
                )

            elif response == "rejected":
                # Mark approval rejected
                condition_id = state.approval_condition_id
                rejected_var = f"_approval_{condition_id}_rejected"
                state.variables[rejected_var] = True
                state.approval_pending = False
                state.approval_condition_id = None
                state.approval_prompt = None
                state.approval_requested_at = None
                self.state_manager.save_state(state)

                logger.info(f"User rejected condition '{condition_id}' in step '{state.step}'")
                return HookResponse(
                    decision="block",
                    reason="User rejected the approval request.",
                )

            else:
                # User didn't respond with approval keyword - remind them
                return HookResponse(
                    decision="allow",
                    context=(
                        f"⏳ **Waiting for approval:** {state.approval_prompt}\n\n"
                        f"Please respond with 'yes' or 'no' to continue."
                    ),
                )

        # Check if we need to request approval
        approval_check = self.evaluator.check_pending_approval(current_step.exit_conditions, state)

        if approval_check and approval_check.needs_approval:
            # Set approval pending state
            state.approval_pending = True
            state.approval_condition_id = approval_check.condition_id
            state.approval_prompt = approval_check.prompt
            state.approval_requested_at = datetime.now(UTC)
            state.approval_timeout_seconds = approval_check.timeout_seconds
            self.state_manager.save_state(state)

            logger.info(
                f"Requesting approval for condition '{approval_check.condition_id}' "
                f"in step '{state.step}'"
            )
            return HookResponse(
                decision="allow",
                context=(
                    f"🔔 **Approval Required**\n\n"
                    f"{approval_check.prompt}\n\n"
                    f"Please respond with 'yes' to approve or 'no' to reject."
                ),
            )

        if approval_check and approval_check.is_timed_out:
            # Timeout - treat as rejection
            condition_id = approval_check.condition_id
            rejected_var = f"_approval_{condition_id}_rejected"
            state.variables[rejected_var] = True
            state.approval_pending = False
            state.approval_condition_id = None
            self.state_manager.save_state(state)

            logger.info(f"Approval timed out for condition '{condition_id}'")
            return HookResponse(
                decision="block",
                reason=f"Approval request timed out after {approval_check.timeout_seconds} seconds.",
            )

        return None

    # Maximum iterations to prevent infinite loops
    MAX_TRIGGER_ITERATIONS = 10

    async def evaluate_all_lifecycle_workflows(
        self, event: HookEvent, context_data: dict[str, Any] | None = None
    ) -> HookResponse:
        """
        Discover and evaluate all lifecycle workflows for the given event.

        Workflows are evaluated in order (project first by priority/alpha, then global).
        Loops until no more triggers fire (up to MAX_TRIGGER_ITERATIONS).

        Args:
            event: The hook event to evaluate
            context_data: Optional context data passed between actions

        Returns:
            Merged HookResponse with combined context and first non-allow decision.
        """
        project_path = event.data.get("cwd") if event.data else None

        # Discover all lifecycle workflows
        workflows = self.loader.discover_lifecycle_workflows(project_path)

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
            lifecycle_state = self.state_manager.get_state(session_id)
            if lifecycle_state and lifecycle_state.variables:
                context_data.update(lifecycle_state.variables)
                logger.debug(
                    f"Loaded {len(lifecycle_state.variables)} session variable(s) "
                    f"for {session_id}: {list(lifecycle_state.variables.keys())}"
                )

        # Track which workflow+trigger combinations have already been processed
        # to prevent duplicate execution of the same trigger
        processed_triggers: set[tuple[str, str]] = set()
        trigger_name = f"on_{event.event_type.name.lower()}"

        # Loop until no triggers fire (or max iterations)
        for iteration in range(self.MAX_TRIGGER_ITERATIONS):
            triggers_fired = False

            for discovered in workflows:
                workflow = discovered.definition

                # Skip if this workflow+trigger has already been processed
                key = (workflow.name, trigger_name)
                if key in processed_triggers:
                    continue

                response = await self._evaluate_workflow_triggers(workflow, event, context_data)

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
                state = self.state_manager.get_state(session_id)
                if state is None:
                    state = WorkflowState(
                        session_id=session_id,
                        workflow_name="__lifecycle__",
                        step="",
                    )
                self._detect_task_claim(event, state)
                self.state_manager.save_state(state)

        return HookResponse(
            decision=final_decision,
            reason=final_reason,
            context="\n\n".join(all_context) if all_context else None,
            system_message=final_system_message,
        )

    async def _evaluate_workflow_triggers(
        self,
        workflow: "WorkflowDefinition",
        event: HookEvent,
        context_data: dict[str, Any],
    ) -> HookResponse:
        """
        Evaluate triggers for a single workflow definition.

        Args:
            workflow: The workflow definition to evaluate
            event: The hook event
            context_data: Shared context for chaining (mutated by actions)

        Returns:
            HookResponse from this workflow's triggers
        """
        from .definitions import WorkflowState

        # Map hook event to trigger name
        trigger_name = f"on_{event.event_type.name.lower()}"

        # Look up triggers - try canonical name first, then aliases
        triggers = []
        if workflow.triggers:
            triggers = workflow.triggers.get(trigger_name, [])
            if not triggers:
                aliases = self.TRIGGER_ALIASES.get(trigger_name, [])
                for alias in aliases:
                    triggers = workflow.triggers.get(alias, [])
                    if triggers:
                        break

        if not triggers:
            return HookResponse(decision="allow")

        logger.debug(
            f"Evaluating {len(triggers)} trigger(s) for '{trigger_name}' "
            f"in workflow '{workflow.name}'"
        )

        # Create ephemeral state for action execution
        from .actions import ActionContext

        session_id = event.metadata.get("_platform_session_id") or "global"

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
            variables=context_data,
            task_list=None,
            current_task_index=0,
            files_modified_this_task=0,
        )

        action_ctx = ActionContext(
            session_id=session_id,
            state=state,
            db=self.action_executor.db,
            session_manager=self.action_executor.session_manager,
            template_engine=self.action_executor.template_engine,
            llm_service=self.action_executor.llm_service,
            transcript_processor=self.action_executor.transcript_processor,
            config=self.action_executor.config,
            mcp_manager=self.action_executor.mcp_manager,
            memory_manager=self.action_executor.memory_manager,
            skill_learner=self.action_executor.skill_learner,
            memory_sync_manager=self.action_executor.memory_sync_manager,
            event_data=event.data,  # Pass hook event data (prompt_text, etc.)
        )

        injected_context: list[str] = []
        system_message: str | None = None

        for trigger in triggers:
            # Check 'when' condition if present
            when_condition = trigger.get("when")
            if when_condition:
                eval_ctx = {
                    "event": event,
                    "workflow_state": state,
                    "handoff": context_data,
                    "variables": state.variables,
                }
                eval_ctx.update(context_data)
                eval_result = self.evaluator.evaluate(when_condition, eval_ctx)
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

                result = await self.action_executor.execute(action_type, action_ctx, **kwargs)
                logger.debug(
                    f"Action '{action_type}' result: {type(result)}, keys={list(result.keys()) if isinstance(result, dict) else 'N/A'}"
                )

                if result and isinstance(result, dict):
                    # Update shared context for chaining
                    context_data.update(result)
                    state.variables.update(result)

                    if "inject_context" in result:
                        injected_context.append(result["inject_context"])
                        logger.debug(
                            f"Added to injected_context, now has {len(injected_context)} items, total chars={sum(len(c) for c in injected_context)}"
                        )

                    # Capture system_message (last one wins)
                    if "system_message" in result:
                        system_message = result["system_message"]

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
        self, workflow_name: str, event: HookEvent, context_data: dict[str, Any] | None = None
    ) -> HookResponse:
        """
        Evaluate triggers for a specific lifecycle workflow (e.g. session-handoff).
        Does not require an active session state.
        """
        # Get project path from event for project-specific workflow lookup
        project_path = event.data.get("cwd") if event.data else None
        logger.debug(
            f"evaluate_lifecycle_triggers: workflow={workflow_name}, project_path={project_path}"
        )

        workflow = self.loader.load_workflow(workflow_name, project_path=project_path)
        if not workflow:
            logger.warning(f"Workflow '{workflow_name}' not found in project_path={project_path}")
            return HookResponse(decision="allow")

        logger.debug(
            f"Workflow '{workflow_name}' loaded, triggers={list(workflow.triggers.keys()) if workflow.triggers else []}"
        )

        # Map hook event to trigger name (canonical name based on HookEventType)
        trigger_name = (
            f"on_{event.event_type.name.lower()}"  # e.g. on_session_start, on_before_agent
        )

        # Look up triggers - try canonical name first, then aliases
        triggers = []
        if workflow.triggers:
            triggers = workflow.triggers.get(trigger_name, [])
            # If no triggers found, check aliases (e.g., on_prompt_submit for on_before_agent)
            if not triggers:
                aliases = self.TRIGGER_ALIASES.get(trigger_name, [])
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
        from .actions import ActionContext
        from .definitions import WorkflowState

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
            db=self.action_executor.db,
            session_manager=self.action_executor.session_manager,
            template_engine=self.action_executor.template_engine,
            llm_service=self.action_executor.llm_service,
            transcript_processor=self.action_executor.transcript_processor,
            config=self.action_executor.config,
            mcp_manager=self.action_executor.mcp_manager,
            memory_manager=self.action_executor.memory_manager,
            skill_learner=self.action_executor.skill_learner,
            memory_sync_manager=self.action_executor.memory_sync_manager,
            event_data=event.data,  # Pass hook event data (prompt_text, etc.)
        )

        injected_context: list[str] = []
        system_message: str | None = None

        for trigger in triggers:
            # Check 'when' condition if present
            when_condition = trigger.get("when")
            if when_condition:
                # Simple eval context - include variables for conditions like variables.get('session_task')
                eval_ctx = {
                    "event": event,
                    "workflow_state": state,
                    "handoff": context_data or {},
                    "variables": state.variables,
                }
                if context_data:
                    eval_ctx.update(context_data)
                eval_result = self.evaluator.evaluate(when_condition, eval_ctx)
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

                result = await self.action_executor.execute(action_type, action_ctx, **kwargs)
                logger.debug(
                    f"Action '{action_type}' returned: {type(result).__name__}, keys={list(result.keys()) if isinstance(result, dict) else 'N/A'}"
                )

                if result:
                    # Update context for subsequent actions
                    if isinstance(result, dict):
                        if context_data is None:
                            context_data = {}
                        context_data.update(result)
                        state.variables.update(result)

                    if "inject_context" in result:
                        logger.debug(
                            f"Found inject_context in result, length={len(result['inject_context'])}"
                        )
                        injected_context.append(result["inject_context"])

                    # Capture system_message (last one wins)
                    if "system_message" in result:
                        system_message = result["system_message"]

                    # Check for blocking decision from action
                    if isinstance(result, dict) and result.get("decision") == "block":
                        return HookResponse(
                            decision="block",
                            reason=result.get("reason", "Blocked by action"),
                            context="\n\n".join(injected_context) if injected_context else None,
                            system_message=system_message,
                        )

            except Exception as e:
                logger.error(
                    f"Failed to execute lifecycle action '{action_type}': {e}", exc_info=True
                )

        return HookResponse(
            decision="allow",
            context="\n\n".join(injected_context) if injected_context else None,
            system_message=system_message,
        )

    # --- Audit Logging Helpers ---

    def _log_tool_call(
        self,
        session_id: str,
        step: str,
        tool_name: str,
        result: str,
        reason: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Log a tool call permission check to the audit log."""
        if self.audit_manager:
            try:
                self.audit_manager.log_tool_call(
                    session_id=session_id,
                    step=step,
                    tool_name=tool_name,
                    result=result,
                    reason=reason,
                    context=context,
                )
            except Exception as e:
                logger.debug(f"Failed to log tool call audit: {e}")

    def _log_rule_eval(
        self,
        session_id: str,
        step: str,
        rule_id: str,
        condition: str,
        result: str,
        reason: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Log a rule evaluation to the audit log."""
        if self.audit_manager:
            try:
                self.audit_manager.log_rule_eval(
                    session_id=session_id,
                    step=step,
                    rule_id=rule_id,
                    condition=condition,
                    result=result,
                    reason=reason,
                    context=context,
                )
            except Exception as e:
                logger.debug(f"Failed to log rule eval audit: {e}")

    def _log_transition(
        self,
        session_id: str,
        from_step: str,
        to_step: str,
        reason: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Log a step transition to the audit log."""
        if self.audit_manager:
            try:
                self.audit_manager.log_transition(
                    session_id=session_id,
                    from_step=from_step,
                    to_step=to_step,
                    reason=reason,
                    context=context,
                )
            except Exception as e:
                logger.debug(f"Failed to log transition audit: {e}")

    def _log_approval(
        self,
        session_id: str,
        step: str,
        result: str,
        condition_id: str | None = None,
        prompt: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Log an approval gate event to the audit log."""
        if self.audit_manager:
            try:
                self.audit_manager.log_approval(
                    session_id=session_id,
                    step=step,
                    result=result,
                    condition_id=condition_id,
                    prompt=prompt,
                    context=context,
                )
            except Exception as e:
                logger.debug(f"Failed to log approval audit: {e}")

    def _detect_task_claim(self, event: HookEvent, state: WorkflowState) -> None:
        """Detect gobby-tasks calls that claim or release a task for this session.

        Sets `task_claimed: true` in workflow state variables when the agent
        successfully creates a task or updates a task to in_progress status.

        Clears `task_claimed: false` when the agent closes a task, requiring
        them to claim another task before making further file modifications.

        This enables session-scoped task enforcement where each session must
        explicitly claim a task rather than free-riding on project-wide checks.

        Args:
            event: The AFTER_TOOL hook event
            state: Current workflow state (modified in place)
        """
        if not event.data:
            return

        tool_name = event.data.get("tool_name", "")
        tool_input = event.data.get("tool_input", {}) or {}
        tool_output = event.data.get("tool_output", {}) or {}

        # Check if this is a gobby-tasks call via MCP proxy
        # Tool name could be "call_tool" (from Skill) or "mcp__gobby__call_tool" (direct)
        if tool_name not in ("call_tool", "mcp__gobby__call_tool"):
            return

        # Check server is gobby-tasks
        server_name = tool_input.get("server_name", "")
        if server_name != "gobby-tasks":
            return

        # Check inner tool name
        inner_tool_name = tool_input.get("tool_name", "")
        if inner_tool_name not in ("create_task", "update_task", "close_task"):
            return

        # For update_task, only count if status is being set to in_progress
        if inner_tool_name == "update_task":
            arguments = tool_input.get("arguments", {}) or {}
            if arguments.get("status") != "in_progress":
                return

        # For close_task, we'll clear task_claimed after success check
        is_close_task = inner_tool_name == "close_task"

        # Check if the call succeeded (not an error)
        # tool_output structure varies, but errors typically have "error" key
        # or the MCP response has "status": "error"
        if isinstance(tool_output, dict):
            if tool_output.get("error") or tool_output.get("status") == "error":
                return
            # Also check nested result for MCP proxy responses
            result = tool_output.get("result", {})
            if isinstance(result, dict) and result.get("error"):
                return

        # Handle close_task - clear the claim
        if is_close_task:
            state.variables["task_claimed"] = False
            state.variables["claimed_task_id"] = None
            logger.info(
                f"Session {state.session_id}: task_claimed=False (task closed via close_task)"
            )
            return

        # Extract task_id based on tool type
        arguments = tool_input.get("arguments", {}) or {}
        if inner_tool_name == "update_task":
            task_id = arguments.get("task_id")
        elif inner_tool_name == "create_task":
            # For create_task, the id is in the result
            result = tool_output.get("result", {}) if isinstance(tool_output, dict) else {}
            task_id = result.get("id") if isinstance(result, dict) else None
        else:
            task_id = None

        # All conditions met - set task_claimed and claimed_task_id
        state.variables["task_claimed"] = True
        state.variables["claimed_task_id"] = task_id
        logger.info(
            f"Session {state.session_id}: task_claimed=True, claimed_task_id={task_id} "
            f"(via {inner_tool_name})"
        )

        # Auto-link task to session when status is set to in_progress
        if inner_tool_name == "update_task":
            arguments = tool_input.get("arguments", {}) or {}
            task_id = arguments.get("task_id")
            session_task_mgr = getattr(self.action_executor, "session_task_manager", None)
            if task_id and session_task_mgr:
                try:
                    session_task_mgr.link_task(state.session_id, task_id, "worked_on")
                    logger.info(f"Auto-linked task {task_id} to session {state.session_id}")
                except Exception as e:
                    logger.warning(f"Failed to auto-link task {task_id}: {e}")
