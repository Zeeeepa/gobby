"""Time-filtered dashboard statistics endpoint."""

import logging
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Query

if TYPE_CHECKING:
    from gobby.servers.http import HTTPServer

logger = logging.getLogger(__name__)


def _build_filters(
    hours: int | None,
    days: int,
    project_id: str | None,
    *,
    created_col: str = "created_at",
    project_col: str = "project_id",
) -> tuple[str, list[str]]:
    """Build SQL WHERE fragments and params for time + project filtering."""
    clauses: list[str] = []
    params: list[str] = []

    # Time filter: hours takes precedence over days
    if hours is not None and hours > 0:
        clauses.append(f"AND {created_col} >= datetime('now', ?)")
        params.append(f"-{hours} hours")
    elif hours is None and days > 0:
        clauses.append(f"AND {created_col} >= datetime('now', ?)")
        params.append(f"-{days} days")
    # hours=0 or days=0 means all time — no filter

    if project_id:
        clauses.append(f"AND {project_col} = ?")
        params.append(project_id)

    return " ".join(clauses), params


def register_stats_routes(router: APIRouter, server: "HTTPServer") -> None:
    @router.get("/stats")
    async def get_stats(
        days: int = Query(0, ge=0, le=36500),
        hours: int | None = Query(None, ge=0, le=8760),
        project_id: str | None = Query(None),
    ) -> dict[str, Any]:
        """Get time-filtered counts for tasks, sessions, and memory.

        Args:
            days: Time window in days. 0 = all time. Ignored when hours is set.
            hours: Time window in hours. 0 = all time. Takes precedence over days.
            project_id: Filter to a specific project.
        """
        db = server.services.database
        time_filter, params = _build_filters(hours, days, project_id)

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
                tuple(params),
            )
            for row in rows:
                status = row["status"]
                if status in task_stats:
                    task_stats[status] = row["cnt"]

            # Ready = open tasks with no unresolved blocking deps
            tf_aliased = time_filter.replace("created_at", "t.created_at").replace(
                "project_id", "t.project_id"
            )
            ready_rows = db.fetchall(
                "SELECT COUNT(*) as cnt FROM tasks t "
                "WHERE t.status = 'open' "
                f"{tf_aliased} "
                "AND NOT EXISTS ("
                "  SELECT 1 FROM task_dependencies td "
                "  JOIN tasks blocker ON td.depends_on = blocker.id "
                "  WHERE td.task_id = t.id AND blocker.status != 'closed'"
                ")",
                tuple(params),
            )
            task_stats["ready"] = ready_rows[0]["cnt"] if ready_rows else 0

            # Blocked = open/in_progress tasks with unresolved blocking deps
            blocked_rows = db.fetchall(
                "SELECT COUNT(*) as cnt FROM tasks t "
                "WHERE t.status IN ('open', 'in_progress') "
                f"{tf_aliased} "
                "AND EXISTS ("
                "  SELECT 1 FROM task_dependencies td "
                "  JOIN tasks blocker ON td.depends_on = blocker.id "
                "  WHERE td.task_id = t.id AND blocker.status != 'closed'"
                ")",
                tuple(params),
            )
            task_stats["blocked"] = blocked_rows[0]["cnt"] if blocked_rows else 0

            # Closed in last 24h (always relative to now, intersected with window)
            closed_24h_rows = db.fetchall(
                "SELECT COUNT(*) as cnt FROM tasks "
                f"WHERE closed_at >= datetime('now', '-1 days') {time_filter}",
                tuple(params),
            )
            task_stats["closed_24h"] = closed_24h_rows[0]["cnt"] if closed_24h_rows else 0
        except Exception as e:
            logger.warning(f"Failed to get time-filtered task stats: {e}")

        # --- Sessions ---
        session_stats: dict[str, Any] = {
            "active": 0,
            "paused": 0,
            "handoff_ready": 0,
            "total": 0,
            "by_source": {},
        }
        try:
            rows = db.fetchall(
                f"SELECT status, COUNT(*) as cnt FROM sessions "
                f"WHERE 1=1 {time_filter} GROUP BY status",
                tuple(params),
            )
            total = 0
            for row in rows:
                status = row["status"]
                total += row["cnt"]
                if status in session_stats and status != "by_source":
                    session_stats[status] = row["cnt"]
            session_stats["total"] = total

            # By-source breakdown
            by_source: dict[str, dict[str, int]] = {}
            source_rows = db.fetchall(
                "SELECT source, status, COUNT(*) as cnt FROM sessions "
                f"WHERE 1=1 {time_filter} "
                "GROUP BY source, status",
                tuple(params),
            )
            for row in source_rows:
                src = row["source"] or "unknown"
                st = row["status"] or "unknown"
                if src not in by_source:
                    by_source[src] = {}
                by_source[src][st] = row["cnt"]
            session_stats["by_source"] = by_source
        except Exception as e:
            logger.warning(f"Failed to get time-filtered session stats: {e}")

        # --- Memory ---
        memory_stats: dict[str, Any] = {"count": 0, "by_type": {}, "recent_count": 0}
        try:
            rows = db.fetchall(
                f"SELECT memory_type, COUNT(*) as cnt FROM memories "
                f"WHERE 1=1 {time_filter} GROUP BY memory_type",
                tuple(params),
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
                tuple(params),
            )
            memory_stats["recent_count"] = recent_rows[0]["cnt"] if recent_rows else 0
        except Exception as e:
            logger.warning(f"Failed to get time-filtered memory stats: {e}")

        return {
            "days": days,
            "hours": hours,
            "tasks": task_stats,
            "sessions": session_stats,
            "memory": memory_stats,
        }
