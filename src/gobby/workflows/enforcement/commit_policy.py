"""Commit policy enforcement for workflow engine.

Provides actions that enforce commit requirements before stopping or closing tasks.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from gobby.workflows.git_utils import get_dirty_files

if TYPE_CHECKING:
    from gobby.storage.tasks import LocalTaskManager
    from gobby.workflows.definitions import WorkflowState

logger = logging.getLogger(__name__)


async def capture_baseline_dirty_files(
    workflow_state: WorkflowState | None,
    project_path: str | None = None,
) -> dict[str, Any] | None:
    """
    Capture current dirty files as baseline for session-aware detection.

    Called on session_start to record pre-existing dirty files. The
    require_commit_before_stop action will compare against this baseline
    to detect only NEW dirty files made during the session.

    Args:
        workflow_state: Workflow state to store baseline in
        project_path: Path to the project directory for git status check

    Returns:
        Dict with captured baseline info, or None if no workflow_state
    """
    if not workflow_state:
        logger.debug("capture_baseline_dirty_files: No workflow_state, skipping")
        return None

    dirty_files = get_dirty_files(project_path)

    # Store as a list in workflow state (sets aren't JSON serializable)
    workflow_state.variables["baseline_dirty_files"] = list(dirty_files)

    # Log for debugging baseline capture issues
    files_preview = list(dirty_files)[:5]
    logger.info(
        f"capture_baseline_dirty_files: project_path={project_path}, "
        f"captured {len(dirty_files)} files: {files_preview}"
    )

    return {
        "baseline_captured": True,
        "file_count": len(dirty_files),
        "files": list(dirty_files),
    }


async def require_commit_before_stop(
    workflow_state: WorkflowState | None,
    project_path: str | None = None,
    task_manager: LocalTaskManager | None = None,
) -> dict[str, Any] | None:
    """
    Block stop if there's an in_progress task with uncommitted changes.

    This action is designed for on_stop triggers to enforce that agents
    commit their work and close tasks before stopping.

    Args:
        workflow_state: Workflow state with variables (claimed_task_id, etc.)
        project_path: Path to the project directory for git status check
        task_manager: LocalTaskManager to verify task status

    Returns:
        Dict with decision="block" and reason if task has uncommitted changes,
        or None to allow the stop.
    """
    if not workflow_state:
        logger.debug("require_commit_before_stop: No workflow_state, allowing")
        return None

    claimed_task_id = workflow_state.variables.get("claimed_task_id")
    if not claimed_task_id:
        logger.debug("require_commit_before_stop: No claimed task, allowing")
        return None

    # Verify the task is actually still in_progress (not just cached in workflow state)
    if task_manager:
        task = task_manager.get_task(claimed_task_id)
        if not task or task.status != "in_progress":
            # Task was changed - clear the stale workflow state
            logger.debug(
                f"require_commit_before_stop: Task '{claimed_task_id}' is no longer "
                f"in_progress (status={task.status if task else 'not found'}), clearing state"
            )
            workflow_state.variables["claimed_task_id"] = None
            workflow_state.variables["task_claimed"] = False
            return None

    # Check for uncommitted changes using baseline-aware comparison
    current_dirty = get_dirty_files(project_path)

    if not current_dirty:
        logger.debug("require_commit_before_stop: No uncommitted changes, allowing")
        return None

    # Get baseline dirty files captured at session start
    baseline_dirty = set(workflow_state.variables.get("baseline_dirty_files", []))

    # Calculate NEW dirty files (not in baseline)
    new_dirty = current_dirty - baseline_dirty

    if not new_dirty:
        logger.debug(
            f"require_commit_before_stop: All {len(current_dirty)} dirty files were pre-existing "
            f"(in baseline), allowing"
        )
        return None

    logger.debug(
        f"require_commit_before_stop: Found {len(new_dirty)} new dirty files "
        f"(baseline had {len(baseline_dirty)}, current has {len(current_dirty)})"
    )

    # Track how many times we've blocked to prevent infinite loops
    block_count = workflow_state.variables.get("_commit_block_count", 0)
    if block_count >= 3:
        logger.warning(
            f"require_commit_before_stop: Reached max block count ({block_count}), allowing"
        )
        return None

    workflow_state.variables["_commit_block_count"] = block_count + 1

    # Block - agent needs to commit and close
    logger.info(
        f"require_commit_before_stop: Blocking stop - task '{claimed_task_id}' "
        f"has {len(new_dirty)} uncommitted changes"
    )

    # Build list of new dirty files for the message (limit to 10 for readability)
    new_dirty_list = sorted(new_dirty)[:10]
    files_display = "\n".join(f"  - {f}" for f in new_dirty_list)
    if len(new_dirty) > 10:
        files_display += f"\n  ... and {len(new_dirty) - 10} more files"

    return {
        "decision": "block",
        "reason": (
            f"Task '{claimed_task_id}' is in_progress with {len(new_dirty)} uncommitted "
            f"changes made during this session:\n{files_display}\n\n"
            f"Before stopping, commit your changes and close the task:\n"
            f"1. Commit with [{claimed_task_id}] in the message\n"
            f'2. Close the task: close_task(task_id="{claimed_task_id}", commit_sha="...")'
        ),
    }


async def require_task_review_or_close_before_stop(
    workflow_state: WorkflowState | None,
    task_manager: LocalTaskManager | None = None,
    project_id: str | None = None,
    **kwargs: Any,
) -> dict[str, Any] | None:
    """Block stop if session has an in_progress task.

    Agents must close their task (or send to review) before stopping.
    The close_task() validation already requires a commit, so we don't
    need to check for uncommitted changes here - that's handled by
    require_commit_before_stop if needed.

    Checks both:
    1. claimed_task_id - task explicitly claimed via update_task(status="in_progress")
    2. session_task - task(s) assigned via set_variable (fallback if no claimed_task_id)

    Args:
        workflow_state: Workflow state with variables (claimed_task_id, etc.)
        task_manager: LocalTaskManager to verify task status
        project_id: Project ID for resolving task references (#N, N formats)
        **kwargs: Accepts additional kwargs for compatibility

    Returns:
        Dict with decision="block" and reason if task is still in_progress,
        or None to allow the stop.
    """
    if not workflow_state:
        logger.debug("require_task_review_or_close_before_stop: No workflow_state, allowing")
        return None

    # 1. Check claimed_task_id first (existing behavior)
    claimed_task_id = workflow_state.variables.get("claimed_task_id")

    # 2. If no claimed task, fall back to session_task
    if not claimed_task_id and task_manager:
        session_task = workflow_state.variables.get("session_task")
        if session_task and session_task != "*":
            # Normalize to list
            task_ids = [session_task] if isinstance(session_task, str) else session_task

            if isinstance(task_ids, list):
                for task_id in task_ids:
                    try:
                        task = task_manager.get_task(task_id, project_id=project_id)
                    except ValueError:
                        continue
                    if task and task.status == "in_progress":
                        claimed_task_id = task_id
                        logger.debug(
                            f"require_task_review_or_close_before_stop: Found in_progress "
                            f"session_task '{task_id}'"
                        )
                        break
                    # Also check subtasks
                    if task:
                        subtasks = task_manager.list_tasks(parent_task_id=task.id)
                        for subtask in subtasks:
                            if subtask.status == "in_progress":
                                claimed_task_id = subtask.id
                                logger.debug(
                                    f"require_task_review_or_close_before_stop: Found in_progress "
                                    f"subtask '{subtask.id}' under session_task '{task_id}'"
                                )
                                break
                    if claimed_task_id:
                        break

    if not claimed_task_id:
        logger.debug("require_task_review_or_close_before_stop: No claimed task, allowing")
        return None

    if not task_manager:
        logger.debug("require_task_review_or_close_before_stop: No task_manager, allowing")
        return None

    try:
        task = task_manager.get_task(claimed_task_id, project_id=project_id)
        if not task:
            # Task not found - clear stale workflow state and allow
            logger.debug(
                f"require_task_review_or_close_before_stop: Task '{claimed_task_id}' not found, "
                f"clearing state"
            )
            workflow_state.variables["claimed_task_id"] = None
            workflow_state.variables["task_claimed"] = False
            return None

        if task.status != "in_progress":
            # Task is closed or in review - allow stop
            logger.debug(
                f"require_task_review_or_close_before_stop: Task '{claimed_task_id}' "
                f"status={task.status}, allowing"
            )
            # Clear stale workflow state
            workflow_state.variables["claimed_task_id"] = None
            workflow_state.variables["task_claimed"] = False
            return None

        # Task is still in_progress - block the stop
        task_ref = f"#{task.seq_num}" if task.seq_num else task.id[:8]
        logger.info(
            f"require_task_review_or_close_before_stop: Blocking stop - task "
            f"{task_ref} is still in_progress"
        )

        return {
            "decision": "block",
            "reason": (
                f"\nTask {task_ref} is still in_progress. "
                f"Close it with close_task() before stopping."
            ),
            "task_id": claimed_task_id,
            "task_status": task.status,
        }

    except Exception as e:
        logger.warning(
            f"require_task_review_or_close_before_stop: Failed to check task status: {e}"
        )
        # Allow stop if we can't check - don't block on errors
        return None
