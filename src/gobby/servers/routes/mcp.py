"""
MCP routes for Gobby HTTP server.

Provides MCP server management, tool discovery, and tool execution endpoints.
Uses FastAPI dependency injection via Depends() for proper testability.
"""

import json
import logging
import time
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, Request

from gobby.mcp_proxy.services.code_execution import CodeExecutionService
from gobby.servers.routes.dependencies import (
    get_internal_manager,
    get_mcp_manager,
    get_metrics_manager,
    get_server,
)
from gobby.utils.metrics import get_metrics_collector

if TYPE_CHECKING:
    from gobby.mcp_proxy.manager import MCPClientManager
    from gobby.mcp_proxy.metrics import ToolMetricsManager
    from gobby.mcp_proxy.registry_manager import InternalToolRegistryManager
    from gobby.servers.http import HTTPServer

logger = logging.getLogger(__name__)


def create_mcp_router() -> APIRouter:
    """
    Create MCP router with endpoints using dependency injection.

    Returns:
        Configured APIRouter with MCP endpoints
    """
    router = APIRouter(prefix="/mcp", tags=["mcp"])
    metrics = get_metrics_collector()

    @router.get("/{server_name}/tools")
    async def list_mcp_tools(
        server_name: str,
        internal_manager: "InternalToolRegistryManager | None" = Depends(get_internal_manager),
        mcp_manager: "MCPClientManager | None" = Depends(get_mcp_manager),
    ) -> dict[str, Any]:
        """
        List available tools from an MCP server.

        Args:
            server_name: Name of the MCP server (e.g., "supabase", "context7")
            internal_manager: Internal tool registry manager (injected)
            mcp_manager: External MCP client manager (injected)

        Returns:
            List of available tools with their descriptions
        """
        start_time = time.perf_counter()
        metrics.inc_counter("http_requests_total")

        try:
            # Check internal registries first (gobby-tasks, gobby-memory, etc.)
            if internal_manager and internal_manager.is_internal(server_name):
                registry = internal_manager.get_registry(server_name)
                if registry:
                    tools = registry.list_tools()
                    response_time_ms = (time.perf_counter() - start_time) * 1000
                    metrics.observe_histogram("list_mcp_tools", response_time_ms / 1000)
                    return {
                        "status": "success",
                        "tools": tools,
                        "tool_count": len(tools),
                        "response_time_ms": response_time_ms,
                    }
                raise HTTPException(
                    status_code=404, detail=f"Internal server '{server_name}' not found"
                )

            if mcp_manager is None:
                raise HTTPException(status_code=503, detail="MCP manager not available")

            # Check if server is configured
            if not mcp_manager.has_server(server_name):
                raise HTTPException(status_code=404, detail=f"Unknown MCP server: '{server_name}'")

            # Use ensure_connected for lazy loading - connects on-demand if not connected
            try:
                session = await mcp_manager.ensure_connected(server_name)
            except KeyError as e:
                raise HTTPException(status_code=404, detail=str(e)) from e
            except Exception as e:
                raise HTTPException(
                    status_code=503,
                    detail=f"MCP server '{server_name}' connection failed: {e}",
                ) from e

            # List tools using MCP SDK
            try:
                tools_result = await session.list_tools()
                tools = []
                for tool in tools_result.tools:
                    tool_dict: dict[str, Any] = {
                        "name": tool.name,
                        "description": tool.description if hasattr(tool, "description") else None,
                    }

                    # Handle inputSchema
                    if hasattr(tool, "inputSchema"):
                        schema = tool.inputSchema
                        if hasattr(schema, "model_dump"):
                            tool_dict["inputSchema"] = schema.model_dump()
                        elif isinstance(schema, dict):
                            tool_dict["inputSchema"] = schema
                        else:
                            tool_dict["inputSchema"] = None
                    else:
                        tool_dict["inputSchema"] = None

                    tools.append(tool_dict)

                response_time_ms = (time.perf_counter() - start_time) * 1000

                logger.debug(
                    f"Listed {len(tools)} tools from {server_name}",
                    extra={
                        "server": server_name,
                        "tool_count": len(tools),
                        "response_time_ms": response_time_ms,
                    },
                )

                return {
                    "status": "success",
                    "tools": tools,
                    "tool_count": len(tools),
                    "response_time_ms": response_time_ms,
                }

            except Exception as e:
                logger.error(
                    f"Failed to list tools from {server_name}: {e}",
                    exc_info=True,
                    extra={"server": server_name},
                )
                raise HTTPException(status_code=500, detail=f"Failed to list tools: {e}") from e

        except HTTPException:
            raise
        except Exception as e:
            metrics.inc_counter("http_requests_errors_total")
            logger.error(f"MCP list tools error: {server_name}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.get("/servers")
    async def list_mcp_servers(
        internal_manager: "InternalToolRegistryManager | None" = Depends(get_internal_manager),
        mcp_manager: "MCPClientManager | None" = Depends(get_mcp_manager),
    ) -> dict[str, Any]:
        """
        List all configured MCP servers.

        Args:
            internal_manager: Internal tool registry manager (injected)
            mcp_manager: External MCP client manager (injected)

        Returns:
            List of servers with connection status
        """
        start_time = time.perf_counter()
        metrics.inc_counter("http_requests_total")

        try:
            server_list = []

            # Add internal servers (gobby-tasks, gobby-memory, etc.)
            if internal_manager:
                for registry in internal_manager.get_all_registries():
                    server_list.append(
                        {
                            "name": registry.name,
                            "state": "connected",
                            "connected": True,
                            "transport": "internal",
                        }
                    )

            # Add external MCP servers
            if mcp_manager:
                for config in mcp_manager.server_configs:
                    health = mcp_manager.health.get(config.name)
                    is_connected = config.name in mcp_manager.connections
                    server_list.append(
                        {
                            "name": config.name,
                            "state": health.state.value if health else "unknown",
                            "connected": is_connected,
                            "transport": config.transport,
                            "enabled": config.enabled,
                        }
                    )

            response_time_ms = (time.perf_counter() - start_time) * 1000

            return {
                "servers": server_list,
                "total_count": len(server_list),
                "connected_count": len([s for s in server_list if s.get("connected")]),
                "response_time_ms": response_time_ms,
            }

        except Exception as e:
            metrics.inc_counter("http_requests_errors_total")
            logger.error(f"List MCP servers error: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.get("/tools")
    async def list_all_mcp_tools(
        server_filter: str | None = None,
        include_metrics: bool = False,
        project_id: str | None = None,
        server: "HTTPServer" = Depends(get_server),
        metrics_manager: "ToolMetricsManager | None" = Depends(get_metrics_manager),
    ) -> dict[str, Any]:
        """
        List tools from MCP servers.

        Args:
            server_filter: Optional server name to filter by
            include_metrics: When True, include call_count, success_rate, avg_latency for each tool
            project_id: Project ID for metrics lookup (uses current project if not specified)

        Returns:
            Dict of server names to tool lists
        """
        start_time = time.perf_counter()
        metrics.inc_counter("http_requests_total")

        try:
            tools_by_server: dict[str, list[dict[str, Any]]] = {}

            # Resolve project_id for metrics lookup
            resolved_project_id = None
            if include_metrics:
                try:
                    resolved_project_id = server._resolve_project_id(project_id, cwd=None)
                except ValueError:
                    # Project not initialized; skip metrics enrichment
                    resolved_project_id = None

            # If specific server requested
            if server_filter:
                # Check internal first
                if server._internal_manager and server._internal_manager.is_internal(server_filter):
                    registry = server._internal_manager.get_registry(server_filter)
                    if registry:
                        tools_by_server[server_filter] = registry.list_tools()
                elif server.mcp_manager and server.mcp_manager.has_server(server_filter):
                    # Check if server is enabled before attempting connection
                    server_config = server.mcp_manager._configs.get(server_filter)
                    if server_config and not server_config.enabled:
                        tools_by_server[server_filter] = []
                    else:
                        try:
                            # Use ensure_connected for lazy loading
                            session = await server.mcp_manager.ensure_connected(server_filter)
                            tools_result = await session.list_tools()
                            tools_list = []
                            for t in tools_result.tools:
                                desc = getattr(t, "description", "") or ""
                                tools_list.append(
                                    {
                                        "name": t.name,
                                        "brief": desc[:100],
                                    }
                                )
                            tools_by_server[server_filter] = tools_list
                        except Exception as e:
                            logger.warning(f"Failed to list tools from {server_filter}: {e}")
                            tools_by_server[server_filter] = []
            else:
                # Get tools from all servers
                # Internal servers
                if server._internal_manager:
                    for registry in server._internal_manager.get_all_registries():
                        tools_by_server[registry.name] = registry.list_tools()

                # External MCP servers - use ensure_connected for lazy loading
                if server.mcp_manager:
                    for config in server.mcp_manager.server_configs:
                        if config.enabled:
                            try:
                                session = await server.mcp_manager.ensure_connected(config.name)
                                tools_result = await session.list_tools()
                                tools_list = []
                                for t in tools_result.tools:
                                    desc = getattr(t, "description", "") or ""
                                    tools_list.append(
                                        {
                                            "name": t.name,
                                            "brief": desc[:100],
                                        }
                                    )
                                tools_by_server[config.name] = tools_list
                            except Exception as e:
                                logger.warning(f"Failed to list tools from {config.name}: {e}")
                                tools_by_server[config.name] = []

            # Enrich with metrics if requested
            if include_metrics and metrics_manager and resolved_project_id:
                # Get all metrics for this project
                metrics_data = metrics_manager.get_metrics(project_id=resolved_project_id)
                metrics_by_key = {
                    (m["server_name"], m["tool_name"]): m for m in metrics_data.get("tools", [])
                }

                for server_name, tools_list in tools_by_server.items():
                    for tool in tools_list:
                        # Guard against non-dict or missing-name entries
                        if not isinstance(tool, dict) or "name" not in tool:
                            continue
                        tool_name = tool.get("name")
                        key = (server_name, tool_name)
                        if key in metrics_by_key:
                            m = metrics_by_key[key]
                            tool["call_count"] = m.get("call_count", 0)
                            tool["success_rate"] = m.get("success_rate")
                            tool["avg_latency_ms"] = m.get("avg_latency_ms")
                        else:
                            tool["call_count"] = 0
                            tool["success_rate"] = None
                            tool["avg_latency_ms"] = None

            response_time_ms = (time.perf_counter() - start_time) * 1000

            return {
                "tools": tools_by_server,
                "response_time_ms": response_time_ms,
            }

        except Exception as e:
            metrics.inc_counter("http_requests_errors_total")
            logger.error(f"List MCP tools error: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.post("/tools/schema")
    async def get_tool_schema(
        request: Request,
        server: "HTTPServer" = Depends(get_server),
    ) -> dict[str, Any]:
        """
        Get full schema for a specific tool.

        Request body:
            {
                "server_name": "supabase",
                "tool_name": "list_tables"
            }

        Returns:
            Tool schema with inputSchema
        """
        start_time = time.perf_counter()
        metrics.inc_counter("http_requests_total")

        try:
            body = await request.json()
            server_name = body.get("server_name")
            tool_name = body.get("tool_name")

            if not server_name or not tool_name:
                raise HTTPException(
                    status_code=400, detail="Required fields: server_name, tool_name"
                )

            # Check internal first
            if server._internal_manager and server._internal_manager.is_internal(server_name):
                registry = server._internal_manager.get_registry(server_name)
                if registry:
                    schema = registry.get_schema(tool_name)
                    if schema:
                        response_time_ms = (time.perf_counter() - start_time) * 1000
                        return {
                            "name": tool_name,
                            "server": server_name,
                            "inputSchema": schema,
                            "response_time_ms": response_time_ms,
                        }
                    raise HTTPException(
                        status_code=404,
                        detail=f"Tool '{tool_name}' not found on server '{server_name}'",
                    )

            if server.mcp_manager is None:
                raise HTTPException(status_code=503, detail="MCP manager not available")

            # Get from external MCP server
            try:
                schema = await server.mcp_manager.get_tool_input_schema(server_name, tool_name)
                response_time_ms = (time.perf_counter() - start_time) * 1000

                return {
                    "name": tool_name,
                    "server": server_name,
                    "inputSchema": schema,
                    "response_time_ms": response_time_ms,
                }

            except Exception as e:
                raise HTTPException(status_code=404, detail=str(e)) from e

        except HTTPException:
            raise
        except Exception as e:
            metrics.inc_counter("http_requests_errors_total")
            logger.error(f"Get tool schema error: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.post("/tools/call")
    async def call_mcp_tool(
        request: Request,
        server: "HTTPServer" = Depends(get_server),
    ) -> dict[str, Any]:
        """
        Call an MCP tool.

        Request body:
            {
                "server_name": "supabase",
                "tool_name": "list_tables",
                "arguments": {}
            }

        Returns:
            Tool execution result
        """
        start_time = time.perf_counter()
        metrics.inc_counter("http_requests_total")
        metrics.inc_counter("mcp_tool_calls_total")

        try:
            body = await request.json()
            server_name = body.get("server_name")
            tool_name = body.get("tool_name")
            arguments = body.get("arguments", {})

            if not server_name or not tool_name:
                raise HTTPException(
                    status_code=400, detail="Required fields: server_name, tool_name"
                )

            # Check internal first
            if server._internal_manager and server._internal_manager.is_internal(server_name):
                registry = server._internal_manager.get_registry(server_name)
                if registry:
                    try:
                        result = await registry.call(tool_name, arguments or {})
                        response_time_ms = (time.perf_counter() - start_time) * 1000
                        metrics.inc_counter("mcp_tool_calls_succeeded_total")
                        return {
                            "success": True,
                            "result": result,
                            "response_time_ms": response_time_ms,
                        }
                    except Exception as e:
                        metrics.inc_counter("mcp_tool_calls_failed_total")
                        error_msg = str(e) or f"{type(e).__name__}: (no message)"
                        raise HTTPException(
                            status_code=500,
                            detail={"success": False, "error": error_msg},
                        ) from e

            if server.mcp_manager is None:
                raise HTTPException(status_code=503, detail="MCP manager not available")

            # Call external MCP tool
            try:
                result = await server.mcp_manager.call_tool(server_name, tool_name, arguments)
                response_time_ms = (time.perf_counter() - start_time) * 1000
                metrics.inc_counter("mcp_tool_calls_succeeded_total")

                return {
                    "success": True,
                    "result": result,
                    "response_time_ms": response_time_ms,
                }

            except Exception as e:
                metrics.inc_counter("mcp_tool_calls_failed_total")
                error_msg = str(e) or f"{type(e).__name__}: (no message)"
                raise HTTPException(status_code=500, detail=error_msg) from e

        except HTTPException:
            raise
        except Exception as e:
            metrics.inc_counter("mcp_tool_calls_failed_total")
            error_msg = str(e) or f"{type(e).__name__}: (no message)"
            logger.error(f"Call MCP tool error: {error_msg}", exc_info=True)
            raise HTTPException(status_code=500, detail=error_msg) from e

    @router.post("/servers")
    async def add_mcp_server(
        request: Request,
        server: "HTTPServer" = Depends(get_server),
    ) -> dict[str, Any]:
        """
        Add a new MCP server configuration.

        Request body:
            {
                "name": "my-server",
                "transport": "http",
                "url": "https://...",
                "enabled": true
            }

        Returns:
            Success status
        """
        metrics.inc_counter("http_requests_total")

        try:
            body = await request.json()
            name = body.get("name")
            transport = body.get("transport")

            if not name or not transport:
                raise HTTPException(status_code=400, detail="Required fields: name, transport")

            # Import here to avoid circular imports
            from gobby.mcp_proxy.models import MCPServerConfig
            from gobby.utils.project_context import get_project_context

            project_ctx = get_project_context()
            if not project_ctx or not project_ctx.get("id"):
                raise HTTPException(
                    status_code=400, detail="No current project found. Run 'gobby init'."
                )
            project_id = project_ctx["id"]

            config = MCPServerConfig(
                name=name,
                project_id=project_id,
                transport=transport,
                url=body.get("url"),
                command=body.get("command"),
                args=body.get("args"),
                env=body.get("env"),
                headers=body.get("headers"),
                enabled=body.get("enabled", True),
            )

            if server.mcp_manager is None:
                raise HTTPException(status_code=503, detail="MCP manager not available")

            await server.mcp_manager.add_server(config)

            return {
                "success": True,
                "message": f"Added MCP server: {name}",
            }

        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except HTTPException:
            raise
        except Exception as e:
            metrics.inc_counter("http_requests_errors_total")
            logger.error(f"Add MCP server error: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.post("/servers/import")
    async def import_mcp_server(
        request: Request,
        server: "HTTPServer" = Depends(get_server),
    ) -> dict[str, Any]:
        """
        Import MCP server(s) from various sources.

        Request body:
            {
                "from_project": "other-project",  # Import from project
                "github_url": "https://...",      # Import from GitHub
                "query": "supabase mcp",          # Search and import
                "servers": ["name1", "name2"]     # Specific servers to import
            }

        Returns:
            Import result with imported/skipped/failed lists
        """
        metrics.inc_counter("http_requests_total")

        try:
            body = await request.json()
            from_project = body.get("from_project")
            github_url = body.get("github_url")
            query = body.get("query")
            servers = body.get("servers")

            if not from_project and not github_url and not query:
                raise HTTPException(
                    status_code=400,
                    detail="Specify at least one: from_project, github_url, or query",
                )

            # Get current project ID from context
            from gobby.utils.project_context import get_project_context

            project_ctx = get_project_context()
            if not project_ctx or not project_ctx.get("id"):
                raise HTTPException(
                    status_code=400, detail="No current project. Run 'gobby init' first."
                )
            current_project_id = project_ctx["id"]

            if not server.config:
                raise HTTPException(status_code=500, detail="Daemon configuration not available")

            # Create importer
            from gobby.mcp_proxy.importer import MCPServerImporter
            from gobby.storage.database import LocalDatabase

            db = LocalDatabase()
            importer = MCPServerImporter(
                config=server.config,
                db=db,
                current_project_id=current_project_id,
                mcp_client_manager=server.mcp_manager,
            )

            # Execute import based on source
            if from_project:
                result = await importer.import_from_project(
                    source_project=from_project,
                    servers=servers,
                )
            elif github_url:
                result = await importer.import_from_github(github_url)
            elif query:
                result = await importer.import_from_query(query)
            else:
                result = {"success": False, "error": "No import source specified"}

            return result

        except HTTPException:
            raise
        except Exception as e:
            metrics.inc_counter("http_requests_errors_total")
            logger.error(f"Import MCP server error: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.delete("/servers/{name}")
    async def remove_mcp_server(
        name: str,
        server: "HTTPServer" = Depends(get_server),
    ) -> dict[str, Any]:
        """
        Remove an MCP server configuration.

        Args:
            name: Server name to remove

        Returns:
            Success status
        """
        metrics.inc_counter("http_requests_total")

        try:
            if server.mcp_manager is None:
                raise HTTPException(status_code=503, detail="MCP manager not available")

            await server.mcp_manager.remove_server(name)

            return {
                "success": True,
                "message": f"Removed MCP server: {name}",
            }

        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except Exception as e:
            metrics.inc_counter("http_requests_errors_total")
            logger.error(f"Remove MCP server error: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.post("/tools/recommend")
    async def recommend_mcp_tools(
        request: Request,
        server: "HTTPServer" = Depends(get_server),
    ) -> dict[str, Any]:
        """
        Get AI-powered tool recommendations for a task.

        Request body:
            {
                "task_description": "I need to query a database",
                "agent_id": "optional-agent-id",
                "search_mode": "llm" | "semantic" | "hybrid",
                "top_k": 10,
                "min_similarity": 0.3,
                "cwd": "/path/to/project"
            }

        Returns:
            List of tool recommendations
        """
        start_time = time.perf_counter()
        metrics.inc_counter("http_requests_total")

        try:
            body = await request.json()
            task_description = body.get("task_description")
            agent_id = body.get("agent_id")
            search_mode = body.get("search_mode", "llm")
            top_k = body.get("top_k", 10)
            min_similarity = body.get("min_similarity", 0.3)
            cwd = body.get("cwd")

            if not task_description:
                raise HTTPException(status_code=400, detail="Required field: task_description")

            # For semantic/hybrid modes, resolve project_id from cwd
            project_id = None
            if search_mode in ("semantic", "hybrid"):
                try:
                    project_id = server._resolve_project_id(None, cwd)
                except ValueError as e:
                    return {
                        "success": False,
                        "error": str(e),
                        "task": task_description,
                        "response_time_ms": (time.perf_counter() - start_time) * 1000,
                    }

            # Use tools handler if available
            if server._tools_handler:
                result = await server._tools_handler.recommend_tools(
                    task_description=task_description,
                    agent_id=agent_id,
                    search_mode=search_mode,
                    top_k=top_k,
                    min_similarity=min_similarity,
                    project_id=project_id,
                )
                response_time_ms = (time.perf_counter() - start_time) * 1000
                result["response_time_ms"] = response_time_ms
                return result

            # Fallback: no tools handler
            return {
                "success": False,
                "error": "Tools handler not initialized",
                "recommendations": [],
                "response_time_ms": (time.perf_counter() - start_time) * 1000,
            }

        except HTTPException:
            raise
        except Exception as e:
            metrics.inc_counter("http_requests_errors_total")
            logger.error(f"Recommend tools error: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.post("/tools/search")
    async def search_mcp_tools(
        request: Request,
        server: "HTTPServer" = Depends(get_server),
    ) -> dict[str, Any]:
        """
        Search for tools using semantic similarity.

        Request body:
            {
                "query": "create a file",
                "top_k": 10,
                "min_similarity": 0.0,
                "server": "optional-server-filter",
                "cwd": "/path/to/project"
            }

        Returns:
            List of matching tools with similarity scores
        """
        start_time = time.perf_counter()
        metrics.inc_counter("http_requests_total")

        try:
            body = await request.json()
            query = body.get("query")
            top_k = body.get("top_k", 10)
            min_similarity = body.get("min_similarity", 0.0)
            server_filter = body.get("server")
            cwd = body.get("cwd")

            if not query:
                raise HTTPException(status_code=400, detail="Required field: query")

            # Resolve project_id from cwd
            try:
                project_id = server._resolve_project_id(None, cwd)
            except ValueError as e:
                return {
                    "success": False,
                    "error": str(e),
                    "query": query,
                    "response_time_ms": (time.perf_counter() - start_time) * 1000,
                }

            # Use semantic search directly if available
            if server._tools_handler and server._tools_handler._semantic_search:
                try:
                    semantic_search = server._tools_handler._semantic_search

                    # Auto-generate embeddings if none exist
                    existing = semantic_search.get_embeddings_for_project(project_id)
                    if not existing and server._mcp_db_manager:
                        logger.info(f"No embeddings for project {project_id}, generating...")
                        await semantic_search.embed_all_tools(
                            project_id=project_id,
                            mcp_manager=server._mcp_db_manager,
                            force=False,
                        )

                    results = await semantic_search.search_tools(
                        query=query,
                        project_id=project_id,
                        top_k=top_k,
                        min_similarity=min_similarity,
                        server_filter=server_filter,
                    )
                    response_time_ms = (time.perf_counter() - start_time) * 1000
                    return {
                        "success": True,
                        "query": query,
                        "results": [r.to_dict() for r in results],
                        "total_results": len(results),
                        "response_time_ms": response_time_ms,
                    }
                except Exception as e:
                    logger.error(f"Semantic search failed: {e}")
                    return {
                        "success": False,
                        "error": str(e),
                        "query": query,
                        "response_time_ms": (time.perf_counter() - start_time) * 1000,
                    }

            # Fallback: no semantic search
            return {
                "success": False,
                "error": "Semantic search not configured",
                "results": [],
                "response_time_ms": (time.perf_counter() - start_time) * 1000,
            }

        except HTTPException:
            raise
        except Exception as e:
            metrics.inc_counter("http_requests_errors_total")
            logger.error(f"Search tools error: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.post("/tools/embed")
    async def embed_mcp_tools(
        request: Request,
        server: "HTTPServer" = Depends(get_server),
    ) -> dict[str, Any]:
        """
        Generate embeddings for all tools in a project.

        Request body:
            {
                "cwd": "/path/to/project",
                "force": false
            }

        Returns:
            Embedding generation stats
        """
        start_time = time.perf_counter()
        metrics.inc_counter("http_requests_total")

        try:
            body = await request.json()
            cwd = body.get("cwd")
            force = body.get("force", False)

            # Resolve project_id from cwd
            try:
                project_id = server._resolve_project_id(None, cwd)
            except ValueError as e:
                return {
                    "success": False,
                    "error": str(e),
                    "response_time_ms": (time.perf_counter() - start_time) * 1000,
                }

            # Use semantic search to embed all tools
            if server._tools_handler and server._tools_handler._semantic_search:
                try:
                    stats = await server._tools_handler._semantic_search.embed_all_tools(
                        project_id=project_id,
                        mcp_manager=server._mcp_db_manager,
                        force=force,
                    )
                    response_time_ms = (time.perf_counter() - start_time) * 1000
                    return {
                        "success": True,
                        "stats": stats,
                        "response_time_ms": response_time_ms,
                    }
                except Exception as e:
                    logger.error(f"Embedding generation failed: {e}")
                    return {
                        "success": False,
                        "error": str(e),
                        "response_time_ms": (time.perf_counter() - start_time) * 1000,
                    }

            return {
                "success": False,
                "error": "Semantic search not configured",
                "response_time_ms": (time.perf_counter() - start_time) * 1000,
            }

        except HTTPException:
            raise
        except Exception as e:
            metrics.inc_counter("http_requests_errors_total")
            logger.error(f"Embed tools error: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.get("/status")
    async def get_mcp_status(
        server: "HTTPServer" = Depends(get_server),
    ) -> dict[str, Any]:
        """
        Get MCP proxy status and health.

        Returns:
            Status summary with server counts and health info
        """
        start_time = time.perf_counter()
        metrics.inc_counter("http_requests_total")

        try:
            total_servers = 0
            connected_servers = 0
            cached_tools = 0
            server_health: dict[str, dict[str, Any]] = {}

            # Count internal servers
            if server._internal_manager:
                for registry in server._internal_manager.get_all_registries():
                    total_servers += 1
                    connected_servers += 1
                    cached_tools += len(registry.list_tools())
                    server_health[registry.name] = {
                        "state": "connected",
                        "health": "healthy",
                        "failures": 0,
                    }

            # Count external servers
            if server.mcp_manager:
                for config in server.mcp_manager.server_configs:
                    total_servers += 1
                    health = server.mcp_manager.health.get(config.name)
                    is_connected = config.name in server.mcp_manager.connections
                    if is_connected:
                        connected_servers += 1

                    server_health[config.name] = {
                        "state": health.state.value if health else "unknown",
                        "health": health.health.value if health else "unknown",
                        "failures": health.consecutive_failures if health else 0,
                    }

            response_time_ms = (time.perf_counter() - start_time) * 1000

            return {
                "total_servers": total_servers,
                "connected_servers": connected_servers,
                "cached_tools": cached_tools,
                "server_health": server_health,
                "response_time_ms": response_time_ms,
            }

        except Exception as e:
            metrics.inc_counter("http_requests_errors_total")
            logger.error(f"Get MCP status error: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.post("/{server_name}/tools/{tool_name}")
    async def mcp_proxy(
        server_name: str,
        tool_name: str,
        request: Request,
        server: "HTTPServer" = Depends(get_server),
    ) -> dict[str, Any]:
        """
        Unified MCP proxy endpoint for calling MCP server tools.

        Args:
            server_name: Name of the MCP server
            tool_name: Name of the tool to call
            request: FastAPI request with tool arguments in body

        Returns:
            Tool execution result
        """
        start_time = time.perf_counter()
        metrics.inc_counter("http_requests_total")
        metrics.inc_counter("mcp_tool_calls_total")

        try:
            # Parse request body as tool arguments
            try:
                args = await request.json()
            except (json.JSONDecodeError, ValueError) as e:
                raise HTTPException(
                    status_code=400, detail=f"Invalid JSON in request body: {e}"
                ) from e

            # Check internal registries first (gobby-tasks, gobby-memory, etc.)
            if server._internal_manager and server._internal_manager.is_internal(server_name):
                registry = server._internal_manager.get_registry(server_name)
                if registry:
                    try:
                        result = await registry.call(tool_name, args or {})
                        response_time_ms = (time.perf_counter() - start_time) * 1000
                        metrics.inc_counter("mcp_tool_calls_succeeded_total")
                        return {
                            "success": True,
                            "result": result,
                            "response_time_ms": response_time_ms,
                        }
                    except Exception as e:
                        metrics.inc_counter("mcp_tool_calls_failed_total")
                        error_msg = str(e) or f"{type(e).__name__}: (no message)"
                        raise HTTPException(status_code=500, detail=error_msg) from e
                raise HTTPException(
                    status_code=404, detail=f"Internal server '{server_name}' not found"
                )

            if server.mcp_manager is None:
                raise HTTPException(status_code=503, detail="MCP manager not available")

            # Call MCP tool
            try:
                result = await server.mcp_manager.call_tool(server_name, tool_name, args)

                response_time_ms = (time.perf_counter() - start_time) * 1000

                logger.debug(
                    f"MCP tool call successful: {server_name}.{tool_name}",
                    extra={
                        "server": server_name,
                        "tool": tool_name,
                        "response_time_ms": response_time_ms,
                    },
                )

                metrics.inc_counter("mcp_tool_calls_succeeded_total")

                return {
                    "success": True,
                    "result": result,
                    "response_time_ms": response_time_ms,
                }

            except ValueError as e:
                metrics.inc_counter("mcp_tool_calls_failed_total")
                logger.warning(
                    f"MCP tool not found: {server_name}.{tool_name}",
                    extra={"server": server_name, "tool": tool_name, "error": str(e)},
                )
                raise HTTPException(status_code=404, detail=str(e)) from e
            except Exception as e:
                metrics.inc_counter("mcp_tool_calls_failed_total")
                error_msg = str(e) or f"{type(e).__name__}: (no message)"
                logger.error(
                    f"MCP tool call error: {server_name}.{tool_name}",
                    exc_info=True,
                    extra={"server": server_name, "tool": tool_name},
                )
                raise HTTPException(status_code=500, detail=error_msg) from e

        except HTTPException:
            raise
        except Exception as e:
            metrics.inc_counter("mcp_tool_calls_failed_total")
            error_msg = str(e) or f"{type(e).__name__}: (no message)"
            logger.error(f"MCP proxy error: {server_name}.{tool_name}", exc_info=True)
            raise HTTPException(status_code=500, detail=error_msg) from e

    @router.post("/refresh")
    async def refresh_mcp_tools(
        request: Request,
        server: "HTTPServer" = Depends(get_server),
    ) -> dict[str, Any]:
        """
        Refresh MCP tools - detect schema changes and re-index as needed.

        Request body:
            {
                "cwd": "/path/to/project",
                "force": false,
                "server": "optional-server-filter"
            }

        Returns:
            Refresh stats with new/changed/unchanged tool counts
        """
        start_time = time.perf_counter()
        metrics.inc_counter("http_requests_total")

        try:
            body = await request.json()
            cwd = body.get("cwd")
            force = body.get("force", False)
            server_filter = body.get("server")

            # Resolve project_id from cwd
            try:
                project_id = server._resolve_project_id(None, cwd)
            except ValueError as e:
                return {
                    "success": False,
                    "error": str(e),
                    "response_time_ms": (time.perf_counter() - start_time) * 1000,
                }

            # Need schema hash manager and semantic search
            if not server._mcp_db_manager:
                return {
                    "success": False,
                    "error": "MCP database manager not configured",
                    "response_time_ms": (time.perf_counter() - start_time) * 1000,
                }

            from gobby.mcp_proxy.schema_hash import SchemaHashManager, compute_schema_hash

            schema_hash_manager = SchemaHashManager(db=server._mcp_db_manager.db)
            semantic_search = (
                getattr(server._tools_handler, "_semantic_search", None)
                if server._tools_handler
                else None
            )

            stats: dict[str, Any] = {
                "servers_processed": 0,
                "tools_new": 0,
                "tools_changed": 0,
                "tools_unchanged": 0,
                "tools_removed": 0,
                "embeddings_generated": 0,
                "by_server": {},
            }

            # Collect servers to process
            servers_to_process: list[str] = []

            # Internal servers
            if server._internal_manager:
                for registry in server._internal_manager.get_all_registries():
                    if server_filter is None or registry.name == server_filter:
                        servers_to_process.append(registry.name)

            # External MCP servers
            if server.mcp_manager:
                for config in server.mcp_manager.server_configs:
                    if config.enabled:
                        if server_filter is None or config.name == server_filter:
                            servers_to_process.append(config.name)

            # Process each server
            for server_name in servers_to_process:
                try:
                    tools: list[dict[str, Any]] = []

                    # Get tools from internal or external server
                    if server._internal_manager and server._internal_manager.is_internal(
                        server_name
                    ):
                        internal_registry = server._internal_manager.get_registry(server_name)
                        if internal_registry:
                            for t in internal_registry.list_tools():
                                tool_name = t.get("name", "")
                                tools.append(
                                    {
                                        "name": tool_name,
                                        "description": t.get("description"),
                                        "inputSchema": internal_registry.get_schema(tool_name),
                                    }
                                )
                    elif server.mcp_manager:
                        try:
                            session = await server.mcp_manager.ensure_connected(server_name)
                            tools_result = await session.list_tools()
                            for t in tools_result.tools:
                                schema = None
                                if hasattr(t, "inputSchema"):
                                    if hasattr(t.inputSchema, "model_dump"):
                                        schema = t.inputSchema.model_dump()
                                    elif isinstance(t.inputSchema, dict):
                                        schema = t.inputSchema
                                tools.append(
                                    {
                                        "name": t.name,  # type: ignore[attr-defined]
                                        "description": getattr(t, "description", ""),
                                        "inputSchema": schema,
                                    }
                                )
                        except Exception as e:
                            logger.warning(f"Failed to connect to {server_name}: {e}")
                            stats["by_server"][server_name] = {"error": str(e)}
                            continue

                    # Check for schema changes
                    if force:
                        # Force mode: treat all as new
                        changes = {
                            "new": [t["name"] for t in tools],
                            "changed": [],
                            "unchanged": [],
                        }
                    else:
                        changes = schema_hash_manager.check_tools_for_changes(
                            server_name=server_name,
                            project_id=project_id,
                            tools=tools,
                        )

                    server_stats = {
                        "new": len(changes["new"]),
                        "changed": len(changes["changed"]),
                        "unchanged": len(changes["unchanged"]),
                        "removed": 0,
                        "embeddings": 0,
                    }

                    # Update schema hashes for new/changed tools
                    tools_to_embed = []
                    for tool in tools:
                        tool_name = tool["name"]
                        if tool_name in changes["new"] or tool_name in changes["changed"]:
                            schema = tool.get("inputSchema")
                            schema_hash = compute_schema_hash(schema)
                            schema_hash_manager.store_hash(
                                server_name=server_name,
                                tool_name=tool_name,
                                project_id=project_id,
                                schema_hash=schema_hash,
                            )
                            tools_to_embed.append(tool)
                        else:
                            # Just update verification time for unchanged
                            schema_hash_manager.update_verification_time(
                                server_name=server_name,
                                tool_name=tool_name,
                                project_id=project_id,
                            )

                    # Clean up stale hashes
                    valid_tool_names = [t["name"] for t in tools]
                    removed = schema_hash_manager.cleanup_stale_hashes(
                        server_name=server_name,
                        project_id=project_id,
                        valid_tool_names=valid_tool_names,
                    )
                    server_stats["removed"] = removed

                    # Generate embeddings for new/changed tools
                    if semantic_search and tools_to_embed:
                        for tool in tools_to_embed:
                            try:
                                await semantic_search.embed_tool(
                                    server_name=server_name,
                                    tool_name=tool["name"],
                                    description=tool.get("description", ""),
                                    input_schema=tool.get("inputSchema"),
                                    project_id=project_id,
                                )
                                server_stats["embeddings"] += 1
                            except Exception as e:
                                logger.warning(f"Failed to embed {server_name}/{tool['name']}: {e}")

                    stats["by_server"][server_name] = server_stats
                    stats["servers_processed"] += 1
                    stats["tools_new"] += server_stats["new"]
                    stats["tools_changed"] += server_stats["changed"]
                    stats["tools_unchanged"] += server_stats["unchanged"]
                    stats["tools_removed"] += server_stats["removed"]
                    stats["embeddings_generated"] += server_stats["embeddings"]

                except Exception as e:
                    logger.error(f"Error processing server {server_name}: {e}")
                    stats["by_server"][server_name] = {"error": str(e)}

            response_time_ms = (time.perf_counter() - start_time) * 1000
            return {
                "success": True,
                "force": force,
                "stats": stats,
                "response_time_ms": response_time_ms,
            }

        except HTTPException:
            raise
        except Exception as e:
            metrics.inc_counter("http_requests_errors_total")
            logger.error(f"Refresh tools error: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)) from e

    return router


def create_code_router(server: "HTTPServer") -> APIRouter:
    """
    Create code execution router with endpoints bound to server instance.

    Args:
        server: HTTPServer instance for accessing state and dependencies

    Returns:
        Configured APIRouter with code execution endpoints
    """
    router = APIRouter(prefix="/code", tags=["code"])
    metrics = get_metrics_collector()

    @router.post("/execute")
    async def execute_code(
        request: Request,
        server: "HTTPServer" = Depends(get_server),
    ) -> dict[str, Any]:
        """
        Execute code using LLM-powered code execution.

        Request body:
            {
                "code": "print('hello')",
                "language": "python",
                "context": "optional context",
                "timeout": 30
            }

        Returns:
            Execution result or error
        """
        start_time = time.perf_counter()
        metrics.inc_counter("http_requests_total")

        try:
            body = await request.json()
            code = body.get("code")
            language = body.get("language", "python")
            context = body.get("context")
            timeout = body.get("timeout", 30)

            if not code:
                raise HTTPException(status_code=400, detail="Required field: code")

            code_service = CodeExecutionService(
                llm_service=server.llm_service, config=server.config
            )
            result = await code_service.execute_code(code, language, context, timeout)

            response_time_ms = (time.perf_counter() - start_time) * 1000
            result["response_time_ms"] = response_time_ms
            return result

        except HTTPException:
            raise
        except Exception as e:
            metrics.inc_counter("http_requests_errors_total")
            logger.error(f"Code execution error: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.post("/process-dataset")
    async def process_dataset(
        request: Request,
        server: "HTTPServer" = Depends(get_server),
    ) -> dict[str, Any]:
        """
        Process large datasets using LLM-powered chunked processing.

        Request body:
            {
                "data": [...],
                "operation": "summarize",
                "parameters": {},
                "timeout": 60
            }

        Returns:
            Processed result or error
        """
        start_time = time.perf_counter()
        metrics.inc_counter("http_requests_total")

        try:
            body = await request.json()
            data = body.get("data")
            operation = body.get("operation")
            parameters = body.get("parameters")
            timeout = body.get("timeout", 60)

            if data is None:
                raise HTTPException(status_code=400, detail="Required field: data")
            if not operation:
                raise HTTPException(status_code=400, detail="Required field: operation")

            code_service = CodeExecutionService(
                llm_service=server.llm_service, config=server.config
            )
            result = await code_service.process_dataset(data, operation, parameters, timeout)

            response_time_ms = (time.perf_counter() - start_time) * 1000
            result["response_time_ms"] = response_time_ms
            return result

        except HTTPException:
            raise
        except Exception as e:
            metrics.inc_counter("http_requests_errors_total")
            logger.error(f"Dataset processing error: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)) from e

    return router


def create_hooks_router(server: "HTTPServer") -> APIRouter:
    """
    Create hooks router with endpoints bound to server instance.

    Args:
        server: HTTPServer instance for accessing state and dependencies

    Returns:
        Configured APIRouter with hooks endpoints
    """
    router = APIRouter(prefix="/hooks", tags=["hooks"])
    metrics = get_metrics_collector()

    @router.post("/execute")
    async def execute_hook(request: Request) -> dict[str, Any]:
        """
        Execute CLI hook via adapter pattern.

        Request body:
            {
                "hook_type": "session-start",
                "input_data": {...},
                "source": "claude"
            }

        Returns:
            Hook execution result with status
        """
        import asyncio

        start_time = time.perf_counter()
        metrics.inc_counter("http_requests_total")
        metrics.inc_counter("hooks_total")

        try:
            # Parse request
            payload = await request.json()
            hook_type = payload.get("hook_type")
            source = payload.get("source")

            if not hook_type:
                raise HTTPException(status_code=400, detail="hook_type required")

            if not source:
                raise HTTPException(status_code=400, detail="source required")

            # Get HookManager from app.state
            if not hasattr(request.app.state, "hook_manager"):
                raise HTTPException(status_code=503, detail="HookManager not initialized")

            hook_manager = request.app.state.hook_manager

            # Select adapter based on source
            from gobby.adapters.base import BaseAdapter
            from gobby.adapters.claude_code import ClaudeCodeAdapter
            from gobby.adapters.codex import CodexNotifyAdapter
            from gobby.adapters.gemini import GeminiAdapter

            if source == "claude":
                adapter: BaseAdapter = ClaudeCodeAdapter(hook_manager=hook_manager)
            elif source == "gemini":
                adapter = GeminiAdapter(hook_manager=hook_manager)
            elif source == "codex":
                adapter = CodexNotifyAdapter(hook_manager=hook_manager)
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported source: {source}. Supported: claude, gemini, codex",
                )

            # Execute hook via adapter
            try:
                result = await asyncio.to_thread(adapter.handle_native, payload, hook_manager)

                response_time_ms = (time.perf_counter() - start_time) * 1000
                metrics.inc_counter("hooks_succeeded_total")

                logger.debug(
                    f"Hook executed: {hook_type}",
                    extra={
                        "hook_type": hook_type,
                        "continue": result.get("continue"),
                        "response_time_ms": response_time_ms,
                    },
                )

                return result

            except ValueError as e:
                metrics.inc_counter("hooks_failed_total")
                logger.warning(
                    f"Invalid hook request: {hook_type}",
                    extra={"hook_type": hook_type, "error": str(e)},
                )
                raise HTTPException(status_code=400, detail=str(e)) from e

            except Exception as e:
                metrics.inc_counter("hooks_failed_total")
                logger.error(
                    f"Hook execution failed: {hook_type}",
                    exc_info=True,
                    extra={"hook_type": hook_type},
                )
                raise HTTPException(status_code=500, detail=str(e)) from e

        except HTTPException:
            raise
        except Exception as e:
            metrics.inc_counter("hooks_failed_total")
            logger.error("Hook endpoint error", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)) from e

    return router


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


def create_webhooks_router() -> APIRouter:
    """
    Create webhooks management router using dependency injection.

    Returns:
        Configured APIRouter with webhooks endpoints
    """
    router = APIRouter(prefix="/webhooks", tags=["webhooks"])

    @router.get("")
    async def list_webhooks(
        server: "HTTPServer" = Depends(get_server),
    ) -> dict[str, Any]:
        """
        List configured webhook endpoints.

        Returns:
            List of webhook endpoint configurations
        """
        config = server.config
        if not config:
            return {
                "success": True,
                "enabled": False,
                "endpoints": [],
            }

        webhooks_config = config.hook_extensions.webhooks

        endpoints = [
            {
                "name": e.name,
                "url": e.url,
                "events": e.events,
                "enabled": e.enabled,
                "can_block": e.can_block,
                "timeout": e.timeout,
                "retry_count": e.retry_count,
            }
            for e in webhooks_config.endpoints
        ]

        return {
            "success": True,
            "enabled": webhooks_config.enabled,
            "endpoints": endpoints,
        }

    @router.post("/test")
    async def test_webhook(
        request: Request,
        server: "HTTPServer" = Depends(get_server),
    ) -> dict[str, Any]:
        """
        Test a webhook endpoint by sending a test event.

        Request body:
            {"name": "webhook-name", "event_type": "notification"}

        Returns:
            Test result with status code and response time
        """
        import httpx

        try:
            body = await request.json()
            webhook_name = body.get("name")
            event_type = body.get("event_type", "notification")

            if not webhook_name:
                raise HTTPException(status_code=400, detail="Webhook name required")

            config = server.config
            if not config:
                return {"success": False, "error": "Configuration not available"}

            webhooks_config = config.hook_extensions.webhooks
            if not webhooks_config.enabled:
                return {"success": False, "error": "Webhooks are disabled"}

            # Find the webhook endpoint
            endpoint = None
            for e in webhooks_config.endpoints:
                if e.name == webhook_name:
                    endpoint = e
                    break

            if endpoint is None:
                return {"success": False, "error": f"Webhook not found: {webhook_name}"}

            if not endpoint.enabled:
                return {"success": False, "error": f"Webhook is disabled: {webhook_name}"}

            # Build test payload
            test_payload = {
                "event_type": event_type,
                "test": True,
                "timestamp": time.time(),
                "data": {
                    "message": f"Test event from gobby CLI for webhook '{webhook_name}'",
                },
            }

            # Send test request
            start_time = time.perf_counter()
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    endpoint.url,
                    json=test_payload,
                    headers=endpoint.headers,
                    timeout=endpoint.timeout,
                )
            response_time_ms = (time.perf_counter() - start_time) * 1000

            success = 200 <= response.status_code < 300

            return {
                "success": success,
                "status_code": response.status_code,
                "response_time_ms": response_time_ms,
                "error": None if success else f"HTTP {response.status_code}",
            }

        except httpx.TimeoutException:
            return {"success": False, "error": "Request timed out"}
        except httpx.RequestError as e:
            return {"success": False, "error": f"Request failed: {e}"}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Webhook test error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    return router
