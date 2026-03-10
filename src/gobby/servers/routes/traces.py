from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, Query

from gobby.storage.spans import SpanStorage

if TYPE_CHECKING:
    from gobby.servers.http import HTTPServer

logger = logging.getLogger(__name__)


def _span_to_trace_record(span: dict[str, Any]) -> dict[str, Any]:
    """Transform a raw span dict into the TraceRecord shape the frontend expects."""
    start_ns = span.get("start_time_ns", 0)
    end_ns = span.get("end_time_ns", 0)
    duration_ms = (end_ns - start_ns) / 1_000_000 if end_ns and start_ns else 0
    attrs = span.get("attributes", {})
    if isinstance(attrs, str):
        attrs = json.loads(attrs) if attrs else {}
    return {
        "id": span.get("id", span.get("span_id", "")),
        "project_id": attrs.get("project_id", ""),
        "trace_id": span["trace_id"],
        "root_span_name": span.get("name", "Unknown"),
        "status": span.get("status", "UNSET"),
        "start_time_ns": start_ns,
        "end_time_ns": end_ns,
        "duration_ms": round(duration_ms, 2),
        "timestamp": span.get("created_at", ""),
    }


def _span_to_span_record(span: dict[str, Any]) -> dict[str, Any]:
    """Transform a raw span dict into the SpanRecord shape the frontend expects."""
    result = {
        "id": span.get("id", span.get("span_id", "")),
        "trace_id": span.get("trace_id", ""),
        "span_id": span.get("span_id", ""),
        "parent_id": span.get("parent_span_id"),
        "name": span.get("name", ""),
        "kind": span.get("kind", ""),
        "status": span.get("status", "UNSET"),
        "start_time_ns": span.get("start_time_ns", 0),
        "end_time_ns": span.get("end_time_ns", 0),
        "attributes_json": _ensure_json_string(
            span.get("attributes", span.get("attributes_json", "{}"))
        ),
        "events_json": _ensure_json_string(span.get("events", span.get("events_json", "[]"))),
    }
    return result


def _ensure_json_string(value: Any) -> str:
    """Ensure a value is a JSON string — pass through strings, serialize dicts/lists."""
    if isinstance(value, str):
        return value
    return json.dumps(value) if value is not None else "{}"


def create_traces_router(server: HTTPServer) -> APIRouter:
    """Create the traces API router."""
    router = APIRouter(prefix="/api/traces", tags=["traces"])

    def _get_storage() -> SpanStorage:
        """Get SpanStorage from the ServiceContainer."""
        if server.services.span_storage is not None:
            return server.services.span_storage  # type: ignore[no-any-return]
        if server.services.database is None:
            raise HTTPException(503, "Database not available")
        return SpanStorage(server.services.database)

    @router.get("")
    async def list_traces(
        session_id: str | None = Query(None, description="Filter by session ID"),
        project_id: str | None = Query(None, description="Filter by project ID"),
        status: str | None = Query(None, description="Filter by span status (OK, ERROR, UNSET)"),
        limit: int = Query(50, ge=1, le=1000, description="Maximum results"),
        offset: int = Query(0, ge=0, description="Pagination offset"),
    ) -> dict[str, Any]:
        """List recent traces with optional filters."""
        storage = _get_storage()

        if session_id:
            traces = storage.get_traces_by_session(session_id, limit=limit, offset=offset)
            total = storage.get_trace_count_by_session(session_id)
        else:
            traces = storage.get_recent_traces(
                limit=limit,
                offset=offset,
                project_id=project_id,
                status=status,
            )
            total = storage.get_span_count()

        return {
            "traces": [_span_to_trace_record(t) for t in traces],
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

        root_span = next((s for s in spans if s.get("parent_span_id") is None), None)
        if not root_span and spans:
            root_span = spans[0]

        return {
            "trace_id": trace_id,
            "spans": [_span_to_span_record(s) for s in spans],
            "root_span": _span_to_span_record(root_span) if root_span else None,
        }

    return router
