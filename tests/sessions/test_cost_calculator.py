"""Tests for CostCalculator."""

import pytest

from gobby.sessions.cost_calculator import CostCalculator
from gobby.storage.model_costs import ModelCost


class FakeModelCostStore:
    """Fake store that returns pre-configured costs."""

    def __init__(self, costs: dict[str, ModelCost]) -> None:
        self._costs = costs

    def get_all(self) -> dict[str, ModelCost]:
        return self._costs


class TestCostCalculator:
    def _make_calculator(self, costs: dict[str, ModelCost]) -> CostCalculator:
        return CostCalculator(FakeModelCostStore(costs))  # type: ignore[arg-type]

    def test_basic_calculation(self) -> None:
        calc = self._make_calculator(
            {
                "claude-sonnet-4-20250514": ModelCost(
                    input=0.000003, output=0.000015, cache_read=0.0000003, cache_creation=0.00000375
                ),
            }
        )
        cost = calc.calculate(
            model="claude-sonnet-4-20250514",
            input_tokens=1000,
            output_tokens=500,
        )
        assert cost is not None
        assert cost == pytest.approx(0.000003 * 1000 + 0.000015 * 500)

    def test_with_cache_tokens(self) -> None:
        calc = self._make_calculator(
            {
                "claude-sonnet-4-20250514": ModelCost(
                    input=0.000003, output=0.000015, cache_read=0.0000003, cache_creation=0.00000375
                ),
            }
        )
        cost = calc.calculate(
            model="claude-sonnet-4-20250514",
            input_tokens=1000,
            output_tokens=500,
            cache_creation_tokens=2000,
            cache_read_tokens=5000,
        )
        assert cost is not None
        expected = 0.000003 * 1000 + 0.000015 * 500 + 0.00000375 * 2000 + 0.0000003 * 5000
        assert cost == pytest.approx(expected)

    def test_cache_rate_fallback(self) -> None:
        """When cache rates are None, use standard Anthropic ratios."""
        calc = self._make_calculator(
            {
                "some-model": ModelCost(input=0.00001, output=0.00003),
            }
        )
        cost = calc.calculate(
            model="some-model",
            input_tokens=1000,
            output_tokens=500,
            cache_creation_tokens=2000,
            cache_read_tokens=5000,
        )
        assert cost is not None
        expected = (
            0.00001 * 1000
            + 0.00003 * 500
            + 0.00001 * 1.25 * 2000  # cache creation fallback
            + 0.00001 * 0.1 * 5000  # cache read fallback
        )
        assert cost == pytest.approx(expected)

    def test_unknown_model_returns_none(self) -> None:
        calc = self._make_calculator(
            {
                "claude-sonnet-4-20250514": ModelCost(input=0.000003, output=0.000015),
            }
        )
        cost = calc.calculate(model="unknown-model", input_tokens=100, output_tokens=50)
        assert cost is None

    def test_provider_prefix_stripped(self) -> None:
        calc = self._make_calculator(
            {
                "claude-sonnet-4-20250514": ModelCost(input=0.000003, output=0.000015),
            }
        )
        cost = calc.calculate(
            model="anthropic/claude-sonnet-4-20250514",
            input_tokens=1000,
            output_tokens=500,
        )
        assert cost is not None
        assert cost == pytest.approx(0.000003 * 1000 + 0.000015 * 500)

    def test_prefix_matching(self) -> None:
        calc = self._make_calculator(
            {
                "claude-sonnet-4": ModelCost(input=0.000003, output=0.000015),
            }
        )
        cost = calc.calculate(
            model="claude-sonnet-4-20250514",
            input_tokens=1000,
            output_tokens=500,
        )
        assert cost is not None
        assert cost == pytest.approx(0.000003 * 1000 + 0.000015 * 500)

    def test_negative_tokens_clamped_to_zero(self) -> None:
        calc = self._make_calculator(
            {
                "test-model": ModelCost(input=0.00001, output=0.00003),
            }
        )
        cost = calc.calculate(model="test-model", input_tokens=-100, output_tokens=500)
        assert cost is not None
        assert cost == pytest.approx(0.00003 * 500)

    def test_zero_tokens(self) -> None:
        calc = self._make_calculator(
            {
                "test-model": ModelCost(input=0.00001, output=0.00003),
            }
        )
        cost = calc.calculate(model="test-model", input_tokens=0, output_tokens=0)
        assert cost is not None
        assert cost == 0.0

    def test_long_context_surcharge_sonnet(self) -> None:
        """Sonnet models get 2x input rate when total input exceeds 200k."""
        calc = self._make_calculator(
            {
                "claude-sonnet-4-20250514": ModelCost(
                    input=3e-6, output=15e-6, cache_read=0.3e-6, cache_creation=3.75e-6
                ),
            }
        )
        # Total input = 250k (exceeds 200k threshold)
        cost = calc.calculate(
            model="claude-sonnet-4-20250514",
            input_tokens=200_000,
            output_tokens=1000,
            cache_creation_tokens=30_000,
            cache_read_tokens=20_000,
        )
        assert cost is not None
        # With 2x surcharge on input rates
        expected = (
            200_000 * 3e-6 * 2
            + 1000 * 15e-6  # output rate unchanged
            + 30_000 * 3.75e-6 * 2
            + 20_000 * 0.3e-6 * 2
        )
        assert cost == pytest.approx(expected)

    def test_no_long_context_surcharge_under_threshold(self) -> None:
        """No surcharge when total input is under 200k."""
        calc = self._make_calculator(
            {
                "claude-sonnet-4-20250514": ModelCost(
                    input=3e-6, output=15e-6, cache_read=0.3e-6, cache_creation=3.75e-6
                ),
            }
        )
        cost = calc.calculate(
            model="claude-sonnet-4-20250514",
            input_tokens=100_000,
            output_tokens=1000,
        )
        assert cost is not None
        expected = 100_000 * 3e-6 + 1000 * 15e-6
        assert cost == pytest.approx(expected)

    def test_no_long_context_surcharge_at_exact_threshold(self) -> None:
        """No surcharge when total input is exactly 200k (threshold is >200k)."""
        calc = self._make_calculator(
            {
                "claude-sonnet-4-20250514": ModelCost(
                    input=3e-6, output=15e-6, cache_read=0.3e-6, cache_creation=3.75e-6
                ),
            }
        )
        cost = calc.calculate(
            model="claude-sonnet-4-20250514",
            input_tokens=200_000,
            output_tokens=1000,
        )
        assert cost is not None
        # Exactly at threshold — no surcharge
        expected = 200_000 * 3e-6 + 1000 * 15e-6
        assert cost == pytest.approx(expected)

    def test_no_long_context_surcharge_for_opus(self) -> None:
        """Opus models don't get long-context surcharge."""
        calc = self._make_calculator(
            {
                "claude-opus-4-6": ModelCost(input=15e-6, output=75e-6),
            }
        )
        cost = calc.calculate(
            model="claude-opus-4-6",
            input_tokens=300_000,
            output_tokens=1000,
        )
        assert cost is not None
        # No surcharge — standard rates with cache fallbacks (no cache tokens here)
        expected = 300_000 * 15e-6 + 1000 * 75e-6
        assert cost == pytest.approx(expected)

    def test_configurable_cache_creation_multiplier(self) -> None:
        """Cache creation multiplier parameter works."""
        calc = self._make_calculator(
            {
                "some-model": ModelCost(input=0.00001, output=0.00003),
            }
        )
        # Default (1.25) vs extended cache (2.0)
        cost_default = calc.calculate(
            model="some-model",
            input_tokens=0,
            output_tokens=0,
            cache_creation_tokens=10_000,
        )
        cost_extended = calc.calculate(
            model="some-model",
            input_tokens=0,
            output_tokens=0,
            cache_creation_tokens=10_000,
            cache_creation_multiplier=2.0,
        )
        assert cost_default is not None
        assert cost_extended is not None
        assert cost_default == pytest.approx(0.00001 * 1.25 * 10_000)
        assert cost_extended == pytest.approx(0.00001 * 2.0 * 10_000)
        assert cost_extended > cost_default
