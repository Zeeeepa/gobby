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
    task.is_expanded = False
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
            patch("gobby.cli.utils.get_active_session_id", return_value="sess-123"),
        ):
            mock_manager = MagicMock()
            mock_get_manager.return_value = mock_manager
            mock_config.return_value.gobby_tasks.expansion.enabled = True

            mock_expander.expand_task.return_value = {
                "complexity_analysis": {"score": 5},
                "phases": [{"subtasks": [{"title": "Sub 1"}]}],
                "subtask_ids": ["sub-1"],
            }

            # Test with comma-separated task refs
            result = runner.invoke(tasks, ["expand", "#42,#43,#44"])

            # Verify CLI exits successfully
            assert result.exit_code == 0, (
                f"Expected exit code 0, got {result.exit_code}. Output: {result.output}"
            )

            # Verify expander was called three times (once per task ref)
            assert mock_expander.expand_task.call_count == 3, (
                f"Expected 3 calls to expand_task, got {mock_expander.expand_task.call_count}"
            )

            # Verify expander was called with the resolved mock task
            # Verify expander was called with the resolved task ID
            for call in mock_expander.expand_task.call_args_list:
                assert call.kwargs.get("task_id") == "task-123", (
                    f"Expected expand_task to be called with task_id='task-123', got {call}"
                )

            # Verify output contains expected expansion content
            # Verify output contains expected expansion content
            assert "Created 1 subtasks" in result.output, (
                f"Expected 'Created 1 subtasks' in output, got: {result.output}"
            )


class TestExpandCascade:
    """Tests for expand command with --cascade flag."""

    def test_expand_with_cascade(self, runner: CliRunner, mock_task, mock_expander):
        """Test expanding with cascade flag to include subtasks."""
        child_task = MagicMock()
        child_task.id = "child-123"
        child_task.seq_num = 43
        child_task.title = "Child Task"
        child_task.status = "open"
        child_task.is_expanded = False
        child_task.task_type = "epic"

        mock_task.task_type = "epic"
        mock_task.is_expanded = False

        # Dynamic get_task to behave like DB
        def get_task_side_effect(task_id):
            if task_id == mock_task.id:
                return mock_task
            if task_id == child_task.id:
                return child_task
            return None

        # Dynamic list_tasks to reflect hierarchy
        def list_tasks_side_effect(**kwargs):
            parent = kwargs.get("parent_task_id")
            if parent == mock_task.id:
                return [child_task]
            return []

        # Side effect to update task state on expansion
        async def expand_side_effect(*args, **kwargs):
            t_id = kwargs.get("task_id")
            if t_id == mock_task.id:
                mock_task.is_expanded = True
            elif t_id == child_task.id:
                child_task.is_expanded = True
            return {
                "phases": [{"subtasks": []}],
                "subtask_ids": ["sub-1"],
            }

        with (
            patch("gobby.cli.tasks.ai.get_task_manager") as mock_get_manager,
            patch("gobby.cli.tasks.ai.resolve_task_id", return_value=mock_task),
            patch("gobby.config.app.load_config") as mock_config,
            patch("gobby.llm.LLMService"),
            patch("gobby.tasks.expansion.TaskExpander", return_value=mock_expander),
            patch("gobby.cli.utils.get_active_session_id", return_value="sess-123"),
        ):
            mock_manager = MagicMock()
            mock_manager.get_task.side_effect = get_task_side_effect
            mock_manager.list_tasks.side_effect = list_tasks_side_effect
            mock_get_manager.return_value = mock_manager
            mock_config.return_value.gobby_tasks.expansion.enabled = True

            mock_expander.expand_task.side_effect = expand_side_effect

            result = runner.invoke(tasks, ["expand", "#42", "--cascade"])

            # Verify CLI exits successfully
            assert result.exit_code == 0, (
                f"Expected exit code 0, got {result.exit_code}. Output: {result.output}"
            )

            # Verify expander was called for both parent and child tasks
            # Logic:
            # 1. Finds root (unexpanded). Expands root. Sets root.is_expanded=True.
            # 2. Finds root (expanded). Checks children. Finds child (unexpanded). Expands child. Sets child.is_expanded=True.
            # 3. Finds root (expanded). Checks children. Finds child (expanded). Returns None. Breaks.
            assert mock_expander.expand_task.call_count == 2, (
                f"Expected 2 calls to expand_task (parent + child), got {mock_expander.expand_task.call_count}"
            )

            # Verify expand_task was called for child task
            child_expanded = any(
                call.kwargs.get("task_id") == "child-123"
                for call in mock_expander.expand_task.call_args_list
            )
            assert child_expanded, "Expected expand_task to be called for child-123"


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
            patch("gobby.cli.utils.get_active_session_id", return_value="sess-123"),
        ):
            mock_manager = MagicMock()
            mock_get_manager.return_value = mock_manager
            mock_config.return_value.gobby_tasks.expansion.enabled = True

            mock_expander.expand_task.return_value = {
                "phases": [{"subtasks": []}],
                "subtask_ids": ["sub-1"],
            }

            result = runner.invoke(tasks, ["expand", "#42", "--force"])

            # The --force option should be recognized and command should succeed
            assert result.exit_code == 0, f"Command failed: {result.output}"
            # Verify no unknown option error for --force
            assert "Error: No such option" not in result.output
