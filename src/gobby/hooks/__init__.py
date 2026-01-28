"""
Gobby hooks package for Claude Code, Gemini CLI, and Codex integration.

This package provides a hook system for intercepting and processing events
from AI coding assistants. The architecture follows the Coordinator pattern:

Core Components:
    HookManager: Main entry point and coordinator. Receives hook events and
        delegates to specialized components.

    EventHandlers: Contains all event handler implementations for the 15
        supported event types (session, agent, tool, etc.)

    SessionCoordinator: Manages session lifecycle - registration, lookup,
        status tracking, and cleanup.

    HealthMonitor: Background daemon health check monitoring with caching.

    WebhookDispatcher: Dispatches hook events to external webhook endpoints.

Event Models:
    HookEventType: Unified event type enum (15 types across all CLIs)
    SessionSource: Enum identifying which CLI originated the session
    HookEvent: Unified event dataclass from any CLI source
    HookResponse: Unified response dataclass returned to CLIs

Plugin System:
    HookPlugin: Base class for custom hook plugins
    PluginLoader: Discovers and loads plugins from configured paths
    hook_handler: Decorator for registering plugin handlers

Example:
    ```python
    from gobby.hooks import HookManager, HookEvent, HookEventType

    # Create manager (typically done once in daemon)
    manager = HookManager()

    # Handle incoming events
    response = manager.handle(event)
    ```
"""

# Core coordinator and components
# Artifact capture hook
from gobby.hooks.artifact_capture import ArtifactCaptureHook
from gobby.hooks.event_handlers import EventHandlers
from gobby.hooks.events import (
    EVENT_TYPE_CLI_SUPPORT,
    HookEvent,
    HookEventType,
    HookResponse,
    SessionSource,
)
from gobby.hooks.health_monitor import HealthMonitor
from gobby.hooks.hook_manager import HookManager
from gobby.hooks.plugins import (
    HookPlugin,
    PluginLoader,
    PluginRegistry,
    RegisteredHandler,
    hook_handler,
    run_plugin_handlers,
)
from gobby.hooks.session_coordinator import SessionCoordinator
from gobby.hooks.webhooks import WebhookDispatcher

__all__ = [
    # Core coordinator
    "HookManager",
    # Extracted components (for advanced usage/testing)
    "EventHandlers",
    "SessionCoordinator",
    "HealthMonitor",
    "WebhookDispatcher",
    # Artifact capture
    "ArtifactCaptureHook",
    # Unified hook event models
    "HookEventType",
    "SessionSource",
    "HookEvent",
    "HookResponse",
    "EVENT_TYPE_CLI_SUPPORT",
    # Plugin system
    "HookPlugin",
    "PluginLoader",
    "PluginRegistry",
    "RegisteredHandler",
    "hook_handler",
    "run_plugin_handlers",
]
