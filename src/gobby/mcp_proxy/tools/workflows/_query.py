"""
Query tools for workflows.
"""

import logging
from pathlib import Path
from typing import Any

import yaml

from gobby.mcp_proxy.tools.workflows._resolution import resolve_session_id
from gobby.storage.sessions import LocalSessionManager
from gobby.utils.project_context import get_workflow_project_path
from gobby.workflows.loader import WorkflowLoader
from gobby.workflows.state_manager import WorkflowStateManager

logger = logging.getLogger(__name__)


def get_workflow(
    loader: WorkflowLoader,
    name: str,
    project_path: str | None = None,
) -> dict[str, Any]:
    """
    Get workflow details including steps, triggers, and settings.

    Args:
        loader: WorkflowLoader instance
        name: Workflow name (without .yaml extension)
        project_path: Project directory path. Auto-discovered from cwd if not provided.

    Returns:
        Workflow definition details
    """
    # Auto-discover project path if not provided
    if not project_path:
        discovered = get_workflow_project_path()
        if discovered:
            project_path = str(discovered)

    proj = Path(project_path) if project_path else None
    definition = loader.load_workflow(name, proj)

    if not definition:
        return {"success": False, "error": f"Workflow '{name}' not found"}

    return {
        "success": True,
        "name": definition.name,
        "type": definition.type,
        "description": definition.description,
        "version": definition.version,
        "steps": (
            [
                {
                    "name": s.name,
                    "description": s.description,
                    "allowed_tools": s.allowed_tools,
                    "blocked_tools": s.blocked_tools,
                }
                for s in definition.steps
            ]
            if definition.steps
            else []
        ),
        "triggers": (
            {name: len(actions) for name, actions in definition.triggers.items()}
            if definition.triggers
            else {}
        ),
        "settings": definition.settings,
    }


def list_workflows(
    loader: WorkflowLoader,
    project_path: str | None = None,
    workflow_type: str | None = None,
    global_only: bool = False,
) -> dict[str, Any]:
    """
    List available workflows.

    Lists workflows from both project (.gobby/workflows) and global (~/.gobby/workflows)
    directories. Project workflows shadow global ones with the same name.

    Args:
        loader: WorkflowLoader instance
        project_path: Project directory path. Auto-discovered from cwd if not provided.
        workflow_type: Filter by type ("step" or "lifecycle")
        global_only: If True, only show global workflows (ignore project)

    Returns:
        List of workflows with name, type, description, and source
    """

    # Auto-discover project path if not provided
    if not project_path:
        discovered = get_workflow_project_path()
        if discovered:
            project_path = str(discovered)

    search_dirs = list(loader.global_dirs)
    proj = Path(project_path) if project_path else None

    # Include project workflows unless global_only (project searched first to shadow global)
    if not global_only and proj:
        project_dir = proj / ".gobby" / "workflows"
        if project_dir.exists():
            search_dirs.insert(0, project_dir)

    workflows = []
    seen_names = set()

    for search_dir in search_dirs:
        if not search_dir.exists():
            continue

        is_project = proj and search_dir == (proj / ".gobby" / "workflows")

        for yaml_path in search_dir.glob("*.yaml"):
            name = yaml_path.stem
            if name in seen_names:
                continue

            try:
                with open(yaml_path, encoding="utf-8") as f:
                    data = yaml.safe_load(f)

                if not data:
                    continue

                wf_type = data.get("type", "step")

                if workflow_type and wf_type != workflow_type:
                    continue

                workflows.append(
                    {
                        "name": name,
                        "type": wf_type,
                        "description": data.get("description", ""),
                        "source": "project" if is_project else "global",
                    }
                )
                seen_names.add(name)

            except Exception as e:
                logger.debug(
                    "Skipping invalid workflow file %s: %s",
                    yaml_path,
                    e,
                    exc_info=True,
                )  # nosec B110

    return {"workflows": workflows, "count": len(workflows)}


def get_workflow_status(
    state_manager: WorkflowStateManager,
    session_manager: LocalSessionManager,
    session_id: str | None = None,
) -> dict[str, Any]:
    """
    Get current workflow step and state.

    Args:
        state_manager: WorkflowStateManager instance
        session_manager: LocalSessionManager instance
        session_id: Session reference (accepts #N, N, UUID, or prefix) - required to prevent cross-session bleed

    Returns:
        Workflow state including step, action counts, artifacts
    """
    # Require explicit session_id to prevent cross-session bleed
    if not session_id:
        return {
            "has_workflow": False,
            "error": "session_id is required. Pass the session ID explicitly to prevent cross-session variable bleed.",
        }

    # Resolve session_id to UUID (accepts #N, N, UUID, or prefix)
    try:
        resolved_session_id = resolve_session_id(session_manager, session_id)
    except ValueError as e:
        return {"has_workflow": False, "error": str(e)}

    state = state_manager.get_state(resolved_session_id)
    if not state:
        return {"has_workflow": False, "session_id": resolved_session_id}

    return {
        "has_workflow": True,
        "session_id": resolved_session_id,
        "workflow_name": state.workflow_name,
        "step": state.step,
        "step_action_count": state.step_action_count,
        "total_action_count": state.total_action_count,
        "reflection_pending": state.reflection_pending,
        "artifacts": list(state.artifacts.keys()) if state.artifacts else [],
        "variables": state.variables,
        "task_progress": (
            f"{state.current_task_index + 1}/{len(state.task_list)}" if state.task_list else None
        ),
        "updated_at": state.updated_at.isoformat() if state.updated_at else None,
    }
