"""Tool proxy service."""

import logging
from typing import TYPE_CHECKING, Any

from gobby.mcp_proxy.manager import MCPClientManager
from gobby.mcp_proxy.models import MCPError

if TYPE_CHECKING:
    from gobby.mcp_proxy.services.fallback import ToolFallbackResolver
    from gobby.mcp_proxy.services.tool_filter import ToolFilterService
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
        tool_filter: "ToolFilterService | None" = None,
        fallback_resolver: "ToolFallbackResolver | None" = None,
    ):
        self._mcp_manager = mcp_manager
        self._internal_manager = internal_manager
        self._tool_filter = tool_filter
        self._fallback_resolver = fallback_resolver

    async def list_tools(
        self,
        server_name: str,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """
        List tools for a specific server with progressive disclosure format.

        When session_id is provided and a workflow is active, tools are filtered
        based on the current phase's allowed_tools and blocked_tools settings.

        Args:
            server_name: Server name (e.g., "gobby-tasks", "context7")
            session_id: Optional session ID to apply workflow phase filtering

        Returns:
            Dict with tool metadata: {"status": "success", "tools": [...], "tool_count": N}
        """
        # Check internal servers first (gobby-tasks, gobby-memory, etc.)
        if self._internal_manager and self._internal_manager.is_internal(server_name):
            registry = self._internal_manager.get_registry(server_name)
            if registry:
                tools = registry.list_tools()
                # Apply phase filtering if session_id provided
                if session_id and self._tool_filter:
                    tools = self._tool_filter.filter_tools(tools, session_id)
                return {"status": "success", "tools": tools, "tool_count": len(tools)}
            return {
                "status": "error",
                "tools": [],
                "error": f"Internal server '{server_name}' not found",
            }

        # Check external servers
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
            # Apply phase filtering if session_id provided
            if session_id and self._tool_filter:
                brief_tools = self._tool_filter.filter_tools(brief_tools, session_id)
            return {"status": "success", "tools": brief_tools, "tool_count": len(brief_tools)}

        return {
            "status": "error",
            "tools": [],
            "error": f"Server '{server_name}' not found",
        }

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> Any:
        """Execute a tool.

        On error, includes fallback_suggestions if a fallback resolver is configured.
        Returns a dict with {success: False, error: ..., fallback_suggestions: [...]}
        on failure, or the raw tool result on success.
        """
        try:
            # Check internal tools first
            if self._internal_manager and self._internal_manager.is_internal(server_name):
                registry = self._internal_manager.get_registry(server_name)
                if registry:
                    return await registry.call(tool_name, arguments or {})
                raise MCPError(f"Internal server '{server_name}' not found")

            # Use MCP manager for external servers
            return await self._mcp_manager.call_tool(server_name, tool_name, arguments)

        except Exception as e:
            error_message = str(e)
            logger.warning(f"Tool call failed: {server_name}/{tool_name}: {error_message}")

            # Build error response with fallback suggestions
            response: dict[str, Any] = {
                "success": False,
                "error": error_message,
                "server_name": server_name,
                "tool_name": tool_name,
            }

            # Get fallback suggestions if resolver is available
            if self._fallback_resolver:
                try:
                    project_id = self._mcp_manager.project_id
                    if project_id:
                        suggestions = await self._fallback_resolver.find_alternatives_for_error(
                            server_name=server_name,
                            tool_name=tool_name,
                            error_message=error_message,
                            project_id=project_id,
                        )
                        response["fallback_suggestions"] = suggestions
                    else:
                        response["fallback_suggestions"] = []
                except Exception as fallback_error:
                    logger.debug(f"Fallback resolver failed: {fallback_error}")
                    response["fallback_suggestions"] = []
            else:
                response["fallback_suggestions"] = []

            return response

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
