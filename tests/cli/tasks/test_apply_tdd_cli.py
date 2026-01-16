"""Tests for gobby tasks apply-tdd CLI command.

Tests verify the apply-tdd command for transforming tasks into TDD triplets:
- Single task transformation
- Multiple task refs
- --cascade flag for applying to subtasks
- --force flag to reapply
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
    task.title = "Implement feature"
    task.description = "Implement the feature"
    task.project_id = "proj-123"
    task.task_type = "task"
    return task


class TestApplyTddCommand:
    """Tests for the apply-tdd CLI command."""

    def test_apply_tdd_command_exists(self, runner: CliRunner):
        """Test that apply-tdd command is registered."""
        result = runner.invoke(tasks, ["apply-tdd", "--help"])
        assert result.exit_code == 0
        assert "tdd" in result.output.lower() or "triplet" in result.output.lower()

    def test_apply_tdd_single_task(self, runner: CliRunner, mock_task):
        """Test applying TDD to a single task."""
        with (
            patch("gobby.cli.tasks.ai.get_task_manager") as mock_get_manager,
            patch("gobby.cli.tasks.ai.resolve_task_id", return_value=mock_task),
        ):
            mock_manager = MagicMock()
            mock_get_manager.return_value = mock_manager
            mock_manager.create_task.return_value = mock_task

            result = runner.invoke(tasks, ["apply-tdd", "#42"])

            assert result.exit_code == 0

    def test_apply_tdd_multiple_tasks(self, runner: CliRunner, mock_task):
        """Test applying TDD to multiple tasks."""
        with (
            patch("gobby.cli.tasks.ai.get_task_manager") as mock_get_manager,
            patch("gobby.cli.tasks.ai.resolve_task_id", return_value=mock_task),
        ):
            mock_manager = MagicMock()
            mock_get_manager.return_value = mock_manager
            mock_manager.create_task.return_value = mock_task

            result = runner.invoke(tasks, ["apply-tdd", "#42,#43"])

            assert result.exit_code == 0

    def test_apply_tdd_with_cascade(self, runner: CliRunner, mock_task):
        """Test applying TDD with cascade to include subtasks."""
        child_task = MagicMock()
        child_task.id = "child-123"
        child_task.seq_num = 43
        child_task.title = "Child task"
        child_task.task_type = "task"

        with (
            patch("gobby.cli.tasks.ai.get_task_manager") as mock_get_manager,
            patch("gobby.cli.tasks.ai.resolve_task_id", return_value=mock_task),
        ):
            mock_manager = MagicMock()
            # Return child_task only for the parent, empty list for child to prevent recursion
            mock_manager.list_tasks.side_effect = (
                lambda parent_task_id=None, **kwargs: [child_task]
                if parent_task_id == mock_task.id
                else []
            )
            mock_manager.create_task.return_value = mock_task
            mock_get_manager.return_value = mock_manager

            result = runner.invoke(tasks, ["apply-tdd", "#42", "--cascade"])

            assert result.exit_code == 0, f"--cascade flag should be recognized: {result.output}"

    def test_apply_tdd_with_force(self, runner: CliRunner, mock_task):
        """Test reapplying TDD with force flag."""
        with (
            patch("gobby.cli.tasks.ai.get_task_manager") as mock_get_manager,
            patch("gobby.cli.tasks.ai.resolve_task_id", return_value=mock_task),
        ):
            mock_manager = MagicMock()
            mock_manager.create_task.return_value = mock_task
            mock_get_manager.return_value = mock_manager

            result = runner.invoke(tasks, ["apply-tdd", "#42", "--force"])

            assert result.exit_code == 0, f"Command failed: {result.output}"
            # Verify the command executed (either created TDD tasks or reported skip)
            assert (
                "created" in result.output.lower()
                or "skipped" in result.output.lower()
                or "applied" in result.output.lower()
            ), f"--force flag should produce output: {result.output}"


class TestApplyTddErrors:
    """Tests for error handling in apply-tdd command."""

    def test_apply_tdd_task_not_found(self, runner: CliRunner):
        """Test error when task is not found."""
        with (
            patch("gobby.cli.tasks.ai.get_task_manager") as mock_get_manager,
            patch("gobby.cli.tasks.ai.resolve_task_id", return_value=None),
        ):
            mock_manager = MagicMock()
            mock_get_manager.return_value = mock_manager

            result = runner.invoke(tasks, ["apply-tdd", "#999"])

            assert "no valid" in result.output.lower() or result.exit_code != 0
