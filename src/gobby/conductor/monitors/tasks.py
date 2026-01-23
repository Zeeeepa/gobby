"""Task monitor for detecting stale and blocked tasks.

Provides monitoring for:
- Stale tasks: Tasks in_progress longer than a threshold
- Blocked chains: Tasks blocked by open dependencies
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gobby.storage.tasks import LocalTaskManager

logger = logging.getLogger(__name__)


@dataclass
class TaskMonitor:
    """Monitor for task health and status.

    Detects:
    - Stale tasks: in_progress longer than threshold
    - Blocked chains: tasks waiting on open dependencies
    """

    task_manager: LocalTaskManager

    def check(
        self,
        project_id: str | None = None,
        stale_threshold_hours: int = 24,
    ) -> dict[str, Any]:
        """
        Check for task health issues.

        Args:
            project_id: Optional project filter
            stale_threshold_hours: Hours before an in_progress task is considered stale

        Returns:
            Dict with stale_tasks, blocked_chains, and summary
        """
        stale_tasks = self._find_stale_tasks(
            project_id=project_id,
            threshold_hours=stale_threshold_hours,
        )
        blocked_chains = self._find_blocked_chains(project_id=project_id)

        return {
            "stale_tasks": stale_tasks,
            "blocked_chains": blocked_chains,
            "summary": {
                "stale_count": len(stale_tasks),
                "blocked_count": len(blocked_chains),
                "checked_at": datetime.now(UTC).isoformat(),
            },
        }

    def _find_stale_tasks(
        self,
        project_id: str | None = None,
        threshold_hours: int = 24,
    ) -> list[dict[str, Any]]:
        """
        Find tasks that have been in_progress longer than threshold.

        Args:
            project_id: Optional project filter
            threshold_hours: Hours before task is considered stale

        Returns:
            List of stale task info dicts
        """
        # Get all in_progress tasks
        in_progress_tasks = self.task_manager.list_tasks(
            project_id=project_id,
            status="in_progress",
            limit=1000,
        )

        threshold = datetime.now(UTC) - timedelta(hours=threshold_hours)
        stale_tasks = []

        for task in in_progress_tasks:
            # Parse updated_at timestamp
            try:
                if task.updated_at:
                    # Handle both string and datetime types
                    if isinstance(task.updated_at, str):
                        # Parse ISO format, handle both Z and +00:00 formats
                        updated_str = task.updated_at.replace("Z", "+00:00")
                        updated_at = datetime.fromisoformat(updated_str)
                    else:
                        updated_at = task.updated_at

                    # Timezone policy: All timestamps are expected to be stored in UTC.
                    # If updated_at is naive (no tzinfo), log a warning and skip
                    # rather than assuming UTC which could cause incorrect staleness detection.
                    if updated_at.tzinfo is None:
                        logger.warning(
                            f"Task {task.id} has naive updated_at timestamp "
                            f"({updated_at}); skipping staleness check. "
                            "Ensure the task storage stores UTC timestamps."
                        )
                        continue

                    if updated_at < threshold:
                        hours_stale = (datetime.now(UTC) - updated_at).total_seconds() / 3600
                        stale_tasks.append(
                            {
                                "task_id": task.id,
                                "title": task.title,
                                "updated_at": task.updated_at,
                                "hours_stale": round(hours_stale, 1),
                            }
                        )
            except (ValueError, TypeError) as e:
                logger.warning(f"Could not parse updated_at for task {task.id}: {e}")
                continue

        return stale_tasks

    def _find_blocked_chains(
        self,
        project_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Find blocked task chains.

        Args:
            project_id: Optional project filter

        Returns:
            List of blocked chain info dicts
        """
        blocked_tasks = self.task_manager.list_blocked_tasks(
            project_id=project_id,
            limit=1000,
        )

        blocked_chains = []
        for task in blocked_tasks:
            blocked_chains.append(
                {
                    "task_id": task.id,
                    "title": task.title,
                    "status": task.status,
                }
            )

        return blocked_chains
