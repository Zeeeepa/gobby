"""Task orchestration tools: wait (wait_for_task, wait_for_any_task, wait_for_all_tasks).

Provides blocking wait operations for task completion with timeout support.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.storage.tasks import TaskNotFoundError

if TYPE_CHECKING:
    from gobby.storage.tasks import LocalTaskManager

logger = logging.getLogger(__name__)

# Default timeout and poll interval
DEFAULT_TIMEOUT = 300.0  # 5 minutes
DEFAULT_POLL_INTERVAL = 5.0  # 5 seconds


def register_wait(
    registry: InternalToolRegistry,
    task_manager: LocalTaskManager,
) -> None:
    """
    Register wait tools for task completion.

    Args:
        registry: The tool registry to add tools to
        task_manager: Task manager for checking task status
    """

    def _resolve_task_id(task_ref: str) -> str:
        """Resolve a task reference to its UUID."""
        from gobby.mcp_proxy.tools.tasks import resolve_task_id_for_mcp

        return resolve_task_id_for_mcp(task_manager, task_ref)

    def _is_task_complete(task_id: str) -> tuple[bool, dict[str, Any] | None]:
        """
        Check if a task is complete.

        Returns:
            Tuple of (is_complete, task_info_dict or None)
        """
        task = task_manager.get_task(task_id)
        if task is None:
            return False, None

        task_info = {
            "id": task.id,
            "seq_num": task.seq_num,
            "title": task.title,
            "status": task.status,
            "closed_at": task.closed_at,
        }

        # Consider task complete if status is "closed" or "review"
        # (review tasks have completed their work, just awaiting human approval)
        is_complete = task.status in ("closed", "review")
        return is_complete, task_info

    async def wait_for_task(
        task_id: str,
        timeout: float = DEFAULT_TIMEOUT,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
    ) -> dict[str, Any]:
        """
        Wait for a single task to complete.

        Blocks until the task reaches "closed" or "review" status, or timeout expires.

        Args:
            task_id: Task reference (#N, N, path, or UUID)
            timeout: Maximum wait time in seconds (default: 300)
            poll_interval: Time between status checks in seconds (default: 5)

        Returns:
            Dict with:
            - success: Whether the operation succeeded
            - completed: Whether the task completed
            - timed_out: Whether timeout was reached
            - task: Task info dict (if found)
            - wait_time: How long we waited
        """
        # Validate poll_interval
        if poll_interval <= 0:
            poll_interval = DEFAULT_POLL_INTERVAL

        start_time = time.monotonic()

        try:
            resolved_id = _resolve_task_id(task_id)
        except (TaskNotFoundError, ValueError) as e:
            return {
                "success": False,
                "error": f"Task not found: {task_id} ({e})",
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to resolve task: {task_id} ({e})",
            }

        # Check initial state
        try:
            is_complete, task_info = _is_task_complete(resolved_id)
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to check task status: {e}",
            }

        if task_info is None:
            return {
                "success": False,
                "error": f"Task not found: {task_id}",
            }

        if is_complete:
            return {
                "success": True,
                "completed": True,
                "timed_out": False,
                "task": task_info,
                "wait_time": 0.0,
            }

        # Poll until complete or timeout
        while True:
            elapsed = time.monotonic() - start_time

            if elapsed >= timeout:
                # Re-fetch latest task state before returning timeout
                try:
                    _, task_info = _is_task_complete(resolved_id)
                except Exception as e:
                    logger.warning(f"Error fetching final task status on timeout: {e}")
                return {
                    "success": True,
                    "completed": False,
                    "timed_out": True,
                    "task": task_info,
                    "wait_time": elapsed,
                }

            await asyncio.sleep(poll_interval)

            try:
                is_complete, task_info = _is_task_complete(resolved_id)
            except Exception as e:
                logger.warning(f"Error checking task status: {e}")
                continue

            if is_complete:
                return {
                    "success": True,
                    "completed": True,
                    "timed_out": False,
                    "task": task_info,
                    "wait_time": time.monotonic() - start_time,
                }

    registry.register(
        name="wait_for_task",
        description=(
            "Wait for a single task to complete. "
            "Blocks until task reaches 'closed' or 'review' status, or timeout expires."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task reference: #N, N (seq_num), path (1.2.3), or UUID",
                },
                "timeout": {
                    "type": "number",
                    "description": f"Maximum wait time in seconds (default: {DEFAULT_TIMEOUT})",
                },
                "poll_interval": {
                    "type": "number",
                    "description": f"Time between status checks in seconds (default: {DEFAULT_POLL_INTERVAL})",
                },
            },
            "required": ["task_id"],
        },
        func=wait_for_task,
    )

    async def wait_for_any_task(
        task_ids: list[str],
        timeout: float = DEFAULT_TIMEOUT,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
    ) -> dict[str, Any]:
        """
        Wait for any one of multiple tasks to complete.

        Blocks until at least one task reaches "closed" or "review" status, or timeout expires.

        Args:
            task_ids: List of task references (#N, N, path, or UUID)
            timeout: Maximum wait time in seconds (default: 300)
            poll_interval: Time between status checks in seconds (default: 5)

        Returns:
            Dict with:
            - success: Whether the operation succeeded
            - completed_task_id: ID of the first completed task (or None)
            - timed_out: Whether timeout was reached
            - wait_time: How long we waited
        """
        if not task_ids:
            return {
                "success": False,
                "error": "No task IDs provided - task_ids list is empty",
            }

        # Validate poll_interval
        if poll_interval <= 0:
            poll_interval = DEFAULT_POLL_INTERVAL

        start_time = time.monotonic()

        # Resolve all task IDs upfront
        resolved_ids = []
        for task_ref in task_ids:
            try:
                resolved_id = _resolve_task_id(task_ref)
                resolved_ids.append(resolved_id)
            except (TaskNotFoundError, ValueError) as e:
                logger.warning(f"Could not resolve task {task_ref}: {e}")
                # Continue with other tasks

        if not resolved_ids:
            return {
                "success": False,
                "error": "None of the provided task IDs could be resolved",
            }

        # Check if any are already complete
        for resolved_id in resolved_ids:
            try:
                is_complete, task_info = _is_task_complete(resolved_id)
                if is_complete:
                    return {
                        "success": True,
                        "completed_task_id": resolved_id,
                        "task": task_info,
                        "timed_out": False,
                        "wait_time": 0.0,
                    }
            except Exception as e:
                logger.warning(f"Error checking task {resolved_id}: {e}")

        # Poll until one completes or timeout
        while True:
            elapsed = time.monotonic() - start_time

            if elapsed >= timeout:
                return {
                    "success": True,
                    "completed_task_id": None,
                    "timed_out": True,
                    "wait_time": elapsed,
                }

            await asyncio.sleep(poll_interval)

            for resolved_id in resolved_ids:
                try:
                    is_complete, task_info = _is_task_complete(resolved_id)
                    if is_complete:
                        return {
                            "success": True,
                            "completed_task_id": resolved_id,
                            "task": task_info,
                            "timed_out": False,
                            "wait_time": time.monotonic() - start_time,
                        }
                except Exception as e:
                    logger.warning(f"Error checking task {resolved_id}: {e}")

    registry.register(
        name="wait_for_any_task",
        description=(
            "Wait for any one of multiple tasks to complete. "
            "Returns as soon as the first task reaches 'closed' or 'review' status."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "task_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of task references",
                },
                "timeout": {
                    "type": "number",
                    "description": f"Maximum wait time in seconds (default: {DEFAULT_TIMEOUT})",
                },
                "poll_interval": {
                    "type": "number",
                    "description": f"Time between status checks in seconds (default: {DEFAULT_POLL_INTERVAL})",
                },
            },
            "required": ["task_ids"],
        },
        func=wait_for_any_task,
    )

    async def wait_for_all_tasks(
        task_ids: list[str],
        timeout: float = DEFAULT_TIMEOUT,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
    ) -> dict[str, Any]:
        """
        Wait for all tasks to complete.

        Blocks until all tasks reach "closed" or "review" status, or timeout expires.

        Args:
            task_ids: List of task references (#N, N, path, or UUID)
            timeout: Maximum wait time in seconds (default: 300)
            poll_interval: Time between status checks in seconds (default: 5)

        Returns:
            Dict with:
            - success: Whether the operation succeeded
            - all_completed: Whether all tasks completed
            - completed_count: Number of completed tasks
            - pending_count: Number of still-pending tasks
            - timed_out: Whether timeout was reached
            - completed_tasks: List of completed task IDs
            - pending_tasks: List of pending task IDs
            - wait_time: How long we waited
        """
        if not task_ids:
            # Empty list is vacuously true - all (zero) tasks are complete
            return {
                "success": True,
                "all_completed": True,
                "completed_count": 0,
                "pending_count": 0,
                "timed_out": False,
                "completed_tasks": [],
                "pending_tasks": [],
                "wait_time": 0.0,
            }

        # Validate poll_interval
        if poll_interval <= 0:
            poll_interval = DEFAULT_POLL_INTERVAL

        start_time = time.monotonic()

        # Resolve all task IDs upfront
        resolved_ids = []
        for task_ref in task_ids:
            try:
                resolved_id = _resolve_task_id(task_ref)
                resolved_ids.append(resolved_id)
            except (TaskNotFoundError, ValueError) as e:
                logger.warning(f"Could not resolve task {task_ref}: {e}")

        if not resolved_ids:
            return {
                "success": False,
                "error": "None of the provided task IDs could be resolved",
            }

        def check_all_complete() -> tuple[list[str], list[str]]:
            """Check which tasks are complete. Returns (completed, pending)."""
            completed = []
            pending = []
            for resolved_id in resolved_ids:
                try:
                    is_complete, _ = _is_task_complete(resolved_id)
                    if is_complete:
                        completed.append(resolved_id)
                    else:
                        pending.append(resolved_id)
                except Exception as e:
                    logger.warning(f"Error checking task {resolved_id}: {e}")
                    pending.append(resolved_id)  # Assume not complete on error
            return completed, pending

        # Check initial state
        completed, pending = check_all_complete()

        if not pending:
            return {
                "success": True,
                "all_completed": True,
                "completed_count": len(completed),
                "pending_count": 0,
                "timed_out": False,
                "completed_tasks": completed,
                "pending_tasks": [],
                "wait_time": 0.0,
            }

        # Poll until all complete or timeout
        while True:
            elapsed = time.monotonic() - start_time

            if elapsed >= timeout:
                completed, pending = check_all_complete()
                return {
                    "success": True,
                    "all_completed": False,
                    "completed_count": len(completed),
                    "pending_count": len(pending),
                    "timed_out": True,
                    "completed_tasks": completed,
                    "pending_tasks": pending,
                    "wait_time": elapsed,
                }

            await asyncio.sleep(poll_interval)

            completed, pending = check_all_complete()

            if not pending:
                return {
                    "success": True,
                    "all_completed": True,
                    "completed_count": len(completed),
                    "pending_count": 0,
                    "timed_out": False,
                    "completed_tasks": completed,
                    "pending_tasks": [],
                    "wait_time": time.monotonic() - start_time,
                }

    registry.register(
        name="wait_for_all_tasks",
        description=(
            "Wait for all tasks to complete. "
            "Blocks until all tasks reach 'closed' or 'review' status, or timeout expires."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "task_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of task references",
                },
                "timeout": {
                    "type": "number",
                    "description": f"Maximum wait time in seconds (default: {DEFAULT_TIMEOUT})",
                },
                "poll_interval": {
                    "type": "number",
                    "description": f"Time between status checks in seconds (default: {DEFAULT_POLL_INTERVAL})",
                },
            },
            "required": ["task_ids"],
        },
        func=wait_for_all_tasks,
    )
