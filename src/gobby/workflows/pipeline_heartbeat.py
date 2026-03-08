"""Pipeline heartbeat — safety net for event-driven pipeline execution.

Registered as a cron handler. On each tick:
1. Detects stalled RUNNING executions (no updated_at change)
2. Checks if associated agents are alive
3. Fires lost continuations or fails truly dead executions
4. Cleans up orphaned pipeline_continuations rows
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from gobby.workflows.pipeline_state import ExecutionStatus, PipelineExecution

if TYPE_CHECKING:
    from gobby.agents.registry import RunningAgentRegistry
    from gobby.events.completion_registry import CompletionEventRegistry
    from gobby.storage.agents import LocalAgentRunManager
    from gobby.storage.cron_models import CronJob
    from gobby.storage.database import DatabaseProtocol
    from gobby.storage.pipelines import LocalPipelineExecutionManager

logger = logging.getLogger(__name__)


class PipelineHeartbeat:
    """Safety net for event-driven pipeline execution.

    Callable cron handler that detects stalled pipelines, checks agent
    liveness, and fires lost continuations.
    """

    def __init__(
        self,
        execution_manager: LocalPipelineExecutionManager,
        completion_registry: CompletionEventRegistry,
        agent_registry: RunningAgentRegistry,
        agent_run_manager: LocalAgentRunManager,
        db: DatabaseProtocol,
        stall_threshold_seconds: float = 120.0,
    ) -> None:
        self._execution_manager = execution_manager
        self._completion_registry = completion_registry
        self._agent_registry = agent_registry
        self._agent_run_manager = agent_run_manager
        self._db = db
        self._stall_threshold_seconds = stall_threshold_seconds

    async def __call__(self, job: CronJob) -> str:
        """Cron handler entry point."""
        stalled = await self.check_stalled_executions()
        orphaned = await self.check_orphaned_continuations()
        return f"Heartbeat: {stalled} stalled handled, {orphaned} orphaned fired"

    async def check_stalled_executions(self) -> int:
        """Find stalled RUNNING executions and take corrective action.

        For each stalled execution:
        - If agents still alive → touch updated_at (slow, not stalled)
        - If agents dead + orphaned continuation → fire continuation
        - If agents dead + no continuation → mark FAILED

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

        # Agents are dead — check for orphaned continuations
        result = self._get_continuation_for_execution(execution.id)
        if result:
            run_id, config = result
            # Lost continuation — fire it now
            await self._fire_continuation(run_id, config)
            logger.warning(
                "Heartbeat: fired lost continuation for execution %s",
                execution.id,
            )
            return 1

        # No alive agents, no continuations — truly dead
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
        agents = self._agent_registry.list_by_parent(execution.session_id)
        return len(agents) > 0

    def _get_continuation_for_execution(
        self, execution_id: str
    ) -> tuple[str, dict[str, Any]] | None:
        """Look up pipeline continuation for an execution.

        Checks both the in-memory registry and the DB table.
        Returns (run_id, config) or None.
        """
        # Check in-memory continuations first
        result = self._completion_registry.find_continuation_by_execution(execution_id)
        if result is not None:
            return result

        # Check DB table (may not be loaded into registry yet)
        try:
            rows = self._db.fetchall("SELECT run_id, config_json FROM pipeline_continuations")
            for row in rows:
                config = json.loads(row["config_json"])
                if config.get("execution_id") == execution_id:
                    return (row["run_id"], config)
        except Exception:
            logger.debug("Failed to query pipeline_continuations", exc_info=True)

        return None

    async def _fire_continuation(self, run_id: str, config: dict[str, Any] | None = None) -> None:
        """Fire a lost pipeline continuation via the registry's public API.

        If config is provided and the continuation is not already in-memory,
        registers it first so fire_continuation can find it.
        """
        if config is not None:
            # Ensure the continuation is in-memory (may have been found via DB only)
            self._completion_registry.register_continuation(run_id, config)
        await self._completion_registry.fire_continuation(run_id)

    async def check_orphaned_continuations(self) -> int:
        """Find continuations whose agent has completed but weren't fired.

        Queries pipeline_continuations, checks agent_runs status.
        If agent completed/failed but continuation still exists → fire it.

        Returns:
            Number of orphaned continuations fired
        """
        try:
            rows = self._db.fetchall("SELECT run_id, config_json FROM pipeline_continuations")
        except Exception:
            logger.debug("Failed to query pipeline_continuations", exc_info=True)
            return 0

        fired = 0
        for row in rows:
            run_id = row["run_id"]
            try:
                config = json.loads(row["config_json"])
            except (json.JSONDecodeError, TypeError):
                continue

            # Check if the agent run is still active
            agent_in_registry = self._agent_registry.get(run_id)
            if agent_in_registry:
                # Agent still running — skip
                continue

            # Agent not in registry — check DB for terminal status
            agent_run = self._agent_run_manager.get(run_id)
            if agent_run and agent_run.status in ("success", "error", "timeout", "cancelled"):
                # Agent completed but continuation wasn't fired — fire it now
                logger.warning(
                    "Heartbeat: firing orphaned continuation for completed agent %s (status=%s)",
                    run_id,
                    agent_run.status,
                )
                await self._fire_continuation(run_id, config)
                fired += 1

        return fired
