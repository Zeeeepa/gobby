"""Context building functions for the workflow engine.

Extracted from engine.py as part of Strangler Fig decomposition (Wave 2).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from gobby.storage.projects import LocalProjectManager

from .engine_models import DotDict

if TYPE_CHECKING:
    from gobby.hooks.events import HookEvent

    from .actions import ActionExecutor
    from .definitions import WorkflowState

logger = logging.getLogger(__name__)


def _resolve_session_and_project(
    action_executor: ActionExecutor | None,
    event: HookEvent,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Look up session and project info for eval context.

    Returns:
        Tuple of (session_info dict, project_info dict)
    """
    session_info: dict[str, Any] = {}
    if (
        action_executor
        and action_executor.session_manager
        and event.machine_id
        and event.project_id
    ):
        session = action_executor.session_manager.find_by_external_id(
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
    if event.project_id and action_executor and action_executor.db:
        project_mgr = LocalProjectManager(action_executor.db)
        project = project_mgr.get(event.project_id)
        if project:
            project_info = {"name": project.name, "id": project.id}

    return session_info, project_info


def _build_eval_context(
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


