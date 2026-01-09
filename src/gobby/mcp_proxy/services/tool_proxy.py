"""Tool proxy service."""

import logging
from typing import TYPE_CHECKING, Any

from gobby.mcp_proxy.manager import MCPClientManager
from gobby.mcp_proxy.models import MCPError

if TYPE_CHECKING:
    from gobby.mcp_proxy.services.fallback import ToolFallbackResolver
    from gobby.mcp_proxy.services.response_transformer import ResponseTransformerService
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
        response_transformer: "ResponseTransformerService | None" = None,
    ):
        self._mcp_manager = mcp_manager
        self._internal_manager = internal_manager
        self._tool_filter = tool_filter
        self._fallback_resolver = fallback_resolver
        self._response_transformer = response_transformer

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
            Dict with tool metadata: {"success": true, "tools": [...], "tool_count": N}
        """
        # Check internal servers first (gobby-tasks, gobby-memory, etc.)
        if self._internal_manager and self._internal_manager.is_internal(server_name):
            registry = self._internal_manager.get_registry(server_name)
            if registry:
                tools = registry.list_tools()
                # Apply phase filtering if session_id provided
                if session_id and self._tool_filter:
                    tools = self._tool_filter.filter_tools(tools, session_id)
                return {"success": True, "tools": tools, "tool_count": len(tools)}
            return {
                "success": False,
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
            return {"success": True, "tools": brief_tools, "tool_count": len(brief_tools)}

        return {
            "success": False,
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

        If a response_transformer is configured, large string fields in the response
        will be compressed using LLMLingua.
        """
        try:
            # Check internal tools first
            if self._internal_manager and self._internal_manager.is_internal(server_name):
                registry = self._internal_manager.get_registry(server_name)
                if registry:
                    result = await registry.call(tool_name, arguments or {})
                    # Apply response transformation if configured
                    if self._response_transformer:
                        result = self._response_transformer.transform_response(result)
                    return result
                raise MCPError(f"Internal server '{server_name}' not found")

            # Use MCP manager for external servers
            result = await self._mcp_manager.call_tool(server_name, tool_name, arguments)
            # Apply response transformation if configured
            if self._response_transformer:
                result = self._response_transformer.transform_response(result)
            return result

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
                    return {"success": True, "tool": schema}
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

    def find_tool_server(self, tool_name: str) -> str | None:
        """
        Find which server owns a tool by searching all available servers.

        Searches internal registries first (faster), then external server configs.

        Args:
            tool_name: Name of the tool to find

        Returns:
            Server name if found, None otherwise
        """
        # Search internal registries first (fast, in-memory lookup)
        if self._internal_manager:
            server = self._internal_manager.find_tool_server(tool_name)
            if server:
                return server

        # Search external server configs (cached tool metadata)
        for server_name, config in self._mcp_manager._configs.items():
            if config.tools:
                for tool in config.tools:
                    tool_name_in_config = (
                        tool.get("name") if isinstance(tool, dict) else getattr(tool, "name", None)
                    )
                    if tool_name_in_config == tool_name:
                        return server_name

        return None

    async def call_tool_by_name(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> Any:
        """
        Call a tool by name, automatically resolving the server.

        Searches all available servers to find which one owns the tool,
        then routes the call appropriately.

        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments

        Returns:
            Tool execution result, or error dict if tool not found
        """
        server_name = self.find_tool_server(tool_name)

        if server_name is None:
            logger.warning(f"Tool '{tool_name}' not found on any server")
            return {
                "success": False,
                "error": f"Tool '{tool_name}' not found on any available server",
                "tool_name": tool_name,
            }

        logger.debug(f"Routing tool '{tool_name}' to server '{server_name}'")
        return await self.call_tool(server_name, tool_name, arguments)
