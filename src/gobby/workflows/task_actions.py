"""Workflow-Task integration module.

Provides functions for integrating the task system with the workflow engine:
- persist_decomposed_tasks(): Create tasks from workflow decomposition with ID mapping
- update_task_from_workflow(): Update task fields from workflow state
- get_workflow_tasks(): Retrieve tasks for a workflow state
"""

import logging
from typing import Any

from gobby.storage.database import DatabaseProtocol
from gobby.storage.tasks import LocalTaskManager, Task

logger = logging.getLogger(__name__)


def persist_decomposed_tasks(
    db: DatabaseProtocol,
    project_id: str,
    tasks_data: list[dict[str, Any]],
    workflow_name: str,
    parent_task_id: str | None = None,
    created_in_session_id: str | None = None,
) -> dict[str, str]:
    """Persist a list of decomposed tasks to the database with ID mapping.

    Takes task data from workflow decomposition (e.g., from LLM output) and creates
    persistent tasks in the database. Returns a mapping from original task references
    (e.g., "1", "task_1") to the generated database IDs.

    Args:
        db: LocalDatabase instance
        project_id: Project ID to create tasks in
        tasks_data: List of task dicts from decomposition, each with:
            - id (str/int): Original reference ID (optional, uses index if missing)
            - title or description (str): Task title (required)
            - verification (str): How to verify completion (optional)
            - priority (int): Task priority 1-3 (optional, default 2)
            - labels (list[str]): Task labels (optional)
        workflow_name: Name of the workflow these tasks belong to
        parent_task_id: Optional parent task ID for all created tasks
        created_in_session_id: Optional session ID where task was created

    Returns:
        Dict mapping original task references to database task UUIDs.
        Example: {"1": "550e8400-e29b-41d4-a716-446655440000", "2": "6ba7b810-9dad-11d1-80b4-00c04fd430c8"}

    Raises:
        ValueError: If no tasks provided or tasks_data is invalid
    """
    if not tasks_data:
        raise ValueError("No tasks provided for persistence")

    task_manager = LocalTaskManager(db)
    id_mapping: dict[str, str] = {}

    for index, task_data in enumerate(tasks_data):
        # Get original reference ID (could be int from LLM JSON)
        original_id = str(task_data.get("id", index + 1))

        # Get title - support both 'title' and 'description' keys
        title = task_data.get("title") or task_data.get("description")
        if not title:
            logger.warning(f"Skipping task {original_id}: no title or description")
            continue

        # Extract other fields
        verification = task_data.get("verification")
        priority = task_data.get("priority", 2)
        labels = task_data.get("labels", [])
        description = task_data.get("description")

        # Don't use description as both title and description
        if description == title:
            description = None

        try:
            task = task_manager.create_task(
                project_id=project_id,
                title=title,
                description=description,
                priority=priority,
                labels=labels,
                parent_task_id=parent_task_id,
                created_in_session_id=created_in_session_id,
                workflow_name=workflow_name,
                verification=verification,
                sequence_order=index,
            )
            id_mapping[original_id] = task.id
            logger.debug(f"Created task {task.id} from decomposition ref {original_id}")
        except Exception as e:
            logger.error(f"Failed to create task for ref {original_id}: {e}")
            continue

    logger.info(
        f"Persisted {len(id_mapping)} tasks for workflow '{workflow_name}' in project {project_id}"
    )
    return id_mapping


def update_task_from_workflow(
    db: DatabaseProtocol,
    task_id: str,
    status: str | None = None,
    verification: str | None = None,
    validation_status: str | None = None,
    validation_feedback: str | None = None,
) -> Task | None:
    """Update a task based on workflow state changes.

    Called when workflow transitions or verifications occur to update the
    corresponding task record.

    Args:
        db: LocalDatabase instance
        task_id: ID of the task to update
        status: New status ('open', 'in_progress', 'closed')
        verification: Updated verification instructions/result
        validation_status: Validation status ('pending', 'valid', 'invalid')
        validation_feedback: Feedback from validation

    Returns:
        Updated Task object, or None if task not found
    """
    task_manager = LocalTaskManager(db)

    try:
        # Build update kwargs only for provided values
        update_kwargs: dict[str, Any] = {}
        if status is not None:
            update_kwargs["status"] = status
        if verification is not None:
            update_kwargs["verification"] = verification
        if validation_status is not None:
            update_kwargs["validation_status"] = validation_status
        if validation_feedback is not None:
            update_kwargs["validation_feedback"] = validation_feedback

        if not update_kwargs:
            # No updates to apply, just return current task
            return task_manager.get_task(task_id)

        task = task_manager.update_task(task_id, **update_kwargs)
        logger.debug(f"Updated task {task_id} from workflow: {list(update_kwargs.keys())}")
        return task

    except ValueError as e:
        logger.warning(f"Task {task_id} not found for workflow update: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to update task {task_id} from workflow: {e}")
        return None


def get_workflow_tasks(
    db: DatabaseProtocol,
    workflow_name: str,
    project_id: str | None = None,
    include_closed: bool = False,
) -> list[Task]:
    """Retrieve all tasks associated with a workflow state.

    Returns tasks ordered by sequence_order for workflows that use ordered task
    execution (like plan-to-tasks).

    Args:
        db: LocalDatabase instance
        workflow_name: Name of the workflow to get tasks for
        project_id: Optional project ID filter
        include_closed: If True, include closed tasks; otherwise only open/in_progress

    Returns:
        List of Task objects ordered by sequence_order, then created_at
    """
    task_manager = LocalTaskManager(db)

    # Determine status filter
    status = None if include_closed else None  # We'll handle in the method

    tasks = task_manager.list_workflow_tasks(
        workflow_name=workflow_name,
        project_id=project_id,
        status=status,
    )

    # Filter out closed if not including them
    if not include_closed:
        tasks = [t for t in tasks if t.status != "closed"]

    logger.debug(f"Retrieved {len(tasks)} tasks for workflow '{workflow_name}'")
    return tasks


def get_next_workflow_task(
    db: DatabaseProtocol,
    workflow_name: str,
    project_id: str | None = None,
) -> Task | None:
    """Get the next task to work on for a workflow.

    Returns the first open task by sequence_order that hasn't been started.
    Useful for workflows that execute tasks sequentially.

    Args:
        db: LocalDatabase instance
        workflow_name: Name of the workflow
        project_id: Optional project ID filter

    Returns:
        Next Task to work on, or None if all tasks are complete
    """
    task_manager = LocalTaskManager(db)

    tasks = task_manager.list_workflow_tasks(
        workflow_name=workflow_name,
        project_id=project_id,
        status="open",
        limit=1,
    )

    if tasks:
        return tasks[0]
    return None


def mark_workflow_task_complete(
    db: DatabaseProtocol,
    task_id: str,
    verification_result: str | None = None,
) -> Task | None:
    """Mark a workflow task as complete with optional verification result.

    Args:
        db: LocalDatabase instance
        task_id: ID of the task to complete
        verification_result: Optional result/notes from verification

    Returns:
        Updated Task object, or None if task not found
    """
    return update_task_from_workflow(
        db=db,
        task_id=task_id,
        status="closed",
        verification=verification_result,
        validation_status="valid",
    )
