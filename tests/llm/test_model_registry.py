"""Tests for OpenRouter-backed model registry."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from gobby.llm.model_registry import (
    ModelInfo,
    _parse_pricing,
    _provider_for_model,
    fetch_models_sync,
    group_by_provider,
    strip_provider_prefix,
)

# -- Fixtures ----------------------------------------------------------------

SAMPLE_OPENROUTER_RESPONSE = {
    "data": [
        {
            "id": "anthropic/claude-sonnet-4-6",
            "name": "Anthropic: Claude Sonnet 4.6",
            "context_length": 200000,
            "pricing": {
                "prompt": "0.000003",
                "completion": "0.000015",
                "input_cache_read": "0.0000003",
                "input_cache_write": "0.00000375",
            },
            "top_provider": {
                "context_length": 200000,
                "max_completion_tokens": 64000,
            },
        },
        {
            "id": "openai/gpt-4o",
            "name": "OpenAI: GPT-4o",
            "context_length": 128000,
            "pricing": {
                "prompt": "0.0000025",
                "completion": "0.00001",
            },
            "top_provider": {
                "context_length": 128000,
                "max_completion_tokens": 16384,
            },
        },
        {
            "id": "google/gemini-2.5-pro",
            "name": "Google: Gemini 2.5 Pro",
            "context_length": 1000000,
            "pricing": {
                "prompt": "0.00000125",
                "completion": "0.00001",
            },
            "top_provider": {
                "context_length": 1000000,
                "max_completion_tokens": 65536,
            },
        },
        # Should be filtered out — not a provider we care about
        {
            "id": "mistral/mistral-large",
            "name": "Mistral: Large",
            "context_length": 128000,
            "pricing": {"prompt": "0.000002", "completion": "0.000006"},
            "top_provider": {"context_length": 128000},
        },
        # Should be filtered out — free model (zero cost)
        {
            "id": "anthropic/claude-free",
            "name": "Free Claude",
            "context_length": 8000,
            "pricing": {"prompt": "0", "completion": "0"},
            "top_provider": {},
        },
    ]
}


# -- _parse_pricing ----------------------------------------------------------


class TestParsePricing:
    def test_parses_string_values(self) -> None:
        pricing = {
            "prompt": "0.000003",
            "completion": "0.000015",
            "input_cache_read": "0.0000003",
            "input_cache_write": "0.00000375",
        }
        inp, out, cr, cw = _parse_pricing(pricing)
        assert inp == 3e-6
        assert out == 15e-6
        assert cr == 3e-7
        assert cw == 3.75e-6

    def test_missing_cache_fields(self) -> None:
        pricing = {"prompt": "0.000003", "completion": "0.000015"}
        inp, out, cr, cw = _parse_pricing(pricing)
        assert inp == 3e-6
        assert out == 15e-6
        assert cr is None
        assert cw is None

    def test_none_pricing(self) -> None:
        assert _parse_pricing(None) == (0.0, 0.0, None, None)

    def test_empty_pricing(self) -> None:
        assert _parse_pricing({}) == (0.0, 0.0, None, None)

    def test_unparseable_values(self) -> None:
        pricing = {"prompt": "not-a-number", "completion": "also-bad"}
        inp, out, cr, cw = _parse_pricing(pricing)
        assert inp == 0.0
        assert out == 0.0


# -- _provider_for_model -----------------------------------------------------


class TestProviderForModel:
    def test_anthropic(self) -> None:
        assert _provider_for_model("anthropic/claude-opus-4-6") == "claude"

    def test_openai(self) -> None:
        assert _provider_for_model("openai/gpt-4o") == "codex"

    def test_google(self) -> None:
        assert _provider_for_model("google/gemini-2.5-pro") == "gemini"

    def test_unknown_provider(self) -> None:
        assert _provider_for_model("mistral/mistral-large") is None

    def test_no_prefix(self) -> None:
        assert _provider_for_model("claude-opus-4-6") is None


# -- fetch_models_sync -------------------------------------------------------


class TestFetchModelsSync:
    @patch("gobby.llm.model_registry.httpx.get")
    def test_fetches_and_filters(self, mock_get: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = SAMPLE_OPENROUTER_RESPONSE
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        models = fetch_models_sync()

        # 3 valid models (mistral filtered by provider, free claude filtered by zero cost)
        assert len(models) == 3
        providers = {m.provider for m in models}
        assert providers == {"claude", "codex", "gemini"}

    @patch("gobby.llm.model_registry.httpx.get")
    def test_parses_model_fields(self, mock_get: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = SAMPLE_OPENROUTER_RESPONSE
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        models = fetch_models_sync()
        claude = next(m for m in models if m.provider == "claude")

        assert claude.id == "anthropic/claude-sonnet-4-6"
        assert claude.name == "Anthropic: Claude Sonnet 4.6"
        assert claude.context_length == 200000
        assert claude.max_completion_tokens == 64000
        assert claude.input_cost_per_token == 3e-6
        assert claude.output_cost_per_token == 15e-6
        assert claude.cache_read_cost_per_token == 3e-7
        assert claude.cache_creation_cost_per_token == 3.75e-6

    @patch("gobby.llm.model_registry.httpx.get")
    def test_network_failure_returns_empty(self, mock_get: MagicMock) -> None:
        import httpx as _httpx

        mock_get.side_effect = _httpx.ConnectError("connection refused")
        models = fetch_models_sync()
        assert models == []

    @patch("gobby.llm.model_registry.httpx.get")
    def test_http_error_returns_empty(self, mock_get: MagicMock) -> None:
        import httpx as _httpx

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = _httpx.HTTPStatusError(
            "500", request=MagicMock(), response=MagicMock()
        )
        mock_get.return_value = mock_response
        models = fetch_models_sync()
        assert models == []

    @patch("gobby.llm.model_registry.httpx.get")
    def test_malformed_json_returns_empty(self, mock_get: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.side_effect = ValueError("bad json")
        mock_get.return_value = mock_response
        models = fetch_models_sync()
        assert models == []

    @patch("gobby.llm.model_registry.httpx.get")
    def test_empty_data_returns_empty(self, mock_get: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"data": []}
        mock_get.return_value = mock_response
        models = fetch_models_sync()
        assert models == []


# -- group_by_provider -------------------------------------------------------


class TestGroupByProvider:
    def test_groups_correctly(self) -> None:
        models = [
            ModelInfo("anthropic/a", "A", "claude", 100000, None, 1e-6, 5e-6),
            ModelInfo("anthropic/b", "B", "claude", 200000, None, 3e-6, 15e-6),
            ModelInfo("openai/c", "C", "codex", 128000, None, 2e-6, 10e-6),
        ]
        grouped = group_by_provider(models)
        assert len(grouped["claude"]) == 2
        assert len(grouped["codex"]) == 1
        assert "gemini" not in grouped

    def test_empty_list(self) -> None:
        assert group_by_provider([]) == {}


# -- strip_provider_prefix ---------------------------------------------------


class TestStripProviderPrefix:
    def test_strips_anthropic(self) -> None:
        assert strip_provider_prefix("anthropic/claude-opus-4-6") == "claude-opus-4-6"

    def test_strips_openai(self) -> None:
        assert strip_provider_prefix("openai/gpt-4o") == "gpt-4o"

    def test_no_prefix(self) -> None:
        assert strip_provider_prefix("claude-opus-4-6") == "claude-opus-4-6"
