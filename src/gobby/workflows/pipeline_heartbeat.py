"""Pipeline heartbeat — safety net for event-driven pipeline execution.

Registered as a cron handler. On each tick:
1. Detects stalled RUNNING executions (no updated_at change)
2. Checks if associated agents are alive
3. Marks truly dead executions as FAILED
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from gobby.workflows.pipeline_state import ExecutionStatus, PipelineExecution

if TYPE_CHECKING:
    from gobby.agents.registry import RunningAgentRegistry
    from gobby.storage.agents import LocalAgentRunManager
    from gobby.storage.cron_models import CronJob
    from gobby.storage.pipelines import LocalPipelineExecutionManager
    from gobby.storage.tasks._manager import LocalTaskManager

logger = logging.getLogger(__name__)


class PipelineHeartbeat:
    """Safety net for event-driven pipeline execution.

    Callable cron handler that detects stalled pipelines and marks
    dead executions as failed.
    """

    def __init__(
        self,
        execution_manager: LocalPipelineExecutionManager,
        agent_registry: RunningAgentRegistry,
        stall_threshold_seconds: float = 120.0,
        task_manager: LocalTaskManager | None = None,
        agent_run_manager: LocalAgentRunManager | None = None,
    ) -> None:
        self._execution_manager = execution_manager
        self._agent_registry = agent_registry
        self._stall_threshold_seconds = stall_threshold_seconds
        self._task_manager = task_manager
        self._agent_run_manager = agent_run_manager

    async def __call__(self, job: CronJob) -> str:
        """Cron handler entry point."""
        stalled = await self.check_stalled_executions()
        recovered = await self.check_stale_tasks()
        parts = [f"{stalled} stalled handled"]
        if recovered:
            parts.append(f"{recovered} stale tasks recovered")
        return f"Heartbeat: {', '.join(parts)}"

    async def check_stalled_executions(self) -> int:
        """Find stalled RUNNING executions and take corrective action.

        For each stalled execution:
        - If agents still alive → touch updated_at (slow, not stalled)
        - If agents dead → mark FAILED

        Returns:
            Number of stalled executions handled
        """
        stalled = self._execution_manager.get_stalled_executions(int(self._stall_threshold_seconds))
        if not stalled:
            return 0

        handled = 0
        for execution in stalled:
            try:
                handled += await self._handle_stalled_execution(execution)
            except Exception:
                logger.error("Heartbeat error handling execution %s", execution.id, exc_info=True)
        return handled

    async def _handle_stalled_execution(self, execution: PipelineExecution) -> int:
        """Handle a single stalled execution.

        Returns 1 if action was taken, 0 otherwise.
        """
        # Check if any agents are alive for this execution's session
        has_alive_agents = self._has_alive_agents(execution)

        if has_alive_agents:
            # Agents still working — touch updated_at so we don't re-flag
            self._execution_manager.update_execution_status(execution.id, ExecutionStatus.RUNNING)
            logger.debug(
                "Heartbeat: execution %s has alive agents, touched updated_at",
                execution.id,
            )
            return 1

        # No alive agents — truly dead
        self._execution_manager.update_execution_status(
            execution.id,
            ExecutionStatus.FAILED,
            outputs_json=json.dumps({"error": "Heartbeat: execution stalled with no alive agents"}),
        )
        logger.warning(
            "Heartbeat: marked execution %s as FAILED (stalled, no agents)",
            execution.id,
        )
        return 1

    def _has_alive_agents(self, execution: PipelineExecution) -> bool:
        """Check if any agents are alive for a pipeline execution.

        Checks RunningAgentRegistry for agents whose parent session
        matches the execution's session_id.
        """
        if not execution.session_id:
            return False
        try:
            agents = self._agent_registry.list_by_parent(execution.session_id)
            return len(agents) > 0
        except Exception:
            logger.exception("Failed to check alive agents for execution %s", execution.id)
            return False

    async def check_stale_tasks(self) -> int:
        """Find in_progress tasks with no alive agent and reset to open.

        For each in_progress task that has an assignee:
        1. Check if there's an active agent run (pending/running) for the task
        2. If not, reset the task to open with no assignee

        Returns:
            Number of recovered tasks.
        """
        import asyncio

        if not self._task_manager or not self._agent_run_manager:
            return 0

        try:
            in_progress = await asyncio.to_thread(
                self._task_manager.list_tasks, status="in_progress", limit=100
            )
        except Exception:
            logger.exception("Heartbeat: failed to query in_progress tasks")
            return 0

        recovered = 0
        for task in in_progress:
            if not task.assignee:
                continue
            try:
                has_active = await asyncio.to_thread(
                    self._agent_run_manager.has_active_run_for_task, task.id
                )
                if has_active:
                    continue

                # No active agent run — task is orphaned.
                # If the task has linked commits, the agent did real work
                # but didn't call mark_task_needs_review — promote to
                # needs_review instead of wiping the claim entirely.
                has_commits = bool(getattr(task, "commits", None))
                if has_commits:
                    await asyncio.to_thread(
                        self._task_manager.update_task,
                        task.id,
                        status="needs_review",
                        assignee=None,
                    )
                    logger.info(
                        "Heartbeat: promoted stale task %s (#%s) to needs_review "
                        "(has commits, no active agent run)",
                        task.id,
                        task.seq_num,
                    )
                else:
                    await asyncio.to_thread(
                        self._task_manager.update_task,
                        task.id,
                        status="open",
                        assignee=None,
                    )
                    logger.warning(
                        "Heartbeat: recovered stale task %s (#%s) — "
                        "reset to open (no active agent run, no commits)",
                        task.id,
                        task.seq_num,
                    )
                recovered += 1
            except Exception:
                logger.exception("Heartbeat: error checking task %s for staleness", task.id)
        return recovered
