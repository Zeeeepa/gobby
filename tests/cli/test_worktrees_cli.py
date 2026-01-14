"""Tests for the worktrees CLI module."""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from gobby.cli import cli


class TestWorktreesShowCommand:
    """Tests for gobby worktrees show command."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create a CLI test runner."""
        return CliRunner()

    @patch("gobby.cli.worktrees.resolve_worktree_id")
    @patch("gobby.cli.worktrees.get_worktree_manager")
    def test_show_success(
        self,
        mock_get_manager: MagicMock,
        mock_resolve: MagicMock,
        runner: CliRunner,
    ):
        """Test showing a worktree successfully."""
        mock_manager = MagicMock()
        mock_wt = MagicMock()
        mock_wt.id = "wt-123"
        mock_wt.branch_name = "feat/test"
        mock_wt.worktree_path = "/tmp/wt-123"
        mock_wt.status = "active"
        mock_wt.base_branch = "main"
        mock_wt.project_id = None
        mock_wt.agent_session_id = None
        mock_wt.created_at = "2024-01-01"
        mock_wt.updated_at = "2024-01-01"

        mock_manager.get.return_value = mock_wt
        mock_get_manager.return_value = mock_manager

        mock_resolve.return_value = "wt-123"

        result = runner.invoke(cli, ["worktrees", "show", "wt-123"])

        assert result.exit_code == 0
        assert "Worktree: wt-123" in result.output
        assert "feat/test" in result.output

    def test_show_help(self, runner: CliRunner):
        """Test show --help."""
        result = runner.invoke(cli, ["worktrees", "show", "--help"])
        assert result.exit_code == 0
        assert "Show details for a worktree" in result.output


class TestWorktreesDeleteCommand:
    """Tests for gobby worktrees delete command."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create a CLI test runner."""
        return CliRunner()

    @patch("gobby.cli.worktrees.httpx.post")
    @patch("gobby.cli.worktrees.get_daemon_url")
    @patch("gobby.cli.worktrees.resolve_worktree_id")
    @patch("gobby.cli.worktrees.get_worktree_manager")
    def test_delete_success(
        self,
        mock_get_manager: MagicMock,
        mock_resolve: MagicMock,
        mock_get_url: MagicMock,
        mock_post: MagicMock,
        runner: CliRunner,
    ):
        """Test deleting a worktree."""
        mock_manager = MagicMock()
        mock_get_manager.return_value = mock_manager
        mock_resolve.return_value = "wt-del123"
        mock_get_url.return_value = "http://localhost:8765"

        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True}
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        # Need to patch get_daemon_url
        result = runner.invoke(cli, ["worktrees", "delete", "wt-del123", "--yes"])

        assert result.exit_code == 0
        assert "Deleted worktree: wt-del123" in result.output
        mock_post.assert_called_once()


class TestWorktreesClaimCommand:
    """Tests for gobby worktrees claim command."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create a CLI test runner."""
        return CliRunner()

    @patch("gobby.cli.worktrees.resolve_session_id")
    @patch("gobby.cli.worktrees.resolve_worktree_id")
    @patch("gobby.cli.worktrees.get_worktree_manager")
    def test_claim_success(
        self,
        mock_get_manager: MagicMock,
        mock_resolve_wt: MagicMock,
        mock_resolve_sess: MagicMock,
        runner: CliRunner,
    ):
        """Test claiming a worktree."""
        mock_manager = MagicMock()
        mock_manager.claim.return_value = True
        mock_get_manager.return_value = mock_manager
        mock_resolve_wt.return_value = "wt-claim123"
        mock_resolve_sess.return_value = "sess-123"

        result = runner.invoke(cli, ["worktrees", "claim", "wt-claim123", "sess-123"])

        assert result.exit_code == 0
        assert "Claimed worktree wt-claim123 for session sess-123" in result.output
        mock_manager.claim.assert_called_once_with("wt-claim123", "sess-123")
