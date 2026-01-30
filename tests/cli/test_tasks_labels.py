"""Tests for task label CLI commands.

Tests cover:
- Adding labels to tasks
- Removing labels from tasks
- Error handling for task not found
- Error handling for ValueError exceptions
- Error handling for unexpected exceptions
"""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from gobby.cli import cli

pytestmark = pytest.mark.unit

@pytest.fixture
def runner() -> CliRunner:
    """Create a CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_task():
    """Create a mock task with common attributes."""
    task = MagicMock()
    task.id = "gt-abc123"
    task.seq_num = 1
    task.title = "Test Task"
    return task


class TestAddLabel:
    """Tests for gobby tasks label add command."""

    @patch("gobby.cli.tasks.labels.get_task_manager")
    @patch("gobby.cli.tasks.labels.resolve_task_id")
    def test_add_label_success(
        self,
        mock_resolve: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ) -> None:
        """Test successfully adding a label to a task."""
        mock_manager = MagicMock()
        mock_get_manager.return_value = mock_manager
        mock_resolve.return_value = mock_task

        result = runner.invoke(cli, ["tasks", "label", "add", "#1", "urgent"])

        assert result.exit_code == 0
        assert "Added label 'urgent'" in result.output
        mock_manager.add_label.assert_called_once_with("gt-abc123", "urgent")

    @patch("gobby.cli.tasks.labels.get_task_manager")
    @patch("gobby.cli.tasks.labels.resolve_task_id")
    def test_add_label_task_not_found(
        self,
        mock_resolve: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
    ) -> None:
        """Test adding label when task is not found."""
        mock_manager = MagicMock()
        mock_get_manager.return_value = mock_manager
        mock_resolve.return_value = None

        result = runner.invoke(cli, ["tasks", "label", "add", "#999", "urgent"])

        assert result.exit_code == 1
        assert "Could not resolve task '#999'" in result.output
        mock_manager.add_label.assert_not_called()

    @patch("gobby.cli.tasks.labels.get_task_manager")
    @patch("gobby.cli.tasks.labels.resolve_task_id")
    def test_add_label_value_error(
        self,
        mock_resolve: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ) -> None:
        """Test adding label when ValueError is raised."""
        mock_manager = MagicMock()
        mock_manager.add_label.side_effect = ValueError("Label already exists")
        mock_get_manager.return_value = mock_manager
        mock_resolve.return_value = mock_task

        result = runner.invoke(cli, ["tasks", "label", "add", "#1", "urgent"])

        assert result.exit_code == 1
        assert "Error: Label already exists" in result.output

    @patch("gobby.cli.tasks.labels.get_task_manager")
    @patch("gobby.cli.tasks.labels.resolve_task_id")
    def test_add_label_unexpected_error(
        self,
        mock_resolve: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ) -> None:
        """Test adding label when unexpected exception is raised."""
        mock_manager = MagicMock()
        mock_manager.add_label.side_effect = RuntimeError("Database error")
        mock_get_manager.return_value = mock_manager
        mock_resolve.return_value = mock_task

        result = runner.invoke(cli, ["tasks", "label", "add", "#1", "urgent"])

        assert result.exit_code == 1
        assert "Unexpected error adding label" in result.output


class TestRemoveLabel:
    """Tests for gobby tasks label remove command."""

    @patch("gobby.cli.tasks.labels.get_task_manager")
    @patch("gobby.cli.tasks.labels.resolve_task_id")
    def test_remove_label_success(
        self,
        mock_resolve: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ) -> None:
        """Test successfully removing a label from a task."""
        mock_manager = MagicMock()
        mock_get_manager.return_value = mock_manager
        mock_resolve.return_value = mock_task

        result = runner.invoke(cli, ["tasks", "label", "remove", "#1", "urgent"])

        assert result.exit_code == 0
        assert "Removed label 'urgent'" in result.output
        mock_manager.remove_label.assert_called_once_with("gt-abc123", "urgent")

    @patch("gobby.cli.tasks.labels.get_task_manager")
    @patch("gobby.cli.tasks.labels.resolve_task_id")
    def test_remove_label_task_not_found(
        self,
        mock_resolve: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
    ) -> None:
        """Test removing label when task is not found."""
        mock_manager = MagicMock()
        mock_get_manager.return_value = mock_manager
        mock_resolve.return_value = None

        result = runner.invoke(cli, ["tasks", "label", "remove", "#999", "urgent"])

        assert result.exit_code == 1
        assert "Could not resolve task '#999'" in result.output
        mock_manager.remove_label.assert_not_called()

    @patch("gobby.cli.tasks.labels.get_task_manager")
    @patch("gobby.cli.tasks.labels.resolve_task_id")
    def test_remove_label_value_error(
        self,
        mock_resolve: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ) -> None:
        """Test removing label when ValueError is raised."""
        mock_manager = MagicMock()
        mock_manager.remove_label.side_effect = ValueError("Label not found")
        mock_get_manager.return_value = mock_manager
        mock_resolve.return_value = mock_task

        result = runner.invoke(cli, ["tasks", "label", "remove", "#1", "urgent"])

        assert result.exit_code == 1
        assert "Error: Label not found" in result.output

    @patch("gobby.cli.tasks.labels.get_task_manager")
    @patch("gobby.cli.tasks.labels.resolve_task_id")
    def test_remove_label_unexpected_error(
        self,
        mock_resolve: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ) -> None:
        """Test removing label when unexpected exception is raised."""
        mock_manager = MagicMock()
        mock_manager.remove_label.side_effect = RuntimeError("Database error")
        mock_get_manager.return_value = mock_manager
        mock_resolve.return_value = mock_task

        result = runner.invoke(cli, ["tasks", "label", "remove", "#1", "urgent"])

        assert result.exit_code == 1
        assert "Unexpected error removing label" in result.output
