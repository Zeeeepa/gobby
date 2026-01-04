"""Tests for commit linking and diff functionality."""

from unittest.mock import MagicMock, patch

import pytest

from gobby.tasks.commits import get_task_diff, TaskDiffResult


class TestGetTaskDiff:
    """Tests for get_task_diff function."""

    @pytest.fixture
    def mock_task_manager(self):
        """Create a mock task manager."""
        manager = MagicMock()
        return manager

    def test_returns_combined_diff_for_linked_commits(self, mock_task_manager):
        """Test that get_task_diff returns combined diff for all linked commits."""
        # Mock task with commits
        mock_task = MagicMock()
        mock_task.commits = ["abc123", "def456"]
        mock_task_manager.get_task.return_value = mock_task

        # Mock git diff output
        with patch("gobby.tasks.commits.run_git_command") as mock_git:
            mock_git.return_value = "diff --git a/file.py b/file.py\n+added line"

            result = get_task_diff("gt-test123", mock_task_manager)

            assert isinstance(result, TaskDiffResult)
            assert "added line" in result.diff
            assert result.commits == ["abc123", "def456"]

    def test_includes_uncommitted_changes(self, mock_task_manager):
        """Test that uncommitted changes are included when flag is set."""
        mock_task = MagicMock()
        mock_task.commits = ["abc123"]
        mock_task_manager.get_task.return_value = mock_task

        with patch("gobby.tasks.commits.run_git_command") as mock_git:
            # First call for committed diff, second for uncommitted
            mock_git.side_effect = [
                "diff from commit",
                "diff from uncommitted",
            ]

            result = get_task_diff(
                "gt-test123",
                mock_task_manager,
                include_uncommitted=True,
            )

            assert "diff from commit" in result.diff
            assert "diff from uncommitted" in result.diff
            assert result.has_uncommitted_changes is True

    def test_excludes_uncommitted_changes_by_default(self, mock_task_manager):
        """Test that uncommitted changes are excluded by default."""
        mock_task = MagicMock()
        mock_task.commits = ["abc123"]
        mock_task_manager.get_task.return_value = mock_task

        with patch("gobby.tasks.commits.run_git_command") as mock_git:
            mock_git.return_value = "diff from commit"

            result = get_task_diff("gt-test123", mock_task_manager)

            # Should only call git once for the commit diff
            assert mock_git.call_count == 1
            assert result.has_uncommitted_changes is False

    def test_handles_task_with_no_commits(self, mock_task_manager):
        """Test graceful handling of tasks with no linked commits."""
        mock_task = MagicMock()
        mock_task.commits = None
        mock_task_manager.get_task.return_value = mock_task

        result = get_task_diff("gt-test123", mock_task_manager)

        assert result.diff == ""
        assert result.commits == []
        assert result.has_uncommitted_changes is False

    def test_handles_empty_commits_list(self, mock_task_manager):
        """Test graceful handling of empty commits list."""
        mock_task = MagicMock()
        mock_task.commits = []
        mock_task_manager.get_task.return_value = mock_task

        result = get_task_diff("gt-test123", mock_task_manager)

        assert result.diff == ""
        assert result.commits == []

    def test_returns_empty_diff_when_no_changes(self, mock_task_manager):
        """Test that empty diff is returned when commits have no diff."""
        mock_task = MagicMock()
        mock_task.commits = ["abc123"]
        mock_task_manager.get_task.return_value = mock_task

        with patch("gobby.tasks.commits.run_git_command") as mock_git:
            mock_git.return_value = ""

            result = get_task_diff("gt-test123", mock_task_manager)

            assert result.diff == ""
            assert result.commits == ["abc123"]

    def test_orders_commits_chronologically(self, mock_task_manager):
        """Test that commits are processed in chronological order."""
        mock_task = MagicMock()
        # Commits listed newest to oldest (as typically stored)
        mock_task.commits = ["newest", "middle", "oldest"]
        mock_task_manager.get_task.return_value = mock_task

        call_order = []
        with patch("gobby.tasks.commits.run_git_command") as mock_git:
            def capture_call(*args, **kwargs):
                call_order.append(args)
                return "diff"

            mock_git.side_effect = capture_call

            result = get_task_diff("gt-test123", mock_task_manager)

            # Commits should be in the result in order
            assert result.commits == ["newest", "middle", "oldest"]

    def test_raises_on_invalid_task(self, mock_task_manager):
        """Test that ValueError is raised for non-existent task."""
        mock_task_manager.get_task.side_effect = ValueError("Task not found")

        with pytest.raises(ValueError, match="not found"):
            get_task_diff("gt-nonexistent", mock_task_manager)

    def test_task_diff_result_structure(self, mock_task_manager):
        """Test TaskDiffResult contains expected fields."""
        mock_task = MagicMock()
        mock_task.commits = ["abc123"]
        mock_task_manager.get_task.return_value = mock_task

        with patch("gobby.tasks.commits.run_git_command") as mock_git:
            mock_git.return_value = "diff content"

            result = get_task_diff("gt-test123", mock_task_manager)

            assert hasattr(result, "diff")
            assert hasattr(result, "commits")
            assert hasattr(result, "has_uncommitted_changes")
            assert hasattr(result, "file_count")

    def test_counts_modified_files(self, mock_task_manager):
        """Test that file count is calculated from diff."""
        mock_task = MagicMock()
        mock_task.commits = ["abc123"]
        mock_task_manager.get_task.return_value = mock_task

        diff_with_files = """diff --git a/file1.py b/file1.py
index abc..def 100644
--- a/file1.py
+++ b/file1.py
@@ -1,1 +1,2 @@
+new line
diff --git a/file2.py b/file2.py
index 123..456 100644
--- a/file2.py
+++ b/file2.py
@@ -1,1 +1,2 @@
+another line
"""

        with patch("gobby.tasks.commits.run_git_command") as mock_git:
            mock_git.return_value = diff_with_files

            result = get_task_diff("gt-test123", mock_task_manager)

            assert result.file_count == 2
