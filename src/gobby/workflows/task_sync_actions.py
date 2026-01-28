"""Task sync workflow actions.

Extracted from actions.py as part of strangler fig decomposition.
These functions handle task sync import/export and workflow task operations.
"""

import asyncio
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gobby.storage.database import DatabaseProtocol
    from gobby.storage.sessions import LocalSessionManager
    from gobby.workflows.definitions import WorkflowState

logger = logging.getLogger(__name__)


async def task_sync_import(
    task_sync_manager: Any,
    session_manager: "LocalSessionManager",
    session_id: str,
) -> dict[str, Any]:
    """Import tasks from JSONL file.

    Reads .gobby/tasks.jsonl and imports tasks into SQLite using
    Last-Write-Wins conflict resolution based on updated_at.

    Args:
        task_sync_manager: TaskSyncManager instance
        session_manager: Session manager for project lookup
        session_id: Current session ID

    Returns:
        Dict with imported status or error
    """
    if not task_sync_manager:
        logger.debug("task_sync_import: No task_sync_manager available")
        return {"error": "Task Sync Manager not available"}

    try:
        # Get project_id from session for project-scoped sync
        project_id = None
        session = await asyncio.to_thread(session_manager.get, session_id)
        if session:
            project_id = session.project_id

        await asyncio.to_thread(task_sync_manager.import_from_jsonl, project_id=project_id)
        logger.info("Task sync import completed")
        return {"imported": True}
    except Exception as e:
        logger.error(f"task_sync_import failed: {e}", exc_info=True)
        return {"error": str(e)}


async def task_sync_export(
    task_sync_manager: Any,
    session_manager: "LocalSessionManager",
    session_id: str,
) -> dict[str, Any]:
    """Export tasks to JSONL file.

    Writes tasks and dependencies to .gobby/tasks.jsonl for Git persistence.
    Uses content hashing to skip writes if nothing changed.

    Args:
        task_sync_manager: TaskSyncManager instance
        session_manager: Session manager for project lookup
        session_id: Current session ID

    Returns:
        Dict with exported status or error
    """
    if not task_sync_manager:
        logger.debug("task_sync_export: No task_sync_manager available")
        return {"error": "Task Sync Manager not available"}

    try:
        # Get project_id from session for project-scoped sync
        project_id = None
        session = await asyncio.to_thread(session_manager.get, session_id)
        if session:
            project_id = session.project_id

        await asyncio.to_thread(task_sync_manager.export_to_jsonl, project_id=project_id)
        logger.info("Task sync export completed")
        return {"exported": True}
    except Exception as e:
        logger.error(f"task_sync_export failed: {e}", exc_info=True)
        return {"error": str(e)}


async def persist_tasks(
    db: "DatabaseProtocol",
    session_manager: "LocalSessionManager",
    session_id: str,
    state: "WorkflowState",
    tasks: list[dict[str, Any]] | None = None,
    source: str | None = None,
    workflow_name: str | None = None,
    parent_task_id: str | None = None,
) -> dict[str, Any]:
    """Persist a list of task dicts to Gobby task system.

    Enhanced to support workflow integration with ID mapping.

    Args:
        db: Database instance
        session_manager: Session manager
        session_id: Current session ID
        state: WorkflowState for variables access
        tasks: List of task dicts
        source: Variable name containing task list (alternative to tasks)
        workflow_name: Associate tasks with this workflow
        parent_task_id: Optional parent task for all created tasks

    Returns:
        Dict with tasks_persisted count, ids list, and id_mapping dict
    """
    # Get tasks from either 'tasks' kwarg or 'source' variable
    task_list = tasks or []

    if source and state.variables:
        source_data = state.variables.get(source)
        if source_data:
            # Handle nested structure like task_list.tasks
            if isinstance(source_data, dict) and "tasks" in source_data:
                task_list = source_data["tasks"]
            elif isinstance(source_data, list):
                task_list = source_data

    if not task_list:
        return {"tasks_persisted": 0, "ids": [], "id_mapping": {}}

    try:
        from gobby.workflows.task_actions import persist_decomposed_tasks

        current_session = await asyncio.to_thread(session_manager.get, session_id)
        project_id = current_session.project_id if current_session else "default"

        # Get workflow name from kwargs or state
        wf_name = workflow_name
        if not wf_name and state.workflow_name:
            wf_name = state.workflow_name

        id_mapping = await asyncio.to_thread(
            persist_decomposed_tasks,
            db=db,
            project_id=project_id,
            tasks_data=task_list,
            workflow_name=wf_name or "unnamed",
            parent_task_id=parent_task_id,
            created_in_session_id=session_id,
        )

        # Store ID mapping in workflow state for reference
        if not state.variables:
            state.variables = {}
        state.variables["task_id_mapping"] = id_mapping

        return {
            "tasks_persisted": len(id_mapping),
            "ids": list(id_mapping.values()),
            "id_mapping": id_mapping,
        }
    except Exception as e:
        logger.error(f"persist_tasks: Failed: {e}", exc_info=True)
        return {"error": str(e)}


async def get_workflow_tasks(
    db: "DatabaseProtocol",
    session_manager: "LocalSessionManager",
    session_id: str,
    state: "WorkflowState",
    workflow_name: str | None = None,
    include_closed: bool = False,
    output_as: str | None = None,
) -> dict[str, Any]:
    """Get tasks associated with the current workflow.

    Args:
        db: Database instance
        session_manager: Session manager
        session_id: Current session ID
        state: WorkflowState for variables access
        workflow_name: Override workflow name (defaults to current)
        include_closed: Include closed tasks (default: False)
        output_as: Variable name to store result in

    Returns:
        Dict with tasks list and count
    """
    from gobby.workflows.task_actions import get_workflow_tasks as _get_workflow_tasks

    wf_name = workflow_name
    if not wf_name and state.workflow_name:
        wf_name = state.workflow_name

    if not wf_name:
        return {"error": "No workflow name specified"}

    try:
        current_session = await asyncio.to_thread(session_manager.get, session_id)
        project_id = current_session.project_id if current_session else None

        tasks = await asyncio.to_thread(
            _get_workflow_tasks,
            db=db,
            workflow_name=wf_name,
            project_id=project_id,
            include_closed=include_closed,
        )

        # Convert to dicts for YAML/JSON serialization
        tasks_data = [t.to_dict() for t in tasks]

        # Store in variable if requested
        if output_as:
            if not state.variables:
                state.variables = {}
            state.variables[output_as] = tasks_data

        # Also update task_list in state for workflow engine use
        state.task_list = [{"id": t.id, "title": t.title, "status": t.status} for t in tasks]

        return {"tasks": tasks_data, "count": len(tasks)}
    except Exception as e:
        logger.error(f"get_workflow_tasks: Failed: {e}", exc_info=True)
        return {"error": str(e)}


async def update_workflow_task(
    db: "DatabaseProtocol",
    state: "WorkflowState",
    task_id: str | None = None,
    status: str | None = None,
    verification: str | None = None,
    validation_status: str | None = None,
    validation_feedback: str | None = None,
) -> dict[str, Any]:
    """Update a task from workflow context.

    Args:
        db: Database instance
        state: WorkflowState for task_list access
        task_id: ID of task to update (required)
        status: New status
        verification: Verification result
        validation_status: Validation status
        validation_feedback: Validation feedback

    Returns:
        Dict with updated task data
    """
    from gobby.workflows.task_actions import update_task_from_workflow

    tid = task_id
    if not tid:
        # Try to get from current_task_index in state
        if state.task_list and state.current_task_index is not None:
            idx = state.current_task_index
            if 0 <= idx < len(state.task_list):
                tid = state.task_list[idx].get("id")

    if not tid:
        return {"error": "No task_id specified"}

    try:
        task = await asyncio.to_thread(
            update_task_from_workflow,
            db=db,
            task_id=tid,
            status=status,
            verification=verification,
            validation_status=validation_status,
            validation_feedback=validation_feedback,
        )

        if task:
            return {"updated": True, "task": task.to_dict()}
        return {"updated": False, "error": "Task not found"}
    except Exception as e:
        logger.error(f"update_workflow_task: Failed for task {tid}: {e}", exc_info=True)
        return {"updated": False, "error": str(e)}


# --- ActionHandler-compatible wrappers ---
# These match the ActionHandler protocol: (context: ActionContext, **kwargs) -> dict | None


async def handle_task_sync_import(context: Any, **kwargs: Any) -> dict[str, Any] | None:
    """ActionHandler wrapper for task_sync_import."""
    return await task_sync_import(
        task_sync_manager=context.task_sync_manager,
        session_manager=context.session_manager,
        session_id=context.session_id,
    )


async def handle_task_sync_export(context: Any, **kwargs: Any) -> dict[str, Any] | None:
    """ActionHandler wrapper for task_sync_export."""
    return await task_sync_export(
        task_sync_manager=context.task_sync_manager,
        session_manager=context.session_manager,
        session_id=context.session_id,
    )


async def handle_persist_tasks(context: Any, **kwargs: Any) -> dict[str, Any] | None:
    """ActionHandler wrapper for persist_tasks."""
    return await persist_tasks(
        db=context.db,
        session_manager=context.session_manager,
        session_id=context.session_id,
        state=context.state,
        tasks=kwargs.get("tasks"),
        source=kwargs.get("source"),
        workflow_name=kwargs.get("workflow_name"),
        parent_task_id=kwargs.get("parent_task_id"),
    )


async def handle_get_workflow_tasks(context: Any, **kwargs: Any) -> dict[str, Any] | None:
    """ActionHandler wrapper for get_workflow_tasks."""
    return await get_workflow_tasks(
        db=context.db,
        session_manager=context.session_manager,
        session_id=context.session_id,
        state=context.state,
        workflow_name=kwargs.get("workflow_name"),
        include_closed=kwargs.get("include_closed", False),
        output_as=kwargs.get("as"),
    )


async def handle_update_workflow_task(context: Any, **kwargs: Any) -> dict[str, Any] | None:
    """ActionHandler wrapper for update_workflow_task."""
    return await update_workflow_task(
        db=context.db,
        state=context.state,
        task_id=kwargs.get("task_id"),
        status=kwargs.get("status"),
        verification=kwargs.get("verification"),
        validation_status=kwargs.get("validation_status"),
        validation_feedback=kwargs.get("validation_feedback"),
    )
