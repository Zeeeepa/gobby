"""Tests for the DB-backed model cost table."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from gobby.llm.cost_table import (
    ModelCost,
    _costs,
    calculate_cost,
    init,
    lookup_context_window,
    lookup_cost,
)
from gobby.llm.model_registry import ModelInfo
from gobby.storage.model_costs import ModelCostStore

if TYPE_CHECKING:
    from gobby.storage.database import LocalDatabase

pytestmark = pytest.mark.unit

# Test fixture data matching OpenRouter format
_TEST_MODELS = [
    ModelInfo(
        id="openai/gpt-4o",
        name="OpenAI: GPT-4o",
        provider="codex",
        context_length=128000,
        max_completion_tokens=16384,
        input_cost_per_token=2.5e-6,
        output_cost_per_token=10e-6,
        cache_read_cost_per_token=None,
        cache_creation_cost_per_token=None,
    ),
    ModelInfo(
        id="openai/gpt-4o-mini",
        name="OpenAI: GPT-4o Mini",
        provider="codex",
        context_length=128000,
        max_completion_tokens=16384,
        input_cost_per_token=0.15e-6,
        output_cost_per_token=0.6e-6,
        cache_read_cost_per_token=None,
        cache_creation_cost_per_token=None,
    ),
    ModelInfo(
        id="anthropic/claude-sonnet-4-6",
        name="Anthropic: Claude Sonnet 4.6",
        provider="claude",
        context_length=200000,
        max_completion_tokens=64000,
        input_cost_per_token=3e-6,
        output_cost_per_token=15e-6,
        cache_read_cost_per_token=0.3e-6,
        cache_creation_cost_per_token=3.75e-6,
    ),
]


@pytest.fixture()
def populated_db(temp_db: LocalDatabase) -> LocalDatabase:
    """DB with model_costs populated from test fixture data."""
    store = ModelCostStore(temp_db)
    count = store.populate(_TEST_MODELS)
    assert count == 3
    init(temp_db)
    return temp_db


class TestModelCostStore:
    """Tests for the ModelCostStore storage layer."""

    def test_populate_returns_count(self, temp_db: LocalDatabase) -> None:
        """populate inserts models and returns count."""
        store = ModelCostStore(temp_db)
        count = store.populate(_TEST_MODELS)
        assert count == 3

    def test_populate_is_idempotent(self, temp_db: LocalDatabase) -> None:
        """Calling populate twice replaces data, not appends."""
        store = ModelCostStore(temp_db)
        count1 = store.populate(_TEST_MODELS)
        count2 = store.populate(_TEST_MODELS)
        assert count1 == count2

    def test_populate_empty_keeps_existing(self, temp_db: LocalDatabase) -> None:
        """Empty model list preserves existing cached data."""
        store = ModelCostStore(temp_db)
        store.populate(_TEST_MODELS)
        count = store.populate([])
        assert count == 0
        # Data should still be there
        assert len(store.get_all()) == 3

    def test_get_all_returns_dict(self, temp_db: LocalDatabase) -> None:
        """get_all returns model -> ModelCost dict."""
        store = ModelCostStore(temp_db)
        store.populate(_TEST_MODELS)
        costs = store.get_all()
        assert len(costs) == 3
        for model, mc in costs.items():
            assert isinstance(model, str)
            assert isinstance(mc.input, float)
            assert isinstance(mc.output, float)

    def test_strips_provider_prefix_in_db(self, temp_db: LocalDatabase) -> None:
        """Model keys in DB have provider prefix stripped."""
        store = ModelCostStore(temp_db)
        store.populate(_TEST_MODELS)
        costs = store.get_all()
        # Keys should be "gpt-4o" not "openai/gpt-4o"
        assert "gpt-4o" in costs
        assert "openai/gpt-4o" not in costs

    def test_get_context_window(self, temp_db: LocalDatabase) -> None:
        """get_context_window returns context_length from DB."""
        store = ModelCostStore(temp_db)
        store.populate(_TEST_MODELS)
        assert store.get_context_window("claude-sonnet-4-6") == 200000
        assert store.get_context_window("gpt-4o") == 128000

    def test_get_context_window_strips_prefix(self, temp_db: LocalDatabase) -> None:
        """get_context_window strips provider prefix."""
        store = ModelCostStore(temp_db)
        store.populate(_TEST_MODELS)
        assert store.get_context_window("anthropic/claude-sonnet-4-6") == 200000

    def test_get_context_window_unknown(self, temp_db: LocalDatabase) -> None:
        """Unknown model returns None."""
        store = ModelCostStore(temp_db)
        store.populate(_TEST_MODELS)
        assert store.get_context_window("totally-unknown") is None


class TestLookupCost:
    """Tests for lookup_cost function with DB-backed data."""

    def test_known_model(self, populated_db: LocalDatabase) -> None:
        """Known model returns non-zero cost."""
        cost = lookup_cost("gpt-4o")
        assert cost.input_cost_per_token > 0
        assert cost.output_cost_per_token > 0

    def test_prefix_match_versioned_model(self, populated_db: LocalDatabase) -> None:
        """Versioned model name matches via prefix."""
        cost = lookup_cost("gpt-4o-2024-08-06-extended")
        assert cost.input_cost_per_token > 0

    def test_strips_provider_prefix(self, populated_db: LocalDatabase) -> None:
        """Provider prefix is stripped before lookup."""
        cost_with = lookup_cost("openai/gpt-4o")
        cost_without = lookup_cost("gpt-4o")
        assert cost_with == cost_without

    def test_unknown_model_returns_zero(self, populated_db: LocalDatabase) -> None:
        """Unknown model returns zero costs."""
        cost = lookup_cost("completely-unknown-model-xyz")
        assert cost.input_cost_per_token == 0.0
        assert cost.output_cost_per_token == 0.0

    def test_uninitialized_returns_zero(self) -> None:
        """When init() never called, lookups return zero."""
        saved = dict(_costs)
        _costs.clear()
        try:
            cost = lookup_cost("gpt-4o")
            assert cost.input_cost_per_token == 0.0
            assert cost.output_cost_per_token == 0.0
        finally:
            _costs.update(saved)

    def test_longest_prefix_wins(self, populated_db: LocalDatabase) -> None:
        """Longer prefix match takes priority over shorter one."""
        mini_cost = lookup_cost("gpt-4o-mini")
        base_cost = lookup_cost("gpt-4o")
        assert mini_cost != base_cost


class TestLookupContextWindow:
    """Tests for lookup_context_window function."""

    def test_known_model(self, populated_db: LocalDatabase) -> None:
        """Known model returns context window."""
        assert lookup_context_window("claude-sonnet-4-6") == 200000

    def test_strips_provider_prefix(self, populated_db: LocalDatabase) -> None:
        """Provider prefix is stripped."""
        assert lookup_context_window("anthropic/claude-sonnet-4-6") == 200000

    def test_unknown_returns_none(self, populated_db: LocalDatabase) -> None:
        """Unknown model returns None."""
        assert lookup_context_window("unknown-model") is None

    def test_uninitialized_returns_none(self) -> None:
        """When cache empty, returns None."""
        saved = dict(_costs)
        _costs.clear()
        try:
            assert lookup_context_window("claude-sonnet-4-6") is None
        finally:
            _costs.update(saved)


class TestCalculateCost:
    """Tests for calculate_cost function."""

    def test_basic_cost_calculation(self, populated_db: LocalDatabase) -> None:
        """Cost calculation multiplies tokens by per-token rates."""
        cost = calculate_cost("gpt-4o-mini", prompt_tokens=1000, completion_tokens=500)
        assert cost > 0

    def test_zero_tokens_zero_cost(self, populated_db: LocalDatabase) -> None:
        """Zero tokens produce zero cost."""
        cost = calculate_cost("gpt-4o", prompt_tokens=0, completion_tokens=0)
        assert cost == 0.0

    def test_unknown_model_zero_cost(self, populated_db: LocalDatabase) -> None:
        """Unknown model produces zero cost."""
        cost = calculate_cost("unknown-model", prompt_tokens=1000, completion_tokens=1000)
        assert cost == 0.0

    def test_cost_is_sum_of_input_and_output(self, populated_db: LocalDatabase) -> None:
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

    def test_negative_tokens_clamped(self, populated_db: LocalDatabase) -> None:
        """Negative tokens are clamped to zero."""
        cost = calculate_cost("gpt-4o", prompt_tokens=-100, completion_tokens=-50)
        assert cost == 0.0


class TestModelCost:
    """Tests for ModelCost dataclass."""

    def test_frozen(self) -> None:
        """ModelCost is immutable."""
        cost = ModelCost(1.0, 2.0)
        with pytest.raises(AttributeError):
            cost.input_cost_per_token = 3.0  # type: ignore[misc]

    def test_context_length_default_none(self) -> None:
        """context_length defaults to None."""
        cost = ModelCost(1.0, 2.0)
        assert cost.context_length is None

    def test_context_length_set(self) -> None:
        """context_length can be set."""
        cost = ModelCost(1.0, 2.0, context_length=200000)
        assert cost.context_length == 200000
