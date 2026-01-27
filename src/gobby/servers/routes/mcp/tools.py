"""
MCP routes for Gobby HTTP server.

Provides MCP server management, tool discovery, and tool execution endpoints.
Uses FastAPI dependency injection via Depends() for proper testability.
"""

import json
import logging
import re
import time
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, Request

from gobby.servers.routes.dependencies import (
    get_internal_manager,
    get_mcp_manager,
    get_server,
)
from gobby.servers.routes.mcp.endpoints.discovery import (
    list_all_mcp_tools,
    recommend_mcp_tools,
    search_mcp_tools,
)
from gobby.servers.routes.mcp.endpoints.server import (
    add_mcp_server,
    import_mcp_server,
    list_mcp_servers,
    remove_mcp_server,
)
from gobby.utils.metrics import get_metrics_collector

if TYPE_CHECKING:
    from gobby.mcp_proxy.manager import MCPClientManager
    from gobby.mcp_proxy.registry_manager import InternalToolRegistryManager
    from gobby.servers.http import HTTPServer

logger = logging.getLogger(__name__)


def _process_tool_proxy_result(
    result: Any,
    server_name: str,
    tool_name: str,
    response_time_ms: float,
    metrics_collector: Any,
) -> dict[str, Any]:
    """
    Process tool proxy result with consistent metrics, logging, and error handling.

    Args:
        result: The result from tool_proxy.call_tool()
        server_name: Name of the MCP server
        tool_name: Name of the tool called
        response_time_ms: Response time in milliseconds
        metrics_collector: Metrics collector instance

    Returns:
        Wrapped result dict with success status and response time

    Raises:
        HTTPException: 404 if server not found/not configured
    """
    # Track metrics for tool-level failures vs successes
    if isinstance(result, dict) and result.get("success") is False:
        metrics_collector.inc_counter("mcp_tool_calls_failed_total")

        # Check structured error code first (preferred)
        error_code = result.get("error_code")
        if error_code in ("SERVER_NOT_FOUND", "SERVER_NOT_CONFIGURED"):
            # Normalize result to standard error shape while preserving existing fields
            normalized = {"success": False, "error": result.get("error", "Unknown error")}
            for key, value in result.items():
                if key not in normalized:
                    normalized[key] = value
            raise HTTPException(status_code=404, detail=normalized)

        # Backward compatibility: fall back to regex matching if no error_code
        if not error_code:
            logger.debug(
                "ToolProxyService returned error without error_code - using regex fallback"
            )
            error_msg = str(result.get("error", ""))
            if re.search(r"server\s+(not\s+found|not\s+configured)", error_msg, re.IGNORECASE):
                normalized = {"success": False, "error": result.get("error", "Unknown error")}
                for key, value in result.items():
                    if key not in normalized:
                        normalized[key] = value
                raise HTTPException(status_code=404, detail=normalized)

        # Tool-level failure (not a transport error) - return failure envelope
        return {
            "success": False,
            "result": result,
            "response_time_ms": response_time_ms,
        }
    else:
        metrics_collector.inc_counter("mcp_tool_calls_succeeded_total")
        logger.debug(
            f"MCP tool call successful: {server_name}.{tool_name}",
            extra={
                "server": server_name,
                "tool": tool_name,
                "response_time_ms": response_time_ms,
            },
        )

    # Return 200 with wrapped result for success cases
    return {
        "success": True,
        "result": result,
        "response_time_ms": response_time_ms,
    }


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
                    status_code=404,
                    detail={
                        "success": False,
                        "error": f"Internal server '{server_name}' not found",
                    },
                )

            if mcp_manager is None:
                raise HTTPException(
                    status_code=503, detail={"success": False, "error": "MCP manager not available"}
                )

            # Check if server is configured
            if not mcp_manager.has_server(server_name):
                raise HTTPException(
                    status_code=404,
                    detail={"success": False, "error": f"Unknown MCP server: '{server_name}'"},
                )

            # Use ensure_connected for lazy loading - connects on-demand if not connected
            try:
                session = await mcp_manager.ensure_connected(server_name)
            except KeyError as e:
                raise HTTPException(
                    status_code=404, detail={"success": False, "error": str(e)}
                ) from e
            except Exception as e:
                raise HTTPException(
                    status_code=503,
                    detail={
                        "success": False,
                        "error": f"MCP server '{server_name}' connection failed: {e}",
                    },
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
                raise HTTPException(
                    status_code=500,
                    detail={"success": False, "error": f"Failed to list tools: {e}"},
                ) from e

        except HTTPException:
            raise
        except Exception as e:
            metrics.inc_counter("http_requests_errors_total")
            logger.error(f"MCP list tools error: {server_name}", exc_info=True)
            raise HTTPException(status_code=500, detail={"success": False, "error": str(e)}) from e

    # Register server management endpoint from endpoints/server.py
    router.get("/servers")(list_mcp_servers)

    # Register discovery endpoint from endpoints/discovery.py
    router.get("/tools")(list_all_mcp_tools)

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
                    status_code=400,
                    detail={"success": False, "error": "Required fields: server_name, tool_name"},
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
                        detail={
                            "success": False,
                            "error": f"Tool '{tool_name}' not found on server '{server_name}'",
                        },
                    )

            if server.mcp_manager is None:
                raise HTTPException(
                    status_code=503,
                    detail={"success": False, "error": "MCP manager not available"},
                )

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

            except (KeyError, ValueError) as e:
                # Tool or server not found - 404
                raise HTTPException(
                    status_code=404, detail={"success": False, "error": str(e)}
                ) from e
            except Exception as e:
                # Connection, timeout, or internal errors - 500
                logger.error(
                    f"Failed to get tool schema {server_name}/{tool_name}: {e}", exc_info=True
                )
                raise HTTPException(
                    status_code=500,
                    detail={"success": False, "error": f"Failed to get tool schema: {e}"},
                ) from e

        except HTTPException:
            raise
        except Exception as e:
            metrics.inc_counter("http_requests_errors_total")
            logger.error(f"Get tool schema error: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail={"success": False, "error": str(e)}) from e

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
                    status_code=400,
                    detail={"success": False, "error": "Required fields: server_name, tool_name"},
                )

            # Route through ToolProxyService for consistent error enrichment
            if server.tool_proxy:
                result = await server.tool_proxy.call_tool(server_name, tool_name, arguments)
                response_time_ms = (time.perf_counter() - start_time) * 1000
                return _process_tool_proxy_result(
                    result, server_name, tool_name, response_time_ms, metrics
                )

            # Fallback: no tool_proxy available, use direct registry calls
            # Check internal first
            if server._internal_manager and server._internal_manager.is_internal(server_name):
                registry = server._internal_manager.get_registry(server_name)
                if registry:
                    # Check if tool exists before calling - return helpful 404 if not
                    if not registry.get_schema(tool_name):
                        available = [t["name"] for t in registry.list_tools()]
                        raise HTTPException(
                            status_code=404,
                            detail={
                                "success": False,
                                "error": f"Tool '{tool_name}' not found on '{server_name}'. "
                                f"Available: {', '.join(available)}. "
                                f"Use list_tools(server='{server_name}') to see all tools, "
                                f"or get_tool_schema(server_name='{server_name}', tool_name='...') for full schema.",
                            },
                        )
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
                raise HTTPException(
                    status_code=503,
                    detail={"success": False, "error": "MCP manager not available"},
                )

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
                raise HTTPException(
                    status_code=500, detail={"success": False, "error": error_msg}
                ) from e

        except HTTPException:
            raise
        except Exception as e:
            metrics.inc_counter("mcp_tool_calls_failed_total")
            error_msg = str(e) or f"{type(e).__name__}: (no message)"
            logger.error(f"Call MCP tool error: {error_msg}", exc_info=True)
            raise HTTPException(
                status_code=500, detail={"success": False, "error": error_msg}
            ) from e

    # Register server management endpoints from endpoints/server.py
    router.post("/servers")(add_mcp_server)
    router.post("/servers/import")(import_mcp_server)
    router.delete("/servers/{name}")(remove_mcp_server)

    # Register discovery endpoints from endpoints/discovery.py
    router.post("/tools/recommend")(recommend_mcp_tools)

    router.post("/tools/search")(search_mcp_tools)

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
            raise HTTPException(status_code=500, detail={"success": False, "error": str(e)}) from e

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
            raise HTTPException(status_code=500, detail={"success": False, "error": str(e)}) from e

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
                    status_code=400,
                    detail={"success": False, "error": f"Invalid JSON in request body: {e}"},
                ) from e

            # Route through ToolProxyService for consistent error enrichment
            if server.tool_proxy:
                result = await server.tool_proxy.call_tool(server_name, tool_name, args)
                response_time_ms = (time.perf_counter() - start_time) * 1000
                return _process_tool_proxy_result(
                    result, server_name, tool_name, response_time_ms, metrics
                )

            # Fallback: no tool_proxy available, use direct registry calls
            # Check internal registries first (gobby-tasks, gobby-memory, etc.)
            if server._internal_manager and server._internal_manager.is_internal(server_name):
                registry = server._internal_manager.get_registry(server_name)
                if registry:
                    # Check if tool exists before calling - return helpful 404 if not
                    if not registry.get_schema(tool_name):
                        available = [t["name"] for t in registry.list_tools()]
                        raise HTTPException(
                            status_code=404,
                            detail={
                                "success": False,
                                "error": f"Tool '{tool_name}' not found on '{server_name}'. "
                                f"Available: {', '.join(available)}. "
                                f"Use list_tools(server='{server_name}') to see all tools, "
                                f"or get_tool_schema(server_name='{server_name}', tool_name='...') for full schema.",
                            },
                        )
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
                        raise HTTPException(
                            status_code=500, detail={"success": False, "error": error_msg}
                        ) from e
                raise HTTPException(
                    status_code=404,
                    detail={
                        "success": False,
                        "error": f"Internal server '{server_name}' not found",
                    },
                )

            if server.mcp_manager is None:
                raise HTTPException(
                    status_code=503,
                    detail={"success": False, "error": "MCP manager not available"},
                )

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
                raise HTTPException(
                    status_code=404, detail={"success": False, "error": str(e)}
                ) from e
            except Exception as e:
                metrics.inc_counter("mcp_tool_calls_failed_total")
                error_msg = str(e) or f"{type(e).__name__}: (no message)"
                logger.error(
                    f"MCP tool call error: {server_name}.{tool_name}",
                    exc_info=True,
                    extra={"server": server_name, "tool": tool_name},
                )
                raise HTTPException(
                    status_code=500, detail={"success": False, "error": error_msg}
                ) from e

        except HTTPException:
            raise
        except Exception as e:
            metrics.inc_counter("mcp_tool_calls_failed_total")
            error_msg = str(e) or f"{type(e).__name__}: (no message)"
            logger.error(f"MCP proxy error: {server_name}.{tool_name}", exc_info=True)
            raise HTTPException(
                status_code=500, detail={"success": False, "error": error_msg}
            ) from e

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
                                        "name": getattr(t, "name", ""),
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
            raise HTTPException(status_code=500, detail={"success": False, "error": str(e)}) from e

    return router
