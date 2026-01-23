"""
Gobby Daemon Tools MCP Server.
"""

import json
import logging
from datetime import UTC
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent

from gobby.config.app import DaemonConfig
from gobby.mcp_proxy.instructions import build_gobby_instructions
from gobby.mcp_proxy.manager import MCPClientManager
from gobby.mcp_proxy.services.recommendation import RecommendationService, SearchMode
from gobby.mcp_proxy.services.server_mgmt import ServerManagementService
from gobby.mcp_proxy.services.system import SystemService
from gobby.mcp_proxy.services.tool_proxy import ToolProxyService

logger = logging.getLogger("gobby.mcp.server")


class GobbyDaemonTools:
    """Handler for Gobby Daemon MCP tools (Refactored to use services)."""

    def __init__(
        self,
        mcp_manager: MCPClientManager,
        daemon_port: int,
        websocket_port: int,
        start_time: float,
        internal_manager: Any,
        config: DaemonConfig | None = None,
        llm_service: Any | None = None,
        session_manager: Any | None = None,
        memory_manager: Any | None = None,
        config_manager: Any | None = None,
        semantic_search: Any | None = None,
        tool_filter: Any | None = None,
        fallback_resolver: Any | None = None,
    ):
        self.config = config
        self.internal_manager = internal_manager
        self._mcp_manager = mcp_manager  # Store for project_id access
        self._semantic_search = semantic_search  # Store for direct search access

        # Initialize services
        self.system_service = SystemService(mcp_manager, daemon_port, websocket_port, start_time)
        self.tool_proxy = ToolProxyService(
            mcp_manager,
            internal_manager=internal_manager,
            tool_filter=tool_filter,
            fallback_resolver=fallback_resolver,
        )
        self.server_mgmt = ServerManagementService(mcp_manager, config_manager, config)
        self.recommendation = RecommendationService(
            llm_service,
            mcp_manager,
            semantic_search=semantic_search,
            project_id=mcp_manager.project_id,
            config=config.recommend_tools if config else None,
        )

    # --- System Tools ---

    async def status(self) -> dict[str, Any]:
        """Get daemon status."""
        return self.system_service.get_status()

    async def list_mcp_servers(self) -> dict[str, Any]:
        """List configured MCP servers."""
        status = self.system_service.get_status()
        servers_info = status.get("mcp_servers", {})

        server_list = []
        for name, info in servers_info.items():
            server_list.append(
                {
                    "name": name,
                    "state": info["state"],
                    "connected": info["state"] == "connected",
                    # Additional fields can be fetched from config if we had access
                }
            )

        return {
            "success": True,
            "servers": server_list,
            "total_count": len(server_list),
            "connected_count": len([s for s in server_list if s["connected"]]),
        }

    # --- Tool Proxying ---

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> Any:
        """Call a tool.

        Returns the tool result, or a CallToolResult with isError=True if the
        underlying service indicates an error. This ensures the MCP protocol
        properly signals errors to LLM clients instead of returning error dicts
        as successful responses.
        """
        result = await self.tool_proxy.call_tool(server_name, tool_name, arguments)

        # Check if result indicates an error (ToolProxyService returns dict with success: False)
        if isinstance(result, dict) and result.get("success") is False:
            # Build helpful error message with schema hint if available
            error_msg = result.get("error", "Unknown error")
            hint = result.get("hint", "")
            schema = result.get("schema")

            parts = [f"Error: {error_msg}"]
            if hint:
                parts.append(f"\n{hint}")
            if schema:
                parts.append(f"\nCorrect schema:\n{json.dumps(schema, indent=2)}")

            # Return MCP error response with isError=True
            return CallToolResult(
                content=[TextContent(type="text", text="\n".join(parts))],
                isError=True,
            )

        return result

    async def list_tools(self, server: str, session_id: str | None = None) -> dict[str, Any]:
        """List tools for a specific server, optionally filtered by workflow phase restrictions."""
        return await self.tool_proxy.list_tools(server, session_id=session_id)

    async def get_tool_schema(self, server_name: str, tool_name: str) -> dict[str, Any]:
        """Get tool schema."""
        return await self.tool_proxy.get_tool_schema(server_name, tool_name)

    async def read_mcp_resource(self, server_name: str, resource_uri: str) -> Any:
        """Read resource."""
        return await self.tool_proxy.read_resource(server_name, resource_uri)

    # --- Server Management ---

    async def add_mcp_server(
        self,
        name: str,
        transport: str,
        url: str | None = None,
        headers: dict[str, str] | None = None,
        command: str | None = None,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        enabled: bool = True,
    ) -> dict[str, Any]:
        """Add server."""
        return await self.server_mgmt.add_server(
            name, transport, url, command, args, env, headers, enabled
        )

    async def remove_mcp_server(self, name: str) -> dict[str, Any]:
        """Remove server."""
        return await self.server_mgmt.remove_server(name)

    async def import_mcp_server(
        self,
        from_project: str | None = None,
        servers: list[str] | None = None,
        github_url: str | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        """Import server."""
        return await self.server_mgmt.import_server(from_project, github_url, query, servers)

    # --- Recommendation ---

    async def recommend_tools(
        self,
        task_description: str,
        agent_id: str | None = None,
        search_mode: SearchMode = "llm",
        top_k: int = 10,
        min_similarity: float = 0.3,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        """Recommend tools for a task.

        Args:
            task_description: What the user wants to accomplish
            agent_id: Optional agent profile for filtering (reserved)
            search_mode: How to search - "llm" (default), "semantic", or "hybrid"
            top_k: Maximum recommendations to return (semantic/hybrid modes)
            min_similarity: Minimum similarity threshold (semantic/hybrid modes)
            project_id: Project ID for semantic/hybrid search

        Returns:
            Dict with tool recommendations
        """
        return await self.recommendation.recommend_tools(
            task_description,
            agent_id=agent_id,
            search_mode=search_mode,
            top_k=top_k,
            min_similarity=min_similarity,
            project_id=project_id,
        )

    # --- Fallback Resolver ---

    async def get_tool_alternatives(
        self,
        server_name: str,
        tool_name: str,
        error_message: str | None = None,
        top_k: int = 5,
    ) -> dict[str, Any]:
        """Get alternative tool suggestions when a tool fails.

        Uses semantic similarity and historical success rates to suggest
        similar tools that might work as alternatives.

        Args:
            server_name: Server where the tool failed
            tool_name: Name of the failed tool
            error_message: Optional error message for context-aware matching
            top_k: Maximum number of alternatives to return (default: 5)

        Returns:
            Dict with alternative tool suggestions and scores
        """
        project_id = self._mcp_manager.project_id
        if not project_id:
            return {
                "success": False,
                "error": "No project_id available. Run 'gobby init' first.",
            }

        fallback_resolver = self.tool_proxy._fallback_resolver
        if not fallback_resolver:
            return {
                "success": False,
                "error": "Fallback resolver not configured",
            }

        try:
            suggestions = await fallback_resolver.find_alternatives_for_error(
                server_name=server_name,
                tool_name=tool_name,
                error_message=error_message or "Tool call failed",
                project_id=project_id,
                top_k=top_k,
            )

            return {
                "success": True,
                "failed_tool": f"{server_name}/{tool_name}",
                "alternatives": suggestions,
                "count": len(suggestions),
            }
        except Exception as e:
            logger.error(f"Failed to get tool alternatives: {e}")
            return {"success": False, "error": str(e)}

    # --- Semantic Search ---

    async def search_tools(
        self,
        query: str,
        top_k: int = 10,
        min_similarity: float = 0.0,
        server: str | None = None,
    ) -> dict[str, Any]:
        """Search for tools using semantic similarity.

        Args:
            query: Natural language query describing the tool you need
            top_k: Maximum number of results to return (default: 10)
            min_similarity: Minimum similarity threshold (default: 0.0)
            server: Optional server name to filter results

        Returns:
            Dict with search results and metadata
        """
        if not self._semantic_search:
            return {
                "success": False,
                "error": "Semantic search not configured",
                "query": query,
            }

        project_id = self._mcp_manager.project_id
        if not project_id:
            return {
                "success": False,
                "error": "No project_id available. Run 'gobby init' first.",
                "query": query,
            }

        try:
            results = await self._semantic_search.search_tools(
                query=query,
                project_id=project_id,
                top_k=top_k,
                min_similarity=min_similarity,
                server_filter=server,
            )

            return {
                "success": True,
                "query": query,
                "results": [r.to_dict() for r in results],
                "total_results": len(results),
            }
        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            return {"success": False, "error": str(e), "query": query}

    # --- Hook Extensions ---

    async def list_hook_handlers(self) -> dict[str, Any]:
        """List registered hook handlers from plugins.

        Returns:
            Dict with handler information organized by event type
        """
        # Access plugin registry via internal_manager if available
        if not self.internal_manager:
            return {
                "success": False,
                "error": "Internal manager not available",
            }

        # Get hook_manager from app state if available (set during HTTP server startup)
        hook_manager = getattr(self.internal_manager, "_hook_manager", None)
        if not hook_manager:
            return {
                "success": True,
                "handlers": {},
                "message": "No hook manager available - plugins not loaded",
            }

        plugin_loader = getattr(hook_manager, "plugin_loader", None)
        if not plugin_loader:
            return {
                "success": True,
                "handlers": {},
                "message": "Plugin system not initialized",
            }

        # Get handlers organized by event type
        from gobby.hooks.events import HookEventType

        handlers_by_event: dict[str, list[dict[str, Any]]] = {}

        for event_type in HookEventType:
            handlers = plugin_loader.registry.get_handlers(event_type)
            if handlers:
                handlers_by_event[event_type.value] = [
                    {
                        "plugin": h.plugin.name,
                        "method": h.method.__name__,
                        "priority": h.priority,
                        "is_pre_handler": h.priority < 50,
                    }
                    for h in handlers
                ]

        return {
            "success": True,
            "handlers": handlers_by_event,
            "total_handlers": sum(len(h) for h in handlers_by_event.values()),
        }

    async def test_hook_event(
        self,
        event_type: str,
        source: str = "claude",
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Test a hook event by sending it through the hook system.

        Args:
            event_type: Hook event type (e.g., "session_start", "before_tool")
            source: Source CLI to simulate (claude, gemini, codex)
            data: Optional additional data for the event

        Returns:
            Hook execution result
        """
        if not self.internal_manager:
            return {
                "success": False,
                "error": "Internal manager not available",
            }

        hook_manager = getattr(self.internal_manager, "_hook_manager", None)
        if not hook_manager:
            return {
                "success": False,
                "error": "No hook manager available",
            }

        # Build test event
        from datetime import datetime

        from gobby.hooks.events import HookEvent, HookEventType, SessionSource

        try:
            hook_event_type = HookEventType(event_type)
        except ValueError:
            return {
                "success": False,
                "error": f"Invalid event type: {event_type}",
                "valid_types": [e.value for e in HookEventType],
            }

        # Map source string to SessionSource enum
        try:
            session_source = SessionSource(source)
        except ValueError:
            session_source = SessionSource.CLAUDE  # Default to Claude

        test_data = {
            "session_id": "test-mcp-event",
            "source": source,
            **(data or {}),
        }

        event = HookEvent(
            event_type=hook_event_type,
            session_id="test-mcp-event",
            source=session_source,
            timestamp=datetime.now(UTC),
            data=test_data,
        )

        # Process through hook manager
        try:
            result = hook_manager.process_event(event)
            return {
                "success": True,
                "event_type": event_type,
                "continue": result.get("continue", True),
                "reason": result.get("reason"),
                "inject_context": result.get("inject_context"),
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    async def list_plugins(self) -> dict[str, Any]:
        """List loaded Python plugins.

        Returns:
            Dict with plugin information
        """
        if not self.internal_manager:
            return {
                "success": False,
                "error": "Internal manager not available",
            }

        hook_manager = getattr(self.internal_manager, "_hook_manager", None)
        if not hook_manager:
            return {
                "success": True,
                "enabled": False,
                "plugins": [],
                "message": "Plugin system not initialized",
            }

        plugin_loader = getattr(hook_manager, "plugin_loader", None)
        if not plugin_loader:
            return {
                "success": True,
                "enabled": False,
                "plugins": [],
                "message": "No plugin loader available",
            }

        plugins = plugin_loader.registry.list_plugins()

        return {
            "success": True,
            "enabled": plugin_loader.config.enabled,
            "plugins": plugins,
            "plugin_dirs": plugin_loader.config.plugin_dirs,
        }

    async def reload_plugin(self, name: str) -> dict[str, Any]:
        """Reload a plugin by name.

        Args:
            name: Plugin name to reload

        Returns:
            Reload result
        """
        if not self.internal_manager:
            return {
                "success": False,
                "error": "Internal manager not available",
            }

        hook_manager = getattr(self.internal_manager, "_hook_manager", None)
        if not hook_manager:
            return {
                "success": False,
                "error": "Plugin system not initialized",
            }

        plugin_loader = getattr(hook_manager, "plugin_loader", None)
        if not plugin_loader:
            return {
                "success": False,
                "error": "No plugin loader available",
            }

        try:
            plugin = plugin_loader.reload_plugin(name)
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
            return {
                "success": False,
                "error": str(e),
            }


def create_mcp_server(tools_handler: GobbyDaemonTools) -> FastMCP:
    """Create the FastMCP server instance for the HTTP daemon."""
    mcp = FastMCP("gobby", instructions=build_gobby_instructions())

    # System tools
    mcp.add_tool(tools_handler.status)
    mcp.add_tool(tools_handler.list_mcp_servers)

    # Tool Proxy
    mcp.add_tool(tools_handler.call_tool)
    mcp.add_tool(tools_handler.list_tools)
    mcp.add_tool(tools_handler.get_tool_schema)
    # read_mcp_resource is a tool that proxies resource reading
    mcp.add_tool(tools_handler.read_mcp_resource)

    # Server Management
    mcp.add_tool(tools_handler.add_mcp_server)
    mcp.add_tool(tools_handler.remove_mcp_server)
    mcp.add_tool(tools_handler.import_mcp_server)

    # Recommendation
    mcp.add_tool(tools_handler.recommend_tools)

    # Fallback Resolver
    mcp.add_tool(tools_handler.get_tool_alternatives)

    # Semantic Search
    mcp.add_tool(tools_handler.search_tools)

    # Hook Extensions
    mcp.add_tool(tools_handler.list_hook_handlers)
    mcp.add_tool(tools_handler.test_hook_event)
    mcp.add_tool(tools_handler.list_plugins)
    mcp.add_tool(tools_handler.reload_plugin)

    return mcp
