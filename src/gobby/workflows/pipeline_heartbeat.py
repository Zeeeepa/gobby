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
    from gobby.storage.cron_models import CronJob
    from gobby.storage.pipelines import LocalPipelineExecutionManager

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
    ) -> None:
        self._execution_manager = execution_manager
        self._agent_registry = agent_registry
        self._stall_threshold_seconds = stall_threshold_seconds

    async def __call__(self, job: CronJob) -> str:
        """Cron handler entry point."""
        stalled = await self.check_stalled_executions()
        return f"Heartbeat: {stalled} stalled handled"

    async def check_stalled_executions(self) -> int:
        """Find stalled RUNNING executions and take corrective action.

        For each stalled execution:
        - If agents still alive → touch updated_at (slow, not stalled)
        - If agents dead → mark FAILED

        Returns:
            Number of stalled executions handled
        """
        stalled = self._execution_manager.get_stalled_executions(
            int(self._stall_threshold_seconds), all_projects=True
        )
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
