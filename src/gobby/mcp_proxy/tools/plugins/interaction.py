"""Plugin interaction tools: call actions, list actions/conditions."""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gobby.hooks.hook_manager import HookManager
    from gobby.mcp_proxy.tools.internal import InternalToolRegistry

logger = logging.getLogger(__name__)


def register_interaction_tools(
    registry: InternalToolRegistry,
    get_hook_manager: Callable[[], HookManager | None],
) -> None:
    """Register plugin interaction tools on the registry."""

    def _get_loader() -> Any:
        hm = get_hook_manager()
        if hm is None:
            return None
        return getattr(hm, "_plugin_loader", None)

    @registry.tool(
        name="call_plugin_action",
        description="Call a registered plugin action by plugin name and action name.",
    )
    async def call_plugin_action(
        plugin: str,
        action: str,
        args: str = "",
    ) -> dict[str, Any]:
        """
        Call a plugin action.

        Args:
            plugin: Plugin name
            action: Action name
            args: JSON string of action arguments (optional)
        """
        loader = _get_loader()
        if loader is None:
            return {"success": False, "error": "Plugin system not initialized"}

        plugin_action = loader.registry.get_plugin_action(plugin, action)
        if plugin_action is None:
            return {
                "success": False,
                "error": f"Action '{action}' not found on plugin '{plugin}'",
            }

        # Parse args
        kwargs: dict[str, Any] = {}
        if args:
            try:
                kwargs = json.loads(args)
            except json.JSONDecodeError as e:
                return {"success": False, "error": f"Invalid JSON args: {e}"}

        # Validate input against schema
        is_valid, err = plugin_action.validate_input(kwargs)
        if not is_valid:
            return {"success": False, "error": f"Validation failed: {err}"}

        # Call the action handler
        try:
            if inspect.iscoroutinefunction(plugin_action.handler):
                result = await plugin_action.handler(**kwargs)
            else:
                result = await asyncio.to_thread(plugin_action.handler, **kwargs)

            return {"success": True, "result": result}
        except Exception as e:
            logger.exception(f"Plugin action '{plugin}.{action}' failed")
            return {"success": False, "error": "Plugin action failed"}

    @registry.tool(
        name="list_plugin_actions",
        description="List available actions for a specific plugin.",
    )
    async def list_plugin_actions(plugin: str) -> dict[str, Any]:
        """
        List actions registered by a plugin.

        Args:
            plugin: Plugin name
        """
        loader = _get_loader()
        if loader is None:
            return {"success": False, "error": "Plugin system not initialized"}

        plugin_obj = loader.registry.get_plugin(plugin)
        if plugin_obj is None:
            return {"success": False, "error": f"Plugin not found: {plugin}"}

        actions = [
            {
                "name": a.name,
                "schema": a.schema if a.schema else None,
                "plugin": a.plugin_name,
            }
            for a in plugin_obj._actions.values()
        ]

        return {"success": True, "plugin": plugin, "actions": actions}

    @registry.tool(
        name="list_plugin_conditions",
        description="List available conditions for a specific plugin.",
    )
    async def list_plugin_conditions(plugin: str) -> dict[str, Any]:
        """
        List conditions registered by a plugin.

        Args:
            plugin: Plugin name
        """
        loader = _get_loader()
        if loader is None:
            return {"success": False, "error": "Plugin system not initialized"}

        plugin_obj = loader.registry.get_plugin(plugin)
        if plugin_obj is None:
            return {"success": False, "error": f"Plugin not found: {plugin}"}

        return {
            "success": True,
            "plugin": plugin,
            "conditions": list(plugin_obj._conditions.keys()),
        }
