"""Tests for commit linking and diff functionality."""

from unittest.mock import MagicMock, patch

import pytest

from gobby.tasks.commits import (
    AutoLinkResult,
    TaskDiffResult,
    auto_link_commits,
    extract_task_ids_from_message,
    get_task_diff,
    is_doc_only_diff,
    summarize_diff_for_validation,
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
            mock_git.return_value = "abc123|Fix bug [gt-test123]\ndef456|Unrelated commit\n"

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
            mock_git.return_value = "abc123|[gt-task1] first task\ndef456|gt-task2: second task\n"

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
            mock_git.return_value = "abc123|[gt-test123] commit 1\ndef456|gt-test123: commit 2\n"

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
                "abc123|[gt-specific] target task\ndef456|[gt-other] different task\n"
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


class TestIsDocOnlyDiff:
    """Tests for is_doc_only_diff function."""

    def test_returns_true_for_markdown_only(self):
        """Test that returns True for markdown-only diffs."""
        diff = """diff --git a/README.md b/README.md
index abc..def 100644
--- a/README.md
+++ b/README.md
@@ -1,1 +1,2 @@
+new line
"""
        assert is_doc_only_diff(diff) is True

    def test_returns_true_for_multiple_doc_files(self):
        """Test that returns True for multiple doc files."""
        diff = """diff --git a/README.md b/README.md
+content
diff --git a/CHANGELOG.md b/CHANGELOG.md
+more content
diff --git a/docs/guide.txt b/docs/guide.txt
+text file
"""
        assert is_doc_only_diff(diff) is True

    def test_returns_false_for_code_files(self):
        """Test that returns False when code files are included."""
        diff = """diff --git a/src/main.py b/src/main.py
index abc..def 100644
--- a/src/main.py
+++ b/src/main.py
@@ -1,1 +1,2 @@
+new code
"""
        assert is_doc_only_diff(diff) is False

    def test_returns_false_for_mixed_files(self):
        """Test that returns False for mixed doc and code files."""
        diff = """diff --git a/README.md b/README.md
+doc content
diff --git a/src/main.py b/src/main.py
+code content
"""
        assert is_doc_only_diff(diff) is False

    def test_returns_false_for_empty_diff(self):
        """Test that returns False for empty diff."""
        assert is_doc_only_diff("") is False

    def test_supports_multiple_doc_extensions(self):
        """Test that various doc extensions are supported."""
        diff = """diff --git a/doc.rst b/doc.rst
+rst content
diff --git a/notes.adoc b/notes.adoc
+adoc content
diff --git a/info.markdown b/info.markdown
+markdown content
"""
        assert is_doc_only_diff(diff) is True


class TestSummarizeDiffForValidation:
    """Tests for summarize_diff_for_validation function."""

    def test_returns_original_for_small_diffs(self):
        """Test that small diffs are returned unchanged."""
        small_diff = "diff --git a/file.py b/file.py\n+line"
        result = summarize_diff_for_validation(small_diff)
        assert result == small_diff

    def test_includes_file_list_summary(self):
        """Test that summarized diffs include file list."""
        large_diff = "diff --git a/file1.py b/file1.py\n" + ("+" * 20000)
        large_diff += "\ndiff --git a/file2.py b/file2.py\n" + ("+" * 20000)

        result = summarize_diff_for_validation(large_diff, max_chars=5000)

        assert "file1.py" in result
        assert "file2.py" in result
        assert "Files Changed:" in result

    def test_counts_additions_and_deletions(self):
        """Test that summary includes +/- counts."""
        diff = """diff --git a/file.py b/file.py
+added line 1
+added line 2
-removed line
""" + ("x" * 50000)

        result = summarize_diff_for_validation(diff, max_chars=5000)

        # Should have stats in the summary
        assert "+" in result
        assert "-" in result

    def test_truncates_to_max_chars(self):
        """Test that result respects max_chars limit."""
        large_diff = "diff --git a/file.py b/file.py\n" + ("+" * 100000)

        result = summarize_diff_for_validation(large_diff, max_chars=10000)

        assert len(result) <= 10000

    def test_handles_empty_diff(self):
        """Test graceful handling of empty diff."""
        result = summarize_diff_for_validation("")
        assert result == ""

    def test_handles_none_diff(self):
        """Test graceful handling of None diff."""
        result = summarize_diff_for_validation(None)
        assert result is None

    def test_preserves_file_headers_when_truncating(self):
        """Test that file headers are preserved even when content is truncated."""
        diff = """diff --git a/important.py b/important.py
index abc..def 100644
--- a/important.py
+++ b/important.py
@@ -1,100 +1,200 @@
""" + ("+added\n" * 10000)

        result = summarize_diff_for_validation(diff, max_chars=2000)

        # Should still have the file name visible
        assert "important.py" in result


class TestExtractMentionedFiles:
    """Tests for extract_mentioned_files function."""

    def test_extracts_simple_path_from_description(self):
        """Test extraction of simple file paths from task description."""
        from gobby.tasks.commits import extract_mentioned_files

        task = {
            "title": "Fix bug",
            "description": "The issue is in src/gobby/tasks/commits.py",
        }
        result = extract_mentioned_files(task)
        assert "src/gobby/tasks/commits.py" in result

    def test_extracts_backtick_quoted_paths(self):
        """Test extraction of paths wrapped in backticks."""
        from gobby.tasks.commits import extract_mentioned_files

        task = {
            "title": "Update validation",
            "description": "Modify `path/to/file.py` to fix the issue",
        }
        result = extract_mentioned_files(task)
        assert "path/to/file.py" in result

    def test_extracts_multiple_paths(self):
        """Test extraction of multiple file paths from same text."""
        from gobby.tasks.commits import extract_mentioned_files

        task = {
            "title": "Refactor modules",
            "description": "Update src/module_a.py and src/module_b.py for consistency",
        }
        result = extract_mentioned_files(task)
        assert "src/module_a.py" in result
        assert "src/module_b.py" in result

    def test_extracts_paths_from_title(self):
        """Test extraction of file paths from task title."""
        from gobby.tasks.commits import extract_mentioned_files

        task = {
            "title": "Fix src/utils/helpers.py error handling",
            "description": "Add try/except blocks",
        }
        result = extract_mentioned_files(task)
        assert "src/utils/helpers.py" in result

    def test_extracts_relative_paths(self):
        """Test extraction of relative file paths."""
        from gobby.tasks.commits import extract_mentioned_files

        task = {
            "title": "Update tests",
            "description": "Modify tests/test_main.py and ./config/settings.yaml",
        }
        result = extract_mentioned_files(task)
        assert "tests/test_main.py" in result
        assert "./config/settings.yaml" in result

    def test_extracts_paths_without_extension(self):
        """Test extraction of paths that may not have extensions."""
        from gobby.tasks.commits import extract_mentioned_files

        task = {
            "title": "Update Makefile",
            "description": "Modify src/Makefile and scripts/build",
        }
        result = extract_mentioned_files(task)
        # Should extract paths with common file-like patterns
        assert any("Makefile" in p for p in result)

    def test_extracts_absolute_paths(self):
        """Test extraction of absolute file paths."""
        from gobby.tasks.commits import extract_mentioned_files

        task = {
            "title": "Fix config",
            "description": "Update /etc/config.yaml if needed",
        }
        result = extract_mentioned_files(task)
        assert "/etc/config.yaml" in result

    def test_returns_empty_list_when_no_paths(self):
        """Test returns empty list when no file paths found."""
        from gobby.tasks.commits import extract_mentioned_files

        task = {
            "title": "Improve performance",
            "description": "Make the application faster by optimizing algorithms",
        }
        result = extract_mentioned_files(task)
        assert result == []

    def test_handles_none_description(self):
        """Test graceful handling of None description."""
        from gobby.tasks.commits import extract_mentioned_files

        task = {
            "title": "Simple task",
            "description": None,
        }
        result = extract_mentioned_files(task)
        assert isinstance(result, list)

    def test_handles_missing_description(self):
        """Test graceful handling of missing description key."""
        from gobby.tasks.commits import extract_mentioned_files

        task = {"title": "Task with no description"}
        result = extract_mentioned_files(task)
        assert isinstance(result, list)

    def test_deduplicates_paths(self):
        """Test that duplicate paths are removed."""
        from gobby.tasks.commits import extract_mentioned_files

        task = {
            "title": "Fix src/main.py",
            "description": "The bug in src/main.py needs to be fixed in `src/main.py`",
        }
        result = extract_mentioned_files(task)
        assert result.count("src/main.py") == 1

    def test_extracts_paths_with_various_extensions(self):
        """Test extraction of paths with various common extensions."""
        from gobby.tasks.commits import extract_mentioned_files

        task = {
            "title": "Update configs",
            "description": """
            Files to update:
            - src/app.ts
            - src/styles.css
            - config.json
            - setup.cfg
            - tests/test_api.py
            """,
        }
        result = extract_mentioned_files(task)
        assert "src/app.ts" in result
        assert "src/styles.css" in result
        assert "config.json" in result
        assert "setup.cfg" in result
        assert "tests/test_api.py" in result

    def test_extracts_from_validation_criteria(self):
        """Test extraction from validation_criteria field if present."""
        from gobby.tasks.commits import extract_mentioned_files

        task = {
            "title": "Implement feature",
            "description": "Add new functionality",
            "validation_criteria": "Verify changes in src/feature.py and tests/test_feature.py",
        }
        result = extract_mentioned_files(task)
        assert "src/feature.py" in result
        assert "tests/test_feature.py" in result
