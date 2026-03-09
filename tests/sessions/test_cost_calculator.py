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
