"""Code index routes for Gobby HTTP server.

Provides endpoints for incremental indexing (git hooks), status queries,
and graph visualization for the code explorer.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

if TYPE_CHECKING:
    from gobby.servers.http import HTTPServer

logger = logging.getLogger(__name__)


class IncrementalIndexRequest(BaseModel):
    """Request body for POST /api/code-index/incremental."""

    files: list[str]
    project_id: str = ""


def create_code_index_router(server: HTTPServer) -> APIRouter:
    """Create code index router."""
    router = APIRouter(prefix="/api/code-index", tags=["code-index"])

    @router.post("/incremental")
    async def trigger_incremental_index(
        request: Request, body: IncrementalIndexRequest
    ) -> JSONResponse:
        """Called by git post-commit hook with list of changed files."""
        services = server.services
        code_indexer = getattr(services, "code_indexer", None)

        if code_indexer is None:
            return JSONResponse(
                status_code=503,
                content={"error": "Code indexer not available"},
            )

        if not body.files:
            return JSONResponse(
                status_code=400,
                content={"error": "No files provided for indexing"},
            )

        project_id = body.project_id or getattr(services, "project_id", "") or ""
        root_path = ""

        # Look up project root
        if project_id:
            project_stats = code_indexer.storage.get_project_stats(project_id)
            if project_stats:
                root_path = project_stats.root_path

        if not root_path:
            return JSONResponse(
                status_code=400,
                content={"error": "No root_path found for project"},
            )

        from gobby.code_index.watcher import handle_incremental_index

        result = await handle_incremental_index(
            indexer=code_indexer,
            project_id=project_id,
            root_path=root_path,
            changed_files=body.files,
        )

        return JSONResponse(content=result)

    @router.get("/status")
    async def index_status(project_id: str = "") -> JSONResponse:
        """Get indexing status for a project."""
        services = server.services
        code_indexer = getattr(services, "code_indexer", None)

        if code_indexer is None:
            return JSONResponse(
                status_code=503,
                content={"error": "Code indexer not available"},
            )

        pid = project_id or getattr(services, "project_id", "") or ""
        if not pid:
            projects = code_indexer.storage.list_indexed_projects()
            return JSONResponse(content={"projects": [p.to_dict() for p in projects]})

        stats = code_indexer.storage.get_project_stats(pid)
        if stats is None:
            return JSONResponse(content={"indexed": False, "project_id": pid})

        return JSONResponse(content={"indexed": True, **stats.to_dict()})

    # ── Graph visualization endpoints ────────────────────────────────

    def _get_indexer_and_project(
        project_id: str = "",
    ) -> tuple[Any, str]:
        """Helper to resolve code_indexer and project_id."""
        services = server.services
        indexer = getattr(services, "code_indexer", None)
        pid = project_id or getattr(services, "project_id", "") or ""
        return indexer, pid

    @router.get("/graph")
    async def code_graph(
        project_id: str = Query("", description="Project ID"),
        limit: int = Query(200, description="Max file nodes"),
    ) -> JSONResponse:
        """Get file-level overview graph for visualization."""
        indexer, pid = _get_indexer_and_project(project_id)
        if indexer is None:
            return JSONResponse(
                status_code=503,
                content={"error": "Code indexer not available"},
            )
        if not pid:
            return JSONResponse(
                status_code=400,
                content={"error": "No project_id provided"},
            )

        # Try Neo4j graph first, fall back to SQLite
        if indexer.graph is not None and indexer.graph.available:
            data = await indexer.graph.get_file_graph(pid, limit=limit)
        else:
            data = indexer.storage.get_file_symbol_tree(pid, limit=limit)

        return JSONResponse(content=data)

    @router.get("/graph/file/{file_path:path}")
    async def code_graph_file(
        file_path: str,
        project_id: str = Query("", description="Project ID"),
    ) -> JSONResponse:
        """Expand a file to show its symbols and call edges."""
        indexer, pid = _get_indexer_and_project(project_id)
        if indexer is None:
            return JSONResponse(
                status_code=503,
                content={"error": "Code indexer not available"},
            )
        if not pid:
            return JSONResponse(
                status_code=400,
                content={"error": "No project_id provided"},
            )

        if indexer.graph is not None and indexer.graph.available:
            data = await indexer.graph.get_file_symbols(file_path, pid)
        else:
            # SQLite fallback: just return symbols for the file
            symbols = indexer.storage.get_symbols_for_file(pid, file_path)
            nodes = [
                {
                    "id": sym.id,
                    "name": sym.name,
                    "type": sym.kind or "function",
                    "kind": sym.kind,
                    "file_path": sym.file_path,
                    "line_start": sym.line_start,
                    "signature": sym.signature,
                }
                for sym in symbols
                if sym.parent_symbol_id is None
            ]
            links = [
                {"source": file_path, "target": n["id"], "type": "DEFINES"}
                for n in nodes
            ]
            data = {"nodes": nodes, "links": links}

        return JSONResponse(content=data)

    @router.get("/graph/symbol/{symbol_id}/neighbors")
    async def code_graph_symbol_neighbors(
        symbol_id: str,
        project_id: str = Query("", description="Project ID"),
        limit: int = Query(50, description="Max neighbors"),
    ) -> JSONResponse:
        """Expand a symbol to show its callers and callees."""
        indexer, pid = _get_indexer_and_project(project_id)
        if indexer is None:
            return JSONResponse(
                status_code=503,
                content={"error": "Code indexer not available"},
            )

        if indexer.graph is None or not indexer.graph.available:
            return JSONResponse(
                content={"nodes": [], "links": [], "note": "Neo4j not available"},
            )

        data = await indexer.graph.get_symbol_neighbors(symbol_id, pid, limit=limit)
        return JSONResponse(content=data)

    @router.get("/graph/blast-radius")
    async def code_graph_blast_radius(
        symbol_name: str | None = Query(None, description="Symbol name"),
        file_path: str | None = Query(None, description="File path"),
        project_id: str = Query("", description="Project ID"),
        depth: int = Query(3, description="Max traversal depth"),
    ) -> JSONResponse:
        """Get blast radius for a symbol or file as graph data."""
        indexer, pid = _get_indexer_and_project(project_id)
        if indexer is None:
            return JSONResponse(
                status_code=503,
                content={"error": "Code indexer not available"},
            )

        if not symbol_name and not file_path:
            return JSONResponse(
                status_code=400,
                content={"error": "Either symbol_name or file_path required"},
            )

        if indexer.graph is None or not indexer.graph.available:
            return JSONResponse(
                content={"nodes": [], "links": [], "center": "", "note": "Neo4j not available"},
            )

        try:
            data = await indexer.graph.get_blast_radius_graph(
                symbol_name=symbol_name,
                file_path=file_path,
                project_id=pid,
                depth=depth,
            )
            return JSONResponse(content=data)
        except ValueError as e:
            return JSONResponse(status_code=400, content={"error": str(e)})

    @router.get("/graph/search")
    async def code_graph_search(
        q: str = Query("", description="Search query"),
        project_id: str = Query("", description="Project ID"),
        limit: int = Query(20, description="Max results"),
    ) -> JSONResponse:
        """Search symbols for graph focus."""
        indexer, pid = _get_indexer_and_project(project_id)
        if indexer is None:
            return JSONResponse(
                status_code=503,
                content={"error": "Code indexer not available"},
            )
        if not q.strip():
            return JSONResponse(content={"results": []})

        results = indexer.storage.search_symbols_for_graph(q, pid, limit=limit)
        return JSONResponse(content={"results": results})

    return router
