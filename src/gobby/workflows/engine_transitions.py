"""Workflow transition logic: step transitions, action execution, and chaining.

Extracted from engine.py as part of Strangler Fig decomposition (Wave 2).
These are the hot-path functions that handle step-to-step transitions.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from .engine_models import DotDict, TransitionResult

if TYPE_CHECKING:
    from .definitions import WorkflowDefinition, WorkflowState, WorkflowTransition
    from .engine import WorkflowEngine

logger = logging.getLogger(__name__)


async def transition_to(
    engine: WorkflowEngine,
    state: WorkflowState,
    new_step_name: str,
    workflow: WorkflowDefinition,
    transition: WorkflowTransition | None = None,
) -> TransitionResult:
    """Execute transition logic.

    Args:
        engine: WorkflowEngine instance providing state_manager, action_executor, etc.
        state: Current workflow state.
        new_step_name: Name of the step to transition to.
        workflow: Workflow definition.
        transition: Optional transition object containing on_transition actions.

    Returns:
        TransitionResult with injected messages (LLM context) and system messages (user-visible).
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
    engine._log_transition(state.session_id, state.step, new_step_name)

    try:
        # Execute on_exit of old step
        if old_step:
            await _execute_actions(engine, old_step.on_exit, state)

        # Execute on_transition actions if defined
        from .definitions import WorkflowTransition as _WT

        if transition and isinstance(transition, _WT) and transition.on_transition:
            await _execute_actions(engine, transition.on_transition, state)

        # Update state
        state.step = new_step_name
        state.step_entered_at = datetime.now(UTC)
        state.step_action_count = 0
        state.context_injected = False  # Reset for new step context
        # Clear per-step MCP tracking so stale results from the previous step
        # don't trigger transitions in the new step.
        state.variables.pop("mcp_results", None)
        state.variables.pop("mcp_calls", None)

        engine.state_manager.save_state(state)

        # Execute on_enter of new step and capture injected messages
        injected_messages = await _execute_actions(engine, new_step.on_enter, state)

        if injected_messages:
            state.context_injected = True
            engine.state_manager.save_state(state)

        # Render status_message for user visibility
        system_messages: list[str] = []
        status_msg = _render_status_message(engine, new_step, state)
        if status_msg:
            system_messages.append(status_msg)

        return TransitionResult(
            injected_messages=injected_messages, system_messages=system_messages
        )
    except Exception as e:
        logger.error(
            f"Transition failed from '{state.step}' to '{new_step_name}': {e}", exc_info=True
        )
        raise


async def _execute_actions(
    engine: WorkflowEngine,
    actions: list[dict[str, Any]],
    state: WorkflowState,
) -> list[str]:
    """Execute a list of actions.

    Returns:
        List of injected messages from inject_message/inject_context actions.
    """
    from .actions import ActionContext

    context = ActionContext(
        session_id=state.session_id,
        state=state,
        db=engine.action_executor.db,
        session_manager=engine.action_executor.session_manager,
        template_engine=engine.action_executor.template_engine,
        llm_service=engine.action_executor.llm_service,
        transcript_processor=engine.action_executor.transcript_processor,
        config=engine.action_executor.config,
        tool_proxy_getter=engine.action_executor.tool_proxy_getter,
        memory_manager=engine.action_executor.memory_manager,
        memory_sync_manager=engine.action_executor.memory_sync_manager,
        task_sync_manager=engine.action_executor.task_sync_manager,
        session_task_manager=engine.action_executor.session_task_manager,
        pipeline_executor=engine.action_executor.pipeline_executor,
        workflow_loader=engine.action_executor.workflow_loader,
        skill_manager=engine.action_executor.skill_manager,
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
            if not engine.evaluator.evaluate(when, eval_ctx):
                logger.debug(f"Skipping action '{action_type}': when condition false: {when}")
                continue

        result = await engine.action_executor.execute(action_type, context, **action_def)

        if result:
            if "inject_message" in result:
                msg = result["inject_message"]
                injected_messages.append(msg)
                logger.info(f"Message injected: {msg[:50]}...")
            elif "inject_context" in result:
                msg = result["inject_context"]
                injected_messages.append(msg)
                logger.info(f"Context injected: {msg[:50]}...")

    return injected_messages


def _render_status_message(engine: WorkflowEngine, step: Any, state: WorkflowState) -> str | None:
    """Render a step's status_message template if defined.

    Called after on_enter actions so that variables set during on_enter
    are available for template rendering.
    """
    status_message = getattr(step, "status_message", None)
    if not isinstance(status_message, str):
        return None

    template_engine = getattr(engine.action_executor, "template_engine", None)
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


async def _auto_transition_chain(
    engine: WorkflowEngine,
    state: WorkflowState,
    workflow: WorkflowDefinition,
    session_info: dict[str, Any],
    project_info: dict[str, Any],
    event: Any,
    initial_result: TransitionResult,
    max_depth: int = 10,
) -> TransitionResult:
    """Follow automatic transitions after on_enter actions.

    If on_enter actions set variables that satisfy a transition condition,
    execute the transition immediately and repeat. This chains deterministic
    steps without waiting for the next hook event.
    """
    result = TransitionResult(
        injected_messages=list(initial_result.injected_messages),
        system_messages=list(initial_result.system_messages),
    )

    visited_steps: list[str] = [state.step]

    for _ in range(max_depth):
        # Rebuild eval context with updated variables after on_enter actions
        eval_context = engine._build_eval_context(event, state, session_info, project_info)

        current_step = workflow.get_step(state.step)
        if not current_step:
            break

        # Check transitions on the current step
        transitioned = False
        for trans in current_step.transitions:
            if engine.evaluator.evaluate(trans.when, eval_context):
                logger.info(f"Auto-transition: {state.step} → {trans.to} (condition: {trans.when})")
                transition_result = await engine.transition_to(
                    state, trans.to, workflow, transition=trans
                )
                result.extend(transition_result)
                visited_steps.append(trans.to)
                transitioned = True
                break  # Only follow first matching transition

        if not transitioned:
            break
    else:
        logger.error(
            f"Auto-transition chain truncated at max_depth={max_depth} "
            f"for workflow '{workflow.name}' session={state.session_id} "
            f"chain: {' → '.join(visited_steps)}"
        )

    return result
