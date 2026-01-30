"""
Lifecycle tools for workflows (activate, end, transition).
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from gobby.mcp_proxy.tools.workflows._resolution import (
    resolve_session_id,
    resolve_session_task_value,
)
from gobby.storage.database import DatabaseProtocol
from gobby.storage.sessions import LocalSessionManager
from gobby.utils.project_context import get_workflow_project_path
from gobby.workflows.definitions import WorkflowState
from gobby.workflows.loader import WorkflowLoader
from gobby.workflows.state_manager import WorkflowStateManager


def activate_workflow(
    loader: WorkflowLoader,
    state_manager: WorkflowStateManager,
    session_manager: LocalSessionManager,
    db: DatabaseProtocol,
    name: str,
    session_id: str | None = None,
    initial_step: str | None = None,
    variables: dict[str, Any] | None = None,
    project_path: str | None = None,
) -> dict[str, Any]:
    """
    Activate a step-based workflow for the current session.

    Args:
        loader: WorkflowLoader instance
        state_manager: WorkflowStateManager instance
        session_manager: LocalSessionManager instance
        db: LocalDatabase instance
        name: Workflow name (e.g., "plan-act-reflect", "auto-task")
        session_id: Session reference (accepts #N, N, UUID, or prefix) - required to prevent cross-session bleed
        initial_step: Optional starting step (defaults to first step)
        variables: Optional initial variables to set (merged with workflow defaults)
        project_path: Project directory path. Auto-discovered from cwd if not provided.

    Returns:
        Success status, workflow info, and current step.
    """
    # Auto-discover project path if not provided
    if not project_path:
        discovered = get_workflow_project_path()
        if discovered:
            project_path = str(discovered)

    proj = Path(project_path) if project_path else None

    # Load workflow
    definition = loader.load_workflow(name, proj)
    if not definition:
        return {"success": False, "error": f"Workflow '{name}' not found"}

    if definition.type == "lifecycle":
        return {
            "success": False,
            "error": f"Workflow '{name}' is lifecycle type (auto-runs on events, not manually activated)",
        }

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

    # Check for existing workflow
    # Allow if:
    # - No existing state
    # - Existing is __lifecycle__ placeholder
    # - Existing is a lifecycle-type workflow (they run concurrently with step workflows)
    existing = state_manager.get_state(resolved_session_id)
    if existing and existing.workflow_name != "__lifecycle__":
        # Check if existing workflow is a lifecycle type
        existing_def = loader.load_workflow(existing.workflow_name, proj)
        # Only allow if we can confirm it's a lifecycle workflow
        # If definition not found or it's a step workflow, block activation
        if not existing_def or existing_def.type != "lifecycle":
            # It's a step workflow (or unknown) - can only have one active
            return {
                "success": False,
                "error": f"Session already has step workflow '{existing.workflow_name}' active. Use end_workflow first.",
            }
        # Existing is a lifecycle workflow - allow step workflow to activate alongside it

    # Determine initial step
    if initial_step:
        if not any(s.name == initial_step for s in definition.steps):
            return {
                "success": False,
                "error": f"Step '{initial_step}' not found. Available: {[s.name for s in definition.steps]}",
            }
        step = initial_step
    else:
        if not definition.steps:
            return {
                "success": False,
                "error": f"Workflow '{name}' has no steps defined. Cannot activate a workflow without steps.",
            }
        step = definition.steps[0].name

    # Merge variables: preserve existing lifecycle variables, then apply workflow declarations
    # Priority: existing state < workflow defaults < passed-in variables
    # This preserves lifecycle variables (like unlocked_tools) that the step workflow doesn't declare
    merged_variables = dict(existing.variables) if existing else {}
    merged_variables.update(definition.variables)  # Override with workflow-declared defaults
    if variables:
        merged_variables.update(variables)  # Override with passed-in values

    # Resolve session_task references (#N or N) to UUIDs upfront
    # This prevents repeated resolution failures in condition evaluation
    if "session_task" in merged_variables:
        session_task_val = merged_variables["session_task"]
        if isinstance(session_task_val, str):
            merged_variables["session_task"] = resolve_session_task_value(
                session_task_val, resolved_session_id, session_manager, db
            )

    # Create state
    state = WorkflowState(
        session_id=resolved_session_id,
        workflow_name=name,
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

    state_manager.save_state(state)

    return {
        "success": True,
        "session_id": resolved_session_id,
        "workflow": name,
        "step": step,
        "steps": [s.name for s in definition.steps],
        "variables": merged_variables,
    }


def end_workflow(
    loader: WorkflowLoader,
    state_manager: WorkflowStateManager,
    session_manager: LocalSessionManager,
    session_id: str | None = None,
    reason: str | None = None,
    project_path: str | None = None,
) -> dict[str, Any]:
    """
    End the currently active step-based workflow.

    Allows starting a different workflow afterward.
    Does not affect lifecycle workflows (they continue running).

    Args:
        loader: WorkflowLoader instance
        state_manager: WorkflowStateManager instance
        session_manager: LocalSessionManager instance
        session_id: Session reference (accepts #N, N, UUID, or prefix) - required to prevent cross-session bleed
        reason: Optional reason for ending
        project_path: Project directory path. Auto-discovered from cwd if not provided.

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

    # Check if this is a lifecycle workflow - those cannot be ended manually
    # Auto-discover project path if not provided
    if not project_path:
        discovered = get_workflow_project_path()
        if discovered:
            project_path = str(discovered)

    proj = Path(project_path) if project_path else None
    definition = loader.load_workflow(state.workflow_name, proj)

    # If definition exists and is lifecycle type, block manual ending
    if definition and definition.type == "lifecycle":
        return {
            "success": False,
            "error": f"Workflow '{state.workflow_name}' is lifecycle type (auto-runs on events, cannot be manually ended).",
        }

    state_manager.delete_state(resolved_session_id)

    return {"success": True, "workflow": state.workflow_name, "reason": reason}


def request_step_transition(
    loader: WorkflowLoader,
    state_manager: WorkflowStateManager,
    session_manager: LocalSessionManager,
    to_step: str,
    reason: str | None = None,
    session_id: str | None = None,
    force: bool = False,
    project_path: str | None = None,
) -> dict[str, Any]:
    """
    Request transition to a different step. May require approval.

    Args:
        loader: WorkflowLoader instance
        state_manager: WorkflowStateManager instance
        session_manager: LocalSessionManager instance
        to_step: Target step name
        reason: Reason for transition
        session_id: Session reference (accepts #N, N, UUID, or prefix) - required to prevent cross-session bleed
        force: Skip exit condition checks
        project_path: Project directory path. Auto-discovered from cwd if not provided.

    Returns:
        Success status and new step info
    """
    # Auto-discover project path if not provided
    if not project_path:
        discovered = get_workflow_project_path()
        if discovered:
            project_path = str(discovered)

    proj = Path(project_path) if project_path else None

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

    # Load workflow to validate step
    definition = loader.load_workflow(state.workflow_name, proj)
    if not definition:
        return {"success": False, "error": f"Workflow '{state.workflow_name}' not found"}

    if not any(s.name == to_step for s in definition.steps):
        return {
            "success": False,
            "error": f"Step '{to_step}' not found. Available: {[s.name for s in definition.steps]}",
        }

    # Block manual transitions to steps that have conditional auto-transitions
    # These steps should only be reached when their conditions are met
    # Skip this check when force=True to allow bypassing workflow guards
    if not force:
        current_step_def = next((s for s in definition.steps if s.name == state.step), None)
        if current_step_def and current_step_def.transitions:
            for transition in current_step_def.transitions:
                if transition.to == to_step and transition.when:
                    # This step has a conditional transition - block manual transition
                    return {
                        "success": False,
                        "error": (
                            f"Step '{to_step}' has a conditional auto-transition "
                            f"(when: {transition.when}). Manual transitions to this step "
                            f"are blocked to prevent workflow circumvention. "
                            f"The transition will occur automatically when the condition is met."
                        ),
                    }

    old_step = state.step
    state.step = to_step
    state.step_entered_at = datetime.now(UTC)
    state.step_action_count = 0

    state_manager.save_state(state)

    return {
        "success": True,
        "from_step": old_step,
        "to_step": to_step,
        "reason": reason,
        "forced": force,
    }
