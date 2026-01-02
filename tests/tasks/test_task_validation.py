import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from gobby.tasks.validation import TaskValidator, ValidationResult, get_git_diff
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
        )  # Missing criteria and instruction
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
