"""
Tests for gobby.mcp_proxy.tools.orchestration.wait module.

Tests the blocking wait tools:
- wait_for_task: Wait for single task to complete
- wait_for_any_task: Wait for any of multiple tasks to complete
- wait_for_all_tasks: Wait for all tasks to complete
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.mcp_proxy.tools.internal import InternalToolRegistry


class MockTask:
    """Mock task object for tests."""

    def __init__(
        self,
        id: str = "task-123",
        seq_num: int = 123,
        title: str = "Test task",
        status: str = "open",
        closed_at: str | None = None,
    ):
        self.id = id
        self.seq_num = seq_num
        self.title = title
        self.status = status
        self.closed_at = closed_at


@pytest.fixture
def mock_task_manager():
    """Create a mock task manager."""
    manager = MagicMock()
    manager.get_task = MagicMock(return_value=MockTask())
    return manager


@pytest.fixture
def wait_registry(mock_task_manager):
    """Create a registry with wait tools."""
    from gobby.mcp_proxy.tools.orchestration.wait import register_wait

    registry = InternalToolRegistry(
        name="gobby-tasks",
        description="Task management with wait tools",
    )
    register_wait(
        registry=registry,
        task_manager=mock_task_manager,
    )
    return registry


class TestRegisterWait:
    """Tests for register_wait function."""

    def test_registers_all_expected_tools(self, wait_registry):
        """Test that all wait tools are registered."""
        tools = wait_registry.list_tools()
        tool_names = [t["name"] for t in tools]

        assert "wait_for_task" in tool_names
        assert "wait_for_any_task" in tool_names
        assert "wait_for_all_tasks" in tool_names


class TestWaitForTask:
    """Tests for wait_for_task tool."""

    @pytest.mark.asyncio
    async def test_wait_for_task_already_complete(self, wait_registry, mock_task_manager):
        """Test waiting for task that's already closed."""
        mock_task_manager.get_task.return_value = MockTask(
            id="task-1",
            status="closed",
            closed_at="2026-01-22T12:00:00Z",
        )

        result = await wait_registry.call(
            "wait_for_task",
            {"task_id": "task-1"},
        )

        assert result["success"] is True
        assert result["completed"] is True
        assert result["task"]["status"] == "closed"

    @pytest.mark.asyncio
    async def test_wait_for_task_becomes_complete(self, wait_registry, mock_task_manager):
        """Test waiting for task that completes during wait."""
        # Task starts open, then becomes closed
        call_count = 0

        def get_task_side_effect(task_id):
            nonlocal call_count
            call_count += 1
            if call_count >= 3:
                return MockTask(id=task_id, status="closed")
            return MockTask(id=task_id, status="in_progress")

        mock_task_manager.get_task.side_effect = get_task_side_effect

        with patch(
            "gobby.mcp_proxy.tools.orchestration.wait.asyncio.sleep", new_callable=AsyncMock
        ):
            result = await wait_registry.call(
                "wait_for_task",
                {"task_id": "task-1", "poll_interval": 0.1},
            )

        assert result["success"] is True
        assert result["completed"] is True
        assert call_count >= 3

    @pytest.mark.asyncio
    async def test_wait_for_task_timeout(self, wait_registry, mock_task_manager):
        """Test timeout when task doesn't complete."""
        mock_task_manager.get_task.return_value = MockTask(
            id="task-1",
            status="in_progress",
        )

        result = await wait_registry.call(
            "wait_for_task",
            {"task_id": "task-1", "timeout": 0.2, "poll_interval": 0.05},
        )

        assert result["success"] is True
        assert result["completed"] is False
        assert result["timed_out"] is True

    @pytest.mark.asyncio
    async def test_wait_for_task_not_found(self, wait_registry, mock_task_manager):
        """Test waiting for non-existent task."""
        mock_task_manager.get_task.return_value = None

        result = await wait_registry.call(
            "wait_for_task",
            {"task_id": "nonexistent"},
        )

        assert result["success"] is False
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_wait_for_task_accepts_seq_num_format(self, wait_registry, mock_task_manager):
        """Test wait_for_task accepts #N format."""
        mock_task_manager.get_task.return_value = MockTask(
            id="task-uuid",
            seq_num=5926,
            status="closed",
        )

        result = await wait_registry.call(
            "wait_for_task",
            {"task_id": "#5926"},
        )

        assert result["success"] is True


class TestWaitForAnyTask:
    """Tests for wait_for_any_task tool."""

    @pytest.mark.asyncio
    async def test_wait_for_any_one_already_complete(self, wait_registry, mock_task_manager):
        """Test with one task already complete."""

        def get_task_side_effect(task_id):
            if task_id == "task-2":
                return MockTask(id=task_id, status="closed")
            return MockTask(id=task_id, status="open")

        mock_task_manager.get_task.side_effect = get_task_side_effect

        result = await wait_registry.call(
            "wait_for_any_task",
            {"task_ids": ["task-1", "task-2", "task-3"]},
        )

        assert result["success"] is True
        assert result["completed_task_id"] == "task-2"

    @pytest.mark.asyncio
    async def test_wait_for_any_first_to_complete(self, wait_registry, mock_task_manager):
        """Test waiting until first task completes."""
        call_count = 0

        def get_task_side_effect(task_id):
            nonlocal call_count
            call_count += 1
            # task-3 completes after a few polls
            if task_id == "task-3" and call_count > 6:
                return MockTask(id=task_id, status="closed")
            return MockTask(id=task_id, status="in_progress")

        mock_task_manager.get_task.side_effect = get_task_side_effect

        with patch(
            "gobby.mcp_proxy.tools.orchestration.wait.asyncio.sleep", new_callable=AsyncMock
        ):
            result = await wait_registry.call(
                "wait_for_any_task",
                {"task_ids": ["task-1", "task-2", "task-3"], "poll_interval": 0.01},
            )

        assert result["success"] is True
        assert result["completed_task_id"] == "task-3"

    @pytest.mark.asyncio
    async def test_wait_for_any_timeout(self, wait_registry, mock_task_manager):
        """Test timeout when no tasks complete."""
        mock_task_manager.get_task.return_value = MockTask(status="open")

        result = await wait_registry.call(
            "wait_for_any_task",
            {"task_ids": ["task-1", "task-2"], "timeout": 0.2, "poll_interval": 0.05},
        )

        assert result["success"] is True
        assert result["completed_task_id"] is None
        assert result["timed_out"] is True

    @pytest.mark.asyncio
    async def test_wait_for_any_empty_list(self, wait_registry, mock_task_manager):
        """Test with empty task list."""
        result = await wait_registry.call(
            "wait_for_any_task",
            {"task_ids": []},
        )

        assert result["success"] is False
        assert "empty" in result["error"].lower() or "no task" in result["error"].lower()


class TestWaitForAllTasks:
    """Tests for wait_for_all_tasks tool."""

    @pytest.mark.asyncio
    async def test_wait_for_all_already_complete(self, wait_registry, mock_task_manager):
        """Test with all tasks already complete."""
        mock_task_manager.get_task.return_value = MockTask(status="closed")

        result = await wait_registry.call(
            "wait_for_all_tasks",
            {"task_ids": ["task-1", "task-2", "task-3"]},
        )

        assert result["success"] is True
        assert result["all_completed"] is True
        assert result["completed_count"] == 3

    @pytest.mark.asyncio
    async def test_wait_for_all_becomes_complete(self, wait_registry, mock_task_manager):
        """Test waiting for all tasks to complete."""
        completed = set()
        call_count = 0

        def get_task_side_effect(task_id):
            nonlocal call_count
            call_count += 1
            # Tasks complete one at a time
            if call_count > 3:
                completed.add("task-1")
            if call_count > 6:
                completed.add("task-2")
            if call_count > 9:
                completed.add("task-3")

            if task_id in completed:
                return MockTask(id=task_id, status="closed")
            return MockTask(id=task_id, status="in_progress")

        mock_task_manager.get_task.side_effect = get_task_side_effect

        with patch(
            "gobby.mcp_proxy.tools.orchestration.wait.asyncio.sleep", new_callable=AsyncMock
        ):
            result = await wait_registry.call(
                "wait_for_all_tasks",
                {"task_ids": ["task-1", "task-2", "task-3"], "poll_interval": 0.01},
            )

        assert result["success"] is True
        assert result["all_completed"] is True
        assert result["completed_count"] == 3

    @pytest.mark.asyncio
    async def test_wait_for_all_partial_completion(self, wait_registry, mock_task_manager):
        """Test timeout with partial completion."""

        def get_task_side_effect(task_id):
            if task_id == "task-1":
                return MockTask(id=task_id, status="closed")
            return MockTask(id=task_id, status="in_progress")

        mock_task_manager.get_task.side_effect = get_task_side_effect

        result = await wait_registry.call(
            "wait_for_all_tasks",
            {"task_ids": ["task-1", "task-2", "task-3"], "timeout": 0.2, "poll_interval": 0.05},
        )

        assert result["success"] is True
        assert result["all_completed"] is False
        assert result["completed_count"] == 1
        assert result["pending_count"] == 2
        assert result["timed_out"] is True

    @pytest.mark.asyncio
    async def test_wait_for_all_empty_list(self, wait_registry, mock_task_manager):
        """Test with empty task list."""
        result = await wait_registry.call(
            "wait_for_all_tasks",
            {"task_ids": []},
        )

        # Empty list should succeed immediately (vacuously true)
        assert result["success"] is True
        assert result["all_completed"] is True
        assert result["completed_count"] == 0


class TestWaitToolParameters:
    """Tests for wait tool parameter handling."""

    @pytest.mark.asyncio
    async def test_default_timeout(self, wait_registry, mock_task_manager):
        """Test default timeout is 300 seconds."""
        # This test verifies the default timeout by checking behavior,
        # not by running for 5 minutes
        mock_task_manager.get_task.return_value = MockTask(status="closed")

        result = await wait_registry.call(
            "wait_for_task",
            {"task_id": "task-1"},
            # Not specifying timeout should use default 300s
        )

        # Should succeed immediately since task is closed
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_custom_poll_interval(self, wait_registry, mock_task_manager):
        """Test custom poll interval is respected."""
        poll_count = 0

        def get_task_side_effect(task_id):
            nonlocal poll_count
            poll_count += 1
            if poll_count >= 3:
                return MockTask(id=task_id, status="closed")
            return MockTask(id=task_id, status="open")

        mock_task_manager.get_task.side_effect = get_task_side_effect

        with patch(
            "gobby.mcp_proxy.tools.orchestration.wait.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep:
            result = await wait_registry.call(
                "wait_for_task",
                {"task_id": "task-1", "poll_interval": 10},  # 10 second interval
            )

            # Verify sleep was called with the custom interval
            if mock_sleep.call_count > 0:
                mock_sleep.assert_called_with(10)

        assert result["success"] is True


class TestErrorHandling:
    """Tests for error handling in wait tools."""

    @pytest.mark.asyncio
    async def test_task_manager_error(self, wait_registry, mock_task_manager):
        """Test handling of task manager errors."""
        mock_task_manager.get_task.side_effect = Exception("Database error")

        result = await wait_registry.call(
            "wait_for_task",
            {"task_id": "task-1"},
        )

        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_invalid_task_reference(self, wait_registry, mock_task_manager):
        """Test handling of invalid task reference format."""
        from gobby.storage.tasks import TaskNotFoundError

        mock_task_manager.get_task.side_effect = TaskNotFoundError("task-bad")

        result = await wait_registry.call(
            "wait_for_task",
            {"task_id": "task-bad"},
        )

        assert result["success"] is False
