"""Workflow state management actions.

Extracted from actions.py as part of strangler fig decomposition.
These functions handle workflow state persistence and variable management.
"""

import asyncio
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gobby.workflows.actions import ActionContext

logger = logging.getLogger(__name__)


def load_workflow_state(db: Any, session_id: str, state: Any) -> dict[str, Any]:
    """Load workflow state from DB into the provided state object.

    Args:
        db: Database instance
        session_id: Session ID to load state for
        state: WorkflowState object to update

    Returns:
        Dict with state_loaded boolean
    """
    from gobby.workflows.state_manager import WorkflowStateManager

    state_manager = WorkflowStateManager(db)
    loaded_state = state_manager.get_state(session_id)

    if loaded_state:
        # Copy attributes from loaded state to existing state object
        for field in loaded_state.model_fields:
            val = getattr(loaded_state, field)
            setattr(state, field, val)
        return {"state_loaded": True}

    return {"state_loaded": False}


def save_workflow_state(db: Any, state: Any) -> dict[str, Any]:
    """Save workflow state to DB.

    Args:
        db: Database instance
        state: WorkflowState object to save

    Returns:
        Dict with state_saved boolean
    """
    from gobby.workflows.state_manager import WorkflowStateManager

    state_manager = WorkflowStateManager(db)
    state_manager.save_state(state)
    return {"state_saved": True}


def set_variable(state: Any, name: str | None, value: Any) -> dict[str, Any] | None:
    """Set a workflow variable.

    Args:
        state: WorkflowState object
        name: Variable name
        value: Variable value

    Returns:
        Dict with variable_set and value, or None if no name
    """
    if not name:
        return None

    if not state.variables:
        state.variables = {}

    state.variables[name] = value
    return {"variable_set": name, "value": value}


def increment_variable(
    state: Any, name: str | None, amount: int | float = 1
) -> dict[str, Any] | None:
    """Increment a numeric workflow variable.

    Args:
        state: WorkflowState object
        name: Variable name
        amount: Amount to increment by (default: 1)

    Returns:
        Dict with variable_incremented and value, or None if no name
    """
    if not name:
        return None

    if not state.variables:
        state.variables = {}

    current = state.variables.get(name, 0)
    if not isinstance(current, (int, float)):
        logger.error(
            f"increment_variable: Variable '{name}' is not numeric, got {type(current).__name__}: {current}"
        )
        raise TypeError(
            f"Cannot increment non-numeric variable '{name}': "
            f"expected int or float, got {type(current).__name__} with value {current!r}"
        )

    new_value = current + amount
    state.variables[name] = new_value
    return {"variable_incremented": name, "value": new_value}


def mark_loop_complete(state: Any) -> dict[str, Any]:
    """Mark the autonomous loop as complete.

    Args:
        state: WorkflowState object

    Returns:
        Dict with loop_marked_complete boolean
    """
    if not state.variables:
        state.variables = {}
    state.variables["stop_reason"] = "completed"
    return {"loop_marked_complete": True}


# --- ActionHandler-compatible wrappers ---
# These match the ActionHandler protocol: (context: ActionContext, **kwargs) -> dict | None


async def handle_load_workflow_state(
    context: "ActionContext", **kwargs: Any
) -> dict[str, Any] | None:
    """ActionHandler wrapper for load_workflow_state."""
    return await asyncio.to_thread(
        load_workflow_state, context.db, context.session_id, context.state
    )


async def handle_save_workflow_state(
    context: "ActionContext", **kwargs: Any
) -> dict[str, Any] | None:
    """ActionHandler wrapper for save_workflow_state."""
    return await asyncio.to_thread(save_workflow_state, context.db, context.state)


async def handle_set_variable(context: "ActionContext", **kwargs: Any) -> dict[str, Any] | None:
    """ActionHandler wrapper for set_variable.

    Values containing Jinja2 templates ({{ ... }}) are rendered before setting.
    """
    value = kwargs.get("value")

    # Render template if value contains Jinja2 syntax
    if isinstance(value, str) and "{{" in value:
        template_context = {
            "variables": context.state.variables or {},
            "state": context.state,
        }
        if context.template_engine:
            value = context.template_engine.render(value, template_context)
        else:
            logger.warning("handle_set_variable: template_engine is None, skipping template render")

    return set_variable(context.state, kwargs.get("name"), value)


async def handle_increment_variable(
    context: "ActionContext", **kwargs: Any
) -> dict[str, Any] | None:
    """ActionHandler wrapper for increment_variable."""
    return increment_variable(context.state, kwargs.get("name"), kwargs.get("amount", 1))


async def handle_mark_loop_complete(
    context: "ActionContext", **kwargs: Any
) -> dict[str, Any] | None:
    """ActionHandler wrapper for mark_loop_complete."""
    return mark_loop_complete(context.state)
