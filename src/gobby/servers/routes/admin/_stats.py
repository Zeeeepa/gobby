"""Time-filtered dashboard statistics endpoint."""

import logging
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Query

if TYPE_CHECKING:
    from gobby.servers.http import HTTPServer

logger = logging.getLogger(__name__)


def register_stats_routes(router: APIRouter, server: "HTTPServer") -> None:
    @router.get("/stats")
    async def get_stats(days: int = Query(0, ge=0, le=36500)) -> dict[str, Any]:
        """Get time-filtered counts for tasks, sessions, and memory.

        Args:
            days: Time window in days. 0 = all time (no filter).
        """
        db = server.services.database
        time_filter = ""
        params: tuple[str, ...] = ()
        if days > 0:
            time_filter = "AND created_at >= datetime('now', ?)"
            params = (f"-{days} days",)

        # --- Tasks ---
        task_stats: dict[str, Any] = {
            "open": 0,
            "in_progress": 0,
            "closed": 0,
            "needs_review": 0,
            "review_approved": 0,
            "escalated": 0,
            "ready": 0,
            "blocked": 0,
            "closed_24h": 0,
        }
        try:
            rows = db.fetchall(
                f"SELECT status, COUNT(*) as cnt FROM tasks "
                f"WHERE 1=1 {time_filter} GROUP BY status",
                params,
            )
            for row in rows:
                status = row["status"]
                if status in task_stats:
                    task_stats[status] = row["cnt"]

            # Ready = open tasks with no unresolved blocking deps
            ready_rows = db.fetchall(
                "SELECT COUNT(*) as cnt FROM tasks t "
                "WHERE t.status = 'open' "
                f"{time_filter.replace('created_at', 't.created_at')} "
                "AND NOT EXISTS ("
                "  SELECT 1 FROM task_dependencies td "
                "  JOIN tasks blocker ON td.depends_on_task_id = blocker.id "
                "  WHERE td.task_id = t.id AND blocker.status != 'closed'"
                ")",
                params,
            )
            task_stats["ready"] = ready_rows[0]["cnt"] if ready_rows else 0

            # Blocked = open/in_progress tasks with unresolved blocking deps
            blocked_rows = db.fetchall(
                "SELECT COUNT(*) as cnt FROM tasks t "
                "WHERE t.status IN ('open', 'in_progress') "
                f"{time_filter.replace('created_at', 't.created_at')} "
                "AND EXISTS ("
                "  SELECT 1 FROM task_dependencies td "
                "  JOIN tasks blocker ON td.depends_on_task_id = blocker.id "
                "  WHERE td.task_id = t.id AND blocker.status != 'closed'"
                ")",
                params,
            )
            task_stats["blocked"] = blocked_rows[0]["cnt"] if blocked_rows else 0

            # Closed in last 24h (always relative to now, not the window)
            closed_24h_rows = db.fetchall(
                "SELECT COUNT(*) as cnt FROM tasks "
                f"WHERE closed_at >= datetime('now', '-1 days') {time_filter}",
                params,
            )
            task_stats["closed_24h"] = closed_24h_rows[0]["cnt"] if closed_24h_rows else 0
        except Exception as e:
            logger.warning(f"Failed to get time-filtered task stats: {e}")

        # --- Sessions ---
        session_stats: dict[str, Any] = {"active": 0, "paused": 0, "handoff_ready": 0, "total": 0}
        try:
            rows = db.fetchall(
                f"SELECT status, COUNT(*) as cnt FROM sessions "
                f"WHERE 1=1 {time_filter} GROUP BY status",
                params,
            )
            total = 0
            for row in rows:
                status = row["status"]
                total += row["cnt"]
                if status in session_stats:
                    session_stats[status] = row["cnt"]
            session_stats["total"] = total
        except Exception as e:
            logger.warning(f"Failed to get time-filtered session stats: {e}")

        # --- Memory ---
        memory_stats: dict[str, Any] = {"count": 0, "by_type": {}, "recent_count": 0}
        try:
            rows = db.fetchall(
                f"SELECT memory_type, COUNT(*) as cnt FROM memories "
                f"WHERE 1=1 {time_filter} GROUP BY memory_type",
                params,
            )
            total = 0
            by_type: dict[str, int] = {}
            for row in rows:
                mtype = row["memory_type"]
                cnt = row["cnt"]
                by_type[mtype] = cnt
                total += cnt
            memory_stats["count"] = total
            memory_stats["by_type"] = by_type

            # Recent = created in last 24h (within the filtered set)
            recent_rows = db.fetchall(
                "SELECT COUNT(*) as cnt FROM memories "
                f"WHERE created_at >= datetime('now', '-1 days') {time_filter}",
                params,
            )
            memory_stats["recent_count"] = recent_rows[0]["cnt"] if recent_rows else 0
        except Exception as e:
            logger.warning(f"Failed to get time-filtered memory stats: {e}")

        return {
            "days": days,
            "tasks": task_stats,
            "sessions": session_stats,
            "memory": memory_stats,
        }
