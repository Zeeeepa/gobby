"""DB-backed model cost table for LLM cost tracking.

Provides per-token cost lookups with prefix matching for versioned model names.

On daemon startup, costs are populated from OpenRouter's model registry into
the model_costs DB table, then loaded into memory via init().
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gobby.storage.database import DatabaseProtocol

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelCost:
    """Per-token costs for a model (USD per token)."""

    input_cost_per_token: float
    output_cost_per_token: float
    context_length: int | None = None


# Module-level cache loaded by init(). Empty until init() is called.
_costs: dict[str, ModelCost] = {}

# Sentinel for unknown models — zero cost
_ZERO_COST = ModelCost(0.0, 0.0)


def init(db: DatabaseProtocol) -> None:
    """Load all model costs from DB into the module-level cache.

    Called once at daemon startup after ModelCostStore.populate().
    If never called (e.g. in tests without DB), lookups return zero cost.
    """
    from gobby.storage.model_costs import ModelCostStore

    store = ModelCostStore(db)
    raw = store.get_all()

    # Also load context windows
    context_rows = db.fetchall(
        "SELECT model, context_length FROM model_costs WHERE context_length IS NOT NULL"
    )
    context_map = {r["model"]: r["context_length"] for r in context_rows}

    _costs.clear()
    _costs.update(
        {model: ModelCost(mc.input, mc.output, context_map.get(model)) for model, mc in raw.items()}
    )
    logger.info(f"Loaded {len(_costs)} model costs into memory")


def lookup_cost(model: str) -> ModelCost:
    """
    Look up per-token costs for a model using longest prefix match.

    Strips any provider prefix (e.g., "anthropic/claude-opus-4-6" -> "claude-opus-4-6")
    then finds the longest matching prefix in the cost table.

    Args:
        model: Model name, optionally with provider prefix.

    Returns:
        ModelCost with per-token costs. Returns zero costs for unknown models.
    """
    # Strip provider prefix (e.g., "anthropic/claude-opus-4-6" -> "claude-opus-4-6")
    if "/" in model:
        model = model.split("/", 1)[1]

    # Exact match first
    if model in _costs:
        return _costs[model]

    # Longest prefix match
    best_match: str | None = None
    best_len = 0
    for prefix in _costs:
        if model.startswith(prefix) and len(prefix) > best_len:
            best_match = prefix
            best_len = len(prefix)

    if best_match is not None:
        return _costs[best_match]

    logger.debug(f"No cost data for model {model!r} - returning zero cost")
    return _ZERO_COST


def calculate_cost(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    """
    Calculate total cost in USD for a model call.

    Args:
        model: Model name (with or without provider prefix).
        prompt_tokens: Number of input tokens.
        completion_tokens: Number of output tokens.

    Returns:
        Total cost in USD. Returns 0.0 for unknown models.
    """
    prompt_tokens = max(0, prompt_tokens)
    completion_tokens = max(0, completion_tokens)
    costs = lookup_cost(model)
    return (
        costs.input_cost_per_token * prompt_tokens + costs.output_cost_per_token * completion_tokens
    )


def lookup_context_window(model: str) -> int | None:
    """Look up context window size for a model using the same prefix-match logic as lookup_cost.

    Returns None if the model is unknown or has no context_length data.
    """
    if "/" in model:
        model = model.split("/", 1)[1]

    # Exact match
    if model in _costs and _costs[model].context_length is not None:
        return _costs[model].context_length

    # Longest prefix match
    best_match: str | None = None
    best_len = 0
    for prefix in _costs:
        if (
            model.startswith(prefix)
            and len(prefix) > best_len
            and _costs[prefix].context_length is not None
        ):
            best_match = prefix
            best_len = len(prefix)

    if best_match is not None:
        return _costs[best_match].context_length

    return None
