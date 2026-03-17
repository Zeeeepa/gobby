"""Storage manager for cached model costs from LiteLLM."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from gobby.storage.database import DatabaseProtocol

logger = logging.getLogger(__name__)


class ModelCost(NamedTuple):
    """Per-token costs for a model (USD per token)."""

    input: float
    output: float
    cache_read: float | None = None
    cache_creation: float | None = None


class ModelCostStore:
    """Manages the model_costs table populated from LiteLLM's registry."""

    def __init__(self, db: DatabaseProtocol) -> None:
        self.db = db

    def populate_from_litellm(self) -> int:
        """Clear and bulk-insert costs from litellm.model_cost.

        Returns:
            Number of models inserted.
        """
        try:
            import litellm
        except ImportError:
            logger.warning("litellm not installed — skipping model cost population")
            return 0

        rows: list[tuple[str, str | None, float, float, float | None, float | None, str]] = []
        for model, info in litellm.model_cost.items():
            input_cost = info.get("input_cost_per_token")
            output_cost = info.get("output_cost_per_token")
            if input_cost is None or output_cost is None:
                continue
            # Skip entries with zero costs for both (image/audio-only models)
            if input_cost == 0 and output_cost == 0:
                continue
            provider = info.get("litellm_provider")
            cache_read = info.get("cache_read_input_token_cost")
            cache_creation = info.get("cache_creation_input_token_cost")
            rows.append(
                (
                    model,
                    provider,
                    float(input_cost),
                    float(output_cost),
                    float(cache_read) if cache_read is not None else None,
                    float(cache_creation) if cache_creation is not None else None,
                    "litellm",
                )
            )

        with self.db.transaction() as conn:
            conn.execute("DELETE FROM model_costs")
            conn.executemany(
                "INSERT INTO model_costs (model, provider, input_cost_per_token, "
                "output_cost_per_token, cache_read_cost_per_token, "
                "cache_creation_cost_per_token, source) VALUES (?, ?, ?, ?, ?, ?, ?)",
                rows,
            )

        # Apply Anthropic's known pricing as overrides to guard against stale LiteLLM data
        self._apply_anthropic_overrides()

        logger.info(f"Populated model_costs table with {len(rows)} models from LiteLLM")
        return len(rows)

    def _apply_anthropic_overrides(self) -> None:
        """Override LiteLLM pricing with Anthropic's known current rates.

        Guards against stale or missing entries in the LiteLLM registry.
        Prices are per-token (USD).
        """
        # fmt: off
        overrides: list[tuple[str, float, float, float, float]] = [
            # (model_prefix, input, output, cache_read, cache_creation)
            ("claude-opus-4", 15e-6, 75e-6, 1.5e-6, 18.75e-6),
            ("claude-sonnet-4", 3e-6, 15e-6, 0.3e-6, 3.75e-6),
            ("claude-haiku-4", 0.8e-6, 4e-6, 0.08e-6, 1e-6),
        ]
        # fmt: on
        for prefix, inp, out, cr, cc in overrides:
            self.db.execute(
                """
                UPDATE model_costs
                SET input_cost_per_token = ?,
                    output_cost_per_token = ?,
                    cache_read_cost_per_token = ?,
                    cache_creation_cost_per_token = ?,
                    source = 'anthropic_override'
                WHERE model LIKE ? || '%'
                """,
                (inp, out, cr, cc, prefix),
            )

    def get_all(self) -> dict[str, ModelCost]:
        """Return all cached costs as {model: ModelCost}."""
        rows = self.db.fetchall(
            "SELECT model, input_cost_per_token, output_cost_per_token, "
            "cache_read_cost_per_token, cache_creation_cost_per_token FROM model_costs"
        )
        return {
            row["model"]: ModelCost(
                input=row["input_cost_per_token"],
                output=row["output_cost_per_token"],
                cache_read=row["cache_read_cost_per_token"],
                cache_creation=row["cache_creation_cost_per_token"],
            )
            for row in rows
        }
