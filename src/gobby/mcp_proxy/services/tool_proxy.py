"""Tool proxy service."""

import logging
from typing import TYPE_CHECKING, Any

from gobby.mcp_proxy.manager import MCPClientManager
from gobby.mcp_proxy.models import MCPError

if TYPE_CHECKING:
    from gobby.mcp_proxy.tools.internal import InternalRegistryManager

logger = logging.getLogger("gobby.mcp.server")


def safe_truncate(text: str | bytes | None, length: int = 100) -> str:
    """Safely truncate text to length by unicode code points."""
    if text is None:
        return ""
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")
    if len(text) <= length:
        return text
    return text[:length] + "..."


class ToolProxyService:
    """Service for proxying tool calls and resource reads to underlying MCP servers."""

    def __init__(
        self,
        mcp_manager: MCPClientManager,
        internal_manager: "InternalRegistryManager | None" = None,
    ):
        self._mcp_manager = mcp_manager
        self._internal_manager = internal_manager

    async def list_tools(self, server_name: str | None = None) -> dict[str, Any]:
        """
        List tools with progressive disclosure format.

        Args:
            server_name: Optional server to filter by (e.g., "gobby-tasks", "context7")

        Returns:
            Dict with server name(s) and lightweight tool metadata:
            - If server specified: {"server": "name", "tools": [{name, brief}, ...]}
            - If no server: {"servers": [{"name": "...", "tools": [...]}, ...]}
        """
        # Check if requesting a specific internal server
        if (
            server_name
            and self._internal_manager
            and self._internal_manager.is_internal(server_name)
        ):
            registry = self._internal_manager.get_registry(server_name)
            if registry:
                return {"server": server_name, "tools": registry.list_tools()}
            return {
                "server": server_name,
                "tools": [],
                "error": f"Internal server '{server_name}' not found",
            }

        # Check if requesting a specific external server
        if server_name:
            if self._mcp_manager.has_server(server_name):
                tools_map = await self._mcp_manager.list_tools(server_name)
                tools_list = tools_map.get(server_name, [])
                # Convert to lightweight format
                brief_tools = []
                for tool in tools_list:
                    if isinstance(tool, dict):
                        brief_tools.append(
                            {
                                "name": tool.get("name", "unknown"),
                                "brief": safe_truncate(tool.get("description", "")),
                            }
                        )
                    else:
                        brief_tools.append(
                            {
                                "name": tool.name,
                                "brief": safe_truncate(tool.description),
                            }
                        )
                return {"server": server_name, "tools": brief_tools}

            # NOTE: Keeping return-dict error pattern for list_tools as it returns "data"
            # But for action-oriented methods we switch to raising MCPError
            return {
                "server": server_name,
                "tools": [],
                "error": f"Server '{server_name}' not found",
            }

        # No server specified - return all servers
        servers_result = []

        # Add internal servers first
        if self._internal_manager:
            for registry in self._internal_manager.get_all_registries():
                servers_result.append(
                    {
                        "name": registry.name,
                        "tools": registry.list_tools(),
                    }
                )

        # Add external servers
        tools_map = await self._mcp_manager.list_tools()
        for srv_name, tools_list in tools_map.items():
            brief_tools = []
            for tool in tools_list:
                if isinstance(tool, dict):
                    brief_tools.append(
                        {
                            "name": tool.get("name", "unknown"),
                            "brief": safe_truncate(tool.get("description", "")),
                        }
                    )
                else:
                    brief_tools.append(
                        {
                            "name": tool.name,
                            "brief": safe_truncate(tool.description),
                        }
                    )
            servers_result.append({"name": srv_name, "tools": brief_tools})

        return {"servers": servers_result}

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> Any:
        """Execute a tool."""
        # Check internal tools first
        if self._internal_manager and self._internal_manager.is_internal(server_name):
            registry = self._internal_manager.get_registry(server_name)
            if registry:
                return await registry.call(tool_name, arguments or {})
            raise MCPError(f"Internal server '{server_name}' not found")

        # Use MCP manager for external servers
        return await self._mcp_manager.call_tool(server_name, tool_name, arguments)

    async def read_resource(self, server_name: str, uri: str) -> Any:
        """Read a resource."""
        return await self._mcp_manager.read_resource(server_name, uri)

    async def get_tool_schema(self, server_name: str, tool_name: str) -> dict[str, Any]:
        """Get full schema for a specific tool."""
        # Check internal tools first
        if self._internal_manager and self._internal_manager.is_internal(server_name):
            registry = self._internal_manager.get_registry(server_name)
            if registry:
                schema = registry.get_schema(tool_name)
                if schema:
                    return {"status": "success", "tool": schema}
                return {
                    "success": False,
                    "error": f"Tool '{tool_name}' not found on '{server_name}'",
                }
            return {"success": False, "error": f"Internal server '{server_name}' not found"}

        if not self._mcp_manager.has_server(server_name):
            return {"success": False, "error": f"Server '{server_name}' not found"}

        # Use MCP manager for external servers
        try:
            return await self._mcp_manager.get_tool_input_schema(server_name, tool_name)
        except Exception as e:
            raise MCPError(f"Failed to get schema for {tool_name} on {server_name}: {e}") from e
