import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from gobby.hooks.events import HookEvent, HookEventType, HookResponse
from gobby.storage.projects import LocalProjectManager
from gobby.storage.workflow_audit import WorkflowAuditManager

from .approval_flow import handle_approval_response
from .audit_helpers import (
    log_approval,
    log_rule_eval,
    log_tool_call,
    log_transition,
)
from .definitions import WorkflowDefinition, WorkflowState, WorkflowTransition
from .detection_helpers import (
    detect_mcp_call,
    detect_plan_mode,
    detect_plan_mode_from_context,
    detect_task_claim,
    process_mcp_handlers,
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


class DotDict(dict[str, Any]):
    """Dict subclass that supports both dot-notation and .get() access.

    SimpleNamespace supports dot-notation but not .get(), which breaks
    workflow transition conditions that use ``variables.get('key')``.
    DotDict supports both patterns.
    """

    def __getattr__(self, key: str) -> Any:
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key) from None

    def __setattr__(self, key: str, value: Any) -> None:
        self[key] = value


# Read-only MCP discovery tools that are always allowed regardless of workflow step restrictions.
# These "meta" tools enable progressive disclosure and are required for agents to discover
# what tools are available. They don't execute actions, only return information.
# NOTE: call_tool is intentionally NOT exempt - it executes actual tools and should be restricted.
EXEMPT_TOOLS = frozenset(
    {
        # Gobby MCP discovery tools (both prefixed and unprefixed forms)
        "list_mcp_servers",
        "mcp__gobby__list_mcp_servers",
        "list_tools",
        "mcp__gobby__list_tools",
        "get_tool_schema",
        "mcp__gobby__get_tool_schema",
        "recommend_tools",
        "mcp__gobby__recommend_tools",
        "search_tools",
        "mcp__gobby__search_tools",
    }
)


@dataclass
class TransitionResult:
    """Result of a workflow step transition.

    Carries both LLM-facing context (injected_messages) and user-visible
    output (system_messages) through transition chains.
    """

    injected_messages: list[str] = field(default_factory=list)
    system_messages: list[str] = field(default_factory=list)

    def extend(self, other: "TransitionResult") -> None:
        """Accumulate messages from another transition result."""
        self.injected_messages.extend(other.injected_messages)
        self.system_messages.extend(other.system_messages)


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
                    workflow = await self.loader.load_workflow(state.workflow_name, project_path)
                    if (
                        workflow
                        and isinstance(workflow, WorkflowDefinition)
                        and workflow.get_step("reflect")
                    ):
                        result = await self.transition_to(state, "reflect", workflow)
                        context = "[System Alert] Step duration limit exceeded. Transitioning to 'reflect' step."
                        if result.injected_messages:
                            context = context + "\n\n" + "\n\n".join(result.injected_messages)
                        system_message = "\n".join(result.system_messages) if result.system_messages else None
                        return HookResponse(decision="modify", context=context, system_message=system_message)

        # 3. Load definition
        # Skip if this is a lifecycle-only state or ended workflow (used for task_claimed tracking)
        if state.workflow_name in ("__lifecycle__", "__ended__"):
            logger.debug(
                f"Skipping step workflow handling for {state.workflow_name} state in session {session_id}"
            )
            return HookResponse(decision="allow")

        project_path = Path(event.cwd) if event.cwd else None
        workflow = await self.loader.load_workflow(state.workflow_name, project_path)
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

        # Step handling only applies to WorkflowDefinition, not PipelineDefinition
        if not isinstance(workflow, WorkflowDefinition):
            logger.debug(f"Workflow '{workflow.name}' is a pipeline, skipping step handling")
            return HookResponse(decision="allow")

        # 4. Process event
        # Logic matches WORKFLOWS.md "Evaluation Flow"

        # Determine context for evaluation
        session_info, project_info = self._resolve_session_and_project(event)
        eval_context = self._build_eval_context(event, state, session_info, project_info)

        current_step = workflow.get_step(state.step)
        if not current_step:
            logger.error(f"Step '{state.step}' not found in workflow '{workflow.name}'")
            return HookResponse(decision="allow")

        # Inject on_enter context for initial step when not yet injected
        # This handles the case where activate_workflow creates state but doesn't execute on_enter
        if not state.context_injected and (
            current_step.on_enter or getattr(current_step, "status_message", None)
        ):
            logger.info(
                f"Injecting initial on_enter context for step '{state.step}' "
                f"in session {session_id}"
            )
            injected_messages = await self._execute_actions(current_step.on_enter, state)
            state.context_injected = True
            self.state_manager.save_state(state)

            # Render initial step's status_message (after on_enter so variables are populated)
            initial_system: list[str] = []
            status_msg = self._render_status_message(current_step, state)
            if status_msg:
                initial_system.append(status_msg)

            # Auto-transition chain: if on_enter set variables that satisfy transitions,
            # follow them immediately without waiting for the next hook event.
            # This chains deterministic steps (e.g., find_work → spawn_worker → wait_for_worker).
            initial_result = TransitionResult(
                injected_messages=injected_messages,
                system_messages=initial_system,
            )
            result = await self._auto_transition_chain(
                state,
                workflow,
                session_info,
                project_info,
                event,
                initial_result,
            )

            if result.injected_messages or result.system_messages:
                context = "\n\n".join(result.injected_messages) if result.injected_messages else None
                system_message = "\n".join(result.system_messages) if result.system_messages else None
                return HookResponse(decision="modify", context=context, system_message=system_message)

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

            # Allow exempt tools (MCP discovery tools) regardless of step restrictions
            if tool_name in EXEMPT_TOOLS:
                self._log_tool_call(session_id, state.step, tool_name, "allow", "exempt tool")
                return HookResponse(decision="allow")

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

            # Check MCP-level tool restrictions for call_tool/get_tool_schema
            # Adapters normalize mcp_server/mcp_tool from tool_input for these calls
            if tool_name in (
                "call_tool",
                "mcp__gobby__call_tool",
                "get_tool_schema",
                "mcp__gobby__get_tool_schema",
            ):
                mcp_server = event.data.get("mcp_server", "")
                mcp_tool = event.data.get("mcp_tool", "")
                if mcp_server and mcp_tool:
                    mcp_key = f"{mcp_server}:{mcp_tool}"
                    mcp_wildcard = f"{mcp_server}:*"

                    # Check blocked MCP tools (explicit block or wildcard)
                    if (
                        mcp_key in current_step.blocked_mcp_tools
                        or mcp_wildcard in current_step.blocked_mcp_tools
                    ):
                        reason = f"MCP tool '{mcp_key}' is blocked in step '{state.step}'."
                        self._log_tool_call(session_id, state.step, mcp_key, "block", reason)
                        return HookResponse(decision="block", reason=reason)

                    # Check allowed MCP tools (if not "all")
                    if current_step.allowed_mcp_tools != "all":
                        # Allow if explicitly listed or matches wildcard
                        if (
                            mcp_key not in current_step.allowed_mcp_tools
                            and mcp_wildcard not in current_step.allowed_mcp_tools
                        ):
                            reason = f"MCP tool '{mcp_key}' is not in allowed list for step '{state.step}'."
                            self._log_tool_call(session_id, state.step, mcp_key, "block", reason)
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

        # For AFTER_TOOL events, run detection BEFORE checking transitions
        # This ensures variables like task_claimed are set before evaluating conditions
        if event.event_type == HookEventType.AFTER_TOOL:
            state.step_action_count += 1
            state.total_action_count += 1

            # Detect gobby-tasks calls for session-scoped task claiming
            self._detect_task_claim(event, state)

            # Detect Claude Code plan mode entry/exit
            self._detect_plan_mode(event, state)

            # Track all MCP proxy calls for workflow conditions
            # Also process on_mcp_success/on_mcp_error handlers from step definition
            self._detect_mcp_call(event, state, current_step)

            # Rebuild eval_context variables after detection updates
            eval_context["variables"] = DotDict(state.variables)
            # Also update flattened variables at top level
            eval_context.update(state.variables)

        # Check premature stop for STOP events
        if event.event_type == HookEventType.STOP:
            premature_response = await self._check_premature_stop(event, state.variables)
            if premature_response and premature_response.decision != "allow":
                logger.info(
                    f"Premature stop blocked for session {session_id}: {premature_response.reason}"
                )
                return premature_response

        # Check transitions
        logger.debug("Checking transitions")
        for transition in current_step.transitions:
            if self.evaluator.evaluate(transition.when, eval_context):
                # Transition!
                transition_result = await self.transition_to(
                    state, transition.to, workflow, transition=transition
                )

                # Auto-transition chain after the transition's on_enter
                result = await self._auto_transition_chain(
                    state,
                    workflow,
                    session_info,
                    project_info,
                    event,
                    transition_result,
                )

                # Save state after transition
                if event.event_type == HookEventType.AFTER_TOOL:
                    self.state_manager.save_state(state)

                # Build context with on_enter messages if any were injected
                if result.injected_messages:
                    context = "\n\n".join(result.injected_messages)
                else:
                    context = f"Transitioning to step: {transition.to}"

                system_message = "\n".join(result.system_messages) if result.system_messages else None
                return HookResponse(decision="modify", context=context, system_message=system_message)

        # Check exit conditions
        logger.debug("Checking exit conditions")
        if self.evaluator.check_exit_conditions(current_step.exit_conditions, state):
            # TODO: Determine next step or completion logic
            # For now, simplistic 'next step' if linear, or rely on transitions
            pass

        # Save state for AFTER_TOOL events (if no transition occurred)
        if event.event_type == HookEventType.AFTER_TOOL:
            self.state_manager.save_state(state)

        return HookResponse(decision="allow")

    async def transition_to(
        self,
        state: WorkflowState,
        new_step_name: str,
        workflow: WorkflowDefinition,
        transition: WorkflowTransition | None = None,
    ) -> TransitionResult:
        """
        Execute transition logic.

        Args:
            state: Current workflow state
            new_step_name: Name of the step to transition to
            workflow: Workflow definition
            transition: Optional transition object containing on_transition actions

        Returns:
            TransitionResult with injected messages (LLM context) and system messages (user-visible)
        """
        old_step = workflow.get_step(state.step)
        new_step = workflow.get_step(new_step_name)

        if not new_step:
            logger.error(f"Cannot transition to unknown step '{new_step_name}'")
            return TransitionResult()

        logger.info(
            f"Transitioning session {state.session_id} from '{state.step}' to '{new_step_name}'"
        )

        # Log the transition
        self._log_transition(state.session_id, state.step, new_step_name)

        # Execute on_exit of old step
        if old_step:
            await self._execute_actions(old_step.on_exit, state)

        # Execute on_transition actions if defined
        if transition and isinstance(transition, WorkflowTransition) and transition.on_transition:
            await self._execute_actions(transition.on_transition, state)

        # Update state
        state.step = new_step_name
        state.step_entered_at = datetime.now(UTC)
        state.step_action_count = 0
        state.context_injected = False  # Reset for new step context

        self.state_manager.save_state(state)

        # Execute on_enter of new step and capture injected messages
        injected_messages = await self._execute_actions(new_step.on_enter, state)

        if injected_messages:
            state.context_injected = True
            self.state_manager.save_state(state)

        # Render status_message for user visibility (after on_enter so variables are populated)
        system_messages: list[str] = []
        status_msg = self._render_status_message(new_step, state)
        if status_msg:
            system_messages.append(status_msg)

        return TransitionResult(injected_messages=injected_messages, system_messages=system_messages)

    async def _execute_actions(
        self, actions: list[dict[str, Any]], state: WorkflowState
    ) -> list[str]:
        """
        Execute a list of actions.

        Returns:
            List of injected messages from inject_message/inject_context actions.
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
            tool_proxy_getter=self.action_executor.tool_proxy_getter,
            memory_manager=self.action_executor.memory_manager,
            memory_sync_manager=self.action_executor.memory_sync_manager,
            task_sync_manager=self.action_executor.task_sync_manager,
            session_task_manager=self.action_executor.session_task_manager,
            pipeline_executor=self.action_executor.pipeline_executor,
            workflow_loader=self.action_executor.workflow_loader,
            skill_manager=self.action_executor.skill_manager,
        )

        injected_messages: list[str] = []

        for action_def in actions:
            action_type = action_def.get("action")
            if not action_type:
                continue

            # Support conditional actions via `when` field
            when = action_def.get("when")
            if when is not None:
                eval_ctx = {"variables": DotDict(state.variables), **state.variables}
                if not self.evaluator.evaluate(when, eval_ctx):
                    logger.debug(f"Skipping action '{action_type}': when condition false: {when}")
                    continue

            result = await self.action_executor.execute(action_type, context, **action_def)

            if result:
                # Capture injected messages to return to caller
                if "inject_message" in result:
                    msg = result["inject_message"]
                    injected_messages.append(msg)
                    logger.info(f"Message injected: {msg[:50]}...")
                elif "inject_context" in result:
                    msg = result["inject_context"]
                    injected_messages.append(msg)
                    logger.info(f"Context injected: {msg[:50]}...")

        return injected_messages

    def _render_status_message(self, step: Any, state: WorkflowState) -> str | None:
        """Render a step's status_message template if defined.

        Called after on_enter actions so that variables set during on_enter
        are available for template rendering. Returns the rendered string
        for inclusion as a user-visible system_message on HookResponse.
        """
        status_message = getattr(step, "status_message", None)
        if not isinstance(status_message, str):
            return None

        template_engine = getattr(self.action_executor, "template_engine", None)
        if not template_engine:
            return None

        template_context: dict[str, Any] = {
            "variables": state.variables,
            "state": state,
            "session_id": state.session_id,
        }
        try:
            rendered = template_engine.render(status_message, template_context)
            return rendered if isinstance(rendered, str) else None
        except Exception as e:
            logger.warning(f"Failed to render status_message for step '{step.name}': {e}")
            return None

    def _resolve_session_and_project(
        self, event: HookEvent
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Look up session and project info for eval context.

        Returns:
            Tuple of (session_info dict, project_info dict)
        """
        session_info: dict[str, Any] = {}
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

        project_info: dict[str, Any] = {"name": "", "id": ""}
        if event.project_id and self.action_executor and self.action_executor.db:
            project_mgr = LocalProjectManager(self.action_executor.db)
            project = project_mgr.get(event.project_id)
            if project:
                project_info = {"name": project.name, "id": project.id}

        return session_info, project_info

    def _build_eval_context(
        self,
        event: HookEvent,
        state: WorkflowState,
        session_info: dict[str, Any],
        project_info: dict[str, Any],
    ) -> dict[str, Any]:
        """Build evaluation context dict for condition checking.

        Uses DotDict for variables so both dot notation (variables.session_task)
        and .get() access (variables.get('key')) work in transition conditions.
        Flattens variables to top level for simpler conditions like "task_claimed".
        """
        return {
            "event": event,
            "workflow_state": state,
            "variables": DotDict(state.variables),
            "session": DotDict(session_info),
            "project": DotDict(project_info),
            "tool_name": event.data.get("tool_name") if event.data else None,
            "tool_args": event.data.get("tool_args", {}) if event.data else {},
            # State attributes for transition conditions
            "step_action_count": state.step_action_count,
            "total_action_count": state.total_action_count,
            "step": state.step,
            # Flatten variables to top level for simpler conditions like "task_claimed"
            # instead of requiring "variables.task_claimed"
            **state.variables,
        }

    async def _auto_transition_chain(
        self,
        state: WorkflowState,
        workflow: WorkflowDefinition,
        session_info: dict[str, Any],
        project_info: dict[str, Any],
        event: HookEvent,
        initial_result: TransitionResult,
        max_depth: int = 10,
    ) -> TransitionResult:
        """Follow automatic transitions after on_enter actions.

        If on_enter actions set variables that satisfy a transition condition,
        execute the transition immediately and repeat. This chains deterministic
        steps without waiting for the next hook event.

        Args:
            state: Current workflow state
            workflow: Workflow definition
            session_info: Session info for eval context
            project_info: Project info for eval context
            event: Original hook event
            initial_result: Messages accumulated so far from the triggering transition
            max_depth: Safety limit to prevent infinite loops

        Returns:
            Accumulated TransitionResult from all chained transitions
        """
        result = TransitionResult(
            injected_messages=list(initial_result.injected_messages),
            system_messages=list(initial_result.system_messages),
        )

        for _ in range(max_depth):
            # Rebuild eval context with updated variables after on_enter actions
            eval_context = self._build_eval_context(event, state, session_info, project_info)

            current_step = workflow.get_step(state.step)
            if not current_step:
                break

            # Check transitions on the current step
            transitioned = False
            for transition in current_step.transitions:
                if self.evaluator.evaluate(transition.when, eval_context):
                    logger.info(
                        f"Auto-transition: {state.step} → {transition.to} "
                        f"(condition: {transition.when})"
                    )
                    transition_result = await self.transition_to(
                        state, transition.to, workflow, transition=transition
                    )
                    result.extend(transition_result)
                    transitioned = True
                    break  # Only follow first matching transition

            if not transitioned:
                break
        else:
            # Loop exhausted max_depth without a non-transitioning step
            logger.warning(
                f"Auto-transition chain truncated at max_depth={max_depth} "
                f"for workflow '{workflow.name}' at step '{state.step}'"
            )

        return result

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

    def _detect_mcp_call(
        self, event: HookEvent, state: WorkflowState, current_step: Any | None = None
    ) -> None:
        """Track MCP tool calls and process on_mcp_success/on_mcp_error handlers."""
        # First, track the call (this also returns success/error status)
        detect_mcp_call(event, state)

        # Process on_mcp_success/on_mcp_error handlers from step definition
        if current_step and event.data:
            server_name = event.data.get("mcp_server", "")
            tool_name = event.data.get("mcp_tool", "")
            if server_name and tool_name:
                # Check if call succeeded by looking at tool_output
                tool_output = event.data.get("tool_output") or {}
                succeeded = True
                if isinstance(tool_output, dict):
                    if tool_output.get("error") or tool_output.get("status") == "error":
                        succeeded = False
                    else:
                        result = tool_output.get("result")
                        if isinstance(result, dict) and result.get("error"):
                            succeeded = False

                # Get handlers from step definition
                on_success = getattr(current_step, "on_mcp_success", []) or []
                on_error = getattr(current_step, "on_mcp_error", []) or []

                if on_success or on_error:
                    template_engine = (
                        self.action_executor.template_engine if self.action_executor else None
                    )
                    process_mcp_handlers(
                        state,
                        server_name,
                        tool_name,
                        succeeded,
                        on_success,
                        on_error,
                        template_engine=template_engine,
                    )

    async def activate_workflow(
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
        definition = await self.loader.load_workflow(workflow_name, project_path)
        if not definition:
            logger.warning(f"Workflow '{workflow_name}' not found for auto-activation")
            return {"success": False, "error": f"Workflow '{workflow_name}' not found"}

        if definition.type == "lifecycle":
            logger.debug(f"Skipping auto-activation of lifecycle workflow '{workflow_name}'")
            return {
                "success": False,
                "error": f"Workflow '{workflow_name}' is lifecycle type (auto-runs on events)",
            }

        # Only WorkflowDefinition can be activated as step workflows
        if not isinstance(definition, WorkflowDefinition):
            logger.debug(f"Workflow '{workflow_name}' is a pipeline, not a step workflow")
            return {
                "success": False,
                "error": f"'{workflow_name}' is a pipeline. Use pipeline execution instead.",
            }

        # Check for existing step workflow
        existing = self.state_manager.get_state(session_id)
        if existing and existing.workflow_name not in ("__lifecycle__", "__ended__"):
            # Check if existing is lifecycle type
            existing_def = await self.loader.load_workflow(existing.workflow_name, project_path)
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
