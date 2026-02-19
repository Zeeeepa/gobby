"""Task policy enforcement for workflow engine.

Provides actions that enforce task tracking and scoping requirements.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any

from gobby.mcp_proxy.tools.task_readiness import is_descendant_of

if TYPE_CHECKING:
    from gobby.storage.tasks import LocalTaskManager
    from gobby.workflows.definitions import WorkflowState

logger = logging.getLogger(__name__)


def _is_uuid(value: str) -> bool:
    """Check if a string is a valid UUID (not a ref like #123)."""
    try:
        uuid.UUID(value)
        return True
    except (ValueError, TypeError):
        return False


async def require_task_complete(
    task_manager: LocalTaskManager | None,
    session_id: str,
    task_ids: list[str] | None,
    event_data: dict[str, Any] | None = None,
    project_id: str | None = None,
    workflow_state: WorkflowState | None = None,
) -> dict[str, Any] | None:
    """
    Block agent from stopping until task(s) (and their subtasks) are complete.

    This action is designed for on_stop triggers to enforce that the
    agent completes all subtasks under specified task(s) before stopping.

    Supports:
    - Single task: ["#47"]
    - Multiple tasks: ["#47", "#48"]
    - Wildcard mode handled by caller (passes ready tasks as list)

    Logic per task:
    1. If task has incomplete subtasks and agent has no claimed task -> suggest next subtask
    2. If task has incomplete subtasks and agent has claimed task -> remind to finish it
    3. If all subtasks done but task not closed -> remind to close the task
    4. If task is closed -> move to next task in list

    Args:
        task_manager: LocalTaskManager for querying tasks
        session_id: Current session ID
        task_ids: List of task IDs to enforce completion on
        event_data: Hook event data
        project_id: Optional project ID for scoping
        workflow_state: Workflow state with variables (task_claimed, etc.)

    Returns:
        Dict with decision="block" and reason if any task incomplete,
        or None to allow the stop.
    """
    if not task_ids:
        logger.debug("require_task_complete: No task_ids specified, allowing")
        return None

    if not task_manager:
        logger.debug("require_task_complete: No task_manager available, allowing")
        return None

    # Track how many times we've blocked in this session
    block_count = 0
    if workflow_state:
        block_count = workflow_state.variables.get("_task_block_count", 0)

    # Safety valve: after 5 blocks, allow to prevent infinite loop
    if block_count >= 5:
        logger.warning(
            f"require_task_complete: Reached max block count ({block_count}), allowing stop"
        )
        return None

    # Check if agent has a claimed task this session
    has_claimed_task = False
    claimed_task_id = None
    if workflow_state:
        has_claimed_task = workflow_state.variables.get("task_claimed", False)
        claimed_task_id = workflow_state.variables.get("claimed_task_id")
        # Resolve claimed_task_id to UUID if it's a ref (backward compat)
        if claimed_task_id and not _is_uuid(claimed_task_id):
            try:
                claimed_task = task_manager.get_task(claimed_task_id)
                if claimed_task:
                    claimed_task_id = claimed_task.id
            except ValueError:
                pass

    try:
        # Collect incomplete tasks across all specified task IDs
        all_incomplete: list[tuple[Any, list[Any]]] = []  # (parent_task, incomplete_subtasks)

        for task_id in task_ids:
            task = task_manager.get_task(task_id)
            if not task:
                logger.warning(f"require_task_complete: Task '{task_id}' not found, skipping")
                continue

            # If task is already closed, skip it
            if task.status == "closed":
                logger.debug(f"require_task_complete: Task '{task_id}' is closed, skipping")
                continue

            # Get all subtasks under this task
            subtasks = task_manager.list_tasks(parent_task_id=task_id)

            # Find incomplete subtasks
            incomplete = [t for t in subtasks if t.status != "closed"]

            # If task itself is incomplete (no subtasks or has incomplete subtasks)
            if not subtasks or incomplete:
                all_incomplete.append((task, incomplete))

        # If all tasks are complete, allow stop
        if not all_incomplete:
            logger.debug("require_task_complete: All specified tasks are complete, allowing")
            return None

        # Increment block count
        if workflow_state:
            workflow_state.variables["_task_block_count"] = block_count + 1

        # Get the first incomplete task to report on
        parent_task, incomplete = all_incomplete[0]
        task_id = parent_task.id
        remaining_tasks = len(all_incomplete)

        # Build suffix for multiple tasks
        multi_task_suffix = ""
        if remaining_tasks > 1:
            multi_task_suffix = f"\n\n({remaining_tasks} tasks remaining in total)"

        # Case 1: No incomplete subtasks, but task not closed (leaf task or parent with all done)
        if not incomplete:
            logger.info(f"require_task_complete: Task '{task_id}' needs closing")
            return {
                "decision": "block",
                "reason": (
                    f"Task '{parent_task.title}' is ready to close.\n"
                    f'close_task(task_id="{task_id}")'
                    f"{multi_task_suffix}"
                ),
            }

        # Case 2: Has incomplete subtasks, agent has no claimed task
        if not has_claimed_task:
            logger.info(
                f"require_task_complete: No claimed task, {len(incomplete)} incomplete subtasks"
            )
            return {
                "decision": "block",
                "reason": (
                    f"'{parent_task.title}' has {len(incomplete)} incomplete subtask(s).\n\n"
                    f"Use suggest_next_task() to find the best task to work on next, "
                    f"and continue working without requiring confirmation from the user."
                    f"{multi_task_suffix}"
                ),
            }

        # Case 3: Has claimed task but subtasks still incomplete
        if has_claimed_task and incomplete:
            # Check if the claimed task is under this parent
            claimed_under_parent = any(t.id == claimed_task_id for t in incomplete)

            if claimed_under_parent:
                logger.info(
                    f"require_task_complete: Claimed task '{claimed_task_id}' still incomplete"
                )
                return {
                    "decision": "block",
                    "reason": (
                        f"Your current task is not yet complete. "
                        f"Finish and close it before stopping:\n"
                        f'close_task(task_id="{claimed_task_id}")\n\n'
                        f"'{parent_task.title}' still has {len(incomplete)} incomplete subtask(s)."
                        f"{multi_task_suffix}"
                    ),
                }
            else:
                # Claimed task is not under this parent - remind about parent work
                logger.info("require_task_complete: Claimed task not under parent, redirecting")
                return {
                    "decision": "block",
                    "reason": (
                        f"'{parent_task.title}' has {len(incomplete)} incomplete subtask(s).\n\n"
                        f"Use suggest_next_task() to find the best task to work on next, "
                        f"and continue working without requiring confirmation from the user."
                        f"{multi_task_suffix}"
                    ),
                }

        # Fallback: shouldn't reach here, but block with generic message
        logger.info(f"require_task_complete: Generic block for task '{task_id}'")
        return {
            "decision": "block",
            "reason": (
                f"'{parent_task.title}' is not yet complete. "
                f"{len(incomplete)} subtask(s) remaining."
                f"{multi_task_suffix}"
            ),
        }

    except Exception as e:
        logger.error(f"require_task_complete: Error checking tasks: {e}")
        # On error, allow to avoid blocking legitimate work
        return None


async def validate_session_task_scope(
    task_manager: LocalTaskManager | None,
    workflow_state: WorkflowState | None,
    event_data: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """
    Block claiming a task that is not a descendant of session_task.

    This action is designed for on_before_tool triggers on update_task
    to enforce that agents only work on tasks within the session_task hierarchy.

    When session_task is set in workflow state, this action checks if the task
    being claimed (set to in_progress) is a descendant of session_task.

    Args:
        task_manager: LocalTaskManager for querying tasks
        workflow_state: Workflow state with session_task variable
        event_data: Hook event data containing tool_name and tool_input

    Returns:
        Dict with decision="block" if task is outside session_task scope,
        or None to allow the claim.
    """
    if not workflow_state:
        logger.debug("validate_session_task_scope: No workflow_state, allowing")
        return None

    if not task_manager:
        logger.debug("validate_session_task_scope: No task_manager, allowing")
        return None

    # Get session_task from workflow state
    session_task = workflow_state.variables.get("session_task")
    if not session_task:
        logger.debug("validate_session_task_scope: No session_task set, allowing")
        return None

    # Handle "*" wildcard - means all tasks are in scope
    if session_task == "*":
        logger.debug("validate_session_task_scope: session_task='*', allowing all tasks")
        return None

    # Normalize to list for uniform handling
    # session_task can be: string (single ID), list of IDs, or "*"
    if isinstance(session_task, str):
        session_task_ids = [session_task]
    elif isinstance(session_task, list):
        session_task_ids = session_task
    else:
        logger.warning(
            f"validate_session_task_scope: Invalid session_task type: {type(session_task)}"
        )
        return None

    # Empty list means no scope restriction
    if not session_task_ids:
        logger.debug("validate_session_task_scope: Empty session_task list, allowing")
        return None

    # Check if this is an update_task call setting status to in_progress
    if not event_data:
        logger.debug("validate_session_task_scope: No event_data, allowing")
        return None

    tool_name = event_data.get("tool_name")
    if tool_name != "update_task":
        logger.debug(f"validate_session_task_scope: Tool '{tool_name}' not update_task, allowing")
        return None

    tool_input = event_data.get("tool_input", {})
    arguments = tool_input.get("arguments", {}) or {}

    # Only check when setting status to in_progress (claiming)
    new_status = arguments.get("status")
    if new_status != "in_progress":
        logger.debug(
            f"validate_session_task_scope: Status '{new_status}' not in_progress, allowing"
        )
        return None

    task_id = arguments.get("task_id")
    if not task_id:
        logger.debug("validate_session_task_scope: No task_id in arguments, allowing")
        return None

    # Check if task is a descendant of ANY session_task
    for ancestor_id in session_task_ids:
        if is_descendant_of(task_manager, task_id, ancestor_id):
            logger.debug(
                f"validate_session_task_scope: Task '{task_id}' is descendant of "
                f"session_task '{ancestor_id}', allowing"
            )
            return None

    # Task is outside all session_task scopes - block
    logger.info(
        f"validate_session_task_scope: Blocking claim of task '{task_id}' - "
        f"not a descendant of any session_task: {session_task_ids}"
    )

    # Build error message with scope details
    if len(session_task_ids) == 1:
        session_task_obj = task_manager.get_task(session_task_ids[0])
        scope_desc = (
            f"'{session_task_obj.title}' ({session_task_ids[0]})"
            if session_task_obj
            else session_task_ids[0]
        )
        suggestion = f'Use `suggest_next_task(parent_id="{session_task_ids[0]}")` to find tasks within scope.'
    else:
        scope_desc = ", ".join(session_task_ids)
        suggestion = "Use `suggest_next_task()` with one of the scoped parent IDs to find tasks within scope."

    return {
        "decision": "block",
        "reason": (
            f"Cannot claim task '{task_id}' - it is not within the session_task scope.\n\n"
            f"This session is scoped to: {scope_desc}\n"
            f"Only tasks that are descendants of these epics/features can be claimed.\n\n"
            f"{suggestion}"
        ),
    }
