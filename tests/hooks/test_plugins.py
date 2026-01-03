"""Tests for the Python plugin system."""

import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from gobby.config.app import PluginItemConfig, PluginsConfig
from gobby.hooks.events import HookEvent, HookEventType, HookResponse, SessionSource
from gobby.hooks.plugins import (
    HookPlugin,
    PluginLoader,
    PluginRegistry,
    RegisteredHandler,
    hook_handler,
    run_plugin_handlers,
)


# =============================================================================
# Test Fixtures
# =============================================================================


class SamplePlugin(HookPlugin):
    """Sample plugin for testing."""

    name = "sample-plugin"
    version = "1.0.0"
    description = "A sample plugin for testing"

    def __init__(self):
        super().__init__()
        self.loaded_config = None
        self.unloaded = False

    def on_load(self, config: dict) -> None:
        self.loaded_config = config

    def on_unload(self) -> None:
        self.unloaded = True

    @hook_handler(HookEventType.BEFORE_TOOL, priority=10)
    def check_before_tool(self, event: HookEvent) -> HookResponse | None:
        if "blocked" in str(event.data):
            return HookResponse(decision="deny", reason="Blocked by plugin")
        return None

    @hook_handler(HookEventType.AFTER_TOOL, priority=60)
    def observe_after_tool(self, event: HookEvent, response: HookResponse | None = None) -> None:
        # Post-handler, observe only
        pass


class HighPriorityPlugin(HookPlugin):
    """Plugin with high priority (runs first)."""

    name = "high-priority"

    @hook_handler(HookEventType.BEFORE_TOOL, priority=5)
    def check_first(self, event: HookEvent) -> HookResponse | None:
        return None


class LowPriorityPlugin(HookPlugin):
    """Plugin with low priority (runs later)."""

    name = "low-priority"

    @hook_handler(HookEventType.BEFORE_TOOL, priority=40)
    def check_later(self, event: HookEvent) -> HookResponse | None:
        return None


@pytest.fixture
def sample_event() -> HookEvent:
    """Create a sample hook event."""
    return HookEvent(
        event_type=HookEventType.BEFORE_TOOL,
        session_id="test-session",
        source=SessionSource.CLAUDE,
        timestamp=datetime.now(timezone.utc).isoformat(),
        data={"tool_name": "Edit", "tool_input": {}},
    )


@pytest.fixture
def blocked_event() -> HookEvent:
    """Create an event that should be blocked."""
    return HookEvent(
        event_type=HookEventType.BEFORE_TOOL,
        session_id="test-session",
        source=SessionSource.CLAUDE,
        timestamp=datetime.now(timezone.utc).isoformat(),
        data={"tool_name": "blocked_command"},
    )


@pytest.fixture
def plugins_config() -> PluginsConfig:
    """Create a test plugins config."""
    return PluginsConfig(
        enabled=True,
        plugin_dirs=[],
        auto_discover=False,
        plugins={},
    )


# =============================================================================
# Test Configuration
# =============================================================================


class TestPluginsConfig:
    """Tests for PluginsConfig."""

    def test_default_values(self):
        """Test default configuration values."""
        config = PluginsConfig()
        assert config.enabled is False  # Disabled by default for security
        assert "~/.gobby/plugins" in config.plugin_dirs
        assert ".gobby/plugins" in config.plugin_dirs
        assert config.auto_discover is True
        assert config.plugins == {}

    def test_custom_values(self):
        """Test custom configuration values."""
        config = PluginsConfig(
            enabled=True,
            plugin_dirs=["/custom/path"],
            auto_discover=False,
            plugins={
                "my-plugin": PluginItemConfig(enabled=True, config={"key": "value"})
            },
        )
        assert config.enabled is True
        assert config.plugin_dirs == ["/custom/path"]
        assert config.auto_discover is False
        assert "my-plugin" in config.plugins
        assert config.plugins["my-plugin"].config == {"key": "value"}


class TestPluginItemConfig:
    """Tests for PluginItemConfig."""

    def test_default_values(self):
        """Test default values."""
        config = PluginItemConfig()
        assert config.enabled is True
        assert config.config == {}

    def test_custom_config(self):
        """Test custom config values."""
        config = PluginItemConfig(
            enabled=False,
            config={"setting1": "value1", "setting2": 42},
        )
        assert config.enabled is False
        assert config.config["setting1"] == "value1"
        assert config.config["setting2"] == 42


# =============================================================================
# Test Decorator
# =============================================================================


class TestHookHandlerDecorator:
    """Tests for @hook_handler decorator."""

    def test_decorator_sets_attributes(self):
        """Test that decorator sets metadata on function."""

        @hook_handler(HookEventType.SESSION_START, priority=25)
        def my_handler(event):
            pass

        assert hasattr(my_handler, "_hook_event_type")
        assert my_handler._hook_event_type == HookEventType.SESSION_START
        assert my_handler._hook_priority == 25

    def test_decorator_preserves_function(self):
        """Test that decorator preserves the original function."""

        @hook_handler(HookEventType.BEFORE_TOOL)
        def my_handler(event):
            return "result"

        assert my_handler(None) == "result"

    def test_default_priority(self):
        """Test that default priority is 50."""

        @hook_handler(HookEventType.AFTER_TOOL)
        def my_handler(event):
            pass

        assert my_handler._hook_priority == 50


# =============================================================================
# Test HookPlugin Base Class
# =============================================================================


class TestHookPlugin:
    """Tests for HookPlugin base class."""

    def test_plugin_instantiation(self):
        """Test that plugins can be instantiated."""
        plugin = SamplePlugin()
        assert plugin.name == "sample-plugin"
        assert plugin.version == "1.0.0"
        assert plugin.description == "A sample plugin for testing"

    def test_on_load_called(self):
        """Test that on_load receives config."""
        plugin = SamplePlugin()
        test_config = {"key": "value"}
        plugin.on_load(test_config)
        assert plugin.loaded_config == test_config

    def test_on_unload_called(self):
        """Test that on_unload is called."""
        plugin = SamplePlugin()
        assert plugin.unloaded is False
        plugin.on_unload()
        assert plugin.unloaded is True

    def test_register_action(self):
        """Test action registration."""
        plugin = SamplePlugin()

        async def my_action(context, **kwargs):
            return {"done": True}

        plugin.register_action("my_action", my_action)
        assert "my_action" in plugin._actions
        assert plugin._actions["my_action"] is my_action

    def test_register_condition(self):
        """Test condition registration."""
        plugin = SamplePlugin()

        def my_condition():
            return True

        plugin.register_condition("my_condition", my_condition)
        assert "my_condition" in plugin._conditions
        assert plugin._conditions["my_condition"] is my_condition


# =============================================================================
# Test PluginRegistry
# =============================================================================


class TestPluginRegistry:
    """Tests for PluginRegistry."""

    def test_register_plugin(self):
        """Test plugin registration."""
        registry = PluginRegistry()
        plugin = SamplePlugin()
        plugin.on_load({})

        registry.register_plugin(plugin)

        assert "sample-plugin" in registry._plugins
        assert registry.get_plugin("sample-plugin") is plugin

    def test_register_duplicate_raises(self):
        """Test that registering duplicate plugin raises error."""
        registry = PluginRegistry()
        plugin = SamplePlugin()
        plugin.on_load({})

        registry.register_plugin(plugin)

        with pytest.raises(ValueError, match="already registered"):
            registry.register_plugin(plugin)

    def test_unregister_plugin(self):
        """Test plugin unregistration."""
        registry = PluginRegistry()
        plugin = SamplePlugin()
        plugin.on_load({})
        registry.register_plugin(plugin)

        registry.unregister_plugin("sample-plugin")

        assert "sample-plugin" not in registry._plugins
        assert registry.get_plugin("sample-plugin") is None

    def test_handlers_registered(self):
        """Test that handlers are registered from plugin."""
        registry = PluginRegistry()
        plugin = SamplePlugin()
        plugin.on_load({})
        registry.register_plugin(plugin)

        handlers = registry.get_handlers(HookEventType.BEFORE_TOOL)
        assert len(handlers) == 1
        assert handlers[0].priority == 10

    def test_handlers_sorted_by_priority(self):
        """Test that handlers are sorted by priority."""
        registry = PluginRegistry()

        high = HighPriorityPlugin()
        low = LowPriorityPlugin()

        registry.register_plugin(high)
        registry.register_plugin(low)

        handlers = registry.get_handlers(HookEventType.BEFORE_TOOL)
        assert len(handlers) == 2
        assert handlers[0].priority == 5  # high priority runs first
        assert handlers[1].priority == 40

    def test_get_pre_handlers(self):
        """Test getting only pre-handlers (priority < 50)."""
        registry = PluginRegistry()
        plugin = SamplePlugin()
        plugin.on_load({})
        registry.register_plugin(plugin)

        pre_handlers = registry.get_handlers(HookEventType.BEFORE_TOOL, pre_only=True)
        post_handlers = registry.get_handlers(HookEventType.AFTER_TOOL, post_only=True)

        assert len(pre_handlers) == 1
        assert pre_handlers[0].priority == 10
        assert len(post_handlers) == 1
        assert post_handlers[0].priority == 60

    def test_list_plugins(self):
        """Test listing all plugins."""
        registry = PluginRegistry()
        plugin = SamplePlugin()
        plugin.on_load({})
        registry.register_plugin(plugin)

        plugins = registry.list_plugins()
        assert len(plugins) == 1
        assert plugins[0]["name"] == "sample-plugin"
        assert plugins[0]["version"] == "1.0.0"
        assert len(plugins[0]["handlers"]) == 2


# =============================================================================
# Test PluginLoader
# =============================================================================


class TestPluginLoader:
    """Tests for PluginLoader."""

    def test_discover_empty_directory(self, plugins_config):
        """Test discovery with no plugins."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugins_config.plugin_dirs = [tmpdir]
            loader = PluginLoader(plugins_config)

            discovered = loader.discover_plugins()
            assert discovered == []

    def test_discover_nonexistent_directory(self, plugins_config):
        """Test discovery with nonexistent directory."""
        plugins_config.plugin_dirs = ["/nonexistent/path"]
        loader = PluginLoader(plugins_config)

        discovered = loader.discover_plugins()
        assert discovered == []

    def test_load_plugin(self, plugins_config):
        """Test loading a plugin directly."""
        loader = PluginLoader(plugins_config)

        plugin = loader.load_plugin(SamplePlugin, {"test": "config"})

        assert plugin.name == "sample-plugin"
        assert plugin.loaded_config == {"test": "config"}
        assert "sample-plugin" in loader.registry._plugins

    def test_load_plugin_disabled(self, plugins_config):
        """Test loading disabled plugin raises error."""
        plugins_config.plugins["sample-plugin"] = PluginItemConfig(enabled=False)
        loader = PluginLoader(plugins_config)

        with pytest.raises(ValueError, match="disabled"):
            loader.load_plugin(SamplePlugin)

    def test_unload_plugin(self, plugins_config):
        """Test unloading a plugin."""
        loader = PluginLoader(plugins_config)
        plugin = loader.load_plugin(SamplePlugin)

        loader.unload_plugin("sample-plugin")

        assert plugin.unloaded is True
        assert loader.registry.get_plugin("sample-plugin") is None

    def test_load_all_disabled(self):
        """Test load_all when plugins disabled."""
        config = PluginsConfig(enabled=False)
        loader = PluginLoader(config)

        loaded = loader.load_all()
        assert loaded == []


# =============================================================================
# Test Handler Execution
# =============================================================================


class TestRunPluginHandlers:
    """Tests for run_plugin_handlers function."""

    def test_pre_handler_allows(self, sample_event):
        """Test pre-handler that allows event."""
        registry = PluginRegistry()
        plugin = SamplePlugin()
        plugin.on_load({})
        registry.register_plugin(plugin)

        result = run_plugin_handlers(registry, sample_event, pre=True)
        assert result is None  # None means allow

    def test_pre_handler_blocks(self, blocked_event):
        """Test pre-handler that blocks event."""
        registry = PluginRegistry()
        plugin = SamplePlugin()
        plugin.on_load({})
        registry.register_plugin(plugin)

        result = run_plugin_handlers(registry, blocked_event, pre=True)
        assert result is not None
        assert result.decision == "deny"
        assert "Blocked by plugin" in result.reason

    def test_post_handler_runs(self, sample_event):
        """Test post-handler execution."""
        registry = PluginRegistry()
        plugin = SamplePlugin()
        plugin.on_load({})
        registry.register_plugin(plugin)

        # Create an after_tool event
        after_event = HookEvent(
            event_type=HookEventType.AFTER_TOOL,
            session_id="test-session",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(timezone.utc).isoformat(),
            data={},
        )
        core_response = HookResponse(decision="allow")

        # Post-handlers always return None
        result = run_plugin_handlers(
            registry, after_event, pre=False, core_response=core_response
        )
        assert result is None

    def test_handler_error_continues(self, sample_event):
        """Test that handler errors don't stop processing."""

        class ErrorPlugin(HookPlugin):
            name = "error-plugin"

            @hook_handler(HookEventType.BEFORE_TOOL, priority=5)
            def will_error(self, event):
                raise RuntimeError("Handler error")

        registry = PluginRegistry()
        error_plugin = ErrorPlugin()
        registry.register_plugin(error_plugin)

        sample_plugin = SamplePlugin()
        sample_plugin.on_load({})
        registry.register_plugin(sample_plugin)

        # Should continue despite error in first handler
        result = run_plugin_handlers(registry, sample_event, pre=True)
        assert result is None  # Second handler allowed


# =============================================================================
# Test Workflow Integration
# =============================================================================


class TestWorkflowIntegration:
    """Tests for workflow action/condition integration."""

    def test_action_executor_registers_plugin_actions(self):
        """Test that ActionExecutor registers plugin actions."""
        from gobby.workflows.actions import ActionExecutor

        registry = PluginRegistry()
        plugin = SamplePlugin()
        plugin.on_load({})

        async def my_action(context, **kwargs):
            return {"done": True}

        plugin.register_action("test_action", my_action)
        registry.register_plugin(plugin)

        executor = ActionExecutor(
            db=None, session_manager=None, template_engine=None
        )
        executor.register_plugin_actions(registry)

        assert "plugin:sample-plugin:test_action" in executor._handlers

    def test_condition_evaluator_registers_plugin_conditions(self):
        """Test that ConditionEvaluator registers plugin conditions."""
        from gobby.workflows.evaluator import ConditionEvaluator

        registry = PluginRegistry()
        plugin = SamplePlugin()
        plugin.on_load({})

        def my_condition():
            return True

        plugin.register_condition("is_ready", my_condition)
        registry.register_plugin(plugin)

        evaluator = ConditionEvaluator()
        evaluator.register_plugin_conditions(registry)

        assert "plugin_sample_plugin_is_ready" in evaluator._plugin_conditions

    def test_condition_can_be_evaluated(self):
        """Test that registered conditions can be evaluated."""
        from gobby.workflows.evaluator import ConditionEvaluator

        registry = PluginRegistry()
        plugin = SamplePlugin()
        plugin.on_load({})

        call_count = 0

        def my_condition():
            nonlocal call_count
            call_count += 1
            return True

        plugin.register_condition("check", my_condition)
        registry.register_plugin(plugin)

        evaluator = ConditionEvaluator()
        evaluator.register_plugin_conditions(registry)

        result = evaluator.evaluate("plugin_sample_plugin_check()", {})
        assert result is True
        assert call_count == 1
