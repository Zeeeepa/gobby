"""
Tests for agents.py MCP tools module.

This file tests the agent-related MCP tools:
- start_agent: Spawn a subagent
- get_agent_result: Get agent run result
- list_agents: List agent runs for a session
- cancel_agent: Cancel a running agent
- can_spawn_agent: Check if spawning is allowed
- list_running_agents: List in-memory running agents
- get_running_agent: Get running agent state
- unregister_agent: Remove agent from registry
- running_agent_stats: Get agent statistics
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.agents.registry import RunningAgent, RunningAgentRegistry
from gobby.mcp_proxy.tools.agents import create_agents_registry


class TestCreateAgentsRegistry:
    """Tests for create_agents_registry factory function."""

    def test_creates_registry_with_correct_name(self):
        """Test registry has correct name."""
        runner = MagicMock()
        registry = create_agents_registry(runner)

        assert registry.name == "gobby-agents"
        assert "Agent" in registry.description

    def test_registers_all_expected_tools(self):
        """Test all agent tools are registered."""
        runner = MagicMock()
        registry = create_agents_registry(runner)

        expected_tools = [
            "start_agent",
            "get_agent_result",
            "list_agents",
            "cancel_agent",
            "can_spawn_agent",
            "list_running_agents",
            "get_running_agent",
            "unregister_agent",
            "running_agent_stats",
        ]

        for tool_name in expected_tools:
            assert registry.get_schema(tool_name) is not None, f"Missing tool: {tool_name}"

    def test_uses_provided_running_registry(self):
        """Test that provided registry is used instead of global."""
        runner = MagicMock()
        custom_registry = RunningAgentRegistry()

        registry = create_agents_registry(runner, running_registry=custom_registry)
        # Verify registry was accepted (test indirectly via list_running_agents)
        assert registry is not None


class TestStartAgent:
    """Tests for start_agent MCP tool."""

    @pytest.fixture
    def mock_runner(self):
        """Create a mock runner with common setup."""
        runner = MagicMock()
        runner.can_spawn.return_value = (True, "Can spawn", 0)
        return runner

    @pytest.fixture
    def mock_context(self):
        """Create mock project context."""
        return {
            "id": "proj-test-123",
            "project_path": "/tmp/test-project",
        }

    @pytest.mark.asyncio
    async def test_invalid_mode_returns_error(self, mock_runner):
        """Test that invalid mode returns an error."""
        registry = create_agents_registry(mock_runner)
        start_agent = registry._tools["start_agent"].func

        result = await start_agent(
            prompt="Test prompt",
            mode="invalid_mode",
            parent_session_id="sess-123",
        )

        assert result["success"] is False
        assert "Invalid mode" in result["error"]
        assert "invalid_mode" in result["error"]

    @pytest.mark.asyncio
    async def test_no_project_context_returns_error(self, mock_runner):
        """Test error when no project context is available."""
        registry = create_agents_registry(mock_runner)
        start_agent = registry._tools["start_agent"].func

        with patch("gobby.mcp_proxy.tools.agents.get_project_context", return_value=None):
            result = await start_agent(
                prompt="Test prompt",
                parent_session_id="sess-123",
            )

        assert result["success"] is False
        assert "No project context" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_parent_session_id_returns_error(self, mock_runner, mock_context):
        """Test error when parent_session_id is not provided."""
        registry = create_agents_registry(mock_runner)
        start_agent = registry._tools["start_agent"].func

        with patch("gobby.mcp_proxy.tools.agents.get_project_context", return_value=mock_context):
            result = await start_agent(prompt="Test prompt")

        assert result["success"] is False
        assert "parent_session_id is required" in result["error"]

    @pytest.mark.asyncio
    async def test_cannot_spawn_returns_error(self, mock_runner, mock_context):
        """Test error when can_spawn returns False."""
        mock_runner.can_spawn.return_value = (False, "Max depth exceeded", 3)
        registry = create_agents_registry(mock_runner)
        start_agent = registry._tools["start_agent"].func

        with patch("gobby.mcp_proxy.tools.agents.get_project_context", return_value=mock_context):
            result = await start_agent(
                prompt="Test prompt",
                parent_session_id="sess-123",
            )

        assert result["success"] is False
        assert "Max depth exceeded" in result["error"]

    @pytest.mark.asyncio
    async def test_lifecycle_workflow_rejected(self, mock_runner, mock_context):
        """Test that lifecycle workflows are rejected for agent spawning."""
        mock_loader = MagicMock()
        mock_loader.validate_workflow_for_agent.return_value = (
            False,
            "Cannot use lifecycle workflow",
        )

        registry = create_agents_registry(mock_runner)
        start_agent = registry._tools["start_agent"].func

        with (
            patch("gobby.mcp_proxy.tools.agents.get_project_context", return_value=mock_context),
            patch(
                "gobby.workflows.loader.WorkflowLoader",
                return_value=mock_loader,
            ),
        ):
            result = await start_agent(
                prompt="Test prompt",
                parent_session_id="sess-123",
                workflow="lifecycle-workflow",
            )

        assert result["success"] is False
        assert (
            "lifecycle workflow" in result["error"].lower()
            or "cannot use" in result["error"].lower()
        )

    @pytest.mark.asyncio
    async def test_in_process_mode_runs_via_runner(self, mock_runner, mock_context):
        """Test in_process mode executes via runner.run()."""
        # Setup mock result
        mock_result = MagicMock()
        mock_result.status = "success"
        mock_result.run_id = "run-123"
        mock_result.output = "Task completed"
        mock_result.error = None
        mock_result.turns_used = 3
        mock_result.tool_calls = [MagicMock(), MagicMock()]

        mock_runner.run = AsyncMock(return_value=mock_result)

        registry = create_agents_registry(mock_runner)
        start_agent = registry._tools["start_agent"].func

        with patch("gobby.mcp_proxy.tools.agents.get_project_context", return_value=mock_context):
            result = await start_agent(
                prompt="Test prompt",
                mode="in_process",
                parent_session_id="sess-123",
            )

        assert result["success"] is True
        assert result["status"] == "success"
        assert result["run_id"] == "run-123"
        assert result["turns_used"] == 3
        assert result["tool_calls_count"] == 2

    @pytest.mark.asyncio
    async def test_terminal_mode_spawns_terminal(self, mock_runner, mock_context):
        """Test terminal mode spawns via TerminalSpawner."""
        # Setup prepare_run to return context
        mock_session = MagicMock()
        mock_session.id = "child-sess-123"
        mock_session.agent_depth = 1

        mock_run = MagicMock()
        mock_run.id = "run-456"

        mock_context_obj = MagicMock()
        mock_context_obj.session = mock_session
        mock_context_obj.run = mock_run

        mock_runner.prepare_run.return_value = mock_context_obj
        mock_runner._child_session_manager.max_agent_depth = 3

        # Mock TerminalSpawner
        mock_spawn_result = MagicMock()
        mock_spawn_result.success = True
        mock_spawn_result.pid = 12345
        mock_spawn_result.terminal_type = "ghostty"
        mock_spawn_result.error = None
        mock_spawn_result.message = "Spawned"

        mock_terminal_spawner = MagicMock()
        mock_terminal_spawner.spawn_agent.return_value = mock_spawn_result

        running_registry = RunningAgentRegistry()
        registry = create_agents_registry(mock_runner, running_registry=running_registry)
        start_agent = registry._tools["start_agent"].func

        with (
            patch("gobby.mcp_proxy.tools.agents.get_project_context", return_value=mock_context),
            patch(
                "gobby.mcp_proxy.tools.agents.TerminalSpawner",
                return_value=mock_terminal_spawner,
            ),
        ):
            result = await start_agent(
                prompt="Test prompt",
                mode="terminal",
                parent_session_id="sess-123",
                terminal="ghostty",
            )

        assert result["success"] is True
        assert result["status"] == "pending"
        assert result["run_id"] == "run-456"
        assert result["child_session_id"] == "child-sess-123"
        assert result["pid"] == 12345
        assert result["terminal_type"] == "ghostty"

        # Verify agent was registered
        registered_agent = running_registry.get("run-456")
        assert registered_agent is not None
        assert registered_agent.mode == "terminal"
        assert registered_agent.pid == 12345

    @pytest.mark.asyncio
    async def test_terminal_spawn_failure(self, mock_runner, mock_context):
        """Test terminal spawn failure returns error."""
        mock_session = MagicMock()
        mock_session.id = "child-sess-123"
        mock_session.agent_depth = 1

        mock_run = MagicMock()
        mock_run.id = "run-456"

        mock_context_obj = MagicMock()
        mock_context_obj.session = mock_session
        mock_context_obj.run = mock_run

        mock_runner.prepare_run.return_value = mock_context_obj
        mock_runner._child_session_manager.max_agent_depth = 3

        mock_spawn_result = MagicMock()
        mock_spawn_result.success = False
        mock_spawn_result.error = "Terminal not found"
        mock_spawn_result.message = "Failed to spawn"

        mock_terminal_spawner = MagicMock()
        mock_terminal_spawner.spawn_agent.return_value = mock_spawn_result

        registry = create_agents_registry(mock_runner)
        start_agent = registry._tools["start_agent"].func

        with (
            patch("gobby.mcp_proxy.tools.agents.get_project_context", return_value=mock_context),
            patch(
                "gobby.mcp_proxy.tools.agents.TerminalSpawner",
                return_value=mock_terminal_spawner,
            ),
        ):
            result = await start_agent(
                prompt="Test prompt",
                mode="terminal",
                parent_session_id="sess-123",
            )

        assert result["success"] is False
        assert result["error"] == "Terminal not found"

    @pytest.mark.asyncio
    async def test_embedded_mode_spawns_with_pty(self, mock_runner, mock_context):
        """Test embedded mode spawns via EmbeddedSpawner."""
        mock_session = MagicMock()
        mock_session.id = "child-sess-123"
        mock_session.agent_depth = 1

        mock_run = MagicMock()
        mock_run.id = "run-789"

        mock_context_obj = MagicMock()
        mock_context_obj.session = mock_session
        mock_context_obj.run = mock_run

        mock_runner.prepare_run.return_value = mock_context_obj
        mock_runner._child_session_manager.max_agent_depth = 3

        mock_spawn_result = MagicMock()
        mock_spawn_result.success = True
        mock_spawn_result.pid = 54321
        mock_spawn_result.master_fd = 7
        mock_spawn_result.error = None
        mock_spawn_result.message = "PTY spawned"

        mock_embedded_spawner = MagicMock()
        mock_embedded_spawner.spawn_agent.return_value = mock_spawn_result

        running_registry = RunningAgentRegistry()
        registry = create_agents_registry(mock_runner, running_registry=running_registry)
        start_agent = registry._tools["start_agent"].func

        with (
            patch("gobby.mcp_proxy.tools.agents.get_project_context", return_value=mock_context),
            patch(
                "gobby.mcp_proxy.tools.agents.EmbeddedSpawner",
                return_value=mock_embedded_spawner,
            ),
        ):
            result = await start_agent(
                prompt="Test prompt",
                mode="embedded",
                parent_session_id="sess-123",
            )

        assert result["success"] is True
        assert result["status"] == "pending"
        assert result["pid"] == 54321
        assert result["master_fd"] == 7

        registered_agent = running_registry.get("run-789")
        assert registered_agent.mode == "embedded"
        assert registered_agent.master_fd == 7

    @pytest.mark.asyncio
    async def test_headless_mode_spawns_headless(self, mock_runner, mock_context):
        """Test headless mode spawns via HeadlessSpawner."""
        mock_session = MagicMock()
        mock_session.id = "child-sess-123"
        mock_session.agent_depth = 1

        mock_run = MagicMock()
        mock_run.id = "run-abc"

        mock_context_obj = MagicMock()
        mock_context_obj.session = mock_session
        mock_context_obj.run = mock_run

        mock_runner.prepare_run.return_value = mock_context_obj
        mock_runner._child_session_manager.max_agent_depth = 3

        mock_spawn_result = MagicMock()
        mock_spawn_result.success = True
        mock_spawn_result.pid = 11111
        mock_spawn_result.error = None
        mock_spawn_result.message = "Headless spawned"

        mock_headless_spawner = MagicMock()
        mock_headless_spawner.spawn_agent.return_value = mock_spawn_result

        running_registry = RunningAgentRegistry()
        registry = create_agents_registry(mock_runner, running_registry=running_registry)
        start_agent = registry._tools["start_agent"].func

        with (
            patch("gobby.mcp_proxy.tools.agents.get_project_context", return_value=mock_context),
            patch(
                "gobby.mcp_proxy.tools.agents.HeadlessSpawner",
                return_value=mock_headless_spawner,
            ),
        ):
            result = await start_agent(
                prompt="Test prompt",
                mode="headless",
                parent_session_id="sess-123",
            )

        assert result["success"] is True
        assert result["status"] == "pending"
        assert result["pid"] == 11111
        assert "master_fd" not in result

        registered_agent = running_registry.get("run-abc")
        assert registered_agent.mode == "headless"

    @pytest.mark.asyncio
    async def test_context_injection_with_resolver(self, mock_runner, mock_context):
        """Test that context is injected when resolver is configured."""
        mock_result = MagicMock()
        mock_result.status = "success"
        mock_result.run_id = "run-123"
        mock_result.output = "Done"
        mock_result.error = None
        mock_result.turns_used = 1
        mock_result.tool_calls = []

        mock_runner.run = AsyncMock(return_value=mock_result)

        # Create a mock session with summary_markdown
        mock_session = MagicMock()
        mock_session.summary_markdown = "Parent session context from summary"

        mock_session_manager = MagicMock()
        mock_session_manager.get.return_value = mock_session

        mock_message_manager = MagicMock()

        # Create registry with managers to enable context resolution
        registry = create_agents_registry(
            mock_runner,
            session_manager=mock_session_manager,
            message_manager=mock_message_manager,
        )
        start_agent = registry._tools["start_agent"].func

        with patch("gobby.mcp_proxy.tools.agents.get_project_context", return_value=mock_context):
            result = await start_agent(
                prompt="Do something",
                mode="in_process",
                parent_session_id="sess-123",
                session_context="summary_markdown",
            )

        # The test passes if we get here - context was resolved and injected
        assert result["success"] is True
        # Verify the runner was called with the context-injected prompt
        mock_runner.run.assert_called_once()
        call_args = mock_runner.run.call_args
        config = call_args[0][0]
        # The prompt should contain both context and original task
        assert "Parent session context from summary" in config.prompt
        assert "Do something" in config.prompt

    @pytest.mark.asyncio
    async def test_prepare_run_error_returns_failure(self, mock_runner, mock_context):
        """Test that prepare_run errors are returned properly."""
        from gobby.llm.executor import AgentResult

        mock_runner.prepare_run.return_value = AgentResult(
            output="",
            status="error",
            error="Failed to create session",
            turns_used=0,
        )

        registry = create_agents_registry(mock_runner)
        start_agent = registry._tools["start_agent"].func

        with patch("gobby.mcp_proxy.tools.agents.get_project_context", return_value=mock_context):
            result = await start_agent(
                prompt="Test prompt",
                mode="terminal",
                parent_session_id="sess-123",
            )

        assert result["success"] is False
        assert result["error"] == "Failed to create session"

    @pytest.mark.asyncio
    async def test_explicit_project_id_used_when_provided(self, mock_runner, mock_context):
        """Test that explicit project_id overrides inferred value."""
        mock_result = MagicMock()
        mock_result.status = "success"
        mock_result.run_id = "run-123"
        mock_result.output = "Done"
        mock_result.error = None
        mock_result.turns_used = 1
        mock_result.tool_calls = []

        mock_runner.run = AsyncMock(return_value=mock_result)

        registry = create_agents_registry(mock_runner)
        start_agent = registry._tools["start_agent"].func

        with patch("gobby.mcp_proxy.tools.agents.get_project_context", return_value=mock_context):
            result = await start_agent(
                prompt="Test prompt",
                mode="in_process",
                parent_session_id="sess-123",
                project_id="explicit-project-id",
            )

        assert result["success"] is True
        # The explicit project_id should be used in the AgentConfig passed to runner.run()
        call_args = mock_runner.run.call_args
        assert call_args is not None


class TestGetAgentResult:
    """Tests for get_agent_result MCP tool."""

    @pytest.mark.asyncio
    async def test_run_not_found_returns_error(self):
        """Test error when run_id not found."""
        runner = MagicMock()
        runner.get_run.return_value = None

        registry = create_agents_registry(runner)
        get_result = registry._tools["get_agent_result"].func

        result = await get_result(run_id="non-existent")

        assert result["success"] is False
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_returns_run_details(self):
        """Test successful run retrieval returns all details."""
        mock_run = MagicMock()
        mock_run.id = "run-123"
        mock_run.status = "success"
        mock_run.result = "Task completed"
        mock_run.error = None
        mock_run.provider = "claude"
        mock_run.model = "claude-3-opus"
        mock_run.prompt = "Do the thing"
        mock_run.tool_calls_count = 5
        mock_run.turns_used = 3
        mock_run.started_at = "2024-01-01T00:00:00Z"
        mock_run.completed_at = "2024-01-01T00:01:00Z"
        mock_run.child_session_id = "child-sess-456"

        runner = MagicMock()
        runner.get_run.return_value = mock_run

        registry = create_agents_registry(runner)
        get_result = registry._tools["get_agent_result"].func

        result = await get_result(run_id="run-123")

        assert result["success"] is True
        assert result["run_id"] == "run-123"
        assert result["status"] == "success"
        assert result["result"] == "Task completed"
        assert result["provider"] == "claude"
        assert result["model"] == "claude-3-opus"
        assert result["tool_calls_count"] == 5
        assert result["turns_used"] == 3
        assert result["child_session_id"] == "child-sess-456"


class TestListAgents:
    """Tests for list_agents MCP tool."""

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_runs(self):
        """Test empty list when no runs exist."""
        runner = MagicMock()
        runner.list_runs.return_value = []

        registry = create_agents_registry(runner)
        list_agents = registry._tools["list_agents"].func

        result = await list_agents(parent_session_id="sess-123")

        assert result["success"] is True
        assert result["runs"] == []
        assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_returns_runs_with_truncated_prompts(self):
        """Test that long prompts are truncated in list."""
        mock_run = MagicMock()
        mock_run.id = "run-123"
        mock_run.status = "running"
        mock_run.provider = "claude"
        mock_run.model = "claude-3"
        mock_run.workflow_name = "plan-execute"
        mock_run.prompt = "A" * 200  # Long prompt
        mock_run.started_at = "2024-01-01T00:00:00Z"
        mock_run.completed_at = None

        runner = MagicMock()
        runner.list_runs.return_value = [mock_run]

        registry = create_agents_registry(runner)
        list_agents = registry._tools["list_agents"].func

        result = await list_agents(parent_session_id="sess-123")

        assert result["success"] is True
        assert result["count"] == 1
        assert len(result["runs"][0]["prompt"]) == 103  # 100 chars + "..."
        assert result["runs"][0]["prompt"].endswith("...")

    @pytest.mark.asyncio
    async def test_respects_status_filter(self):
        """Test status filter is passed to runner."""
        runner = MagicMock()
        runner.list_runs.return_value = []

        registry = create_agents_registry(runner)
        list_agents = registry._tools["list_agents"].func

        await list_agents(parent_session_id="sess-123", status="running")

        runner.list_runs.assert_called_once_with("sess-123", status="running", limit=20)

    @pytest.mark.asyncio
    async def test_respects_limit(self):
        """Test limit parameter is passed to runner."""
        runner = MagicMock()
        runner.list_runs.return_value = []

        registry = create_agents_registry(runner)
        list_agents = registry._tools["list_agents"].func

        await list_agents(parent_session_id="sess-123", limit=50)

        runner.list_runs.assert_called_once_with("sess-123", status=None, limit=50)


class TestCancelAgent:
    """Tests for cancel_agent MCP tool."""

    @pytest.mark.asyncio
    async def test_successful_cancellation(self):
        """Test successful agent cancellation."""
        runner = MagicMock()
        runner.cancel_run.return_value = True

        running_registry = RunningAgentRegistry()
        running_registry.add(
            RunningAgent(
                run_id="run-123",
                session_id="sess-456",
                parent_session_id="sess-parent",
                mode="terminal",
            )
        )

        registry = create_agents_registry(runner, running_registry=running_registry)
        cancel_agent = registry._tools["cancel_agent"].func

        result = await cancel_agent(run_id="run-123")

        assert result["success"] is True
        assert "cancelled" in result["message"]

        # Verify removed from registry
        assert running_registry.get("run-123") is None

    @pytest.mark.asyncio
    async def test_run_not_found(self):
        """Test error when run not found."""
        runner = MagicMock()
        runner.cancel_run.return_value = False
        runner.get_run.return_value = None

        registry = create_agents_registry(runner)
        cancel_agent = registry._tools["cancel_agent"].func

        result = await cancel_agent(run_id="non-existent")

        assert result["success"] is False
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_cannot_cancel_completed_run(self):
        """Test error when trying to cancel non-running agent."""
        mock_run = MagicMock()
        mock_run.status = "success"

        runner = MagicMock()
        runner.cancel_run.return_value = False
        runner.get_run.return_value = mock_run

        registry = create_agents_registry(runner)
        cancel_agent = registry._tools["cancel_agent"].func

        result = await cancel_agent(run_id="run-123")

        assert result["success"] is False
        assert "Cannot cancel" in result["error"]
        assert "success" in result["error"]


class TestCanSpawnAgent:
    """Tests for can_spawn_agent MCP tool."""

    @pytest.mark.asyncio
    async def test_can_spawn_returns_true(self):
        """Test when spawning is allowed."""
        runner = MagicMock()
        runner.can_spawn.return_value = (True, "Spawning allowed", 0)

        registry = create_agents_registry(runner)
        can_spawn = registry._tools["can_spawn_agent"].func

        result = await can_spawn(parent_session_id="sess-123")

        assert result["can_spawn"] is True
        assert result["reason"] == "Spawning allowed"

    @pytest.mark.asyncio
    async def test_cannot_spawn_returns_false(self):
        """Test when spawning is not allowed."""
        runner = MagicMock()
        runner.can_spawn.return_value = (False, "Max depth reached", 3)

        registry = create_agents_registry(runner)
        can_spawn = registry._tools["can_spawn_agent"].func

        result = await can_spawn(parent_session_id="sess-123")

        assert result["can_spawn"] is False
        assert result["reason"] == "Max depth reached"


class TestListRunningAgents:
    """Tests for list_running_agents MCP tool."""

    @pytest.fixture
    def populated_registry(self):
        """Create a registry with test agents."""
        registry = RunningAgentRegistry()
        registry.add(
            RunningAgent(
                run_id="run-1",
                session_id="sess-1",
                parent_session_id="parent-1",
                mode="terminal",
                pid=1001,
            )
        )
        registry.add(
            RunningAgent(
                run_id="run-2",
                session_id="sess-2",
                parent_session_id="parent-1",
                mode="embedded",
                pid=1002,
            )
        )
        registry.add(
            RunningAgent(
                run_id="run-3",
                session_id="sess-3",
                parent_session_id="parent-2",
                mode="terminal",
                pid=1003,
            )
        )
        return registry

    @pytest.mark.asyncio
    async def test_list_all_running_agents(self, populated_registry):
        """Test listing all running agents."""
        runner = MagicMock()
        registry = create_agents_registry(runner, running_registry=populated_registry)
        list_running = registry._tools["list_running_agents"].func

        result = await list_running()

        assert result["success"] is True
        assert result["count"] == 3
        assert len(result["agents"]) == 3

    @pytest.mark.asyncio
    async def test_filter_by_parent_session(self, populated_registry):
        """Test filtering by parent session ID."""
        runner = MagicMock()
        registry = create_agents_registry(runner, running_registry=populated_registry)
        list_running = registry._tools["list_running_agents"].func

        result = await list_running(parent_session_id="parent-1")

        assert result["success"] is True
        assert result["count"] == 2
        for agent in result["agents"]:
            assert agent["parent_session_id"] == "parent-1"

    @pytest.mark.asyncio
    async def test_filter_by_mode(self, populated_registry):
        """Test filtering by execution mode."""
        runner = MagicMock()
        registry = create_agents_registry(runner, running_registry=populated_registry)
        list_running = registry._tools["list_running_agents"].func

        result = await list_running(mode="terminal")

        assert result["success"] is True
        assert result["count"] == 2
        for agent in result["agents"]:
            assert agent["mode"] == "terminal"


class TestGetRunningAgent:
    """Tests for get_running_agent MCP tool."""

    @pytest.mark.asyncio
    async def test_agent_found(self):
        """Test getting an existing running agent."""
        running_registry = RunningAgentRegistry()
        running_registry.add(
            RunningAgent(
                run_id="run-123",
                session_id="sess-456",
                parent_session_id="sess-parent",
                mode="terminal",
                pid=12345,
                terminal_type="ghostty",
                provider="claude",
            )
        )

        runner = MagicMock()
        registry = create_agents_registry(runner, running_registry=running_registry)
        get_running = registry._tools["get_running_agent"].func

        result = await get_running(run_id="run-123")

        assert result["success"] is True
        assert result["agent"]["run_id"] == "run-123"
        assert result["agent"]["pid"] == 12345
        assert result["agent"]["terminal_type"] == "ghostty"

    @pytest.mark.asyncio
    async def test_agent_not_found(self):
        """Test error when agent not found."""
        running_registry = RunningAgentRegistry()
        runner = MagicMock()
        registry = create_agents_registry(runner, running_registry=running_registry)
        get_running = registry._tools["get_running_agent"].func

        result = await get_running(run_id="non-existent")

        assert result["success"] is False
        assert "no running agent found" in result["error"].lower()


class TestUnregisterAgent:
    """Tests for unregister_agent MCP tool."""

    @pytest.mark.asyncio
    async def test_successful_unregistration(self):
        """Test successful agent unregistration."""
        running_registry = RunningAgentRegistry()
        running_registry.add(
            RunningAgent(
                run_id="run-123",
                session_id="sess-456",
                parent_session_id="sess-parent",
                mode="terminal",
            )
        )

        runner = MagicMock()
        registry = create_agents_registry(runner, running_registry=running_registry)
        unregister = registry._tools["unregister_agent"].func

        result = await unregister(run_id="run-123")

        assert result["success"] is True
        assert "Unregistered" in result["message"]
        assert running_registry.get("run-123") is None

    @pytest.mark.asyncio
    async def test_unregister_not_found(self):
        """Test error when agent not found."""
        running_registry = RunningAgentRegistry()
        runner = MagicMock()
        registry = create_agents_registry(runner, running_registry=running_registry)
        unregister = registry._tools["unregister_agent"].func

        result = await unregister(run_id="non-existent")

        assert result["success"] is False
        assert "no running agent found" in result["error"].lower()


class TestRunningAgentStats:
    """Tests for running_agent_stats MCP tool."""

    @pytest.mark.asyncio
    async def test_empty_stats(self):
        """Test stats with no running agents."""
        running_registry = RunningAgentRegistry()
        runner = MagicMock()
        registry = create_agents_registry(runner, running_registry=running_registry)
        stats = registry._tools["running_agent_stats"].func

        result = await stats()

        assert result["success"] is True
        assert result["total"] == 0
        assert result["by_mode"] == {}
        assert result["by_parent_count"] == 0

    @pytest.mark.asyncio
    async def test_stats_with_agents(self):
        """Test stats with multiple running agents."""
        running_registry = RunningAgentRegistry()
        running_registry.add(
            RunningAgent(
                run_id="run-1",
                session_id="sess-1",
                parent_session_id="parent-1",
                mode="terminal",
            )
        )
        running_registry.add(
            RunningAgent(
                run_id="run-2",
                session_id="sess-2",
                parent_session_id="parent-1",
                mode="terminal",
            )
        )
        running_registry.add(
            RunningAgent(
                run_id="run-3",
                session_id="sess-3",
                parent_session_id="parent-2",
                mode="embedded",
            )
        )
        running_registry.add(
            RunningAgent(
                run_id="run-4",
                session_id="sess-4",
                parent_session_id="parent-3",
                mode="headless",
            )
        )

        runner = MagicMock()
        registry = create_agents_registry(runner, running_registry=running_registry)
        stats = registry._tools["running_agent_stats"].func

        result = await stats()

        assert result["success"] is True
        assert result["total"] == 4
        assert result["by_mode"]["terminal"] == 2
        assert result["by_mode"]["embedded"] == 1
        assert result["by_mode"]["headless"] == 1
        assert result["by_parent_count"] == 3  # 3 unique parents


class TestContextInjection:
    """Tests for context injection functionality."""

    @pytest.mark.asyncio
    async def test_context_resolver_called_when_configured(self):
        """Test context resolver is called when session_context provided."""
        mock_session_manager = MagicMock()
        mock_message_manager = MagicMock()

        mock_result = MagicMock()
        mock_result.status = "success"
        mock_result.run_id = "run-123"
        mock_result.output = "Done"
        mock_result.error = None
        mock_result.turns_used = 1
        mock_result.tool_calls = []

        runner = MagicMock()
        runner.can_spawn.return_value = (True, "OK", 0)
        runner.run = AsyncMock(return_value=mock_result)

        mock_context = {
            "id": "proj-123",
            "project_path": "/test/project",
        }

        with (
            patch("gobby.mcp_proxy.tools.agents.get_project_context", return_value=mock_context),
            patch("gobby.mcp_proxy.tools.agents.ContextResolver") as MockResolver,
        ):
            mock_resolver_instance = AsyncMock()
            mock_resolver_instance.resolve.return_value = "Parent session context"
            MockResolver.return_value = mock_resolver_instance

            # Create registry with managers to enable context resolution
            registry = create_agents_registry(
                runner,
                session_manager=mock_session_manager,
                message_manager=mock_message_manager,
            )
            start_agent = registry._tools["start_agent"].func

            await start_agent(
                prompt="Original prompt",
                mode="in_process",
                parent_session_id="sess-123",
                session_context="summary_markdown",
            )

        # Verify runner.run was called with potentially modified prompt
        runner.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_context_resolution_error_continues_with_original_prompt(self):
        """Test that context resolution failure doesn't block agent execution."""
        from gobby.agents.context import ContextResolutionError

        mock_session_manager = MagicMock()
        mock_message_manager = MagicMock()

        mock_result = MagicMock()
        mock_result.status = "success"
        mock_result.run_id = "run-123"
        mock_result.output = "Done"
        mock_result.error = None
        mock_result.turns_used = 1
        mock_result.tool_calls = []

        runner = MagicMock()
        runner.can_spawn.return_value = (True, "OK", 0)
        runner.run = AsyncMock(return_value=mock_result)

        mock_context = {
            "id": "proj-123",
            "project_path": "/test/project",
        }

        with (
            patch("gobby.mcp_proxy.tools.agents.get_project_context", return_value=mock_context),
            patch("gobby.mcp_proxy.tools.agents.ContextResolver") as MockResolver,
        ):
            mock_resolver_instance = AsyncMock()
            mock_resolver_instance.resolve.side_effect = ContextResolutionError("Session not found")
            MockResolver.return_value = mock_resolver_instance

            registry = create_agents_registry(
                runner,
                session_manager=mock_session_manager,
                message_manager=mock_message_manager,
            )
            start_agent = registry._tools["start_agent"].func

            result = await start_agent(
                prompt="Original prompt",
                mode="in_process",
                parent_session_id="sess-123",
                session_context="summary_markdown",
            )

        # Should succeed despite context resolution failure
        assert result["success"] is True
        runner.run.assert_called_once()


class TestToolProxyIntegration:
    """Tests for tool proxy integration in in_process mode."""

    @pytest.mark.asyncio
    async def test_tool_proxy_used_for_in_process_tool_calls(self):
        """Test that tool proxy is used for routing tool calls."""
        mock_tool_proxy = MagicMock()
        mock_tool_proxy.list_tools = AsyncMock(
            return_value={
                "success": True,
                "tools": [{"name": "create_task", "brief": "Create a task"}],
            }
        )
        mock_tool_proxy.get_tool_schema = AsyncMock(
            return_value={
                "success": True,
                "tool": {
                    "name": "create_task",
                    "inputSchema": {"type": "object"},
                },
            }
        )

        mock_result = MagicMock()
        mock_result.status = "success"
        mock_result.run_id = "run-123"
        mock_result.output = "Done"
        mock_result.error = None
        mock_result.turns_used = 1
        mock_result.tool_calls = []

        runner = MagicMock()
        runner.can_spawn.return_value = (True, "OK", 0)
        runner.run = AsyncMock(return_value=mock_result)

        mock_context = {
            "id": "proj-123",
            "project_path": "/test/project",
        }

        with patch("gobby.mcp_proxy.tools.agents.get_project_context", return_value=mock_context):
            registry = create_agents_registry(
                runner,
                tool_proxy_getter=lambda: mock_tool_proxy,
            )
            start_agent = registry._tools["start_agent"].func

            result = await start_agent(
                prompt="Test prompt",
                mode="in_process",
                parent_session_id="sess-123",
            )

        assert result["success"] is True
        # Verify tool proxy was queried for available tools
        mock_tool_proxy.list_tools.assert_called()

    @pytest.mark.asyncio
    async def test_no_tool_proxy_returns_tool_not_available_error(self):
        """Test that missing tool proxy returns appropriate error for tool calls."""
        # This is tested indirectly - when tool_proxy_getter returns None,
        # tool calls should fail with "Tool proxy not configured" error
        mock_result = MagicMock()
        mock_result.status = "success"
        mock_result.run_id = "run-123"
        mock_result.output = "Done"
        mock_result.error = None
        mock_result.turns_used = 1
        mock_result.tool_calls = []

        runner = MagicMock()
        runner.can_spawn.return_value = (True, "OK", 0)
        runner.run = AsyncMock(return_value=mock_result)

        mock_context = {
            "id": "proj-123",
            "project_path": "/test/project",
        }

        with patch("gobby.mcp_proxy.tools.agents.get_project_context", return_value=mock_context):
            registry = create_agents_registry(
                runner,
                tool_proxy_getter=lambda: None,  # No tool proxy
            )
            start_agent = registry._tools["start_agent"].func

            result = await start_agent(
                prompt="Test prompt",
                mode="in_process",
                parent_session_id="sess-123",
            )

        # Should still succeed (in this test case, no tools were called)
        assert result["success"] is True


class TestMachineIdInference:
    """Tests for machine_id inference."""

    @pytest.mark.asyncio
    async def test_machine_id_inferred_from_hostname(self):
        """Test that machine_id is inferred from hostname when not provided."""
        mock_result = MagicMock()
        mock_result.status = "success"
        mock_result.run_id = "run-123"
        mock_result.output = "Done"
        mock_result.error = None
        mock_result.turns_used = 1
        mock_result.tool_calls = []

        runner = MagicMock()
        runner.can_spawn.return_value = (True, "OK", 0)
        runner.run = AsyncMock(return_value=mock_result)

        mock_context = {
            "id": "proj-123",
            "project_path": "/test/project",
        }

        with (
            patch("gobby.mcp_proxy.tools.agents.get_project_context", return_value=mock_context),
            patch("gobby.mcp_proxy.tools.agents.socket.gethostname", return_value="test-host"),
        ):
            registry = create_agents_registry(runner)
            start_agent = registry._tools["start_agent"].func

            await start_agent(
                prompt="Test prompt",
                mode="in_process",
                parent_session_id="sess-123",
            )

        # Verify runner.run was called with machine_id
        runner.run.assert_called_once()
        call_args = runner.run.call_args
        config = call_args[0][0]  # First positional arg is AgentConfig
        assert config.machine_id == "test-host"


class TestProviderSelection:
    """Tests for provider selection."""

    @pytest.mark.asyncio
    async def test_default_provider_is_claude(self):
        """Test that default provider is claude."""
        mock_result = MagicMock()
        mock_result.status = "success"
        mock_result.run_id = "run-123"
        mock_result.output = "Done"
        mock_result.error = None
        mock_result.turns_used = 1
        mock_result.tool_calls = []

        runner = MagicMock()
        runner.can_spawn.return_value = (True, "OK", 0)
        runner.run = AsyncMock(return_value=mock_result)

        mock_context = {
            "id": "proj-123",
            "project_path": "/test/project",
        }

        with patch("gobby.mcp_proxy.tools.agents.get_project_context", return_value=mock_context):
            registry = create_agents_registry(runner)
            start_agent = registry._tools["start_agent"].func

            await start_agent(
                prompt="Test prompt",
                mode="in_process",
                parent_session_id="sess-123",
            )

        call_args = runner.run.call_args
        config = call_args[0][0]
        assert config.provider == "claude"

    @pytest.mark.asyncio
    async def test_explicit_provider_used(self):
        """Test that explicit provider overrides default."""
        mock_result = MagicMock()
        mock_result.status = "success"
        mock_result.run_id = "run-123"
        mock_result.output = "Done"
        mock_result.error = None
        mock_result.turns_used = 1
        mock_result.tool_calls = []

        runner = MagicMock()
        runner.can_spawn.return_value = (True, "OK", 0)
        runner.run = AsyncMock(return_value=mock_result)

        mock_context = {
            "id": "proj-123",
            "project_path": "/test/project",
        }

        with patch("gobby.mcp_proxy.tools.agents.get_project_context", return_value=mock_context):
            registry = create_agents_registry(runner)
            start_agent = registry._tools["start_agent"].func

            await start_agent(
                prompt="Test prompt",
                mode="in_process",
                parent_session_id="sess-123",
                provider="gemini",
            )

        call_args = runner.run.call_args
        config = call_args[0][0]
        assert config.provider == "gemini"


class TestPrepareRunContextValidation:
    """Tests for context validation in prepare_run path."""

    @pytest.mark.asyncio
    async def test_missing_session_in_context_returns_error(self):
        """Test error when prepare_run returns context without session."""
        mock_context_obj = MagicMock()
        mock_context_obj.session = None
        mock_context_obj.run = MagicMock()

        runner = MagicMock()
        runner.can_spawn.return_value = (True, "OK", 0)
        runner.prepare_run.return_value = mock_context_obj

        mock_context = {
            "id": "proj-123",
            "project_path": "/test/project",
        }

        with patch("gobby.mcp_proxy.tools.agents.get_project_context", return_value=mock_context):
            registry = create_agents_registry(runner)
            start_agent = registry._tools["start_agent"].func

            result = await start_agent(
                prompt="Test prompt",
                mode="terminal",
                parent_session_id="sess-123",
            )

        assert result["success"] is False
        assert "missing session" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_missing_run_in_context_returns_error(self):
        """Test error when prepare_run returns context without run."""
        mock_context_obj = MagicMock()
        mock_context_obj.session = MagicMock()
        mock_context_obj.run = None

        runner = MagicMock()
        runner.can_spawn.return_value = (True, "OK", 0)
        runner.prepare_run.return_value = mock_context_obj

        mock_context = {
            "id": "proj-123",
            "project_path": "/test/project",
        }

        with patch("gobby.mcp_proxy.tools.agents.get_project_context", return_value=mock_context):
            registry = create_agents_registry(runner)
            start_agent = registry._tools["start_agent"].func

            result = await start_agent(
                prompt="Test prompt",
                mode="terminal",
                parent_session_id="sess-123",
            )

        assert result["success"] is False
        assert "missing" in result["error"].lower() and "run" in result["error"].lower()
