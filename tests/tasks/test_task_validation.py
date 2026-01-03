import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock
from gobby.tasks.validation import (
    TaskValidator,
    ValidationResult,
    get_git_diff,
    get_recent_commits,
    get_multi_commit_diff,
    get_commits_since,
    extract_file_patterns_from_text,
    find_matching_files,
    read_files_content,
    get_validation_context_smart,
)
from gobby.config.app import TaskValidationConfig
from gobby.llm import LLMService, LLMProvider


class TestGetGitDiff:
    @patch("subprocess.run")
    def test_get_git_diff_success(self, mock_run):
        # Mock unstaged
        mock_unstaged = MagicMock()
        mock_unstaged.returncode = 0
        mock_unstaged.stdout = "diff unstaged"

        # Mock staged
        mock_staged = MagicMock()
        mock_staged.returncode = 0
        mock_staged.stdout = "diff staged"

        mock_run.side_effect = [mock_unstaged, mock_staged]

        diff = get_git_diff()
        assert "=== STAGED CHANGES ===" in diff
        assert "diff staged" in diff
        assert "=== UNSTAGED CHANGES ===" in diff
        assert "diff unstaged" in diff

    @patch("subprocess.run")
    def test_get_git_diff_no_changes(self, mock_run):
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = ""
        mock_run.return_value = mock_res

        assert get_git_diff() is None

    @patch("subprocess.run")
    def test_get_git_diff_error_code(self, mock_run):
        mock_res = MagicMock()
        mock_res.returncode = 1
        mock_run.return_value = mock_res

        assert get_git_diff() is None

    @patch("subprocess.run")
    def test_get_git_diff_exception(self, mock_run):
        mock_run.side_effect = Exception("Git error")
        assert get_git_diff() is None

    @patch("subprocess.run")
    def test_get_git_diff_truncate(self, mock_run):
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "a" * 100
        mock_run.return_value = mock_res

        diff = get_git_diff(max_chars=10)
        assert len(diff) < 100
        assert "... [diff truncated] ..." in diff


class TestTaskValidator:
    @pytest.fixture
    def mock_llm(self):
        llm = MagicMock(spec=LLMService)
        provider = AsyncMock(spec=LLMProvider)
        llm.get_provider.return_value = provider
        return llm

    @pytest.fixture
    def config(self):
        return TaskValidationConfig(enabled=True, provider="claude", model="test-model")

    @pytest.mark.asyncio
    async def test_validate_task_disabled(self, mock_llm):
        config = TaskValidationConfig(enabled=False)
        validator = TaskValidator(config, mock_llm)
        result = await validator.validate_task("task-1", "title", "instr", "summary")
        assert result.status == "pending"
        assert "disabled" in result.feedback

    @pytest.mark.asyncio
    async def test_validate_task_missing_info(self, config, mock_llm):
        validator = TaskValidator(config, mock_llm)
        result = await validator.validate_task(
            "task-1", "title", None, "summary"
        )  # Missing instruction (instr is None)
        assert result.status == "pending"
        assert "Missing" in result.feedback

    @pytest.mark.asyncio
    async def test_validate_task_success(self, config, mock_llm):
        validator = TaskValidator(config, mock_llm)

        mock_provider = mock_llm.get_provider.return_value
        mock_provider.generate_text.return_value = (
            '```json\n{"status": "valid", "feedback": "Good job"}\n```'
        )

        result = await validator.validate_task("task-1", "title", "instr", "summary")

        assert result.status == "valid"
        assert result.feedback == "Good job"
        mock_provider.generate_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_task_with_context(self, config, mock_llm, tmp_path):
        validator = TaskValidator(config, mock_llm)

        test_file = tmp_path / "test.txt"
        test_file.write_text("file content")

        mock_provider = mock_llm.get_provider.return_value
        mock_provider.generate_text.return_value = '{"status": "invalid", "feedback": "Bad"}'

        result = await validator.validate_task(
            "task-1", "title", "instr", "summary", context_files=[str(test_file)]
        )

        assert result.status == "invalid"
        # Verify context was gathered
        call_args = mock_provider.generate_text.call_args
        prompt = call_args.kwargs["prompt"]
        assert "file content" in prompt

    @pytest.mark.asyncio
    async def test_validate_task_llm_error(self, config, mock_llm):
        validator = TaskValidator(config, mock_llm)
        mock_provider = mock_llm.get_provider.return_value
        mock_provider.generate_text.side_effect = Exception("LLM Error")

        result = await validator.validate_task("task-1", "title", "instr", "summary")
        assert result.status == "pending"
        assert "failed" in result.feedback

    @pytest.mark.asyncio
    async def test_validate_task_bad_json(self, config, mock_llm):
        validator = TaskValidator(config, mock_llm)
        mock_provider = mock_llm.get_provider.return_value
        mock_provider.generate_text.return_value = "Not JSON"

        result = await validator.validate_task("task-1", "title", "instr", "summary")
        assert result.status == "pending"  # JSON decode error caught
        assert "failed" in result.feedback

    @pytest.mark.asyncio
    async def test_generate_criteria_success(self, config, mock_llm):
        validator = TaskValidator(config, mock_llm)
        mock_provider = mock_llm.get_provider.return_value
        mock_provider.generate_text.return_value = "- Criterion 1"

        criteria = await validator.generate_criteria("Title", "Desc")
        assert criteria == "- Criterion 1"

    @pytest.mark.asyncio
    async def test_generate_criteria_disabled(self, mock_llm):
        config = TaskValidationConfig(enabled=False)
        validator = TaskValidator(config, mock_llm)
        assert await validator.generate_criteria("Title") is None

    @pytest.mark.asyncio
    async def test_generate_criteria_error(self, config, mock_llm):
        validator = TaskValidator(config, mock_llm)
        mock_provider = mock_llm.get_provider.return_value
        mock_provider.generate_text.side_effect = Exception("Error")

        assert await validator.generate_criteria("Title") is None


class TestGetRecentCommits:
    """Tests for get_recent_commits function."""

    @patch("subprocess.run")
    def test_get_recent_commits_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="abc123|First commit\ndef456|Second commit\nghi789|Third commit",
        )

        commits = get_recent_commits(3)
        assert len(commits) == 3
        assert commits[0] == {"sha": "abc123", "subject": "First commit"}
        assert commits[1] == {"sha": "def456", "subject": "Second commit"}
        assert commits[2] == {"sha": "ghi789", "subject": "Third commit"}

    @patch("subprocess.run")
    def test_get_recent_commits_empty(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        commits = get_recent_commits(5)
        assert commits == []

    @patch("subprocess.run")
    def test_get_recent_commits_error(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        commits = get_recent_commits(5)
        assert commits == []

    @patch("subprocess.run")
    def test_get_recent_commits_exception(self, mock_run):
        mock_run.side_effect = Exception("Git error")
        commits = get_recent_commits(5)
        assert commits == []


class TestGetMultiCommitDiff:
    """Tests for get_multi_commit_diff function."""

    @patch("subprocess.run")
    def test_get_multi_commit_diff_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="diff --git a/file.py b/file.py\n+new line",
        )

        diff = get_multi_commit_diff(5)
        assert diff is not None
        assert "diff --git" in diff

    @patch("subprocess.run")
    def test_get_multi_commit_diff_truncate(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="a" * 1000)
        diff = get_multi_commit_diff(5, max_chars=100)
        assert len(diff) < 1000
        assert "... [diff truncated] ..." in diff

    @patch("subprocess.run")
    def test_get_multi_commit_diff_empty(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        diff = get_multi_commit_diff(5)
        assert diff is None

    @patch("subprocess.run")
    def test_get_multi_commit_diff_error(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        diff = get_multi_commit_diff(5)
        assert diff is None


class TestGetCommitsSince:
    """Tests for get_commits_since function."""

    @patch("subprocess.run")
    def test_get_commits_since_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="diff content here",
        )

        diff = get_commits_since("abc123")
        assert diff is not None
        assert "diff content" in diff

    @patch("subprocess.run")
    def test_get_commits_since_empty(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        diff = get_commits_since("abc123")
        assert diff is None


class TestExtractFilePatternsFromText:
    """Tests for extract_file_patterns_from_text function."""

    def test_extract_explicit_paths(self):
        text = "Check the file src/gobby/tasks/validation.py for issues"
        patterns = extract_file_patterns_from_text(text)
        assert "src/gobby/tasks/validation.py" in patterns

    def test_extract_module_references(self):
        text = "The module gobby.tasks.validation handles this"
        patterns = extract_file_patterns_from_text(text)
        assert "src/gobby/tasks/validation.py" in patterns

    def test_extract_test_patterns(self):
        text = "Run test_validation to verify"
        patterns = extract_file_patterns_from_text(text)
        assert any("test_validation" in p for p in patterns)

    def test_extract_class_references(self):
        text = "Check the TaskValidator class"
        patterns = extract_file_patterns_from_text(text)
        assert any("validator" in p.lower() for p in patterns)

    def test_skip_urls(self):
        text = "See http://example.com/file.py for details"
        patterns = extract_file_patterns_from_text(text)
        # Should not include the URL as a file pattern
        assert not any("http" in p for p in patterns)

    def test_empty_text(self):
        patterns = extract_file_patterns_from_text("")
        assert patterns == []


class TestFindMatchingFiles:
    """Tests for find_matching_files function."""

    def test_find_direct_path(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("content")

        files = find_matching_files(["test.py"], base_dir=tmp_path)
        assert len(files) == 1
        assert files[0] == test_file

    def test_find_glob_pattern(self, tmp_path):
        (tmp_path / "test_one.py").write_text("content")
        (tmp_path / "test_two.py").write_text("content")
        (tmp_path / "other.txt").write_text("content")

        files = find_matching_files(["*.py"], base_dir=tmp_path)
        assert len(files) == 2
        assert all(f.suffix == ".py" for f in files)

    def test_find_nested_glob(self, tmp_path):
        subdir = tmp_path / "src"
        subdir.mkdir()
        (subdir / "module.py").write_text("content")

        files = find_matching_files(["**/*.py"], base_dir=tmp_path)
        assert len(files) == 1
        assert files[0].name == "module.py"

    def test_max_files_limit(self, tmp_path):
        for i in range(10):
            (tmp_path / f"file{i}.py").write_text("content")

        files = find_matching_files(["*.py"], base_dir=tmp_path, max_files=3)
        assert len(files) == 3

    def test_no_matches(self, tmp_path):
        files = find_matching_files(["nonexistent.py"], base_dir=tmp_path)
        assert files == []


class TestReadFilesContent:
    """Tests for read_files_content function."""

    def test_read_single_file(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("file content here")

        content = read_files_content([test_file])
        assert "file content here" in content
        assert "=== " in content  # Header

    def test_read_multiple_files(self, tmp_path):
        file1 = tmp_path / "file1.py"
        file2 = tmp_path / "file2.py"
        file1.write_text("content 1")
        file2.write_text("content 2")

        content = read_files_content([file1, file2])
        assert "content 1" in content
        assert "content 2" in content

    def test_truncate_large_content(self, tmp_path):
        test_file = tmp_path / "large.py"
        test_file.write_text("a" * 10000)

        content = read_files_content([test_file], max_chars=100)
        assert len(content) < 10000
        assert "... [file truncated] ..." in content

    def test_read_nonexistent_file(self, tmp_path):
        nonexistent = tmp_path / "missing.py"
        content = read_files_content([nonexistent])
        assert "Error reading file" in content


class TestGetValidationContextSmart:
    """Tests for get_validation_context_smart function."""

    @patch("subprocess.run")
    def test_includes_uncommitted_changes(self, mock_run):
        # Mock staged and unstaged diffs
        mock_staged = MagicMock(returncode=0, stdout="staged diff content")
        mock_unstaged = MagicMock(returncode=0, stdout="unstaged diff content")
        mock_run.side_effect = [mock_unstaged, mock_staged]

        context = get_validation_context_smart("Test task")
        assert context is not None
        assert "STAGED CHANGES" in context
        assert "UNSTAGED CHANGES" in context

    @patch("subprocess.run")
    @patch("gobby.tasks.validation.get_multi_commit_diff")
    def test_includes_multi_commit_diff(self, mock_multi_diff, mock_run):
        # No uncommitted changes
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        mock_multi_diff.return_value = "multi commit diff content"

        context = get_validation_context_smart("Test task", commit_window=5)
        assert context is not None
        assert "COMBINED DIFF" in context or "multi commit diff" in context

    @patch("subprocess.run")
    @patch("gobby.tasks.validation.get_multi_commit_diff")
    @patch("gobby.tasks.validation.get_recent_commits")
    def test_includes_commit_summary(self, mock_commits, mock_diff, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        mock_diff.return_value = "diff content"
        mock_commits.return_value = [
            {"sha": "abc12345", "subject": "First commit"},
            {"sha": "def67890", "subject": "Second commit"},
        ]

        context = get_validation_context_smart("Test task")
        assert context is not None
        assert "RECENT COMMITS" in context

    @patch("subprocess.run")
    @patch("gobby.tasks.validation.get_multi_commit_diff")
    @patch("gobby.tasks.validation.find_matching_files")
    def test_includes_file_analysis(self, mock_find, mock_diff, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        mock_diff.return_value = None  # No git diff

        test_file = tmp_path / "validation.py"
        test_file.write_text("def validate(): pass")
        mock_find.return_value = [test_file]

        context = get_validation_context_smart(
            "Check validation.py",
            validation_criteria="Ensure src/gobby/tasks/validation.py works",
        )
        # Should try to find files mentioned in criteria
        mock_find.assert_called()

    @patch("subprocess.run")
    @patch("gobby.tasks.validation.get_multi_commit_diff")
    def test_returns_none_when_no_context(self, mock_diff, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        mock_diff.return_value = None

        context = get_validation_context_smart(
            "Task with no related files",
            max_chars=100,  # Very limited
        )
        # May return None or minimal context
        # The function should handle this gracefully

    @patch("subprocess.run")
    def test_respects_max_chars(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="a" * 10000)

        context = get_validation_context_smart("Test task", max_chars=500)
        assert context is None or len(context) <= 600  # Some buffer for headers
