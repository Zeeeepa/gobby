"""Additional tests for AgentLifecycleMonitor."""

import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from gobby.agents.lifecycle_monitor import AgentLifecycleMonitor
from gobby.storage.agents import AgentRun

pytestmark = pytest.mark.unit


class TestRecoverTaskFromFailedAgent:
    """Tests for _recover_task_from_failed_agent."""

    @pytest.mark.asyncio
    async def test_recover_task_with_task_id(self):
        """Task recovered using explicit task_id."""
        mock_run_mgr = MagicMock()
        mock_task_mgr = MagicMock()
        mock_db = MagicMock()
        mock_stall = MagicMock()

        monitor = AgentLifecycleMonitor(
            agent_run_manager=mock_run_mgr,
            db=mock_db,
            task_manager=mock_task_mgr,
            check_interval_seconds=1.0,
        )
        monitor._stall_classifier = mock_stall

        # Setup mock db run
        db_run = AgentRun(
            id="run-1",
            parent_session_id="parent-1",
            task_id="task-123",
            provider="claude",
            prompt="do it",
            status="error",
            error="API failed",
            created_at="2024-01-01T00:00:00Z",
        )
        mock_run_mgr.get.return_value = db_run

        # Setup mock task
        mock_task = MagicMock()
        mock_task.status = "in_progress"
        mock_task.seq_num = 5
        mock_task_mgr.get_task.return_value = mock_task
        mock_stall.is_provider_error.return_value = True

        await monitor._recover_task_from_failed_agent("run-1")

        mock_task_mgr.get_task.assert_called_once_with("task-123")
        mock_task_mgr.update_task.assert_called_once_with(
            "task-123", status="open", assignee=None
        )

    @pytest.mark.asyncio
    async def test_recover_task_fallback_assignee(self):
        """Task recovered using child_session_id as fallback."""
        mock_run_mgr = MagicMock()
        mock_task_mgr = MagicMock()
        mock_db = MagicMock()
        mock_stall = MagicMock()

        monitor = AgentLifecycleMonitor(
            agent_run_manager=mock_run_mgr,
            db=mock_db,
            task_manager=mock_task_mgr,
        )
        monitor._stall_classifier = mock_stall

        # Setup mock db run (no task_id, but has child_session_id)
        db_run = AgentRun(
            id="run-2",
            parent_session_id="parent-1",
            child_session_id="child-123",
            task_id=None,
            provider="claude",
            prompt="do it",
            status="error",
            error="",
            created_at="2024-01-01",
        )
        mock_run_mgr.get.return_value = db_run

        mock_fallback_task = MagicMock()
        mock_fallback_task.id = "task-fallback"
        mock_fallback_task.status = "in_progress"
        mock_fallback_task.seq_num = None
        mock_task_mgr.list_tasks.return_value = [mock_fallback_task]
        mock_task_mgr.get_task.return_value = mock_fallback_task
        mock_stall.is_provider_error.return_value = False

        await monitor._recover_task_from_failed_agent("run-2")

        mock_task_mgr.list_tasks.assert_called_once_with(
            status="in_progress", assignee="child-123"
        )
        mock_task_mgr.get_task.assert_called_once_with("task-fallback")
        mock_task_mgr.update_task.assert_called_once_with(
            "task-fallback", status="open", assignee=None
        )

    @pytest.mark.asyncio
    async def test_recover_task_no_task_manager(self):
        """Does nothing if no task_manager is configured."""
        monitor = AgentLifecycleMonitor(
            agent_run_manager=MagicMock(),
            db=MagicMock(),
        )
        await monitor._recover_task_from_failed_agent("run-1")
        # Should return safely

    @pytest.mark.asyncio
    async def test_recover_task_not_in_progress(self):
        """Does not recover task if it is not in_progress."""
        mock_run_mgr = MagicMock()
        mock_task_mgr = MagicMock()
        monitor = AgentLifecycleMonitor(
            agent_run_manager=mock_run_mgr,
            db=MagicMock(),
            task_manager=mock_task_mgr,
        )

        db_run = AgentRun(
            id="run-1",
            parent_session_id="p",
            task_id="task-123",
            provider="claude",
            prompt="p",
            status="error",
            created_at="2024-01-01",
        )
        mock_run_mgr.get.return_value = db_run

        mock_task = MagicMock()
        mock_task.status = "completed"
        mock_task_mgr.get_task.return_value = mock_task

        await monitor._recover_task_from_failed_agent("run-1")
        mock_task_mgr.update_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleanup_stale_pending_runs(self):
        """Tests that cleanup_stale_pending_runs calls the manager method correctly."""
        mock_run_mgr = MagicMock()
        mock_run_mgr.cleanup_stale_pending_runs.return_value = 5
        
        monitor = AgentLifecycleMonitor(
            agent_run_manager=mock_run_mgr,
            db=MagicMock(),
        )
        
        cleaned = await monitor.cleanup_stale_pending_runs()
        assert cleaned == 5
        mock_run_mgr.cleanup_stale_pending_runs.assert_called_once()
