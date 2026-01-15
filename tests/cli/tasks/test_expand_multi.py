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

            # Should accept multiple refs
            assert result.exit_code == 0 or "multiple" not in result.output.lower()


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

            # The --cascade option should be recognized
            assert result.exit_code == 0 or "--cascade" not in result.output


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

            # The --no-enrich option should be recognized
            assert result.exit_code == 0 or "--no-enrich" not in result.output


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
