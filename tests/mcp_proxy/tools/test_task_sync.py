"""
Tests for task_sync.py MCP tools module.

This file tests the sync and commit linking tools that will be extracted
from tasks.py into task_sync.py using Strangler Fig pattern.

RED PHASE: These tests will fail initially because task_sync.py
does not exist yet. The module will be created in the green phase.
"""

from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


class TestSyncTasks:
    """Tests for sync_tasks MCP tool."""

    def test_sync_tasks_both_directions(self, mock_sync_registry) -> None:
        """Test sync_tasks with both directions."""
        from gobby.mcp_proxy.tools.task_sync import create_sync_registry

        sync_manager = MagicMock()
        registry = create_sync_registry(task_manager=MagicMock(), sync_manager=sync_manager)

        sync = registry.get_tool("sync_tasks")
        result = sync(direction="both")

        assert result["import"] == "completed"
        assert result["export"] == "completed"
        sync_manager.import_from_jsonl.assert_called_once()
        sync_manager.export_to_jsonl.assert_called_once()

    def test_sync_tasks_import_only(self, mock_sync_registry) -> None:
        """Test sync_tasks with import direction only."""
        from gobby.mcp_proxy.tools.task_sync import create_sync_registry

        sync_manager = MagicMock()
        registry = create_sync_registry(task_manager=MagicMock(), sync_manager=sync_manager)

        sync = registry.get_tool("sync_tasks")
        result = sync(direction="import")

        assert result["import"] == "completed"
        assert "export" not in result
        sync_manager.import_from_jsonl.assert_called_once()
        sync_manager.export_to_jsonl.assert_not_called()

    def test_sync_tasks_export_only(self, mock_sync_registry) -> None:
        """Test sync_tasks with export direction only."""
        from gobby.mcp_proxy.tools.task_sync import create_sync_registry

        sync_manager = MagicMock()
        registry = create_sync_registry(task_manager=MagicMock(), sync_manager=sync_manager)

        sync = registry.get_tool("sync_tasks")
        result = sync(direction="export")

        assert result["export"] == "completed"
        assert "import" not in result
        sync_manager.export_to_jsonl.assert_called_once()
        sync_manager.import_from_jsonl.assert_not_called()

    def test_sync_tasks_default_is_both(self, mock_sync_registry) -> None:
        """Test that default direction is 'both'."""
        from gobby.mcp_proxy.tools.task_sync import create_sync_registry

        sync_manager = MagicMock()
        registry = create_sync_registry(task_manager=MagicMock(), sync_manager=sync_manager)

        sync = registry.get_tool("sync_tasks")
        result = sync()

        assert "import" in result
        assert "export" in result


class TestGetSyncStatus:
    """Tests for get_sync_status MCP tool."""

    def test_get_sync_status_basic(self, mock_sync_registry) -> None:
        """Test get_sync_status returns sync manager status."""
        from gobby.mcp_proxy.tools.task_sync import create_sync_registry

        sync_manager = MagicMock()
        sync_manager.get_sync_status.return_value = {
            "last_import": "2026-01-01T00:00:00Z",
            "last_export": "2026-01-01T00:00:00Z",
            "pending_changes": 0,
        }
        registry = create_sync_registry(task_manager=MagicMock(), sync_manager=sync_manager)

        get_status = registry.get_tool("get_sync_status")
        result = get_status()

        assert "last_import" in result
        assert "last_export" in result
        sync_manager.get_sync_status.assert_called_once()


class TestLinkCommit:
    """Tests for link_commit MCP tool."""

    def test_link_commit_success(self, mock_sync_registry) -> None:
        """Test successful commit linking."""
        from gobby.mcp_proxy.tools.task_sync import create_sync_registry

        task_manager = MagicMock()
        mock_task = MagicMock()
        mock_task.id = "task-1"
        mock_task.commits = ["abc123"]
        task_manager.link_commit.return_value = mock_task

        registry = create_sync_registry(
            task_manager=task_manager,
            sync_manager=MagicMock(),
        )

        link = registry.get_tool("link_commit")
        result = link(task_id="task-1", commit_sha="abc123")

        assert result["task_id"] == "task-1"
        assert "abc123" in result["commits"]
        task_manager.link_commit.assert_called_once_with("task-1", "abc123", cwd=None)

    def test_link_commit_error(self, mock_sync_registry) -> None:
        """Test link_commit returns error on failure."""
        from gobby.mcp_proxy.tools.task_sync import create_sync_registry

        task_manager = MagicMock()
        task_manager.link_commit.side_effect = ValueError("Task not found")

        registry = create_sync_registry(
            task_manager=task_manager,
            sync_manager=MagicMock(),
        )

        link = registry.get_tool("link_commit")
        result = link(task_id="task-1", commit_sha="abc123")

        assert "error" in result
        assert "Task not found" in result["error"]

    def test_link_commit_empty_commits_list(self, mock_sync_registry) -> None:
        """Test link_commit when task had no previous commits."""
        from gobby.mcp_proxy.tools.task_sync import create_sync_registry

        task_manager = MagicMock()
        mock_task = MagicMock()
        mock_task.id = "task-1"
        mock_task.commits = None  # No commits yet
        task_manager.link_commit.return_value = mock_task

        registry = create_sync_registry(
            task_manager=task_manager,
            sync_manager=MagicMock(),
        )

        link = registry.get_tool("link_commit")
        result = link(task_id="task-1", commit_sha="abc123")

        # Should handle None commits gracefully
        assert result["commits"] == []


class TestUnlinkCommit:
    """Tests for unlink_commit MCP tool."""

    def test_unlink_commit_success(self, mock_sync_registry) -> None:
        """Test successful commit unlinking."""
        from gobby.mcp_proxy.tools.task_sync import create_sync_registry

        task_manager = MagicMock()
        mock_task = MagicMock()
        mock_task.id = "task-1"
        mock_task.commits = []  # After unlink
        task_manager.unlink_commit.return_value = mock_task

        registry = create_sync_registry(
            task_manager=task_manager,
            sync_manager=MagicMock(),
        )

        unlink = registry.get_tool("unlink_commit")
        result = unlink(task_id="task-1", commit_sha="abc123")

        assert result["task_id"] == "task-1"
        assert result["commits"] == []
        task_manager.unlink_commit.assert_called_once_with("task-1", "abc123", cwd=None)

    def test_unlink_commit_error(self, mock_sync_registry) -> None:
        """Test unlink_commit returns error on failure."""
        from gobby.mcp_proxy.tools.task_sync import create_sync_registry

        task_manager = MagicMock()
        task_manager.unlink_commit.side_effect = ValueError("Commit not linked")

        registry = create_sync_registry(
            task_manager=task_manager,
            sync_manager=MagicMock(),
        )

        unlink = registry.get_tool("unlink_commit")
        result = unlink(task_id="task-1", commit_sha="abc123")

        assert "error" in result
        assert "Commit not linked" in result["error"]


class TestAutoLinkCommits:
    """Tests for auto_link_commits MCP tool."""

    def test_auto_link_commits_basic(self, mock_sync_registry) -> None:
        """Test auto_link_commits basic call."""
        from gobby.mcp_proxy.tools.task_sync import create_sync_registry

        task_manager = MagicMock()
        project_manager = MagicMock()
        mock_project = MagicMock()
        mock_project.repo_path = "/path/to/repo"
        project_manager.get.return_value = mock_project

        mock_result = MagicMock()
        mock_result.linked_tasks = ["task-1", "task-2"]
        mock_result.total_linked = 2
        mock_result.skipped = []

        registry = create_sync_registry(
            task_manager=task_manager,
            sync_manager=MagicMock(),
            project_manager=project_manager,
            auto_link_commits_fn=MagicMock(return_value=mock_result),
        )

        auto_link = registry.get_tool("auto_link_commits")
        result = auto_link()

        assert result["total_linked"] == 2
        assert "task-1" in result["linked_tasks"]
        assert "task-2" in result["linked_tasks"]

    def test_auto_link_commits_with_task_filter(self, mock_sync_registry) -> None:
        """Test auto_link_commits with task_id filter."""
        from gobby.mcp_proxy.tools.task_sync import create_sync_registry

        task_manager = MagicMock()
        project_manager = MagicMock()
        project_manager.get.return_value = None

        mock_fn = MagicMock()
        mock_result = MagicMock()
        mock_result.linked_tasks = ["task-1"]
        mock_result.total_linked = 1
        mock_result.skipped = []
        mock_fn.return_value = mock_result

        registry = create_sync_registry(
            task_manager=task_manager,
            sync_manager=MagicMock(),
            project_manager=project_manager,
            auto_link_commits_fn=mock_fn,
        )

        auto_link = registry.get_tool("auto_link_commits")
        auto_link(task_id="task-1")

        # Verify task_id was passed
        call_kwargs = mock_fn.call_args.kwargs
        assert call_kwargs["task_id"] == "task-1"

    def test_auto_link_commits_with_since(self, mock_sync_registry) -> None:
        """Test auto_link_commits with since parameter."""
        from gobby.mcp_proxy.tools.task_sync import create_sync_registry

        task_manager = MagicMock()
        project_manager = MagicMock()
        project_manager.get.return_value = None

        mock_fn = MagicMock()
        mock_result = MagicMock()
        mock_result.linked_tasks = []
        mock_result.total_linked = 0
        mock_result.skipped = []
        mock_fn.return_value = mock_result

        registry = create_sync_registry(
            task_manager=task_manager,
            sync_manager=MagicMock(),
            project_manager=project_manager,
            auto_link_commits_fn=mock_fn,
        )

        auto_link = registry.get_tool("auto_link_commits")
        auto_link(since="1 week ago")

        call_kwargs = mock_fn.call_args.kwargs
        assert call_kwargs["since"] == "1 week ago"

    def test_auto_link_commits_no_project(self, mock_sync_registry) -> None:
        """Test auto_link_commits when no project context."""
        from gobby.mcp_proxy.tools.task_sync import create_sync_registry

        task_manager = MagicMock()
        project_manager = MagicMock()
        project_manager.get.return_value = None

        mock_fn = MagicMock()
        mock_result = MagicMock()
        mock_result.linked_tasks = []
        mock_result.total_linked = 0
        mock_result.skipped = []
        mock_fn.return_value = mock_result

        with patch(
            "gobby.mcp_proxy.tools.task_sync.get_project_context",
            return_value=None,
        ):
            registry = create_sync_registry(
                task_manager=task_manager,
                sync_manager=MagicMock(),
                project_manager=project_manager,
                auto_link_commits_fn=mock_fn,
            )

            auto_link = registry.get_tool("auto_link_commits")
            auto_link()

            # Should still work, just with cwd=None
            call_kwargs = mock_fn.call_args.kwargs
            assert call_kwargs["cwd"] is None


class TestGetTaskDiff:
    """Tests for get_task_diff MCP tool."""

    def test_get_task_diff_basic(self, mock_sync_registry) -> None:
        """Test get_task_diff basic call."""
        from gobby.mcp_proxy.tools.task_sync import create_sync_registry

        task_manager = MagicMock()
        mock_task = MagicMock()
        mock_task.project_id = "project-1"
        task_manager.get_task.return_value = mock_task

        project_manager = MagicMock()
        mock_project = MagicMock()
        mock_project.repo_path = "/path/to/repo"
        project_manager.get.return_value = mock_project

        mock_diff_result = MagicMock()
        mock_diff_result.diff = "diff content"
        mock_diff_result.commits = ["abc123"]
        mock_diff_result.has_uncommitted_changes = False
        mock_diff_result.file_count = 3

        mock_get_task_diff = MagicMock(return_value=mock_diff_result)

        registry = create_sync_registry(
            task_manager=task_manager,
            sync_manager=MagicMock(),
            project_manager=project_manager,
            get_task_diff_fn=mock_get_task_diff,
        )

        get_diff = registry.get_tool("get_task_diff")
        result = get_diff(task_id="task-1")

        assert result["diff"] == "diff content"
        assert result["commits"] == ["abc123"]
        assert result["has_uncommitted_changes"] is False
        assert result["file_count"] == 3

    def test_get_task_diff_task_not_found(self, mock_sync_registry) -> None:
        """Test get_task_diff when task not found."""
        from gobby.mcp_proxy.tools.task_sync import create_sync_registry

        task_manager = MagicMock()
        task_manager.get_task.return_value = None

        registry = create_sync_registry(
            task_manager=task_manager,
            sync_manager=MagicMock(),
        )

        get_diff = registry.get_tool("get_task_diff")
        result = get_diff(task_id="nonexistent")

        assert "error" in result
        assert "not found" in result["error"]

    def test_get_task_diff_include_uncommitted(self, mock_sync_registry) -> None:
        """Test get_task_diff with include_uncommitted=True."""
        from gobby.mcp_proxy.tools.task_sync import create_sync_registry

        task_manager = MagicMock()
        mock_task = MagicMock()
        mock_task.project_id = "project-1"
        task_manager.get_task.return_value = mock_task

        project_manager = MagicMock()
        project_manager.get.return_value = None

        mock_diff_result = MagicMock()
        mock_diff_result.diff = "diff with uncommitted"
        mock_diff_result.commits = []
        mock_diff_result.has_uncommitted_changes = True
        mock_diff_result.file_count = 5

        mock_get_task_diff = MagicMock(return_value=mock_diff_result)

        registry = create_sync_registry(
            task_manager=task_manager,
            sync_manager=MagicMock(),
            project_manager=project_manager,
            get_task_diff_fn=mock_get_task_diff,
        )

        get_diff = registry.get_tool("get_task_diff")
        result = get_diff(task_id="task-1", include_uncommitted=True)

        assert result["has_uncommitted_changes"] is True
        call_kwargs = mock_get_task_diff.call_args.kwargs
        assert call_kwargs["include_uncommitted"] is True


class TestGitIntegrationEdgeCases:
    """Tests for git integration edge cases."""

    def test_link_commit_full_sha(self, mock_sync_registry) -> None:
        """Test linking with full SHA."""
        from gobby.mcp_proxy.tools.task_sync import create_sync_registry

        task_manager = MagicMock()
        mock_task = MagicMock()
        mock_task.id = "task-1"
        mock_task.commits = ["abc123def456"]
        task_manager.link_commit.return_value = mock_task

        registry = create_sync_registry(
            task_manager=task_manager,
            sync_manager=MagicMock(),
        )

        link = registry.get_tool("link_commit")
        full_sha = "abc123def456789abcdef123456789abcdef1234"
        link(task_id="task-1", commit_sha=full_sha)

        task_manager.link_commit.assert_called_with("task-1", full_sha, cwd=None)

    def test_link_commit_short_sha(self, mock_sync_registry) -> None:
        """Test linking with short SHA."""
        from gobby.mcp_proxy.tools.task_sync import create_sync_registry

        task_manager = MagicMock()
        mock_task = MagicMock()
        mock_task.id = "task-1"
        mock_task.commits = ["abc123"]
        task_manager.link_commit.return_value = mock_task

        registry = create_sync_registry(
            task_manager=task_manager,
            sync_manager=MagicMock(),
        )

        link = registry.get_tool("link_commit")
        link(task_id="task-1", commit_sha="abc123")

        task_manager.link_commit.assert_called_with("task-1", "abc123", cwd=None)

    def test_auto_link_with_skipped_commits(self, mock_sync_registry) -> None:
        """Test auto_link_commits reports skipped commits."""
        from gobby.mcp_proxy.tools.task_sync import create_sync_registry

        task_manager = MagicMock()
        project_manager = MagicMock()
        project_manager.get.return_value = None

        mock_fn = MagicMock()
        mock_result = MagicMock()
        mock_result.linked_tasks = ["task-1"]
        mock_result.total_linked = 1
        mock_result.skipped = [
            {"sha": "abc123", "reason": "already linked"},
            {"sha": "def456", "reason": "task not found"},
        ]
        mock_fn.return_value = mock_result

        registry = create_sync_registry(
            task_manager=task_manager,
            sync_manager=MagicMock(),
            project_manager=project_manager,
            auto_link_commits_fn=mock_fn,
        )

        auto_link = registry.get_tool("auto_link_commits")
        result = auto_link()

        assert len(result["skipped"]) == 2

    def test_get_task_diff_no_commits(self, mock_sync_registry) -> None:
        """Test get_task_diff when task has no linked commits."""
        from gobby.mcp_proxy.tools.task_sync import create_sync_registry

        task_manager = MagicMock()
        mock_task = MagicMock()
        mock_task.project_id = "project-1"
        task_manager.get_task.return_value = mock_task

        project_manager = MagicMock()
        project_manager.get.return_value = None

        mock_diff_result = MagicMock()
        mock_diff_result.diff = ""
        mock_diff_result.commits = []
        mock_diff_result.has_uncommitted_changes = False
        mock_diff_result.file_count = 0

        mock_get_task_diff = MagicMock(return_value=mock_diff_result)

        registry = create_sync_registry(
            task_manager=task_manager,
            sync_manager=MagicMock(),
            project_manager=project_manager,
            get_task_diff_fn=mock_get_task_diff,
        )

        get_diff = registry.get_tool("get_task_diff")
        result = get_diff(task_id="task-1")

        assert result["diff"] == ""
        assert result["commits"] == []
        assert result["file_count"] == 0


@pytest.fixture
def mock_sync_registry():
    """Fixture providing mock dependencies for registry creation."""
    with patch("gobby.mcp_proxy.tools.task_sync.get_project_context") as mock_proj:
        mock_proj.return_value = {"id": "test-project-id"}
        yield mock_proj
