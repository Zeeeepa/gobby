"""Conductor loop for orchestrating monitors and agents.

The main daemon loop that:
- Runs TaskMonitor and AgentWatcher periodically
- Dispatches alerts based on monitor results
- Checks budget before running
- Optionally spawns agents in autonomous mode
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from gobby.conductor.alerts import AlertDispatcher
    from gobby.conductor.monitors.agents import AgentWatcher
    from gobby.conductor.monitors.tasks import TaskMonitor

logger = logging.getLogger(__name__)


class BudgetChecker(Protocol):
    """Protocol for budget checking."""

    def is_budget_exceeded(self) -> bool:
        """Check if budget is exceeded."""
        ...


class AgentSpawner(Protocol):
    """Protocol for agent spawning."""

    def spawn(self, task_id: str) -> dict[str, Any]:
        """Spawn an agent for a task."""
        ...


@dataclass
class ConductorLoop:
    """Main conductor loop that orchestrates monitors and agents.

    Runs periodic checks:
    - TaskMonitor: Detects stale tasks and blocked chains
    - AgentWatcher: Detects stuck agents
    - AlertDispatcher: Sends alerts for issues

    Supports optional autonomous mode for auto-spawning agents.
    """

    task_monitor: TaskMonitor
    """Monitor for task health."""

    agent_watcher: AgentWatcher
    """Watcher for agent health."""

    alert_dispatcher: AlertDispatcher
    """Dispatcher for alerts."""

    budget_checker: BudgetChecker | None = None
    """Optional budget checker for throttling."""

    agent_spawner: AgentSpawner | None = None
    """Optional agent spawner for autonomous mode."""

    autonomous_mode: bool = False
    """Whether to auto-spawn agents for ready tasks."""

    _logger: logging.Logger = field(default_factory=lambda: logging.getLogger(__name__))
    """Logger instance."""

    def tick(self) -> dict[str, Any]:
        """
        Run one iteration of the conductor loop.

        This method:
        1. Checks budget (if budget_checker configured)
        2. Runs TaskMonitor.check()
        3. Runs AgentWatcher.check()
        4. Dispatches alerts for any issues found
        5. Optionally spawns agents in autonomous mode

        Returns:
            Dict with results from all checks and alerts
        """
        now = datetime.now(UTC)

        # Check budget first
        if self.budget_checker is not None:
            if self.budget_checker.is_budget_exceeded():
                self._logger.warning("Budget exceeded, throttling conductor")
                return {
                    "success": True,
                    "throttled": True,
                    "reason": "budget_exceeded",
                    "checked_at": now.isoformat(),
                }

        # Run monitors
        task_result = self.task_monitor.check()
        agent_result = self.agent_watcher.check()

        # Track alerts dispatched
        alerts_dispatched = []

        # Alert for stale tasks
        stale_count = task_result["summary"]["stale_count"]
        if stale_count > 0:
            alert_result = self.alert_dispatcher.dispatch(
                priority="urgent",
                message=f"{stale_count} stale task(s) detected",
                context={"stale_tasks": task_result["stale_tasks"]},
                source="TaskMonitor",
            )
            alerts_dispatched.append(alert_result)

        # Alert for blocked chains
        blocked_count = task_result["summary"]["blocked_count"]
        if blocked_count > 0:
            alert_result = self.alert_dispatcher.dispatch(
                priority="info",
                message=f"{blocked_count} blocked task chain(s) detected",
                context={"blocked_chains": task_result["blocked_chains"]},
                source="TaskMonitor",
            )
            alerts_dispatched.append(alert_result)

        # Alert for stuck agents
        stuck_count = agent_result["summary"]["stuck_count"]
        if stuck_count > 0:
            alert_result = self.alert_dispatcher.dispatch(
                priority="urgent",
                message=f"{stuck_count} stuck agent(s) detected",
                context={"stuck_agents": agent_result["stuck_agents"]},
                source="AgentWatcher",
            )
            alerts_dispatched.append(alert_result)

        # Build result
        result: dict[str, Any] = {
            "success": True,
            "task_monitor_result": task_result,
            "agent_watcher_result": agent_result,
            "alerts_dispatched": len(alerts_dispatched),
            "checked_at": now.isoformat(),
        }

        # Handle autonomous mode
        if self.autonomous_mode:
            result["autonomous_mode"] = True
            if self.agent_spawner is not None:
                result["spawner_available"] = True
                # TODO: implement auto-spawn - see issue tracker for orchestration epic
                self._logger.warning(
                    "Autonomous mode enabled but auto-spawning not yet implemented. "
                    f"Spawner available: {self.agent_spawner is not None}"
                )
            else:
                result["spawner_available"] = False
                self._logger.warning("Autonomous mode enabled but no spawner configured")

        return result
