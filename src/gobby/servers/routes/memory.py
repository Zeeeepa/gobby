"""
Memory routes for Gobby HTTP server.

Provides CRUD, search, and stats endpoints for the memory system.
"""

import logging
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from gobby.utils.metrics import get_metrics_collector

if TYPE_CHECKING:
    from gobby.servers.http import HTTPServer

logger = logging.getLogger(__name__)


# =============================================================================
# Request/Response models
# =============================================================================


class MemoryCreateRequest(BaseModel):
    """Request body for creating a memory."""

    content: str = Field(..., description="Memory content text")
    memory_type: str = Field(
        default="fact", description="Memory type (fact, preference, pattern, context)"
    )
    importance: float = Field(default=0.5, description="Importance score (0.0-1.0)")
    project_id: str | None = Field(default=None, description="Project ID to associate with")
    source_type: str = Field(default="user", description="Source type (user, session, inferred)")
    source_session_id: str | None = Field(default=None, description="Source session ID")
    tags: list[str] | None = Field(default=None, description="Tags for categorization")


class MemoryUpdateRequest(BaseModel):
    """Request body for updating a memory."""

    content: str | None = Field(default=None, description="New content text")
    importance: float | None = Field(default=None, description="New importance score")
    tags: list[str] | None = Field(default=None, description="New tags")


# =============================================================================
# Router
# =============================================================================


def create_memory_router(server: "HTTPServer") -> APIRouter:
    """Create memory router with endpoints bound to server instance."""
    router = APIRouter(prefix="/memories", tags=["memories"])
    metrics = get_metrics_collector()

    @router.get("")
    async def list_memories(
        project_id: str | None = Query(None, description="Filter by project ID"),
        memory_type: str | None = Query(None, description="Filter by memory type"),
        min_importance: float | None = Query(None, description="Minimum importance"),
        limit: int = Query(50, description="Maximum results"),
        offset: int = Query(0, description="Pagination offset"),
    ) -> dict[str, Any]:
        """List memories with optional filters."""
        metrics.inc_counter("http_requests_total")
        memories = server.memory_manager.list_memories(
            project_id=project_id,
            memory_type=memory_type,
            min_importance=min_importance,
            limit=limit,
            offset=offset,
        )
        return {"memories": [m.to_dict() for m in memories]}

    @router.post("", status_code=201)
    async def create_memory(request_data: MemoryCreateRequest) -> Any:
        """Create a new memory."""
        metrics.inc_counter("http_requests_total")
        try:
            memory = await server.memory_manager.remember(
                content=request_data.content,
                memory_type=request_data.memory_type,
                importance=request_data.importance,
                project_id=request_data.project_id,
                source_type=request_data.source_type,
                source_session_id=request_data.source_session_id,
                tags=request_data.tags,
            )
            return memory.to_dict()
        except Exception as e:
            logger.error(f"Failed to create memory: {e}")
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.get("/search")
    async def search_memories(
        q: str = Query(..., description="Search query"),
        project_id: str | None = Query(None, description="Filter by project ID"),
        limit: int = Query(10, description="Maximum results"),
        min_importance: float = Query(0.0, description="Minimum importance"),
    ) -> dict[str, Any]:
        """Search memories by query."""
        metrics.inc_counter("http_requests_total")
        results = server.memory_manager.recall(
            query=q,
            project_id=project_id,
            limit=limit,
            min_importance=min_importance,
        )
        return {
            "query": q,
            "results": [m.to_dict() for m in results],
            "count": len(results),
        }

    @router.get("/stats")
    async def memory_stats(
        project_id: str | None = Query(None, description="Filter by project ID"),
    ) -> Any:
        """Get memory statistics."""
        metrics.inc_counter("http_requests_total")
        return server.memory_manager.get_stats(project_id=project_id)

    @router.get("/{memory_id}")
    async def get_memory(memory_id: str) -> Any:
        """Get a specific memory by ID."""
        metrics.inc_counter("http_requests_total")
        memory = server.memory_manager.get_memory(memory_id)
        if memory is None:
            raise HTTPException(status_code=404, detail="Memory not found")
        return memory.to_dict()

    @router.put("/{memory_id}")
    async def update_memory(memory_id: str, request_data: MemoryUpdateRequest) -> Any:
        """Update an existing memory."""
        metrics.inc_counter("http_requests_total")
        try:
            memory = server.memory_manager.update_memory(
                memory_id=memory_id,
                content=request_data.content,
                importance=request_data.importance,
                tags=request_data.tags,
            )
            return memory.to_dict()
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.delete("/{memory_id}")
    async def delete_memory(memory_id: str) -> dict[str, Any]:
        """Delete a memory."""
        metrics.inc_counter("http_requests_total")
        result = server.memory_manager.forget(memory_id)
        if not result:
            raise HTTPException(status_code=404, detail="Memory not found")
        return {"deleted": True, "id": memory_id}

    return router
