"""
Tests for spawn_agent unified MCP tool.

This file tests the unified spawn_agent tool that consolidates:
- start_agent
- spawn_agent_in_worktree
- spawn_agent_in_clone
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.agents.isolation import (
    IsolationContext,
)

pytestmark = pytest.mark.unit


class TestCreateSpawnAgentRegistry:
    """Tests for create_spawn_agent_registry factory function."""

    def test_creates_registry_with_correct_name(self) -> None:
        """Test registry has correct name."""
        from gobby.mcp_proxy.tools.spawn_agent import create_spawn_agent_registry

        runner = MagicMock()
        registry = create_spawn_agent_registry(runner)

        assert registry.name == "gobby-spawn-agent"

    def test_registers_spawn_agent_tool(self) -> None:
        """Test spawn_agent tool is registered."""
        from gobby.mcp_proxy.tools.spawn_agent import create_spawn_agent_registry

        runner = MagicMock()
        registry = create_spawn_agent_registry(runner)

        assert registry.get_schema("spawn_agent") is not None


class TestSpawnAgentDefaults:
    """Tests for spawn_agent with default values."""

    @pytest.fixture
    def mock_runner(self):
        """Create a mock runner with common setup."""
        runner = MagicMock()
        runner.can_spawn.return_value = (True, "Can spawn", 0)
        runner._child_session_manager = MagicMock()
        return runner

    @pytest.mark.asyncio
    async def test_spawn_agent_defaults_to_generic_agent(self, mock_runner) -> None:
        """Test spawn_agent with defaults uses generic agent definition."""
        from gobby.mcp_proxy.tools.spawn_agent import create_spawn_agent_registry

        mock_loader = MagicMock()
        mock_agent_def = MagicMock()
        mock_agent_def.isolation = None
        mock_agent_def.provider = "claude"
        mock_agent_def.mode = "terminal"
        mock_agent_def.workflow = "generic"
        mock_agent_def.base_branch = "main"
        mock_agent_def.branch_prefix = None
        mock_agent_def.timeout = 120.0
        mock_agent_def.max_turns = 10
        mock_agent_def.get_effective_workflow.return_value = None  # Skip workflow validation
        mock_agent_def.workflows = None
        mock_agent_def.default_workflow = None
        mock_loader.load.return_value = mock_agent_def

        registry = create_spawn_agent_registry(
            mock_runner,
            agent_loader=mock_loader,
        )

        with (
            patch("gobby.mcp_proxy.tools.spawn_agent.get_project_context") as mock_ctx,
            patch("gobby.mcp_proxy.tools.spawn_agent.execute_spawn") as mock_execute,
        ):
            mock_ctx.return_value = {
                "id": "proj-123",
                "project_path": "/path/to/project",
            }
            mock_execute.return_value = MagicMock(
                success=True,
                run_id="run-123",
                child_session_id="child-456",
                status="pending",
            )

            result = await registry.call(
                "spawn_agent",
                {
                    "prompt": "Test prompt",
                    "parent_session_id": "parent-789",
                },
            )

            # Should load "generic" agent by default
            mock_loader.load.assert_called_with("generic")
            assert result["success"] is True


class TestSpawnAgentIsolation:
    """Tests for spawn_agent isolation parameter."""

    @pytest.fixture
    def mock_runner(self):
        """Create a mock runner with common setup."""
        runner = MagicMock()
        runner.can_spawn.return_value = (True, "Can spawn", 0)
        runner._child_session_manager = MagicMock()
        return runner

    @pytest.fixture
    def mock_agent_def(self):
        """Create a mock agent definition."""
        agent_def = MagicMock()
        agent_def.isolation = None
        agent_def.provider = "claude"
        agent_def.mode = "terminal"
        agent_def.workflow = "generic"
        agent_def.base_branch = "main"
        agent_def.branch_prefix = None
        agent_def.timeout = 120.0
        agent_def.max_turns = 10
        agent_def.get_effective_workflow.return_value = None  # Skip workflow validation
        agent_def.workflows = None
        agent_def.default_workflow = None
        return agent_def

    @pytest.mark.asyncio
    async def test_spawn_agent_current_uses_current_handler(
        self, mock_runner, mock_agent_def
    ) -> None:
        """Test spawn_agent with isolation='current' uses CurrentIsolationHandler."""
        from gobby.mcp_proxy.tools.spawn_agent import create_spawn_agent_registry

        mock_loader = MagicMock()
        mock_loader.load.return_value = mock_agent_def

        registry = create_spawn_agent_registry(
            mock_runner,
            agent_loader=mock_loader,
        )

        with (
            patch("gobby.mcp_proxy.tools.spawn_agent.get_project_context") as mock_ctx,
            patch("gobby.mcp_proxy.tools.spawn_agent.get_isolation_handler") as mock_get_handler,
            patch("gobby.mcp_proxy.tools.spawn_agent.execute_spawn") as mock_execute,
        ):
            mock_ctx.return_value = {
                "id": "proj-123",
                "project_path": "/path/to/project",
            }
            mock_handler = MagicMock()
            mock_handler.prepare_environment = AsyncMock(
                return_value=IsolationContext(cwd="/path/to/project")
            )
            mock_handler.build_context_prompt.return_value = "Test prompt"
            mock_get_handler.return_value = mock_handler

            mock_execute.return_value = MagicMock(
                success=True,
                run_id="run-123",
                child_session_id="child-456",
                status="pending",
            )

            result = await registry.call(
                "spawn_agent",
                {
                    "prompt": "Test prompt",
                    "parent_session_id": "parent-789",
                    "isolation": "current",
                },
            )

            mock_get_handler.assert_called_once()
            call_args = mock_get_handler.call_args
            assert call_args[0][0] == "current"
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_spawn_agent_worktree_creates_worktree(self, mock_runner, mock_agent_def) -> None:
        """Test spawn_agent with isolation='worktree' creates/reuses worktree."""
        from gobby.mcp_proxy.tools.spawn_agent import create_spawn_agent_registry

        mock_loader = MagicMock()
        mock_loader.load.return_value = mock_agent_def

        mock_worktree_storage = MagicMock()
        mock_git_manager = MagicMock()

        registry = create_spawn_agent_registry(
            mock_runner,
            agent_loader=mock_loader,
            worktree_storage=mock_worktree_storage,
            git_manager=mock_git_manager,
        )

        with (
            patch("gobby.mcp_proxy.tools.spawn_agent.get_project_context") as mock_ctx,
            patch("gobby.mcp_proxy.tools.spawn_agent.get_isolation_handler") as mock_get_handler,
            patch("gobby.mcp_proxy.tools.spawn_agent.execute_spawn") as mock_execute,
        ):
            mock_ctx.return_value = {
                "id": "proj-123",
                "project_path": "/path/to/project",
            }
            mock_handler = MagicMock()
            mock_handler.prepare_environment = AsyncMock(
                return_value=IsolationContext(
                    cwd="/tmp/worktrees/branch",
                    branch_name="test-branch",
                    worktree_id="wt-123",
                    isolation_type="worktree",
                )
            )
            mock_handler.build_context_prompt.return_value = "Test prompt"
            mock_get_handler.return_value = mock_handler

            mock_execute.return_value = MagicMock(
                success=True,
                run_id="run-123",
                child_session_id="child-456",
                status="pending",
            )

            result = await registry.call(
                "spawn_agent",
                {
                    "prompt": "Test prompt",
                    "parent_session_id": "parent-789",
                    "isolation": "worktree",
                },
            )

            mock_get_handler.assert_called_once()
            call_args = mock_get_handler.call_args
            assert call_args[0][0] == "worktree"
            assert result["success"] is True
            assert result["worktree_id"] == "wt-123"

    @pytest.mark.asyncio
    async def test_spawn_agent_clone_creates_clone(self, mock_runner, mock_agent_def) -> None:
        """Test spawn_agent with isolation='clone' creates clone."""
        from gobby.mcp_proxy.tools.spawn_agent import create_spawn_agent_registry

        mock_loader = MagicMock()
        mock_loader.load.return_value = mock_agent_def

        mock_clone_storage = MagicMock()
        mock_clone_manager = MagicMock()

        registry = create_spawn_agent_registry(
            mock_runner,
            agent_loader=mock_loader,
            clone_storage=mock_clone_storage,
            clone_manager=mock_clone_manager,
        )

        with (
            patch("gobby.mcp_proxy.tools.spawn_agent.get_project_context") as mock_ctx,
            patch("gobby.mcp_proxy.tools.spawn_agent.get_isolation_handler") as mock_get_handler,
            patch("gobby.mcp_proxy.tools.spawn_agent.execute_spawn") as mock_execute,
        ):
            mock_ctx.return_value = {
                "id": "proj-123",
                "project_path": "/path/to/project",
            }
            mock_handler = MagicMock()
            mock_handler.prepare_environment = AsyncMock(
                return_value=IsolationContext(
                    cwd="/tmp/clones/branch",
                    branch_name="test-branch",
                    clone_id="clone-123",
                    isolation_type="clone",
                )
            )
            mock_handler.build_context_prompt.return_value = "Test prompt"
            mock_get_handler.return_value = mock_handler

            mock_execute.return_value = MagicMock(
                success=True,
                run_id="run-123",
                child_session_id="child-456",
                status="pending",
            )

            result = await registry.call(
                "spawn_agent",
                {
                    "prompt": "Test prompt",
                    "parent_session_id": "parent-789",
                    "isolation": "clone",
                },
            )

            mock_get_handler.assert_called_once()
            call_args = mock_get_handler.call_args
            assert call_args[0][0] == "clone"
            assert result["success"] is True
            assert result["clone_id"] == "clone-123"


class TestSpawnAgentParamOverrides:
    """Tests for tool params overriding agent definition values."""

    @pytest.fixture
    def mock_runner(self):
        """Create a mock runner with common setup."""
        runner = MagicMock()
        runner.can_spawn.return_value = (True, "Can spawn", 0)
        runner._child_session_manager = MagicMock()
        return runner

    @pytest.mark.asyncio
    async def test_tool_params_override_agent_definition(self, mock_runner) -> None:
        """Test that tool params take precedence over agent definition values."""
        from gobby.mcp_proxy.tools.spawn_agent import create_spawn_agent_registry

        # Agent definition says isolation=current, mode=headless
        mock_agent_def = MagicMock()
        mock_agent_def.isolation = "current"
        mock_agent_def.provider = "claude"
        mock_agent_def.mode = "headless"
        mock_agent_def.workflow = "default-workflow"
        mock_agent_def.base_branch = "main"
        mock_agent_def.branch_prefix = None
        mock_agent_def.timeout = 120.0
        mock_agent_def.max_turns = 10

        mock_loader = MagicMock()
        mock_loader.load.return_value = mock_agent_def

        # Mock workflow loader to validate workflow exists (load_workflow is async)
        mock_wf_loader = MagicMock()
        mock_wf_loader.load_workflow = AsyncMock(return_value=MagicMock())

        registry = create_spawn_agent_registry(
            mock_runner,
            agent_loader=mock_loader,
            workflow_loader=mock_wf_loader,
        )

        with (
            patch("gobby.mcp_proxy.tools.spawn_agent.get_project_context") as mock_ctx,
            patch("gobby.mcp_proxy.tools.spawn_agent.get_isolation_handler") as mock_get_handler,
            patch("gobby.mcp_proxy.tools.spawn_agent.execute_spawn") as mock_execute,
        ):
            mock_ctx.return_value = {
                "id": "proj-123",
                "project_path": "/path/to/project",
            }
            mock_handler = MagicMock()
            mock_handler.prepare_environment = AsyncMock(
                return_value=IsolationContext(cwd="/path/to/project")
            )
            mock_handler.build_context_prompt.return_value = "Test prompt"
            mock_get_handler.return_value = mock_handler

            mock_execute.return_value = MagicMock(
                success=True,
                run_id="run-123",
                child_session_id="child-456",
                status="pending",
            )

            # Override with mode=terminal via tool param
            result = await registry.call(
                "spawn_agent",
                {
                    "prompt": "Test prompt",
                    "parent_session_id": "parent-789",
                    "mode": "terminal",  # Override agent definition's headless
                },
            )

            # Verify execute_spawn was called with terminal mode
            assert result["success"] is True
            execute_call = mock_execute.call_args
            assert execute_call[0][0].mode == "terminal"


class TestSpawnAgentTaskResolution:
    """Tests for task_id resolution formats."""

    @pytest.fixture
    def mock_runner(self):
        """Create a mock runner with common setup."""
        runner = MagicMock()
        runner.can_spawn.return_value = (True, "Can spawn", 0)
        runner._child_session_manager = MagicMock()
        return runner

    @pytest.fixture
    def mock_agent_def(self):
        """Create a mock agent definition."""
        agent_def = MagicMock()
        agent_def.isolation = None
        agent_def.provider = "claude"
        agent_def.mode = "terminal"
        agent_def.workflow = "generic"
        agent_def.base_branch = "main"
        agent_def.branch_prefix = None
        agent_def.timeout = 120.0
        agent_def.max_turns = 10
        agent_def.get_effective_workflow.return_value = None  # Skip workflow validation
        agent_def.workflows = None
        agent_def.default_workflow = None
        return agent_def

    @pytest.mark.asyncio
    async def test_task_id_supports_hash_n_format(self, mock_runner, mock_agent_def) -> None:
        """Test task_id resolution supports #N format."""
        from gobby.mcp_proxy.tools.spawn_agent import create_spawn_agent_registry

        mock_loader = MagicMock()
        mock_loader.load.return_value = mock_agent_def

        mock_task_manager = MagicMock()
        mock_task = MagicMock()
        mock_task.title = "Implement feature"
        mock_task.seq_num = 6100
        mock_task.id = "uuid-123"
        mock_task_manager.get_task.return_value = mock_task

        registry = create_spawn_agent_registry(
            mock_runner,
            agent_loader=mock_loader,
            task_manager=mock_task_manager,
        )

        with (
            patch("gobby.mcp_proxy.tools.spawn_agent.get_project_context") as mock_ctx,
            patch("gobby.mcp_proxy.tools.spawn_agent.get_isolation_handler") as mock_get_handler,
            patch("gobby.mcp_proxy.tools.spawn_agent.execute_spawn") as mock_execute,
            patch("gobby.mcp_proxy.tools.spawn_agent.resolve_task_id_for_mcp") as mock_resolve,
        ):
            mock_ctx.return_value = {
                "id": "proj-123",
                "project_path": "/path/to/project",
            }
            mock_resolve.return_value = "uuid-123"

            mock_handler = MagicMock()
            mock_handler.prepare_environment = AsyncMock(
                return_value=IsolationContext(cwd="/path/to/project")
            )
            mock_handler.build_context_prompt.return_value = "Test prompt"
            mock_get_handler.return_value = mock_handler

            mock_execute.return_value = MagicMock(
                success=True,
                run_id="run-123",
                child_session_id="child-456",
                status="pending",
            )

            result = await registry.call(
                "spawn_agent",
                {
                    "prompt": "Test prompt",
                    "parent_session_id": "parent-789",
                    "task_id": "#6100",
                },
            )

            mock_resolve.assert_called_once()
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_task_id_supports_numeric_format(self, mock_runner, mock_agent_def) -> None:
        """Test task_id resolution supports N format (bare number)."""
        from gobby.mcp_proxy.tools.spawn_agent import create_spawn_agent_registry

        mock_loader = MagicMock()
        mock_loader.load.return_value = mock_agent_def

        mock_task_manager = MagicMock()
        mock_task = MagicMock()
        mock_task.title = "Implement feature"
        mock_task.seq_num = 6100
        mock_task.id = "uuid-123"
        mock_task_manager.get_task.return_value = mock_task

        registry = create_spawn_agent_registry(
            mock_runner,
            agent_loader=mock_loader,
            task_manager=mock_task_manager,
        )

        with (
            patch("gobby.mcp_proxy.tools.spawn_agent.get_project_context") as mock_ctx,
            patch("gobby.mcp_proxy.tools.spawn_agent.get_isolation_handler") as mock_get_handler,
            patch("gobby.mcp_proxy.tools.spawn_agent.execute_spawn") as mock_execute,
            patch("gobby.mcp_proxy.tools.spawn_agent.resolve_task_id_for_mcp") as mock_resolve,
        ):
            mock_ctx.return_value = {
                "id": "proj-123",
                "project_path": "/path/to/project",
            }
            mock_resolve.return_value = "uuid-123"

            mock_handler = MagicMock()
            mock_handler.prepare_environment = AsyncMock(
                return_value=IsolationContext(cwd="/path/to/project")
            )
            mock_handler.build_context_prompt.return_value = "Test prompt"
            mock_get_handler.return_value = mock_handler

            mock_execute.return_value = MagicMock(
                success=True,
                run_id="run-123",
                child_session_id="child-456",
                status="pending",
            )

            result = await registry.call(
                "spawn_agent",
                {
                    "prompt": "Test prompt",
                    "parent_session_id": "parent-789",
                    "task_id": "6100",
                },
            )

            mock_resolve.assert_called_once()
            assert result["success"] is True


class TestSpawnAgentBranchGeneration:
    """Tests for branch auto-generation from task title."""

    @pytest.fixture
    def mock_runner(self):
        """Create a mock runner with common setup."""
        runner = MagicMock()
        runner.can_spawn.return_value = (True, "Can spawn", 0)
        runner._child_session_manager = MagicMock()
        return runner

    @pytest.fixture
    def mock_agent_def(self):
        """Create a mock agent definition."""
        agent_def = MagicMock()
        agent_def.isolation = "worktree"
        agent_def.provider = "claude"
        agent_def.mode = "terminal"
        agent_def.workflow = "generic"
        agent_def.base_branch = "main"
        agent_def.branch_prefix = "task/"
        agent_def.timeout = 120.0
        agent_def.max_turns = 10
        agent_def.get_effective_workflow.return_value = None  # Skip workflow validation
        agent_def.workflows = None
        agent_def.default_workflow = None
        return agent_def

    @pytest.mark.asyncio
    async def test_branch_auto_generated_from_task_title(self, mock_runner, mock_agent_def) -> None:
        """Test branch is auto-generated from task title when not provided."""
        from gobby.mcp_proxy.tools.spawn_agent import create_spawn_agent_registry

        mock_loader = MagicMock()
        mock_loader.load.return_value = mock_agent_def

        mock_task_manager = MagicMock()
        mock_task = MagicMock()
        mock_task.title = "Implement Login Feature"
        mock_task.seq_num = 6100
        mock_task.id = "uuid-123"
        mock_task_manager.get_task.return_value = mock_task

        mock_worktree_storage = MagicMock()
        mock_git_manager = MagicMock()

        registry = create_spawn_agent_registry(
            mock_runner,
            agent_loader=mock_loader,
            task_manager=mock_task_manager,
            worktree_storage=mock_worktree_storage,
            git_manager=mock_git_manager,
        )

        with (
            patch("gobby.mcp_proxy.tools.spawn_agent.get_project_context") as mock_ctx,
            patch("gobby.mcp_proxy.tools.spawn_agent.get_isolation_handler") as mock_get_handler,
            patch("gobby.mcp_proxy.tools.spawn_agent.execute_spawn") as mock_execute,
            patch("gobby.mcp_proxy.tools.spawn_agent.resolve_task_id_for_mcp") as mock_resolve,
        ):
            mock_ctx.return_value = {
                "id": "proj-123",
                "project_path": "/path/to/project",
            }
            mock_resolve.return_value = "uuid-123"

            mock_handler = MagicMock()
            mock_handler.prepare_environment = AsyncMock(
                return_value=IsolationContext(
                    cwd="/tmp/worktrees/task-6100-implement-login-feature",
                    branch_name="task-6100-implement-login-feature",
                    worktree_id="wt-123",
                    isolation_type="worktree",
                )
            )
            mock_handler.build_context_prompt.return_value = "Test prompt"
            mock_get_handler.return_value = mock_handler

            mock_execute.return_value = MagicMock(
                success=True,
                run_id="run-123",
                child_session_id="child-456",
                status="pending",
            )

            result = await registry.call(
                "spawn_agent",
                {
                    "prompt": "Test prompt",
                    "parent_session_id": "parent-789",
                    "task_id": "#6100",
                    "isolation": "worktree",
                },
            )

            # Verify handler.prepare_environment was called
            mock_handler.prepare_environment.assert_called_once()
            # The SpawnConfig passed should have task info for branch generation
            spawn_config = mock_handler.prepare_environment.call_args[0][0]
            assert spawn_config.task_seq_num == 6100
            assert spawn_config.task_title == "Implement Login Feature"
            assert result["success"] is True
            assert result["branch_name"] == "task-6100-implement-login-feature"


class TestSpawnAgentSandbox:
    """Tests for spawn_agent sandbox parameters."""

    @pytest.fixture
    def mock_runner(self):
        """Create a mock runner with common setup."""
        runner = MagicMock()
        runner.can_spawn.return_value = (True, "Can spawn", 0)
        runner._child_session_manager = MagicMock()
        return runner

    @pytest.fixture
    def mock_agent_def(self):
        """Create a mock agent definition without sandbox."""
        agent_def = MagicMock()
        agent_def.isolation = None
        agent_def.provider = "claude"
        agent_def.mode = "terminal"
        agent_def.workflow = "generic"
        agent_def.base_branch = "main"
        agent_def.branch_prefix = None
        agent_def.timeout = 120.0
        agent_def.max_turns = 10
        agent_def.sandbox = None  # No sandbox config
        agent_def.get_effective_workflow.return_value = None  # Skip workflow validation
        agent_def.workflows = None
        agent_def.default_workflow = None
        return agent_def

    @pytest.mark.asyncio
    async def test_sandbox_params_create_sandbox_config(self, mock_runner, mock_agent_def) -> None:
        """Test sandbox params create SandboxConfig and pass to SpawnRequest."""
        from gobby.mcp_proxy.tools.spawn_agent import create_spawn_agent_registry

        mock_loader = MagicMock()
        mock_loader.load.return_value = mock_agent_def

        registry = create_spawn_agent_registry(
            mock_runner,
            agent_loader=mock_loader,
        )

        with (
            patch("gobby.mcp_proxy.tools.spawn_agent.get_project_context") as mock_ctx,
            patch("gobby.mcp_proxy.tools.spawn_agent.get_isolation_handler") as mock_get_handler,
            patch("gobby.mcp_proxy.tools.spawn_agent.execute_spawn") as mock_execute,
        ):
            mock_ctx.return_value = {
                "id": "proj-123",
                "project_path": "/path/to/project",
            }
            mock_handler = MagicMock()
            mock_handler.prepare_environment = AsyncMock(
                return_value=IsolationContext(cwd="/path/to/project")
            )
            mock_handler.build_context_prompt.return_value = "Test prompt"
            mock_get_handler.return_value = mock_handler

            mock_execute.return_value = MagicMock(
                success=True,
                run_id="run-123",
                child_session_id="child-456",
                status="pending",
            )

            result = await registry.call(
                "spawn_agent",
                {
                    "prompt": "Test prompt",
                    "parent_session_id": "parent-789",
                    "sandbox": True,
                    "sandbox_mode": "restrictive",
                    "sandbox_allow_network": False,
                },
            )

            assert result["success"] is True
            # Verify SpawnRequest received sandbox_config
            spawn_request = mock_execute.call_args[0][0]
            assert spawn_request.sandbox_config is not None
            assert spawn_request.sandbox_config.enabled is True
            assert spawn_request.sandbox_config.mode == "restrictive"
            assert spawn_request.sandbox_config.allow_network is False

    @pytest.mark.asyncio
    async def test_sandbox_params_override_agent_def_sandbox(self, mock_runner) -> None:
        """Test that tool sandbox params override agent_def.sandbox."""
        from gobby.agents.sandbox import SandboxConfig
        from gobby.mcp_proxy.tools.spawn_agent import create_spawn_agent_registry

        # Agent definition has sandbox enabled with permissive mode
        mock_agent_def = MagicMock()
        mock_agent_def.isolation = None
        mock_agent_def.provider = "claude"
        mock_agent_def.mode = "terminal"
        mock_agent_def.workflow = "generic"
        mock_agent_def.base_branch = "main"
        mock_agent_def.branch_prefix = None
        mock_agent_def.timeout = 120.0
        mock_agent_def.max_turns = 10
        mock_agent_def.sandbox = SandboxConfig(
            enabled=True,
            mode="permissive",
            allow_network=True,
            extra_read_paths=["/opt/data"],
        )
        mock_agent_def.get_effective_workflow.return_value = None
        mock_agent_def.workflows = None
        mock_agent_def.default_workflow = None

        mock_loader = MagicMock()
        mock_loader.load.return_value = mock_agent_def

        registry = create_spawn_agent_registry(
            mock_runner,
            agent_loader=mock_loader,
        )

        with (
            patch("gobby.mcp_proxy.tools.spawn_agent.get_project_context") as mock_ctx,
            patch("gobby.mcp_proxy.tools.spawn_agent.get_isolation_handler") as mock_get_handler,
            patch("gobby.mcp_proxy.tools.spawn_agent.execute_spawn") as mock_execute,
        ):
            mock_ctx.return_value = {
                "id": "proj-123",
                "project_path": "/path/to/project",
            }
            mock_handler = MagicMock()
            mock_handler.prepare_environment = AsyncMock(
                return_value=IsolationContext(cwd="/path/to/project")
            )
            mock_handler.build_context_prompt.return_value = "Test prompt"
            mock_get_handler.return_value = mock_handler

            mock_execute.return_value = MagicMock(
                success=True,
                run_id="run-123",
                child_session_id="child-456",
                status="pending",
            )

            # Override sandbox_mode to restrictive via tool param
            result = await registry.call(
                "spawn_agent",
                {
                    "prompt": "Test prompt",
                    "parent_session_id": "parent-789",
                    "sandbox_mode": "restrictive",  # Override permissive
                    "sandbox_allow_network": False,  # Override True
                },
            )

            assert result["success"] is True
            spawn_request = mock_execute.call_args[0][0]
            # Should be enabled (from agent_def) with overrides applied
            assert spawn_request.sandbox_config is not None
            assert spawn_request.sandbox_config.enabled is True
            assert spawn_request.sandbox_config.mode == "restrictive"  # Overridden
            assert spawn_request.sandbox_config.allow_network is False  # Overridden
            # Should keep extra_read_paths from agent_def
            assert spawn_request.sandbox_config.extra_read_paths == ["/opt/data"]

    @pytest.mark.asyncio
    async def test_sandbox_extra_paths_passed_to_config(self, mock_runner, mock_agent_def):
        """Test sandbox_extra_paths are passed to SandboxConfig."""
        from gobby.mcp_proxy.tools.spawn_agent import create_spawn_agent_registry

        mock_loader = MagicMock()
        mock_loader.load.return_value = mock_agent_def

        registry = create_spawn_agent_registry(
            mock_runner,
            agent_loader=mock_loader,
        )

        with (
            patch("gobby.mcp_proxy.tools.spawn_agent.get_project_context") as mock_ctx,
            patch("gobby.mcp_proxy.tools.spawn_agent.get_isolation_handler") as mock_get_handler,
            patch("gobby.mcp_proxy.tools.spawn_agent.execute_spawn") as mock_execute,
        ):
            mock_ctx.return_value = {
                "id": "proj-123",
                "project_path": "/path/to/project",
            }
            mock_handler = MagicMock()
            mock_handler.prepare_environment = AsyncMock(
                return_value=IsolationContext(cwd="/path/to/project")
            )
            mock_handler.build_context_prompt.return_value = "Test prompt"
            mock_get_handler.return_value = mock_handler

            mock_execute.return_value = MagicMock(
                success=True,
                run_id="run-123",
                child_session_id="child-456",
                status="pending",
            )

            result = await registry.call(
                "spawn_agent",
                {
                    "prompt": "Test prompt",
                    "parent_session_id": "parent-789",
                    "sandbox": True,
                    "sandbox_extra_paths": ["/tmp/data", "/opt/tools"],
                },
            )

            assert result["success"] is True
            spawn_request = mock_execute.call_args[0][0]
            assert spawn_request.sandbox_config is not None
            # Extra paths should be set as extra_write_paths
            assert "/tmp/data" in spawn_request.sandbox_config.extra_write_paths
            assert "/opt/tools" in spawn_request.sandbox_config.extra_write_paths

    @pytest.mark.asyncio
    async def test_sandbox_disabled_when_param_false(self, mock_runner):
        """Test sandbox is disabled when sandbox=False even if agent_def has it enabled."""
        from gobby.agents.sandbox import SandboxConfig
        from gobby.mcp_proxy.tools.spawn_agent import create_spawn_agent_registry

        # Agent definition has sandbox enabled
        mock_agent_def = MagicMock()
        mock_agent_def.isolation = None
        mock_agent_def.provider = "claude"
        mock_agent_def.mode = "terminal"
        mock_agent_def.workflow = "generic"
        mock_agent_def.base_branch = "main"
        mock_agent_def.branch_prefix = None
        mock_agent_def.timeout = 120.0
        mock_agent_def.max_turns = 10
        mock_agent_def.sandbox = SandboxConfig(enabled=True, mode="permissive")
        mock_agent_def.get_effective_workflow.return_value = None
        mock_agent_def.workflows = None
        mock_agent_def.default_workflow = None

        mock_loader = MagicMock()
        mock_loader.load.return_value = mock_agent_def

        registry = create_spawn_agent_registry(
            mock_runner,
            agent_loader=mock_loader,
        )

        with (
            patch("gobby.mcp_proxy.tools.spawn_agent.get_project_context") as mock_ctx,
            patch("gobby.mcp_proxy.tools.spawn_agent.get_isolation_handler") as mock_get_handler,
            patch("gobby.mcp_proxy.tools.spawn_agent.execute_spawn") as mock_execute,
        ):
            mock_ctx.return_value = {
                "id": "proj-123",
                "project_path": "/path/to/project",
            }
            mock_handler = MagicMock()
            mock_handler.prepare_environment = AsyncMock(
                return_value=IsolationContext(cwd="/path/to/project")
            )
            mock_handler.build_context_prompt.return_value = "Test prompt"
            mock_get_handler.return_value = mock_handler

            mock_execute.return_value = MagicMock(
                success=True,
                run_id="run-123",
                child_session_id="child-456",
                status="pending",
            )

            # Explicitly disable sandbox via param
            result = await registry.call(
                "spawn_agent",
                {
                    "prompt": "Test prompt",
                    "parent_session_id": "parent-789",
                    "sandbox": False,  # Explicitly disable
                },
            )

            assert result["success"] is True
            spawn_request = mock_execute.call_args[0][0]
            # sandbox_config should be None or have enabled=False
            if spawn_request.sandbox_config is not None:
                assert spawn_request.sandbox_config.enabled is False


class TestSpawnAgentPreRegistration:
    """Tests for agent registry pre-registration before execute_spawn."""

    @pytest.fixture
    def mock_runner(self):
        runner = MagicMock()
        runner.can_spawn.return_value = (True, "Can spawn", 0)
        runner._child_session_manager = MagicMock()
        return runner

    @pytest.fixture
    def mock_agent_def(self):
        agent_def = MagicMock()
        agent_def.isolation = None
        agent_def.provider = "claude"
        agent_def.mode = "terminal"
        agent_def.workflow = "generic"
        agent_def.base_branch = "main"
        agent_def.branch_prefix = None
        agent_def.timeout = 120.0
        agent_def.max_turns = 10
        agent_def.get_effective_workflow.return_value = None
        agent_def.workflows = None
        agent_def.default_workflow = None
        return agent_def

    @pytest.mark.asyncio
    async def test_agent_registered_before_spawn(self, mock_runner, mock_agent_def):
        """Agent is pre-registered in RunningAgentRegistry before execute_spawn."""
        from gobby.mcp_proxy.tools.spawn_agent import create_spawn_agent_registry

        mock_loader = MagicMock()
        mock_loader.load.return_value = mock_agent_def

        registry = create_spawn_agent_registry(mock_runner, agent_loader=mock_loader)

        call_order: list[str] = []
        mock_agent_registry = MagicMock()
        mock_agent_registry.add.side_effect = lambda agent: call_order.append(f"add:{agent.run_id}")

        async def fake_execute(req):
            # At this point, add should have been called already
            call_order.append("execute_spawn")
            return MagicMock(
                success=True,
                run_id=req.run_id,
                child_session_id="child-456",
                status="pending",
                pid=12345,
                terminal_type="ghostty",
                tmux_session_name=None,
                message="Spawned",
            )

        with (
            patch("gobby.mcp_proxy.tools.spawn_agent.get_project_context") as mock_ctx,
            patch("gobby.mcp_proxy.tools.spawn_agent.execute_spawn", side_effect=fake_execute),
            patch(
                "gobby.mcp_proxy.tools.spawn_agent.get_running_agent_registry",
                return_value=mock_agent_registry,
            ),
        ):
            mock_ctx.return_value = {"id": "proj-123", "project_path": "/path"}

            result = await registry.call(
                "spawn_agent",
                {"prompt": "Test", "parent_session_id": "parent-789"},
            )

            assert result["success"] is True
            # Pre-registration happened before execute_spawn
            assert len(call_order) == 3  # add (pre-reg), execute_spawn, add (update)
            assert call_order[0].startswith("add:")
            assert call_order[1] == "execute_spawn"
            assert call_order[2].startswith("add:")
            # remove was never called (spawn succeeded)
            mock_agent_registry.remove.assert_not_called()

    @pytest.mark.asyncio
    async def test_agent_removed_on_spawn_failure(self, mock_runner, mock_agent_def):
        """Pre-registered agent is removed from registry when spawn fails."""
        from gobby.mcp_proxy.tools.spawn_agent import create_spawn_agent_registry

        mock_loader = MagicMock()
        mock_loader.load.return_value = mock_agent_def

        registry = create_spawn_agent_registry(mock_runner, agent_loader=mock_loader)

        mock_agent_registry = MagicMock()
        pre_registered_run_id: list[str] = []

        def track_add(agent):
            pre_registered_run_id.append(agent.run_id)

        mock_agent_registry.add.side_effect = track_add

        with (
            patch("gobby.mcp_proxy.tools.spawn_agent.get_project_context") as mock_ctx,
            patch("gobby.mcp_proxy.tools.spawn_agent.execute_spawn") as mock_execute,
            patch(
                "gobby.mcp_proxy.tools.spawn_agent.get_running_agent_registry",
                return_value=mock_agent_registry,
            ),
        ):
            mock_ctx.return_value = {"id": "proj-123", "project_path": "/path"}
            mock_execute.return_value = MagicMock(
                success=False,
                error="Terminal not found",
                child_session_id=None,
            )

            result = await registry.call(
                "spawn_agent",
                {"prompt": "Test", "parent_session_id": "parent-789"},
            )

            assert result["success"] is False
            # Pre-registration happened (1 add call)
            assert len(pre_registered_run_id) == 1
            # Agent was removed after failure
            mock_agent_registry.remove.assert_called_once_with(
                pre_registered_run_id[0], status="failed"
            )
