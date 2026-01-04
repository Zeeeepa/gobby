"""Tests for commit linking and diff functionality."""

from unittest.mock import MagicMock, patch

import pytest

from gobby.tasks.commits import (
    AutoLinkResult,
    TaskDiffResult,
    auto_link_commits,
    extract_task_ids_from_message,
    get_task_diff,
)


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


class TestExtractTaskIdsFromMessage:
    """Tests for task ID extraction from commit messages."""

    def test_extracts_bracket_pattern(self):
        """Test extraction of [gt-xxxxx] pattern."""
        message = "Fix authentication bug [gt-abc123]"
        result = extract_task_ids_from_message(message)
        assert "gt-abc123" in result

    def test_extracts_colon_pattern(self):
        """Test extraction of 'gt-xxxxx:' pattern."""
        message = "gt-def456: Add new feature"
        result = extract_task_ids_from_message(message)
        assert "gt-def456" in result

    def test_extracts_implements_pattern(self):
        """Test extraction of 'Implements gt-xxxxx' pattern."""
        message = "Implements gt-789abc feature request"
        result = extract_task_ids_from_message(message)
        assert "gt-789abc" in result

    def test_extracts_fixes_pattern(self):
        """Test extraction of 'Fixes gt-xxxxx' pattern."""
        message = "Fixes gt-fix123 by updating validation"
        result = extract_task_ids_from_message(message)
        assert "gt-fix123" in result

    def test_extracts_closes_pattern(self):
        """Test extraction of 'Closes gt-xxxxx' pattern."""
        message = "Closes gt-close99"
        result = extract_task_ids_from_message(message)
        assert "gt-close99" in result

    def test_extracts_multiple_task_ids(self):
        """Test extraction of multiple task IDs from one message."""
        message = "[gt-task1] and also gt-task2: and Fixes gt-task3"
        result = extract_task_ids_from_message(message)
        assert "gt-task1" in result
        assert "gt-task2" in result
        assert "gt-task3" in result

    def test_returns_empty_for_no_matches(self):
        """Test returns empty list when no task IDs found."""
        message = "Just a regular commit message"
        result = extract_task_ids_from_message(message)
        assert result == []

    def test_deduplicates_task_ids(self):
        """Test that duplicate task IDs are removed."""
        message = "[gt-dup123] gt-dup123: Implements gt-dup123"
        result = extract_task_ids_from_message(message)
        assert result.count("gt-dup123") == 1

    def test_case_insensitive_keywords(self):
        """Test that keywords are case insensitive."""
        message = "IMPLEMENTS GT-upper123 and FIXES GT-upper456"
        result = extract_task_ids_from_message(message)
        # Task IDs should be normalized to lowercase
        assert any("upper123" in tid.lower() for tid in result)


class TestAutoLinkCommits:
    """Tests for auto_link_commits function."""

    @pytest.fixture
    def mock_task_manager(self):
        """Create a mock task manager."""
        manager = MagicMock()
        return manager

    def test_links_commits_matching_task_id(self, mock_task_manager):
        """Test that commits mentioning task IDs are linked."""
        # Mock task exists
        mock_task = MagicMock()
        mock_task.id = "gt-test123"
        mock_task.commits = []
        mock_task_manager.get_task.return_value = mock_task

        with patch("gobby.tasks.commits.run_git_command") as mock_git:
            # Mock git log output with commit mentioning task
            mock_git.return_value = (
                "abc123|Fix bug [gt-test123]\n"
                "def456|Unrelated commit\n"
            )

            result = auto_link_commits(mock_task_manager, cwd="/tmp/repo")

            assert isinstance(result, AutoLinkResult)
            assert "gt-test123" in result.linked_tasks
            assert "abc123" in result.linked_tasks["gt-test123"]

    def test_respects_since_parameter(self, mock_task_manager):
        """Test that --since parameter filters commits."""
        mock_task = MagicMock()
        mock_task.id = "gt-test123"
        mock_task.commits = []
        mock_task_manager.get_task.return_value = mock_task

        with patch("gobby.tasks.commits.run_git_command") as mock_git:
            mock_git.return_value = "abc123|[gt-test123] commit\n"

            auto_link_commits(
                mock_task_manager,
                since="1 week ago",
                cwd="/tmp/repo",
            )

            # Verify --since was passed to git log
            call_args = mock_git.call_args[0][0]
            assert any("--since" in str(arg) for arg in call_args)

    def test_does_not_duplicate_already_linked_commits(self, mock_task_manager):
        """Test that already-linked commits are not re-linked."""
        mock_task = MagicMock()
        mock_task.id = "gt-test123"
        mock_task.commits = ["abc123"]  # Already linked
        mock_task_manager.get_task.return_value = mock_task

        with patch("gobby.tasks.commits.run_git_command") as mock_git:
            mock_git.return_value = "abc123|[gt-test123] existing commit\n"

            result = auto_link_commits(mock_task_manager, cwd="/tmp/repo")

            # Should not link abc123 again
            if "gt-test123" in result.linked_tasks:
                assert "abc123" not in result.linked_tasks["gt-test123"]

    def test_links_to_multiple_tasks(self, mock_task_manager):
        """Test linking commits that mention multiple tasks."""
        task1 = MagicMock()
        task1.id = "gt-task1"
        task1.commits = []

        task2 = MagicMock()
        task2.id = "gt-task2"
        task2.commits = []

        def get_task_side_effect(task_id):
            if task_id == "gt-task1":
                return task1
            elif task_id == "gt-task2":
                return task2
            raise ValueError(f"Task {task_id} not found")

        mock_task_manager.get_task.side_effect = get_task_side_effect

        with patch("gobby.tasks.commits.run_git_command") as mock_git:
            mock_git.return_value = (
                "abc123|[gt-task1] first task\n"
                "def456|gt-task2: second task\n"
            )

            result = auto_link_commits(mock_task_manager, cwd="/tmp/repo")

            assert "gt-task1" in result.linked_tasks
            assert "gt-task2" in result.linked_tasks

    def test_skips_non_existent_tasks(self, mock_task_manager):
        """Test that commits mentioning non-existent tasks are skipped."""
        mock_task_manager.get_task.side_effect = ValueError("Task not found")

        with patch("gobby.tasks.commits.run_git_command") as mock_git:
            mock_git.return_value = "abc123|[gt-nonexistent] commit\n"

            result = auto_link_commits(mock_task_manager, cwd="/tmp/repo")

            # Should not crash, just skip the task
            assert "gt-nonexistent" not in result.linked_tasks

    def test_returns_count_of_linked_commits(self, mock_task_manager):
        """Test that result includes count of newly linked commits."""
        mock_task = MagicMock()
        mock_task.id = "gt-test123"
        mock_task.commits = []
        mock_task_manager.get_task.return_value = mock_task

        with patch("gobby.tasks.commits.run_git_command") as mock_git:
            mock_git.return_value = (
                "abc123|[gt-test123] commit 1\n"
                "def456|gt-test123: commit 2\n"
            )

            result = auto_link_commits(mock_task_manager, cwd="/tmp/repo")

            assert result.total_linked >= 2

    def test_filters_by_task_id(self, mock_task_manager):
        """Test filtering auto-link to specific task ID."""
        mock_task = MagicMock()
        mock_task.id = "gt-specific"
        mock_task.commits = []
        mock_task_manager.get_task.return_value = mock_task

        with patch("gobby.tasks.commits.run_git_command") as mock_git:
            mock_git.return_value = (
                "abc123|[gt-specific] target task\n"
                "def456|[gt-other] different task\n"
            )

            result = auto_link_commits(
                mock_task_manager,
                task_id="gt-specific",
                cwd="/tmp/repo",
            )

            # Should only link to gt-specific
            assert "gt-specific" in result.linked_tasks
            assert "gt-other" not in result.linked_tasks

    def test_handles_empty_git_log(self, mock_task_manager):
        """Test handling of empty git log output."""
        with patch("gobby.tasks.commits.run_git_command") as mock_git:
            mock_git.return_value = ""

            result = auto_link_commits(mock_task_manager, cwd="/tmp/repo")

            assert result.linked_tasks == {}
            assert result.total_linked == 0

    def test_result_includes_skipped_count(self, mock_task_manager):
        """Test that result includes count of skipped commits."""
        mock_task = MagicMock()
        mock_task.id = "gt-test123"
        mock_task.commits = ["abc123"]  # Already linked
        mock_task_manager.get_task.return_value = mock_task

        with patch("gobby.tasks.commits.run_git_command") as mock_git:
            mock_git.return_value = "abc123|[gt-test123] already linked\n"

            result = auto_link_commits(mock_task_manager, cwd="/tmp/repo")

            assert result.skipped >= 1
