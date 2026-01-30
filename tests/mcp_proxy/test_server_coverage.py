"""Additional coverage tests for GobbyDaemonTools in server.py.

Targets uncovered lines: 202-233, 285-287, 298-339, 345-422, 424-461, 463-511
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


class TestListHookHandlers:
    """Tests for list_hook_handlers method (lines 298-339)."""

    @pytest.mark.asyncio
    async def test_list_hook_handlers_no_internal_manager(self, mock_mcp_manager):
        """Test error when internal manager is not available."""
        handler = GobbyDaemonTools(
            mcp_manager=mock_mcp_manager,
            daemon_port=8787,
            websocket_port=8788,
            start_time=1000.0,
            internal_manager=None,
        )

        result = await handler.list_hook_handlers()

        assert result["success"] is False
        assert "not available" in result["error"]

    @pytest.mark.asyncio
    async def test_list_hook_handlers_no_hook_manager(
        self, mock_mcp_manager, mock_internal_manager
    ):
        """Test when hook manager is not available."""
        mock_internal_manager._hook_manager = None

        handler = GobbyDaemonTools(
            mcp_manager=mock_mcp_manager,
            daemon_port=8787,
            websocket_port=8788,
            start_time=1000.0,
            internal_manager=mock_internal_manager,
        )

        result = await handler.list_hook_handlers()

        assert result["success"] is True
        assert result["handlers"] == {}
        assert "not loaded" in result["message"]

    @pytest.mark.asyncio
    async def test_list_hook_handlers_no_plugin_loader(
        self, mock_mcp_manager, mock_internal_manager
    ):
        """Test when plugin loader is not available."""
        mock_hook_manager = MagicMock()
        mock_hook_manager.plugin_loader = None
        mock_internal_manager._hook_manager = mock_hook_manager

        handler = GobbyDaemonTools(
            mcp_manager=mock_mcp_manager,
            daemon_port=8787,
            websocket_port=8788,
            start_time=1000.0,
            internal_manager=mock_internal_manager,
        )

        result = await handler.list_hook_handlers()

        assert result["success"] is True
        assert result["handlers"] == {}
        assert "not initialized" in result["message"]

    @pytest.mark.asyncio
    async def test_list_hook_handlers_success(self, mock_mcp_manager, mock_internal_manager):
        """Test successful handler listing."""
        from gobby.hooks.events import HookEventType

        # Mock plugin and handler structures
        mock_plugin = MagicMock()
        mock_plugin.name = "test-plugin"

        mock_handler = MagicMock()
        mock_handler.plugin = mock_plugin
        mock_handler.method = MagicMock(__name__="on_session_start")
        mock_handler.priority = 10

        mock_registry = MagicMock()

        # Return handler for SESSION_START, empty for others
        def get_handlers_for_type(event_type):
            if event_type == HookEventType.SESSION_START:
                return [mock_handler]
            return []

        mock_registry.get_handlers.side_effect = get_handlers_for_type

        mock_plugin_loader = MagicMock()
        mock_plugin_loader.registry = mock_registry

        mock_hook_manager = MagicMock()
        mock_hook_manager.plugin_loader = mock_plugin_loader
        mock_internal_manager._hook_manager = mock_hook_manager

        handler = GobbyDaemonTools(
            mcp_manager=mock_mcp_manager,
            daemon_port=8787,
            websocket_port=8788,
            start_time=1000.0,
            internal_manager=mock_internal_manager,
        )

        result = await handler.list_hook_handlers()

        assert result["success"] is True
        assert "handlers" in result
        assert result["total_handlers"] >= 1
        assert "session_start" in result["handlers"]

    @pytest.mark.asyncio
    async def test_list_hook_handlers_multiple_event_types(
        self, mock_mcp_manager, mock_internal_manager
    ):
        """Test listing handlers for multiple event types."""
        from gobby.hooks.events import HookEventType

        mock_plugin = MagicMock()
        mock_plugin.name = "my-plugin"

        mock_handler1 = MagicMock()
        mock_handler1.plugin = mock_plugin
        mock_handler1.method = MagicMock(__name__="handle_start")
        mock_handler1.priority = 10

        mock_handler2 = MagicMock()
        mock_handler2.plugin = mock_plugin
        mock_handler2.method = MagicMock(__name__="handle_stop")
        mock_handler2.priority = 60

        mock_registry = MagicMock()

        def get_handlers_side_effect(event_type):
            if event_type == HookEventType.SESSION_START:
                return [mock_handler1]
            elif event_type == HookEventType.STOP:
                return [mock_handler2]
            return []

        mock_registry.get_handlers.side_effect = get_handlers_side_effect

        mock_plugin_loader = MagicMock()
        mock_plugin_loader.registry = mock_registry

        mock_hook_manager = MagicMock()
        mock_hook_manager.plugin_loader = mock_plugin_loader
        mock_internal_manager._hook_manager = mock_hook_manager

        handler = GobbyDaemonTools(
            mcp_manager=mock_mcp_manager,
            daemon_port=8787,
            websocket_port=8788,
            start_time=1000.0,
            internal_manager=mock_internal_manager,
        )

        result = await handler.list_hook_handlers()

        assert result["success"] is True
        assert result["total_handlers"] == 2


class TestTestHookEvent:
    """Tests for test_hook_event method (lines 345-422)."""

    @pytest.mark.asyncio
    async def test_test_hook_event_no_internal_manager(self, mock_mcp_manager):
        """Test error when internal manager is not available."""
        handler = GobbyDaemonTools(
            mcp_manager=mock_mcp_manager,
            daemon_port=8787,
            websocket_port=8788,
            start_time=1000.0,
            internal_manager=None,
        )

        result = await handler.test_hook_event(
            event_type="session_start",
            source="claude",
        )

        assert result["success"] is False
        assert "not available" in result["error"]

    @pytest.mark.asyncio
    async def test_test_hook_event_no_hook_manager(self, mock_mcp_manager, mock_internal_manager):
        """Test error when hook manager is not available."""
        mock_internal_manager._hook_manager = None

        handler = GobbyDaemonTools(
            mcp_manager=mock_mcp_manager,
            daemon_port=8787,
            websocket_port=8788,
            start_time=1000.0,
            internal_manager=mock_internal_manager,
        )

        result = await handler.test_hook_event(
            event_type="session_start",
            source="claude",
        )

        assert result["success"] is False
        assert "No hook manager" in result["error"]

    @pytest.mark.asyncio
    async def test_test_hook_event_invalid_event_type(
        self, mock_mcp_manager, mock_internal_manager
    ):
        """Test error for invalid event type."""
        mock_hook_manager = MagicMock()
        mock_internal_manager._hook_manager = mock_hook_manager

        handler = GobbyDaemonTools(
            mcp_manager=mock_mcp_manager,
            daemon_port=8787,
            websocket_port=8788,
            start_time=1000.0,
            internal_manager=mock_internal_manager,
        )

        result = await handler.test_hook_event(
            event_type="invalid_event_type",
            source="claude",
        )

        assert result["success"] is False
        assert "Invalid event type" in result["error"]
        assert "valid_types" in result

    @pytest.mark.asyncio
    async def test_test_hook_event_success(self, mock_mcp_manager, mock_internal_manager):
        """Test successful hook event processing."""
        mock_hook_manager = MagicMock()
        mock_hook_manager.process_event.return_value = {
            "continue": True,
            "reason": None,
            "inject_context": "Test context",
        }
        mock_internal_manager._hook_manager = mock_hook_manager

        handler = GobbyDaemonTools(
            mcp_manager=mock_mcp_manager,
            daemon_port=8787,
            websocket_port=8788,
            start_time=1000.0,
            internal_manager=mock_internal_manager,
        )

        result = await handler.test_hook_event(
            event_type="session_start",
            source="claude",
            data={"extra_key": "extra_value"},
        )

        assert result["success"] is True
        assert result["event_type"] == "session_start"
        assert result["continue"] is True
        assert result["inject_context"] == "Test context"

    @pytest.mark.asyncio
    async def test_test_hook_event_invalid_source_defaults_to_claude(
        self, mock_mcp_manager, mock_internal_manager
    ):
        """Test that invalid source defaults to Claude."""
        mock_hook_manager = MagicMock()
        mock_hook_manager.process_event.return_value = {"continue": True}
        mock_internal_manager._hook_manager = mock_hook_manager

        handler = GobbyDaemonTools(
            mcp_manager=mock_mcp_manager,
            daemon_port=8787,
            websocket_port=8788,
            start_time=1000.0,
            internal_manager=mock_internal_manager,
        )

        result = await handler.test_hook_event(
            event_type="session_start",
            source="invalid_source",  # Should default to claude
        )

        assert result["success"] is True
        # Verify the event was created with the source (defaulting to claude internally)
        call_args = mock_hook_manager.process_event.call_args
        assert call_args is not None
        # Extract the event from call args and verify source defaulted to "claude"
        event = call_args[0][0] if call_args[0] else call_args.kwargs.get("event")
        assert event is not None
        assert event.source.value == "claude"

    @pytest.mark.asyncio
    async def test_test_hook_event_gemini_source(self, mock_mcp_manager, mock_internal_manager):
        """Test hook event with gemini source."""
        mock_hook_manager = MagicMock()
        mock_hook_manager.process_event.return_value = {"continue": True}
        mock_internal_manager._hook_manager = mock_hook_manager

        handler = GobbyDaemonTools(
            mcp_manager=mock_mcp_manager,
            daemon_port=8787,
            websocket_port=8788,
            start_time=1000.0,
            internal_manager=mock_internal_manager,
        )

        result = await handler.test_hook_event(
            event_type="session_start",
            source="gemini",
        )

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_test_hook_event_process_exception(self, mock_mcp_manager, mock_internal_manager):
        """Test exception handling during event processing."""
        mock_hook_manager = MagicMock()
        mock_hook_manager.process_event.side_effect = RuntimeError("Plugin crashed")
        mock_internal_manager._hook_manager = mock_hook_manager

        handler = GobbyDaemonTools(
            mcp_manager=mock_mcp_manager,
            daemon_port=8787,
            websocket_port=8788,
            start_time=1000.0,
            internal_manager=mock_internal_manager,
        )

        result = await handler.test_hook_event(
            event_type="session_start",
            source="claude",
        )

        assert result["success"] is False
        assert "Plugin crashed" in result["error"]

    @pytest.mark.asyncio
    async def test_test_hook_event_blocked_response(self, mock_mcp_manager, mock_internal_manager):
        """Test hook event that returns blocked response."""
        mock_hook_manager = MagicMock()
        mock_hook_manager.process_event.return_value = {
            "continue": False,
            "reason": "Plugin blocked this event",
            "inject_context": None,
        }
        mock_internal_manager._hook_manager = mock_hook_manager

        handler = GobbyDaemonTools(
            mcp_manager=mock_mcp_manager,
            daemon_port=8787,
            websocket_port=8788,
            start_time=1000.0,
            internal_manager=mock_internal_manager,
        )

        result = await handler.test_hook_event(
            event_type="stop",  # Using valid event type that can be blocked
            source="claude",
        )

        assert result["success"] is True
        assert result["continue"] is False
        assert result["reason"] == "Plugin blocked this event"


class TestListPlugins:
    """Tests for list_plugins method (lines 424-461)."""

    @pytest.mark.asyncio
    async def test_list_plugins_no_internal_manager(self, mock_mcp_manager):
        """Test error when internal manager is not available."""
        handler = GobbyDaemonTools(
            mcp_manager=mock_mcp_manager,
            daemon_port=8787,
            websocket_port=8788,
            start_time=1000.0,
            internal_manager=None,
        )

        result = await handler.list_plugins()

        assert result["success"] is False
        assert "not available" in result["error"]

    @pytest.mark.asyncio
    async def test_list_plugins_no_hook_manager(self, mock_mcp_manager, mock_internal_manager):
        """Test when hook manager is not available."""
        mock_internal_manager._hook_manager = None

        handler = GobbyDaemonTools(
            mcp_manager=mock_mcp_manager,
            daemon_port=8787,
            websocket_port=8788,
            start_time=1000.0,
            internal_manager=mock_internal_manager,
        )

        result = await handler.list_plugins()

        assert result["success"] is True
        assert result["enabled"] is False
        assert result["plugins"] == []
        assert "not initialized" in result["message"]

    @pytest.mark.asyncio
    async def test_list_plugins_no_plugin_loader(self, mock_mcp_manager, mock_internal_manager):
        """Test when plugin loader is not available."""
        mock_hook_manager = MagicMock()
        mock_hook_manager.plugin_loader = None
        mock_internal_manager._hook_manager = mock_hook_manager

        handler = GobbyDaemonTools(
            mcp_manager=mock_mcp_manager,
            daemon_port=8787,
            websocket_port=8788,
            start_time=1000.0,
            internal_manager=mock_internal_manager,
        )

        result = await handler.list_plugins()

        assert result["success"] is True
        assert result["enabled"] is False
        assert result["plugins"] == []
        assert "No plugin loader" in result["message"]

    @pytest.mark.asyncio
    async def test_list_plugins_success(self, mock_mcp_manager, mock_internal_manager):
        """Test successful plugin listing."""
        mock_config = MagicMock()
        mock_config.enabled = True
        mock_config.plugin_dirs = ["/path/to/plugins", "/another/path"]

        mock_registry = MagicMock()
        mock_registry.list_plugins.return_value = [
            {"name": "plugin1", "version": "1.0.0", "description": "First plugin"},
            {"name": "plugin2", "version": "2.0.0", "description": "Second plugin"},
        ]

        mock_plugin_loader = MagicMock()
        mock_plugin_loader.config = mock_config
        mock_plugin_loader.registry = mock_registry

        mock_hook_manager = MagicMock()
        mock_hook_manager.plugin_loader = mock_plugin_loader
        mock_internal_manager._hook_manager = mock_hook_manager

        handler = GobbyDaemonTools(
            mcp_manager=mock_mcp_manager,
            daemon_port=8787,
            websocket_port=8788,
            start_time=1000.0,
            internal_manager=mock_internal_manager,
        )

        result = await handler.list_plugins()

        assert result["success"] is True
        assert result["enabled"] is True
        assert len(result["plugins"]) == 2
        assert result["plugin_dirs"] == ["/path/to/plugins", "/another/path"]

    @pytest.mark.asyncio
    async def test_list_plugins_disabled(self, mock_mcp_manager, mock_internal_manager):
        """Test listing plugins when plugin system is disabled."""
        mock_config = MagicMock()
        mock_config.enabled = False
        mock_config.plugin_dirs = []

        mock_registry = MagicMock()
        mock_registry.list_plugins.return_value = []

        mock_plugin_loader = MagicMock()
        mock_plugin_loader.config = mock_config
        mock_plugin_loader.registry = mock_registry

        mock_hook_manager = MagicMock()
        mock_hook_manager.plugin_loader = mock_plugin_loader
        mock_internal_manager._hook_manager = mock_hook_manager

        handler = GobbyDaemonTools(
            mcp_manager=mock_mcp_manager,
            daemon_port=8787,
            websocket_port=8788,
            start_time=1000.0,
            internal_manager=mock_internal_manager,
        )

        result = await handler.list_plugins()

        assert result["success"] is True
        assert result["enabled"] is False


class TestReloadPlugin:
    """Tests for reload_plugin method (lines 463-511)."""

    @pytest.mark.asyncio
    async def test_reload_plugin_no_internal_manager(self, mock_mcp_manager):
        """Test error when internal manager is not available."""
        handler = GobbyDaemonTools(
            mcp_manager=mock_mcp_manager,
            daemon_port=8787,
            websocket_port=8788,
            start_time=1000.0,
            internal_manager=None,
        )

        result = await handler.reload_plugin(name="test-plugin")

        assert result["success"] is False
        assert "not available" in result["error"]

    @pytest.mark.asyncio
    async def test_reload_plugin_no_hook_manager(self, mock_mcp_manager, mock_internal_manager):
        """Test error when hook manager is not available."""
        mock_internal_manager._hook_manager = None

        handler = GobbyDaemonTools(
            mcp_manager=mock_mcp_manager,
            daemon_port=8787,
            websocket_port=8788,
            start_time=1000.0,
            internal_manager=mock_internal_manager,
        )

        result = await handler.reload_plugin(name="test-plugin")

        assert result["success"] is False
        assert "not initialized" in result["error"]

    @pytest.mark.asyncio
    async def test_reload_plugin_no_plugin_loader(self, mock_mcp_manager, mock_internal_manager):
        """Test error when plugin loader is not available."""
        mock_hook_manager = MagicMock()
        mock_hook_manager.plugin_loader = None
        mock_internal_manager._hook_manager = mock_hook_manager

        handler = GobbyDaemonTools(
            mcp_manager=mock_mcp_manager,
            daemon_port=8787,
            websocket_port=8788,
            start_time=1000.0,
            internal_manager=mock_internal_manager,
        )

        result = await handler.reload_plugin(name="test-plugin")

        assert result["success"] is False
        assert "No plugin loader" in result["error"]

    @pytest.mark.asyncio
    async def test_reload_plugin_not_found(self, mock_mcp_manager, mock_internal_manager):
        """Test error when plugin is not found."""
        mock_plugin_loader = MagicMock()
        mock_plugin_loader.reload_plugin.return_value = None

        mock_hook_manager = MagicMock()
        mock_hook_manager.plugin_loader = mock_plugin_loader
        mock_internal_manager._hook_manager = mock_hook_manager

        handler = GobbyDaemonTools(
            mcp_manager=mock_mcp_manager,
            daemon_port=8787,
            websocket_port=8788,
            start_time=1000.0,
            internal_manager=mock_internal_manager,
        )

        result = await handler.reload_plugin(name="nonexistent-plugin")

        assert result["success"] is False
        assert "not found" in result["error"] or "reload failed" in result["error"]
        assert "nonexistent-plugin" in result["error"]

    @pytest.mark.asyncio
    async def test_reload_plugin_success(self, mock_mcp_manager, mock_internal_manager):
        """Test successful plugin reload."""
        mock_plugin = MagicMock()
        mock_plugin.name = "my-plugin"
        mock_plugin.version = "1.2.3"
        mock_plugin.description = "A reloaded plugin"

        mock_plugin_loader = MagicMock()
        mock_plugin_loader.reload_plugin.return_value = mock_plugin

        mock_hook_manager = MagicMock()
        mock_hook_manager.plugin_loader = mock_plugin_loader
        mock_internal_manager._hook_manager = mock_hook_manager

        handler = GobbyDaemonTools(
            mcp_manager=mock_mcp_manager,
            daemon_port=8787,
            websocket_port=8788,
            start_time=1000.0,
            internal_manager=mock_internal_manager,
        )

        result = await handler.reload_plugin(name="my-plugin")

        assert result["success"] is True
        assert result["name"] == "my-plugin"
        assert result["version"] == "1.2.3"
        assert result["description"] == "A reloaded plugin"

        mock_plugin_loader.reload_plugin.assert_called_once_with("my-plugin")

    @pytest.mark.asyncio
    async def test_reload_plugin_exception(self, mock_mcp_manager, mock_internal_manager):
        """Test exception handling during plugin reload."""
        mock_plugin_loader = MagicMock()
        mock_plugin_loader.reload_plugin.side_effect = RuntimeError("File not found")

        mock_hook_manager = MagicMock()
        mock_hook_manager.plugin_loader = mock_plugin_loader
        mock_internal_manager._hook_manager = mock_hook_manager

        handler = GobbyDaemonTools(
            mcp_manager=mock_mcp_manager,
            daemon_port=8787,
            websocket_port=8788,
            start_time=1000.0,
            internal_manager=mock_internal_manager,
        )

        result = await handler.reload_plugin(name="broken-plugin")

        assert result["success"] is False
        assert "File not found" in result["error"]
