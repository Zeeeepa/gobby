"""Integration tests for start_agent MCP tool.

These tests verify the start_agent MCP tool across all 4 execution modes:
- in_process: SDK execution with tool routing
- terminal: Terminal spawning
- headless: CLI subprocess with output capture
- embedded: PTY-based spawning
"""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.agents.runner import AgentRunner
from gobby.agents.spawn import EmbeddedPTYResult, HeadlessResult, SpawnResult
from gobby.llm.executor import AgentResult
from gobby.mcp_proxy.tools.agents import create_agents_registry
from gobby.storage.database import LocalDatabase
from gobby.storage.migrations import run_migrations
from gobby.storage.projects import LocalProjectManager
from gobby.storage.sessions import LocalSessionManager

pytestmark = [pytest.mark.integration]


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = LocalDatabase(str(db_path))
        run_migrations(db)
        yield db


@pytest.fixture
def project(temp_db, tmp_path):
    """Create a test project."""
    project_manager = LocalProjectManager(temp_db)
    repo_path = tmp_path / "test-repo"
    repo_path.mkdir(parents=True, exist_ok=True)
    return project_manager.create(
        name="test-project",
        repo_path=str(repo_path),
    )


@pytest.fixture
def session_storage(temp_db):
    """Create session storage."""
    return LocalSessionManager(temp_db)


@pytest.fixture
def parent_session(session_storage, project):
    """Create a parent session."""
    return session_storage.register(
        machine_id="test-machine",
        source="claude",
        project_id=project.id,
        external_id="ext-start-agent-test",
        title="Parent Session",
    )


@pytest.fixture
def mock_executor():
    """Create a mock executor for in_process mode."""
    executor = MagicMock()
    executor.run = AsyncMock(
        return_value=AgentResult(
            output="Agent completed the task",
            status="success",
            turns_used=2,
            tool_calls=[],
        )
    )
    executor.provider_name = "claude"
    return executor


@pytest.fixture
def mock_message_manager():
    """Create a mock message manager."""
    manager = MagicMock()
    manager.get_messages = AsyncMock(return_value=[])
    return manager


@pytest.fixture
def mock_project_context(project, tmp_path):
    """Mock project context for tool invocation."""
    return {
        "id": project.id,
        "name": "test-project",
        "project_path": str(tmp_path / "test-repo"),
    }


class TestStartAgentInProcessMode:
    """Tests for start_agent with mode='in_process'."""

    async def test_successful_in_process_run(
        self,
        temp_db,
        session_storage,
        parent_session,
        project,
        mock_executor,
        mock_message_manager,
        mock_project_context,
    ):
        """in_process mode executes via SDK executor."""
        # Create runner
        runner = AgentRunner(
            db=temp_db,
            session_storage=session_storage,
            executors={"claude": mock_executor},
            max_agent_depth=3,
        )

        # Create tool proxy getter
        tool_proxy = MagicMock()
        tool_proxy.list_tools = AsyncMock(return_value={"success": True, "tools": []})

        def tool_proxy_getter():
            return tool_proxy

        # Create agents registry
        registry = create_agents_registry(
            runner=runner,
            session_manager=session_storage,
            message_manager=mock_message_manager,
            tool_proxy_getter=tool_proxy_getter,
        )

        # Call with mocked context
        with patch(
            "gobby.mcp_proxy.tools.agents.get_project_context",
            return_value=mock_project_context,
        ):
            result = await registry.call(
                "start_agent",
                {
                    "prompt": "Test task for in_process mode",
                    "mode": "in_process",
                    "parent_session_id": parent_session.id,
                    "project_id": project.id,
                    "machine_id": "test-machine",
                },
            )

        # Verify success
        assert result.get("success") is True
        assert result.get("status") == "success"
        assert "run_id" in result
        assert "output" in result

        # Verify executor was called
        mock_executor.run.assert_called_once()

    async def test_in_process_with_tool_routing(
        self,
        temp_db,
        session_storage,
        parent_session,
        project,
        mock_executor,
        mock_message_manager,
        mock_project_context,
    ):
        """in_process mode routes tool calls through MCP proxy."""
        runner = AgentRunner(
            db=temp_db,
            session_storage=session_storage,
            executors={"claude": mock_executor},
            max_agent_depth=3,
        )

        # Mock tool proxy with tools
        tool_proxy = MagicMock()
        tool_proxy.list_tools = AsyncMock(
            return_value={
                "success": True,
                "tools": [{"name": "test_tool", "brief": "A test tool"}],
            }
        )
        tool_proxy.get_tool_schema = AsyncMock(
            return_value={
                "success": True,
                "tool": {"inputSchema": {"type": "object", "properties": {}}},
            }
        )

        def tool_proxy_getter():
            return tool_proxy

        registry = create_agents_registry(
            runner=runner,
            session_manager=session_storage,
            message_manager=mock_message_manager,
            tool_proxy_getter=tool_proxy_getter,
        )

        with patch(
            "gobby.mcp_proxy.tools.agents.get_project_context",
            return_value=mock_project_context,
        ):
            result = await registry.call(
                "start_agent",
                {
                    "prompt": "Test with tools",
                    "mode": "in_process",
                    "parent_session_id": parent_session.id,
                    "project_id": project.id,
                    "machine_id": "test-machine",
                },
            )

        assert result.get("success") is True


class TestStartAgentTerminalMode:
    """Tests for start_agent with mode='terminal'."""

    async def test_terminal_mode_spawns_process(
        self,
        temp_db,
        session_storage,
        parent_session,
        project,
        mock_message_manager,
        mock_project_context,
    ):
        """terminal mode spawns CLI in terminal window."""
        # Create runner without executor (terminal mode doesn't use it directly)
        runner = AgentRunner(
            db=temp_db,
            session_storage=session_storage,
            executors={},
            max_agent_depth=3,
        )

        registry = create_agents_registry(
            runner=runner,
            session_manager=session_storage,
            message_manager=mock_message_manager,
        )

        # Mock the terminal spawner
        mock_spawn_result = SpawnResult(
            success=True,
            message="Spawned in terminal",
            pid=12345,
            terminal_type="ghostty",
        )

        with (
            patch(
                "gobby.mcp_proxy.tools.agents.get_project_context",
                return_value=mock_project_context,
            ),
            patch("gobby.mcp_proxy.tools.agents.TerminalSpawner") as mock_spawner_class,
        ):
            mock_spawner = MagicMock()
            mock_spawner.spawn_agent.return_value = mock_spawn_result
            mock_spawner_class.return_value = mock_spawner

            result = await registry.call(
                "start_agent",
                {
                    "prompt": "Test terminal mode",
                    "mode": "terminal",
                    "terminal": "ghostty",
                    "parent_session_id": parent_session.id,
                    "project_id": project.id,
                    "machine_id": "test-machine",
                },
            )

        # Verify success
        assert result.get("success") is True
        assert result.get("pid") == 12345
        assert "run_id" in result
        assert "child_session_id" in result

        # Verify spawner was called
        mock_spawner.spawn_agent.assert_called_once()

    async def test_terminal_mode_spawn_failure(
        self,
        temp_db,
        session_storage,
        parent_session,
        project,
        mock_message_manager,
        mock_project_context,
    ):
        """terminal mode handles spawn failure gracefully."""
        runner = AgentRunner(
            db=temp_db,
            session_storage=session_storage,
            executors={},
            max_agent_depth=3,
        )

        registry = create_agents_registry(
            runner=runner,
            session_manager=session_storage,
            message_manager=mock_message_manager,
        )

        # Mock spawn failure
        mock_spawn_result = SpawnResult(
            success=False,
            message="No terminal available",
            error="Terminal not found",
        )

        with (
            patch(
                "gobby.mcp_proxy.tools.agents.get_project_context",
                return_value=mock_project_context,
            ),
            patch("gobby.mcp_proxy.tools.agents.TerminalSpawner") as mock_spawner_class,
        ):
            mock_spawner = MagicMock()
            mock_spawner.spawn_agent.return_value = mock_spawn_result
            mock_spawner_class.return_value = mock_spawner

            result = await registry.call(
                "start_agent",
                {
                    "prompt": "Test terminal failure",
                    "mode": "terminal",
                    "parent_session_id": parent_session.id,
                    "project_id": project.id,
                    "machine_id": "test-machine",
                },
            )

        # Verify failure
        assert result.get("success") is False
        assert "error" in result


class TestStartAgentHeadlessMode:
    """Tests for start_agent with mode='headless'."""

    async def test_headless_mode_spawns_process(
        self,
        temp_db,
        session_storage,
        parent_session,
        project,
        mock_message_manager,
        mock_project_context,
    ):
        """headless mode spawns CLI with output capture."""
        runner = AgentRunner(
            db=temp_db,
            session_storage=session_storage,
            executors={},
            max_agent_depth=3,
        )

        registry = create_agents_registry(
            runner=runner,
            session_manager=session_storage,
            message_manager=mock_message_manager,
        )

        # Mock headless spawn result
        mock_headless_result = HeadlessResult(
            success=True,
            message="Spawned headless",
            pid=54321,
            process=MagicMock(),
            output_buffer=[],
        )

        with (
            patch(
                "gobby.mcp_proxy.tools.agents.get_project_context",
                return_value=mock_project_context,
            ),
            patch("gobby.mcp_proxy.tools.agents.HeadlessSpawner") as mock_spawner_class,
        ):
            mock_spawner = MagicMock()
            mock_spawner.spawn_agent.return_value = mock_headless_result
            mock_spawner_class.return_value = mock_spawner

            result = await registry.call(
                "start_agent",
                {
                    "prompt": "Test headless mode",
                    "mode": "headless",
                    "parent_session_id": parent_session.id,
                    "project_id": project.id,
                    "machine_id": "test-machine",
                },
            )

        # Verify success
        assert result.get("success") is True
        assert result.get("pid") == 54321
        assert "run_id" in result
        assert "child_session_id" in result

        # Verify spawner was called
        mock_spawner.spawn_agent.assert_called_once()


class TestStartAgentEmbeddedMode:
    """Tests for start_agent with mode='embedded'."""

    async def test_embedded_mode_spawns_pty(
        self,
        temp_db,
        session_storage,
        parent_session,
        project,
        mock_message_manager,
        mock_project_context,
    ):
        """embedded mode spawns CLI with PTY."""
        runner = AgentRunner(
            db=temp_db,
            session_storage=session_storage,
            executors={},
            max_agent_depth=3,
        )

        registry = create_agents_registry(
            runner=runner,
            session_manager=session_storage,
            message_manager=mock_message_manager,
        )

        # Mock embedded PTY result
        mock_pty_result = EmbeddedPTYResult(
            success=True,
            message="Spawned embedded PTY",
            master_fd=10,
            slave_fd=None,
            pid=99999,
        )

        with (
            patch(
                "gobby.mcp_proxy.tools.agents.get_project_context",
                return_value=mock_project_context,
            ),
            patch("gobby.mcp_proxy.tools.agents.EmbeddedSpawner") as mock_spawner_class,
        ):
            mock_spawner = MagicMock()
            mock_spawner.spawn_agent.return_value = mock_pty_result
            mock_spawner_class.return_value = mock_spawner

            result = await registry.call(
                "start_agent",
                {
                    "prompt": "Test embedded mode",
                    "mode": "embedded",
                    "parent_session_id": parent_session.id,
                    "project_id": project.id,
                    "machine_id": "test-machine",
                },
            )

        # Verify success
        assert result.get("success") is True
        assert result.get("pid") == 99999
        assert result.get("master_fd") == 10
        assert "run_id" in result
        assert "child_session_id" in result


class TestStartAgentSessionTracking:
    """Tests for session creation and tracking."""

    async def test_creates_child_session(
        self,
        temp_db,
        session_storage,
        parent_session,
        project,
        mock_executor,
        mock_message_manager,
        mock_project_context,
    ):
        """start_agent creates a child session."""
        runner = AgentRunner(
            db=temp_db,
            session_storage=session_storage,
            executors={"claude": mock_executor},
            max_agent_depth=3,
        )

        tool_proxy = MagicMock()
        tool_proxy.list_tools = AsyncMock(return_value={"success": True, "tools": []})

        def tool_proxy_getter():
            return tool_proxy

        registry = create_agents_registry(
            runner=runner,
            session_manager=session_storage,
            message_manager=mock_message_manager,
            tool_proxy_getter=tool_proxy_getter,
        )

        # Count children before
        children_before = session_storage.find_children(parent_session.id)

        with patch(
            "gobby.mcp_proxy.tools.agents.get_project_context",
            return_value=mock_project_context,
        ):
            result = await registry.call(
                "start_agent",
                {
                    "prompt": "Test session tracking",
                    "mode": "in_process",
                    "parent_session_id": parent_session.id,
                    "project_id": project.id,
                    "machine_id": "test-machine",
                },
            )

        # Count children after
        children_after = session_storage.find_children(parent_session.id)

        assert result.get("success") is True
        assert len(children_after) == len(children_before) + 1

        # Verify child session properties
        child = children_after[-1]
        assert child.parent_session_id == parent_session.id
        assert child.agent_depth == 1


class TestStartAgentErrorHandling:
    """Tests for error handling."""

    async def test_invalid_mode(
        self,
        temp_db,
        session_storage,
        parent_session,
        project,
        mock_message_manager,
        mock_project_context,
    ):
        """start_agent rejects invalid mode."""
        runner = AgentRunner(
            db=temp_db,
            session_storage=session_storage,
            executors={},
            max_agent_depth=3,
        )

        registry = create_agents_registry(
            runner=runner,
            session_manager=session_storage,
            message_manager=mock_message_manager,
        )

        with patch(
            "gobby.mcp_proxy.tools.agents.get_project_context",
            return_value=mock_project_context,
        ):
            result = await registry.call(
                "start_agent",
                {
                    "prompt": "Test invalid mode",
                    "mode": "invalid_mode",
                    "parent_session_id": parent_session.id,
                    "project_id": project.id,
                    "machine_id": "test-machine",
                },
            )

        assert result.get("success") is False
        assert "Invalid mode" in result.get("error", "")

    async def test_missing_project_context(
        self,
        temp_db,
        session_storage,
        mock_message_manager,
    ):
        """start_agent handles missing project context."""
        runner = AgentRunner(
            db=temp_db,
            session_storage=session_storage,
            executors={},
            max_agent_depth=3,
        )

        registry = create_agents_registry(
            runner=runner,
            session_manager=session_storage,
            message_manager=mock_message_manager,
        )

        # No project context
        with patch(
            "gobby.mcp_proxy.tools.agents.get_project_context",
            return_value=None,
        ):
            result = await registry.call(
                "start_agent",
                {
                    "prompt": "Test missing context",
                    "mode": "in_process",
                },
            )

        assert result.get("success") is False
        assert "project" in result.get("error", "").lower()

    async def test_missing_parent_session_id(
        self,
        temp_db,
        session_storage,
        mock_message_manager,
        mock_project_context,
    ):
        """start_agent requires parent_session_id."""
        runner = AgentRunner(
            db=temp_db,
            session_storage=session_storage,
            executors={},
            max_agent_depth=3,
        )

        registry = create_agents_registry(
            runner=runner,
            session_manager=session_storage,
            message_manager=mock_message_manager,
        )

        with patch(
            "gobby.mcp_proxy.tools.agents.get_project_context",
            return_value=mock_project_context,
        ):
            result = await registry.call(
                "start_agent",
                {
                    "prompt": "Test missing parent session",
                    "mode": "in_process",
                },
            )

        assert result.get("success") is False
        assert "parent_session_id" in result.get("error", "").lower()
