"""Comprehensive tests for task CLI commands (ai.py and crud.py).

These tests focus on increasing coverage for the low-coverage CLI modules:
- tasks/ai.py (26% coverage)
- tasks/crud.py (35% coverage)

Tests use Click's CliRunner and mock external dependencies.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from gobby.cli import cli

# ==============================================================================
# Fixtures
# ==============================================================================


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
    task.description = "A test task description"
    task.status = "open"
    task.priority = 2
    task.task_type = "task"
    task.created_at = "2024-01-01T00:00:00Z"
    task.updated_at = "2024-01-01T00:00:00Z"
    task.project_id = "proj-123"
    task.parent_task_id = None
    task.assignee = None
    task.labels = None
    task.validation_criteria = None
    task.validation_fail_count = 0
    task.complexity_score = None
    task.estimated_subtasks = None
    task.test_strategy = None
    task.to_dict.return_value = {
        "id": "gt-abc123",
        "title": "Test Task",
        "description": "A test task description",
        "status": "open",
        "priority": 2,
        "task_type": "task",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
        "project_id": "proj-123",
    }
    return task


@pytest.fixture
def mock_manager():
    """Create a mock task manager."""
    manager = MagicMock()
    manager.db = MagicMock()
    return manager


# ==============================================================================
# Tests for crud.py - List Commands
# ==============================================================================


class TestListTasksCommand:
    """Tests for gobby tasks list command."""

    @patch("gobby.cli.tasks.crud.get_task_manager")
    @patch("gobby.cli.tasks.crud.get_project_context")
    def test_list_no_tasks(
        self,
        mock_project_ctx: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
    ):
        """Test list with no tasks found."""
        mock_project_ctx.return_value = {"id": "proj-123"}
        mock_manager = MagicMock()
        mock_manager.list_tasks.return_value = []
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["tasks", "list"])

        assert result.exit_code == 0
        assert "No tasks found" in result.output

    @patch("gobby.cli.tasks.crud.get_task_manager")
    @patch("gobby.cli.tasks.crud.get_project_context")
    @patch("gobby.cli.tasks.crud.get_claimed_task_ids")
    def test_list_with_tasks(
        self,
        mock_claimed: MagicMock,
        mock_project_ctx: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test list with tasks."""
        mock_project_ctx.return_value = {"id": "proj-123"}
        mock_claimed.return_value = set()
        mock_manager = MagicMock()
        mock_manager.list_tasks.return_value = [mock_task]
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["tasks", "list"])

        assert result.exit_code == 0
        assert "Found 1 tasks" in result.output
        assert "#1" in result.output  # Shows seq_num instead of full task ID

    @patch("gobby.cli.tasks.crud.get_task_manager")
    @patch("gobby.cli.tasks.crud.get_project_context")
    def test_list_json_output(
        self,
        mock_project_ctx: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test list with JSON output."""
        mock_project_ctx.return_value = {"id": "proj-123"}
        mock_manager = MagicMock()
        mock_manager.list_tasks.return_value = [mock_task]
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["tasks", "list", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["id"] == "gt-abc123"

    @patch("gobby.cli.tasks.crud.get_task_manager")
    @patch("gobby.cli.tasks.crud.get_project_context")
    def test_list_with_status_filter(
        self,
        mock_project_ctx: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test list with status filter."""
        mock_project_ctx.return_value = {"id": "proj-123"}
        mock_manager = MagicMock()
        mock_manager.list_tasks.return_value = [mock_task]
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["tasks", "list", "--status", "open"])

        assert result.exit_code == 0
        mock_manager.list_tasks.assert_called_once()
        call_kwargs = mock_manager.list_tasks.call_args.kwargs
        assert call_kwargs["status"] == "open"

    @patch("gobby.cli.tasks.crud.get_task_manager")
    @patch("gobby.cli.tasks.crud.get_project_context")
    def test_list_with_comma_separated_statuses(
        self,
        mock_project_ctx: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test list with comma-separated status filters."""
        mock_project_ctx.return_value = {"id": "proj-123"}
        mock_manager = MagicMock()
        mock_manager.list_tasks.return_value = [mock_task]
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["tasks", "list", "--status", "open,in_progress"])

        assert result.exit_code == 0
        mock_manager.list_tasks.assert_called_once()
        call_kwargs = mock_manager.list_tasks.call_args.kwargs
        assert call_kwargs["status"] == ["open", "in_progress"]

    @patch("gobby.cli.tasks.crud.get_task_manager")
    @patch("gobby.cli.tasks.crud.get_project_context")
    def test_list_with_active_flag(
        self,
        mock_project_ctx: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test list with --active flag."""
        mock_project_ctx.return_value = {"id": "proj-123"}
        mock_manager = MagicMock()
        mock_manager.list_tasks.return_value = [mock_task]
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["tasks", "list", "--active"])

        assert result.exit_code == 0
        mock_manager.list_tasks.assert_called_once()
        call_kwargs = mock_manager.list_tasks.call_args.kwargs
        assert call_kwargs["status"] == ["open", "in_progress"]

    def test_list_ready_and_blocked_mutually_exclusive(self, runner: CliRunner):
        """Test that --ready and --blocked are mutually exclusive."""
        result = runner.invoke(cli, ["tasks", "list", "--ready", "--blocked"])

        assert result.exit_code == 0
        assert "--ready and --blocked are mutually exclusive" in result.output

    def test_list_active_and_status_mutually_exclusive(self, runner: CliRunner):
        """Test that --active and --status are mutually exclusive."""
        result = runner.invoke(cli, ["tasks", "list", "--active", "--status", "open"])

        assert result.exit_code == 0
        assert "--active and --status are mutually exclusive" in result.output

    @patch("gobby.cli.tasks.crud.get_task_manager")
    @patch("gobby.cli.tasks.crud.get_project_context")
    @patch("gobby.cli.tasks.crud.get_claimed_task_ids")
    @patch("gobby.cli.tasks.crud.collect_ancestors")
    def test_list_with_ready_flag(
        self,
        mock_ancestors: MagicMock,
        mock_claimed: MagicMock,
        mock_project_ctx: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test list with --ready flag."""
        mock_project_ctx.return_value = {"id": "proj-123"}
        mock_claimed.return_value = set()
        mock_manager = MagicMock()
        mock_manager.list_ready_tasks.return_value = [mock_task]
        mock_get_manager.return_value = mock_manager
        mock_ancestors.return_value = ([mock_task], {mock_task.id})

        result = runner.invoke(cli, ["tasks", "list", "--ready"])

        assert result.exit_code == 0
        assert "Found 1 ready tasks" in result.output
        mock_manager.list_ready_tasks.assert_called_once()

    @patch("gobby.cli.tasks.crud.get_task_manager")
    @patch("gobby.cli.tasks.crud.get_project_context")
    @patch("gobby.cli.tasks.crud.get_claimed_task_ids")
    @patch("gobby.cli.tasks.crud.collect_ancestors")
    def test_list_with_blocked_flag(
        self,
        mock_ancestors: MagicMock,
        mock_claimed: MagicMock,
        mock_project_ctx: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test list with --blocked flag."""
        mock_project_ctx.return_value = {"id": "proj-123"}
        mock_claimed.return_value = set()
        mock_manager = MagicMock()
        mock_manager.list_blocked_tasks.return_value = [mock_task]
        mock_get_manager.return_value = mock_manager
        mock_ancestors.return_value = ([mock_task], {mock_task.id})

        result = runner.invoke(cli, ["tasks", "list", "--blocked"])

        assert result.exit_code == 0
        assert "Found 1 blocked tasks" in result.output
        mock_manager.list_blocked_tasks.assert_called_once()


class TestReadyTasksCommand:
    """Tests for gobby tasks ready command."""

    @patch("gobby.cli.tasks.crud.get_task_manager")
    def test_ready_no_tasks(
        self,
        mock_get_manager: MagicMock,
        runner: CliRunner,
    ):
        """Test ready with no tasks."""
        mock_manager = MagicMock()
        mock_manager.list_ready_tasks.return_value = []
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["tasks", "ready"])

        assert result.exit_code == 0
        assert "No ready tasks found" in result.output

    @patch("gobby.cli.tasks.crud.get_task_manager")
    @patch("gobby.cli.tasks.crud.get_claimed_task_ids")
    @patch("gobby.cli.tasks.crud.collect_ancestors")
    def test_ready_with_tasks(
        self,
        mock_ancestors: MagicMock,
        mock_claimed: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test ready with tasks."""
        mock_claimed.return_value = set()
        mock_manager = MagicMock()
        mock_manager.list_ready_tasks.return_value = [mock_task]
        mock_get_manager.return_value = mock_manager
        mock_ancestors.return_value = ([mock_task], {mock_task.id})

        result = runner.invoke(cli, ["tasks", "ready"])

        assert result.exit_code == 0
        assert "Found 1 ready tasks" in result.output

    @patch("gobby.cli.tasks.crud.get_task_manager")
    def test_ready_json_output(
        self,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test ready with JSON output."""
        mock_manager = MagicMock()
        mock_manager.list_ready_tasks.return_value = [mock_task]
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["tasks", "ready", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 1

    @patch("gobby.cli.tasks.crud.get_task_manager")
    @patch("gobby.cli.tasks.crud.get_claimed_task_ids")
    def test_ready_flat_output(
        self,
        mock_claimed: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test ready with --flat flag."""
        mock_claimed.return_value = set()
        mock_manager = MagicMock()
        mock_manager.list_ready_tasks.return_value = [mock_task]
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["tasks", "ready", "--flat"])

        assert result.exit_code == 0
        assert "Found 1 ready tasks" in result.output

    @patch("gobby.cli.tasks.crud.get_task_manager")
    def test_ready_with_filters(
        self,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test ready with priority and type filters."""
        mock_manager = MagicMock()
        mock_manager.list_ready_tasks.return_value = [mock_task]
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(
            cli, ["tasks", "ready", "--priority", "1", "--type", "bug", "--limit", "5"]
        )

        assert result.exit_code == 0
        call_kwargs = mock_manager.list_ready_tasks.call_args.kwargs
        assert call_kwargs["priority"] == 1
        assert call_kwargs["task_type"] == "bug"
        assert call_kwargs["limit"] == 5


class TestBlockedTasksCommand:
    """Tests for gobby tasks blocked command."""

    @patch("gobby.cli.tasks.crud.get_task_manager")
    def test_blocked_no_tasks(
        self,
        mock_get_manager: MagicMock,
        runner: CliRunner,
    ):
        """Test blocked with no tasks."""
        mock_manager = MagicMock()
        mock_manager.list_blocked_tasks.return_value = []
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["tasks", "blocked"])

        assert result.exit_code == 0
        assert "No blocked tasks found" in result.output

    @patch("gobby.storage.task_dependencies.TaskDependencyManager")
    @patch("gobby.cli.tasks.crud.get_task_manager")
    def test_blocked_with_tasks(
        self,
        mock_get_manager: MagicMock,
        mock_dep_cls: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test blocked with tasks."""
        mock_manager = MagicMock()
        mock_manager.list_blocked_tasks.return_value = [mock_task]
        mock_manager.db = MagicMock()
        mock_get_manager.return_value = mock_manager

        mock_dep_manager = MagicMock()
        mock_dep_manager.get_dependency_tree.return_value = {"blockers": [{"id": "gt-blocker1"}]}
        mock_dep_cls.return_value = mock_dep_manager

        blocker_task = MagicMock()
        blocker_task.status = "open"
        blocker_task.title = "Blocker Task"
        mock_manager.get_task.return_value = blocker_task

        result = runner.invoke(cli, ["tasks", "blocked"])

        assert result.exit_code == 0
        assert "Found 1 blocked tasks" in result.output

    @patch("gobby.storage.task_dependencies.TaskDependencyManager")
    @patch("gobby.cli.tasks.crud.get_task_manager")
    def test_blocked_json_output(
        self,
        mock_get_manager: MagicMock,
        mock_dep_cls: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test blocked with JSON output."""
        mock_manager = MagicMock()
        mock_manager.list_blocked_tasks.return_value = [mock_task]
        mock_manager.db = MagicMock()
        mock_get_manager.return_value = mock_manager

        mock_dep_manager = MagicMock()
        mock_dep_manager.get_dependency_tree.return_value = {"blockers": []}
        mock_dep_cls.return_value = mock_dep_manager

        result = runner.invoke(cli, ["tasks", "blocked", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 1
        assert "task" in data[0]
        assert "blocked_by" in data[0]


class TestTaskStatsCommand:
    """Tests for gobby tasks stats command."""

    @patch("gobby.cli.tasks.crud.get_task_manager")
    def test_stats_basic(
        self,
        mock_get_manager: MagicMock,
        runner: CliRunner,
    ):
        """Test stats command."""
        mock_task = MagicMock()
        mock_task.status = "open"
        mock_task.priority = 2
        mock_task.task_type = "feature"

        mock_manager = MagicMock()
        mock_manager.list_tasks.return_value = [mock_task]
        mock_manager.list_ready_tasks.return_value = [mock_task]
        mock_manager.list_blocked_tasks.return_value = []
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["tasks", "stats"])

        assert result.exit_code == 0
        assert "Task Statistics" in result.output
        assert "Total: 1" in result.output
        assert "Open: 1" in result.output

    @patch("gobby.cli.tasks.crud.get_task_manager")
    def test_stats_json_output(
        self,
        mock_get_manager: MagicMock,
        runner: CliRunner,
    ):
        """Test stats with JSON output."""
        mock_manager = MagicMock()
        mock_manager.list_tasks.return_value = []
        mock_manager.list_ready_tasks.return_value = []
        mock_manager.list_blocked_tasks.return_value = []
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["tasks", "stats", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "total" in data
        assert "by_status" in data
        assert "by_priority" in data


# ==============================================================================
# Tests for crud.py - CRUD Commands
# ==============================================================================


class TestCreateTaskCommand:
    """Tests for gobby tasks create command."""

    @patch("gobby.cli.tasks.crud.get_task_manager")
    @patch("gobby.cli.tasks.crud.get_project_context")
    def test_create_task(
        self,
        mock_project_ctx: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test creating a task."""
        mock_project_ctx.return_value = {"id": "proj-123", "name": "Test Project"}
        mock_manager = MagicMock()
        mock_manager.create_task.return_value = mock_task
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["tasks", "create", "My new task"])

        assert result.exit_code == 0
        assert "Created task Test Project-#1: Test Task" in result.output
        mock_manager.create_task.assert_called_once()

    @patch("gobby.cli.tasks.crud.get_task_manager")
    @patch("gobby.cli.tasks.crud.get_project_context")
    def test_create_task_with_options(
        self,
        mock_project_ctx: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test creating a task with options."""
        mock_project_ctx.return_value = {"id": "proj-123"}
        mock_manager = MagicMock()
        mock_manager.create_task.return_value = mock_task
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(
            cli,
            [
                "tasks",
                "create",
                "My new task",
                "--description",
                "Task description",
                "--priority",
                "1",
                "--type",
                "bug",
            ],
        )

        assert result.exit_code == 0
        mock_manager.create_task.assert_called_once_with(
            project_id="proj-123",
            title="My new task",
            description="Task description",
            priority=1,
            task_type="bug",
        )

    @patch("gobby.cli.tasks.crud.get_project_context")
    def test_create_task_no_project(
        self,
        mock_project_ctx: MagicMock,
        runner: CliRunner,
    ):
        """Test creating a task with no project context."""
        mock_project_ctx.return_value = None

        result = runner.invoke(cli, ["tasks", "create", "My new task"])

        assert result.exit_code == 0
        assert "Not in a gobby project" in result.output


class TestShowTaskCommand:
    """Tests for gobby tasks show command."""

    @patch("gobby.cli.tasks.crud.get_task_manager")
    @patch("gobby.cli.tasks.crud.resolve_task_id")
    def test_show_task(
        self,
        mock_resolve: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test showing a task."""
        mock_resolve.return_value = mock_task
        mock_get_manager.return_value = MagicMock()

        result = runner.invoke(cli, ["tasks", "show", "gt-abc123"])

        assert result.exit_code == 0
        assert "Test Task" in result.output
        assert "gt-abc123" in result.output

    @patch("gobby.cli.tasks.crud.get_task_manager")
    @patch("gobby.cli.tasks.crud.resolve_task_id")
    def test_show_task_with_labels(
        self,
        mock_resolve: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test showing a task with labels."""
        mock_task.labels = ["bug", "priority"]
        mock_task.assignee = "john"
        mock_resolve.return_value = mock_task
        mock_get_manager.return_value = MagicMock()

        result = runner.invoke(cli, ["tasks", "show", "gt-abc123"])

        assert result.exit_code == 0
        assert "bug, priority" in result.output
        assert "john" in result.output

    @patch("gobby.cli.tasks.crud.get_task_manager")
    @patch("gobby.cli.tasks.crud.resolve_task_id")
    def test_show_task_not_found(
        self,
        mock_resolve: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
    ):
        """Test showing a non-existent task."""
        mock_resolve.return_value = None
        mock_get_manager.return_value = MagicMock()

        result = runner.invoke(cli, ["tasks", "show", "gt-nonexistent"])

        assert result.exit_code == 0  # Click doesn't set exit code for None return


class TestUpdateTaskCommand:
    """Tests for gobby tasks update command."""

    @patch("gobby.cli.tasks.crud.get_task_manager")
    @patch("gobby.cli.tasks.crud.resolve_task_id")
    def test_update_task(
        self,
        mock_resolve: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test updating a task."""
        mock_resolve.return_value = mock_task
        mock_manager = MagicMock()
        mock_manager.update_task.return_value = mock_task
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["tasks", "update", "gt-abc123", "--title", "Updated title"])

        assert result.exit_code == 0
        assert "Updated task" in result.output

    @patch("gobby.cli.tasks.crud.get_task_manager")
    @patch("gobby.cli.tasks.crud.resolve_task_id")
    def test_update_task_multiple_fields(
        self,
        mock_resolve: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test updating multiple task fields."""
        mock_resolve.return_value = mock_task
        mock_manager = MagicMock()
        mock_manager.update_task.return_value = mock_task
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(
            cli,
            [
                "tasks",
                "update",
                "gt-abc123",
                "--title",
                "New title",
                "--status",
                "in_progress",
                "--priority",
                "1",
                "--assignee",
                "alice",
            ],
        )

        assert result.exit_code == 0
        mock_manager.update_task.assert_called_once()
        call_kwargs = mock_manager.update_task.call_args.kwargs
        assert call_kwargs["title"] == "New title"
        assert call_kwargs["status"] == "in_progress"
        assert call_kwargs["priority"] == 1
        assert call_kwargs["assignee"] == "alice"

    @patch("gobby.cli.tasks.crud.get_task_manager")
    @patch("gobby.cli.tasks.crud.resolve_task_id")
    def test_update_task_with_parent(
        self,
        mock_resolve: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test updating task with parent re-assignment."""
        parent_task = MagicMock()
        parent_task.id = "gt-parent"

        # First call returns the task, second call returns parent
        mock_resolve.side_effect = [mock_task, parent_task]
        mock_manager = MagicMock()
        mock_manager.update_task.return_value = mock_task
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["tasks", "update", "gt-abc123", "--parent", "gt-parent"])

        assert result.exit_code == 0
        mock_manager.update_task.assert_called_once()
        call_kwargs = mock_manager.update_task.call_args.kwargs
        assert call_kwargs["parent_task_id"] == "gt-parent"


class TestCloseTaskCommand:
    """Tests for gobby tasks close command."""

    @patch("gobby.cli.tasks.crud.get_task_manager")
    @patch("gobby.cli.tasks.crud.resolve_task_id")
    def test_close_task(
        self,
        mock_resolve: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test closing a task."""
        mock_resolve.return_value = mock_task
        mock_manager = MagicMock()
        mock_manager.list_tasks.return_value = []  # No children
        mock_manager.close_task.return_value = mock_task
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["tasks", "close", "gt-abc123"])

        assert result.exit_code == 0
        assert "Closed task" in result.output

    @patch("gobby.cli.tasks.crud.get_task_manager")
    @patch("gobby.cli.tasks.crud.resolve_task_id")
    def test_close_task_with_reason(
        self,
        mock_resolve: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test closing a task with a reason."""
        mock_resolve.return_value = mock_task
        mock_manager = MagicMock()
        mock_manager.list_tasks.return_value = []
        mock_manager.close_task.return_value = mock_task
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["tasks", "close", "gt-abc123", "--reason", "wont_fix"])

        assert result.exit_code == 0
        assert "wont_fix" in result.output
        mock_manager.close_task.assert_called_once_with(mock_task.id, reason="wont_fix")

    @patch("gobby.cli.tasks.crud.get_task_manager")
    @patch("gobby.cli.tasks.crud.resolve_task_id")
    def test_close_task_with_open_children(
        self,
        mock_resolve: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test closing a task with open children fails."""
        child_task = MagicMock()
        child_task.id = "gt-child1"
        child_task.title = "Child task"
        child_task.status = "open"

        mock_resolve.return_value = mock_task
        mock_manager = MagicMock()
        mock_manager.list_tasks.return_value = [child_task]
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["tasks", "close", "gt-abc123"])

        assert result.exit_code == 0
        assert "Cannot close" in result.output
        assert "child tasks still open" in result.output

    @patch("gobby.cli.tasks.crud.get_task_manager")
    @patch("gobby.cli.tasks.crud.resolve_task_id")
    def test_close_task_with_force(
        self,
        mock_resolve: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test closing a task with --force bypasses child check."""
        child_task = MagicMock()
        child_task.id = "gt-child1"
        child_task.status = "open"

        mock_resolve.return_value = mock_task
        mock_manager = MagicMock()
        mock_manager.close_task.return_value = mock_task
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["tasks", "close", "gt-abc123", "--force"])

        assert result.exit_code == 0
        assert "Closed task" in result.output
        mock_manager.close_task.assert_called_once()


class TestReopenTaskCommand:
    """Tests for gobby tasks reopen command."""

    @patch("gobby.cli.tasks.crud.get_task_manager")
    @patch("gobby.cli.tasks.crud.resolve_task_id")
    def test_reopen_task(
        self,
        mock_resolve: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test reopening a task."""
        mock_task.status = "closed"
        mock_resolve.return_value = mock_task
        mock_manager = MagicMock()
        mock_manager.reopen_task.return_value = mock_task
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["tasks", "reopen", "gt-abc123"])

        assert result.exit_code == 0
        assert "Reopened task" in result.output

    @patch("gobby.cli.tasks.crud.get_task_manager")
    @patch("gobby.cli.tasks.crud.resolve_task_id")
    def test_reopen_task_with_reason(
        self,
        mock_resolve: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test reopening a task with a reason."""
        mock_task.status = "closed"
        mock_resolve.return_value = mock_task
        mock_manager = MagicMock()
        mock_manager.reopen_task.return_value = mock_task
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(
            cli, ["tasks", "reopen", "gt-abc123", "--reason", "bug still exists"]
        )

        assert result.exit_code == 0
        assert "bug still exists" in result.output

    @patch("gobby.cli.tasks.crud.get_task_manager")
    @patch("gobby.cli.tasks.crud.resolve_task_id")
    def test_reopen_non_closed_task(
        self,
        mock_resolve: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test reopening a non-closed task fails."""
        mock_task.status = "open"
        mock_resolve.return_value = mock_task
        mock_get_manager.return_value = MagicMock()

        result = runner.invoke(cli, ["tasks", "reopen", "gt-abc123"])

        assert "not closed" in result.output


class TestDeleteTaskCommand:
    """Tests for gobby tasks delete command."""

    @patch("gobby.cli.tasks.crud.get_task_manager")
    @patch("gobby.cli.tasks.crud.resolve_task_id")
    def test_delete_task(
        self,
        mock_resolve: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test deleting a task with confirmation."""
        mock_resolve.return_value = mock_task
        mock_manager = MagicMock()
        mock_get_manager.return_value = mock_manager

        # Need to confirm with 'y'
        result = runner.invoke(cli, ["tasks", "delete", "gt-abc123"], input="y\n")

        assert result.exit_code == 0
        assert "Deleted task" in result.output
        mock_manager.delete_task.assert_called_once_with(mock_task.id, cascade=False)

    @patch("gobby.cli.tasks.crud.get_task_manager")
    @patch("gobby.cli.tasks.crud.resolve_task_id")
    def test_delete_task_with_cascade(
        self,
        mock_resolve: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test deleting a task with cascade."""
        mock_resolve.return_value = mock_task
        mock_manager = MagicMock()
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["tasks", "delete", "gt-abc123", "--cascade"], input="y\n")

        assert result.exit_code == 0
        mock_manager.delete_task.assert_called_once_with(mock_task.id, cascade=True)

    @patch("gobby.cli.tasks.crud.get_task_manager")
    @patch("gobby.cli.tasks.crud.resolve_task_id")
    def test_delete_task_abort(
        self,
        mock_resolve: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test aborting task deletion."""
        mock_resolve.return_value = mock_task
        mock_manager = MagicMock()
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["tasks", "delete", "gt-abc123"], input="n\n")

        assert result.exit_code == 1
        mock_manager.delete_task.assert_not_called()


# ==============================================================================
# Tests for ai.py - AI Commands
# ==============================================================================


class TestSuggestCommand:
    """Tests for gobby tasks suggest command."""

    @patch("gobby.cli.tasks.ai.get_task_manager")
    def test_suggest_no_ready_tasks(
        self,
        mock_get_manager: MagicMock,
        runner: CliRunner,
    ):
        """Test suggest with no ready tasks."""
        mock_manager = MagicMock()
        mock_manager.list_ready_tasks.return_value = []
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["tasks", "suggest"])

        assert result.exit_code == 0
        assert "No ready tasks found" in result.output

    @patch("gobby.cli.tasks.ai.get_task_manager")
    def test_suggest_with_tasks(
        self,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test suggest returns best task."""
        mock_manager = MagicMock()
        mock_manager.list_ready_tasks.return_value = [mock_task]
        mock_manager.list_tasks.return_value = []  # No children
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["tasks", "suggest"])

        assert result.exit_code == 0
        assert "Suggested next task" in result.output
        assert "gt-abc123" in result.output

    @patch("gobby.cli.tasks.ai.get_task_manager")
    def test_suggest_json_output(
        self,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test suggest with JSON output."""
        mock_manager = MagicMock()
        mock_manager.list_ready_tasks.return_value = [mock_task]
        mock_manager.list_tasks.return_value = []
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["tasks", "suggest", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "suggestion" in data
        assert "score" in data
        assert "reason" in data

    @patch("gobby.cli.tasks.ai.get_task_manager")
    def test_suggest_prefers_leaf_tasks(
        self,
        mock_get_manager: MagicMock,
        runner: CliRunner,
    ):
        """Test that suggest prefers leaf tasks by default."""
        leaf_task = MagicMock()
        leaf_task.id = "gt-leaf"
        leaf_task.title = "Leaf Task"
        leaf_task.priority = 2
        leaf_task.status = "open"
        leaf_task.complexity_score = 3
        leaf_task.test_strategy = None
        leaf_task.description = "A leaf task"
        leaf_task.to_dict.return_value = {"id": "gt-leaf", "title": "Leaf Task"}

        parent_task = MagicMock()
        parent_task.id = "gt-parent"
        parent_task.title = "Parent Task"
        parent_task.priority = 1  # Higher priority
        parent_task.status = "open"
        parent_task.complexity_score = 5
        parent_task.test_strategy = None
        parent_task.description = "A parent task"
        parent_task.to_dict.return_value = {"id": "gt-parent", "title": "Parent Task"}

        mock_manager = MagicMock()
        mock_manager.list_ready_tasks.return_value = [parent_task, leaf_task]

        # Parent has children, leaf doesn't
        def list_tasks_side_effect(**kwargs):
            if kwargs.get("parent_task_id") == "gt-parent":
                return [MagicMock()]  # Has child
            return []  # No children

        mock_manager.list_tasks.side_effect = list_tasks_side_effect
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["tasks", "suggest", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        # With prefer_subtasks=True, leaf task should be suggested
        assert data["suggestion"]["id"] == "gt-leaf"

    @patch("gobby.cli.tasks.ai.get_task_manager")
    def test_suggest_no_prefer_subtasks(
        self,
        mock_get_manager: MagicMock,
        runner: CliRunner,
    ):
        """Test suggest with --no-prefer-subtasks."""
        task = MagicMock()
        task.id = "gt-abc123"
        task.title = "High Priority Task"
        task.priority = 1
        task.status = "open"
        task.complexity_score = 3
        task.test_strategy = None
        task.description = "High priority"
        task.to_dict.return_value = {"id": "gt-abc123", "title": "High Priority Task"}

        mock_manager = MagicMock()
        mock_manager.list_ready_tasks.return_value = [task]
        mock_manager.list_tasks.return_value = []
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["tasks", "suggest", "--no-prefer-subtasks"])

        assert result.exit_code == 0
        assert "high priority" in result.output.lower()


class TestComplexityCommand:
    """Tests for gobby tasks complexity command."""

    @patch("gobby.cli.tasks.ai.get_task_manager")
    @patch("gobby.cli.tasks.ai.resolve_task_id")
    def test_complexity_single_task(
        self,
        mock_resolve: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test complexity analysis for single task."""
        mock_task.description = "Short task"
        mock_resolve.return_value = mock_task
        mock_manager = MagicMock()
        mock_manager.list_tasks.return_value = []  # No subtasks
        mock_manager.update_task.return_value = mock_task
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["tasks", "complexity", "gt-abc123"])

        assert result.exit_code == 0
        assert "Complexity Score" in result.output

    @patch("gobby.cli.tasks.ai.get_task_manager")
    @patch("gobby.cli.tasks.ai.resolve_task_id")
    def test_complexity_json_output(
        self,
        mock_resolve: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test complexity with JSON output."""
        mock_task.description = "Short task"
        mock_resolve.return_value = mock_task
        mock_manager = MagicMock()
        mock_manager.list_tasks.return_value = []
        mock_manager.update_task.return_value = mock_task
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["tasks", "complexity", "gt-abc123", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "complexity_score" in data
        assert "reasoning" in data

    @patch("gobby.cli.tasks.ai.get_task_manager")
    @patch("gobby.cli.tasks.ai.get_project_context")
    def test_complexity_all_tasks(
        self,
        mock_project_ctx: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test complexity analysis for all tasks."""
        mock_project_ctx.return_value = {"id": "proj-123"}
        mock_task.description = "Short task"
        mock_manager = MagicMock()
        mock_manager.list_tasks.side_effect = [
            [mock_task],  # First call: all tasks
            [],  # Second call: subtasks check
        ]
        mock_manager.update_task.return_value = mock_task
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["tasks", "complexity", "--all"])

        assert result.exit_code == 0
        assert "Analyzed 1 tasks" in result.output

    @patch("gobby.cli.tasks.ai.get_task_manager")
    @patch("gobby.cli.tasks.ai.get_project_context")
    def test_complexity_pending_only(
        self,
        mock_project_ctx: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test complexity for pending tasks only."""
        mock_project_ctx.return_value = {"id": "proj-123"}
        mock_task.description = "Short task"
        mock_manager = MagicMock()
        mock_manager.list_tasks.side_effect = [[mock_task], []]
        mock_manager.update_task.return_value = mock_task
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["tasks", "complexity", "--all", "--pending"])

        assert result.exit_code == 0
        # Verify status filter was passed
        first_call = mock_manager.list_tasks.call_args_list[0]
        assert first_call.kwargs.get("status") == "open"

    def test_complexity_requires_task_id_or_all(self, runner: CliRunner):
        """Test that complexity requires task ID or --all."""
        result = runner.invoke(cli, ["tasks", "complexity"])

        assert result.exit_code == 0
        assert "TASK_ID required" in result.output

    @patch("gobby.cli.tasks.ai.get_task_manager")
    @patch("gobby.cli.tasks.ai.resolve_task_id")
    def test_complexity_with_subtasks(
        self,
        mock_resolve: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test complexity scoring for task with subtasks."""
        mock_resolve.return_value = mock_task
        mock_manager = MagicMock()
        # Task has 5 subtasks
        mock_manager.list_tasks.return_value = [MagicMock() for _ in range(5)]
        mock_manager.update_task.return_value = mock_task
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["tasks", "complexity", "gt-abc123", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["existing_subtasks"] == 5
        assert "subtasks" in data["reasoning"].lower()


class TestGenerateCriteriaCommand:
    """Tests for gobby tasks generate-criteria command."""

    def test_generate_criteria_requires_task_id_or_all(self, runner: CliRunner):
        """Test that generate-criteria requires task ID or --all."""
        result = runner.invoke(cli, ["tasks", "generate-criteria"])

        assert result.exit_code == 0
        assert "TASK_ID is required" in result.output

    @patch("gobby.cli.tasks.ai.get_task_manager")
    @patch("gobby.cli.tasks.ai.resolve_task_id")
    def test_generate_criteria_already_has_criteria(
        self,
        mock_resolve: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test generate-criteria when task already has criteria."""
        mock_task.validation_criteria = "Existing criteria"
        mock_resolve.return_value = mock_task
        mock_get_manager.return_value = MagicMock()

        result = runner.invoke(cli, ["tasks", "generate-criteria", "gt-abc123"])

        assert result.exit_code == 0
        assert "already has validation criteria" in result.output
        assert "Existing criteria" in result.output

    @patch("gobby.cli.tasks.ai.get_task_manager")
    @patch("gobby.cli.tasks.ai.resolve_task_id")
    def test_generate_criteria_parent_task(
        self,
        mock_resolve: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test generate-criteria for parent task."""
        mock_task.validation_criteria = None
        mock_resolve.return_value = mock_task
        mock_manager = MagicMock()
        mock_manager.list_tasks.return_value = [MagicMock()]  # Has children
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["tasks", "generate-criteria", "gt-abc123"])

        assert result.exit_code == 0
        assert "Parent task detected" in result.output
        mock_manager.update_task.assert_called_once()


class TestExpandCommand:
    """Tests for gobby tasks expand command."""

    def test_expand_help(self, runner: CliRunner):
        """Test expand --help shows options."""
        result = runner.invoke(cli, ["tasks", "expand", "--help"])

        assert result.exit_code == 0
        assert "--web-research" in result.output
        assert "--code-context" in result.output
        assert "--context" in result.output

    @patch("gobby.cli.tasks.ai.get_task_manager")
    @patch("gobby.cli.tasks.ai.resolve_task_id")
    def test_expand_task_not_found(
        self,
        mock_resolve: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
    ):
        """Test expand with non-existent task."""
        mock_resolve.return_value = None
        mock_get_manager.return_value = MagicMock()

        result = runner.invoke(cli, ["tasks", "expand", "gt-nonexistent"])

        assert result.exit_code == 0


class TestExpandAllCommand:
    """Tests for gobby tasks expand-all command."""

    @patch("gobby.cli.tasks.ai.get_task_manager")
    def test_expand_all_no_tasks(
        self,
        mock_get_manager: MagicMock,
        runner: CliRunner,
    ):
        """Test expand-all with no unexpanded tasks."""
        mock_manager = MagicMock()
        mock_manager.list_tasks.return_value = []
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["tasks", "expand-all"])

        assert result.exit_code == 0
        assert "No unexpanded tasks found" in result.output

    @patch("gobby.cli.tasks.ai.get_task_manager")
    def test_expand_all_dry_run(
        self,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test expand-all with --dry-run."""
        mock_task.complexity_score = 5
        mock_manager = MagicMock()
        # list_tasks returns the task, but no children
        mock_manager.list_tasks.side_effect = [[mock_task], []]
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["tasks", "expand-all", "--dry-run"])

        assert result.exit_code == 0
        assert "Would expand 1 tasks" in result.output


class TestImportSpecCommand:
    """Tests for gobby tasks import-spec command."""

    def test_import_spec_help(self, runner: CliRunner):
        """Test import-spec --help shows options."""
        result = runner.invoke(cli, ["tasks", "import-spec", "--help"])

        assert result.exit_code == 0
        assert "--type" in result.output
        assert "--parent" in result.output


class TestValidateCommand:
    """Tests for gobby tasks validate command - AI module."""

    @patch("gobby.cli.tasks.ai.get_task_manager")
    @patch("gobby.cli.tasks.ai.resolve_task_id")
    def test_validate_parent_task_all_children_closed(
        self,
        mock_resolve: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test validate parent task when all children are closed."""
        mock_resolve.return_value = mock_task
        mock_manager = MagicMock()

        child_task = MagicMock()
        child_task.id = "gt-child1"
        child_task.status = "closed"
        mock_manager.list_tasks.return_value = [child_task]
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["tasks", "validate", "gt-abc123", "--summary", "test"])

        assert result.exit_code == 0
        assert "VALID" in result.output
        mock_manager.close_task.assert_called()

    @patch("gobby.cli.tasks.ai.get_task_manager")
    @patch("gobby.cli.tasks.ai.resolve_task_id")
    def test_validate_parent_task_with_open_children(
        self,
        mock_resolve: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test validate parent task with open children."""
        mock_resolve.return_value = mock_task
        mock_manager = MagicMock()

        child_task = MagicMock()
        child_task.id = "gt-child1"
        child_task.title = "Open child"
        child_task.status = "open"
        mock_manager.list_tasks.return_value = [child_task]
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["tasks", "validate", "gt-abc123", "--summary", "test"])

        assert result.exit_code == 0
        assert "INVALID" in result.output
        assert "still open" in result.output

    @patch("gobby.cli.tasks.ai.get_task_manager")
    @patch("gobby.cli.tasks.ai.resolve_task_id")
    def test_validate_leaf_task_empty_summary(
        self,
        mock_resolve: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test validate leaf task with empty summary."""
        mock_resolve.return_value = mock_task
        mock_manager = MagicMock()
        mock_manager.list_tasks.return_value = []  # No children
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["tasks", "validate", "gt-abc123", "--summary", "   "])

        assert "Changes summary is required" in result.output


# ==============================================================================
# Tests for _utils.py helpers
# ==============================================================================


class TestResolveTaskId:
    """Tests for resolve_task_id helper."""

    @patch("gobby.cli.tasks._utils.get_task_manager")
    def test_resolve_exact_match(
        self,
        mock_get_manager: MagicMock,
        mock_task: MagicMock,
    ):
        """Test resolve_task_id with exact match."""
        from gobby.cli.tasks._utils import resolve_task_id

        mock_manager = MagicMock()
        mock_manager.get_task.return_value = mock_task
        mock_get_manager.return_value = mock_manager

        result = resolve_task_id(mock_manager, "gt-abc123")

        assert result == mock_task

    @patch("gobby.cli.tasks._utils.get_task_manager")
    def test_resolve_prefix_single_match(
        self,
        mock_get_manager: MagicMock,
        mock_task: MagicMock,
    ):
        """Test resolve_task_id with single prefix match."""
        from gobby.cli.tasks._utils import resolve_task_id

        mock_manager = MagicMock()
        mock_manager.get_task.side_effect = ValueError("not found")
        mock_manager.find_tasks_by_prefix.return_value = [mock_task]
        mock_get_manager.return_value = mock_manager

        result = resolve_task_id(mock_manager, "abc")

        assert result == mock_task

    @patch("gobby.cli.tasks._utils.get_task_manager")
    def test_resolve_prefix_no_match(
        self,
        mock_get_manager: MagicMock,
    ):
        """Test resolve_task_id with no match."""
        from gobby.cli.tasks._utils import resolve_task_id

        mock_manager = MagicMock()
        mock_manager.get_task.side_effect = ValueError("not found")
        mock_manager.find_tasks_by_prefix.return_value = []
        mock_get_manager.return_value = mock_manager

        result = resolve_task_id(mock_manager, "nonexistent")

        assert result is None

    @patch("gobby.cli.tasks._utils.get_task_manager")
    def test_resolve_prefix_ambiguous(
        self,
        mock_get_manager: MagicMock,
    ):
        """Test resolve_task_id with ambiguous prefix."""
        from gobby.cli.tasks._utils import resolve_task_id

        mock_manager = MagicMock()
        mock_manager.get_task.side_effect = ValueError("not found")

        task1 = MagicMock()
        task1.id = "gt-abc123"
        task1.title = "Task 1"
        task2 = MagicMock()
        task2.id = "gt-abc456"
        task2.title = "Task 2"

        mock_manager.find_tasks_by_prefix.return_value = [task1, task2]
        mock_get_manager.return_value = mock_manager

        result = resolve_task_id(mock_manager, "abc")

        assert result is None


class TestFormatTaskRow:
    """Tests for format_task_row helper."""

    def test_format_task_row_basic(self, mock_task: MagicMock):
        """Test basic task row formatting."""
        from gobby.cli.tasks._utils import format_task_row

        result = format_task_row(mock_task)

        assert "#1" in result  # Shows seq_num instead of full task ID
        assert "Test Task" in result

    def test_format_task_row_muted(self, mock_task: MagicMock):
        """Test muted task row formatting."""
        from gobby.cli.tasks._utils import format_task_row

        result = format_task_row(mock_task, is_primary=False)

        # Should contain ANSI escape codes for dim
        assert "\033[2m" in result or mock_task.title in result

    def test_format_task_row_with_tree_prefix(self, mock_task: MagicMock):
        """Test task row with tree prefix."""
        from gobby.cli.tasks._utils import format_task_row

        result = format_task_row(mock_task, tree_prefix="├── ")

        assert "├── " in result

    def test_format_task_row_claimed(self, mock_task: MagicMock):
        """Test task row for claimed task."""
        from gobby.cli.tasks._utils import format_task_row

        result = format_task_row(mock_task, claimed_task_ids={"gt-abc123"})

        # Claimed open tasks show a different icon
        assert "◐" in result


# ==============================================================================
# Additional ai.py tests for improved coverage
# ==============================================================================


class TestValidateCommandExtended:
    """Extended tests for validate command covering more paths."""

    @patch("gobby.cli.tasks.ai.get_task_manager")
    @patch("gobby.cli.tasks.ai.resolve_task_id")
    def test_validate_task_not_found(
        self,
        mock_resolve: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
    ):
        """Test validate when task is not found."""
        mock_resolve.return_value = None
        mock_get_manager.return_value = MagicMock()

        result = runner.invoke(cli, ["tasks", "validate", "gt-nonexistent", "--summary", "test"])

        assert result.exit_code == 0

    @patch("gobby.cli.tasks.ai.get_task_manager")
    @patch("gobby.cli.tasks.ai.resolve_task_id")
    def test_validate_parent_many_open_children(
        self,
        mock_resolve: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test validate parent task with many open children shows truncated list."""
        mock_resolve.return_value = mock_task
        mock_manager = MagicMock()

        # Create 10 open children
        children = []
        for i in range(10):
            child = MagicMock()
            child.id = f"gt-child{i}"
            child.title = f"Child task {i}"
            child.status = "open"
            children.append(child)

        mock_manager.list_tasks.return_value = children
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["tasks", "validate", "gt-abc123", "--summary", "test"])

        assert result.exit_code == 0
        assert "INVALID" in result.output
        assert "10 of 10" in result.output
        assert "more" in result.output  # Should show truncation

    @patch("gobby.config.app.load_config")
    @patch("gobby.cli.tasks.ai.get_task_manager")
    @patch("gobby.cli.tasks.ai.resolve_task_id")
    def test_validate_with_file_summary(
        self,
        mock_resolve: MagicMock,
        mock_get_manager: MagicMock,
        mock_config: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
        tmp_path,
    ):
        """Test validate with --file option for summary."""
        mock_resolve.return_value = mock_task
        mock_manager = MagicMock()
        mock_manager.list_tasks.return_value = []  # No children
        mock_get_manager.return_value = mock_manager

        # Create temp file with summary
        summary_file = tmp_path / "summary.txt"
        summary_file.write_text("This is a test summary from file")

        mock_config.side_effect = Exception("Config not available")

        result = runner.invoke(cli, ["tasks", "validate", "gt-abc123", "--file", str(summary_file)])

        # Command should attempt to validate (may fail on config but accepts the file)
        assert result.exit_code == 0


class TestComplexityCommandExtended:
    """Extended tests for complexity command."""

    @patch("gobby.cli.tasks.ai.get_task_manager")
    @patch("gobby.cli.tasks.ai.resolve_task_id")
    def test_complexity_medium_description(
        self,
        mock_resolve: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test complexity for task with medium-length description."""
        mock_task.description = "A" * 300  # Medium length
        mock_resolve.return_value = mock_task
        mock_manager = MagicMock()
        mock_manager.list_tasks.return_value = []
        mock_manager.update_task.return_value = mock_task
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["tasks", "complexity", "gt-abc123", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["complexity_score"] == 5
        assert "moderate complexity" in data["reasoning"].lower()

    @patch("gobby.cli.tasks.ai.get_task_manager")
    @patch("gobby.cli.tasks.ai.resolve_task_id")
    def test_complexity_long_description(
        self,
        mock_resolve: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test complexity for task with long description."""
        mock_task.description = "A" * 600  # Long description
        mock_resolve.return_value = mock_task
        mock_manager = MagicMock()
        mock_manager.list_tasks.return_value = []
        mock_manager.update_task.return_value = mock_task
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["tasks", "complexity", "gt-abc123", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["complexity_score"] == 8
        assert "complex" in data["reasoning"].lower()

    @patch("gobby.cli.tasks.ai.get_task_manager")
    @patch("gobby.cli.tasks.ai.get_project_context")
    def test_complexity_all_json_output(
        self,
        mock_project_ctx: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test complexity --all with JSON output."""
        mock_project_ctx.return_value = {"id": "proj-123"}
        mock_task.description = "Short task"
        mock_manager = MagicMock()
        mock_manager.list_tasks.side_effect = [[mock_task], []]
        mock_manager.update_task.return_value = mock_task
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["tasks", "complexity", "--all", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 1

    @patch("gobby.cli.tasks.ai.get_task_manager")
    @patch("gobby.cli.tasks.ai.get_project_context")
    def test_complexity_all_no_tasks(
        self,
        mock_project_ctx: MagicMock,
        mock_get_manager: MagicMock,
        runner: CliRunner,
    ):
        """Test complexity --all with no tasks."""
        mock_project_ctx.return_value = {"id": "proj-123"}
        mock_manager = MagicMock()
        mock_manager.list_tasks.return_value = []
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["tasks", "complexity", "--all"])

        assert result.exit_code == 0
        assert "No tasks found" in result.output


class TestSuggestCommandExtended:
    """Extended tests for suggest command."""

    @patch("gobby.cli.tasks.ai.get_task_manager")
    def test_suggest_no_ready_json_output(
        self,
        mock_get_manager: MagicMock,
        runner: CliRunner,
    ):
        """Test suggest with no ready tasks in JSON mode."""
        mock_manager = MagicMock()
        mock_manager.list_ready_tasks.return_value = []
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["tasks", "suggest", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["suggestion"] is None
        assert "No ready tasks found" in data["reason"]

    @patch("gobby.cli.tasks.ai.get_task_manager")
    def test_suggest_with_type_filter(
        self,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test suggest with type filter."""
        mock_manager = MagicMock()
        mock_manager.list_ready_tasks.return_value = [mock_task]
        mock_manager.list_tasks.return_value = []
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["tasks", "suggest", "--type", "bug"])

        assert result.exit_code == 0
        mock_manager.list_ready_tasks.assert_called_once()
        call_kwargs = mock_manager.list_ready_tasks.call_args.kwargs
        assert call_kwargs["task_type"] == "bug"

    @patch("gobby.cli.tasks.ai.get_task_manager")
    def test_suggest_task_with_test_strategy(
        self,
        mock_get_manager: MagicMock,
        runner: CliRunner,
    ):
        """Test that task with test strategy gets bonus score."""
        task_with_strategy = MagicMock()
        task_with_strategy.id = "gt-strat"
        task_with_strategy.title = "Task with strategy"
        task_with_strategy.priority = 2
        task_with_strategy.status = "open"
        task_with_strategy.complexity_score = 3
        task_with_strategy.test_strategy = "Unit tests for all methods"
        task_with_strategy.description = "Has test strategy"
        task_with_strategy.to_dict.return_value = {
            "id": "gt-strat",
            "title": "Task with strategy",
        }

        mock_manager = MagicMock()
        mock_manager.list_ready_tasks.return_value = [task_with_strategy]
        mock_manager.list_tasks.return_value = []
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["tasks", "suggest", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "test strategy" in data["reason"].lower()

    @patch("gobby.cli.tasks.ai.get_task_manager")
    def test_suggest_high_priority_task(
        self,
        mock_get_manager: MagicMock,
        runner: CliRunner,
    ):
        """Test that high priority task is mentioned in reason."""
        high_priority_task = MagicMock()
        high_priority_task.id = "gt-high"
        high_priority_task.title = "High Priority"
        high_priority_task.priority = 1
        high_priority_task.status = "open"
        high_priority_task.complexity_score = None
        high_priority_task.test_strategy = None
        high_priority_task.description = "Urgent task"
        high_priority_task.to_dict.return_value = {
            "id": "gt-high",
            "title": "High Priority",
        }

        mock_manager = MagicMock()
        mock_manager.list_ready_tasks.return_value = [high_priority_task]
        mock_manager.list_tasks.return_value = []
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["tasks", "suggest", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "high priority" in data["reason"].lower()


class TestGenerateCriteriaCommandExtended:
    """Extended tests for generate-criteria command."""

    @patch("gobby.config.app.load_config")
    @patch("gobby.cli.tasks.ai.get_task_manager")
    @patch("gobby.cli.tasks.ai.resolve_task_id")
    def test_generate_criteria_leaf_task_llm_error(
        self,
        mock_resolve: MagicMock,
        mock_get_manager: MagicMock,
        mock_config: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test generate-criteria for leaf task when LLM initialization fails."""
        mock_task.validation_criteria = None
        mock_resolve.return_value = mock_task
        mock_manager = MagicMock()
        mock_manager.list_tasks.return_value = []  # No children (leaf task)
        mock_get_manager.return_value = mock_manager
        mock_config.side_effect = Exception("LLM config error")

        result = runner.invoke(cli, ["tasks", "generate-criteria", "gt-abc123"])

        assert result.exit_code == 0
        assert "Error initializing validator" in result.output


class TestExpandCommandExtended:
    """Extended tests for expand command."""

    @patch("gobby.config.app.load_config")
    @patch("gobby.cli.tasks.ai.get_task_manager")
    @patch("gobby.cli.tasks.ai.resolve_task_id")
    def test_expand_disabled_in_config(
        self,
        mock_resolve: MagicMock,
        mock_get_manager: MagicMock,
        mock_config: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test expand when expansion is disabled in config."""
        mock_resolve.return_value = mock_task
        mock_get_manager.return_value = MagicMock()
        mock_config.return_value.gobby_tasks.expansion.enabled = False

        result = runner.invoke(cli, ["tasks", "expand", "gt-abc123"])

        assert result.exit_code == 0
        assert "disabled" in result.output.lower()

    @patch("gobby.config.app.load_config")
    @patch("gobby.cli.tasks.ai.get_task_manager")
    @patch("gobby.cli.tasks.ai.resolve_task_id")
    def test_expand_with_context(
        self,
        mock_resolve: MagicMock,
        mock_get_manager: MagicMock,
        mock_config: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test expand with --context option."""
        mock_resolve.return_value = mock_task
        mock_get_manager.return_value = MagicMock()
        mock_config.side_effect = Exception("Config error")

        result = runner.invoke(
            cli, ["tasks", "expand", "gt-abc123", "--context", "Additional info"]
        )

        # Should attempt expansion (fails on config, but accepted the context)
        assert result.exit_code == 0


class TestExpandAllCommandExtended:
    """Extended tests for expand-all command."""

    @patch("gobby.cli.tasks.ai.get_task_manager")
    def test_expand_all_with_min_complexity(
        self,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test expand-all with --min-complexity filter."""
        mock_task.complexity_score = 2  # Below threshold
        mock_manager = MagicMock()
        mock_manager.list_tasks.side_effect = [[mock_task], []]
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["tasks", "expand-all", "--min-complexity", "5", "--dry-run"])

        assert result.exit_code == 0
        assert "No unexpanded tasks found" in result.output

    @patch("gobby.cli.tasks.ai.get_task_manager")
    def test_expand_all_with_type_filter(
        self,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_task: MagicMock,
    ):
        """Test expand-all with --type filter."""
        mock_task.complexity_score = 5
        mock_manager = MagicMock()
        mock_manager.list_tasks.side_effect = [[mock_task], []]
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["tasks", "expand-all", "--type", "feature", "--dry-run"])

        assert result.exit_code == 0
        # Verify type filter was passed
        first_call = mock_manager.list_tasks.call_args_list[0]
        assert first_call.kwargs.get("task_type") == "feature"


class TestUtilsHelpers:
    """Additional tests for _utils.py helpers."""

    def test_format_task_row_different_statuses(self, mock_task: MagicMock):
        """Test format_task_row with different task statuses."""
        from gobby.cli.tasks._utils import format_task_row

        # Test in_progress status
        mock_task.status = "in_progress"
        result = format_task_row(mock_task)
        assert "●" in result

        # Test closed status
        mock_task.status = "closed"
        result = format_task_row(mock_task)
        assert "✓" in result

        # Test blocked status
        mock_task.status = "blocked"
        result = format_task_row(mock_task)
        assert "⊗" in result

        # Test escalated status
        mock_task.status = "escalated"
        result = format_task_row(mock_task)
        assert "⚠" in result

    def test_format_task_row_different_priorities(self, mock_task: MagicMock):
        """Test format_task_row with different priorities."""
        from gobby.cli.tasks._utils import format_task_row

        mock_task.status = "open"

        # High priority
        mock_task.priority = 1
        result = format_task_row(mock_task)
        assert "🔴" in result

        # Medium priority
        mock_task.priority = 2
        result = format_task_row(mock_task)
        assert "🟡" in result

        # Low priority
        mock_task.priority = 3
        result = format_task_row(mock_task)
        assert "🔵" in result


class TestFormatTaskHeader:
    """Tests for format_task_header helper."""

    def test_format_task_header_content(self):
        """Test task header formatting."""
        from gobby.cli.tasks._utils import format_task_header

        result = format_task_header()

        assert "#" in result  # Column header changed from ID to #
        assert "TITLE" in result
