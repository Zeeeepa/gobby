"""Tests for gobby.conductor.pricing module.

Tests for the TokenTracker class that uses LiteLLM pricing utilities
to calculate costs for various models.
"""

from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit

class TestTokenTracker:
    """Tests for TokenTracker class."""

    def test_calculate_cost_claude_model(self) -> None:
        """Calculate cost for Claude model using LiteLLM."""
        from gobby.conductor.pricing import TokenTracker

        tracker = TokenTracker()

        # claude-3-5-sonnet has known pricing
        # We're testing that the calculation works, not the exact prices
        cost = tracker.calculate_cost(
            model="claude-3-5-sonnet-20241022",
            input_tokens=1000,
            output_tokens=500,
        )

        # Cost should be a positive float
        assert isinstance(cost, float)
        assert cost >= 0.0

    def test_calculate_cost_gemini_model(self) -> None:
        """Calculate cost for Gemini model using LiteLLM."""
        from gobby.conductor.pricing import TokenTracker

        tracker = TokenTracker()

        cost = tracker.calculate_cost(
            model="gemini/gemini-2.0-flash-exp",
            input_tokens=1000,
            output_tokens=500,
        )

        assert isinstance(cost, float)
        assert cost >= 0.0

    def test_calculate_cost_gpt_model(self) -> None:
        """Calculate cost for GPT model using LiteLLM."""
        from gobby.conductor.pricing import TokenTracker

        tracker = TokenTracker()

        cost = tracker.calculate_cost(
            model="gpt-4o",
            input_tokens=1000,
            output_tokens=500,
        )

        assert isinstance(cost, float)
        assert cost >= 0.0

    def test_calculate_cost_unknown_model(self) -> None:
        """Calculate cost for unknown model returns 0."""
        from gobby.conductor.pricing import TokenTracker

        tracker = TokenTracker()

        # Unknown model should return 0 rather than raising
        cost = tracker.calculate_cost(
            model="unknown-model-xyz",
            input_tokens=1000,
            output_tokens=500,
        )

        assert cost == 0.0

    def test_calculate_cost_zero_tokens(self) -> None:
        """Calculate cost with zero tokens returns 0."""
        from gobby.conductor.pricing import TokenTracker

        tracker = TokenTracker()

        cost = tracker.calculate_cost(
            model="claude-3-5-sonnet-20241022",
            input_tokens=0,
            output_tokens=0,
        )

        assert cost == 0.0

    def test_calculate_cost_from_response(self) -> None:
        """Calculate cost from LiteLLM response object."""
        from gobby.conductor.pricing import TokenTracker

        tracker = TokenTracker()

        # Mock a response object
        mock_response = MagicMock()
        mock_response.model = "claude-3-5-sonnet-20241022"
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 1000
        mock_response.usage.completion_tokens = 500

        # Mock litellm.completion_cost to return a known value
        with patch("litellm.completion_cost") as mock_completion_cost:
            mock_completion_cost.return_value = 0.015
            cost = tracker.calculate_cost_from_response(mock_response)

        assert cost == 0.015
        mock_completion_cost.assert_called_once_with(mock_response)

    def test_calculate_cost_from_response_error(self) -> None:
        """Calculate cost from response handles errors gracefully."""
        from gobby.conductor.pricing import TokenTracker

        tracker = TokenTracker()

        mock_response = MagicMock()

        # Mock litellm.completion_cost to raise an error
        with patch("litellm.completion_cost") as mock_completion_cost:
            mock_completion_cost.side_effect = Exception("Price not found")
            cost = tracker.calculate_cost_from_response(mock_response)

        assert cost == 0.0

    def test_track_usage(self) -> None:
        """Track usage accumulates costs and tokens."""
        from gobby.conductor.pricing import TokenTracker

        tracker = TokenTracker()

        # Track first usage
        tracker.track_usage(
            model="claude-3-5-sonnet-20241022",
            input_tokens=1000,
            output_tokens=500,
        )

        assert tracker.total_input_tokens == 1000
        assert tracker.total_output_tokens == 500

        # Track second usage
        tracker.track_usage(
            model="claude-3-5-sonnet-20241022",
            input_tokens=500,
            output_tokens=250,
        )

        assert tracker.total_input_tokens == 1500
        assert tracker.total_output_tokens == 750

    def test_track_usage_accumulates_cost(self) -> None:
        """Track usage accumulates total cost."""
        from gobby.conductor.pricing import TokenTracker

        tracker = TokenTracker()

        # Mock cost calculation
        with patch.object(tracker, "calculate_cost") as mock_calc:
            mock_calc.return_value = 0.01
            tracker.track_usage("claude-3-5-sonnet", 1000, 500)
            tracker.track_usage("claude-3-5-sonnet", 1000, 500)

        assert tracker.total_cost == 0.02

    def test_reset(self) -> None:
        """Reset clears all tracked usage."""
        from gobby.conductor.pricing import TokenTracker

        tracker = TokenTracker()
        tracker.track_usage("claude-3-5-sonnet", 1000, 500)

        assert tracker.total_input_tokens > 0

        tracker.reset()

        assert tracker.total_input_tokens == 0
        assert tracker.total_output_tokens == 0
        assert tracker.total_cost == 0.0

    def test_get_summary(self) -> None:
        """Get summary returns dict with usage info."""
        from gobby.conductor.pricing import TokenTracker

        tracker = TokenTracker()
        tracker.track_usage("claude-3-5-sonnet", 1000, 500)

        summary = tracker.get_summary()

        assert "total_input_tokens" in summary
        assert "total_output_tokens" in summary
        assert "total_cost" in summary
        assert summary["total_input_tokens"] == 1000
        assert summary["total_output_tokens"] == 500


class TestTokenTrackerWithCacheTokens:
    """Tests for TokenTracker with cache token support."""

    def test_calculate_cost_with_cache_tokens(self) -> None:
        """Calculate cost with cache tokens for models that support it."""
        from gobby.conductor.pricing import TokenTracker

        tracker = TokenTracker()

        # Some models support cache tokens which have different pricing
        cost = tracker.calculate_cost(
            model="claude-3-5-sonnet-20241022",
            input_tokens=1000,
            output_tokens=500,
            cache_read_tokens=200,
            cache_write_tokens=100,
        )

        # Just ensure it works, cost depends on model pricing
        assert isinstance(cost, float)
        assert cost >= 0.0

    def test_track_usage_with_cache_tokens(self) -> None:
        """Track usage with cache tokens accumulates correctly."""
        from gobby.conductor.pricing import TokenTracker

        tracker = TokenTracker()

        tracker.track_usage(
            model="claude-3-5-sonnet",
            input_tokens=1000,
            output_tokens=500,
            cache_read_tokens=200,
            cache_write_tokens=100,
        )

        assert tracker.total_cache_read_tokens == 200
        assert tracker.total_cache_write_tokens == 100

        summary = tracker.get_summary()
        assert summary["total_cache_read_tokens"] == 200
        assert summary["total_cache_write_tokens"] == 100
