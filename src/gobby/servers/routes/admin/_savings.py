"""Savings tracking API endpoints."""

import logging
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter

if TYPE_CHECKING:
    from gobby.servers.http import HTTPServer

logger = logging.getLogger(__name__)


def register_savings_routes(router: APIRouter, server: "HTTPServer") -> None:
    @router.get("/savings")
    async def get_savings(days: int = 1, project_id: str | None = None) -> dict[str, Any]:
        """Get savings summary for the specified time window."""
        tracker = _get_tracker(server)
        if tracker is None:
            return {"error": "Savings tracker not available", "days": days}
        result: dict[str, Any] = tracker.get_summary(days=days, project_id=project_id)
        return result

    @router.get("/savings/cumulative")
    async def get_cumulative_savings(
        days: int = 30, project_id: str | None = None
    ) -> dict[str, Any]:
        """Get cumulative savings over a longer window."""
        tracker = _get_tracker(server)
        if tracker is None:
            return {"error": "Savings tracker not available", "days": days}
        result: dict[str, Any] = tracker.get_cumulative(days=days, project_id=project_id)
        return result

    @router.post("/savings/record")
    async def record_savings(body: dict[str, Any]) -> dict[str, Any]:
        """Record a savings event from an external caller (e.g. gobby compress)."""
        tracker = _get_tracker(server)
        if tracker is None:
            return {"success": False, "error": "Savings tracker not available"}

        category = body.get("category", "")
        if not category:
            return {"success": False, "error": "category is required"}

        # Support both chars and tokens
        if "original_tokens" in body:
            tracker.record_tokens(
                category=category,
                original_tokens=body.get("original_tokens", 0),
                actual_tokens=body.get("actual_tokens", 0),
                session_id=body.get("session_id"),
                project_id=body.get("project_id"),
                model=body.get("model"),
                metadata=body.get("metadata"),
            )
        else:
            tracker.record(
                category=category,
                original_chars=body.get("original_chars", 0),
                actual_chars=body.get("actual_chars", 0),
                session_id=body.get("session_id"),
                project_id=body.get("project_id"),
                model=body.get("model"),
                metadata=body.get("metadata"),
            )

        return {"success": True}


def _get_tracker(server: "HTTPServer") -> Any:
    """Get SavingsTracker from server, creating lazily if needed."""
    tracker = getattr(server, "_savings_tracker", None)
    if tracker is not None:
        return tracker

    try:
        from gobby.savings.tracker import SavingsTracker
        from gobby.storage.model_costs import ModelCostStore

        db = server.services.database
        model_costs = ModelCostStore(db)
        tracker = SavingsTracker(db=db, model_costs=model_costs)
        server._savings_tracker = tracker  # type: ignore[attr-defined]
        return tracker
    except Exception as e:
        logger.warning(f"Failed to create SavingsTracker: {e}")
        return None
