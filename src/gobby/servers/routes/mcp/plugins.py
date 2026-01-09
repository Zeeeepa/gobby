"""
Plugin management routes for Gobby HTTP server.

Provides plugin listing and reloading endpoints.
Extracted from base.py as part of Strangler Fig decomposition.
"""

import logging
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, Request

from gobby.servers.routes.dependencies import get_server

if TYPE_CHECKING:
    from gobby.servers.http import HTTPServer

logger = logging.getLogger(__name__)


def create_plugins_router() -> APIRouter:
    """
    Create plugins management router using dependency injection.

    Returns:
        Configured APIRouter with plugins endpoints
    """
    router = APIRouter(prefix="/plugins", tags=["plugins"])

    @router.get("")
    async def list_plugins(
        request: Request,
        server: "HTTPServer" = Depends(get_server),
    ) -> dict[str, Any]:
        """
        List loaded plugins.

        Returns:
            List of plugins with metadata
        """
        config = server.config
        if not config:
            return {
                "success": True,
                "enabled": False,
                "plugins": [],
                "plugin_dirs": [],
            }

        plugins_config = config.hook_extensions.plugins

        # Get plugin registry from hook manager
        if not hasattr(request.app.state, "hook_manager"):
            return {
                "success": True,
                "enabled": plugins_config.enabled,
                "plugins": [],
                "plugin_dirs": plugins_config.plugin_dirs,
            }

        hook_manager = request.app.state.hook_manager
        if not hasattr(hook_manager, "plugin_loader") or not hook_manager.plugin_loader:
            return {
                "success": True,
                "enabled": plugins_config.enabled,
                "plugins": [],
                "plugin_dirs": plugins_config.plugin_dirs,
            }

        plugins = hook_manager.plugin_loader.registry.list_plugins()

        return {
            "success": True,
            "enabled": plugins_config.enabled,
            "plugins": plugins,
            "plugin_dirs": plugins_config.plugin_dirs,
        }

    @router.post("/reload")
    async def reload_plugin(request: Request) -> dict[str, Any]:
        """
        Reload a plugin by name.

        Request body:
            {"name": "plugin-name"}

        Returns:
            Reload result
        """
        try:
            body = await request.json()
            plugin_name = body.get("name")

            if not plugin_name:
                raise HTTPException(status_code=400, detail="Plugin name required")

            if not hasattr(request.app.state, "hook_manager"):
                return {"success": False, "error": "HookManager not initialized"}

            hook_manager = request.app.state.hook_manager
            if not hasattr(hook_manager, "plugin_loader") or not hook_manager.plugin_loader:
                return {"success": False, "error": "Plugin system not initialized"}

            plugin = hook_manager.plugin_loader.reload_plugin(plugin_name)

            if plugin is None:
                return {"success": False, "error": f"Plugin not found: {plugin_name}"}

            return {
                "success": True,
                "name": plugin.name,
                "version": plugin.version,
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Plugin reload error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    return router
