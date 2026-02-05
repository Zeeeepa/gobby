"""
Tests for gobby.mcp_proxy.tools.orchestration.cleanup module.

Tests for the approve_and_cleanup orchestration tool.
"""

from unittest.mock import MagicMock

import pytest

from gobby.mcp_proxy.tools.internal import InternalToolRegistry

pytestmark = pytest.mark.unit


class MockTask:
    """Mock task object for tests."""

    def __init__(
        self,
        id: str = "task-123",
        seq_num: int = 123,
        title: str = "Test task",
        status: str = "needs_review",
        closed_at: str | None = None,
        closed_commit_sha: str | None = None,
    ):
        self.id = id
        self.seq_num = seq_num
        self.title = title
        self.status = status
        self.closed_at = closed_at
        self.closed_commit_sha = closed_commit_sha


class MockWorktree:
    """Mock worktree object for tests."""

    def __init__(
        self,
        id: str = "wt-123",
        branch_name: str = "feature/test",
        worktree_path: str = "/tmp/worktree",
        base_branch: str = "main",
        status: str = "active",
        task_id: str | None = "task-123",
    ):
        self.id = id
        self.branch_name = branch_name
        self.worktree_path = worktree_path
        self.base_branch = base_branch
        self.status = status
        self.task_id = task_id


class MockDeleteResult:
    """Mock git delete result."""

    def __init__(self, success: bool = True, message: str = ""):
        self.success = success
        self.message = message


@pytest.fixture
def mock_task_manager():
    """Create a mock task manager."""
    manager = MagicMock()
    manager.get_task = MagicMock(return_value=MockTask())
    manager.update_task = MagicMock()
    return manager


@pytest.fixture
def mock_worktree_storage():
    """Create a mock worktree storage."""
    storage = MagicMock()
    storage.get = MagicMock(return_value=MockWorktree())
    storage.get_by_task = MagicMock(return_value=MockWorktree())
    storage.delete = MagicMock()
    storage.mark_merged = MagicMock()
    return storage


@pytest.fixture
def mock_git_manager():
    """Create a mock git manager."""
    manager = MagicMock()
    manager.delete_worktree = MagicMock(return_value=MockDeleteResult(success=True))
    manager._run_git = MagicMock(return_value=MagicMock(returncode=0, stdout="abc123", stderr=""))
    return manager


@pytest.fixture
def cleanup_registry(mock_task_manager, mock_worktree_storage, mock_git_manager):
    """Create a registry with cleanup tools."""
    from gobby.mcp_proxy.tools.orchestration.cleanup import register_cleanup

    registry = InternalToolRegistry(
        name="gobby-orchestration",
        description="Task orchestration tools",
    )
    register_cleanup(
        registry=registry,
        task_manager=mock_task_manager,
        worktree_storage=mock_worktree_storage,
        git_manager=mock_git_manager,
        default_project_id="test-project",
    )
    return registry


class TestRegisterCleanup:
    """Tests for register_cleanup function."""

    def test_registers_approve_and_cleanup_tool(self, cleanup_registry) -> None:
        """Test that approve_and_cleanup tool is registered."""
        tools = cleanup_registry.list_tools()
        tool_names = [t["name"] for t in tools]

        assert "approve_and_cleanup" in tool_names


class TestApproveAndCleanup:
    """Tests for approve_and_cleanup tool."""

    @pytest.mark.asyncio
    async def test_approve_and_cleanup_success(
        self, cleanup_registry, mock_task_manager, mock_worktree_storage, mock_git_manager
    ):
        """Test successful approve and cleanup."""
        mock_task_manager.get_task.return_value = MockTask(
            id="task-123",
            status="needs_review",
        )

        result = await cleanup_registry.call(
            "approve_and_cleanup",
            {"task_id": "task-123"},
        )

        assert "error" not in result
        # Task should be updated to closed
        mock_task_manager.update_task.assert_called()
        # Worktree should be deleted
        mock_git_manager.delete_worktree.assert_called()

    @pytest.mark.asyncio
    async def test_approve_and_cleanup_task_not_in_review(
        self, cleanup_registry, mock_task_manager
    ):
        """Test approve_and_cleanup fails if task not in needs_review status."""
        mock_task_manager.get_task.return_value = MockTask(
            id="task-123",
            status="open",  # Not in needs_review
        )

        result = await cleanup_registry.call(
            "approve_and_cleanup",
            {"task_id": "task-123"},
        )

        assert "error" in result
        assert "needs_review" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_approve_and_cleanup_task_not_found(self, cleanup_registry, mock_task_manager):
        """Test approve_and_cleanup fails if task not found."""
        mock_task_manager.get_task.return_value = None

        result = await cleanup_registry.call(
            "approve_and_cleanup",
            {"task_id": "nonexistent"},
        )

        assert "error" in result
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_approve_and_cleanup_no_worktree(
        self, cleanup_registry, mock_task_manager, mock_worktree_storage
    ):
        """Test approve_and_cleanup succeeds if no worktree exists."""
        mock_task_manager.get_task.return_value = MockTask(status="needs_review")
        mock_worktree_storage.get_by_task.return_value = None

        result = await cleanup_registry.call(
            "approve_and_cleanup",
            {"task_id": "task-123"},
        )

        # Should still succeed - just skip worktree cleanup
        assert "error" not in result
        assert result["worktree_deleted"] is False

    @pytest.mark.asyncio
    async def test_approve_and_cleanup_delete_worktree_fails(
        self, cleanup_registry, mock_task_manager, mock_git_manager
    ):
        """Test approve_and_cleanup handles worktree deletion failure."""
        mock_task_manager.get_task.return_value = MockTask(status="needs_review")
        mock_git_manager.delete_worktree.return_value = MockDeleteResult(
            success=False, message="Permission denied"
        )

        result = await cleanup_registry.call(
            "approve_and_cleanup",
            {"task_id": "task-123"},
        )

        # Should succeed (task closed) but report worktree not deleted
        assert "error" not in result
        assert result["worktree_deleted"] is False

    @pytest.mark.asyncio
    async def test_approve_and_cleanup_with_push_branch(
        self, cleanup_registry, mock_task_manager, mock_git_manager
    ):
        """Test approve_and_cleanup with push_branch option."""
        mock_task_manager.get_task.return_value = MockTask(status="needs_review")

        result = await cleanup_registry.call(
            "approve_and_cleanup",
            {"task_id": "task-123", "push_branch": True},
        )

        assert "error" not in result
        # Verify push was attempted
        push_calls = [
            call for call in mock_git_manager._run_git.call_args_list if "push" in str(call)
        ]
        assert len(push_calls) > 0

    @pytest.mark.asyncio
    async def test_approve_and_cleanup_with_force(
        self, cleanup_registry, mock_task_manager, mock_git_manager
    ):
        """Test approve_and_cleanup with force option."""
        mock_task_manager.get_task.return_value = MockTask(status="needs_review")

        result = await cleanup_registry.call(
            "approve_and_cleanup",
            {"task_id": "task-123", "force": True},
        )

        assert "error" not in result
        # Verify force was passed to delete_worktree
        mock_git_manager.delete_worktree.assert_called_once()
        call_kwargs = mock_git_manager.delete_worktree.call_args.kwargs
        assert call_kwargs.get("force") is True

    @pytest.mark.asyncio
    async def test_approve_and_cleanup_skip_worktree_deletion(
        self, cleanup_registry, mock_task_manager, mock_git_manager
    ):
        """Test approve_and_cleanup with delete_worktree=False."""
        mock_task_manager.get_task.return_value = MockTask(status="needs_review")

        result = await cleanup_registry.call(
            "approve_and_cleanup",
            {"task_id": "task-123", "delete_worktree": False},
        )

        assert "error" not in result
        # Verify delete_worktree was NOT called
        mock_git_manager.delete_worktree.assert_not_called()

    @pytest.mark.asyncio
    async def test_approve_and_cleanup_updates_task_status(
        self, cleanup_registry, mock_task_manager
    ):
        """Test that task status is updated to closed."""
        task = MockTask(id="task-123", status="needs_review")
        mock_task_manager.get_task.return_value = task

        result = await cleanup_registry.call(
            "approve_and_cleanup",
            {"task_id": "task-123"},
        )

        assert "error" not in result
        # Verify update_task was called with correct status
        mock_task_manager.update_task.assert_called()
        update_call = mock_task_manager.update_task.call_args
        # Should have set status to closed
        assert "status" in update_call.kwargs or (
            len(update_call.args) > 1 and "closed" in str(update_call)
        )


class TestApproveAndCleanupNoGitManager:
    """Tests for approve_and_cleanup when git manager is not available."""

    @pytest.fixture
    def cleanup_registry_no_git(self, mock_task_manager, mock_worktree_storage):
        """Create a registry without git manager."""
        from gobby.mcp_proxy.tools.orchestration.cleanup import register_cleanup

        registry = InternalToolRegistry(
            name="gobby-orchestration",
            description="Task orchestration tools",
        )
        register_cleanup(
            registry=registry,
            task_manager=mock_task_manager,
            worktree_storage=mock_worktree_storage,
            git_manager=None,  # No git manager
            default_project_id="test-project",
        )
        return registry

    @pytest.mark.asyncio
    async def test_approve_and_cleanup_without_git_manager(
        self, cleanup_registry_no_git, mock_task_manager, mock_worktree_storage
    ):
        """Test approve_and_cleanup works without git manager (skip worktree ops)."""
        mock_task_manager.get_task.return_value = MockTask(status="needs_review")

        result = await cleanup_registry_no_git.call(
            "approve_and_cleanup",
            {"task_id": "task-123"},
        )

        # Should succeed but skip worktree deletion
        assert "error" not in result
        assert result["worktree_deleted"] is False


class TestApproveAndCleanupTaskResolution:
    """Tests for task ID resolution in approve_and_cleanup."""

    @pytest.mark.asyncio
    async def test_approve_and_cleanup_accepts_seq_num_format(
        self, cleanup_registry, mock_task_manager
    ):
        """Test approve_and_cleanup accepts #N format."""
        mock_task_manager.get_task.return_value = MockTask(
            id="task-uuid", seq_num=5927, status="needs_review"
        )

        result = await cleanup_registry.call(
            "approve_and_cleanup",
            {"task_id": "#5927"},
        )

        assert "error" not in result

    @pytest.mark.asyncio
    async def test_approve_and_cleanup_accepts_uuid_format(
        self, cleanup_registry, mock_task_manager
    ):
        """Test approve_and_cleanup accepts UUID format."""
        mock_task_manager.get_task.return_value = MockTask(
            id="e4860c60-bd55-4131-be9b-7fe774590c2b", status="needs_review"
        )

        result = await cleanup_registry.call(
            "approve_and_cleanup",
            {"task_id": "e4860c60-bd55-4131-be9b-7fe774590c2b"},
        )

        assert "error" not in result
