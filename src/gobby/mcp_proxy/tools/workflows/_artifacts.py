"""
Artifact and variable tools for workflows.
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
from gobby.workflows.state_manager import WorkflowStateManager

logger = logging.getLogger(__name__)


def mark_artifact_complete(
    state_manager: WorkflowStateManager,
    session_manager: LocalSessionManager,
    artifact_type: str,
    file_path: str,
    session_id: str | None = None,
) -> dict[str, Any]:
    """
    Register an artifact as complete.

    Args:
        state_manager: WorkflowStateManager instance
        session_manager: LocalSessionManager instance
        artifact_type: Type of artifact (e.g., "plan", "spec", "test")
        file_path: Path to the artifact file
        session_id: Session reference (accepts #N, N, UUID, or prefix) - required to prevent cross-session bleed

    Returns:
        Success status
    """
    # Require explicit session_id to prevent cross-session bleed
    if not session_id:
        return {
            "success": False,
            "error": "session_id is required. Pass the session ID explicitly to prevent cross-session variable bleed.",
        }

    # Resolve session_id to UUID (accepts #N, N, UUID, or prefix)
    try:
        resolved_session_id = resolve_session_id(session_manager, session_id)
    except ValueError as e:
        return {"success": False, "error": str(e)}

    state = state_manager.get_state(resolved_session_id)
    if not state:
        return {"success": False, "error": "No workflow active for session"}

    # Update artifacts
    state.artifacts[artifact_type] = file_path
    state_manager.save_state(state)

    return {"success": True}


def set_variable(
    state_manager: WorkflowStateManager,
    session_manager: LocalSessionManager,
    db: DatabaseProtocol,
    name: str,
    value: str | int | float | bool | None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """
    Set a workflow variable for the current session.

    Variables set this way are session-scoped - they persist in the database
    for the duration of the session but do not modify the workflow YAML file.

    This is useful for:
    - Setting session_epic to enforce epic completion before stopping
    - Setting is_worktree to mark a session as a worktree agent
    - Dynamic configuration without modifying workflow definitions

    Args:
        state_manager: WorkflowStateManager instance
        session_manager: LocalSessionManager instance
        db: LocalDatabase instance
        name: Variable name (e.g., "session_epic", "is_worktree")
        value: Variable value (string, number, boolean, or null)
        session_id: Session reference (accepts #N, N, UUID, or prefix) - required to prevent cross-session bleed

    Returns:
        Success status and updated variables
    """
    # Require explicit session_id to prevent cross-session bleed
    if not session_id:
        return {
            "success": False,
            "error": "session_id is required. Pass the session ID explicitly to prevent cross-session variable bleed.",
        }

    # Resolve session_id to UUID (accepts #N, N, UUID, or prefix)
    try:
        resolved_session_id = resolve_session_id(session_manager, session_id)
    except ValueError as e:
        return {"success": False, "error": str(e)}

    # Get or create state
    state = state_manager.get_state(resolved_session_id)
    if not state:
        # Create a minimal lifecycle state for variable storage
        state = WorkflowState(
            session_id=resolved_session_id,
            workflow_name="__lifecycle__",
            step="",
            step_entered_at=datetime.now(UTC),
            variables={},
        )

    # Block modification of session_task when a real workflow is active
    # This prevents circumventing workflows by changing the tracked task
    if name == "session_task" and state.workflow_name != "__lifecycle__":
        current_value = state.variables.get("session_task")
        if current_value is not None and value != current_value:
            return {
                "success": False,
                "error": (
                    f"Cannot modify session_task while workflow '{state.workflow_name}' is active. "
                    f"Current value: {current_value}. "
                    f"Use end_workflow() first if you need to change the tracked task."
                ),
            }

    # Resolve session_task references (#N or N) to UUIDs upfront
    # This prevents repeated resolution failures in condition evaluation
    if name == "session_task" and isinstance(value, str):
        try:
            value = resolve_session_task_value(value, resolved_session_id, session_manager, db)
        except (ValueError, KeyError) as e:
            logger.warning(
                f"Failed to resolve session_task value '{value}' for session {resolved_session_id}: {e}"
            )
            return {
                "success": False,
                "error": f"Failed to resolve session_task value '{value}': {e}",
            }

    # Set the variable
    state.variables[name] = value
    state_manager.save_state(state)

    # Add deprecation warning for session_task on __lifecycle__ workflow
    if name == "session_task" and state.workflow_name == "__lifecycle__":
        return {
            "warning": (
                "DEPRECATED: Setting session_task via set_variable on __lifecycle__ workflow. "
                "Prefer using activate_workflow(variables={session_task: ...}) instead."
            )
        }

    return {}


def get_variable(
    state_manager: WorkflowStateManager,
    session_manager: LocalSessionManager,
    name: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """
    Get workflow variable(s) for the current session.

    Args:
        state_manager: WorkflowStateManager instance
        session_manager: LocalSessionManager instance
        name: Variable name to get (if None, returns all variables)
        session_id: Session reference (accepts #N, N, UUID, or prefix) - required to prevent cross-session bleed

    Returns:
        Variable value(s) and session info
    """
    # Require explicit session_id to prevent cross-session bleed
    if not session_id:
        return {
            "success": False,
            "error": "session_id is required. Pass the session ID explicitly to prevent cross-session variable bleed.",
        }

    # Resolve session_id to UUID (accepts #N, N, UUID, or prefix)
    try:
        resolved_session_id = resolve_session_id(session_manager, session_id)
    except ValueError as e:
        return {"success": False, "error": str(e)}

    state = state_manager.get_state(resolved_session_id)
    if not state:
        if name:
            return {
                "success": True,
                "session_id": resolved_session_id,
                "variable": name,
                "value": None,
                "exists": False,
            }
        return {
            "success": True,
            "session_id": resolved_session_id,
            "variables": {},
        }

    if name:
        value = state.variables.get(name)
        return {
            "success": True,
            "session_id": resolved_session_id,
            "variable": name,
            "value": value,
            "exists": name in state.variables,
        }

    return {
        "success": True,
        "session_id": resolved_session_id,
        "variables": state.variables,
    }
