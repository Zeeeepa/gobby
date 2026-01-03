"""Tool metrics tracking for MCP proxy."""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from gobby.storage.database import LocalDatabase

logger = logging.getLogger(__name__)

# Default retention period for metrics
DEFAULT_RETENTION_DAYS = 7


@dataclass
class ToolMetrics:
    """Tool metrics data model."""

    id: str
    project_id: str
    server_name: str
    tool_name: str
    call_count: int
    success_count: int
    failure_count: int
    total_latency_ms: float
    avg_latency_ms: float | None
    last_called_at: str | None
    created_at: str
    updated_at: str

    @classmethod
    def from_row(cls, row: Any) -> "ToolMetrics":
        """Create ToolMetrics from database row."""
        return cls(
            id=row["id"],
            project_id=row["project_id"],
            server_name=row["server_name"],
            tool_name=row["tool_name"],
            call_count=row["call_count"],
            success_count=row["success_count"],
            failure_count=row["failure_count"],
            total_latency_ms=row["total_latency_ms"],
            avg_latency_ms=row["avg_latency_ms"],
            last_called_at=row["last_called_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "project_id": self.project_id,
            "server_name": self.server_name,
            "tool_name": self.tool_name,
            "call_count": self.call_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "total_latency_ms": self.total_latency_ms,
            "avg_latency_ms": self.avg_latency_ms,
            "success_rate": (
                self.success_count / self.call_count if self.call_count > 0 else None
            ),
            "last_called_at": self.last_called_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class ToolMetricsManager:
    """
    Manager for tracking tool call metrics.

    Tracks call counts, success/failure rates, and latency for MCP tools.
    Metrics are persisted to SQLite and can be used for tool recommendations.
    """

    def __init__(self, db: LocalDatabase):
        """
        Initialize the metrics manager.

        Args:
            db: LocalDatabase instance for persistence
        """
        self.db = db

    def record_call(
        self,
        server_name: str,
        tool_name: str,
        project_id: str,
        latency_ms: float,
        success: bool = True,
    ) -> None:
        """
        Record a tool call with its metrics.

        Args:
            server_name: Name of the MCP server
            tool_name: Name of the tool
            project_id: Project ID the call was made from
            latency_ms: Execution time in milliseconds
            success: Whether the call succeeded
        """
        now = datetime.now(UTC).isoformat()

        # Check if metrics row exists for this tool
        row = self.db.fetchone(
            """
            SELECT id, call_count, success_count, failure_count, total_latency_ms
            FROM tool_metrics
            WHERE project_id = ? AND server_name = ? AND tool_name = ?
            """,
            (project_id, server_name, tool_name),
        )

        if row:
            # Update existing metrics
            new_call_count = row["call_count"] + 1
            new_success_count = row["success_count"] + (1 if success else 0)
            new_failure_count = row["failure_count"] + (0 if success else 1)
            new_total_latency = row["total_latency_ms"] + latency_ms
            new_avg_latency = new_total_latency / new_call_count

            self.db.execute(
                """
                UPDATE tool_metrics
                SET call_count = ?,
                    success_count = ?,
                    failure_count = ?,
                    total_latency_ms = ?,
                    avg_latency_ms = ?,
                    last_called_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    new_call_count,
                    new_success_count,
                    new_failure_count,
                    new_total_latency,
                    new_avg_latency,
                    now,
                    now,
                    row["id"],
                ),
            )
        else:
            # Create new metrics row
            metrics_id = f"tm-{uuid.uuid4().hex[:6]}"
            self.db.execute(
                """
                INSERT INTO tool_metrics (
                    id, project_id, server_name, tool_name,
                    call_count, success_count, failure_count,
                    total_latency_ms, avg_latency_ms,
                    last_called_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    metrics_id,
                    project_id,
                    server_name,
                    tool_name,
                    1,
                    1 if success else 0,
                    0 if success else 1,
                    latency_ms,
                    latency_ms,  # avg = total for first call
                    now,
                    now,
                    now,
                ),
            )

    def get_metrics(
        self,
        project_id: str | None = None,
        server_name: str | None = None,
        tool_name: str | None = None,
    ) -> dict[str, Any]:
        """
        Get metrics, optionally filtered by project/server/tool.

        Args:
            project_id: Filter by project ID
            server_name: Filter by server name
            tool_name: Filter by tool name

        Returns:
            Dictionary with metrics data including per-tool stats
        """
        conditions = []
        params: list[Any] = []

        if project_id:
            conditions.append("project_id = ?")
            params.append(project_id)
        if server_name:
            conditions.append("server_name = ?")
            params.append(server_name)
        if tool_name:
            conditions.append("tool_name = ?")
            params.append(tool_name)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        rows = self.db.fetchall(
            f"""
            SELECT * FROM tool_metrics
            WHERE {where_clause}
            ORDER BY call_count DESC
            """,
            tuple(params),
        )

        tools = [ToolMetrics.from_row(row).to_dict() for row in rows]

        # Calculate aggregates
        total_calls = sum(t["call_count"] for t in tools)
        total_success = sum(t["success_count"] for t in tools)
        total_failure = sum(t["failure_count"] for t in tools)
        total_latency = sum(t["total_latency_ms"] for t in tools)

        return {
            "tools": tools,
            "summary": {
                "total_tools": len(tools),
                "total_calls": total_calls,
                "total_success": total_success,
                "total_failure": total_failure,
                "overall_success_rate": (
                    total_success / total_calls if total_calls > 0 else None
                ),
                "overall_avg_latency_ms": (
                    total_latency / total_calls if total_calls > 0 else None
                ),
            },
        }

    def get_top_tools(
        self,
        project_id: str | None = None,
        limit: int = 10,
        order_by: str = "call_count",
    ) -> list[dict[str, Any]]:
        """
        Get top tools by call count or other metrics.

        Args:
            project_id: Filter by project ID
            limit: Maximum number of tools to return
            order_by: Column to sort by (call_count, success_count, avg_latency_ms)

        Returns:
            List of tool metrics sorted by the specified column
        """
        valid_order_columns = {"call_count", "success_count", "avg_latency_ms"}
        if order_by not in valid_order_columns:
            order_by = "call_count"

        if project_id:
            rows = self.db.fetchall(
                f"""
                SELECT * FROM tool_metrics
                WHERE project_id = ?
                ORDER BY {order_by} DESC
                LIMIT ?
                """,
                (project_id, limit),
            )
        else:
            rows = self.db.fetchall(
                f"""
                SELECT * FROM tool_metrics
                ORDER BY {order_by} DESC
                LIMIT ?
                """,
                (limit,),
            )

        return [ToolMetrics.from_row(row).to_dict() for row in rows]

    def get_tool_success_rate(
        self,
        server_name: str,
        tool_name: str,
        project_id: str,
    ) -> float | None:
        """
        Get success rate for a specific tool.

        Args:
            server_name: Name of the MCP server
            tool_name: Name of the tool
            project_id: Project ID

        Returns:
            Success rate as a float between 0 and 1, or None if no data
        """
        row = self.db.fetchone(
            """
            SELECT success_count, call_count
            FROM tool_metrics
            WHERE project_id = ? AND server_name = ? AND tool_name = ?
            """,
            (project_id, server_name, tool_name),
        )

        if row and row["call_count"] > 0:
            return row["success_count"] / row["call_count"]
        return None

    def reset_metrics(
        self,
        project_id: str | None = None,
        server_name: str | None = None,
    ) -> int:
        """
        Reset/delete metrics.

        Args:
            project_id: Reset only for this project
            server_name: Reset only for this server

        Returns:
            Number of rows deleted
        """
        conditions = []
        params: list[Any] = []

        if project_id:
            conditions.append("project_id = ?")
            params.append(project_id)
        if server_name:
            conditions.append("server_name = ?")
            params.append(server_name)

        if conditions:
            where_clause = " AND ".join(conditions)
            cursor = self.db.execute(
                f"DELETE FROM tool_metrics WHERE {where_clause}",
                tuple(params),
            )
        else:
            cursor = self.db.execute("DELETE FROM tool_metrics")

        return cursor.rowcount

    def cleanup_old_metrics(self, retention_days: int = DEFAULT_RETENTION_DAYS) -> int:
        """
        Delete metrics older than the retention period.

        Deletes metrics where last_called_at is older than retention_days.
        This helps keep the database size manageable while preserving
        recent tool usage patterns.

        Args:
            retention_days: Number of days to retain metrics (default: 7)

        Returns:
            Number of rows deleted
        """
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        cutoff_str = cutoff.isoformat()

        cursor = self.db.execute(
            """
            DELETE FROM tool_metrics
            WHERE last_called_at < ?
            """,
            (cutoff_str,),
        )

        deleted = cursor.rowcount
        if deleted > 0:
            logger.info(f"Metrics cleanup: deleted {deleted} stale metrics (older than {retention_days} days)")
        return deleted

    def get_retention_stats(self) -> dict[str, Any]:
        """
        Get statistics about metrics retention.

        Returns:
            Dictionary with retention statistics including oldest/newest metrics
        """
        row = self.db.fetchone(
            """
            SELECT
                COUNT(*) as total_count,
                MIN(last_called_at) as oldest,
                MAX(last_called_at) as newest,
                SUM(call_count) as total_calls
            FROM tool_metrics
            """
        )

        if row:
            return {
                "total_metrics": row["total_count"],
                "oldest_metric": row["oldest"],
                "newest_metric": row["newest"],
                "total_calls_recorded": row["total_calls"],
            }
        return {
            "total_metrics": 0,
            "oldest_metric": None,
            "newest_metric": None,
            "total_calls_recorded": 0,
        }
