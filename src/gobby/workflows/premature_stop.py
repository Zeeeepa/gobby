"""
Premature stop handling for workflow engine.

Extracted from engine.py to reduce complexity.
Handles the case when a session tries to stop before the workflow's
exit condition is satisfied.
"""

import logging
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from gobby.hooks.events import HookEvent, HookResponse

if TYPE_CHECKING:
    from .evaluator import ConditionEvaluator
    from .loader import WorkflowLoader
    from .state_manager import WorkflowStateManager
    from .templates import TemplateEngine

logger = logging.getLogger(__name__)


async def check_premature_stop(
    event: HookEvent,
    context_data: dict[str, Any],
    state_manager: "WorkflowStateManager",
    loader: "WorkflowLoader",
    evaluator: "ConditionEvaluator",
    template_engine: "TemplateEngine | None",
) -> HookResponse | None:
    """
    Check if an active step workflow should handle a premature stop.

    Called on STOP events to evaluate whether the workflow's exit_condition
    is met. If not met and workflow has on_premature_stop defined, returns
    an appropriate response.

    Args:
        event: The STOP hook event
        context_data: Shared context data including session variables
        state_manager: Workflow state manager
        loader: Workflow definition loader
        evaluator: Condition evaluator
        template_engine: Template engine for rendering messages

    Returns:
        HookResponse if premature stop detected, None otherwise
    """
    session_id = event.metadata.get("_platform_session_id")
    if not session_id:
        return None

    # Check if there's an active step workflow
    state = state_manager.get_state(session_id)
    if not state:
        return None

    # Skip lifecycle-only states
    if state.workflow_name == "__lifecycle__":
        return None

    # Load the workflow definition
    project_path = Path(event.cwd) if event.cwd else None
    workflow = loader.load_workflow(state.workflow_name, project_path=project_path)
    if not workflow:
        logger.warning(f"Workflow '{state.workflow_name}' not found for premature stop check")
        return None

    # Check if workflow has exit_condition and on_premature_stop
    if not workflow.exit_condition:
        return None

    # Build evaluation context
    # Use SimpleNamespace for variables so dot notation works (variables.session_task)
    eval_context: dict[str, Any] = {
        "workflow_state": state,
        "state": state,
        "variables": SimpleNamespace(**state.variables),
        "current_step": state.step,
    }
    # Add session variables to context
    eval_context.update(context_data)

    # Evaluate the exit condition
    exit_condition_met = evaluator.evaluate(workflow.exit_condition, eval_context)

    if exit_condition_met:
        logger.debug(f"Workflow '{workflow.name}' exit_condition met, allowing stop")
        return None

    # Exit condition not met - check for premature stop handler
    if not workflow.on_premature_stop:
        logger.debug(
            f"Workflow '{workflow.name}' exit_condition not met but no on_premature_stop defined"
        )
        return None

    # Failsafe: check if we've exceeded max stop attempts
    # Counter is stored in variables and resets on BEFORE_AGENT (user prompt)
    stop_count = state.variables.get("_premature_stop_count", 0) + 1
    max_attempts = state.variables.get("premature_stop_max_attempts", 3)

    # Update and persist the counter
    state.variables["_premature_stop_count"] = stop_count
    state_manager.save_state(state)

    if max_attempts > 0 and stop_count >= max_attempts:
        logger.warning(
            f"Premature stop failsafe triggered for workflow '{workflow.name}': "
            f"stop_count={stop_count} >= max_attempts={max_attempts}"
        )
        return HookResponse(
            decision="allow",
            context=(
                f"⚠️ **Failsafe Exit**: Allowing stop after {stop_count} blocked attempts. "
                f"Task may be incomplete."
            ),
        )

    # Handle premature stop based on action type
    handler = workflow.on_premature_stop

    # Render the message through template engine (supports Jinja2 variables)
    rendered_message = handler.message
    if template_engine and handler.message:
        render_context = {
            "variables": state.variables,
            "state": state,
            "workflow": workflow,
        }
        try:
            rendered_message = template_engine.render(handler.message, render_context)
        except Exception as e:
            logger.warning(f"Failed to render on_premature_stop message: {e}")
            # Fall back to unrendered message

    logger.info(
        f"Premature stop detected for workflow '{workflow.name}': "
        f"action={handler.action}, message={rendered_message[:100] if rendered_message else None}..., "
        f"attempt {stop_count}/{max_attempts}"
    )

    if handler.action == "block":
        return HookResponse(
            decision="block",
            reason=rendered_message,
        )
    elif handler.action == "warn":
        return HookResponse(
            decision="allow",
            context=f"⚠️ **Warning**: {rendered_message}",
        )
    else:  # guide_continuation (default)
        return HookResponse(
            decision="block",
            reason=rendered_message,
            context=(
                f"📋 **Task Incomplete**\n\n"
                f"{rendered_message}\n\n"
                f"The workflow exit condition `{workflow.exit_condition}` is not yet satisfied."
            ),
        )
