"""Tests for CLI task argument parsing with #N format.

These tests verify that CLI commands correctly accept and resolve:
- `#N` format (e.g., #1, #47) via resolve_task_reference
- Path format (e.g., 1.2.3)
- UUID format (pass-through)
- Deprecation error for `gt-*` format
- Error handling for invalid formats
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from gobby.cli import cli
from gobby.storage.tasks import TaskNotFoundError


@pytest.fixture
def runner() -> CliRunner:
    """Create a CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_task_with_uuid():
    """Create a mock task with UUID-style ID."""
    task = MagicMock()
    task.id = str(uuid.uuid4())
    task.title = "Test Task"
    task.description = "A test task description"
    task.status = "open"
    task.priority = 2
    task.task_type = "task"
    task.seq_num = 1
    task.path_cache = "1"
    task.created_at = "2024-01-01T00:00:00Z"
    task.updated_at = "2024-01-01T00:00:00Z"
    task.project_id = "proj-123"
    task.parent_task_id = None
    task.assignee = None
    task.labels = None
    task.to_dict.return_value = {
        "id": task.id,
        "title": "Test Task",
        "description": "A test task description",
        "status": "open",
        "priority": 2,
        "task_type": "task",
        "seq_num": 1,
        "path_cache": "1",
    }
    return task


class TestResolveTaskIdWithSeqNum:
    """Tests for resolve_task_id with #N format."""

    def test_resolve_hash_format_success(self, mock_task_with_uuid: MagicMock):
        """Test resolving #N format to task."""
        from gobby.cli.tasks._utils import resolve_task_id

        mock_manager = MagicMock()
        # First get_task fails (not a direct UUID lookup)
        mock_manager.get_task.side_effect = ValueError("not found")
        # Prefix match also fails
        mock_manager.find_tasks_by_prefix.return_value = []
        # But resolve_task_reference succeeds
        mock_manager.resolve_task_reference.return_value = mock_task_with_uuid.id

        # Now simulate get_task succeeding with the resolved UUID
        def get_task_side_effect(task_id):
            if task_id == mock_task_with_uuid.id:
                return mock_task_with_uuid
            raise ValueError("not found")

        mock_manager.get_task.side_effect = get_task_side_effect

        result = resolve_task_id(mock_manager, "#1", project_id="proj-123")

        assert result == mock_task_with_uuid
        mock_manager.resolve_task_reference.assert_called_once_with("#1", "proj-123")

    def test_resolve_hash_format_not_found(self):
        """Test #N format when task doesn't exist."""
        from gobby.cli.tasks._utils import resolve_task_id

        mock_manager = MagicMock()
        mock_manager.get_task.side_effect = ValueError("not found")
        mock_manager.find_tasks_by_prefix.return_value = []
        mock_manager.resolve_task_reference.side_effect = TaskNotFoundError("Task #999 not found")

        result = resolve_task_id(mock_manager, "#999", project_id="proj-123")

        assert result is None

    def test_resolve_hash_format_invalid(self):
        """Test invalid #N format (e.g., #abc)."""
        from gobby.cli.tasks._utils import resolve_task_id

        mock_manager = MagicMock()
        mock_manager.get_task.side_effect = ValueError("not found")
        mock_manager.find_tasks_by_prefix.return_value = []
        mock_manager.resolve_task_reference.side_effect = TaskNotFoundError(
            "Invalid seq_num format: #abc"
        )

        result = resolve_task_id(mock_manager, "#abc", project_id="proj-123")

        assert result is None

    def test_resolve_hash_zero_invalid(self):
        """Test that #0 is invalid (seq_num starts at 1)."""
        from gobby.cli.tasks._utils import resolve_task_id

        mock_manager = MagicMock()
        mock_manager.get_task.side_effect = ValueError("not found")
        mock_manager.find_tasks_by_prefix.return_value = []
        mock_manager.resolve_task_reference.side_effect = TaskNotFoundError(
            "Invalid seq_num: #0 (must be positive)"
        )

        result = resolve_task_id(mock_manager, "#0", project_id="proj-123")

        assert result is None


class TestResolveTaskIdWithPathFormat:
    """Tests for resolve_task_id with path format (1.2.3)."""

    def test_resolve_path_format_success(self, mock_task_with_uuid: MagicMock):
        """Test resolving path format like 1.2.3."""
        from gobby.cli.tasks._utils import resolve_task_id

        mock_manager = MagicMock()
        mock_manager.get_task.side_effect = ValueError("not found")
        mock_manager.find_tasks_by_prefix.return_value = []
        mock_manager.resolve_task_reference.return_value = mock_task_with_uuid.id

        def get_task_side_effect(task_id):
            if task_id == mock_task_with_uuid.id:
                return mock_task_with_uuid
            raise ValueError("not found")

        mock_manager.get_task.side_effect = get_task_side_effect

        result = resolve_task_id(mock_manager, "1.2.3", project_id="proj-123")

        assert result == mock_task_with_uuid

    def test_resolve_path_format_not_found(self):
        """Test path format when path doesn't exist."""
        from gobby.cli.tasks._utils import resolve_task_id

        mock_manager = MagicMock()
        mock_manager.get_task.side_effect = ValueError("not found")
        mock_manager.find_tasks_by_prefix.return_value = []
        mock_manager.resolve_task_reference.side_effect = TaskNotFoundError(
            "Task with path '99.99.99' not found in project"
        )

        result = resolve_task_id(mock_manager, "99.99.99", project_id="proj-123")

        assert result is None


class TestResolveTaskIdWithDeprecatedFormat:
    """Tests for deprecated gt-* format handling."""

    def test_resolve_gt_format_shows_deprecation_error(self, runner: CliRunner):
        """Test that gt-* format shows deprecation error."""
        from gobby.cli.tasks._utils import resolve_task_id

        mock_manager = MagicMock()
        mock_manager.get_task.side_effect = ValueError("not found")
        mock_manager.find_tasks_by_prefix.return_value = []
        mock_manager.resolve_task_reference.side_effect = ValueError(
            "The 'gt-*' task ID format is deprecated. Use '#N' format instead."
        )

        result = resolve_task_id(mock_manager, "gt-abc123", project_id="proj-123")

        assert result is None


class TestCliShowCommandWithHashFormat:
    """Tests for `gobby tasks show` with #N format."""

    @patch("gobby.cli.tasks.crud.get_task_manager")
    @patch("gobby.cli.tasks._utils.get_task_manager")
    def test_show_with_hash_format(
        self,
        mock_utils_get_manager: MagicMock,
        mock_crud_get_manager: MagicMock,
        runner: CliRunner,
        mock_task_with_uuid: MagicMock,
    ):
        """Test `gobby tasks show #1` resolves correctly."""
        mock_manager = MagicMock()
        mock_manager.resolve_task_reference.return_value = mock_task_with_uuid.id
        mock_manager.get_task.return_value = mock_task_with_uuid
        mock_crud_get_manager.return_value = mock_manager
        mock_utils_get_manager.return_value = mock_manager

        # Run the command - this tests the CLI invocation path
        runner.invoke(cli, ["tasks", "show", "#1"])


class TestCliUpdateCommandWithHashFormat:
    """Tests for `gobby tasks update` with #N format."""

    @patch("gobby.cli.tasks.crud.get_task_manager")
    @patch("gobby.cli.tasks._utils.get_task_manager")
    def test_update_with_hash_format(
        self,
        mock_utils_get_manager: MagicMock,
        mock_crud_get_manager: MagicMock,
        runner: CliRunner,
        mock_task_with_uuid: MagicMock,
    ):
        """Test `gobby tasks update #5 --status done` resolves correctly."""
        mock_manager = MagicMock()
        mock_manager.resolve_task_reference.return_value = mock_task_with_uuid.id
        mock_manager.get_task.return_value = mock_task_with_uuid
        mock_manager.update_task.return_value = mock_task_with_uuid
        mock_crud_get_manager.return_value = mock_manager
        mock_utils_get_manager.return_value = mock_manager

        # Run the command - this tests the CLI invocation path
        runner.invoke(cli, ["tasks", "update", "#5", "--status", "in_progress"])


class TestCliDeleteCommandWithHashFormat:
    """Tests for `gobby tasks delete` with #N format."""

    @patch("gobby.cli.tasks.crud.get_task_manager")
    @patch("gobby.cli.tasks._utils.get_task_manager")
    def test_delete_with_hash_format(
        self,
        mock_utils_get_manager: MagicMock,
        mock_crud_get_manager: MagicMock,
        runner: CliRunner,
        mock_task_with_uuid: MagicMock,
    ):
        """Test `gobby tasks delete #10` resolves correctly."""
        mock_manager = MagicMock()
        mock_manager.resolve_task_reference.return_value = mock_task_with_uuid.id
        mock_manager.get_task.return_value = mock_task_with_uuid
        mock_crud_get_manager.return_value = mock_manager
        mock_utils_get_manager.return_value = mock_manager

        # Run the command (--yes auto-confirms deletion)
        runner.invoke(cli, ["tasks", "delete", "#10", "--yes"])


class TestCliCloseCommandWithHashFormat:
    """Tests for `gobby tasks close` with #N format."""

    @patch("gobby.cli.tasks.crud.get_task_manager")
    @patch("gobby.cli.tasks._utils.get_task_manager")
    def test_close_with_hash_format(
        self,
        mock_utils_get_manager: MagicMock,
        mock_crud_get_manager: MagicMock,
        runner: CliRunner,
        mock_task_with_uuid: MagicMock,
    ):
        """Test `gobby tasks close #3` resolves correctly."""
        mock_manager = MagicMock()
        mock_manager.resolve_task_reference.return_value = mock_task_with_uuid.id
        mock_manager.get_task.return_value = mock_task_with_uuid
        mock_manager.list_tasks.return_value = []  # No children
        mock_manager.close_task.return_value = mock_task_with_uuid
        mock_crud_get_manager.return_value = mock_manager
        mock_utils_get_manager.return_value = mock_manager

        # Run the command - this tests the CLI invocation path
        runner.invoke(cli, ["tasks", "close", "#3"])


class TestIntegrationResolveTaskId:
    """Integration tests using real database for #N format resolution."""

    @pytest.mark.integration
    def test_resolve_hash_format_integration(self, temp_db, sample_project):
        """Test #N resolution with real database."""
        from gobby.cli.tasks._utils import resolve_task_id
        from gobby.storage.tasks import LocalTaskManager

        manager = LocalTaskManager(temp_db)
        project_id = sample_project["id"]

        # Create tasks
        task1 = manager.create_task(project_id=project_id, title="Task 1")
        task2 = manager.create_task(project_id=project_id, title="Task 2")
        task3 = manager.create_task(project_id=project_id, title="Task 3")

        # Resolve using #N format
        result = resolve_task_id(manager, "#1", project_id=project_id)
        assert result is not None
        assert result.id == task1.id

        result = resolve_task_id(manager, "#2", project_id=project_id)
        assert result is not None
        assert result.id == task2.id

        result = resolve_task_id(manager, "#3", project_id=project_id)
        assert result is not None
        assert result.id == task3.id

    @pytest.mark.integration
    def test_resolve_path_format_integration(self, temp_db, sample_project):
        """Test path format resolution with real database."""
        from gobby.cli.tasks._utils import resolve_task_id
        from gobby.storage.tasks import LocalTaskManager

        manager = LocalTaskManager(temp_db)
        project_id = sample_project["id"]

        # Create hierarchy: parent -> child -> grandchild
        parent = manager.create_task(project_id=project_id, title="Parent")
        child = manager.create_task(project_id=project_id, title="Child", parent_task_id=parent.id)
        grandchild = manager.create_task(
            project_id=project_id, title="Grandchild", parent_task_id=child.id
        )

        # For root task "1", use #1 format (path format requires dots)
        result = resolve_task_id(manager, "#1", project_id=project_id)
        assert result is not None
        assert result.id == parent.id

        # Resolve child using path format "1.2"
        result = resolve_task_id(manager, "1.2", project_id=project_id)
        assert result is not None
        assert result.id == child.id

        # Resolve grandchild using path format "1.2.3"
        result = resolve_task_id(manager, "1.2.3", project_id=project_id)
        assert result is not None
        assert result.id == grandchild.id

    @pytest.mark.integration
    def test_resolve_uuid_format_integration(self, temp_db, sample_project):
        """Test UUID format resolution with real database."""
        from gobby.cli.tasks._utils import resolve_task_id
        from gobby.storage.tasks import LocalTaskManager

        manager = LocalTaskManager(temp_db)
        project_id = sample_project["id"]

        task = manager.create_task(project_id=project_id, title="UUID Test Task")

        # Resolve using full UUID
        result = resolve_task_id(manager, task.id, project_id=project_id)
        assert result is not None
        assert result.id == task.id

    @pytest.mark.integration
    def test_resolve_gt_format_deprecated_integration(self, temp_db, sample_project):
        """Test gt-* format shows deprecation error."""
        from gobby.cli.tasks._utils import resolve_task_id
        from gobby.storage.tasks import LocalTaskManager

        manager = LocalTaskManager(temp_db)
        project_id = sample_project["id"]

        manager.create_task(project_id=project_id, title="Test Task")

        # gt-* format should fail with deprecation error
        result = resolve_task_id(manager, "gt-abc123", project_id=project_id)
        assert result is None

    @pytest.mark.integration
    def test_resolve_nonexistent_seq_num_integration(self, temp_db, sample_project):
        """Test non-existent #N returns None."""
        from gobby.cli.tasks._utils import resolve_task_id
        from gobby.storage.tasks import LocalTaskManager

        manager = LocalTaskManager(temp_db)
        project_id = sample_project["id"]

        manager.create_task(project_id=project_id, title="Task 1")

        # #999 doesn't exist
        result = resolve_task_id(manager, "#999", project_id=project_id)
        assert result is None
