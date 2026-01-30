import logging
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from gobby.hooks.events import HookEvent, HookEventType, HookResponse
from gobby.storage.workflow_audit import WorkflowAuditManager

from .approval_flow import handle_approval_response
from .audit_helpers import (
    log_approval,
    log_rule_eval,
    log_tool_call,
    log_transition,
)
from .definitions import WorkflowDefinition, WorkflowState
from .detection_helpers import (
    detect_mcp_call,
    detect_plan_mode,
    detect_plan_mode_from_context,
    detect_task_claim,
)
from .evaluator import ConditionEvaluator
from .lifecycle_evaluator import (
    evaluate_all_lifecycle_workflows as _evaluate_all_lifecycle_workflows,
)
from .lifecycle_evaluator import (
    evaluate_lifecycle_triggers as _evaluate_lifecycle_triggers,
)
from .lifecycle_evaluator import (
    evaluate_workflow_triggers as _evaluate_workflow_triggers,
)
from .lifecycle_evaluator import (
    process_action_result,
)
from .loader import WorkflowLoader
from .premature_stop import check_premature_stop
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

    # Variables to inherit from parent session
    VARS_TO_INHERIT = ["plan_mode"]

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
                    project_path = Path(event.cwd) if event.cwd else None
                    workflow = self.loader.load_workflow(state.workflow_name, project_path)
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

        project_path = Path(event.cwd) if event.cwd else None
        workflow = self.loader.load_workflow(state.workflow_name, project_path)
        if not workflow:
            logger.error(f"Workflow '{state.workflow_name}' not found for session {session_id}")
            return HookResponse(decision="allow")

        # Skip step handling for lifecycle workflows - they only use triggers
        if workflow.type == "lifecycle":
            logger.debug(
                f"Skipping step workflow handling for lifecycle workflow '{workflow.name}' "
                f"in session {session_id}"
            )
            return HookResponse(decision="allow")

        # 4. Process event
        # Logic matches WORKFLOWS.md "Evaluation Flow"

        # Determine context for evaluation
        # Use SimpleNamespace for variables so dot notation works (variables.session_task)
        # Look up session info for condition evaluation
        session_info = {}
        if (
            self.action_executor
            and self.action_executor.session_manager
            and event.machine_id
            and event.project_id
        ):
            session = self.action_executor.session_manager.find_by_external_id(
                external_id=event.session_id,
                machine_id=event.machine_id,
                project_id=event.project_id,
                source=event.source.value,
            )
            if session:
                session_info = {
                    "id": session.id,
                    "external_id": session.external_id,
                    "project_id": session.project_id,
                    "status": session.status,
                    "git_branch": session.git_branch,
                    "source": session.source,
                }
        eval_context = {
            "event": event,
            "workflow_state": state,
            "variables": SimpleNamespace(**state.variables),
            "session": SimpleNamespace(**session_info),
            "tool_name": event.data.get("tool_name"),
            "tool_args": event.data.get("tool_args", {}),
            # State attributes for transition conditions
            "step_action_count": state.step_action_count,
            "total_action_count": state.total_action_count,
            "step": state.step,
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

            # Reset premature stop counter on user prompt
            # This allows the failsafe to distinguish agent-stuck-in-loop from user-initiated-stops
            if state.variables.get("_premature_stop_count", 0) > 0:
                state.variables["_premature_stop_count"] = 0
                self.state_manager.save_state(state)
                logger.debug(f"Reset premature_stop_count for session {session_id}")

        # Check blocked tools
        if event.event_type == HookEventType.BEFORE_TOOL:
            # Block tool calls while waiting for approval
            if state.approval_pending:
                reason = "Waiting for user approval. Please respond with 'yes' or 'no'."
                self._log_tool_call(session_id, state.step, "unknown", "block", reason)
                return HookResponse(decision="block", reason=reason)

            # Reset premature stop counter on tool calls
            # This ensures the failsafe only triggers for repeated stops without work in between
            if state.variables.get("_premature_stop_count", 0) > 0:
                state.variables["_premature_stop_count"] = 0
                self.state_manager.save_state(state)
                logger.debug(f"Reset premature_stop_count on tool call for session {session_id}")

            raw_tool_name = eval_context.get("tool_name")
            tool_name = str(raw_tool_name) if raw_tool_name is not None else ""

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

            # Detect Claude Code plan mode entry/exit
            self._detect_plan_mode(event, state)

            # Track all MCP proxy calls for workflow conditions
            self._detect_mcp_call(event, state)

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

    async def _execute_actions(self, actions: list[dict[str, Any]], state: WorkflowState) -> None:
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
            memory_sync_manager=self.action_executor.memory_sync_manager,
            task_sync_manager=self.action_executor.task_sync_manager,
            session_task_manager=self.action_executor.session_task_manager,
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
        """Handle user response to approval request."""
        return handle_approval_response(
            event, state, current_step, self.evaluator, self.state_manager
        )

    async def evaluate_all_lifecycle_workflows(
        self, event: HookEvent, context_data: dict[str, Any] | None = None
    ) -> HookResponse:
        """Discover and evaluate all lifecycle workflows for the given event."""
        return await _evaluate_all_lifecycle_workflows(
            event=event,
            loader=self.loader,
            state_manager=self.state_manager,
            action_executor=self.action_executor,
            evaluator=self.evaluator,
            detect_task_claim_fn=self._detect_task_claim,
            detect_plan_mode_fn=self._detect_plan_mode,
            detect_plan_mode_from_context_fn=self._detect_plan_mode_from_context,
            check_premature_stop_fn=self._check_premature_stop,
            context_data=context_data,
        )

    def _process_action_result(
        self,
        result: dict[str, Any],
        context_data: dict[str, Any],
        state: "WorkflowState",
        injected_context: list[str],
    ) -> str | None:
        """Process action execution result."""
        return process_action_result(result, context_data, state, injected_context)

    async def _evaluate_workflow_triggers(
        self,
        workflow: "WorkflowDefinition",
        event: HookEvent,
        context_data: dict[str, Any],
    ) -> HookResponse:
        """Evaluate triggers for a single workflow definition."""
        return await _evaluate_workflow_triggers(
            workflow, event, context_data, self.state_manager, self.action_executor, self.evaluator
        )

    async def evaluate_lifecycle_triggers(
        self, workflow_name: str, event: HookEvent, context_data: dict[str, Any] | None = None
    ) -> HookResponse:
        """Evaluate triggers for a specific lifecycle workflow (e.g. session-handoff)."""
        return await _evaluate_lifecycle_triggers(
            workflow_name, event, self.loader, self.action_executor, self.evaluator, context_data
        )

    # --- Premature Stop Handling ---

    async def _check_premature_stop(
        self, event: HookEvent, context_data: dict[str, Any]
    ) -> HookResponse | None:
        """Check if an active step workflow should handle a premature stop."""
        template_engine = self.action_executor.template_engine if self.action_executor else None
        return await check_premature_stop(
            event, context_data, self.state_manager, self.loader, self.evaluator, template_engine
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
        log_tool_call(self.audit_manager, session_id, step, tool_name, result, reason, context)

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
        log_rule_eval(
            self.audit_manager, session_id, step, rule_id, condition, result, reason, context
        )

    def _log_transition(
        self,
        session_id: str,
        from_step: str,
        to_step: str,
        reason: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Log a step transition to the audit log."""
        log_transition(self.audit_manager, session_id, from_step, to_step, reason, context)

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
        log_approval(self.audit_manager, session_id, step, result, condition_id, prompt, context)

    def _detect_task_claim(self, event: HookEvent, state: WorkflowState) -> None:
        """Detect gobby-tasks calls that claim or release a task for this session."""
        session_task_manager = getattr(self.action_executor, "session_task_manager", None)
        task_manager = getattr(self.action_executor, "task_manager", None)
        detect_task_claim(event, state, session_task_manager, task_manager)

    def _detect_plan_mode(self, event: HookEvent, state: WorkflowState) -> None:
        """Detect Claude Code plan mode entry/exit and set workflow variable."""
        detect_plan_mode(event, state)

    def _detect_plan_mode_from_context(self, event: HookEvent, state: WorkflowState) -> None:
        """Detect plan mode from system reminders in user prompt."""
        detect_plan_mode_from_context(event, state)

    def _detect_mcp_call(self, event: HookEvent, state: WorkflowState) -> None:
        """Track MCP tool calls by server/tool for workflow conditions."""
        detect_mcp_call(event, state)

    def activate_workflow(
        self,
        workflow_name: str,
        session_id: str,
        project_path: Path | None = None,
        variables: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Activate a step-based workflow for a session.

        This is used internally during session startup for terminal-mode agents
        that have a workflow_name set. It creates the initial workflow state.

        Args:
            workflow_name: Name of the workflow to activate
            session_id: Session ID to activate for
            project_path: Optional project path for workflow discovery
            variables: Optional initial variables to merge with workflow defaults

        Returns:
            Dict with success status and workflow info
        """
        # Load workflow
        definition = self.loader.load_workflow(workflow_name, project_path)
        if not definition:
            logger.warning(f"Workflow '{workflow_name}' not found for auto-activation")
            return {"success": False, "error": f"Workflow '{workflow_name}' not found"}

        if definition.type == "lifecycle":
            logger.debug(f"Skipping auto-activation of lifecycle workflow '{workflow_name}'")
            return {
                "success": False,
                "error": f"Workflow '{workflow_name}' is lifecycle type (auto-runs on events)",
            }

        # Check for existing step workflow
        existing = self.state_manager.get_state(session_id)
        if existing and existing.workflow_name != "__lifecycle__":
            # Check if existing is lifecycle type
            existing_def = self.loader.load_workflow(existing.workflow_name, project_path)
            if not existing_def or existing_def.type != "lifecycle":
                logger.warning(
                    f"Session {session_id} already has workflow '{existing.workflow_name}' active"
                )
                return {
                    "success": False,
                    "error": f"Session already has workflow '{existing.workflow_name}' active",
                }

        # Determine initial step - fail fast if no steps defined
        if not definition.steps:
            logger.error(f"Workflow '{workflow_name}' has no steps defined")
            return {
                "success": False,
                "error": f"Workflow '{workflow_name}' has no steps defined",
            }
        step = definition.steps[0].name

        # Merge variables: preserve existing lifecycle variables, then apply workflow declarations
        # Priority: existing state < workflow defaults < passed-in variables
        # This preserves lifecycle variables (like unlocked_tools) that the step workflow doesn't declare
        merged_variables = dict(existing.variables) if existing else {}
        merged_variables.update(definition.variables)  # Override with workflow-declared defaults
        if variables:
            merged_variables.update(variables)  # Override with passed-in values

        # Create state
        state = WorkflowState(
            session_id=session_id,
            workflow_name=workflow_name,
            step=step,
            step_entered_at=datetime.now(UTC),
            step_action_count=0,
            total_action_count=0,
            artifacts={},
            observations=[],
            reflection_pending=False,
            context_injected=False,
            variables=merged_variables,
            task_list=None,
            current_task_index=0,
            files_modified_this_task=0,
        )

        self.state_manager.save_state(state)
        logger.info(f"Auto-activated workflow '{workflow_name}' for session {session_id}")

        return {
            "success": True,
            "session_id": session_id,
            "workflow": workflow_name,
            "step": step,
            "steps": [s.name for s in definition.steps],
            "variables": merged_variables,
        }
