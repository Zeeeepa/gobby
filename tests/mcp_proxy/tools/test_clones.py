"""Tests for gobby.mcp_proxy.tools.clones module.

Tests for the gobby-clones MCP server tools:
- create_clone
- get_clone
- list_clones
- delete_clone
- sync_clone
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.agents.spawn_executor import SpawnResult
from gobby.storage.clones import Clone

pytestmark = pytest.mark.integration


@pytest.fixture
def mock_clone_storage():
    """Create mock clone storage."""
    return MagicMock()


@pytest.fixture
def mock_git_manager():
    """Create mock git manager."""
    manager = MagicMock()
    manager.repo_path = Path("/tmp/repo")
    return manager


@pytest.fixture
def registry(mock_clone_storage, mock_git_manager):
    """Create registry with clone tools."""
    from gobby.mcp_proxy.tools.clones import create_clones_registry

    return create_clones_registry(
        clone_storage=mock_clone_storage,
        git_manager=mock_git_manager,
        project_id="proj-1",
    )


class TestClonesRegistryCreation:
    """Tests for registry creation."""

    def test_creates_registry_with_expected_tools(self, registry):
        """Registry has all expected tools."""
        tools = registry.list_tools()
        tool_names = [t["name"] for t in tools]

        assert "create_clone" in tool_names
        assert "get_clone" in tool_names
        assert "list_clones" in tool_names
        assert "delete_clone" in tool_names
        assert "sync_clone" in tool_names


class TestCreateClone:
    """Tests for create_clone tool."""

    @pytest.mark.asyncio
    async def test_create_clone_success(self, registry, mock_clone_storage, mock_git_manager):
        """Create clone successfully."""
        mock_git_manager.shallow_clone.return_value = MagicMock(success=True)
        mock_git_manager.get_remote_url.return_value = "https://github.com/user/repo.git"
        mock_clone_storage.create.return_value = Clone(
            id="clone-123",
            project_id="proj-1",
            branch_name="main",
            clone_path="/tmp/clones/test",
            base_branch="main",
            task_id=None,
            agent_session_id=None,
            status="active",
            remote_url="https://github.com/user/repo.git",
            last_sync_at=None,
            cleanup_after=None,
            created_at="now",
            updated_at="now",
        )

        result = await registry.call(
            "create_clone",
            {"branch_name": "main", "clone_path": "/tmp/clones/test"},
        )

        assert result["success"] is True
        assert result["clone"]["id"] == "clone-123"
        mock_git_manager.shallow_clone.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_clone_git_failure(self, registry, mock_clone_storage, mock_git_manager):
        """Create clone fails when git operation fails."""
        mock_git_manager.shallow_clone.return_value = MagicMock(
            success=False, error="Clone failed"
        )
        mock_git_manager.get_remote_url.return_value = "https://github.com/user/repo.git"

        result = await registry.call(
            "create_clone",
            {"branch_name": "main", "clone_path": "/tmp/clones/test"},
        )

        assert result["success"] is False
        assert "failed" in result["error"].lower()
        mock_clone_storage.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_clone_with_task_id(self, registry, mock_clone_storage, mock_git_manager):
        """Create clone linked to a task."""
        mock_git_manager.shallow_clone.return_value = MagicMock(success=True)
        mock_git_manager.get_remote_url.return_value = "https://github.com/user/repo.git"
        mock_clone_storage.create.return_value = Clone(
            id="clone-123",
            project_id="proj-1",
            branch_name="main",
            clone_path="/tmp/clones/test",
            base_branch="main",
            task_id="task-456",
            agent_session_id=None,
            status="active",
            remote_url="https://github.com/user/repo.git",
            last_sync_at=None,
            cleanup_after=None,
            created_at="now",
            updated_at="now",
        )

        result = await registry.call(
            "create_clone",
            {"branch_name": "main", "clone_path": "/tmp/clones/test", "task_id": "task-456"},
        )

        assert result["success"] is True
        assert result["clone"]["task_id"] == "task-456"


class TestGetClone:
    """Tests for get_clone tool."""

    @pytest.mark.asyncio
    async def test_get_clone_by_id(self, registry, mock_clone_storage):
        """Get clone by ID."""
        mock_clone_storage.get.return_value = Clone(
            id="clone-123",
            project_id="proj-1",
            branch_name="main",
            clone_path="/tmp/clones/test",
            base_branch="main",
            task_id=None,
            agent_session_id=None,
            status="active",
            remote_url="https://github.com/user/repo.git",
            last_sync_at=None,
            cleanup_after=None,
            created_at="now",
            updated_at="now",
        )

        result = await registry.call("get_clone", {"clone_id": "clone-123"})

        assert result["success"] is True
        assert result["clone"]["id"] == "clone-123"
        mock_clone_storage.get.assert_called_once_with("clone-123")

    @pytest.mark.asyncio
    async def test_get_clone_not_found(self, registry, mock_clone_storage):
        """Get clone returns error for nonexistent clone."""
        mock_clone_storage.get.return_value = None

        result = await registry.call("get_clone", {"clone_id": "nonexistent"})

        assert result["success"] is False
        assert "not found" in result["error"].lower()


class TestListClones:
    """Tests for list_clones tool."""

    @pytest.mark.asyncio
    async def test_list_all_clones(self, registry, mock_clone_storage):
        """List all clones."""
        mock_clone_storage.list_clones.return_value = [
            Clone(
                id="clone-1",
                project_id="proj-1",
                branch_name="main",
                clone_path="/tmp/clones/one",
                base_branch="main",
                task_id=None,
                agent_session_id=None,
                status="active",
                remote_url=None,
                last_sync_at=None,
                cleanup_after=None,
                created_at="now",
                updated_at="now",
            ),
            Clone(
                id="clone-2",
                project_id="proj-1",
                branch_name="feature",
                clone_path="/tmp/clones/two",
                base_branch="main",
                task_id=None,
                agent_session_id=None,
                status="stale",
                remote_url=None,
                last_sync_at=None,
                cleanup_after=None,
                created_at="now",
                updated_at="now",
            ),
        ]

        result = await registry.call("list_clones", {})

        assert result["success"] is True
        assert len(result["clones"]) == 2
        assert result["clones"][0]["id"] == "clone-1"
        assert result["clones"][1]["id"] == "clone-2"

    @pytest.mark.asyncio
    async def test_list_clones_with_status_filter(self, registry, mock_clone_storage):
        """List clones filtered by status."""
        mock_clone_storage.list_clones.return_value = []

        await registry.call("list_clones", {"status": "active"})

        mock_clone_storage.list_clones.assert_called_once()
        call_kwargs = mock_clone_storage.list_clones.call_args.kwargs
        assert call_kwargs.get("status") == "active"

    @pytest.mark.asyncio
    async def test_list_clones_empty(self, registry, mock_clone_storage):
        """List clones returns empty list when no clones."""
        mock_clone_storage.list_clones.return_value = []

        result = await registry.call("list_clones", {})

        assert result["success"] is True
        assert result["clones"] == []


class TestDeleteClone:
    """Tests for delete_clone tool."""

    @pytest.mark.asyncio
    async def test_delete_clone_success(self, registry, mock_clone_storage, mock_git_manager):
        """Delete clone successfully."""
        mock_clone_storage.get.return_value = Clone(
            id="clone-123",
            project_id="proj-1",
            branch_name="main",
            clone_path="/tmp/clones/test",
            base_branch="main",
            task_id=None,
            agent_session_id=None,
            status="active",
            remote_url=None,
            last_sync_at=None,
            cleanup_after=None,
            created_at="now",
            updated_at="now",
        )
        mock_git_manager.delete_clone.return_value = MagicMock(success=True)
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 1
        mock_clone_storage.delete.return_value = True

        result = await registry.call("delete_clone", {"clone_id": "clone-123"})

        assert result["success"] is True
        mock_git_manager.delete_clone.assert_called_once()
        mock_clone_storage.delete.assert_called_once_with("clone-123")

    @pytest.mark.asyncio
    async def test_delete_clone_not_found(self, registry, mock_clone_storage):
        """Delete clone returns error for nonexistent clone."""
        mock_clone_storage.get.return_value = None

        result = await registry.call("delete_clone", {"clone_id": "nonexistent"})

        assert result["success"] is False
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_delete_clone_force(self, registry, mock_clone_storage, mock_git_manager):
        """Delete clone with force flag."""
        mock_clone_storage.get.return_value = Clone(
            id="clone-123",
            project_id="proj-1",
            branch_name="main",
            clone_path="/tmp/clones/test",
            base_branch="main",
            task_id=None,
            agent_session_id=None,
            status="active",
            remote_url=None,
            last_sync_at=None,
            cleanup_after=None,
            created_at="now",
            updated_at="now",
        )
        mock_git_manager.delete_clone.return_value = MagicMock(success=True)
        mock_clone_storage.delete.return_value = True

        result = await registry.call(
            "delete_clone", {"clone_id": "clone-123", "force": True}
        )

        assert result["success"] is True
        call_kwargs = mock_git_manager.delete_clone.call_args.kwargs
        assert call_kwargs.get("force") is True


class TestSyncClone:
    """Tests for sync_clone tool."""

    @pytest.mark.asyncio
    async def test_sync_clone_pull_success(self, registry, mock_clone_storage, mock_git_manager):
        """Sync clone pull successfully."""
        mock_clone_storage.get.return_value = Clone(
            id="clone-123",
            project_id="proj-1",
            branch_name="main",
            clone_path="/tmp/clones/test",
            base_branch="main",
            task_id=None,
            agent_session_id=None,
            status="active",
            remote_url=None,
            last_sync_at=None,
            cleanup_after=None,
            created_at="now",
            updated_at="now",
        )
        mock_git_manager.sync_clone.return_value = MagicMock(success=True)

        result = await registry.call(
            "sync_clone", {"clone_id": "clone-123", "direction": "pull"}
        )

        assert result["success"] is True
        mock_git_manager.sync_clone.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_clone_push_success(self, registry, mock_clone_storage, mock_git_manager):
        """Sync clone push successfully."""
        mock_clone_storage.get.return_value = Clone(
            id="clone-123",
            project_id="proj-1",
            branch_name="main",
            clone_path="/tmp/clones/test",
            base_branch="main",
            task_id=None,
            agent_session_id=None,
            status="active",
            remote_url=None,
            last_sync_at=None,
            cleanup_after=None,
            created_at="now",
            updated_at="now",
        )
        mock_git_manager.sync_clone.return_value = MagicMock(success=True)

        result = await registry.call(
            "sync_clone", {"clone_id": "clone-123", "direction": "push"}
        )

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_sync_clone_not_found(self, registry, mock_clone_storage):
        """Sync clone returns error for nonexistent clone."""
        mock_clone_storage.get.return_value = None

        result = await registry.call(
            "sync_clone", {"clone_id": "nonexistent", "direction": "pull"}
        )

        assert result["success"] is False
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_sync_clone_failure(self, registry, mock_clone_storage, mock_git_manager):
        """Sync clone handles sync failure."""
        mock_clone_storage.get.return_value = Clone(
            id="clone-123",
            project_id="proj-1",
            branch_name="main",
            clone_path="/tmp/clones/test",
            base_branch="main",
            task_id=None,
            agent_session_id=None,
            status="active",
            remote_url=None,
            last_sync_at=None,
            cleanup_after=None,
            created_at="now",
            updated_at="now",
        )
        mock_git_manager.sync_clone.return_value = MagicMock(
            success=False, error="Network error"
        )

        result = await registry.call(
            "sync_clone", {"clone_id": "clone-123", "direction": "pull"}
        )

        assert result["success"] is False


class TestSpawnAgentInClone:
    """Tests for spawn_agent_in_clone tool."""

    @pytest.fixture
    def registry_with_runner(self, mock_clone_storage, mock_git_manager):
        """Create registry with clone tools and agent runner."""
        from unittest.mock import MagicMock

        from gobby.mcp_proxy.tools.clones import create_clones_registry

        mock_runner = MagicMock()
        mock_runner.can_spawn.return_value = (True, None, 1)

        # Mock prepare_run to return a context with session and run
        mock_context = MagicMock()
        mock_context.session = MagicMock()
        mock_context.session.id = "child-session-123"
        mock_context.session.agent_depth = 1
        mock_context.run = MagicMock()
        mock_context.run.id = "run-123"
        mock_runner.prepare_run.return_value = mock_context
        mock_runner._child_session_manager = MagicMock()
        mock_runner._child_session_manager.max_agent_depth = 3

        return create_clones_registry(
            clone_storage=mock_clone_storage,
            git_manager=mock_git_manager,
            project_id="proj-1",
            agent_runner=mock_runner,
        )

    @pytest.mark.asyncio
    async def test_spawn_agent_in_clone_creates_new_clone(
        self, registry_with_runner, mock_clone_storage, mock_git_manager
    ):
        """Spawn agent creates clone if it doesn't exist."""
        # Mock isolation handler that creates a new clone
        mock_handler = MagicMock()
        mock_isolation_ctx = MagicMock()
        mock_isolation_ctx.cwd = "/tmp/clones/test"
        mock_isolation_ctx.branch_name = "feature/test"
        mock_isolation_ctx.worktree_id = None
        mock_isolation_ctx.clone_id = "clone-123"
        mock_handler.prepare_environment = AsyncMock(return_value=mock_isolation_ctx)
        mock_handler.build_context_prompt.return_value = "Enhanced prompt"

        # Mock spawn result
        mock_spawn_result = SpawnResult(
            success=True,
            run_id="run-123",
            child_session_id="child-session-123",
            status="running",
            pid=12345,
        )

        with (
            patch(
                "gobby.mcp_proxy.tools.spawn_agent.get_project_context",
                return_value={"id": "proj-1", "project_path": "/tmp/repo"},
            ),
            patch(
                "gobby.mcp_proxy.tools.spawn_agent.get_isolation_handler",
                return_value=mock_handler,
            ),
            patch(
                "gobby.mcp_proxy.tools.spawn_agent.execute_spawn",
                AsyncMock(return_value=mock_spawn_result),
            ),
        ):
            result = await registry_with_runner.call(
                "spawn_agent_in_clone",
                {
                    "prompt": "Implement feature X",
                    "branch_name": "feature/test",
                    "parent_session_id": "parent-123",
                },
            )

        assert result["success"] is True
        assert result["clone_id"] == "clone-123"
        assert "run_id" in result

    @pytest.mark.asyncio
    async def test_spawn_agent_in_clone_uses_existing_clone(
        self, registry_with_runner, mock_clone_storage, mock_git_manager
    ):
        """Spawn agent uses existing clone if branch exists."""
        # Mock isolation handler that reuses an existing clone
        mock_handler = MagicMock()
        mock_isolation_ctx = MagicMock()
        mock_isolation_ctx.cwd = "/tmp/clones/existing"
        mock_isolation_ctx.branch_name = "feature/test"
        mock_isolation_ctx.worktree_id = None
        mock_isolation_ctx.clone_id = "clone-existing"
        mock_handler.prepare_environment = AsyncMock(return_value=mock_isolation_ctx)
        mock_handler.build_context_prompt.return_value = "Enhanced prompt"

        # Mock spawn result
        mock_spawn_result = SpawnResult(
            success=True,
            run_id="run-123",
            child_session_id="child-session-123",
            status="running",
            pid=12345,
        )

        with (
            patch(
                "gobby.mcp_proxy.tools.spawn_agent.get_project_context",
                return_value={"id": "proj-1", "project_path": "/tmp/repo"},
            ),
            patch(
                "gobby.mcp_proxy.tools.spawn_agent.get_isolation_handler",
                return_value=mock_handler,
            ),
            patch(
                "gobby.mcp_proxy.tools.spawn_agent.execute_spawn",
                AsyncMock(return_value=mock_spawn_result),
            ),
        ):
            result = await registry_with_runner.call(
                "spawn_agent_in_clone",
                {
                    "prompt": "Implement feature X",
                    "branch_name": "feature/test",
                    "parent_session_id": "parent-123",
                },
            )

        assert result["success"] is True
        assert result["clone_id"] == "clone-existing"

    @pytest.mark.asyncio
    async def test_spawn_agent_in_clone_requires_parent_session(
        self, registry_with_runner
    ):
        """Spawn agent requires parent_session_id."""
        result = await registry_with_runner.call(
            "spawn_agent_in_clone",
            {
                "prompt": "Implement feature X",
                "branch_name": "feature/test",
                # Missing parent_session_id
            },
        )

        assert result["success"] is False
        assert "parent_session_id" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_spawn_agent_in_clone_no_runner(
        self, mock_clone_storage, mock_git_manager
    ):
        """Spawn agent fails when runner not configured."""
        from gobby.mcp_proxy.tools.clones import create_clones_registry

        # Create registry without agent_runner
        registry = create_clones_registry(
            clone_storage=mock_clone_storage,
            git_manager=mock_git_manager,
            project_id="proj-1",
            agent_runner=None,
        )

        result = await registry.call(
            "spawn_agent_in_clone",
            {
                "prompt": "Implement feature X",
                "branch_name": "feature/test",
                "parent_session_id": "parent-123",
            },
        )

        assert result["success"] is False
        assert "not configured" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_spawn_agent_in_clone_depth_exceeded(
        self, mock_clone_storage, mock_git_manager
    ):
        """Spawn agent fails when depth limit exceeded."""
        from unittest.mock import MagicMock

        from gobby.mcp_proxy.tools.clones import create_clones_registry

        mock_runner = MagicMock()
        mock_runner.can_spawn.return_value = (False, "Max depth exceeded", 4)

        registry = create_clones_registry(
            clone_storage=mock_clone_storage,
            git_manager=mock_git_manager,
            project_id="proj-1",
            agent_runner=mock_runner,
        )

        result = await registry.call(
            "spawn_agent_in_clone",
            {
                "prompt": "Implement feature X",
                "branch_name": "feature/test",
                "parent_session_id": "parent-123",
            },
        )

        assert result["success"] is False
        assert "depth" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_spawn_agent_in_clone_with_task_id(
        self, registry_with_runner, mock_clone_storage, mock_git_manager
    ):
        """Spawn agent can be linked to a task."""
        # Mock isolation handler
        mock_handler = MagicMock()
        mock_isolation_ctx = MagicMock()
        mock_isolation_ctx.cwd = "/tmp/clones/test"
        mock_isolation_ctx.branch_name = "feature/test"
        mock_isolation_ctx.worktree_id = None
        mock_isolation_ctx.clone_id = "clone-123"
        mock_handler.prepare_environment = AsyncMock(return_value=mock_isolation_ctx)
        mock_handler.build_context_prompt.return_value = "Enhanced prompt"

        # Mock spawn result
        mock_spawn_result = SpawnResult(
            success=True,
            run_id="run-123",
            child_session_id="child-session-123",
            status="running",
            pid=12345,
        )

        with (
            patch(
                "gobby.mcp_proxy.tools.spawn_agent.get_project_context",
                return_value={"id": "proj-1", "project_path": "/tmp/repo"},
            ),
            patch(
                "gobby.mcp_proxy.tools.spawn_agent.get_isolation_handler",
                return_value=mock_handler,
            ),
            patch(
                "gobby.mcp_proxy.tools.spawn_agent.execute_spawn",
                AsyncMock(return_value=mock_spawn_result),
            ),
        ):
            result = await registry_with_runner.call(
                "spawn_agent_in_clone",
                {
                    "prompt": "Implement feature X",
                    "branch_name": "feature/test",
                    "parent_session_id": "parent-123",
                    "task_id": "task-456",
                },
            )

        assert result["success"] is True
        # Task ID is now handled by spawn_agent_impl via task_manager
        assert result["clone_id"] == "clone-123"


class TestSpawnAgentInCloneDeprecation:
    """Tests for spawn_agent_in_clone deprecation warning."""

    @pytest.fixture
    def registry_with_runner(self, mock_clone_storage, mock_git_manager):
        """Create registry with clone tools and agent runner."""
        from unittest.mock import MagicMock

        from gobby.mcp_proxy.tools.clones import create_clones_registry

        mock_runner = MagicMock()
        mock_runner.can_spawn.return_value = (True, None, 1)

        # Mock prepare_run to return a context with session and run
        mock_context = MagicMock()
        mock_context.session = MagicMock()
        mock_context.session.id = "child-session-123"
        mock_context.session.agent_depth = 1
        mock_context.run = MagicMock()
        mock_context.run.id = "run-123"
        mock_runner.prepare_run.return_value = mock_context
        mock_runner._child_session_manager = MagicMock()
        mock_runner._child_session_manager.max_agent_depth = 3

        return create_clones_registry(
            clone_storage=mock_clone_storage,
            git_manager=mock_git_manager,
            project_id="proj-1",
            agent_runner=mock_runner,
        )

    @pytest.mark.asyncio
    async def test_spawn_agent_in_clone_deprecation_warning(
        self, registry_with_runner, mock_clone_storage, mock_git_manager, caplog
    ):
        """Test that spawn_agent_in_clone logs a deprecation warning."""
        import logging
        import warnings

        # Mock isolation handler
        mock_handler = MagicMock()
        mock_isolation_ctx = MagicMock()
        mock_isolation_ctx.cwd = "/tmp/clones/deprecation"
        mock_isolation_ctx.branch_name = "feature/deprecation"
        mock_isolation_ctx.worktree_id = None
        mock_isolation_ctx.clone_id = "clone-deprecation"
        mock_handler.prepare_environment = AsyncMock(return_value=mock_isolation_ctx)
        mock_handler.build_context_prompt.return_value = "Enhanced prompt"

        # Mock spawn result
        mock_spawn_result = SpawnResult(
            success=True,
            run_id="run-123",
            child_session_id="child-session-123",
            status="running",
            pid=12345,
        )

        with (
            patch(
                "gobby.mcp_proxy.tools.spawn_agent.get_project_context",
                return_value={"id": "proj-1", "project_path": "/tmp/repo"},
            ),
            patch(
                "gobby.mcp_proxy.tools.spawn_agent.get_isolation_handler",
                return_value=mock_handler,
            ),
            patch(
                "gobby.mcp_proxy.tools.spawn_agent.execute_spawn",
                AsyncMock(return_value=mock_spawn_result),
            ),
            caplog.at_level(logging.WARNING),
            warnings.catch_warnings(record=True) as w,
        ):
            warnings.simplefilter("always")

            result = await registry_with_runner.call(
                "spawn_agent_in_clone",
                {
                    "prompt": "Implement feature X",
                    "branch_name": "feature/deprecation",
                    "parent_session_id": "parent-123",
                },
            )

        # Should still succeed (backwards compatibility)
        assert result["success"] is True

        # Should log deprecation warning
        assert any(
            "deprecated" in record.message.lower() and "spawn_agent_in_clone" in record.message
            for record in caplog.records
        ), f"Expected deprecation warning for spawn_agent_in_clone, got: {[r.message for r in caplog.records]}"

        # Should emit DeprecationWarning
        deprecation_warnings = [
            warning for warning in w
            if issubclass(warning.category, DeprecationWarning)
            and "spawn_agent_in_clone" in str(warning.message)
        ]
        assert len(deprecation_warnings) >= 1, (
            f"Expected DeprecationWarning for spawn_agent_in_clone, got: {[str(x.message) for x in w]}"
        )


class TestMergeCloneToTarget:
    """Tests for merge_clone_to_target tool."""

    @pytest.mark.asyncio
    async def test_merge_clone_success(self, registry, mock_clone_storage, mock_git_manager):
        """Merge clone to target branch successfully."""
        from unittest.mock import MagicMock

        # Setup clone
        mock_clone_storage.get.return_value = Clone(
            id="clone-123",
            project_id="proj-1",
            branch_name="feature/test",
            clone_path="/tmp/clones/test",
            base_branch="main",
            task_id=None,
            agent_session_id=None,
            status="active",
            remote_url="https://github.com/user/repo.git",
            last_sync_at=None,
            cleanup_after=None,
            created_at="now",
            updated_at="now",
        )
        mock_clone_storage.update.return_value = MagicMock()

        # Mock sync (push)
        mock_git_manager.sync_clone.return_value = MagicMock(success=True)
        # Mock merge operation
        mock_git_manager.merge_branch.return_value = MagicMock(
            success=True,
            has_conflicts=False,
        )

        result = await registry.call(
            "merge_clone_to_target",
            {"clone_id": "clone-123", "target_branch": "main"},
        )

        assert result["success"] is True
        # Should have synced first
        mock_git_manager.sync_clone.assert_called_once()
        # Should have set cleanup_after on success
        mock_clone_storage.update.assert_called()

    @pytest.mark.asyncio
    async def test_merge_clone_not_found(self, registry, mock_clone_storage):
        """Merge fails for nonexistent clone."""
        mock_clone_storage.get.return_value = None

        result = await registry.call(
            "merge_clone_to_target",
            {"clone_id": "nonexistent", "target_branch": "main"},
        )

        assert result["success"] is False
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_merge_clone_sync_failure(self, registry, mock_clone_storage, mock_git_manager):
        """Merge fails when sync fails."""
        mock_clone_storage.get.return_value = Clone(
            id="clone-123",
            project_id="proj-1",
            branch_name="feature/test",
            clone_path="/tmp/clones/test",
            base_branch="main",
            task_id=None,
            agent_session_id=None,
            status="active",
            remote_url="https://github.com/user/repo.git",
            last_sync_at=None,
            cleanup_after=None,
            created_at="now",
            updated_at="now",
        )

        # Sync fails
        mock_git_manager.sync_clone.return_value = MagicMock(
            success=False,
            error="Push rejected",
        )

        result = await registry.call(
            "merge_clone_to_target",
            {"clone_id": "clone-123", "target_branch": "main"},
        )

        assert result["success"] is False
        assert "sync" in result["error"].lower() or "push" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_merge_clone_with_conflicts(self, registry, mock_clone_storage, mock_git_manager):
        """Merge detects conflicts and reports them."""
        from unittest.mock import MagicMock

        mock_clone_storage.get.return_value = Clone(
            id="clone-123",
            project_id="proj-1",
            branch_name="feature/test",
            clone_path="/tmp/clones/test",
            base_branch="main",
            task_id=None,
            agent_session_id=None,
            status="active",
            remote_url="https://github.com/user/repo.git",
            last_sync_at=None,
            cleanup_after=None,
            created_at="now",
            updated_at="now",
        )

        mock_git_manager.sync_clone.return_value = MagicMock(success=True)
        # Merge has conflicts - error="merge_conflict" signals conflict
        mock_git_manager.merge_branch.return_value = MagicMock(
            success=False,
            error="merge_conflict",
            message="Merge conflict in 2 files",
            output="src/foo.py\nsrc/bar.py",
        )

        result = await registry.call(
            "merge_clone_to_target",
            {"clone_id": "clone-123", "target_branch": "main"},
        )

        assert result["success"] is False
        assert result.get("has_conflicts") is True
        assert "conflicted_files" in result

    @pytest.mark.asyncio
    async def test_merge_clone_sets_cleanup_after(
        self, registry, mock_clone_storage, mock_git_manager
    ):
        """Successful merge sets cleanup_after to 7 days from now."""
        from unittest.mock import MagicMock

        mock_clone_storage.get.return_value = Clone(
            id="clone-123",
            project_id="proj-1",
            branch_name="feature/test",
            clone_path="/tmp/clones/test",
            base_branch="main",
            task_id=None,
            agent_session_id=None,
            status="active",
            remote_url="https://github.com/user/repo.git",
            last_sync_at=None,
            cleanup_after=None,
            created_at="now",
            updated_at="now",
        )
        mock_clone_storage.update.return_value = MagicMock()

        mock_git_manager.sync_clone.return_value = MagicMock(success=True)
        mock_git_manager.merge_branch.return_value = MagicMock(
            success=True,
            has_conflicts=False,
        )

        result = await registry.call(
            "merge_clone_to_target",
            {"clone_id": "clone-123", "target_branch": "main"},
        )

        assert result["success"] is True
        # Verify update was called with cleanup_after set
        update_calls = mock_clone_storage.update.call_args_list
        # Check if any call has cleanup_after
        has_cleanup = any(
            "cleanup_after" in (call.kwargs or {})
            for call in update_calls
        )
        assert has_cleanup or result.get("cleanup_after") is not None
