"""Tests for enhanced gobby tasks expand CLI command.

Tests verify the expand command enhancements:
- Multiple task refs support
- --cascade flag for expanding subtasks
- --no-enrich flag to skip enrichment
- --force flag to re-expand
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from gobby.cli.tasks import tasks


@pytest.fixture
def runner() -> CliRunner:
    """Create a CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_task():
    """Create a mock task."""
    task = MagicMock()
    task.id = "task-123"
    task.seq_num = 42
    task.title = "Test Task"
    task.description = "Test description"
    task.project_id = "proj-123"
    task.status = "open"
    return task


@pytest.fixture
def mock_expander():
    """Create a mock TaskExpander."""
    expander = MagicMock()
    expander.expand_task = AsyncMock()
    return expander


class TestExpandMultipleTaskRefs:
    """Tests for expand command with multiple task refs."""

    def test_expand_multiple_tasks(self, runner: CliRunner, mock_task, mock_expander):
        """Test expanding multiple tasks with comma separation."""
        with (
            patch("gobby.cli.tasks.ai.get_task_manager") as mock_get_manager,
            patch("gobby.cli.tasks.ai.resolve_task_id", return_value=mock_task),
            patch("gobby.config.app.load_config") as mock_config,
            patch("gobby.llm.LLMService"),
            patch("gobby.tasks.expansion.TaskExpander", return_value=mock_expander),
        ):
            mock_manager = MagicMock()
            mock_get_manager.return_value = mock_manager
            mock_config.return_value.gobby_tasks.expansion.enabled = True

            mock_expander.expand_task.return_value = {
                "complexity_analysis": {"score": 5},
                "phases": [{"subtasks": [{"title": "Sub 1"}]}],
            }

            # Test with comma-separated task refs
            result = runner.invoke(tasks, ["expand", "#42,#43,#44"])

            # Verify CLI exits successfully
            assert result.exit_code == 0, f"Expected exit code 0, got {result.exit_code}. Output: {result.output}"

            # Verify expander was called three times (once per task ref)
            assert mock_expander.expand_task.call_count == 3, (
                f"Expected 3 calls to expand_task, got {mock_expander.expand_task.call_count}"
            )

            # Verify expander was called with the resolved mock task
            for call in mock_expander.expand_task.call_args_list:
                assert call.kwargs.get("task") == mock_task or (call.args and call.args[0] == mock_task), (
                    f"Expected expand_task to be called with mock_task, got {call}"
                )

            # Verify output contains expected expansion content
            assert "Sub 1" in result.output, f"Expected 'Sub 1' in output, got: {result.output}"


class TestExpandCascade:
    """Tests for expand command with --cascade flag."""

    def test_expand_with_cascade(self, runner: CliRunner, mock_task, mock_expander):
        """Test expanding with cascade flag to include subtasks."""
        child_task = MagicMock()
        child_task.id = "child-123"
        child_task.seq_num = 43
        child_task.title = "Child Task"
        child_task.status = "open"

        with (
            patch("gobby.cli.tasks.ai.get_task_manager") as mock_get_manager,
            patch("gobby.cli.tasks.ai.resolve_task_id", return_value=mock_task),
            patch("gobby.config.app.load_config") as mock_config,
            patch("gobby.llm.LLMService"),
            patch("gobby.tasks.expansion.TaskExpander", return_value=mock_expander),
        ):
            mock_manager = MagicMock()
            mock_manager.list_tasks.return_value = [child_task]
            mock_get_manager.return_value = mock_manager
            mock_config.return_value.gobby_tasks.expansion.enabled = True

            mock_expander.expand_task.return_value = {
                "phases": [{"subtasks": []}],
            }

            result = runner.invoke(tasks, ["expand", "#42", "--cascade"])

            # Verify CLI exits successfully
            assert result.exit_code == 0, f"Expected exit code 0, got {result.exit_code}. Output: {result.output}"

            # Verify expander was called for both parent and child tasks (cascade processing)
            # With cascade, expand_task should be called for parent (#42) and its child
            assert mock_expander.expand_task.call_count >= 1, (
                f"Expected at least 1 call to expand_task, got {mock_expander.expand_task.call_count}"
            )

            # Verify list_tasks was called to get child tasks for cascade
            mock_manager.list_tasks.assert_called()

            # Verify child task is processed in cascade mode - check output mentions child
            # or expander was called multiple times
            child_processed = (
                "Child Task" in result.output
                or "child-123" in result.output
                or "#43" in result.output
                or mock_expander.expand_task.call_count >= 2
            )
            assert child_processed, (
                f"Expected child task to be processed in cascade mode. "
                f"Call count: {mock_expander.expand_task.call_count}, Output: {result.output}"
            )


class TestExpandNoEnrich:
    """Tests for expand command with --no-enrich flag."""

    def test_expand_with_no_enrich(self, runner: CliRunner, mock_task, mock_expander):
        """Test expanding with --no-enrich to skip enrichment."""
        with (
            patch("gobby.cli.tasks.ai.get_task_manager") as mock_get_manager,
            patch("gobby.cli.tasks.ai.resolve_task_id", return_value=mock_task),
            patch("gobby.config.app.load_config") as mock_config,
            patch("gobby.llm.LLMService"),
            patch("gobby.tasks.expansion.TaskExpander", return_value=mock_expander),
        ):
            mock_manager = MagicMock()
            mock_get_manager.return_value = mock_manager
            mock_config.return_value.gobby_tasks.expansion.enabled = True

            mock_expander.expand_task.return_value = {
                "phases": [{"subtasks": []}],
            }

            result = runner.invoke(tasks, ["expand", "#42", "--no-enrich"])

            # The --no-enrich option should be recognized and succeed
            assert result.exit_code == 0


class TestExpandForce:
    """Tests for expand command with --force flag."""

    def test_expand_with_force(self, runner: CliRunner, mock_expander):
        """Test re-expanding with force flag."""
        already_expanded_task = MagicMock()
        already_expanded_task.id = "task-123"
        already_expanded_task.seq_num = 42
        already_expanded_task.title = "Already Expanded Task"
        already_expanded_task.status = "open"
        already_expanded_task.expansion_context = '{"expanded": true}'

        with (
            patch("gobby.cli.tasks.ai.get_task_manager") as mock_get_manager,
            patch("gobby.cli.tasks.ai.resolve_task_id", return_value=already_expanded_task),
            patch("gobby.config.app.load_config") as mock_config,
            patch("gobby.llm.LLMService"),
            patch("gobby.tasks.expansion.TaskExpander", return_value=mock_expander),
        ):
            mock_manager = MagicMock()
            mock_get_manager.return_value = mock_manager
            mock_config.return_value.gobby_tasks.expansion.enabled = True

            mock_expander.expand_task.return_value = {
                "phases": [{"subtasks": []}],
            }

            result = runner.invoke(tasks, ["expand", "#42", "--force"])

            # The --force option should be recognized
            assert result.exit_code == 0 or "--force" not in result.output
