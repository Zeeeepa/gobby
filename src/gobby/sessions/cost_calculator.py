"""Compute USD cost from token counts + model using ModelCostStore."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gobby.storage.model_costs import ModelCostStore

logger = logging.getLogger(__name__)

# Long-context pricing tiers: model prefix -> (threshold_tokens, input_rate_multiplier)
# Anthropic applies premium rate to the *entire request* when total input exceeds threshold.
LONG_CONTEXT_THRESHOLDS: dict[str, tuple[int, float]] = {
    "claude-sonnet": (200_000, 2.0),  # 2x input rate above 200k
}


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

    def _get_long_context_multiplier(self, model: str, total_input_tokens: int) -> float | None:
        """Check if long-context pricing applies for this model and token count.

        Returns the input rate multiplier if applicable, None otherwise.
        """
        # Strip provider prefix for matching
        bare = model.split("/", 1)[-1] if "/" in model else model
        for prefix, (threshold, multiplier) in LONG_CONTEXT_THRESHOLDS.items():
            if bare.startswith(prefix) and total_input_tokens > threshold:
                return multiplier
        return None

    def calculate(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_creation_tokens: int = 0,
        cache_read_tokens: int = 0,
        cache_creation_multiplier: float = 1.25,
    ) -> float | None:
        """Return USD cost, or None if model not found.

        Cost = (input_tokens * input_rate)
             + (output_tokens * output_rate)
             + (cache_creation_tokens * cache_creation_rate)
             + (cache_read_tokens * cache_read_rate)

        If cache rates are None, falls back to input_rate * cache_creation_multiplier
        for cache creation and input_rate * 0.1 for cache read.

        Args:
            model: Model identifier (e.g., "claude-sonnet-4-20250514")
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            cache_creation_tokens: Number of cache creation tokens
            cache_read_tokens: Number of cache read tokens
            cache_creation_multiplier: Multiplier for cache creation fallback rate.
                1.25 for standard 5-minute cache (default), 2.0 for 1-hour extended cache.
        """
        resolved = self._resolve_model(model)
        if resolved is None:
            logger.debug("No cost data for model %r", model)
            return None

        cost = self._costs[resolved]
        input_rate = cost.input
        output_rate = cost.output
        cache_creation_rate = (
            cost.cache_creation
            if cost.cache_creation is not None
            else input_rate * cache_creation_multiplier
        )
        cache_read_rate = cost.cache_read if cost.cache_read is not None else input_rate * 0.1

        # Check for long-context pricing surcharge
        total_input = (
            max(0, input_tokens) + max(0, cache_creation_tokens) + max(0, cache_read_tokens)
        )
        lc_multiplier = self._get_long_context_multiplier(model, total_input)
        if lc_multiplier is not None:
            input_rate *= lc_multiplier
            cache_creation_rate *= lc_multiplier
            cache_read_rate *= lc_multiplier

        return (
            max(0, input_tokens) * input_rate
            + max(0, output_tokens) * output_rate
            + max(0, cache_creation_tokens) * cache_creation_rate
            + max(0, cache_read_tokens) * cache_read_rate
        )
