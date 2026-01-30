"""ActionHandler wrappers for enforcement actions.

These handlers match the ActionHandler protocol: (context: ActionContext, **kwargs) -> dict | None
They bridge the workflow engine to the core enforcement functions.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from gobby.workflows.enforcement.blocking import block_tools, track_schema_lookup
from gobby.workflows.enforcement.commit_policy import (
    capture_baseline_dirty_files,
    require_commit_before_stop,
    require_task_review_or_close_before_stop,
)
from gobby.workflows.enforcement.task_policy import (
    require_active_task,
    require_task_complete,
    validate_session_task_scope,
)

if TYPE_CHECKING:
    from gobby.storage.tasks import LocalTaskManager

logger = logging.getLogger(__name__)

__all__ = [
    "handle_block_tools",
    "handle_capture_baseline_dirty_files",
    "handle_require_active_task",
    "handle_require_commit_before_stop",
    "handle_require_task_complete",
    "handle_require_task_review_or_close_before_stop",
    "handle_track_schema_lookup",
    "handle_validate_session_task_scope",
]


async def handle_capture_baseline_dirty_files(
    context: Any,
    task_manager: LocalTaskManager | None = None,
    **kwargs: Any,
) -> dict[str, Any] | None:
    """ActionHandler wrapper for capture_baseline_dirty_files.

    Note: project_path comes from session's project lookup or event_data.cwd.
    """
    from gobby.storage.projects import LocalProjectManager

    # Get project path - prioritize session lookup over hook payload
    project_path = None

    # 1. Get from session's project (most reliable - session exists by now)
    if context.session_id and context.session_manager:
        session = context.session_manager.get(context.session_id)
        if session and session.project_id:
            project_mgr = LocalProjectManager(context.db)
            project = project_mgr.get(session.project_id)
            if project and project.repo_path:
                project_path = project.repo_path

    # 2. Fallback to event_data.cwd (from hook payload)
    if not project_path and context.event_data:
        project_path = context.event_data.get("cwd")

    return await capture_baseline_dirty_files(
        workflow_state=context.state,
        project_path=project_path,
    )


async def handle_require_commit_before_stop(
    context: Any,
    task_manager: LocalTaskManager | None = None,
    **kwargs: Any,
) -> dict[str, Any] | None:
    """ActionHandler wrapper for require_commit_before_stop.

    Note: task_manager must be passed via closure from executor.
    """
    from gobby.storage.projects import LocalProjectManager

    # Get project path
    project_path = None

    if context.session_id and context.session_manager:
        session = context.session_manager.get(context.session_id)
        if session and session.project_id:
            project_mgr = LocalProjectManager(context.db)
            project = project_mgr.get(session.project_id)
            if project and project.repo_path:
                project_path = project.repo_path

    if not project_path and context.event_data:
        project_path = context.event_data.get("cwd")

    return await require_commit_before_stop(
        workflow_state=context.state,
        project_path=project_path,
        task_manager=task_manager,
    )


async def handle_require_task_review_or_close_before_stop(
    context: Any,
    task_manager: LocalTaskManager | None = None,
    **kwargs: Any,
) -> dict[str, Any] | None:
    """ActionHandler wrapper for require_task_review_or_close_before_stop."""
    project_id = None
    if context.session_manager:
        session = context.session_manager.get(context.session_id)
        if session:
            project_id = session.project_id

    return await require_task_review_or_close_before_stop(
        workflow_state=context.state,
        task_manager=task_manager,
        project_id=project_id,
    )


async def handle_validate_session_task_scope(
    context: Any,
    task_manager: LocalTaskManager | None = None,
    **kwargs: Any,
) -> dict[str, Any] | None:
    """ActionHandler wrapper for validate_session_task_scope."""
    return await validate_session_task_scope(
        task_manager=task_manager,
        workflow_state=context.state,
        event_data=context.event_data,
    )


async def handle_block_tools(
    context: Any,
    task_manager: LocalTaskManager | None = None,
    **kwargs: Any,
) -> dict[str, Any] | None:
    """ActionHandler wrapper for block_tools.

    Passes task_manager via closure from register_defaults.
    """
    from gobby.storage.projects import LocalProjectManager

    # Get project_path for git dirty file checks
    project_path = kwargs.get("project_path")
    if not project_path and context.event_data:
        project_path = context.event_data.get("cwd")

    # Get source from session for is_plan_file checks
    source = None
    current_session = None
    if context.session_manager:
        current_session = context.session_manager.get(context.session_id)
        if current_session:
            source = current_session.source

    # Fallback to session's project path
    if not project_path and current_session and context.db:
        project_mgr = LocalProjectManager(context.db)
        project = project_mgr.get(current_session.project_id)
        if project and project.repo_path:
            project_path = project.repo_path

    return await block_tools(
        rules=kwargs.get("rules"),
        event_data=context.event_data,
        workflow_state=context.state,
        project_path=project_path,
        task_manager=task_manager,
        source=source,
    )


async def handle_require_active_task(
    context: Any,
    task_manager: LocalTaskManager | None = None,
    **kwargs: Any,
) -> dict[str, Any] | None:
    """ActionHandler wrapper for require_active_task.

    DEPRECATED: Use block_tools action with rules instead.
    Kept for backward compatibility with existing workflows.
    """
    # Get project_id from session for project-scoped task filtering
    current_session = None
    project_id = None
    if context.session_manager:
        current_session = context.session_manager.get(context.session_id)
        if current_session:
            project_id = current_session.project_id

    return await require_active_task(
        task_manager=task_manager,
        session_id=context.session_id,
        config=context.config,
        event_data=context.event_data,
        project_id=project_id,
        workflow_state=context.state,
        session_manager=context.session_manager,
        session_task_manager=context.session_task_manager,
    )


async def handle_require_task_complete(
    context: Any,
    task_manager: LocalTaskManager | None = None,
    template_engine: Any | None = None,
    **kwargs: Any,
) -> dict[str, Any] | None:
    """ActionHandler wrapper for require_task_complete.

    Supports:
    - Single task ID: "#47"
    - List of task IDs: ["#47", "#48"]
    - Wildcard: "*" - work until no ready tasks remain
    """
    project_id = None
    if context.session_manager and context.session_id:
        session = context.session_manager.get(context.session_id)
        if session:
            project_id = session.project_id

    # Get task_id from kwargs - may be a template that needs resolving
    task_spec = kwargs.get("task_id")

    # If it's a template reference like "{{ variables.session_task }}", resolve it
    if task_spec and "{{" in str(task_spec) and template_engine:
        task_spec = template_engine.render(
            str(task_spec),
            {"variables": context.state.variables if context.state else {}},
        )

    # Handle different task_spec types:
    # - None/empty: no enforcement
    # - "*": wildcard - fetch ready tasks
    # - list: multiple specific tasks
    # - string: single task ID
    task_ids: list[str] | None = None

    if not task_spec:
        return None
    elif task_spec == "*":
        # Wildcard: get all ready tasks for this project
        if task_manager:
            ready_tasks = task_manager.list_ready_tasks(
                project_id=project_id,
                limit=100,
            )
            task_ids = [t.id for t in ready_tasks]
            if not task_ids:
                # No ready tasks - allow stop
                return None
    elif isinstance(task_spec, list):
        task_ids = task_spec
    else:
        task_ids = [str(task_spec)]

    return await require_task_complete(
        task_manager=task_manager,
        session_id=context.session_id,
        task_ids=task_ids,
        event_data=context.event_data,
        project_id=project_id,
        workflow_state=context.state,
    )


async def handle_track_schema_lookup(
    context: Any,
    task_manager: LocalTaskManager | None = None,
    **kwargs: Any,
) -> dict[str, Any] | None:
    """ActionHandler wrapper for track_schema_lookup.

    Tracks successful get_tool_schema calls to unlock tools for call_tool.
    Should be triggered on on_after_tool when the tool is get_tool_schema.
    """
    if not context.event_data:
        return None

    tool_name = context.event_data.get("tool_name", "")
    is_failure = context.event_data.get("is_failure", False)

    # Only track successful get_tool_schema calls
    # Handle both native MCP format and Gobby proxy format
    if tool_name not in ("get_tool_schema", "mcp__gobby__get_tool_schema"):
        return None

    if is_failure:
        return None

    # Extract tool_input - for MCP proxy, it's in tool_input directly
    tool_input = context.event_data.get("tool_input", {}) or {}

    return track_schema_lookup(
        tool_input=tool_input,
        workflow_state=context.state,
    )
