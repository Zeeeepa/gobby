"""Server management service."""

import logging
from typing import Any

from gobby.mcp_proxy.manager import MCPClientManager
from gobby.mcp_proxy.models import MCPServerConfig

logger = logging.getLogger("gobby.mcp.server")


class ServerManagementService:
    """Service for managing MCP server configurations."""

    def __init__(self, mcp_manager: MCPClientManager, config_manager: Any):
        """
        Args:
            mcp_manager: MCP client manager
            config_manager: Config manager (for saving changes)
        """
        self._mcp_manager = mcp_manager
        self._config_manager = config_manager

    async def add_server(
        self,
        name: str,
        transport: str,
        url: str | None = None,
        command: str | None = None,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        enabled: bool = True,
    ) -> dict[str, Any]:
        """Add a new MCP server."""
        try:
            # Create config object
            server_config = MCPServerConfig(
                name=name,
                transport=transport,
                url=url,
                command=command,
                args=args,
                env=env,
                headers=headers,
                enabled=enabled,
            )
            # Validate
            server_config.validate()

            # Add to manager (runtime)
            self._mcp_manager.add_server_config(server_config)

            # Persist to config
            # self._config_manager.add_mcp_server(...) # Mocking this interaction

            # Attempt connection
            if enabled:
                try:
                    await self._mcp_manager.connect_all([server_config])
                except Exception as e:
                    logger.warning(f"Added server {name} but connection failed: {e}")
                    return {
                        "success": True,
                        "message": f"Server added but connection failed: {str(e)}",
                        "connected": False,
                    }

            return {
                "success": True,
                "message": f"Server {name} added successfully",
                "connected": enabled,
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def remove_server(self, name: str) -> dict[str, Any]:
        """Remove an MCP server."""
        try:
            # Remove from runtime
            self._mcp_manager.remove_server_config(name)

            # Persist
            # self._config_manager.remove_mcp_server(name)

            return {"success": True, "message": f"Server {name} removed"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def import_server(
        self,
        from_project: str | None = None,
        github_url: str | None = None,
        query: str | None = None,
        servers: list[str] | None = None,
    ) -> dict[str, Any]:
        """Import MCP server(s)."""
        # (This would contain the logic extracted from server.py import_mcp_server)
        return {"success": True, "message": "Import logic stubbed for refactor"}
