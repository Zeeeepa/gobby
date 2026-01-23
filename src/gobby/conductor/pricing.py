"""Token tracking and cost calculation using LiteLLM pricing utilities.

LiteLLM maintains model_prices_and_context_window.json with current pricing
for 100+ models, so we don't need to maintain our own pricing data.

See: https://docs.litellm.ai/docs/completion/token_usage
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

try:
    import litellm
except ImportError:
    litellm = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


@dataclass
class TokenTracker:
    """Track token usage and calculate costs using LiteLLM pricing utilities.

    LiteLLM automatically maintains pricing data for 100+ models including:
    - Claude models (Anthropic)
    - GPT models (OpenAI)
    - Gemini models (Google)
    - And many more

    Example:
        tracker = TokenTracker()
        cost = tracker.calculate_cost("claude-3-5-sonnet", 1000, 500)
        tracker.track_usage("claude-3-5-sonnet", 1000, 500)
        print(tracker.get_summary())
    """

    # Accumulated token counts
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read_tokens: int = 0
    total_cache_write_tokens: int = 0
    total_cost: float = 0.0

    # Track usage by model
    usage_by_model: dict[str, dict[str, Any]] = field(default_factory=dict)

    def calculate_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
    ) -> float:
        """Calculate cost for given token usage using LiteLLM pricing.

        Uses litellm.cost_per_token() to get per-token pricing for the model,
        then calculates total cost.

        Args:
            model: Model name (e.g., "claude-3-5-sonnet-20241022", "gpt-4o")
            input_tokens: Number of input (prompt) tokens
            output_tokens: Number of output (completion) tokens
            cache_read_tokens: Number of cache read tokens (if model supports)
            cache_write_tokens: Number of cache write tokens (if model supports)

        Returns:
            Total cost in USD, or 0.0 if pricing is unavailable
        """
        if input_tokens == 0 and output_tokens == 0:
            return 0.0

        if litellm is None:
            logger.debug("litellm not available, cannot calculate cost")
            return 0.0

        try:
            # Get cost per token for this model
            prompt_cost, completion_cost = litellm.cost_per_token(
                model=model,
                prompt_tokens=input_tokens,
                completion_tokens=output_tokens,
            )

            total = prompt_cost + completion_cost

            # Handle cache tokens if provided using LiteLLM's native cache pricing
            if cache_read_tokens > 0 or cache_write_tokens > 0:
                try:
                    # Get model cost info from LiteLLM
                    model_info = litellm.get_model_info(model=model)

                    # Check for cache-specific pricing in model info
                    cache_read_cost_per_token = model_info.get("cache_read_input_token_cost")
                    cache_creation_cost_per_token = model_info.get(
                        "cache_creation_input_token_cost"
                    )

                    if cache_read_tokens > 0:
                        if cache_read_cost_per_token is not None:
                            # Use native cache read pricing
                            total += cache_read_tokens * cache_read_cost_per_token
                        else:
                            # Fallback: cache reads are typically 10% of input cost
                            input_cost_per_token = model_info.get("input_cost_per_token", 0)
                            total += cache_read_tokens * input_cost_per_token * 0.1

                    if cache_write_tokens > 0:
                        if cache_creation_cost_per_token is not None:
                            # Use native cache creation pricing
                            total += cache_write_tokens * cache_creation_cost_per_token
                        else:
                            # Fallback: cache writes are typically 1.25x input cost
                            input_cost_per_token = model_info.get("input_cost_per_token", 0)
                            total += cache_write_tokens * input_cost_per_token * 1.25

                    # Note: For Anthropic models with prompt caching, LiteLLM may
                    # already account for cache tokens in cost_per_token. Check if
                    # the response usage includes cached_tokens to avoid double-counting.

                except Exception:  # nosec B110 - best effort cache pricing, failure is non-critical
                    # If cache pricing lookup fails, skip cache cost calculation
                    pass

            return total

        except Exception as e:
            # Model not found in LiteLLM pricing data
            logger.debug(f"Could not calculate cost for model {model}: {e}")
            return 0.0

    def calculate_cost_from_response(self, response: Any) -> float:
        """Calculate cost directly from a LiteLLM response object.

        Uses litellm.completion_cost() which extracts usage info from the response
        and calculates the total cost.

        Args:
            response: LiteLLM response object from acompletion/completion

        Returns:
            Total cost in USD, or 0.0 if calculation fails
        """
        if litellm is None:
            logger.debug("litellm not available, cannot calculate cost from response")
            return 0.0

        try:
            return litellm.completion_cost(response)
        except Exception as e:
            logger.debug(f"Could not calculate cost from response: {e}")
            return 0.0

    def track_usage(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
    ) -> float:
        """Track token usage and accumulate costs.

        Args:
            model: Model name
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            cache_read_tokens: Number of cache read tokens
            cache_write_tokens: Number of cache write tokens

        Returns:
            Cost for this usage
        """
        cost = self.calculate_cost(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
        )

        # Accumulate totals
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_cache_read_tokens += cache_read_tokens
        self.total_cache_write_tokens += cache_write_tokens
        self.total_cost += cost

        # Track by model
        if model not in self.usage_by_model:
            self.usage_by_model[model] = {
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
                "cost": 0.0,
                "calls": 0,
            }

        self.usage_by_model[model]["input_tokens"] += input_tokens
        self.usage_by_model[model]["output_tokens"] += output_tokens
        self.usage_by_model[model]["cache_read_tokens"] += cache_read_tokens
        self.usage_by_model[model]["cache_write_tokens"] += cache_write_tokens
        self.usage_by_model[model]["cost"] += cost
        self.usage_by_model[model]["calls"] += 1

        return cost

    def reset(self) -> None:
        """Reset all tracked usage."""
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cache_read_tokens = 0
        self.total_cache_write_tokens = 0
        self.total_cost = 0.0
        self.usage_by_model.clear()

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of all tracked usage.

        Returns:
            Dict with total tokens, cost, and per-model breakdown
        """
        return {
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_cache_read_tokens": self.total_cache_read_tokens,
            "total_cache_write_tokens": self.total_cache_write_tokens,
            "total_cost": self.total_cost,
            "usage_by_model": dict(self.usage_by_model),
        }
