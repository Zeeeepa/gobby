"""
Workflow variable tools (set_variable, get_variable).
"""

import logging
from datetime import UTC, datetime
from typing import Any

from gobby.mcp_proxy.tools.workflows._resolution import (
    resolve_session_id,
    resolve_session_task_value,
)
from gobby.storage.database import DatabaseProtocol
from gobby.storage.sessions import LocalSessionManager
from gobby.workflows.definitions import WorkflowState
from gobby.workflows.state_manager import (
    SessionVariableManager,
    WorkflowInstanceManager,
    WorkflowStateManager,
)

logger = logging.getLogger(__name__)


def _coerce_value(value: str | int | float | bool | None) -> str | int | float | bool | None:
    """Coerce string representations of booleans/null/numbers to native types.

    MCP schema collapses union types (str|int|float|bool|None) to "string",
    so agents send "true"/"false" as strings. Without coercion, "false" is
    truthy and breaks workflow gate conditions like pending_memory_review.
    """
    if isinstance(value, str):
        stripped = value.strip().lower()
        if stripped == "":
            return None
        if stripped in ("true", "false"):
            return stripped == "true"
        if stripped in ("null", "none"):
            return None
        try:
            return int(value)
        except ValueError:
            try:
                return float(value)
            except ValueError:
                pass
    return value


def set_variable(
    state_manager: WorkflowStateManager,
    session_manager: LocalSessionManager,
    db: DatabaseProtocol,
    name: str,
    value: str | int | float | bool | None,
    session_id: str | None = None,
    workflow: str | None = None,
    instance_manager: WorkflowInstanceManager | None = None,
    session_var_manager: SessionVariableManager | None = None,
) -> dict[str, Any]:
    """
    Set a variable scoped to a workflow instance or session.

    When `workflow` is provided, writes to that workflow instance's variables.
    When `workflow` is not provided, writes to session-scoped shared variables
    (via SessionVariableManager), falling back to workflow_states for backward compat.

    Args:
        state_manager: WorkflowStateManager instance
        session_manager: LocalSessionManager instance
        db: LocalDatabase instance
        name: Variable name (e.g., "session_epic", "is_worktree")
        value: Variable value (string, number, boolean, or null)
        session_id: Session reference (accepts #N, N, UUID, or prefix)
        workflow: Optional workflow name to scope the variable to
        instance_manager: Optional WorkflowInstanceManager for workflow-scoped writes
        session_var_manager: Optional SessionVariableManager for session-scoped writes

    Returns:
        Success status and updated variables
    """
    # Require explicit session_id to prevent cross-session bleed
    if not session_id:
        return {
            "ok": False,
            "error": "session_id is required. Pass the session ID explicitly to prevent cross-session variable bleed.",
        }

    # Resolve session_id to UUID (accepts #N, N, UUID, or prefix)
    try:
        resolved_session_id = resolve_session_id(session_manager, session_id)
    except ValueError as e:
        return {"ok": False, "error": str(e)}

    # Coerce value types
    value = _coerce_value(value)

    # Resolve session_task references (#N or N) to UUIDs upfront
    if name == "session_task" and isinstance(value, str):
        try:
            value = resolve_session_task_value(value, resolved_session_id, session_manager, db)
        except (ValueError, KeyError) as e:
            logger.warning(
                "Failed to resolve session_task value %r for session %s: %s",
                value,
                resolved_session_id,
                e,
            )
            return {
                "ok": False,
                "error": f"Failed to resolve session_task value '{value}': {e}",
            }

    # Workflow-scoped: write to workflow_instances.variables
    if workflow:
        if not instance_manager:
            return {"ok": False, "error": "Workflow-scoped variables require instance_manager"}
        instance = instance_manager.get_instance(resolved_session_id, workflow)
        if not instance:
            return {
                "ok": False,
                "error": f"No workflow instance '{workflow}' found for session",
            }
        instance.variables[name] = value
        instance_manager.save_instance(instance)
        return {"ok": True, "value": value, "scope": "workflow", "workflow": workflow}

    # Session-scoped: write to session_variables table
    if session_var_manager:
        session_var_manager.set_variable(resolved_session_id, name, value)
        return {"ok": True, "value": value, "scope": "session"}

    # Backward compat: write to workflow_states.variables
    state = state_manager.get_state(resolved_session_id)
    if not state:
        state = WorkflowState(
            session_id=resolved_session_id,
            workflow_name="__lifecycle__",
            step="",
            step_entered_at=datetime.now(UTC),
            variables={},
        )

    # Block modification of session_task when a real workflow is active
    if name == "session_task" and state.workflow_name not in ("__lifecycle__", "__ended__"):
        current_value = state.variables.get("session_task")
        if current_value is not None and value != current_value:
            return {
                "ok": False,
                "error": (
                    f"Cannot modify session_task while workflow '{state.workflow_name}' is active. "
                    f"Current value: {current_value}. "
                    f"Use end_workflow() first if you need to change the tracked task."
                ),
            }

    state.variables[name] = value
    state_manager.save_state(state)

    if name == "session_task" and state.workflow_name == "__lifecycle__":
        return {
            "ok": True,
            "value": value,
            "warning": (
                "DEPRECATED: Setting session_task via set_variable on __lifecycle__ workflow. "
                "Prefer using activate_workflow(variables={session_task: ...}) instead."
            ),
        }

    return {"ok": True, "value": value}


def get_variable(
    state_manager: WorkflowStateManager,
    session_manager: LocalSessionManager,
    name: str | None = None,
    session_id: str | None = None,
    workflow: str | None = None,
    instance_manager: WorkflowInstanceManager | None = None,
    session_var_manager: SessionVariableManager | None = None,
) -> dict[str, Any]:
    """
    Get variable(s) scoped to a workflow instance or session.

    When `workflow` is provided, reads from that workflow instance's variables.
    When `workflow` is not provided, reads from session-scoped shared variables,
    falling back to workflow_states for backward compat.

    Args:
        state_manager: WorkflowStateManager instance
        session_manager: LocalSessionManager instance
        name: Variable name to get (if None, returns all variables)
        session_id: Session reference (accepts #N, N, UUID, or prefix)
        workflow: Optional workflow name to scope the read to
        instance_manager: Optional WorkflowInstanceManager for workflow-scoped reads
        session_var_manager: Optional SessionVariableManager for session-scoped reads

    Returns:
        Variable value(s) and session info
    """
    # Require explicit session_id to prevent cross-session bleed
    if not session_id:
        return {
            "ok": False,
            "error": "session_id is required. Pass the session ID explicitly to prevent cross-session variable bleed.",
        }

    # Resolve session_id to UUID (accepts #N, N, UUID, or prefix)
    try:
        resolved_session_id = resolve_session_id(session_manager, session_id)
    except ValueError as e:
        return {"ok": False, "error": str(e)}

    # Workflow-scoped: read from workflow_instances.variables
    if workflow:
        if not instance_manager:
            return {"ok": False, "error": "Workflow-scoped variables require instance_manager"}
        instance = instance_manager.get_instance(resolved_session_id, workflow)
        if not instance:
            return {
                "ok": False,
                "error": f"No workflow instance '{workflow}' found for session",
            }
        variables = instance.variables
        if name:
            return {
                "ok": True,
                "session_id": resolved_session_id,
                "variable": name,
                "value": variables.get(name),
                "exists": name in variables,
                "scope": "workflow",
                "workflow": workflow,
            }
        return {
            "ok": True,
            "session_id": resolved_session_id,
            "variables": variables,
            "scope": "workflow",
            "workflow": workflow,
        }

    # Session-scoped: read from session_variables table
    if session_var_manager:
        variables = session_var_manager.get_variables(resolved_session_id)
        if name:
            return {
                "ok": True,
                "session_id": resolved_session_id,
                "variable": name,
                "value": variables.get(name),
                "exists": name in variables,
                "scope": "session",
            }
        return {
            "ok": True,
            "session_id": resolved_session_id,
            "variables": variables,
            "scope": "session",
        }

    # Backward compat: read from workflow_states.variables
    state = state_manager.get_state(resolved_session_id)
    if not state:
        if name:
            return {
                "ok": True,
                "session_id": resolved_session_id,
                "variable": name,
                "value": None,
                "exists": False,
            }
        return {
            "ok": True,
            "session_id": resolved_session_id,
            "variables": {},
        }

    if name:
        value = state.variables.get(name)
        return {
            "ok": True,
            "session_id": resolved_session_id,
            "variable": name,
            "value": value,
            "exists": name in state.variables,
        }

    return {
        "ok": True,
        "session_id": resolved_session_id,
        "variables": state.variables,
    }


def set_session_variable(
    session_manager: LocalSessionManager,
    session_var_manager: SessionVariableManager,
    name: str,
    value: str | int | float | bool | None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """
    Set a session-scoped shared variable (visible to all workflows).

    Args:
        session_manager: LocalSessionManager instance
        session_var_manager: SessionVariableManager instance
        name: Variable name
        value: Variable value
        session_id: Session reference (accepts #N, N, UUID, or prefix)

    Returns:
        Success status
    """
    if not session_id:
        return {
            "ok": False,
            "error": "session_id is required.",
        }

    try:
        resolved_session_id = resolve_session_id(session_manager, session_id)
    except ValueError as e:
        return {"ok": False, "error": str(e)}

    value = _coerce_value(value)
    session_var_manager.set_variable(resolved_session_id, name, value)
    return {"ok": True, "value": value, "scope": "session"}
