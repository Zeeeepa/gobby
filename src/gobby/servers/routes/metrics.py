"""Metrics API routes for dashboard time-series and live data."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, Query

from gobby.storage.metric_snapshots import MetricSnapshotStorage
from gobby.telemetry.instruments import get_all_metrics, update_daemon_metrics

if TYPE_CHECKING:
    from gobby.servers.http import HTTPServer

logger = logging.getLogger(__name__)


def create_metrics_router(server: HTTPServer) -> APIRouter:
    """Create the metrics API router."""
    router = APIRouter(prefix="/api/metrics", tags=["metrics"])

    def _get_storage() -> MetricSnapshotStorage:
        if server.services.database is None:
            raise HTTPException(503, "Database not available")
        return MetricSnapshotStorage(server.services.database)

    @router.get("/snapshots")
    async def get_snapshots(
        hours: int = Query(1, ge=1, le=24, description="Hours of history"),
        limit: int = Query(120, ge=1, le=1440, description="Max snapshots"),
    ) -> dict[str, Any]:
        """Get time-series metric snapshots for charts."""
        storage = _get_storage()
        snapshots = storage.get_snapshots(hours=hours, limit=limit)
        return {
            "snapshots": snapshots,
            "count": len(snapshots),
            "hours": hours,
        }

    @router.get("/current")
    async def get_current() -> dict[str, Any]:
        """Get live point-in-time metrics."""
        update_daemon_metrics()
        return get_all_metrics()

    return router
