"""Tests for gobby.conductor.loop module.

Tests for the ConductorLoop class that:
- Orchestrates monitors (TaskMonitor, AgentWatcher)
- Dispatches alerts based on monitor results
- Checks budget before running monitors
- Throttles when budget exceeded
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock


class TestConductorLoopTick:
    """Tests for ConductorLoop.tick() method."""

    def test_tick_runs_task_monitor(self):
        """ConductorLoop.tick() runs TaskMonitor.check()."""
        from gobby.conductor.loop import ConductorLoop

        mock_task_monitor = MagicMock()
        mock_task_monitor.check.return_value = {
            "stale_tasks": [],
            "blocked_chains": [],
            "summary": {"stale_count": 0, "blocked_count": 0, "checked_at": datetime.now(UTC).isoformat()},
        }

        mock_agent_watcher = MagicMock()
        mock_agent_watcher.check.return_value = {
            "stuck_agents": [],
            "summary": {"stuck_count": 0, "total_running": 0, "checked_at": datetime.now(UTC).isoformat()},
        }

        mock_alert_dispatcher = MagicMock()

        loop = ConductorLoop(
            task_monitor=mock_task_monitor,
            agent_watcher=mock_agent_watcher,
            alert_dispatcher=mock_alert_dispatcher,
        )

        result = loop.tick()

        assert result["success"] is True
        mock_task_monitor.check.assert_called_once()

    def test_tick_runs_agent_watcher(self):
        """ConductorLoop.tick() runs AgentWatcher.check()."""
        from gobby.conductor.loop import ConductorLoop

        mock_task_monitor = MagicMock()
        mock_task_monitor.check.return_value = {
            "stale_tasks": [],
            "blocked_chains": [],
            "summary": {"stale_count": 0, "blocked_count": 0, "checked_at": datetime.now(UTC).isoformat()},
        }

        mock_agent_watcher = MagicMock()
        mock_agent_watcher.check.return_value = {
            "stuck_agents": [],
            "summary": {"stuck_count": 0, "total_running": 0, "checked_at": datetime.now(UTC).isoformat()},
        }

        mock_alert_dispatcher = MagicMock()

        loop = ConductorLoop(
            task_monitor=mock_task_monitor,
            agent_watcher=mock_agent_watcher,
            alert_dispatcher=mock_alert_dispatcher,
        )

        result = loop.tick()

        assert result["success"] is True
        mock_agent_watcher.check.assert_called_once()


class TestConductorLoopAlerts:
    """Tests for alert dispatching."""

    def test_tick_dispatches_alert_for_stale_tasks(self):
        """ConductorLoop.tick() dispatches urgent alert for stale tasks."""
        from gobby.conductor.loop import ConductorLoop

        mock_task_monitor = MagicMock()
        mock_task_monitor.check.return_value = {
            "stale_tasks": [{"task_id": "task-1", "title": "Stale Task"}],
            "blocked_chains": [],
            "summary": {"stale_count": 1, "blocked_count": 0, "checked_at": datetime.now(UTC).isoformat()},
        }

        mock_agent_watcher = MagicMock()
        mock_agent_watcher.check.return_value = {
            "stuck_agents": [],
            "summary": {"stuck_count": 0, "total_running": 0, "checked_at": datetime.now(UTC).isoformat()},
        }

        mock_alert_dispatcher = MagicMock()
        mock_alert_dispatcher.dispatch.return_value = {"success": True}

        loop = ConductorLoop(
            task_monitor=mock_task_monitor,
            agent_watcher=mock_agent_watcher,
            alert_dispatcher=mock_alert_dispatcher,
        )

        loop.tick()

        # Should dispatch an urgent alert for stale tasks
        mock_alert_dispatcher.dispatch.assert_called()
        call_args = mock_alert_dispatcher.dispatch.call_args
        assert call_args[1]["priority"] == "urgent"
        assert "stale" in call_args[1]["message"].lower()

    def test_tick_dispatches_alert_for_stuck_agents(self):
        """ConductorLoop.tick() dispatches urgent alert for stuck agents."""
        from gobby.conductor.loop import ConductorLoop

        mock_task_monitor = MagicMock()
        mock_task_monitor.check.return_value = {
            "stale_tasks": [],
            "blocked_chains": [],
            "summary": {"stale_count": 0, "blocked_count": 0, "checked_at": datetime.now(UTC).isoformat()},
        }

        mock_agent_watcher = MagicMock()
        mock_agent_watcher.check.return_value = {
            "stuck_agents": [{"run_id": "run-1", "session_id": "sess-1", "minutes_running": 20}],
            "summary": {"stuck_count": 1, "total_running": 1, "checked_at": datetime.now(UTC).isoformat()},
        }

        mock_alert_dispatcher = MagicMock()
        mock_alert_dispatcher.dispatch.return_value = {"success": True}

        loop = ConductorLoop(
            task_monitor=mock_task_monitor,
            agent_watcher=mock_agent_watcher,
            alert_dispatcher=mock_alert_dispatcher,
        )

        loop.tick()

        # Should dispatch an urgent alert for stuck agents
        mock_alert_dispatcher.dispatch.assert_called()
        call_args = mock_alert_dispatcher.dispatch.call_args
        assert call_args[1]["priority"] == "urgent"
        assert "stuck" in call_args[1]["message"].lower()

    def test_tick_no_alerts_when_healthy(self):
        """ConductorLoop.tick() dispatches no alerts when all is healthy."""
        from gobby.conductor.loop import ConductorLoop

        mock_task_monitor = MagicMock()
        mock_task_monitor.check.return_value = {
            "stale_tasks": [],
            "blocked_chains": [],
            "summary": {"stale_count": 0, "blocked_count": 0, "checked_at": datetime.now(UTC).isoformat()},
        }

        mock_agent_watcher = MagicMock()
        mock_agent_watcher.check.return_value = {
            "stuck_agents": [],
            "summary": {"stuck_count": 0, "total_running": 0, "checked_at": datetime.now(UTC).isoformat()},
        }

        mock_alert_dispatcher = MagicMock()

        loop = ConductorLoop(
            task_monitor=mock_task_monitor,
            agent_watcher=mock_agent_watcher,
            alert_dispatcher=mock_alert_dispatcher,
        )

        loop.tick()

        # Should not dispatch any alerts
        mock_alert_dispatcher.dispatch.assert_not_called()


class TestConductorLoopBudget:
    """Tests for budget checking."""

    def test_tick_throttles_when_budget_exceeded(self):
        """ConductorLoop.tick() throttles when budget is exceeded."""
        from gobby.conductor.loop import ConductorLoop

        mock_task_monitor = MagicMock()
        mock_agent_watcher = MagicMock()
        mock_alert_dispatcher = MagicMock()

        mock_budget_checker = MagicMock()
        mock_budget_checker.is_budget_exceeded.return_value = True

        loop = ConductorLoop(
            task_monitor=mock_task_monitor,
            agent_watcher=mock_agent_watcher,
            alert_dispatcher=mock_alert_dispatcher,
            budget_checker=mock_budget_checker,
        )

        result = loop.tick()

        assert result["throttled"] is True
        # Monitors should not run when throttled
        mock_task_monitor.check.assert_not_called()
        mock_agent_watcher.check.assert_not_called()

    def test_tick_runs_when_budget_ok(self):
        """ConductorLoop.tick() runs monitors when budget is OK."""
        from gobby.conductor.loop import ConductorLoop

        mock_task_monitor = MagicMock()
        mock_task_monitor.check.return_value = {
            "stale_tasks": [],
            "blocked_chains": [],
            "summary": {"stale_count": 0, "blocked_count": 0, "checked_at": datetime.now(UTC).isoformat()},
        }

        mock_agent_watcher = MagicMock()
        mock_agent_watcher.check.return_value = {
            "stuck_agents": [],
            "summary": {"stuck_count": 0, "total_running": 0, "checked_at": datetime.now(UTC).isoformat()},
        }

        mock_alert_dispatcher = MagicMock()

        mock_budget_checker = MagicMock()
        mock_budget_checker.is_budget_exceeded.return_value = False

        loop = ConductorLoop(
            task_monitor=mock_task_monitor,
            agent_watcher=mock_agent_watcher,
            alert_dispatcher=mock_alert_dispatcher,
            budget_checker=mock_budget_checker,
        )

        result = loop.tick()

        assert result.get("throttled") is not True
        mock_task_monitor.check.assert_called_once()


class TestConductorLoopAutonomousMode:
    """Tests for autonomous agent spawning."""

    def test_tick_can_spawn_agent_in_autonomous_mode(self):
        """ConductorLoop.tick() can spawn agents when autonomous_mode enabled."""
        from gobby.conductor.loop import ConductorLoop

        mock_task_monitor = MagicMock()
        mock_task_monitor.check.return_value = {
            "stale_tasks": [],
            "blocked_chains": [],
            "summary": {"stale_count": 0, "blocked_count": 0, "checked_at": datetime.now(UTC).isoformat()},
        }

        mock_agent_watcher = MagicMock()
        mock_agent_watcher.check.return_value = {
            "stuck_agents": [],
            "summary": {"stuck_count": 0, "total_running": 0, "checked_at": datetime.now(UTC).isoformat()},
        }

        mock_alert_dispatcher = MagicMock()
        mock_agent_spawner = MagicMock()

        loop = ConductorLoop(
            task_monitor=mock_task_monitor,
            agent_watcher=mock_agent_watcher,
            alert_dispatcher=mock_alert_dispatcher,
            agent_spawner=mock_agent_spawner,
            autonomous_mode=True,
        )

        # In autonomous mode, should consider spawning
        result = loop.tick()

        assert result["success"] is True
        assert "autonomous_mode" in result

    def test_tick_does_not_spawn_without_autonomous_mode(self):
        """ConductorLoop.tick() does not auto-spawn without autonomous_mode."""
        from gobby.conductor.loop import ConductorLoop

        mock_task_monitor = MagicMock()
        mock_task_monitor.check.return_value = {
            "stale_tasks": [],
            "blocked_chains": [],
            "summary": {"stale_count": 0, "blocked_count": 0, "checked_at": datetime.now(UTC).isoformat()},
        }

        mock_agent_watcher = MagicMock()
        mock_agent_watcher.check.return_value = {
            "stuck_agents": [],
            "summary": {"stuck_count": 0, "total_running": 0, "checked_at": datetime.now(UTC).isoformat()},
        }

        mock_alert_dispatcher = MagicMock()
        mock_agent_spawner = MagicMock()

        loop = ConductorLoop(
            task_monitor=mock_task_monitor,
            agent_watcher=mock_agent_watcher,
            alert_dispatcher=mock_alert_dispatcher,
            agent_spawner=mock_agent_spawner,
            autonomous_mode=False,
        )

        loop.tick()

        # Spawner should not be called
        mock_agent_spawner.spawn.assert_not_called()


class TestConductorLoopSummary:
    """Tests for tick summary."""

    def test_tick_returns_summary(self):
        """ConductorLoop.tick() returns summary of all checks."""
        from gobby.conductor.loop import ConductorLoop

        mock_task_monitor = MagicMock()
        mock_task_monitor.check.return_value = {
            "stale_tasks": [],
            "blocked_chains": [],
            "summary": {"stale_count": 0, "blocked_count": 0, "checked_at": datetime.now(UTC).isoformat()},
        }

        mock_agent_watcher = MagicMock()
        mock_agent_watcher.check.return_value = {
            "stuck_agents": [],
            "summary": {"stuck_count": 0, "total_running": 0, "checked_at": datetime.now(UTC).isoformat()},
        }

        mock_alert_dispatcher = MagicMock()

        loop = ConductorLoop(
            task_monitor=mock_task_monitor,
            agent_watcher=mock_agent_watcher,
            alert_dispatcher=mock_alert_dispatcher,
        )

        result = loop.tick()

        assert "success" in result
        assert "task_monitor_result" in result
        assert "agent_watcher_result" in result
        assert "checked_at" in result
