"""Storage manager for cached model costs from OpenRouter registry."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from gobby.llm.model_registry import ModelInfo
    from gobby.storage.database import DatabaseProtocol

logger = logging.getLogger(__name__)


class ModelCost(NamedTuple):
    """Per-token costs for a model (USD per token)."""

    input: float
    output: float
    cache_read: float | None = None
    cache_creation: float | None = None
    context_length: int | None = None


class ModelCostStore:
    """Manages the model_costs table populated from OpenRouter's model registry."""

    def __init__(self, db: DatabaseProtocol) -> None:
        self.db = db

    def populate(self, models: list[ModelInfo] | None = None) -> int:
        """Clear and bulk-insert costs from OpenRouter model registry.

        Args:
            models: Pre-fetched model data. If None, fetches from OpenRouter.

        Returns:
            Number of models inserted.
        """
        if models is None:
            from gobby.llm.model_registry import fetch_models_sync

            models = fetch_models_sync()

        if not models:
            logger.warning("No models available — keeping existing cached costs")
            return 0

        from gobby.llm.model_registry import strip_provider_prefix

        rows: list[
            tuple[str, str, float, float, float | None, float | None, int, int | None, str]
        ] = []
        for m in models:
            model_key = strip_provider_prefix(m.id)
            rows.append(
                (
                    model_key,
                    m.provider,
                    m.input_cost_per_token,
                    m.output_cost_per_token,
                    m.cache_read_cost_per_token,
                    m.cache_creation_cost_per_token,
                    m.context_length,
                    m.max_completion_tokens,
                    "registry",
                )
            )

        with self.db.transaction() as conn:
            conn.execute("DELETE FROM model_costs")
            conn.executemany(
                "INSERT INTO model_costs (model, provider, input_cost_per_token, "
                "output_cost_per_token, cache_read_cost_per_token, "
                "cache_creation_cost_per_token, context_length, max_completion_tokens, "
                "source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )

        logger.info(f"Populated model_costs table with {len(rows)} models from registry")
        return len(rows)

    def get_all(self) -> dict[str, ModelCost]:
        """Return all cached costs as {model: ModelCost}."""
        rows = self.db.fetchall(
            "SELECT model, input_cost_per_token, output_cost_per_token, "
            "cache_read_cost_per_token, cache_creation_cost_per_token, "
            "context_length FROM model_costs"
        )
        return {
            row["model"]: ModelCost(
                input=row["input_cost_per_token"],
                output=row["output_cost_per_token"],
                cache_read=row["cache_read_cost_per_token"],
                cache_creation=row["cache_creation_cost_per_token"],
                context_length=row["context_length"],
            )
            for row in rows
        }

    def get_context_window(self, model: str) -> int | None:
        """Look up context_length for a model (exact match, then prefix match)."""
        # Strip provider prefix
        if "/" in model:
            model = model.split("/", 1)[1]

        row = self.db.fetchone("SELECT context_length FROM model_costs WHERE model = ?", (model,))
        if row and row["context_length"]:
            return int(row["context_length"])

        # Prefix match — find longest matching model key
        rows = self.db.fetchall(
            "SELECT model, context_length FROM model_costs WHERE context_length IS NOT NULL"
        )
        best_len = 0
        best_val: int | None = None
        for r in rows:
            key = r["model"]
            if model.startswith(key) and len(key) > best_len:
                best_len = len(key)
                best_val = r["context_length"]

        return best_val
