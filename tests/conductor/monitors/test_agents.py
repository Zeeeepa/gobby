"""Tests for gobby.conductor.monitors.agents module.

Tests for the AgentWatcher class that detects:
- Stuck agents: Running longer than threshold without progress
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.unit

class TestAgentWatcherStuckAgents:
    """Tests for stuck agent detection."""

    def test_check_returns_stuck_agents(self) -> None:
        """AgentWatcher.check() returns agents running longer than threshold."""
        from gobby.conductor.monitors.agents import AgentWatcher

        # Create mock registry
        mock_registry = MagicMock()

        # Create a stuck agent (running for 20 minutes)
        stuck_time = datetime.now(UTC) - timedelta(minutes=20)
        stuck_agent = MagicMock()
        stuck_agent.run_id = "run-stuck"
        stuck_agent.session_id = "session-stuck"
        stuck_agent.started_at = stuck_time
        stuck_agent.mode = "terminal"

        # Create a fresh agent (running for 5 minutes)
        fresh_time = datetime.now(UTC) - timedelta(minutes=5)
        fresh_agent = MagicMock()
        fresh_agent.run_id = "run-fresh"
        fresh_agent.session_id = "session-fresh"
        fresh_agent.started_at = fresh_time
        fresh_agent.mode = "headless"

        mock_registry.list_all.return_value = [stuck_agent, fresh_agent]

        watcher = AgentWatcher(agent_registry=mock_registry)
        result = watcher.check(stuck_threshold_minutes=15)

        assert "stuck_agents" in result
        assert len(result["stuck_agents"]) == 1
        assert result["stuck_agents"][0]["run_id"] == "run-stuck"

    def test_check_with_no_stuck_agents(self) -> None:
        """AgentWatcher.check() returns empty when no stuck agents."""
        from gobby.conductor.monitors.agents import AgentWatcher

        mock_registry = MagicMock()

        # Only fresh agents
        fresh_time = datetime.now(UTC) - timedelta(minutes=5)
        fresh_agent = MagicMock()
        fresh_agent.run_id = "run-fresh"
        fresh_agent.session_id = "session-fresh"
        fresh_agent.started_at = fresh_time
        fresh_agent.mode = "terminal"

        mock_registry.list_all.return_value = [fresh_agent]

        watcher = AgentWatcher(agent_registry=mock_registry)
        result = watcher.check(stuck_threshold_minutes=15)

        assert result["stuck_agents"] == []

    def test_check_custom_threshold(self) -> None:
        """AgentWatcher.check() respects custom stuck threshold."""
        from gobby.conductor.monitors.agents import AgentWatcher

        mock_registry = MagicMock()

        # Agent running for 10 minutes
        start_time = datetime.now(UTC) - timedelta(minutes=10)
        agent = MagicMock()
        agent.run_id = "run-1"
        agent.session_id = "session-1"
        agent.started_at = start_time
        agent.mode = "terminal"

        mock_registry.list_all.return_value = [agent]

        watcher = AgentWatcher(agent_registry=mock_registry)

        # With 5-minute threshold, agent is stuck
        result = watcher.check(stuck_threshold_minutes=5)
        assert len(result["stuck_agents"]) == 1

        # With 15-minute threshold, agent is fresh
        result = watcher.check(stuck_threshold_minutes=15)
        assert len(result["stuck_agents"]) == 0

    def test_check_with_no_running_agents(self) -> None:
        """AgentWatcher.check() handles empty registry."""
        from gobby.conductor.monitors.agents import AgentWatcher

        mock_registry = MagicMock()
        mock_registry.list_all.return_value = []

        watcher = AgentWatcher(agent_registry=mock_registry)
        result = watcher.check()

        assert result["stuck_agents"] == []
        assert result["summary"]["total_running"] == 0


class TestAgentWatcherSummary:
    """Tests for watcher summary output."""

    def test_check_returns_summary_counts(self) -> None:
        """AgentWatcher.check() includes summary counts."""
        from gobby.conductor.monitors.agents import AgentWatcher

        mock_registry = MagicMock()

        stuck_time = datetime.now(UTC) - timedelta(minutes=20)
        stuck_agent = MagicMock()
        stuck_agent.run_id = "run-stuck"
        stuck_agent.session_id = "session-stuck"
        stuck_agent.started_at = stuck_time
        stuck_agent.mode = "terminal"

        fresh_time = datetime.now(UTC) - timedelta(minutes=5)
        fresh_agent = MagicMock()
        fresh_agent.run_id = "run-fresh"
        fresh_agent.session_id = "session-fresh"
        fresh_agent.started_at = fresh_time
        fresh_agent.mode = "headless"

        mock_registry.list_all.return_value = [stuck_agent, fresh_agent]

        watcher = AgentWatcher(agent_registry=mock_registry)
        result = watcher.check()

        assert "summary" in result
        assert result["summary"]["stuck_count"] == 1
        assert result["summary"]["total_running"] == 2
        assert "checked_at" in result["summary"]


class TestAgentWatcherModeFilter:
    """Tests for mode-based filtering."""

    def test_check_filters_by_mode(self) -> None:
        """AgentWatcher.check() can filter by agent mode."""
        from gobby.conductor.monitors.agents import AgentWatcher

        mock_registry = MagicMock()

        # Stuck terminal agent
        terminal_agent = MagicMock()
        terminal_agent.run_id = "run-terminal"
        terminal_agent.session_id = "session-terminal"
        terminal_agent.started_at = datetime.now(UTC) - timedelta(minutes=20)
        terminal_agent.mode = "terminal"

        # Stuck headless agent
        headless_agent = MagicMock()
        headless_agent.run_id = "run-headless"
        headless_agent.session_id = "session-headless"
        headless_agent.started_at = datetime.now(UTC) - timedelta(minutes=20)
        headless_agent.mode = "headless"

        mock_registry.list_all.return_value = [terminal_agent, headless_agent]

        watcher = AgentWatcher(agent_registry=mock_registry)

        # Filter to only headless
        result = watcher.check(mode="headless")
        assert len(result["stuck_agents"]) == 1
        assert result["stuck_agents"][0]["run_id"] == "run-headless"

        # No filter - gets both
        result = watcher.check()
        assert len(result["stuck_agents"]) == 2


class TestAgentWatcherAgentInfo:
    """Tests for stuck agent info."""

    def test_stuck_agent_includes_minutes_running(self) -> None:
        """Stuck agent info includes how long it's been running."""
        from gobby.conductor.monitors.agents import AgentWatcher

        mock_registry = MagicMock()

        start_time = datetime.now(UTC) - timedelta(minutes=25)
        agent = MagicMock()
        agent.run_id = "run-1"
        agent.session_id = "session-1"
        agent.started_at = start_time
        agent.mode = "terminal"
        agent.provider = "claude"

        mock_registry.list_all.return_value = [agent]

        watcher = AgentWatcher(agent_registry=mock_registry)
        result = watcher.check(stuck_threshold_minutes=15)

        stuck = result["stuck_agents"][0]
        assert stuck["run_id"] == "run-1"
        assert stuck["session_id"] == "session-1"
        assert stuck["mode"] == "terminal"
        assert "minutes_running" in stuck
        assert stuck["minutes_running"] >= 25
