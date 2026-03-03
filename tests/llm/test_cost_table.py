"""Tests for the static model cost table."""

import pytest

from gobby.llm.cost_table import ModelCost, calculate_cost, lookup_cost

pytestmark = pytest.mark.unit


class TestLookupCost:
    """Tests for lookup_cost function."""

    def test_exact_match(self) -> None:
        """Exact model name returns correct cost."""
        cost = lookup_cost("gpt-4o")
        assert cost.input_cost_per_token > 0
        assert cost.output_cost_per_token > 0

    def test_prefix_match_versioned_model(self) -> None:
        """Versioned model name matches via prefix."""
        cost = lookup_cost("gemini-2.0-flash-001")
        base_cost = lookup_cost("gemini-2.0-flash")
        assert cost == base_cost

    def test_prefix_match_claude_versioned(self) -> None:
        """Claude versioned model name matches via prefix."""
        cost = lookup_cost("claude-opus-4-6")
        base_cost = lookup_cost("claude-opus-4")
        assert cost == base_cost
        assert cost.input_cost_per_token > 0

    def test_longest_prefix_wins(self) -> None:
        """Longer prefix match takes priority over shorter one."""
        mini_cost = lookup_cost("gpt-4o-mini")
        base_cost = lookup_cost("gpt-4o")
        # gpt-4o-mini should match "gpt-4o-mini" not "gpt-4o"
        assert mini_cost != base_cost
        assert mini_cost.input_cost_per_token < base_cost.input_cost_per_token

    def test_strips_provider_prefix(self) -> None:
        """Provider prefix is stripped before lookup."""
        cost_with_prefix = lookup_cost("anthropic/claude-opus-4-6")
        cost_without = lookup_cost("claude-opus-4-6")
        assert cost_with_prefix == cost_without

    def test_strips_gemini_prefix(self) -> None:
        """Gemini provider prefix is stripped."""
        cost_with = lookup_cost("gemini/gemini-2.0-flash")
        cost_without = lookup_cost("gemini-2.0-flash")
        assert cost_with == cost_without

    def test_unknown_model_returns_zero(self) -> None:
        """Unknown model returns zero costs."""
        cost = lookup_cost("completely-unknown-model-xyz")
        assert cost.input_cost_per_token == 0.0
        assert cost.output_cost_per_token == 0.0

    def test_all_known_models_have_nonzero_cost(self) -> None:
        """All models in the table have non-zero costs."""
        from gobby.llm.cost_table import MODEL_COSTS

        for name, cost in MODEL_COSTS.items():
            assert cost.input_cost_per_token > 0, f"{name} has zero input cost"
            assert cost.output_cost_per_token > 0, f"{name} has zero output cost"


class TestCalculateCost:
    """Tests for calculate_cost function."""

    def test_basic_cost_calculation(self) -> None:
        """Cost calculation multiplies tokens by per-token rates."""
        cost = calculate_cost("gpt-4o-mini", prompt_tokens=1000, completion_tokens=500)
        assert cost > 0

    def test_zero_tokens_zero_cost(self) -> None:
        """Zero tokens produce zero cost."""
        cost = calculate_cost("gpt-4o", prompt_tokens=0, completion_tokens=0)
        assert cost == 0.0

    def test_unknown_model_zero_cost(self) -> None:
        """Unknown model produces zero cost."""
        cost = calculate_cost("unknown-model", prompt_tokens=1000, completion_tokens=1000)
        assert cost == 0.0

    def test_cost_is_sum_of_input_and_output(self) -> None:
        """Total cost equals input cost + output cost."""
        model = "gpt-4o"
        costs = lookup_cost(model)
        prompt_tokens = 1000
        completion_tokens = 500

        expected = (
            costs.input_cost_per_token * prompt_tokens
            + costs.output_cost_per_token * completion_tokens
        )
        actual = calculate_cost(model, prompt_tokens, completion_tokens)
        assert actual == pytest.approx(expected)

    def test_provider_prefix_handled(self) -> None:
        """Provider prefix is handled in cost calculation."""
        cost_with = calculate_cost(
            "anthropic/claude-sonnet-4-6", prompt_tokens=1000, completion_tokens=500
        )
        cost_without = calculate_cost(
            "claude-sonnet-4-6", prompt_tokens=1000, completion_tokens=500
        )
        assert cost_with == cost_without


class TestModelCost:
    """Tests for ModelCost dataclass."""

    def test_frozen(self) -> None:
        """ModelCost is immutable."""
        cost = ModelCost(1.0, 2.0)
        with pytest.raises(AttributeError):
            cost.input_cost_per_token = 3.0  # type: ignore[misc]
