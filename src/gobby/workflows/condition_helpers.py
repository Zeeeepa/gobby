"""Condition helper functions for rule engine expressions.

These functions are registered as allowed_funcs in SafeExpressionEvaluator
so they can be called from rule ``when`` conditions, e.g.:

    when: "task_tree_complete(variables.session_task)"
    when: "task_needs_user_review(variables.session_task)"
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def is_task_complete(task: Any) -> bool:
    """Check if a task counts as complete for workflow purposes.

    A task is complete if:
    - status is 'closed', OR
    - status is 'needs_review' AND requires_user_review is False
    """
    if task.status == "closed":
        return True
    requires_user_review = getattr(task, "requires_user_review", False)
    if task.status == "needs_review" and not requires_user_review:
        return True
    return False


def task_needs_user_review(task_manager: Any, task_id: str | None) -> bool:
    """Check if a task is awaiting user review (in review + HITL flag).

    Used in rule conditions like:
        when: "task_needs_user_review(variables.session_task)"
    """
    if not task_id or not task_manager:
        return False

    task = task_manager.get_task(task_id)
    if not task:
        return False

    return bool(task.status == "needs_review" and getattr(task, "requires_user_review", False))


def task_tree_complete(task_manager: Any, task_id: str | list[str] | None) -> bool:
    """Check if a task tree is complete (all work is done).

    A task tree is complete when either:
    - The task is explicitly closed/needs_review, OR
    - The task has subtasks and ALL subtasks are recursively complete

    Used in rule conditions like:
        when: "task_tree_complete(variables.session_task)"
    """
    if not task_id:
        return True

    if not task_manager:
        logger.warning("task_tree_complete: No task_manager available")
        return False

    task_ids = [task_id] if isinstance(task_id, str) else task_id

    for tid in task_ids:
        if not _is_tree_complete(task_manager, tid):
            return False

    return True


def _is_tree_complete(task_manager: Any, task_id: str) -> bool:
    """Check if a single task and its subtree are complete."""
    task = task_manager.get_task(task_id)
    if not task:
        logger.warning(f"task_tree_complete: Task '{task_id}' not found")
        return False

    task_closed = is_task_complete(task)
    subtasks = task_manager.list_tasks(parent_task_id=task_id)

    if not subtasks:
        if not task_closed:
            logger.debug(
                f"task_tree_complete: Leaf task '{task_id}' is not complete (status={task.status})"
            )
        return task_closed

    for subtask in subtasks:
        if not _is_tree_complete(task_manager, subtask.id):
            return False

    if not task_closed:
        logger.debug(
            f"task_tree_complete: Task '{task_id}' not explicitly closed but all "
            f"{len(subtasks)} subtask(s) complete — tree is complete"
        )

    return True
