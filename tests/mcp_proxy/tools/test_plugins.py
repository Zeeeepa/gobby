"""
Tests for gobby.mcp_proxy.tools.plugins module.

Tests the plugin MCP tools including:
- list_plugins, get_plugin, reload_plugin, get_plugin_config (core)
- call_plugin_action, list_plugin_actions, list_plugin_conditions (interaction)
- list_hook_handlers, test_hook_event (hooks)
"""

from unittest.mock import MagicMock

import pytest

from gobby.mcp_proxy.tools.plugins import create_plugins_registry

pytestmark = pytest.mark.unit


# --- Fixtures ---


@pytest.fixture
def mock_plugin():
    """Create a mock HookPlugin."""
    plugin = MagicMock()
    plugin.name = "test-plugin"
    plugin.version = "1.0.0"
    plugin.description = "A test plugin"
    plugin._actions = {}
    plugin._conditions = {"is_admin": MagicMock()}
    return plugin


@pytest.fixture
def mock_plugin_action():
    """Create a mock PluginAction."""
    action = MagicMock()
    action.name = "greet"
    action.schema = {"type": "object", "properties": {"name": {"type": "string"}}}
    action.plugin_name = "test-plugin"
    action.validate_input.return_value = (True, None)
    action.handler = MagicMock(return_value={"greeting": "hello"})
    return action


@pytest.fixture
def mock_plugin_loader(mock_plugin, mock_plugin_action):
    """Create a mock PluginLoader with registry."""
    loader = MagicMock()
    loader.config.enabled = True
    loader.config.auto_discover = True
    loader.config.plugin_dirs = ["~/.gobby/plugins", ".gobby/plugins"]
    loader.config.plugins = {}

    # Mock registry
    loader.registry.list_plugins.return_value = [
        {
            "name": "test-plugin",
            "version": "1.0.0",
            "description": "A test plugin",
            "handlers": [{"event": "session_start", "priority": 50}],
            "actions": [{"name": "greet", "has_schema": True, "schema": action.schema}],
            "conditions": ["is_admin"],
        }
        for action in [mock_plugin_action]
    ]
    loader.registry.get_plugin.return_value = mock_plugin
    loader.registry.get_plugin_action.return_value = mock_plugin_action
    loader.registry.get_handlers.return_value = []

    # Mock reload
    loader.reload_plugin.return_value = mock_plugin

    return loader


@pytest.fixture
def mock_hook_manager(mock_plugin_loader):
    """Create a mock HookManager with _plugin_loader."""
    hm = MagicMock()
    hm._plugin_loader = mock_plugin_loader
    return hm


@pytest.fixture
def registry(mock_hook_manager):
    """Create a plugins registry with a mock hook manager."""
    return create_plugins_registry(
        hook_manager_resolver=lambda: mock_hook_manager,
    )


@pytest.fixture
def registry_no_hm():
    """Create a plugins registry with no hook manager (not yet available)."""
    return create_plugins_registry(
        hook_manager_resolver=lambda: None,
    )


# --- Core Tools ---


class TestListPlugins:
    @pytest.mark.asyncio
    async def test_list_plugins(self, registry):
        result = await registry.call("list_plugins", {})
        assert result["success"] is True
        assert result["enabled"] is True
        assert len(result["plugins"]) == 1
        assert result["plugins"][0]["name"] == "test-plugin"

    @pytest.mark.asyncio
    async def test_list_plugins_no_hook_manager(self, registry_no_hm):
        result = await registry_no_hm.call("list_plugins", {})
        assert result["success"] is True
        assert result["enabled"] is False
        assert result["plugins"] == []

    @pytest.mark.asyncio
    async def test_list_plugins_enabled_only_when_disabled(self, registry, mock_plugin_loader):
        mock_plugin_loader.config.enabled = False
        result = await registry.call("list_plugins", {"enabled_only": True})
        assert result["success"] is True
        assert result["plugins"] == []


class TestGetPlugin:
    @pytest.mark.asyncio
    async def test_get_plugin(self, registry):
        result = await registry.call("get_plugin", {"name": "test-plugin"})
        assert result["success"] is True
        assert result["name"] == "test-plugin"
        assert result["version"] == "1.0.0"

    @pytest.mark.asyncio
    async def test_get_plugin_not_found(self, registry, mock_plugin_loader):
        mock_plugin_loader.registry.get_plugin.return_value = None
        result = await registry.call("get_plugin", {"name": "nonexistent"})
        assert result["success"] is False
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_get_plugin_no_hook_manager(self, registry_no_hm):
        result = await registry_no_hm.call("get_plugin", {"name": "test-plugin"})
        assert result["success"] is False


class TestReloadPlugin:
    @pytest.mark.asyncio
    async def test_reload_plugin(self, registry):
        result = await registry.call("reload_plugin", {"name": "test-plugin"})
        assert result["success"] is True
        assert result["name"] == "test-plugin"

    @pytest.mark.asyncio
    async def test_reload_plugin_not_found(self, registry, mock_plugin_loader):
        mock_plugin_loader.reload_plugin.return_value = None
        result = await registry.call("reload_plugin", {"name": "nonexistent"})
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_reload_plugin_error(self, registry, mock_plugin_loader):
        mock_plugin_loader.reload_plugin.side_effect = RuntimeError("reload failed")
        result = await registry.call("reload_plugin", {"name": "test-plugin"})
        assert result["success"] is False
        assert "reload failed" in result["error"]


class TestGetPluginConfig:
    @pytest.mark.asyncio
    async def test_get_plugin_config(self, registry):
        result = await registry.call("get_plugin_config", {})
        assert result["success"] is True
        assert result["enabled"] is True
        assert result["auto_discover"] is True
        assert len(result["plugin_dirs"]) == 2


# --- Interaction Tools ---


class TestCallPluginAction:
    @pytest.mark.asyncio
    async def test_call_action(self, registry, mock_plugin_action):
        result = await registry.call(
            "call_plugin_action",
            {"plugin": "test-plugin", "action": "greet", "args": '{"name": "world"}'},
        )
        assert result["success"] is True
        assert result["result"] == {"greeting": "hello"}

    @pytest.mark.asyncio
    async def test_call_action_not_found(self, registry, mock_plugin_loader):
        mock_plugin_loader.registry.get_plugin_action.return_value = None
        result = await registry.call(
            "call_plugin_action",
            {"plugin": "test-plugin", "action": "missing"},
        )
        assert result["success"] is False
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_call_action_invalid_json(self, registry):
        result = await registry.call(
            "call_plugin_action",
            {"plugin": "test-plugin", "action": "greet", "args": "not-json"},
        )
        assert result["success"] is False
        assert "Invalid JSON" in result["error"]

    @pytest.mark.asyncio
    async def test_call_action_validation_failure(self, registry, mock_plugin_action):
        mock_plugin_action.validate_input.return_value = (False, "Missing field: name")
        result = await registry.call(
            "call_plugin_action",
            {"plugin": "test-plugin", "action": "greet", "args": "{}"},
        )
        assert result["success"] is False
        assert "Validation failed" in result["error"]

    @pytest.mark.asyncio
    async def test_call_action_no_hook_manager(self, registry_no_hm):
        result = await registry_no_hm.call(
            "call_plugin_action",
            {"plugin": "test-plugin", "action": "greet"},
        )
        assert result["success"] is False


class TestListPluginActions:
    @pytest.mark.asyncio
    async def test_list_actions(self, registry, mock_plugin, mock_plugin_action):
        mock_plugin._actions = {"greet": mock_plugin_action}
        result = await registry.call("list_plugin_actions", {"plugin": "test-plugin"})
        assert result["success"] is True
        assert len(result["actions"]) == 1
        assert result["actions"][0]["name"] == "greet"

    @pytest.mark.asyncio
    async def test_list_actions_plugin_not_found(self, registry, mock_plugin_loader):
        mock_plugin_loader.registry.get_plugin.return_value = None
        result = await registry.call("list_plugin_actions", {"plugin": "nonexistent"})
        assert result["success"] is False


class TestListPluginConditions:
    @pytest.mark.asyncio
    async def test_list_conditions(self, registry):
        result = await registry.call("list_plugin_conditions", {"plugin": "test-plugin"})
        assert result["success"] is True
        assert "is_admin" in result["conditions"]

    @pytest.mark.asyncio
    async def test_list_conditions_plugin_not_found(self, registry, mock_plugin_loader):
        mock_plugin_loader.registry.get_plugin.return_value = None
        result = await registry.call("list_plugin_conditions", {"plugin": "nonexistent"})
        assert result["success"] is False


# --- Hook Tools ---


class TestListHookHandlers:
    @pytest.mark.asyncio
    async def test_list_handlers_empty(self, registry):
        result = await registry.call("list_hook_handlers", {})
        assert result["success"] is True
        assert result["total_handlers"] == 0

    @pytest.mark.asyncio
    async def test_list_handlers_with_filter(self, registry, mock_plugin_loader, mock_plugin):
        handler = MagicMock()
        handler.plugin = mock_plugin
        handler.method.__name__ = "on_session_start"
        handler.priority = 50
        mock_plugin_loader.registry.get_handlers.return_value = [handler]

        result = await registry.call("list_hook_handlers", {"event_type": "session_start"})
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_list_handlers_invalid_event_type(self, registry):
        result = await registry.call("list_hook_handlers", {"event_type": "invalid_type"})
        assert result["success"] is False
        assert "valid_types" in result

    @pytest.mark.asyncio
    async def test_list_handlers_no_hook_manager(self, registry_no_hm):
        result = await registry_no_hm.call("list_hook_handlers", {})
        assert result["success"] is True
        assert result["handlers"] == {}


class TestTestHookEvent:
    @pytest.mark.asyncio
    async def test_hook_event(self, registry, mock_hook_manager):
        mock_response = MagicMock()
        mock_response.decision = "allow"
        mock_response.reason = None
        mock_response.context = None
        mock_hook_manager.handle.return_value = mock_response

        result = await registry.call(
            "test_hook_event",
            {"event_type": "session_start", "source": "claude"},
        )
        assert result["success"] is True
        assert result["decision"] == "allow"

    @pytest.mark.asyncio
    async def test_hook_event_invalid_type(self, registry):
        result = await registry.call(
            "test_hook_event",
            {"event_type": "bogus_event"},
        )
        assert result["success"] is False
        assert "valid_types" in result

    @pytest.mark.asyncio
    async def test_hook_event_with_data(self, registry, mock_hook_manager):
        mock_response = MagicMock()
        mock_response.decision = "allow"
        mock_response.reason = None
        mock_response.context = None
        mock_hook_manager.handle.return_value = mock_response

        result = await registry.call(
            "test_hook_event",
            {
                "event_type": "session_start",
                "source": "claude",
                "data": '{"extra": "info"}',
            },
        )
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_hook_event_invalid_json_data(self, registry):
        result = await registry.call(
            "test_hook_event",
            {"event_type": "session_start", "data": "not-json"},
        )
        assert result["success"] is False
        assert "Invalid JSON" in result["error"]

    @pytest.mark.asyncio
    async def test_hook_event_no_hook_manager(self, registry_no_hm):
        result = await registry_no_hm.call(
            "test_hook_event",
            {"event_type": "session_start"},
        )
        assert result["success"] is False


# --- Registry Creation ---


class TestRegistryCreation:
    def test_creates_9_tools(self, registry):
        assert len(registry._tools) == 9

    def test_registry_name(self, registry):
        assert registry.name == "gobby-plugins"

    def test_all_tool_names(self, registry):
        expected = {
            "list_plugins",
            "get_plugin",
            "reload_plugin",
            "get_plugin_config",
            "call_plugin_action",
            "list_plugin_actions",
            "list_plugin_conditions",
            "list_hook_handlers",
            "test_hook_event",
        }
        assert set(registry._tools.keys()) == expected
