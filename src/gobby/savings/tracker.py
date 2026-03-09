"""SavingsTracker — records and summarizes token/cost savings."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gobby.storage.database import DatabaseProtocol
    from gobby.storage.model_costs import ModelCostStore

logger = logging.getLogger(__name__)

# Empirical chars-per-token for code-heavy content
CHARS_PER_TOKEN = 3.7


class SavingsTracker:
    """Track token and cost savings from Gobby features.

    Savings categories:
    - compression: tool output compression
    - code_index: symbol retrieval vs full file read
    - discovery: progressive schema loading
    - handoff: context preservation across compactions
    - memory: instant recall vs re-discovery
    """

    def __init__(self, db: DatabaseProtocol, model_costs: ModelCostStore | None = None) -> None:
        self.db = db
        self._model_costs = model_costs

    def record(
        self,
        category: str,
        original_chars: int,
        actual_chars: int,
        session_id: str | None = None,
        project_id: str | None = None,
        model: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record a savings event using character counts (converted to tokens)."""
        original_tokens = max(0, int(original_chars / CHARS_PER_TOKEN))
        actual_tokens = max(0, int(actual_chars / CHARS_PER_TOKEN))
        self.record_tokens(
            category=category,
            original_tokens=original_tokens,
            actual_tokens=actual_tokens,
            session_id=session_id,
            project_id=project_id,
            model=model,
            metadata=metadata,
        )

    def record_tokens(
        self,
        category: str,
        original_tokens: int,
        actual_tokens: int,
        session_id: str | None = None,
        project_id: str | None = None,
        model: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record a savings event using token counts."""
        tokens_saved = max(0, original_tokens - actual_tokens)
        cost_saved = self._estimate_cost(tokens_saved, model)

        self.db.execute(
            "INSERT INTO savings_ledger "
            "(session_id, project_id, category, original_tokens, actual_tokens, "
            "tokens_saved, cost_saved_usd, model, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session_id,
                project_id,
                category,
                original_tokens,
                actual_tokens,
                tokens_saved,
                cost_saved,
                model,
                json.dumps(metadata) if metadata else None,
            ),
        )

    def get_summary(self, days: int = 1, project_id: str | None = None) -> dict[str, Any]:
        """Get savings summary for the specified time window."""
        params: list[Any] = [f"-{days} days"]

        project_filter = ""
        if project_id:
            project_filter = "AND project_id = ?"
            params.append(project_id)

        # Recent ledger entries
        rows = self.db.fetchall(
            f"SELECT category, "
            f"SUM(original_tokens) as original_tokens, "
            f"SUM(actual_tokens) as actual_tokens, "
            f"SUM(tokens_saved) as tokens_saved, "
            f"SUM(cost_saved_usd) as cost_saved_usd, "
            f"COUNT(*) as event_count "
            f"FROM savings_ledger "
            f"WHERE created_at >= datetime('now', ?) {project_filter} "
            f"GROUP BY category",
            tuple(params),
        )

        categories: dict[str, Any] = {}
        total_tokens_saved = 0
        total_cost_saved = 0.0
        total_events = 0

        for row in rows:
            cat = row["category"]
            categories[cat] = {
                "original_tokens": row["original_tokens"] or 0,
                "actual_tokens": row["actual_tokens"] or 0,
                "tokens_saved": row["tokens_saved"] or 0,
                "cost_saved_usd": row["cost_saved_usd"] or 0.0,
                "event_count": row["event_count"] or 0,
            }
            total_tokens_saved += row["tokens_saved"] or 0
            total_cost_saved += row["cost_saved_usd"] or 0.0
            total_events += row["event_count"] or 0

        # Also include rolled-up daily data for the window
        daily_rows = self.db.fetchall(
            f"SELECT category, "
            f"SUM(total_tokens_saved) as tokens_saved, "
            f"SUM(total_cost_saved_usd) as cost_saved_usd, "
            f"SUM(event_count) as event_count "
            f"FROM savings_daily "
            f"WHERE date >= date('now', ?) {project_filter} "
            f"GROUP BY category",
            tuple(params),
        )
        for row in daily_rows:
            cat = row["category"]
            if cat not in categories:
                categories[cat] = {
                    "original_tokens": 0,
                    "actual_tokens": 0,
                    "tokens_saved": 0,
                    "cost_saved_usd": 0.0,
                    "event_count": 0,
                }
            categories[cat]["tokens_saved"] += row["tokens_saved"] or 0
            categories[cat]["cost_saved_usd"] += row["cost_saved_usd"] or 0.0
            categories[cat]["event_count"] += row["event_count"] or 0
            total_tokens_saved += row["tokens_saved"] or 0
            total_cost_saved += row["cost_saved_usd"] or 0.0
            total_events += row["event_count"] or 0

        return {
            "days": days,
            "total_tokens_saved": total_tokens_saved,
            "total_cost_saved_usd": round(total_cost_saved, 6),
            "total_events": total_events,
            "categories": categories,
        }

    def get_cumulative(self, days: int = 30, project_id: str | None = None) -> dict[str, Any]:
        """Get cumulative savings over a longer window (for dashboard headline)."""
        return self.get_summary(days=days, project_id=project_id)

    def rollup_daily(self, retention_days: int = 7) -> int:
        """Roll up old ledger entries into daily aggregates.

        Entries older than retention_days are aggregated into savings_daily,
        then deleted from savings_ledger. Returns number of rows rolled up.
        """
        cutoff = f"-{retention_days} days"

        # Aggregate into daily
        self.db.execute(
            "INSERT INTO savings_daily (project_id, category, date, event_count, "
            "total_original_tokens, total_actual_tokens, total_tokens_saved, total_cost_saved_usd) "
            "SELECT project_id, category, date(created_at), COUNT(*), "
            "SUM(original_tokens), SUM(actual_tokens), SUM(tokens_saved), "
            "COALESCE(SUM(cost_saved_usd), 0.0) "
            "FROM savings_ledger "
            "WHERE created_at < datetime('now', ?) "
            "GROUP BY project_id, category, date(created_at) "
            "ON CONFLICT(project_id, category, date) DO UPDATE SET "
            "event_count = event_count + excluded.event_count, "
            "total_original_tokens = total_original_tokens + excluded.total_original_tokens, "
            "total_actual_tokens = total_actual_tokens + excluded.total_actual_tokens, "
            "total_tokens_saved = total_tokens_saved + excluded.total_tokens_saved, "
            "total_cost_saved_usd = total_cost_saved_usd + excluded.total_cost_saved_usd",
            (cutoff,),
        )

        # Delete rolled-up entries
        result = self.db.execute(
            "DELETE FROM savings_ledger WHERE created_at < datetime('now', ?)",
            (cutoff,),
        )
        count = result.rowcount if result.rowcount else 0
        if count > 0:
            logger.info(f"Rolled up {count} savings ledger entries into daily aggregates")
        return count

    def cleanup(self, retention_days: int = 7) -> int:
        """Convenience alias for rollup_daily."""
        return self.rollup_daily(retention_days=retention_days)

    def _estimate_cost(self, tokens_saved: int, model: str | None) -> float | None:
        """Estimate cost saved based on input token rate for the model."""
        if tokens_saved <= 0:
            return 0.0
        if not model or not self._model_costs:
            return None

        costs = self._model_costs.get_all()

        # Strip provider prefix
        lookup = model
        if "/" in lookup:
            lookup = lookup.split("/", 1)[1]

        mc = costs.get(lookup)
        if mc is None:
            # Try prefix match
            best_match = None
            best_len = 0
            for prefix in costs:
                if lookup.startswith(prefix) and len(prefix) > best_len:
                    best_match = prefix
                    best_len = len(prefix)
            if best_match:
                mc = costs[best_match]

        if mc is None:
            return None

        # Savings are input tokens saved (they would have entered the context)
        return tokens_saved * mc.input
