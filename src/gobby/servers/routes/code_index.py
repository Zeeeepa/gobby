"""Code index routes for Gobby HTTP server.

Provides the invalidate endpoint used by gcode for full-project wipes.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

if TYPE_CHECKING:
    from gobby.servers.http import HTTPServer

logger = logging.getLogger(__name__)


class InvalidateIndexRequest(BaseModel):
    """Request body for POST /api/code-index/invalidate."""

    project_id: str


def create_code_index_router(server: HTTPServer) -> APIRouter:
    """Create code index router."""
    router = APIRouter(prefix="/api/code-index", tags=["code-index"])

    @router.post("/invalidate")
    async def invalidate_index(body: InvalidateIndexRequest) -> JSONResponse:
        """Clear all index data for a project. Called by gcode invalidate."""
        services = server.services
        code_indexer = getattr(services, "code_indexer", None)

        if code_indexer is None:
            return JSONResponse(
                status_code=503,
                content={"error": "Code indexer not available"},
            )

        project_id = body.project_id
        if not project_id:
            return JSONResponse(
                status_code=400,
                content={"error": "project_id is required"},
            )

        # If project isn't indexed, that's already the desired state — be idempotent
        stats = await asyncio.to_thread(code_indexer.storage.get_project_stats, project_id)
        if stats is None:
            return JSONResponse(
                content={"status": "ok", "project_id": project_id, "note": "not indexed"},
            )

        await code_indexer.invalidate(project_id)

        return JSONResponse(content={"status": "ok", "project_id": project_id})

    return router
