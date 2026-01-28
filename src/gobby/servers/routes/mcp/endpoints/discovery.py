"""
Discovery endpoints for MCP tool and server listing.

Extracted from tools.py as part of Phase 2 Strangler Fig decomposition.
These endpoints handle tool discovery, search, and recommendations.
"""

import asyncio
import json
import logging
import time
from typing import TYPE_CHECKING, Any

from fastapi import Depends, HTTPException, Request

from gobby.servers.routes.dependencies import get_metrics_manager, get_server
from gobby.utils.metrics import get_metrics_collector

if TYPE_CHECKING:
    from gobby.mcp_proxy.metrics import ToolMetricsManager
    from gobby.servers.http import HTTPServer

logger = logging.getLogger(__name__)

# Module-level metrics collector (shared across all requests)
_metrics = get_metrics_collector()

# Set to keep background tasks alive (prevent garbage collection)
_background_tasks: set[asyncio.Task[Any]] = set()


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
        server: HTTPServer instance (injected)
        metrics_manager: Tool metrics manager (injected)

    Returns:
        Dict of server names to tool lists
    """
    start_time = time.perf_counter()
    _metrics.inc_counter("http_requests_total")

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
        _metrics.inc_counter("http_requests_errors_total")
        logger.error(f"List MCP tools error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"success": False, "error": str(e)}) from e


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
    _metrics.inc_counter("http_requests_total")

    try:
        try:
            body = await request.json()
        except json.JSONDecodeError as err:
            raise HTTPException(
                status_code=400,
                detail={"success": False, "error": "Malformed JSON", "message": str(err)},
            ) from err

        task_description = body.get("task_description")
        agent_id = body.get("agent_id")
        search_mode = body.get("search_mode", "llm")
        top_k = body.get("top_k", 10)
        min_similarity = body.get("min_similarity", 0.3)
        cwd = body.get("cwd")

        if not task_description:
            raise HTTPException(
                status_code=400,
                detail={"success": False, "error": "Required field: task_description"},
            )

        # For semantic/hybrid modes, resolve project_id from cwd
        project_id = None
        if search_mode in ("semantic", "hybrid"):
            try:
                project_id = server._resolve_project_id(None, cwd)
            except ValueError as e:
                response_time_ms = (time.perf_counter() - start_time) * 1000
                raise HTTPException(
                    status_code=400,
                    detail={
                        "success": False,
                        "error": str(e),
                        "task": task_description,
                        "response_time_ms": response_time_ms,
                    },
                ) from e

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
        _metrics.inc_counter("http_requests_errors_total")
        logger.error(f"Recommend tools error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"success": False, "error": str(e)}) from e


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
    _metrics.inc_counter("http_requests_total")

    try:
        try:
            body = await request.json()
        except json.JSONDecodeError as err:
            raise HTTPException(
                status_code=400,
                detail={"success": False, "error": "Malformed JSON", "message": str(err)},
            ) from err

        query = body.get("query")
        top_k = body.get("top_k", 10)
        min_similarity = body.get("min_similarity", 0.0)
        server_filter = body.get("server")
        cwd = body.get("cwd")

        if not query:
            raise HTTPException(
                status_code=400,
                detail={"success": False, "error": "Required field: query"},
            )

        # Resolve project_id from cwd
        try:
            project_id = server._resolve_project_id(None, cwd)
        except ValueError as e:
            response_time_ms = (time.perf_counter() - start_time) * 1000
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "error": str(e),
                    "query": query,
                    "response_time_ms": response_time_ms,
                },
            ) from e

        # Use semantic search directly if available
        if server._tools_handler and server._tools_handler._semantic_search:
            try:
                import asyncio

                semantic_search = server._tools_handler._semantic_search

                # Check if embeddings exist - if not, trigger background generation
                existing = semantic_search.get_embeddings_for_project(project_id)
                if not existing and server._mcp_db_manager:
                    logger.info(
                        f"No embeddings for project {project_id}, triggering background generation..."
                    )

                    # Wrapper to log exceptions from background embedding generation
                    async def _embed_with_error_handling(proj_id: str) -> None:
                        try:
                            await semantic_search.embed_all_tools(
                                project_id=proj_id,
                                mcp_manager=server._mcp_db_manager,
                                force=False,
                            )
                        except Exception as e:
                            logger.error(
                                f"Background embedding generation failed for project {proj_id}: {e}",
                                exc_info=True,
                            )

                    # Trigger embedding generation as background task (non-blocking)
                    task = asyncio.create_task(_embed_with_error_handling(project_id))
                    _background_tasks.add(task)
                    task.add_done_callback(_background_tasks.discard)
                    # Return early indicating embeddings are being generated
                    response_time_ms = (time.perf_counter() - start_time) * 1000
                    return {
                        "success": True,
                        "embeddings_generating": True,
                        "query": query,
                        "results": [],
                        "total_results": 0,
                        "message": "Embeddings are being generated. Please retry in a few seconds.",
                        "response_time_ms": response_time_ms,
                    }

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
                response_time_ms = (time.perf_counter() - start_time) * 1000
                raise HTTPException(
                    status_code=500,
                    detail={
                        "success": False,
                        "error": str(e),
                        "query": query,
                        "response_time_ms": response_time_ms,
                    },
                ) from e

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
        _metrics.inc_counter("http_requests_errors_total")
        logger.error(f"Search tools error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"success": False, "error": str(e)}) from e


__all__ = [
    "list_all_mcp_tools",
    "recommend_mcp_tools",
    "search_mcp_tools",
]
