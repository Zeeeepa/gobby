"""Compute USD cost from token counts + model using ModelCostStore."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gobby.storage.model_costs import ModelCostStore

logger = logging.getLogger(__name__)


class CostCalculator:
    """Compute USD cost from token counts + model using ModelCostStore.

    Loads cost data once from the store, then uses prefix matching
    (like cost_table.py) for model name resolution.
    """

    def __init__(self, model_costs: ModelCostStore) -> None:
        self._costs = model_costs.get_all()

    def _resolve_model(self, model: str) -> str | None:
        """Resolve model name using exact match then longest prefix match."""
        # Strip provider prefix (e.g., "anthropic/claude-opus-4-6" -> "claude-opus-4-6")
        if "/" in model:
            model = model.split("/", 1)[1]

        if model in self._costs:
            return model

        # Longest prefix match
        best_match: str | None = None
        best_len = 0
        for prefix in self._costs:
            if model.startswith(prefix) and len(prefix) > best_len:
                best_match = prefix
                best_len = len(prefix)

        return best_match

    def calculate(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_creation_tokens: int = 0,
        cache_read_tokens: int = 0,
    ) -> float | None:
        """Return USD cost, or None if model not found.

        Cost = (input_tokens * input_rate)
             + (output_tokens * output_rate)
             + (cache_creation_tokens * cache_creation_rate)
             + (cache_read_tokens * cache_read_rate)

        If cache rates are None, falls back to input_rate * 1.25 for cache creation
        and input_rate * 0.1 for cache read (Anthropic's standard ratios).
        """
        resolved = self._resolve_model(model)
        if resolved is None:
            logger.debug("No cost data for model %r", model)
            return None

        cost = self._costs[resolved]
        input_rate = cost.input
        output_rate = cost.output
        cache_creation_rate = (
            cost.cache_creation if cost.cache_creation is not None else input_rate * 1.25
        )
        cache_read_rate = cost.cache_read if cost.cache_read is not None else input_rate * 0.1

        return (
            max(0, input_tokens) * input_rate
            + max(0, output_tokens) * output_rate
            + max(0, cache_creation_tokens) * cache_creation_rate
            + max(0, cache_read_tokens) * cache_read_rate
        )
