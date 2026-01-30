"""
Execution endpoints for MCP tool invocation.

Extracted from tools.py as part of Phase 2 Strangler Fig decomposition.
These endpoints handle tool listing, schema retrieval, and tool execution.
"""

import json
import logging
import re
import time
from typing import TYPE_CHECKING, Any

from fastapi import Depends, HTTPException, Request

from gobby.servers.routes.dependencies import get_internal_manager, get_mcp_manager, get_server
from gobby.utils.metrics import get_metrics_collector

if TYPE_CHECKING:
    from gobby.mcp_proxy.manager import MCPClientManager
    from gobby.mcp_proxy.registry_manager import InternalToolRegistryManager
    from gobby.servers.http import HTTPServer

logger = logging.getLogger(__name__)

# Module-level metrics collector (shared across all requests)
_metrics = get_metrics_collector()


def _process_tool_proxy_result(
    result: Any,
    server_name: str,
    tool_name: str,
    response_time_ms: float,
) -> dict[str, Any]:
    """
    Process tool proxy result with consistent metrics, logging, and error handling.

    Args:
        result: The result from tool_proxy.call_tool()
        server_name: Name of the MCP server
        tool_name: Name of the tool called
        response_time_ms: Response time in milliseconds

    Returns:
        Wrapped result dict with success status and response time

    Raises:
        HTTPException: 404 if server not found/not configured
    """
    # Track metrics for tool-level failures vs successes
    if isinstance(result, dict) and result.get("success") is False:
        _metrics.inc_counter("mcp_tool_calls_failed_total")

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
        _metrics.inc_counter("mcp_tool_calls_succeeded_total")
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


async def _call_internal_tool(
    registry: Any,
    server_name: str,
    tool_name: str,
    arguments: dict[str, Any] | None,
    start_time: float,
) -> dict[str, Any]:
    """Shared helper for calling internal registry tools.

    Args:
        registry: The internal tool registry
        server_name: Name of the MCP server
        tool_name: Name of the tool to call
        arguments: Arguments to pass to the tool
        start_time: Request start time for response_time_ms calculation

    Returns:
        Tool execution result dict

    Raises:
        HTTPException: 404 if tool not found, 500 on execution error
    """
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
        _metrics.inc_counter("mcp_tool_calls_succeeded_total")
        return {
            "success": True,
            "result": result,
            "response_time_ms": response_time_ms,
        }
    except Exception as e:
        _metrics.inc_counter("mcp_tool_calls_failed_total")
        error_msg = str(e) or f"{type(e).__name__}: (no message)"
        raise HTTPException(
            status_code=500,
            detail={"success": False, "error": error_msg},
        ) from e


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
    _metrics.inc_counter("http_requests_total")

    try:
        # Check internal registries first (gobby-tasks, gobby-memory, etc.)
        if internal_manager and internal_manager.is_internal(server_name):
            registry = internal_manager.get_registry(server_name)
            if registry:
                tools = registry.list_tools()
                response_time_ms = (time.perf_counter() - start_time) * 1000
                _metrics.observe_histogram("list_mcp_tools", response_time_ms / 1000)
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
            raise HTTPException(status_code=404, detail={"success": False, "error": str(e)}) from e
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
        _metrics.inc_counter("http_requests_errors_total")
        logger.error(f"MCP list tools error: {server_name}", exc_info=True)
        raise HTTPException(status_code=500, detail={"success": False, "error": str(e)}) from e


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
    _metrics.inc_counter("http_requests_total")

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
                    # Build response with description only if present
                    result: dict[str, Any] = {
                        "name": schema.get("name", tool_name),
                        "inputSchema": schema.get("inputSchema"),
                        "server": server_name,
                        "response_time_ms": response_time_ms,
                    }
                    if schema.get("description"):
                        result["description"] = schema["description"]
                    return result
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
            tool_info = await server.mcp_manager.get_tool_info(server_name, tool_name)
            response_time_ms = (time.perf_counter() - start_time) * 1000

            # Build response with description only if present
            response: dict[str, Any] = {
                "name": tool_info.get("name", tool_name),
                "inputSchema": tool_info.get("inputSchema"),
                "server": server_name,
                "response_time_ms": response_time_ms,
            }
            if tool_info.get("description"):
                response["description"] = tool_info["description"]
            return response

        except (KeyError, ValueError) as e:
            # Tool or server not found - 404
            raise HTTPException(status_code=404, detail={"success": False, "error": str(e)}) from e
        except Exception as e:
            # Connection, timeout, or internal errors - 500
            logger.error(f"Failed to get tool schema {server_name}/{tool_name}: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail={"success": False, "error": f"Failed to get tool schema: {e}"},
            ) from e

    except HTTPException:
        raise
    except Exception as e:
        _metrics.inc_counter("http_requests_errors_total")
        logger.error(f"Get tool schema error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"success": False, "error": str(e)}) from e


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
    _metrics.inc_counter("http_requests_total")
    _metrics.inc_counter("mcp_tool_calls_total")

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
            return _process_tool_proxy_result(result, server_name, tool_name, response_time_ms)

        # Fallback: no tool_proxy available, use direct registry calls
        # Check internal first
        if server._internal_manager and server._internal_manager.is_internal(server_name):
            registry = server._internal_manager.get_registry(server_name)
            if registry:
                return await _call_internal_tool(
                    registry, server_name, tool_name, arguments, start_time
                )

        if server.mcp_manager is None:
            raise HTTPException(
                status_code=503,
                detail={"success": False, "error": "MCP manager not available"},
            )

        # Call external MCP tool
        try:
            result = await server.mcp_manager.call_tool(server_name, tool_name, arguments)
            response_time_ms = (time.perf_counter() - start_time) * 1000
            _metrics.inc_counter("mcp_tool_calls_succeeded_total")

            return {
                "success": True,
                "result": result,
                "response_time_ms": response_time_ms,
            }

        except Exception as e:
            _metrics.inc_counter("mcp_tool_calls_failed_total")
            error_msg = str(e) or f"{type(e).__name__}: (no message)"
            raise HTTPException(
                status_code=500, detail={"success": False, "error": error_msg}
            ) from e

    except HTTPException:
        raise
    except Exception as e:
        _metrics.inc_counter("mcp_tool_calls_failed_total")
        error_msg = str(e) or f"{type(e).__name__}: (no message)"
        logger.error(f"Call MCP tool error: {error_msg}", exc_info=True)
        raise HTTPException(status_code=500, detail={"success": False, "error": error_msg}) from e


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
    _metrics.inc_counter("http_requests_total")
    _metrics.inc_counter("mcp_tool_calls_total")

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
            return _process_tool_proxy_result(result, server_name, tool_name, response_time_ms)

        # Fallback: no tool_proxy available, use direct registry calls
        # Check internal registries first (gobby-tasks, gobby-memory, etc.)
        if server._internal_manager and server._internal_manager.is_internal(server_name):
            registry = server._internal_manager.get_registry(server_name)
            if registry:
                return await _call_internal_tool(registry, server_name, tool_name, args, start_time)
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

            _metrics.inc_counter("mcp_tool_calls_succeeded_total")

            return {
                "success": True,
                "result": result,
                "response_time_ms": response_time_ms,
            }

        except ValueError as e:
            _metrics.inc_counter("mcp_tool_calls_failed_total")
            logger.warning(
                f"MCP tool not found: {server_name}.{tool_name}",
                extra={"server": server_name, "tool": tool_name, "error": str(e)},
            )
            raise HTTPException(status_code=404, detail={"success": False, "error": str(e)}) from e
        except Exception as e:
            _metrics.inc_counter("mcp_tool_calls_failed_total")
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
        _metrics.inc_counter("mcp_tool_calls_failed_total")
        error_msg = str(e) or f"{type(e).__name__}: (no message)"
        logger.error(f"MCP proxy error: {server_name}.{tool_name}", exc_info=True)
        raise HTTPException(status_code=500, detail={"success": False, "error": error_msg}) from e


__all__ = [
    "list_mcp_tools",
    "get_tool_schema",
    "call_mcp_tool",
    "mcp_proxy",
    "_process_tool_proxy_result",
]
