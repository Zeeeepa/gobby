from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, Query

from gobby.storage.spans import SpanStorage

if TYPE_CHECKING:
    from gobby.servers.http import HTTPServer

logger = logging.getLogger(__name__)


def create_traces_router(server: HTTPServer) -> APIRouter:
    """Create the traces API router."""
    router = APIRouter(prefix="/api/traces", tags=["traces"])

    def _get_storage() -> SpanStorage:
        """Get SpanStorage from the server's database."""
        # We can either use server.services.database or a dedicated span_storage if added to ServiceContainer
        # For now, we'll use the database directly to avoid extensive app_context.py changes if not needed
        if server.services.database is None:
            raise HTTPException(503, "Database not available")
        return SpanStorage(server.services.database)

    @router.get("")
    async def list_traces(
        session_id: str | None = Query(None, description="Filter by session ID"),
        limit: int = Query(50, ge=1, le=1000, description="Maximum results"),
        offset: int = Query(0, ge=0, description="Pagination offset"),
    ) -> dict[str, Any]:
        """List recent traces with optional filters."""
        storage = _get_storage()

        if session_id:
            # Filter traces by session_id in attributes
            traces = storage.get_traces_by_session(session_id)
            total = len(traces)
            # Apply manual pagination for session-filtered traces
            traces = traces[offset : offset + limit]
        else:
            # Get latest traces globally
            traces = storage.get_recent_traces(limit=limit, offset=offset)
            total = storage.get_span_count()  # Approximate total trace count using span count

        return {
            "traces": traces,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    @router.get("/{trace_id}")
    async def get_trace(trace_id: str) -> dict[str, Any]:
        """Get full span tree for a specific trace."""
        storage = _get_storage()
        spans = storage.get_trace(trace_id)

        if not spans:
            raise HTTPException(404, f"Trace {trace_id} not found")

        # Identify root span (parent_span_id is None)
        root_span = next((s for s in spans if s.get("parent_span_id") is None), None)
        if not root_span and spans:
            # Fallback to earliest span if no explicit root found
            root_span = spans[0]

        return {
            "trace_id": trace_id,
            "spans": spans,
            "root_span": root_span,
        }

    return router
