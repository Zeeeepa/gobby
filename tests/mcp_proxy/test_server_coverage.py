"""Additional coverage tests for GobbyDaemonTools in server.py."""

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
