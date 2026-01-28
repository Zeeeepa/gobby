"""
Python plugin system for hook handlers.

This module provides infrastructure for dynamically loading Python plugins
that can intercept and modify hook behavior.

Security Note: Plugins run with full daemon privileges. Only enable plugins
you trust. The plugin system is disabled by default.
"""

from __future__ import annotations

import importlib.util
import inspect
import logging
import sys
from abc import ABC
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from gobby.hooks.events import HookEvent, HookEventType, HookResponse

if TYPE_CHECKING:
    from gobby.config.extensions import PluginsConfig

logger = logging.getLogger(__name__)


# =============================================================================
# Plugin Action Registration
# =============================================================================


@dataclass
class PluginAction:
    """A registered workflow action from a plugin.

    Attributes:
        name: Action name (without plugin prefix).
        handler: Async callable matching ActionHandler protocol.
        schema: JSON Schema dict describing the action's input parameters.
        plugin_name: Name of the plugin that registered this action.
    """

    name: str
    handler: Callable[..., Any]
    schema: dict[str, Any]
    plugin_name: str

    def validate_input(self, kwargs: dict[str, Any]) -> tuple[bool, str | None]:
        """Validate input arguments against the action's schema.

        Args:
            kwargs: Input arguments to validate.

        Returns:
            Tuple of (is_valid, error_message).
            If valid, error_message is None.
        """
        if not self.schema:
            return True, None  # No schema means no validation

        # Basic JSON Schema validation (properties + required)
        properties = self.schema.get("properties", {})
        required = self.schema.get("required", [])

        # Check required fields
        for field_name in required:
            if field_name not in kwargs:
                return False, f"Missing required field: {field_name}"

        # Check property types if specified
        for prop_name, prop_schema in properties.items():
            if prop_name not in kwargs:
                continue  # Optional field not provided

            value = kwargs[prop_name]
            prop_type = prop_schema.get("type")

            if prop_type and not _check_type(value, prop_type):
                return False, f"Field '{prop_name}' has invalid type: expected {prop_type}"

        return True, None


def _check_type(value: Any, expected_type: str) -> bool:
    """Check if a value matches a JSON Schema type."""
    # Explicitly reject bool for numeric types since bool is a subclass of int
    if expected_type in ("integer", "number") and isinstance(value, bool):
        return False

    type_map = {
        "string": str,
        "number": (int, float),
        "integer": int,
        "boolean": bool,
        "array": list,
        "object": dict,
        "null": type(None),
    }

    expected = type_map.get(expected_type)
    if expected is None:
        return True  # Unknown type, skip validation

    return isinstance(value, expected)  # type: ignore[arg-type]


# =============================================================================
# Decorator
# =============================================================================


def hook_handler(
    event_type: HookEventType,
    priority: int = 50,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Decorator to mark a method as a hook handler.

    Args:
        event_type: The HookEventType this handler responds to.
        priority: Execution priority (lower = earlier).
            - Priority < 50: Pre-handlers (run before core, can block)
            - Priority >= 50: Post-handlers (run after core, observe only)

    Handler Signatures:
        Pre-handlers (priority < 50):
            def handler(self, event: HookEvent) -> HookResponse | None
            - Receives only the event
            - Return HookResponse with decision="deny" or "block" to block
            - Return None to continue to next handler

        Post-handlers (priority >= 50):
            def handler(self, event: HookEvent, core_response: HookResponse | None) -> None
            - Receives event AND the core handler's response
            - Cannot block; return value is ignored
            - IMPORTANT: Must accept two arguments or a TypeError will be raised

    Examples:
        class MyPlugin(HookPlugin):
            name = "my-plugin"

            # Pre-handler: can block dangerous tools
            @hook_handler(HookEventType.BEFORE_TOOL, priority=10)
            def check_tool(self, event: HookEvent) -> HookResponse | None:
                if "dangerous" in event.data.get("tool_name", ""):
                    return HookResponse(decision="deny", reason="Blocked")
                return None  # Continue to next handler

            # Post-handler: observe and log after core processing
            @hook_handler(HookEventType.AFTER_TOOL, priority=60)
            def log_tool_result(
                self, event: HookEvent, core_response: HookResponse | None
            ) -> None:
                tool = event.data.get("tool_name", "unknown")
                status = core_response.decision if core_response else "no-response"
                logger.info(f"Tool {tool} completed with status: {status}")
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        # Store metadata on the function
        func._hook_event_type = event_type  # type: ignore[attr-defined]
        func._hook_priority = priority  # type: ignore[attr-defined]
        return func

    return decorator


# =============================================================================
# Base Class
# =============================================================================


class HookPlugin(ABC):
    """
    Base class for hook plugins.

    Subclass this to create a plugin. At minimum, set the `name` class attribute
    and implement handler methods decorated with @hook_handler.

    Attributes:
        name: Unique plugin identifier (required).
        version: Plugin version string (default: "1.0.0").
        description: Human-readable description.

    Example:
        class MyPlugin(HookPlugin):
            name = "my-plugin"
            version = "1.0.0"
            description = "Blocks dangerous commands"

            def on_load(self, config: dict) -> None:
                self.blocked_patterns = config.get("blocked", [])

            @hook_handler(HookEventType.BEFORE_TOOL, priority=10)
            def check_tool(self, event: HookEvent) -> HookResponse | None:
                # Return HookResponse to block, None to continue
                return None
    """

    name: str
    version: str = "1.0.0"
    description: str = ""

    def __init__(self) -> None:
        """Initialize plugin instance."""
        # Containers for registered workflow extensions
        self._actions: dict[str, PluginAction] = {}
        self._conditions: dict[str, Callable[..., Any]] = {}
        self.logger = logging.getLogger(f"gobby.plugins.{self.name}")

    def on_load(self, config: dict[str, Any]) -> None:  # noqa: B027
        """
        Called when plugin is loaded.

        Override to initialize plugin state with configuration.

        Args:
            config: Plugin-specific configuration from PluginItemConfig.config
        """
        # Optional lifecycle hook - subclasses may override

    def on_unload(self) -> None:  # noqa: B027
        """
        Called when plugin is unloaded.

        Override to cleanup resources.
        """
        # Optional lifecycle hook - subclasses may override

    def register_action(self, name: str, handler: Callable[..., Any]) -> None:
        """
        Register a workflow action (simple form without schema).

        Actions registered here can be used in workflow YAML files.
        They will be available as `plugin:<plugin-name>:<action-name>`.

        For actions that require input validation, use register_workflow_action().

        Args:
            name: Action name (without plugin prefix).
            handler: Async callable matching ActionHandler protocol.
        """
        action = PluginAction(
            name=name,
            handler=handler,
            schema={},
            plugin_name=self.name,
        )
        self._actions[name] = action
        self.logger.debug(f"Registered action: {name}")

    def register_workflow_action(
        self,
        action_type: str,
        schema: dict[str, Any],
        executor_fn: Callable[..., Any],
    ) -> None:
        """
        Register a workflow action with schema validation.

        Actions registered here can be used in workflow YAML files.
        They will be available as `plugin:<plugin-name>:<action-type>`.
        Input arguments will be validated against the schema before execution.

        Args:
            action_type: Action name (without plugin prefix).
            schema: JSON Schema dict for input validation. Should contain:
                - properties: Dict of property names to their schemas
                - required: List of required property names
                Example:
                    {
                        "properties": {
                            "message": {"type": "string"},
                            "channel": {"type": "string"}
                        },
                        "required": ["message"]
                    }
            executor_fn: Async callable matching ActionHandler protocol:
                async def handler(context: ActionContext, **kwargs) -> dict | None

        Raises:
            ValueError: If action_type is already registered.
        """
        if action_type in self._actions:
            raise ValueError(
                f"Action type '{action_type}' is already registered for plugin '{self.name}'"
            )

        action = PluginAction(
            name=action_type,
            handler=executor_fn,
            schema=schema,
            plugin_name=self.name,
        )
        self._actions[action_type] = action
        self.logger.debug(f"Registered workflow action: {action_type} with schema")

    def get_action(self, name: str) -> PluginAction | None:
        """
        Get a registered action by name.

        Args:
            name: Action name (without plugin prefix).

        Returns:
            PluginAction if found, None otherwise.
        """
        return self._actions.get(name)

    def register_condition(self, name: str, evaluator: Callable[..., Any]) -> None:
        """
        Register a workflow condition.

        Conditions registered here can be used in workflow `when` clauses.
        They will be available as `plugin:<plugin-name>:<condition-name>`.

        Args:
            name: Condition name (without plugin prefix).
            evaluator: Callable that returns bool given context dict.
        """
        self._conditions[name] = evaluator
        self.logger.debug(f"Registered condition: {name}")


# =============================================================================
# Handler Registration
# =============================================================================


@dataclass
class RegisteredHandler:
    """A registered hook handler with metadata."""

    plugin: HookPlugin
    method: Callable[..., Any]
    event_type: HookEventType
    priority: int


@dataclass
class PluginRegistry:
    """
    Manages loaded plugins and their handlers.

    Maintains a registry of plugins and their hook handlers, providing
    priority-sorted handler retrieval.
    """

    _plugins: dict[str, HookPlugin] = field(default_factory=dict)
    _handlers: dict[HookEventType, list[RegisteredHandler]] = field(default_factory=dict)

    def register_plugin(self, plugin: HookPlugin) -> None:
        """
        Register a plugin and its handlers.

        Scans the plugin for methods decorated with @hook_handler and
        registers them in priority order.

        Args:
            plugin: The plugin instance to register.

        Raises:
            ValueError: If a plugin with the same name is already registered.
        """
        if plugin.name in self._plugins:
            raise ValueError(f"Plugin already registered: {plugin.name}")

        self._plugins[plugin.name] = plugin

        # Find and register all @hook_handler decorated methods
        for name, method in inspect.getmembers(plugin, predicate=inspect.ismethod):
            if hasattr(method, "_hook_event_type"):
                event_type = method._hook_event_type
                priority = getattr(method, "_hook_priority", 50)

                handler = RegisteredHandler(
                    plugin=plugin,
                    method=method,
                    event_type=event_type,
                    priority=priority,
                )

                if event_type not in self._handlers:
                    self._handlers[event_type] = []

                self._handlers[event_type].append(handler)
                # Keep sorted by priority
                self._handlers[event_type].sort(key=lambda h: h.priority)

                logger.debug(
                    f"Registered handler: {plugin.name}.{name} for {event_type.value} "
                    f"(priority={priority})"
                )

    def unregister_plugin(self, name: str) -> None:
        """
        Unregister a plugin and remove its handlers.

        Args:
            name: The plugin name to unregister.
        """
        if name not in self._plugins:
            logger.warning(f"Plugin not registered: {name}")
            return

        plugin = self._plugins.pop(name)

        # Remove handlers for this plugin
        for event_type in list(self._handlers.keys()):
            self._handlers[event_type] = [
                h for h in self._handlers[event_type] if h.plugin is not plugin
            ]
            if not self._handlers[event_type]:
                del self._handlers[event_type]

        logger.info(f"Unregistered plugin: {name}")

    def get_handlers(
        self,
        event_type: HookEventType,
        pre_only: bool = False,
        post_only: bool = False,
    ) -> list[RegisteredHandler]:
        """
        Get handlers for an event type, optionally filtered by priority.

        Args:
            event_type: The event type to get handlers for.
            pre_only: If True, only return handlers with priority < 50.
            post_only: If True, only return handlers with priority >= 50.

        Returns:
            List of RegisteredHandler sorted by priority.
        """
        handlers = self._handlers.get(event_type, [])

        if pre_only:
            return [h for h in handlers if h.priority < 50]
        if post_only:
            return [h for h in handlers if h.priority >= 50]

        return handlers

    def get_plugin(self, name: str) -> HookPlugin | None:
        """Get a plugin by name."""
        return self._plugins.get(name)

    def list_plugins(self) -> list[dict[str, Any]]:
        """List all registered plugins with metadata."""
        return [
            {
                "name": p.name,
                "version": p.version,
                "description": p.description,
                "handlers": [
                    {"event": h.event_type.value, "priority": h.priority}
                    for handlers in self._handlers.values()
                    for h in handlers
                    if h.plugin is p
                ],
                "actions": [
                    {
                        "name": action.name,
                        "has_schema": bool(action.schema),
                        "schema": action.schema if action.schema else None,
                    }
                    for action in p._actions.values()
                ],
                "conditions": list(p._conditions.keys()),
            }
            for p in self._plugins.values()
        ]

    def get_plugin_action(self, plugin_name: str, action_name: str) -> PluginAction | None:
        """Get a specific action from a plugin.

        Args:
            plugin_name: Name of the plugin.
            action_name: Name of the action.

        Returns:
            PluginAction if found, None otherwise.
        """
        plugin = self._plugins.get(plugin_name)
        if plugin is None:
            return None
        return plugin.get_action(action_name)


# =============================================================================
# Plugin Loader
# =============================================================================


class PluginLoader:
    """
    Discovers and loads plugins from configured directories.

    Handles plugin discovery, import, instantiation, and lifecycle management.
    """

    def __init__(self, config: PluginsConfig) -> None:
        """
        Initialize the plugin loader.

        Args:
            config: Plugin system configuration.
        """
        self.config = config
        self.registry = PluginRegistry()
        self._loaded_modules: dict[str, Any] = {}
        self._plugin_sources: dict[str, Path] = {}  # Maps plugin name -> source file path

    def discover_plugins(self, dirs: list[str] | None = None) -> list[type[HookPlugin]]:
        """
        Discover plugin classes from configured directories.

        Args:
            dirs: Optional list of directories to scan. Uses config.plugin_dirs if None.

        Returns:
            List of discovered HookPlugin subclasses.
        """
        search_dirs = dirs or self.config.plugin_dirs
        discovered: list[type[HookPlugin]] = []

        for dir_path in search_dirs:
            # Expand ~ and resolve path
            expanded = Path(dir_path).expanduser().resolve()

            if not expanded.exists():
                logger.debug(f"Plugin directory does not exist: {expanded}")
                continue

            if not expanded.is_dir():
                logger.warning(f"Plugin path is not a directory: {expanded}")
                continue

            # Scan for Python files
            for py_file in expanded.glob("*.py"):
                if py_file.name.startswith("_"):
                    continue  # Skip __init__.py, __pycache__, etc.

                try:
                    plugin_classes = self._load_module(py_file)
                    discovered.extend(plugin_classes)
                except Exception as e:
                    logger.error(f"Failed to load plugin module {py_file}: {e}")

        logger.info(f"Discovered {len(discovered)} plugin class(es)")
        return discovered

    def _load_module(self, path: Path) -> list[type[HookPlugin]]:
        """
        Load a Python module and find HookPlugin subclasses.

        Args:
            path: Path to the Python file.

        Returns:
            List of HookPlugin subclasses found in the module.
        """
        module_name = f"gobby_plugin_{path.stem}"

        # Check if already loaded
        if module_name in self._loaded_modules:
            module = self._loaded_modules[module_name]
        else:
            # Load the module
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                raise ImportError(f"Cannot load module spec from {path}")

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            self._loaded_modules[module_name] = module

        # Find HookPlugin subclasses
        plugin_classes: list[type[HookPlugin]] = []
        for _name, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, HookPlugin)
                and obj is not HookPlugin
                and hasattr(obj, "name")
                and obj.name  # Must have a non-empty name
            ):
                # Store source path on the class for reload tracking
                obj._gobby_source_path = path  # type: ignore[attr-defined]
                plugin_classes.append(obj)

        return plugin_classes

    def load_plugin(
        self,
        plugin_class: type[HookPlugin],
        config: dict[str, Any] | None = None,
    ) -> HookPlugin:
        """
        Instantiate and load a plugin.

        Args:
            plugin_class: The plugin class to instantiate.
            config: Optional configuration to pass to on_load().

        Returns:
            The loaded plugin instance.
        """
        # Get per-plugin config from PluginsConfig if available
        plugin_config = config or {}
        if plugin_class.name in self.config.plugins:
            item_config = self.config.plugins[plugin_class.name]
            if not item_config.enabled:
                raise ValueError(f"Plugin is disabled in config: {plugin_class.name}")
            plugin_config = item_config.config

        # Instantiate
        plugin = plugin_class()

        # Call lifecycle hook
        try:
            plugin.on_load(plugin_config)
        except Exception as e:
            logger.error(f"Plugin on_load failed for {plugin.name}: {e}")
            raise

        # Register in registry
        self.registry.register_plugin(plugin)

        # Track source path for reload support
        if hasattr(plugin_class, "_gobby_source_path"):
            self._plugin_sources[plugin.name] = plugin_class._gobby_source_path

        logger.info(f"Loaded plugin: {plugin.name} v{plugin.version}")
        return plugin

    def unload_plugin(self, name: str) -> None:
        """
        Unload a plugin.

        Args:
            name: The plugin name to unload.
        """
        plugin = self.registry.get_plugin(name)
        if plugin is None:
            logger.warning(f"Plugin not found: {name}")
            return

        # Call lifecycle hook
        try:
            plugin.on_unload()
        except Exception as e:
            logger.error(f"Plugin on_unload failed for {name}: {e}")
            # Continue with unregistration even if on_unload fails

        # Unregister
        self.registry.unregister_plugin(name)

        logger.info(f"Unloaded plugin: {name}")

    def load_all(self) -> list[HookPlugin]:
        """
        Discover and load all plugins.

        Returns:
            List of successfully loaded plugins.
        """
        if not self.config.enabled:
            logger.debug("Plugin system is disabled")
            return []

        loaded: list[HookPlugin] = []

        if self.config.auto_discover:
            plugin_classes = self.discover_plugins()

            for plugin_class in plugin_classes:
                # Check if explicitly disabled
                if plugin_class.name in self.config.plugins:
                    if not self.config.plugins[plugin_class.name].enabled:
                        logger.debug(f"Skipping disabled plugin: {plugin_class.name}")
                        continue

                try:
                    plugin = self.load_plugin(plugin_class)
                    loaded.append(plugin)
                except Exception as e:
                    logger.error(f"Failed to load plugin {plugin_class.name}: {e}")
                    # Continue loading other plugins

        return loaded

    def unload_all(self) -> None:
        """Unload all plugins."""
        plugin_names = list(self.registry._plugins.keys())
        for name in plugin_names:
            try:
                self.unload_plugin(name)
            except Exception as e:
                logger.error(f"Failed to unload plugin {name}: {e}")

    def reload_plugin(self, name: str) -> HookPlugin | None:
        """
        Reload a plugin (unload then load).

        Note: Plugin state is lost on reload.

        Args:
            name: The plugin name to reload.

        Returns:
            The reloaded plugin instance, or None if reload failed.
        """
        plugin = self.registry.get_plugin(name)
        if plugin is None:
            logger.warning(f"Plugin not found for reload: {name}")
            return None

        # Get source path before unloading (prefer tracked path over name-based key)
        source_path = self._plugin_sources.get(name)

        # Unload
        self.unload_plugin(name)

        # Compute module name from source path if available, else fall back to plugin name
        if source_path is not None:
            module_name = f"gobby_plugin_{source_path.stem}"
        else:
            module_name = f"gobby_plugin_{name}"

        # Clear module cache to force reimport
        if module_name in self._loaded_modules:
            del self._loaded_modules[module_name]
        if module_name in sys.modules:
            del sys.modules[module_name]

        # Clear source tracking (will be re-added on load)
        if name in self._plugin_sources:
            del self._plugin_sources[name]

        # Reload from source file if available
        if source_path is not None and source_path.exists():
            try:
                plugin_classes = self._load_module(source_path)
                # Find the plugin class with matching name
                for plugin_class in plugin_classes:
                    if plugin_class.name == name:
                        return self.load_plugin(plugin_class)
                logger.error(f"Plugin class '{name}' not found in reloaded module")
                return None
            except Exception as e:
                logger.error(f"Failed to reload plugin {name}: {e}")
                return None
        else:
            logger.error(f"Cannot reload plugin {name}: source path not available")
            return None


# =============================================================================
# Handler Execution
# =============================================================================


def run_plugin_handlers(
    registry: PluginRegistry,
    event: HookEvent,
    pre: bool = True,
    core_response: HookResponse | None = None,
) -> HookResponse | None:
    """
    Execute plugin handlers for an event.

    Args:
        registry: The plugin registry.
        event: The hook event to process.
        pre: If True, run pre-handlers (priority < 50). If False, run post-handlers.
        core_response: For post-handlers, the response from the core handler.

    Returns:
        For pre-handlers: HookResponse if any handler blocks, None otherwise.
        For post-handlers: Always None (observe only).
    """
    handlers = registry.get_handlers(event.event_type, pre_only=pre, post_only=not pre)

    for handler in handlers:
        try:
            if pre:
                # Pre-handlers can return HookResponse to block
                result = handler.method(event)
                if result is not None and isinstance(result, HookResponse):
                    if result.decision in ("deny", "block"):
                        logger.info(f"Plugin {handler.plugin.name} blocked event: {result.reason}")
                        return HookResponse(
                            decision=result.decision,
                            reason=result.reason,
                            metadata=result.metadata,
                        )
            else:
                # Post-handlers receive the core response but can't block
                handler.method(event, core_response)

        except Exception as e:
            # Fail-open: log error but continue processing
            logger.error(
                f"Plugin handler {handler.plugin.name}.{handler.method.__name__} failed: {e}",
                exc_info=True,
            )

    return None
