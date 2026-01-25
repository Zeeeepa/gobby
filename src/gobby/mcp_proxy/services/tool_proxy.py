"""Tool proxy service."""

import logging
from typing import TYPE_CHECKING, Any

from gobby.mcp_proxy.manager import MCPClientManager
from gobby.mcp_proxy.models import MCPError, ToolProxyErrorCode

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
        validate_arguments: bool = True,
    ):
        self._mcp_manager = mcp_manager
        self._internal_manager = internal_manager
        self._tool_filter = tool_filter
        self._fallback_resolver = fallback_resolver
        self._validate_arguments = validate_arguments

    def _check_arguments(
        self,
        arguments: dict[str, Any],
        schema: dict[str, Any],
    ) -> list[str]:
        """
        Validate arguments against JSON schema.

        Returns list of validation errors, empty if valid.
        """
        errors = []
        properties = schema.get("properties", {})
        required = schema.get("required", [])

        # Check for unknown parameters (likely typos like workflow_name vs name)
        for key in arguments:
            if key not in properties:
                # Find similar parameter names for better error message
                similar = [p for p in properties if p in key or key in p]
                if similar:
                    errors.append(f"Unknown parameter '{key}'. Did you mean '{similar[0]}'?")
                else:
                    valid_params = list(properties.keys())
                    errors.append(f"Unknown parameter '{key}'. Valid parameters: {valid_params}")

        # Check for missing required parameters
        for req in required:
            if req not in arguments:
                errors.append(f"Missing required parameter '{req}'")

        return errors

    def _is_argument_error(self, error_message: str) -> bool:
        """Detect if error message suggests invalid arguments.

        Used to determine whether to include tool schema in error response
        to help the caller self-correct.
        """
        indicators = [
            "parameter",
            "argument",
            "required",
            "missing",
            "invalid",
            "unknown",
            "expected",
            "type error",
            "validation",
            "schema",
            "property",
            "field",
            "400",
            "422",
            "-32602",  # JSON-RPC invalid params error code
        ]
        error_lower = error_message.lower()
        return any(indicator in error_lower for indicator in indicators)

    def _classify_error(self, error_message: str, exception: Exception) -> str:
        """Classify an error into a structured error code.

        Used to provide structured error codes that consumers can rely on
        instead of fragile string matching.

        Args:
            error_message: The error message string
            exception: The original exception

        Returns:
            ToolProxyErrorCode value as string
        """
        error_lower = error_message.lower()

        # Check for server not found/configured errors
        if "server" in error_lower:
            if "not found" in error_lower:
                return ToolProxyErrorCode.SERVER_NOT_FOUND.value
            if "not configured" in error_lower:
                return ToolProxyErrorCode.SERVER_NOT_CONFIGURED.value

        # Check for tool not found
        if "tool" in error_lower and "not found" in error_lower:
            return ToolProxyErrorCode.TOOL_NOT_FOUND.value

        # Check for argument/validation errors
        if self._is_argument_error(error_message):
            return ToolProxyErrorCode.INVALID_ARGUMENTS.value

        # Check for connection errors
        connection_indicators = ["connection", "timeout", "refused", "unreachable", "circuit"]
        if any(ind in error_lower for ind in connection_indicators):
            return ToolProxyErrorCode.CONNECTION_ERROR.value

        # Default to execution error
        return ToolProxyErrorCode.EXECUTION_ERROR.value

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
        """Execute a tool with optional pre-validation.

        Pre-validates arguments against the tool's schema before execution.
        On validation error, returns the schema in the error response so
        the caller can self-correct in one round-trip.

        On execution error, includes fallback_suggestions if a fallback resolver
        is configured.

        """
        args = arguments or {}

        # Pre-validate arguments if enabled
        if self._validate_arguments and args:
            schema_result = await self.get_tool_schema(server_name, tool_name)
            if schema_result.get("success"):
                input_schema = schema_result.get("tool", {}).get("inputSchema", {})
                if input_schema:
                    validation_errors = self._check_arguments(args, input_schema)
                    if validation_errors:
                        return {
                            "success": False,
                            "error": f"Invalid arguments: {validation_errors}",
                            "hint": "Review the schema below and retry with correct parameters",
                            "schema": input_schema,
                            "server_name": server_name,
                            "tool_name": tool_name,
                        }

        try:
            # Check internal tools first
            if self._internal_manager and self._internal_manager.is_internal(server_name):
                registry = self._internal_manager.get_registry(server_name)
                if registry:
                    return await registry.call(tool_name, args)
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
                "error_code": self._classify_error(error_message, e),
                "server_name": server_name,
                "tool_name": tool_name,
            }

            # Enrich with schema if error looks like an argument validation error
            if self._is_argument_error(error_message):
                try:
                    schema_result = await self.get_tool_schema(server_name, tool_name)
                    if schema_result.get("success"):
                        input_schema = schema_result.get("tool", {}).get("inputSchema", {})
                        if input_schema:
                            response["hint"] = (
                                "This appears to be an argument error. "
                                "Schema provided for self-correction."
                            )
                            response["schema"] = input_schema
                except Exception as schema_error:
                    logger.debug(f"Could not fetch schema for error enrichment: {schema_error}")

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
