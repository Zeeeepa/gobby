"""
Static model cost table for native SDK executors.

Provides per-token cost lookups with prefix matching for versioned model names.
Used by GeminiExecutor, OpenAIExecutor, and ClaudeExecutor (api_key mode).

LiteLLMExecutor uses litellm.completion_cost() instead — this module is only
for native SDK executors that don't have LiteLLM's cost tracking.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelCost:
    """Per-token costs for a model (USD per token)."""

    input_cost_per_token: float
    output_cost_per_token: float


# Static cost table. Keys are model name prefixes — longest prefix match wins.
# Costs in USD per token. Updated as of March 2026.
MODEL_COSTS: dict[str, ModelCost] = {
    # Claude models
    "claude-opus-4": ModelCost(15.0 / 1_000_000, 75.0 / 1_000_000),
    "claude-sonnet-4": ModelCost(3.0 / 1_000_000, 15.0 / 1_000_000),
    "claude-haiku-4": ModelCost(0.80 / 1_000_000, 4.0 / 1_000_000),
    # Gemini models
    "gemini-2.5-pro": ModelCost(1.25 / 1_000_000, 10.0 / 1_000_000),
    "gemini-2.5-flash": ModelCost(0.15 / 1_000_000, 0.60 / 1_000_000),
    "gemini-2.0-flash": ModelCost(0.10 / 1_000_000, 0.40 / 1_000_000),
    "gemini-1.5-pro": ModelCost(1.25 / 1_000_000, 5.0 / 1_000_000),
    "gemini-1.5-flash": ModelCost(0.075 / 1_000_000, 0.30 / 1_000_000),
    # OpenAI models
    "gpt-4o-mini": ModelCost(0.15 / 1_000_000, 0.60 / 1_000_000),
    "gpt-4o": ModelCost(2.50 / 1_000_000, 10.0 / 1_000_000),
    "gpt-4.1": ModelCost(2.0 / 1_000_000, 8.0 / 1_000_000),
    "gpt-4.1-mini": ModelCost(0.40 / 1_000_000, 1.60 / 1_000_000),
    "gpt-4.1-nano": ModelCost(0.10 / 1_000_000, 0.40 / 1_000_000),
    "o3-mini": ModelCost(1.10 / 1_000_000, 4.40 / 1_000_000),
    "o3": ModelCost(2.0 / 1_000_000, 8.0 / 1_000_000),
    "o4-mini": ModelCost(1.10 / 1_000_000, 4.40 / 1_000_000),
}

# Sentinel for unknown models — zero cost
_ZERO_COST = ModelCost(0.0, 0.0)


def lookup_cost(model: str) -> ModelCost:
    """
    Look up per-token costs for a model using longest prefix match.

    Strips any provider prefix (e.g., "anthropic/claude-opus-4-6" → "claude-opus-4-6")
    then finds the longest matching prefix in the cost table.

    Args:
        model: Model name, optionally with provider prefix.

    Returns:
        ModelCost with per-token costs. Returns zero costs for unknown models.
    """
    # Strip provider prefix (e.g., "anthropic/claude-opus-4-6" → "claude-opus-4-6")
    if "/" in model:
        model = model.split("/", 1)[1]

    # Exact match first
    if model in MODEL_COSTS:
        return MODEL_COSTS[model]

    # Longest prefix match
    best_match: str | None = None
    best_len = 0
    for prefix in MODEL_COSTS:
        if model.startswith(prefix) and len(prefix) > best_len:
            best_match = prefix
            best_len = len(prefix)

    if best_match is not None:
        return MODEL_COSTS[best_match]

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
    costs = lookup_cost(model)
    return (
        costs.input_cost_per_token * prompt_tokens
        + costs.output_cost_per_token * completion_tokens
    )
