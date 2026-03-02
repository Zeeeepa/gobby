"""Tests for cli/agents.py -- targeting uncovered lines.

Covers: resolve_agent_run_id, agent_stats (global),
        cleanup_agents (dry-run and execute).
Lines targeted: 48, 142-143, 230-231, 293-294, 341-342, 375-376, 405-562, 574-575
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import click
import pytest
from click.testing import CliRunner

from gobby.cli.agents import agents, resolve_agent_run_id

pytestmark = pytest.mark.unit


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _mock_run(**overrides: Any) -> MagicMock:
    defaults = {
        "id": "run-abc123def456789012345678901234",
        "parent_session_id": "sess-parent",
        "child_session_id": "sess-child",
        "workflow_name": "worker",
        "provider": "claude",
        "model": "claude-3-opus",
        "status": "running",
        "prompt": "Do things",
        "result": None,
        "error": None,
        "tool_calls_count": 5,
        "turns_used": 3,
        "started_at": "2024-01-01T10:00:00Z",
        "completed_at": None,
        "created_at": "2024-01-01T09:59:00Z",
        "updated_at": "2024-01-01T10:01:00Z",
    }
    defaults.update(overrides)
    run = MagicMock()
    for k, v in defaults.items():
        setattr(run, k, v)
    run.to_dict.return_value = defaults
    return run


# =============================================================================
# resolve_agent_run_id
# =============================================================================


class TestResolveAgentRunId:
    @patch("gobby.cli.agents.get_agent_run_manager")
    def test_exact_uuid(self, mock_mgr_fn: MagicMock) -> None:
        mgr = MagicMock()
        full_id = "a" * 36
        mgr.get.return_value = _mock_run(id=full_id)
        mock_mgr_fn.return_value = mgr
        assert resolve_agent_run_id(full_id) == full_id

    @patch("gobby.cli.agents.LocalDatabase")
    @patch("gobby.cli.agents.get_agent_run_manager")
    def test_prefix_match(self, mock_mgr_fn: MagicMock, mock_db_cls: MagicMock) -> None:
        mgr = MagicMock()
        mgr.get.return_value = None  # short ref, not exact
        mock_mgr_fn.return_value = mgr
        mock_db_cls.return_value.fetchall.return_value = [{"id": "run-abc123"}]
        assert resolve_agent_run_id("run-abc") == "run-abc123"

    @patch("gobby.cli.agents.LocalDatabase")
    @patch("gobby.cli.agents.get_agent_run_manager")
    def test_not_found(self, mock_mgr_fn: MagicMock, mock_db_cls: MagicMock) -> None:
        mgr = MagicMock()
        mgr.get.return_value = None
        mock_mgr_fn.return_value = mgr
        mock_db_cls.return_value.fetchall.return_value = []
        with pytest.raises(click.ClickException, match="not found"):
            resolve_agent_run_id("zzz")

    @patch("gobby.cli.agents.LocalDatabase")
    @patch("gobby.cli.agents.get_agent_run_manager")
    def test_ambiguous(self, mock_mgr_fn: MagicMock, mock_db_cls: MagicMock) -> None:
        mgr = MagicMock()
        mgr.get.return_value = None
        mock_mgr_fn.return_value = mgr
        mock_db_cls.return_value.fetchall.return_value = [{"id": "run-a1"}, {"id": "run-a2"}]
        with pytest.raises(click.ClickException, match="Ambiguous"):
            resolve_agent_run_id("run-a")


# =============================================================================
# kill_agent
# =============================================================================


# =============================================================================
# check_agent
# =============================================================================


# =============================================================================
# spawn_agent_cmd - error paths
# =============================================================================



# =============================================================================
# agent_stats - global
# =============================================================================


class TestAgentStatsGlobal:
    @patch("gobby.cli.agents.LocalDatabase")
    def test_global_stats(self, mock_db_cls: MagicMock, runner: CliRunner) -> None:
        mock_db_cls.return_value.fetchone.return_value = {
            "total": 20,
            "success": 15,
            "error": 2,
            "running": 1,
            "pending": 0,
            "timeout": 1,
            "cancelled": 1,
        }
        result = runner.invoke(agents, ["stats"])
        assert result.exit_code == 0
        assert "Total Runs: 20" in result.output
        assert "Success Rate: 75.0%" in result.output

    @patch("gobby.cli.agents.LocalDatabase")
    def test_global_stats_empty(self, mock_db_cls: MagicMock, runner: CliRunner) -> None:
        mock_db_cls.return_value.fetchone.return_value = None
        result = runner.invoke(agents, ["stats"])
        assert result.exit_code == 0
        assert "No agent runs found" in result.output

    @patch("gobby.cli.agents.LocalDatabase")
    def test_global_stats_zero_total(self, mock_db_cls: MagicMock, runner: CliRunner) -> None:
        mock_db_cls.return_value.fetchone.return_value = {
            "total": 0, "success": 0, "error": 0,
            "running": 0, "pending": 0, "timeout": 0, "cancelled": 0,
        }
        result = runner.invoke(agents, ["stats"])
        assert result.exit_code == 0
        assert "Total Runs: 0" in result.output
        # No success rate printed when total is 0
        assert "Success Rate" not in result.output


# =============================================================================
# cleanup_agents
# =============================================================================


class TestCleanupAgents:
    @patch("gobby.cli.agents.LocalDatabase")
    def test_cleanup_dry_run(self, mock_db_cls: MagicMock, runner: CliRunner) -> None:
        mock_db = mock_db_cls.return_value
        mock_db.fetchall.side_effect = [
            [{"id": "run-1", "started_at": "2024-01-01T00:00:00"}],  # stale running
            [{"id": "run-2", "created_at": "2024-01-01T00:00:00"}],  # stale pending
        ]
        result = runner.invoke(agents, ["cleanup", "--dry-run"])
        assert result.exit_code == 0
        assert "Stale running runs" in result.output
        assert "Stale pending runs" in result.output

    @patch("gobby.cli.agents.get_agent_run_manager")
    def test_cleanup_execute(self, mock_mgr_fn: MagicMock, runner: CliRunner) -> None:
        mgr = MagicMock()
        mgr.cleanup_stale_runs.return_value = 2
        mgr.cleanup_stale_pending_runs.return_value = 1
        mock_mgr_fn.return_value = mgr
        result = runner.invoke(agents, ["cleanup"])
        assert result.exit_code == 0
        assert "2 timed-out runs" in result.output
        assert "1 stale pending" in result.output

    @patch("gobby.cli.agents.get_agent_run_manager")
    def test_cleanup_with_timeout(self, mock_mgr_fn: MagicMock, runner: CliRunner) -> None:
        mgr = MagicMock()
        mgr.cleanup_stale_runs.return_value = 0
        mgr.cleanup_stale_pending_runs.return_value = 0
        mock_mgr_fn.return_value = mgr
        result = runner.invoke(agents, ["cleanup", "--timeout", "60"])
        assert result.exit_code == 0
        mgr.cleanup_stale_runs.assert_called_once_with(timeout_minutes=60)


# =============================================================================
# list_agents - edge cases
# =============================================================================


class TestListAgentsEdgeCases:
    @patch("gobby.cli.agents.get_agent_run_manager")
    def test_list_running_shortcut(self, mock_mgr_fn: MagicMock, runner: CliRunner) -> None:
        mgr = MagicMock()
        mgr.list_running.return_value = []
        mock_mgr_fn.return_value = mgr
        result = runner.invoke(agents, ["list", "--status", "running"])
        assert result.exit_code == 0
        mgr.list_running.assert_called_once_with(limit=20)

    @patch("gobby.cli.agents.LocalDatabase")
    @patch("gobby.cli.agents.get_agent_run_manager")
    def test_list_all_no_filter(self, mock_mgr_fn: MagicMock, mock_db_cls: MagicMock, runner: CliRunner) -> None:
        mock_db_cls.return_value.fetchall.return_value = []
        result = runner.invoke(agents, ["list"])
        assert result.exit_code == 0
        assert "No agent runs found" in result.output

    @patch("gobby.cli.agents.LocalDatabase")
    @patch("gobby.cli.agents.get_agent_run_manager")
    def test_list_with_status_filter(self, mock_mgr_fn: MagicMock, mock_db_cls: MagicMock, runner: CliRunner) -> None:
        mock_db_cls.return_value.fetchall.return_value = []
        result = runner.invoke(agents, ["list", "--status", "error"])
        assert result.exit_code == 0
        mock_db_cls.return_value.fetchall.assert_called_once()



# =============================================================================
# show_agent / agent_status - edge cases
# =============================================================================


class TestShowStatusEdgeCases:
    @patch("gobby.cli.agents.resolve_agent_run_id", return_value="run-1")
    @patch("gobby.cli.agents.get_agent_run_manager")
    def test_show_not_found(self, mock_mgr_fn: MagicMock, mock_resolve: MagicMock, runner: CliRunner) -> None:
        mock_mgr_fn.return_value.get.return_value = None
        result = runner.invoke(agents, ["show", "run-1"])
        assert result.exit_code == 0
        assert "Agent run not found" in result.output

    @patch("gobby.cli.agents.resolve_agent_run_id", return_value="run-1")
    @patch("gobby.cli.agents.get_agent_run_manager")
    def test_status_not_found(self, mock_mgr_fn: MagicMock, mock_resolve: MagicMock, runner: CliRunner) -> None:
        mock_mgr_fn.return_value.get.return_value = None
        result = runner.invoke(agents, ["status", "run-1"])
        assert result.exit_code == 0
        assert "Agent run not found" in result.output

    @patch("gobby.cli.agents.resolve_agent_run_id", return_value="run-1")
    @patch("gobby.cli.agents.get_agent_run_manager")
    def test_status_completed(self, mock_mgr_fn: MagicMock, mock_resolve: MagicMock, runner: CliRunner) -> None:
        run = _mock_run(status="error", error="segfault", completed_at="2024-01-01T11:00:00Z")
        mock_mgr_fn.return_value.get.return_value = run
        result = runner.invoke(agents, ["status", "run-1"])
        assert result.exit_code == 0
        assert "Completed:" in result.output
        assert "Error: segfault" in result.output

    @patch("gobby.cli.agents.resolve_agent_run_id", return_value="run-1")
    @patch("gobby.cli.agents.get_agent_run_manager")
    def test_stop_not_stoppable(self, mock_mgr_fn: MagicMock, mock_resolve: MagicMock, runner: CliRunner) -> None:
        run = _mock_run(status="success")
        mock_mgr_fn.return_value.get.return_value = run
        result = runner.invoke(agents, ["stop", "run-1", "--yes"])
        assert result.exit_code == 0
        assert "Cannot stop agent in status" in result.output

    @patch("gobby.cli.agents.resolve_agent_run_id", return_value="run-1")
    @patch("gobby.cli.agents.get_agent_run_manager")
    def test_stop_not_found(self, mock_mgr_fn: MagicMock, mock_resolve: MagicMock, runner: CliRunner) -> None:
        mock_mgr_fn.return_value.get.return_value = None
        result = runner.invoke(agents, ["stop", "run-1", "--yes"])
        assert result.exit_code == 0
        assert "Agent run not found" in result.output
