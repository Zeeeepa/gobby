"""
Internal MCP tools for Gobby Plugin System.

Provides tools for managing plugins, calling plugin actions, and inspecting
hook handlers. Registered as the `gobby-plugins` internal registry.

The hook_manager_resolver pattern solves a timing problem: setup_internal_registries()
runs before HookManager is created in the HTTP lifespan. The resolver is a callable
that returns None until the HookManager is available, then returns it thereafter.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.mcp_proxy.tools.plugins.core import register_core_tools
from gobby.mcp_proxy.tools.plugins.hooks import register_hook_tools
from gobby.mcp_proxy.tools.plugins.interaction import register_interaction_tools

if TYPE_CHECKING:
    from gobby.hooks.hook_manager import HookManager

logger = logging.getLogger(__name__)


def create_plugins_registry(
    hook_manager_resolver: Callable[[], HookManager | None],
) -> InternalToolRegistry:
    """
    Create a plugins tool registry with all plugin-related tools.

    Args:
        hook_manager_resolver: Callable that returns the HookManager when available,
            or None if not yet initialized. Called lazily at tool invocation time.

    Returns:
        InternalToolRegistry with plugin tools registered
    """
    registry = InternalToolRegistry(
        name="gobby-plugins",
        description="Plugin management - list_plugins, reload_plugin, call_plugin_action, list_hook_handlers",
    )

    def get_hook_manager() -> HookManager | None:
        return hook_manager_resolver()

    register_core_tools(registry, get_hook_manager)
    register_interaction_tools(registry, get_hook_manager)
    register_hook_tools(registry, get_hook_manager)

    logger.debug("Plugins registry created with %d tools", len(registry._tools))
    return registry
