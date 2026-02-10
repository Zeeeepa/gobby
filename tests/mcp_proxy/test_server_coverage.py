"""Additional coverage tests for GobbyDaemonTools in server.py.

Targets uncovered lines: 202-233, 285-287
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from gobby.mcp_proxy.server import GobbyDaemonTools

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_mcp_manager():
    """Create a mock MCP client manager."""
    manager = MagicMock()
    manager.project_id = "test-project-id"
    manager.connections = {}
    manager.health = {}
    manager.server_configs = []
    manager.get_server_health.return_value = {}
    manager.get_lazy_connection_states.return_value = {}
    return manager


@pytest.fixture
def mock_internal_manager():
    """Create a mock internal tool manager."""
    return MagicMock()


@pytest.fixture
def tools_handler(mock_mcp_manager, mock_internal_manager):
    """Create a GobbyDaemonTools instance for testing."""
    return GobbyDaemonTools(
        mcp_manager=mock_mcp_manager,
        daemon_port=8787,
        websocket_port=8788,
        start_time=1000.0,
        internal_manager=mock_internal_manager,
    )


class TestGetToolAlternatives:
    """Tests for get_tool_alternatives method (lines 202-233)."""

    @pytest.mark.asyncio
    async def test_get_tool_alternatives_no_project_id(
        self, mock_mcp_manager, mock_internal_manager
    ):
        """Test error when no project_id is available."""
        mock_mcp_manager.project_id = None

        handler = GobbyDaemonTools(
            mcp_manager=mock_mcp_manager,
            daemon_port=8787,
            websocket_port=8788,
            start_time=1000.0,
            internal_manager=mock_internal_manager,
        )

        result = await handler.get_tool_alternatives(
            server_name="test-server",
            tool_name="test-tool",
        )

        assert result["success"] is False
        assert "No project_id" in result["error"]
        assert "gobby init" in result["error"]

    @pytest.mark.asyncio
    async def test_get_tool_alternatives_no_fallback_resolver(
        self, mock_mcp_manager, mock_internal_manager
    ):
        """Test error when fallback resolver is not configured."""
        handler = GobbyDaemonTools(
            mcp_manager=mock_mcp_manager,
            daemon_port=8787,
            websocket_port=8788,
            start_time=1000.0,
            internal_manager=mock_internal_manager,
            fallback_resolver=None,
        )

        result = await handler.get_tool_alternatives(
            server_name="test-server",
            tool_name="test-tool",
        )

        assert result["success"] is False
        assert "not configured" in result["error"]

    @pytest.mark.asyncio
    async def test_get_tool_alternatives_success(self, mock_mcp_manager, mock_internal_manager):
        """Test successful alternative suggestions."""
        mock_fallback = AsyncMock()
        mock_fallback.find_alternatives_for_error = AsyncMock(
            return_value=[
                {"tool": "alt-tool-1", "server": "server-1", "score": 0.9},
                {"tool": "alt-tool-2", "server": "server-2", "score": 0.7},
            ]
        )

        handler = GobbyDaemonTools(
            mcp_manager=mock_mcp_manager,
            daemon_port=8787,
            websocket_port=8788,
            start_time=1000.0,
            internal_manager=mock_internal_manager,
            fallback_resolver=mock_fallback,
        )

        result = await handler.get_tool_alternatives(
            server_name="test-server",
            tool_name="test-tool",
            error_message="Connection timeout",
            top_k=5,
        )

        assert result["success"] is True
        assert result["failed_tool"] == "test-server/test-tool"
        assert result["count"] == 2
        assert len(result["alternatives"]) == 2

        mock_fallback.find_alternatives_for_error.assert_called_once_with(
            server_name="test-server",
            tool_name="test-tool",
            error_message="Connection timeout",
            project_id="test-project-id",
            top_k=5,
        )

    @pytest.mark.asyncio
    async def test_get_tool_alternatives_default_error_message(
        self, mock_mcp_manager, mock_internal_manager
    ):
        """Test that default error message is used when not provided."""
        mock_fallback = AsyncMock()
        mock_fallback.find_alternatives_for_error = AsyncMock(return_value=[])

        handler = GobbyDaemonTools(
            mcp_manager=mock_mcp_manager,
            daemon_port=8787,
            websocket_port=8788,
            start_time=1000.0,
            internal_manager=mock_internal_manager,
            fallback_resolver=mock_fallback,
        )

        await handler.get_tool_alternatives(
            server_name="test-server",
            tool_name="test-tool",
            error_message=None,
        )

        call_args = mock_fallback.find_alternatives_for_error.call_args
        assert call_args.kwargs["error_message"] == "Tool call failed"

    @pytest.mark.asyncio
    async def test_get_tool_alternatives_exception_handling(
        self, mock_mcp_manager, mock_internal_manager
    ):
        """Test exception handling in get_tool_alternatives."""
        mock_fallback = AsyncMock()
        mock_fallback.find_alternatives_for_error = AsyncMock(
            side_effect=Exception("Database connection error")
        )

        handler = GobbyDaemonTools(
            mcp_manager=mock_mcp_manager,
            daemon_port=8787,
            websocket_port=8788,
            start_time=1000.0,
            internal_manager=mock_internal_manager,
            fallback_resolver=mock_fallback,
        )

        result = await handler.get_tool_alternatives(
            server_name="test-server",
            tool_name="test-tool",
        )

        assert result["success"] is False
        assert "Database connection error" in result["error"]


class TestSearchToolsExceptionHandling:
    """Tests for search_tools exception handling (lines 285-287)."""

    @pytest.mark.asyncio
    async def test_search_tools_exception_returns_error(
        self, mock_mcp_manager, mock_internal_manager
    ):
        """Test that exceptions in semantic search are caught and returned."""
        mock_semantic = AsyncMock()
        mock_semantic.search_tools = AsyncMock(side_effect=RuntimeError("Embedding model failed"))

        handler = GobbyDaemonTools(
            mcp_manager=mock_mcp_manager,
            daemon_port=8787,
            websocket_port=8788,
            start_time=1000.0,
            internal_manager=mock_internal_manager,
            semantic_search=mock_semantic,
        )

        result = await handler.search_tools(query="find files")

        assert result["success"] is False
        assert "Embedding model failed" in result["error"]
        assert result["query"] == "find files"


# TestListHookHandlers, TestTestHookEvent, TestListPlugins, TestReloadPlugin
# moved to tests/mcp_proxy/tools/test_plugins.py (gobby-plugins internal registry)
