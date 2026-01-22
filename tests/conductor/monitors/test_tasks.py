"""Tests for gobby.conductor.monitors.tasks module.

Tests for the TaskMonitor class that detects:
- Stale tasks (in_progress > threshold)
- Blocked task chains
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock


class TestTaskMonitorStaleTasks:
    """Tests for stale task detection."""

    def test_check_returns_stale_tasks(self):
        """TaskMonitor.check() returns tasks in_progress longer than threshold."""
        from gobby.conductor.monitors.tasks import TaskMonitor

        # Create mock task manager
        mock_task_manager = MagicMock()

        # Create a stale task (in_progress for 25 hours)
        stale_time = (datetime.now(UTC) - timedelta(hours=25)).isoformat()
        stale_task = MagicMock()
        stale_task.id = "task-stale"
        stale_task.status = "in_progress"
        stale_task.updated_at = stale_time
        stale_task.title = "Stale Task"

        # Create a fresh task (in_progress for 1 hour)
        fresh_time = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        fresh_task = MagicMock()
        fresh_task.id = "task-fresh"
        fresh_task.status = "in_progress"
        fresh_task.updated_at = fresh_time
        fresh_task.title = "Fresh Task"

        mock_task_manager.list_tasks.return_value = [stale_task, fresh_task]

        monitor = TaskMonitor(task_manager=mock_task_manager)
        result = monitor.check(stale_threshold_hours=24)

        assert "stale_tasks" in result
        assert len(result["stale_tasks"]) == 1
        assert result["stale_tasks"][0]["task_id"] == "task-stale"

    def test_check_with_no_stale_tasks(self):
        """TaskMonitor.check() returns empty when no stale tasks."""
        from gobby.conductor.monitors.tasks import TaskMonitor

        mock_task_manager = MagicMock()

        # Only fresh tasks
        fresh_time = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        fresh_task = MagicMock()
        fresh_task.id = "task-fresh"
        fresh_task.status = "in_progress"
        fresh_task.updated_at = fresh_time
        fresh_task.title = "Fresh Task"

        mock_task_manager.list_tasks.return_value = [fresh_task]

        monitor = TaskMonitor(task_manager=mock_task_manager)
        result = monitor.check(stale_threshold_hours=24)

        assert result["stale_tasks"] == []

    def test_check_custom_threshold(self):
        """TaskMonitor.check() respects custom stale threshold."""
        from gobby.conductor.monitors.tasks import TaskMonitor

        mock_task_manager = MagicMock()

        # Task in_progress for 5 hours
        five_hours_ago = (datetime.now(UTC) - timedelta(hours=5)).isoformat()
        task = MagicMock()
        task.id = "task-1"
        task.status = "in_progress"
        task.updated_at = five_hours_ago
        task.title = "Task 1"

        mock_task_manager.list_tasks.return_value = [task]

        monitor = TaskMonitor(task_manager=mock_task_manager)

        # With 4-hour threshold, task is stale
        result = monitor.check(stale_threshold_hours=4)
        assert len(result["stale_tasks"]) == 1

        # With 6-hour threshold, task is fresh
        result = monitor.check(stale_threshold_hours=6)
        assert len(result["stale_tasks"]) == 0


class TestTaskMonitorBlockedChains:
    """Tests for blocked task chain detection."""

    def test_check_returns_blocked_chains(self):
        """TaskMonitor.check() returns blocked task chains."""
        from gobby.conductor.monitors.tasks import TaskMonitor

        mock_task_manager = MagicMock()

        # Create a blocked task
        blocked_task = MagicMock()
        blocked_task.id = "task-blocked"
        blocked_task.status = "open"
        blocked_task.title = "Blocked Task"

        # Create a blocker task that is in_progress
        blocker_task = MagicMock()
        blocker_task.id = "task-blocker"
        blocker_task.status = "in_progress"
        blocker_task.title = "Blocker Task"

        mock_task_manager.list_blocked_tasks.return_value = [blocked_task]
        mock_task_manager.list_tasks.return_value = []  # No stale tasks

        monitor = TaskMonitor(task_manager=mock_task_manager)
        result = monitor.check()

        assert "blocked_chains" in result
        assert len(result["blocked_chains"]) == 1

    def test_check_with_no_blocked_tasks(self):
        """TaskMonitor.check() returns empty when no blocked chains."""
        from gobby.conductor.monitors.tasks import TaskMonitor

        mock_task_manager = MagicMock()
        mock_task_manager.list_blocked_tasks.return_value = []
        mock_task_manager.list_tasks.return_value = []

        monitor = TaskMonitor(task_manager=mock_task_manager)
        result = monitor.check()

        assert result["blocked_chains"] == []


class TestTaskMonitorProjectFilter:
    """Tests for project-scoped monitoring."""

    def test_check_filters_by_project(self):
        """TaskMonitor.check() filters by project_id when provided."""
        from gobby.conductor.monitors.tasks import TaskMonitor

        mock_task_manager = MagicMock()
        mock_task_manager.list_tasks.return_value = []
        mock_task_manager.list_blocked_tasks.return_value = []

        monitor = TaskMonitor(task_manager=mock_task_manager)
        monitor.check(project_id="proj-123")

        # Verify project_id was passed to queries
        mock_task_manager.list_tasks.assert_called_once()
        call_kwargs = mock_task_manager.list_tasks.call_args[1]
        assert call_kwargs.get("project_id") == "proj-123"


class TestTaskMonitorSummary:
    """Tests for monitor summary output."""

    def test_check_returns_summary_counts(self):
        """TaskMonitor.check() includes summary counts."""
        from gobby.conductor.monitors.tasks import TaskMonitor

        mock_task_manager = MagicMock()

        stale_time = (datetime.now(UTC) - timedelta(hours=25)).isoformat()
        stale_task = MagicMock()
        stale_task.id = "task-stale"
        stale_task.status = "in_progress"
        stale_task.updated_at = stale_time
        stale_task.title = "Stale"

        blocked_task = MagicMock()
        blocked_task.id = "task-blocked"
        blocked_task.status = "open"
        blocked_task.title = "Blocked"

        mock_task_manager.list_tasks.return_value = [stale_task]
        mock_task_manager.list_blocked_tasks.return_value = [blocked_task]

        monitor = TaskMonitor(task_manager=mock_task_manager)
        result = monitor.check()

        assert "summary" in result
        assert result["summary"]["stale_count"] == 1
        assert result["summary"]["blocked_count"] == 1
        assert "checked_at" in result["summary"]
