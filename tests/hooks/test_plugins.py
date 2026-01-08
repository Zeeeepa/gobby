"""Tests for the Python plugin system."""

import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from gobby.config.app import PluginItemConfig, PluginsConfig
from gobby.hooks.events import HookEvent, HookEventType, HookResponse, SessionSource
from gobby.hooks.plugins import (
    HookPlugin,
    PluginLoader,
    PluginRegistry,
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
        timestamp=datetime.now(UTC).isoformat(),
        data={"tool_name": "Edit", "tool_input": {}},
    )


@pytest.fixture
def blocked_event() -> HookEvent:
    """Create an event that should be blocked."""
    return HookEvent(
        event_type=HookEventType.BEFORE_TOOL,
        session_id="test-session",
        source=SessionSource.CLAUDE,
        timestamp=datetime.now(UTC).isoformat(),
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
            plugins={"my-plugin": PluginItemConfig(enabled=True, config={"key": "value"})},
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
        # Actions are now stored as PluginAction objects
        assert plugin._actions["my_action"].handler is my_action
        assert plugin._actions["my_action"].name == "my_action"
        assert plugin._actions["my_action"].schema == {}  # Empty schema by default

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
            timestamp=datetime.now(UTC).isoformat(),
            data={},
        )
        core_response = HookResponse(decision="allow")

        # Post-handlers always return None
        result = run_plugin_handlers(registry, after_event, pre=False, core_response=core_response)
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

        executor = ActionExecutor(db=None, session_manager=None, template_engine=None)
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


# =============================================================================
# Test Plugin Action Execution (Extended)
# =============================================================================


class PluginWithActions(HookPlugin):
    """Plugin with workflow actions for testing."""

    name = "action-plugin"
    version = "1.0.0"
    description = "Plugin with workflow actions"

    def on_load(self, config: dict) -> None:
        self.config = config

        # Register sync action
        self.register_action("sync_action", self._sync_action)
        # Register async action
        self.register_action("async_action", self._async_action)
        # Register action that returns data
        self.register_action("data_action", self._data_action)
        # Register action that accesses context
        self.register_action("context_action", self._context_action)
        # Register action that raises error
        self.register_action("error_action", self._error_action)

    async def _sync_action(self, context, **kwargs):
        """Simple action that returns success."""
        return {"status": "ok", "kwargs": kwargs}

    async def _async_action(self, context, **kwargs):
        """Async action with await."""
        import asyncio

        await asyncio.sleep(0.01)
        return {"async": True, "value": kwargs.get("value", "default")}

    async def _data_action(self, context, **kwargs):
        """Action that returns complex data."""
        return {
            "items": [1, 2, 3],
            "nested": {"key": "value"},
            "config_value": self.config.get("test_key"),
        }

    async def _context_action(self, context, **kwargs):
        """Action that accesses ActionContext fields."""
        return {
            "session_id": context.session_id,
            "has_state": context.state is not None,
            "has_db": context.db is not None,
        }

    async def _error_action(self, context, **kwargs):
        """Action that raises an error."""
        raise ValueError("Intentional error for testing")


class AnotherPlugin(HookPlugin):
    """Second plugin for namespace testing."""

    name = "another-plugin"

    def on_load(self, config: dict) -> None:
        self.register_action("my_action", self._my_action)

    async def _my_action(self, context, **kwargs):
        return {"from": "another-plugin"}


class TestPluginActionExecution:
    """Tests for plugin action execution through ActionExecutor."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database."""
        return MagicMock()

    @pytest.fixture
    def mock_session_manager(self):
        """Create a mock session manager."""
        manager = MagicMock()
        manager.get.return_value = MagicMock(project_id="test-project")
        return manager

    @pytest.fixture
    def mock_template_engine(self):
        """Create a mock template engine."""
        return MagicMock()

    @pytest.fixture
    def executor_with_plugins(self, mock_db, mock_session_manager, mock_template_engine):
        """Create ActionExecutor with registered plugin actions."""
        from gobby.workflows.actions import ActionExecutor

        registry = PluginRegistry()

        # Load plugin with actions
        plugin = PluginWithActions()
        plugin.on_load({"test_key": "test_value"})
        registry.register_plugin(plugin)

        # Load second plugin
        another = AnotherPlugin()
        another.on_load({})
        registry.register_plugin(another)

        executor = ActionExecutor(
            db=mock_db,
            session_manager=mock_session_manager,
            template_engine=mock_template_engine,
        )
        executor.register_plugin_actions(registry)

        return executor

    @pytest.fixture
    def workflow_state(self):
        """Create a WorkflowState with all required fields."""
        from gobby.workflows.definitions import WorkflowState

        return WorkflowState(
            session_id="test-session",
            workflow_name="test-workflow",
            step="test-step",
        )

    @pytest.mark.asyncio
    async def test_execute_plugin_action_with_kwargs(self, executor_with_plugins, workflow_state):
        """Test executing plugin action with keyword arguments."""
        from gobby.workflows.actions import ActionContext

        context = ActionContext(
            session_id="test-session",
            state=workflow_state,
            db=MagicMock(),
            session_manager=MagicMock(),
            template_engine=MagicMock(),
        )

        result = await executor_with_plugins.execute(
            "plugin:action-plugin:sync_action",
            context,
            foo="bar",
            num=42,
        )

        assert result is not None
        assert result["status"] == "ok"
        assert result["kwargs"]["foo"] == "bar"
        assert result["kwargs"]["num"] == 42

    @pytest.mark.asyncio
    async def test_execute_async_plugin_action(self, executor_with_plugins, workflow_state):
        """Test executing async plugin action."""
        from gobby.workflows.actions import ActionContext

        context = ActionContext(
            session_id="test-session",
            state=workflow_state,
            db=MagicMock(),
            session_manager=MagicMock(),
            template_engine=MagicMock(),
        )

        result = await executor_with_plugins.execute(
            "plugin:action-plugin:async_action",
            context,
            value="async_test",
        )

        assert result is not None
        assert result["async"] is True
        assert result["value"] == "async_test"

    @pytest.mark.asyncio
    async def test_plugin_action_returns_complex_data(self, executor_with_plugins, workflow_state):
        """Test plugin action returning nested data structures."""
        from gobby.workflows.actions import ActionContext

        context = ActionContext(
            session_id="test-session",
            state=workflow_state,
            db=MagicMock(),
            session_manager=MagicMock(),
            template_engine=MagicMock(),
        )

        result = await executor_with_plugins.execute(
            "plugin:action-plugin:data_action",
            context,
        )

        assert result is not None
        assert result["items"] == [1, 2, 3]
        assert result["nested"]["key"] == "value"
        assert result["config_value"] == "test_value"

    @pytest.mark.asyncio
    async def test_plugin_action_accesses_context(self, executor_with_plugins):
        """Test plugin action can access ActionContext fields."""
        from gobby.workflows.actions import ActionContext
        from gobby.workflows.definitions import WorkflowState

        state = WorkflowState(
            session_id="ctx-session-123",
            workflow_name="test-workflow",
            step="test-step",
        )
        context = ActionContext(
            session_id="ctx-session-123",
            state=state,
            db=MagicMock(),
            session_manager=MagicMock(),
            template_engine=MagicMock(),
        )

        result = await executor_with_plugins.execute(
            "plugin:action-plugin:context_action",
            context,
        )

        assert result is not None
        assert result["session_id"] == "ctx-session-123"
        assert result["has_state"] is True
        assert result["has_db"] is True

    @pytest.mark.asyncio
    async def test_plugin_action_error_handling(self, executor_with_plugins, workflow_state):
        """Test that errors in plugin actions are caught and returned."""
        from gobby.workflows.actions import ActionContext

        context = ActionContext(
            session_id="test-session",
            state=workflow_state,
            db=MagicMock(),
            session_manager=MagicMock(),
            template_engine=MagicMock(),
        )

        result = await executor_with_plugins.execute(
            "plugin:action-plugin:error_action",
            context,
        )

        assert result is not None
        assert "error" in result
        assert "Intentional error" in result["error"]

    @pytest.mark.asyncio
    async def test_multiple_plugins_namespace_isolation(
        self, executor_with_plugins, workflow_state
    ):
        """Test that actions from different plugins are properly namespaced."""
        from gobby.workflows.actions import ActionContext

        context = ActionContext(
            session_id="test-session",
            state=workflow_state,
            db=MagicMock(),
            session_manager=MagicMock(),
            template_engine=MagicMock(),
        )

        # Both plugins have registered actions
        assert "plugin:action-plugin:sync_action" in executor_with_plugins._handlers
        assert "plugin:another-plugin:my_action" in executor_with_plugins._handlers

        # Execute action from second plugin
        result = await executor_with_plugins.execute(
            "plugin:another-plugin:my_action",
            context,
        )

        assert result is not None
        assert result["from"] == "another-plugin"

    @pytest.mark.asyncio
    async def test_unknown_plugin_action_returns_none(self, executor_with_plugins, workflow_state):
        """Test that unknown plugin action returns None."""
        from gobby.workflows.actions import ActionContext

        context = ActionContext(
            session_id="test-session",
            state=workflow_state,
            db=MagicMock(),
            session_manager=MagicMock(),
            template_engine=MagicMock(),
        )

        result = await executor_with_plugins.execute(
            "plugin:nonexistent:action",
            context,
        )

        assert result is None

    def test_register_plugin_actions_with_none_registry(self):
        """Test that register_plugin_actions handles None registry gracefully."""
        from gobby.workflows.actions import ActionExecutor

        executor = ActionExecutor(
            db=MagicMock(),
            session_manager=MagicMock(),
            template_engine=MagicMock(),
        )

        # Should not raise
        executor.register_plugin_actions(None)

        # Should not have any plugin actions
        plugin_actions = [k for k in executor._handlers.keys() if k.startswith("plugin:")]
        assert len(plugin_actions) == 0

    def test_register_plugin_actions_empty_registry(self):
        """Test registering from empty registry."""
        from gobby.workflows.actions import ActionExecutor

        registry = PluginRegistry()
        executor = ActionExecutor(
            db=MagicMock(),
            session_manager=MagicMock(),
            template_engine=MagicMock(),
        )

        executor.register_plugin_actions(registry)

        plugin_actions = [k for k in executor._handlers.keys() if k.startswith("plugin:")]
        assert len(plugin_actions) == 0

    def test_plugin_actions_listed_in_plugin_info(self):
        """Test that registered actions appear in plugin listing."""
        registry = PluginRegistry()
        plugin = PluginWithActions()
        plugin.on_load({})
        registry.register_plugin(plugin)

        plugins = registry.list_plugins()
        assert len(plugins) == 1

        plugin_info = plugins[0]
        # Actions are now listed as dicts with name/has_schema/schema
        action_names = [a["name"] for a in plugin_info["actions"]]
        assert "sync_action" in action_names
        assert "async_action" in action_names
        assert "data_action" in action_names
        assert "context_action" in action_names
        assert "error_action" in action_names
        # Verify structure
        for action in plugin_info["actions"]:
            assert "name" in action
            assert "has_schema" in action
            assert action["has_schema"] is False  # No schemas in this plugin


class TestRegisterWorkflowAction:
    """Tests for register_workflow_action with schema validation."""

    def test_register_workflow_action_with_schema(self):
        """Test registering action with JSON schema."""
        plugin = SamplePlugin()

        async def my_action(context, **kwargs):
            return {"message": kwargs.get("message")}

        schema = {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "count": {"type": "integer"},
            },
            "required": ["message"],
        }

        plugin.register_workflow_action("send_message", schema, my_action)

        assert "send_message" in plugin._actions
        action = plugin._actions["send_message"]
        assert action.handler is my_action
        assert action.schema == schema
        assert action.name == "send_message"
        assert action.plugin_name == "sample-plugin"

    def test_register_workflow_action_duplicate_raises(self):
        """Test that duplicate action registration raises error."""
        plugin = SamplePlugin()

        async def action1(context, **kwargs):
            return {}

        async def action2(context, **kwargs):
            return {}

        plugin.register_workflow_action("my_action", {}, action1)

        with pytest.raises(ValueError, match="already registered"):
            plugin.register_workflow_action("my_action", {}, action2)

    def test_validate_input_success(self):
        """Test successful schema validation."""
        plugin = SamplePlugin()

        async def my_action(context, **kwargs):
            return {}

        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "count": {"type": "integer"},
            },
            "required": ["name"],
        }

        plugin.register_workflow_action("test", schema, my_action)
        action = plugin._actions["test"]

        is_valid, error = action.validate_input({"name": "test", "count": 5})
        assert is_valid is True
        assert error is None

    def test_validate_input_missing_required(self):
        """Test validation fails for missing required field."""
        plugin = SamplePlugin()

        async def my_action(context, **kwargs):
            return {}

        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
            },
            "required": ["name"],
        }

        plugin.register_workflow_action("test", schema, my_action)
        action = plugin._actions["test"]

        is_valid, error = action.validate_input({})
        assert is_valid is False
        assert "Missing required field: name" in error

    def test_validate_input_wrong_type(self):
        """Test validation fails for wrong type."""
        plugin = SamplePlugin()

        async def my_action(context, **kwargs):
            return {}

        schema = {
            "type": "object",
            "properties": {
                "count": {"type": "integer"},
            },
        }

        plugin.register_workflow_action("test", schema, my_action)
        action = plugin._actions["test"]

        is_valid, error = action.validate_input({"count": "not_an_int"})
        assert is_valid is False
        assert "invalid type" in error

    def test_validate_input_no_schema(self):
        """Test validation passes when no schema defined."""
        plugin = SamplePlugin()

        async def my_action(context, **kwargs):
            return {}

        plugin.register_workflow_action("test", {}, my_action)
        action = plugin._actions["test"]

        is_valid, error = action.validate_input({"anything": "goes"})
        assert is_valid is True
        assert error is None

    def test_validate_input_optional_field_not_provided(self):
        """Test validation skips optional fields when not provided."""
        plugin = SamplePlugin()

        async def my_action(context, **kwargs):
            return {}

        schema = {
            "type": "object",
            "properties": {
                "required_field": {"type": "string"},
                "optional_field": {"type": "integer"},  # Not required
            },
            "required": ["required_field"],
        }

        plugin.register_workflow_action("test_optional", schema, my_action)
        action = plugin._actions["test_optional"]

        # Only provide required field, optional field not provided
        is_valid, error = action.validate_input({"required_field": "hello"})
        assert is_valid is True
        assert error is None

    def test_get_action(self):
        """Test get_action retrieves registered action."""
        plugin = SamplePlugin()

        async def my_action(context, **kwargs):
            return {}

        plugin.register_workflow_action("my_action", {}, my_action)

        action = plugin.get_action("my_action")
        assert action is not None
        assert action.name == "my_action"

        missing = plugin.get_action("nonexistent")
        assert missing is None

    def test_list_plugins_shows_schema_info(self):
        """Test that list_plugins shows schema information."""
        registry = PluginRegistry()
        plugin = SamplePlugin()

        async def action1(context, **kwargs):
            return {}

        async def action2(context, **kwargs):
            return {}

        schema = {"type": "object", "properties": {"x": {"type": "string"}}}
        plugin.register_workflow_action("with_schema", schema, action1)
        plugin.register_action("without_schema", action2)
        registry.register_plugin(plugin)

        plugins = registry.list_plugins()
        actions = {a["name"]: a for a in plugins[0]["actions"]}

        assert actions["with_schema"]["has_schema"] is True
        assert actions["with_schema"]["schema"] == schema
        assert actions["without_schema"]["has_schema"] is False
        assert actions["without_schema"]["schema"] is None


class TestSchemaValidationInActionExecutor:
    """Tests for schema validation when executing plugin actions."""

    @pytest.fixture
    def registry_with_schema_actions(self):
        """Create registry with plugin that has schema-validated actions."""
        from gobby.hooks.plugins import HookPlugin, PluginRegistry

        class SchemaPlugin(HookPlugin):
            name = "schema-plugin"

            def on_load(self, config: dict) -> None:
                schema = {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "count": {"type": "integer"},
                    },
                    "required": ["name"],
                }
                self.register_workflow_action("validated_action", schema, self._action)

            async def _action(self, context, **kwargs):
                return {"received": kwargs}

        registry = PluginRegistry()
        plugin = SchemaPlugin()
        plugin.on_load({})
        registry.register_plugin(plugin)
        return registry

    @pytest.mark.asyncio
    async def test_valid_input_passes(self, registry_with_schema_actions):
        """Test that valid input passes schema validation."""
        from unittest.mock import MagicMock

        from gobby.workflows.actions import ActionContext, ActionExecutor
        from gobby.workflows.definitions import WorkflowState

        executor = ActionExecutor(
            db=MagicMock(),
            session_manager=MagicMock(),
            template_engine=MagicMock(),
        )
        executor.register_plugin_actions(registry_with_schema_actions)

        state = WorkflowState(
            session_id="test",
            workflow_name="test",
            step="test",
        )
        context = ActionContext(
            session_id="test",
            state=state,
            db=MagicMock(),
            session_manager=MagicMock(),
            template_engine=MagicMock(),
        )

        result = await executor.execute(
            "plugin:schema-plugin:validated_action",
            context,
            name="test",
            count=42,
        )

        assert result is not None
        assert "error" not in result
        assert result["received"]["name"] == "test"
        assert result["received"]["count"] == 42

    @pytest.mark.asyncio
    async def test_invalid_input_returns_error(self, registry_with_schema_actions):
        """Test that invalid input returns validation error."""
        from unittest.mock import MagicMock

        from gobby.workflows.actions import ActionContext, ActionExecutor
        from gobby.workflows.definitions import WorkflowState

        executor = ActionExecutor(
            db=MagicMock(),
            session_manager=MagicMock(),
            template_engine=MagicMock(),
        )
        executor.register_plugin_actions(registry_with_schema_actions)

        state = WorkflowState(
            session_id="test",
            workflow_name="test",
            step="test",
        )
        context = ActionContext(
            session_id="test",
            state=state,
            db=MagicMock(),
            session_manager=MagicMock(),
            template_engine=MagicMock(),
        )

        # Missing required 'name' field
        result = await executor.execute(
            "plugin:schema-plugin:validated_action",
            context,
            count=42,
        )

        assert result is not None
        assert "error" in result
        assert "Schema validation failed" in result["error"]
        assert "Missing required field: name" in result["error"]

    @pytest.mark.asyncio
    async def test_wrong_type_returns_error(self, registry_with_schema_actions):
        """Test that wrong type returns validation error."""
        from unittest.mock import MagicMock

        from gobby.workflows.actions import ActionContext, ActionExecutor
        from gobby.workflows.definitions import WorkflowState

        executor = ActionExecutor(
            db=MagicMock(),
            session_manager=MagicMock(),
            template_engine=MagicMock(),
        )
        executor.register_plugin_actions(registry_with_schema_actions)

        state = WorkflowState(
            session_id="test",
            workflow_name="test",
            step="test",
        )
        context = ActionContext(
            session_id="test",
            state=state,
            db=MagicMock(),
            session_manager=MagicMock(),
            template_engine=MagicMock(),
        )

        # 'count' should be integer, not string
        result = await executor.execute(
            "plugin:schema-plugin:validated_action",
            context,
            name="test",
            count="not_a_number",
        )

        assert result is not None
        assert "error" in result
        assert "Schema validation failed" in result["error"]


class TestPluginActionRegistrationOnLoad:
    """Tests for plugin action registration during on_load lifecycle."""

    def test_actions_registered_during_on_load(self):
        """Test that actions are available after on_load."""
        plugin = PluginWithActions()

        # Before on_load, no actions
        assert len(plugin._actions) == 0

        plugin.on_load({})

        # After on_load, actions registered
        assert len(plugin._actions) == 5
        assert "sync_action" in plugin._actions
        assert "async_action" in plugin._actions

    def test_actions_cleared_on_new_instance(self):
        """Test that each plugin instance has separate actions dict."""
        plugin1 = PluginWithActions()
        plugin1.on_load({})

        plugin2 = PluginWithActions()

        # plugin2 hasn't called on_load yet
        assert len(plugin2._actions) == 0

        # plugin1 still has actions
        assert len(plugin1._actions) == 5

    def test_action_receives_plugin_config(self):
        """Test that action can access plugin config set during on_load."""
        plugin = PluginWithActions()
        plugin.on_load({"custom_key": "custom_value"})

        # The plugin stores config in on_load
        assert plugin.config["custom_key"] == "custom_value"

    def test_unload_preserves_action_registration(self):
        """Test that on_unload doesn't affect action dict (registry handles cleanup)."""
        plugin = PluginWithActions()
        plugin.on_load({})

        assert len(plugin._actions) == 5

        plugin.on_unload()

        # Actions still in plugin's dict (registry cleanup is separate)
        assert len(plugin._actions) == 5


# =============================================================================
# Test _check_type Helper Function
# =============================================================================


class TestCheckTypeFunction:
    """Tests for _check_type helper function."""

    def test_boolean_rejected_for_integer(self):
        """Test that boolean values are rejected for integer type."""
        from gobby.hooks.plugins import _check_type

        # Boolean should NOT be accepted as integer (even though bool is subclass of int)
        assert _check_type(True, "integer") is False
        assert _check_type(False, "integer") is False

        # Actual integers should work
        assert _check_type(42, "integer") is True
        assert _check_type(-5, "integer") is True

    def test_boolean_rejected_for_number(self):
        """Test that boolean values are rejected for number type."""
        from gobby.hooks.plugins import _check_type

        assert _check_type(True, "number") is False
        assert _check_type(False, "number") is False

        # Actual numbers should work
        assert _check_type(3.14, "number") is True
        assert _check_type(42, "number") is True

    def test_unknown_type_returns_true(self):
        """Test that unknown types return True (skip validation)."""
        from gobby.hooks.plugins import _check_type

        assert _check_type("anything", "unknown_type") is True
        assert _check_type(123, "custom") is True
        assert _check_type(None, "nonexistent") is True

    def test_null_type(self):
        """Test null type checking."""
        from gobby.hooks.plugins import _check_type

        assert _check_type(None, "null") is True
        assert _check_type("not none", "null") is False

    def test_array_type(self):
        """Test array type checking."""
        from gobby.hooks.plugins import _check_type

        assert _check_type([1, 2, 3], "array") is True
        assert _check_type([], "array") is True
        assert _check_type("not array", "array") is False

    def test_object_type(self):
        """Test object type checking."""
        from gobby.hooks.plugins import _check_type

        assert _check_type({"key": "value"}, "object") is True
        assert _check_type({}, "object") is True
        assert _check_type([1, 2], "object") is False

    def test_boolean_type(self):
        """Test boolean type checking."""
        from gobby.hooks.plugins import _check_type

        assert _check_type(True, "boolean") is True
        assert _check_type(False, "boolean") is True
        assert _check_type(1, "boolean") is False
        assert _check_type("true", "boolean") is False

    def test_string_type(self):
        """Test string type checking."""
        from gobby.hooks.plugins import _check_type

        assert _check_type("hello", "string") is True
        assert _check_type("", "string") is True
        assert _check_type(123, "string") is False


# =============================================================================
# Test PluginRegistry Additional Coverage
# =============================================================================


class TestPluginRegistryAdditional:
    """Additional tests for PluginRegistry edge cases."""

    def test_unregister_nonexistent_plugin(self):
        """Test unregistering a plugin that doesn't exist logs warning."""
        registry = PluginRegistry()

        # Should not raise, just log warning
        registry.unregister_plugin("nonexistent-plugin")

        # Verify plugin is not in registry
        assert registry.get_plugin("nonexistent-plugin") is None

    def test_get_plugin_action_success(self):
        """Test get_plugin_action returns action when found."""
        registry = PluginRegistry()
        plugin = SamplePlugin()
        plugin.on_load({})

        async def my_action(context, **kwargs):
            return {}

        plugin.register_action("test_action", my_action)
        registry.register_plugin(plugin)

        action = registry.get_plugin_action("sample-plugin", "test_action")
        assert action is not None
        assert action.name == "test_action"

    def test_get_plugin_action_plugin_not_found(self):
        """Test get_plugin_action returns None when plugin not found."""
        registry = PluginRegistry()

        action = registry.get_plugin_action("nonexistent", "some_action")
        assert action is None

    def test_get_plugin_action_action_not_found(self):
        """Test get_plugin_action returns None when action not found."""
        registry = PluginRegistry()
        plugin = SamplePlugin()
        plugin.on_load({})
        registry.register_plugin(plugin)

        action = registry.get_plugin_action("sample-plugin", "nonexistent_action")
        assert action is None

    def test_unregister_removes_handlers_and_cleans_empty_lists(self):
        """Test that unregistering plugin removes handlers and cleans up empty lists."""
        registry = PluginRegistry()

        # Register a plugin with handlers
        plugin = SamplePlugin()
        plugin.on_load({})
        registry.register_plugin(plugin)

        # Verify handlers exist
        assert len(registry.get_handlers(HookEventType.BEFORE_TOOL)) == 1
        assert len(registry.get_handlers(HookEventType.AFTER_TOOL)) == 1

        # Unregister
        registry.unregister_plugin("sample-plugin")

        # Handlers should be gone
        assert len(registry.get_handlers(HookEventType.BEFORE_TOOL)) == 0
        assert len(registry.get_handlers(HookEventType.AFTER_TOOL)) == 0


# =============================================================================
# Test PluginLoader Discovery and Loading
# =============================================================================


class TestPluginLoaderDiscovery:
    """Tests for PluginLoader discovery functionality."""

    def test_discover_path_is_file_not_directory(self, plugins_config):
        """Test discovery when path is a file instead of directory."""
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
            f.write(b"# test file")
            file_path = f.name

        try:
            plugins_config.plugin_dirs = [file_path]
            loader = PluginLoader(plugins_config)

            discovered = loader.discover_plugins()
            assert discovered == []
        finally:
            Path(file_path).unlink()

    def test_discover_skips_underscore_files(self, plugins_config):
        """Test that files starting with underscore are skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create __init__.py
            (Path(tmpdir) / "__init__.py").write_text("# init file")
            # Create _private.py
            (Path(tmpdir) / "_private.py").write_text("# private file")

            plugins_config.plugin_dirs = [tmpdir]
            loader = PluginLoader(plugins_config)

            discovered = loader.discover_plugins()
            assert discovered == []

    def test_discover_handles_module_load_error(self, plugins_config):
        """Test discovery continues when module fails to load."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a plugin file with syntax error
            bad_plugin = Path(tmpdir) / "bad_plugin.py"
            bad_plugin.write_text("def broken(:\n    pass")  # Syntax error

            plugins_config.plugin_dirs = [tmpdir]
            loader = PluginLoader(plugins_config)

            # Should not raise, returns empty list
            discovered = loader.discover_plugins()
            assert discovered == []

    def test_discover_and_load_real_plugin(self, plugins_config):
        """Test discovering and loading a real plugin from file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a valid plugin file
            plugin_file = Path(tmpdir) / "my_plugin.py"
            plugin_file.write_text("""
from gobby.hooks.plugins import HookPlugin, hook_handler
from gobby.hooks.events import HookEventType

class MyTestPlugin(HookPlugin):
    name = "my-test-plugin"
    version = "2.0.0"
    description = "A test plugin from file"

    def on_load(self, config):
        self.config = config

    @hook_handler(HookEventType.BEFORE_TOOL, priority=30)
    def check_tool(self, event):
        return None
""")

            plugins_config.plugin_dirs = [tmpdir]
            loader = PluginLoader(plugins_config)

            discovered = loader.discover_plugins()
            assert len(discovered) == 1
            assert discovered[0].name == "my-test-plugin"

            # Load the plugin
            plugin = loader.load_plugin(discovered[0], {"key": "value"})
            assert plugin.name == "my-test-plugin"
            assert plugin.version == "2.0.0"
            assert plugin.config == {"key": "value"}

    def test_load_module_already_cached(self, plugins_config):
        """Test that _load_module uses cached module."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_file = Path(tmpdir) / "cached_plugin.py"
            plugin_file.write_text("""
from gobby.hooks.plugins import HookPlugin

class CachedPlugin(HookPlugin):
    name = "cached-plugin"
""")

            plugins_config.plugin_dirs = [tmpdir]
            loader = PluginLoader(plugins_config)

            # Load module first time
            classes1 = loader._load_module(plugin_file)
            assert len(classes1) == 1

            # Load same module again - should use cache
            classes2 = loader._load_module(plugin_file)
            assert len(classes2) == 1

            # Verify cache was used (same module object)
            module_name = f"gobby_plugin_{plugin_file.stem}"
            assert module_name in loader._loaded_modules


class TestPluginLoaderLoadPlugin:
    """Tests for PluginLoader.load_plugin method."""

    def test_load_plugin_uses_config_from_plugins_config(self, plugins_config):
        """Test that plugin config is taken from PluginsConfig if available."""
        plugins_config.plugins["sample-plugin"] = PluginItemConfig(
            enabled=True, config={"from_config": True, "value": 42}
        )
        loader = PluginLoader(plugins_config)

        plugin = loader.load_plugin(SamplePlugin)

        # Should use config from PluginsConfig
        assert plugin.loaded_config == {"from_config": True, "value": 42}

    def test_load_plugin_on_load_exception(self, plugins_config):
        """Test that on_load exception is propagated."""

        class FailingPlugin(HookPlugin):
            name = "failing-plugin"

            def on_load(self, config):
                raise RuntimeError("on_load failed!")

        loader = PluginLoader(plugins_config)

        with pytest.raises(RuntimeError, match="on_load failed"):
            loader.load_plugin(FailingPlugin)

    def test_load_plugin_tracks_source_path(self, plugins_config):
        """Test that source path is tracked when available."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_file = Path(tmpdir) / "tracked_plugin.py"
            plugin_file.write_text("""
from gobby.hooks.plugins import HookPlugin

class TrackedPlugin(HookPlugin):
    name = "tracked-plugin"
""")

            plugins_config.plugin_dirs = [tmpdir]
            loader = PluginLoader(plugins_config)

            discovered = loader.discover_plugins()
            assert len(discovered) == 1

            loader.load_plugin(discovered[0])

            # Source path should be tracked
            assert "tracked-plugin" in loader._plugin_sources
            # Compare resolved paths to handle symlinks (e.g., /var -> /private/var on macOS)
            assert loader._plugin_sources["tracked-plugin"].resolve() == plugin_file.resolve()


class TestPluginLoaderUnload:
    """Tests for PluginLoader.unload_plugin method."""

    def test_unload_nonexistent_plugin(self, plugins_config):
        """Test unloading a plugin that doesn't exist."""
        loader = PluginLoader(plugins_config)

        # Should not raise, just return
        loader.unload_plugin("nonexistent")

    def test_unload_plugin_on_unload_exception(self, plugins_config):
        """Test that on_unload exception doesn't prevent unregistration."""

        class FailingUnloadPlugin(HookPlugin):
            name = "failing-unload"

            def on_unload(self):
                raise RuntimeError("on_unload failed!")

        loader = PluginLoader(plugins_config)
        loader.load_plugin(FailingUnloadPlugin)

        # Verify plugin is loaded
        assert loader.registry.get_plugin("failing-unload") is not None

        # Unload should not raise (error is caught)
        loader.unload_plugin("failing-unload")

        # Plugin should still be unregistered despite exception
        assert loader.registry.get_plugin("failing-unload") is None


class TestPluginLoaderLoadAll:
    """Tests for PluginLoader.load_all method."""

    def test_load_all_with_auto_discover(self):
        """Test load_all with auto_discover enabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a plugin file
            plugin_file = Path(tmpdir) / "auto_plugin.py"
            plugin_file.write_text("""
from gobby.hooks.plugins import HookPlugin

class AutoPlugin(HookPlugin):
    name = "auto-plugin"
""")

            config = PluginsConfig(
                enabled=True,
                plugin_dirs=[tmpdir],
                auto_discover=True,
            )
            loader = PluginLoader(config)

            loaded = loader.load_all()
            assert len(loaded) == 1
            assert loaded[0].name == "auto-plugin"

    def test_load_all_skips_disabled_plugin(self):
        """Test load_all skips explicitly disabled plugins."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_file = Path(tmpdir) / "disabled_plugin.py"
            plugin_file.write_text("""
from gobby.hooks.plugins import HookPlugin

class DisabledPlugin(HookPlugin):
    name = "disabled-plugin"
""")

            config = PluginsConfig(
                enabled=True,
                plugin_dirs=[tmpdir],
                auto_discover=True,
                plugins={"disabled-plugin": PluginItemConfig(enabled=False)},
            )
            loader = PluginLoader(config)

            loaded = loader.load_all()
            assert len(loaded) == 0

    def test_load_all_continues_on_error(self):
        """Test load_all continues loading when one plugin fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a failing plugin
            failing = Path(tmpdir) / "failing.py"
            failing.write_text("""
from gobby.hooks.plugins import HookPlugin

class FailingLoadPlugin(HookPlugin):
    name = "failing-load"

    def on_load(self, config):
        raise RuntimeError("Load failed!")
""")

            # Create a working plugin
            working = Path(tmpdir) / "working.py"
            working.write_text("""
from gobby.hooks.plugins import HookPlugin

class WorkingPlugin(HookPlugin):
    name = "working-plugin"
""")

            config = PluginsConfig(
                enabled=True,
                plugin_dirs=[tmpdir],
                auto_discover=True,
            )
            loader = PluginLoader(config)

            loaded = loader.load_all()
            # Only working plugin should be loaded
            assert len(loaded) == 1
            assert loaded[0].name == "working-plugin"


class TestPluginLoaderUnloadAll:
    """Tests for PluginLoader.unload_all method."""

    def test_unload_all(self, plugins_config):
        """Test unload_all unloads all plugins."""
        loader = PluginLoader(plugins_config)

        # Load multiple plugins
        loader.load_plugin(SamplePlugin)
        loader.load_plugin(HighPriorityPlugin)
        loader.load_plugin(LowPriorityPlugin)

        assert len(loader.registry._plugins) == 3

        loader.unload_all()

        assert len(loader.registry._plugins) == 0

    def test_unload_all_handles_exception(self, plugins_config):
        """Test unload_all continues when one unload fails."""

        class FailUnloadPlugin1(HookPlugin):
            name = "fail-unload-1"

            def on_unload(self):
                raise RuntimeError("Unload failed!")

        class NormalPlugin(HookPlugin):
            name = "normal-plugin"
            unloaded = False

            def on_unload(self):
                NormalPlugin.unloaded = True

        loader = PluginLoader(plugins_config)
        loader.load_plugin(FailUnloadPlugin1)
        loader.load_plugin(NormalPlugin)

        # Should not raise
        loader.unload_all()

        # All plugins should be unregistered
        assert len(loader.registry._plugins) == 0
        assert NormalPlugin.unloaded is True

    def test_unload_all_catches_unload_plugin_exception(self, plugins_config):
        """Test unload_all catches exception from unload_plugin itself."""
        from unittest.mock import patch

        loader = PluginLoader(plugins_config)
        loader.load_plugin(SamplePlugin)
        loader.load_plugin(HighPriorityPlugin)

        # Mock unload_plugin to raise an exception
        with patch.object(loader, "unload_plugin", side_effect=RuntimeError("Unload error")):
            # Should not raise
            loader.unload_all()

        # Plugins are still registered because the mock prevented actual unloading,
        # but the test verifies unload_all caught the exception gracefully


class TestPluginLoaderReload:
    """Tests for PluginLoader.reload_plugin method."""

    def test_reload_nonexistent_plugin(self, plugins_config):
        """Test reloading a plugin that doesn't exist."""
        loader = PluginLoader(plugins_config)

        result = loader.reload_plugin("nonexistent")
        assert result is None

    def test_reload_plugin_success(self, plugins_config):
        """Test successfully reloading a plugin from file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_file = Path(tmpdir) / "reloadable.py"
            plugin_file.write_text("""
from gobby.hooks.plugins import HookPlugin

class ReloadablePlugin(HookPlugin):
    name = "reloadable"
    version = "1.0.0"
""")

            plugins_config.plugin_dirs = [tmpdir]
            loader = PluginLoader(plugins_config)

            # Discover and load
            discovered = loader.discover_plugins()
            loader.load_plugin(discovered[0])

            # Modify the plugin file
            plugin_file.write_text("""
from gobby.hooks.plugins import HookPlugin

class ReloadablePlugin(HookPlugin):
    name = "reloadable"
    version = "2.0.0"  # Version changed
""")

            # Reload
            reloaded = loader.reload_plugin("reloadable")

            assert reloaded is not None
            assert reloaded.version == "2.0.0"

    def test_reload_plugin_no_source_path(self, plugins_config):
        """Test reloading a plugin when source path is not available."""
        loader = PluginLoader(plugins_config)

        # Load plugin directly (no source path)
        loader.load_plugin(SamplePlugin)

        result = loader.reload_plugin("sample-plugin")
        assert result is None

    def test_reload_plugin_source_file_deleted(self, plugins_config):
        """Test reloading when source file has been deleted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_file = Path(tmpdir) / "deletable.py"
            plugin_file.write_text("""
from gobby.hooks.plugins import HookPlugin

class DeletablePlugin(HookPlugin):
    name = "deletable"
""")

            plugins_config.plugin_dirs = [tmpdir]
            loader = PluginLoader(plugins_config)

            discovered = loader.discover_plugins()
            loader.load_plugin(discovered[0])

            # Delete the file
            plugin_file.unlink()

            result = loader.reload_plugin("deletable")
            assert result is None

    def test_reload_plugin_class_name_changed(self, plugins_config):
        """Test reloading when plugin class name changes (different class)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_file = Path(tmpdir) / "changeable.py"
            plugin_file.write_text("""
from gobby.hooks.plugins import HookPlugin

class ChangeablePlugin(HookPlugin):
    name = "changeable"
""")

            plugins_config.plugin_dirs = [tmpdir]
            loader = PluginLoader(plugins_config)

            discovered = loader.discover_plugins()
            loader.load_plugin(discovered[0])

            # Modify file to have different plugin name
            plugin_file.write_text("""
from gobby.hooks.plugins import HookPlugin

class DifferentPlugin(HookPlugin):
    name = "different-name"  # Name changed!
""")

            # Reload should fail because plugin name no longer matches
            result = loader.reload_plugin("changeable")
            assert result is None

    def test_reload_plugin_load_error(self, plugins_config):
        """Test reloading when loading the reloaded module fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_file = Path(tmpdir) / "errorprone.py"
            plugin_file.write_text("""
from gobby.hooks.plugins import HookPlugin

class ErrorPronePlugin(HookPlugin):
    name = "errorprone"
""")

            plugins_config.plugin_dirs = [tmpdir]
            loader = PluginLoader(plugins_config)

            discovered = loader.discover_plugins()
            loader.load_plugin(discovered[0])

            # Modify file to have syntax error
            plugin_file.write_text("""
def broken(  # Syntax error
    pass
""")

            result = loader.reload_plugin("errorprone")
            assert result is None

    def test_reload_clears_module_caches(self, plugins_config):
        """Test that reload clears module caches properly."""
        import sys

        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_file = Path(tmpdir) / "cached.py"
            plugin_file.write_text("""
from gobby.hooks.plugins import HookPlugin

class CachedPlugin(HookPlugin):
    name = "cached"
""")

            plugins_config.plugin_dirs = [tmpdir]
            loader = PluginLoader(plugins_config)

            discovered = loader.discover_plugins()
            loader.load_plugin(discovered[0])

            module_name = f"gobby_plugin_{plugin_file.stem}"

            # Verify module is cached
            assert module_name in loader._loaded_modules
            assert module_name in sys.modules
            assert "cached" in loader._plugin_sources

            # Update file content
            plugin_file.write_text("""
from gobby.hooks.plugins import HookPlugin

class CachedPlugin(HookPlugin):
    name = "cached"
    version = "2.0.0"
""")

            # Reload
            reloaded = loader.reload_plugin("cached")

            # Verify new version
            assert reloaded is not None
            assert reloaded.version == "2.0.0"


# =============================================================================
# Test run_plugin_handlers Additional Coverage
# =============================================================================


class TestRunPluginHandlersAdditional:
    """Additional tests for run_plugin_handlers edge cases."""

    def test_post_handler_exception_continues(self):
        """Test that post-handler errors don't stop processing."""

        class PostErrorPlugin(HookPlugin):
            name = "post-error"

            @hook_handler(HookEventType.AFTER_TOOL, priority=60)
            def will_error(self, event, response):
                raise RuntimeError("Post-handler error")

        class PostObserverPlugin(HookPlugin):
            name = "post-observer"
            observed = False

            @hook_handler(HookEventType.AFTER_TOOL, priority=70)
            def observe(self, event, response):
                PostObserverPlugin.observed = True

        registry = PluginRegistry()
        registry.register_plugin(PostErrorPlugin())
        registry.register_plugin(PostObserverPlugin())

        event = HookEvent(
            event_type=HookEventType.AFTER_TOOL,
            session_id="test",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC).isoformat(),
            data={},
        )
        core_response = HookResponse(decision="allow")

        # Should not raise
        result = run_plugin_handlers(registry, event, pre=False, core_response=core_response)

        assert result is None
        assert PostObserverPlugin.observed is True

    def test_pre_handler_returns_block_decision(self):
        """Test that pre-handler can return 'block' decision."""

        class BlockPlugin(HookPlugin):
            name = "block-plugin"

            @hook_handler(HookEventType.BEFORE_TOOL, priority=10)
            def block_it(self, event):
                return HookResponse(
                    decision="block",
                    reason="Blocked for safety",
                    metadata={"blocked_by": "block-plugin"},
                )

        registry = PluginRegistry()
        registry.register_plugin(BlockPlugin())

        event = HookEvent(
            event_type=HookEventType.BEFORE_TOOL,
            session_id="test",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC).isoformat(),
            data={},
        )

        result = run_plugin_handlers(registry, event, pre=True)

        assert result is not None
        assert result.decision == "block"
        assert result.reason == "Blocked for safety"
        assert result.metadata == {"blocked_by": "block-plugin"}

    def test_pre_handler_non_blocking_response_continues(self):
        """Test that pre-handler returning allow continues processing."""

        class AllowPlugin(HookPlugin):
            name = "allow-plugin"

            @hook_handler(HookEventType.BEFORE_TOOL, priority=10)
            def allow_it(self, event):
                return HookResponse(decision="allow")

        class SecondPlugin(HookPlugin):
            name = "second-plugin"
            checked = False

            @hook_handler(HookEventType.BEFORE_TOOL, priority=20)
            def check_it(self, event):
                SecondPlugin.checked = True
                return None

        registry = PluginRegistry()
        registry.register_plugin(AllowPlugin())
        registry.register_plugin(SecondPlugin())

        event = HookEvent(
            event_type=HookEventType.BEFORE_TOOL,
            session_id="test",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC).isoformat(),
            data={},
        )

        result = run_plugin_handlers(registry, event, pre=True)

        assert result is None
        assert SecondPlugin.checked is True
