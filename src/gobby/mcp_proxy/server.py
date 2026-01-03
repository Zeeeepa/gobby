"""
Gobby Daemon Tools MCP Server.
"""

import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from gobby.config.app import DaemonConfig
from gobby.mcp_proxy.manager import MCPClientManager
from gobby.mcp_proxy.services.code_execution import CodeExecutionService
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
        skill_learner: Any | None = None,
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
        self.code_execution = CodeExecutionService(llm_service=llm_service, config=config)
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
            "status": "success",
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
        """Call a tool."""
        return await self.tool_proxy.call_tool(server_name, tool_name, arguments)

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

    # --- Code Execution ---

    async def execute_code(
        self,
        code: str,
        language: str = "python",
        context: str | None = None,
        timeout: int = 30,
    ) -> dict[str, Any]:
        """Execute code."""
        return await self.code_execution.execute_code(code, language, context, timeout)

    async def process_large_dataset(
        self, data: Any, operation: str, parameters: dict[str, Any] | None = None, timeout: int = 60
    ) -> dict[str, Any]:
        """Process dataset."""
        return await self.code_execution.process_dataset(data, operation, parameters, timeout)

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


def create_mcp_server(tools_handler: GobbyDaemonTools) -> FastMCP:
    """Create the FastMCP server instance for the HTTP daemon."""
    mcp = FastMCP("gobby")

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

    # Code Execution
    mcp.add_tool(tools_handler.execute_code)
    mcp.add_tool(tools_handler.process_large_dataset)

    # Recommendation
    mcp.add_tool(tools_handler.recommend_tools)

    # Semantic Search
    mcp.add_tool(tools_handler.search_tools)

    return mcp
