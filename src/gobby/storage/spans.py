from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gobby.storage.database import DatabaseProtocol

logger = logging.getLogger(__name__)


class SpanStorage:
    """Storage manager for OpenTelemetry spans in SQLite."""

    def __init__(self, db: DatabaseProtocol) -> None:
        self.db = db

    def save_span(self, span_data: dict[str, Any]) -> None:
        """Insert a single span record."""
        self.save_spans([span_data])

    def save_spans(self, spans: list[dict[str, Any]]) -> None:
        """Batch insert multiple span records."""
        if not spans:
            return

        query = """
        INSERT INTO spans (
            span_id, trace_id, parent_span_id, name, kind,
            start_time_ns, end_time_ns, status, status_message,
            attributes_json, events_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        rows = []
        for s in spans:
            rows.append(
                (
                    s["span_id"],
                    s["trace_id"],
                    s.get("parent_span_id"),
                    s["name"],
                    s.get("kind"),
                    s["start_time_ns"],
                    s.get("end_time_ns"),
                    s.get("status"),
                    s.get("status_message"),
                    json.dumps(s.get("attributes", {})),
                    json.dumps(s.get("events", [])),
                )
            )

        try:
            self.db.executemany(query, rows)
        except Exception as e:
            logger.error(f"Failed to save spans: {e}")
            raise

    def get_trace(self, trace_id: str) -> list[dict[str, Any]]:
        """Retrieve all spans for a trace, ordered by start time."""
        query = "SELECT * FROM spans WHERE trace_id = ? ORDER BY start_time_ns ASC"
        rows = self.db.fetchall(query, (trace_id,))
        return [self._row_to_dict(row) for row in rows]

    def get_recent_traces(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        """Retrieve recent traces, represented by their root (earliest) span."""
        # Get unique trace_ids ordered by their latest span's start time
        query = """
        SELECT trace_id, MAX(start_time_ns) as last_activity
        FROM spans
        GROUP BY trace_id
        ORDER BY last_activity DESC
        LIMIT ? OFFSET ?
        """
        trace_rows = self.db.fetchall(query, (limit, offset))

        results = []
        for tr in trace_rows:
            trace_id = tr["trace_id"]
            # Find the root/earliest span for this trace
            root_query = "SELECT * FROM spans WHERE trace_id = ? ORDER BY start_time_ns ASC LIMIT 1"
            root_row = self.db.fetchone(root_query, (trace_id,))
            if root_row:
                results.append(self._row_to_dict(root_row))

        return results

    def get_traces_by_session(self, session_id: str) -> list[dict[str, Any]]:
        """Retrieve traces that have a matching session_id in their attributes."""
        # Use SQLite json_extract to filter by session_id in attributes_json
        query = """
        SELECT DISTINCT trace_id FROM spans
        WHERE json_extract(attributes_json, '$.session_id') = ?
        """
        trace_ids = self.db.fetchall(query, (session_id,))

        results = []
        for tr in trace_ids:
            trace_id = tr["trace_id"]
            root_query = "SELECT * FROM spans WHERE trace_id = ? ORDER BY start_time_ns ASC LIMIT 1"
            root_row = self.db.fetchone(root_query, (trace_id,))
            if root_row:
                results.append(self._row_to_dict(root_row))
        return results

    def delete_old_spans(self, retention_days: int = 7) -> int:
        """Delete spans older than the specified retention period."""
        query = "DELETE FROM spans WHERE created_at < datetime('now', ?)"
        cursor = self.db.execute(query, (f"-{retention_days} days",))
        return cursor.rowcount

    def get_span_count(self) -> int:
        """Return the total number of spans in storage."""
        row = self.db.fetchone("SELECT COUNT(*) as count FROM spans")
        return row["count"] if row else 0

    def _row_to_dict(self, row: Any) -> dict[str, Any]:
        """Convert a database row to a dictionary with parsed JSON fields."""
        d = dict(row)
        if "attributes_json" in d:
            d["attributes"] = json.loads(d.pop("attributes_json") or "{}")
        if "events_json" in d:
            d["events"] = json.loads(d.pop("events_json") or "[]")
        return d
