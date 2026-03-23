"""Tests for resolve_context_window in gobby.llm.claude_models.

Verifies the priority order:
1. Config overrides (model substring -> context window)
2. Built-in Claude family map (opus=1M, sonnet/haiku=200K)
3. litellm lookup for non-Claude models only

Note: SDK-reported contextWindow (2nd arg) is deprecated and ignored.
"""

from unittest.mock import MagicMock, patch

import pytest

from gobby.llm.claude_models import (
    _CLAUDE_CONTEXT_WINDOWS,
    CLAUDE_DEFAULT_CONTEXT_WINDOW,
    resolve_context_window,
)

pytestmark = pytest.mark.unit


class TestResolveContextWindow:
    """Tests for resolve_context_window()."""

    def test_sdk_context_window_ignored(self) -> None:
        """SDK-reported contextWindow (2nd arg) is deprecated and ignored."""
        model_usage = {"contextWindow": 180_000}
        result = resolve_context_window("claude-opus-4-6", model_usage)
        assert result == 1_000_000  # Built-in map, _unused ignored

    def test_sdk_1m_context_window_trusted(self) -> None:
        """If the SDK reports 1M context window, trust it (user may have the beta)."""
        model_usage = {"contextWindow": 1_000_000}
        result = resolve_context_window("claude-opus-4-6", model_usage)
        assert result == 1_000_000

    def test_claude_model_family_windows(self) -> None:
        """Claude models without SDK usage should return family-specific windows."""
        assert resolve_context_window("claude-opus-4-6", None) == 1_000_000
        assert resolve_context_window("claude-sonnet-4-6", None) == 200_000
        assert resolve_context_window("claude-haiku-4-5", None) == 200_000

    def test_claude_name_variations(self) -> None:
        """Various Claude model name formats should return family-specific windows."""
        opus_names = ["opus", "claude-3-opus-20240229"]
        for name in opus_names:
            result = resolve_context_window(name, None)
            assert result == _CLAUDE_CONTEXT_WINDOWS["opus"], f"Failed for model name: {name}"

        sonnet_names = ["sonnet", "claude-3-5-sonnet-20241022", "anthropic/claude-sonnet-4-6"]
        for name in sonnet_names:
            result = resolve_context_window(name, None)
            assert result == _CLAUDE_CONTEXT_WINDOWS["sonnet"], f"Failed for model name: {name}"

        haiku_names = ["haiku", "claude-3-haiku-20240307"]
        for name in haiku_names:
            result = resolve_context_window(name, None)
            assert result == _CLAUDE_CONTEXT_WINDOWS["haiku"], f"Failed for model name: {name}"

    def test_non_claude_model_uses_litellm(self) -> None:
        """Non-Claude models should fall through to litellm."""
        mock_litellm = MagicMock()
        mock_litellm.get_model_info.return_value = {"max_input_tokens": 128_000}

        with patch.dict("sys.modules", {"litellm": mock_litellm}):
            result = resolve_context_window("gpt-4o", None)

        assert result == 128_000
        mock_litellm.get_model_info.assert_called_once_with(model="gpt-4o")

    def test_litellm_failure_returns_none(self) -> None:
        """If litellm fails for a non-Claude model, return None."""
        mock_litellm = MagicMock()
        mock_litellm.get_model_info.side_effect = KeyError("Unknown model")

        with patch.dict("sys.modules", {"litellm": mock_litellm}):
            result = resolve_context_window("unknown-model-xyz", None)

        assert result is None

    def test_none_model_returns_none(self) -> None:
        """None model with no SDK usage should return None."""
        assert resolve_context_window(None, None) is None

    def test_none_model_with_sdk_usage_ignored(self) -> None:
        """None model — SDK usage (2nd arg) is ignored, returns None."""
        model_usage = {"contextWindow": 200_000}
        result = resolve_context_window(None, model_usage)
        assert result is None

    def test_empty_model_usage_dict(self) -> None:
        """Empty model_usage dict (no contextWindow key) should fall through."""
        result = resolve_context_window("claude-opus-4-6", {})
        assert result == 1_000_000

    def test_claude_model_never_calls_litellm(self) -> None:
        """Claude models should never reach the litellm fallback path."""
        mock_litellm = MagicMock()

        with patch.dict("sys.modules", {"litellm": mock_litellm}):
            result = resolve_context_window("claude-sonnet-4-6", None)

        assert result == 200_000
        mock_litellm.get_model_info.assert_not_called()

    def test_config_overrides_win_over_builtin(self) -> None:
        """Config overrides should take precedence over built-in map."""
        overrides = {"opus": 500_000}
        result = resolve_context_window("claude-opus-4-6", None, overrides=overrides)
        assert result == 500_000

    def test_config_overrides_partial(self) -> None:
        """Config overrides only affect matched families, others use built-in."""
        overrides = {"opus": 500_000}
        assert resolve_context_window("claude-opus-4-6", None, overrides=overrides) == 500_000
        assert resolve_context_window("claude-sonnet-4-6", None, overrides=overrides) == 200_000

    def test_overrides_win_sdk_ignored(self) -> None:
        """Config overrides win; SDK-reported contextWindow (2nd arg) is ignored."""
        overrides = {"opus": 500_000}
        model_usage = {"contextWindow": 180_000}
        result = resolve_context_window("claude-opus-4-6", model_usage, overrides=overrides)
        assert result == 500_000  # Overrides win, _unused ignored

    def test_unknown_claude_model_returns_default(self) -> None:
        """A Claude model not matching any family should return CLAUDE_DEFAULT_CONTEXT_WINDOW."""
        result = resolve_context_window("claude-unknown-model", None)
        assert result == CLAUDE_DEFAULT_CONTEXT_WINDOW
