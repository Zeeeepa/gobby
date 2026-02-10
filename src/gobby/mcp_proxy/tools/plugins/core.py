"""Core plugin management tools: list, get, reload, config."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gobby.hooks.hook_manager import HookManager
    from gobby.mcp_proxy.tools.internal import InternalToolRegistry

logger = logging.getLogger(__name__)


def _get_plugin_loader(get_hook_manager: Callable[[], HookManager | None]) -> Any:
    """Get the plugin loader from the hook manager, or None."""
    hm = get_hook_manager()
    if hm is None:
        return None
    return getattr(hm, "_plugin_loader", None)


def register_core_tools(
    registry: InternalToolRegistry,
    get_hook_manager: Callable[[], HookManager | None],
) -> None:
    """Register core plugin management tools on the registry."""

    @registry.tool(
        name="list_plugins",
        description="List loaded plugins with metadata (handlers, actions, conditions).",
    )
    async def list_plugins(enabled_only: bool = False) -> dict[str, Any]:
        """
        List loaded plugins.

        Args:
            enabled_only: If true, only show plugins from enabled plugin system
        """
        loader = _get_plugin_loader(get_hook_manager)
        if loader is None:
            return {
                "success": True,
                "enabled": False,
                "plugins": [],
                "message": "Plugin system not initialized",
            }

        if enabled_only and not loader.config.enabled:
            return {
                "success": True,
                "enabled": False,
                "plugins": [],
                "message": "Plugin system is disabled",
            }

        plugins = loader.registry.list_plugins()
        return {
            "success": True,
            "enabled": loader.config.enabled,
            "plugins": plugins,
            "plugin_dirs": loader.config.plugin_dirs,
        }

    @registry.tool(
        name="get_plugin",
        description="Get full metadata for a specific plugin by name.",
    )
    async def get_plugin(name: str) -> dict[str, Any]:
        """
        Get a plugin by name with full metadata.

        Args:
            name: Plugin name
        """
        loader = _get_plugin_loader(get_hook_manager)
        if loader is None:
            return {"success": False, "error": "Plugin system not initialized"}

        plugin = loader.registry.get_plugin(name)
        if plugin is None:
            return {"success": False, "error": f"Plugin not found: {name}"}

        return {
            "success": True,
            "name": plugin.name,
            "version": plugin.version,
            "description": plugin.description,
            "actions": list(plugin._actions.keys()),
            "conditions": list(plugin._conditions.keys()),
        }

    @registry.tool(
        name="reload_plugin",
        description="Reload a plugin by name (unloads then reloads from source).",
    )
    async def reload_plugin(name: str) -> dict[str, Any]:
        """
        Reload a plugin by name.

        Args:
            name: Plugin name to reload
        """
        loader = _get_plugin_loader(get_hook_manager)
        if loader is None:
            return {"success": False, "error": "Plugin system not initialized"}

        try:
            plugin = loader.reload_plugin(name)
            if plugin is None:
                return {
                    "success": False,
                    "error": f"Plugin not found or reload failed: {name}",
                }

            return {
                "success": True,
                "name": plugin.name,
                "version": plugin.version,
                "description": plugin.description,
            }
        except Exception as e:
            logger.error(f"Plugin reload failed: {e}")
            return {"success": False, "error": str(e)}

    @registry.tool(
        name="get_plugin_config",
        description="Get plugin system configuration (enabled state, directories, per-plugin configs).",
    )
    async def get_plugin_config() -> dict[str, Any]:
        """Get plugin system configuration."""
        loader = _get_plugin_loader(get_hook_manager)
        if loader is None:
            return {"success": False, "error": "Plugin system not initialized"}

        plugin_configs = {}
        for name, item in loader.config.plugins.items():
            plugin_configs[name] = {
                "enabled": item.enabled,
                "config": item.config,
            }

        return {
            "success": True,
            "enabled": loader.config.enabled,
            "auto_discover": loader.config.auto_discover,
            "plugin_dirs": loader.config.plugin_dirs,
            "plugins": plugin_configs,
        }
