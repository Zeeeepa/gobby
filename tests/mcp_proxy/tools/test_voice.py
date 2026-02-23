"""Tests for gobby-voice MCP tool registry (Whisper custom vocabulary)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from gobby.config.app import DaemonConfig
from gobby.mcp_proxy.tools.voice import create_voice_registry

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_registry(
    vocab: list[str] | None = None,
    whisper_prompt: str = "Gobby",
):
    """Create a voice registry with mocked dependencies."""
    config_dict = {"voice": {"whisper_prompt": whisper_prompt}}
    if vocab is not None:
        config_dict["voice"]["whisper_vocabulary"] = vocab
    config = DaemonConfig(**config_dict)

    config_store = MagicMock()
    config_setter = MagicMock()

    registry = create_voice_registry(
        config=config,
        config_store=config_store,
        config_setter=config_setter,
    )
    return registry, config_store, config_setter


def _call_tool(registry, name: str, **kwargs):
    """Call a tool on the registry by name."""
    tool = registry.get_tool(name)
    assert tool is not None, f"Tool '{name}' not found"
    return tool(**kwargs)


# ---------------------------------------------------------------------------
# add_vocab
# ---------------------------------------------------------------------------


class TestAddVocab:
    def test_add_single_term(self) -> None:
        registry, config_store, _ = _make_registry(vocab=["Gobby"])
        result = _call_tool(registry, "add_vocab", terms="Kubernetes")
        assert result["success"] is True
        assert result["added"] == ["Kubernetes"]
        assert result["total"] == 2
        config_store.set.assert_called_once()

    def test_add_multiple_terms(self) -> None:
        registry, config_store, _ = _make_registry(vocab=[])
        result = _call_tool(registry, "add_vocab", terms="FastAPI, Pydantic, Redis")
        assert result["success"] is True
        assert result["added"] == ["FastAPI", "Pydantic", "Redis"]
        assert result["total"] == 3

    def test_dedup_case_insensitive(self) -> None:
        registry, config_store, _ = _make_registry(vocab=["Gobby", "MCP"])
        result = _call_tool(registry, "add_vocab", terms="gobby, NewTerm")
        assert result["success"] is True
        assert result["added"] == ["NewTerm"]
        assert result["already_existed"] == 1
        assert result["total"] == 3

    def test_all_duplicates(self) -> None:
        registry, config_store, _ = _make_registry(vocab=["Gobby", "MCP"])
        result = _call_tool(registry, "add_vocab", terms="gobby, mcp")
        assert result["success"] is True
        assert result["added"] == []
        assert result["already_existed"] == 2
        # config_store.set should not be called if nothing was added
        config_store.set.assert_not_called()

    def test_empty_terms(self) -> None:
        registry, config_store, _ = _make_registry(vocab=[])
        result = _call_tool(registry, "add_vocab", terms="  ,  , ")
        assert result["success"] is False
        assert "No valid terms" in result["error"]

    def test_dedup_within_input(self) -> None:
        registry, _, _ = _make_registry(vocab=[])
        result = _call_tool(registry, "add_vocab", terms="FastAPI, fastapi, FASTAPI")
        assert result["success"] is True
        assert result["added"] == ["FastAPI"]
        assert result["total"] == 1


# ---------------------------------------------------------------------------
# remove_vocab
# ---------------------------------------------------------------------------


class TestRemoveVocab:
    def test_remove_existing(self) -> None:
        registry, config_store, _ = _make_registry(vocab=["Gobby", "MCP", "FastAPI"])
        result = _call_tool(registry, "remove_vocab", terms="MCP")
        assert result["success"] is True
        assert result["removed"] == 1
        assert result["total"] == 2
        config_store.set.assert_called_once()

    def test_remove_case_insensitive(self) -> None:
        registry, _, _ = _make_registry(vocab=["Gobby", "MCP"])
        result = _call_tool(registry, "remove_vocab", terms="gobby")
        assert result["success"] is True
        assert result["removed"] == 1
        assert result["total"] == 1

    def test_remove_missing(self) -> None:
        registry, config_store, _ = _make_registry(vocab=["Gobby"])
        result = _call_tool(registry, "remove_vocab", terms="NonExistent")
        assert result["success"] is True
        assert result["removed"] == 0
        assert result["not_found"] == 1
        # config_store.set should not be called if nothing was removed
        config_store.set.assert_not_called()

    def test_empty_terms(self) -> None:
        registry, _, _ = _make_registry(vocab=["Gobby"])
        result = _call_tool(registry, "remove_vocab", terms="  ,  ")
        assert result["success"] is False
        assert "No valid terms" in result["error"]


# ---------------------------------------------------------------------------
# list_vocab
# ---------------------------------------------------------------------------


class TestListVocab:
    def test_list_empty(self) -> None:
        registry, _, _ = _make_registry(vocab=[], whisper_prompt="")
        result = _call_tool(registry, "list_vocab")
        assert result["success"] is True
        assert result["vocabulary"] == []
        assert result["count"] == 0
        assert result["whisper_prompt"] == ""

    def test_list_populated(self) -> None:
        registry, _, _ = _make_registry(
            vocab=["Gobby", "MCP", "FastAPI"],
            whisper_prompt="Gobby",
        )
        result = _call_tool(registry, "list_vocab")
        assert result["success"] is True
        assert result["vocabulary"] == ["Gobby", "MCP", "FastAPI"]
        assert result["count"] == 3
        assert result["whisper_prompt"] == "Gobby"


# ---------------------------------------------------------------------------
# clear_vocab
# ---------------------------------------------------------------------------


class TestClearVocab:
    def test_clear_populated(self) -> None:
        registry, config_store, _ = _make_registry(vocab=["Gobby", "MCP"])
        result = _call_tool(registry, "clear_vocab")
        assert result["success"] is True
        assert result["cleared"] == 2
        config_store.set.assert_called_once()

    def test_clear_already_empty(self) -> None:
        registry, config_store, _ = _make_registry(vocab=[])
        result = _call_tool(registry, "clear_vocab")
        assert result["success"] is True
        assert result["cleared"] == 0

    def test_list_after_clear(self) -> None:
        registry, _, _ = _make_registry(vocab=["Gobby", "MCP"])
        _call_tool(registry, "clear_vocab")
        result = _call_tool(registry, "list_vocab")
        assert result["vocabulary"] == []
        assert result["count"] == 0


# ---------------------------------------------------------------------------
# Persistence (config_store.set + config_setter called correctly)
# ---------------------------------------------------------------------------


class TestPersistence:
    def test_add_calls_config_store_and_setter(self) -> None:
        registry, config_store, config_setter = _make_registry(vocab=["Gobby"])
        _call_tool(registry, "add_vocab", terms="NewTerm")

        config_store.set.assert_called_once()
        args = config_store.set.call_args
        assert args[0][0] == "voice.whisper_vocabulary"
        assert "NewTerm" in args[0][1]
        assert args[1]["source"] == "mcp"

        config_setter.assert_called_once()
        new_config = config_setter.call_args[0][0]
        assert isinstance(new_config, DaemonConfig)

    def test_remove_calls_config_store_and_setter(self) -> None:
        registry, config_store, config_setter = _make_registry(vocab=["Gobby", "MCP"])
        _call_tool(registry, "remove_vocab", terms="MCP")

        config_store.set.assert_called_once()
        args = config_store.set.call_args
        assert args[0][0] == "voice.whisper_vocabulary"
        assert "MCP" not in args[0][1]

        config_setter.assert_called_once()

    def test_clear_calls_config_store_with_empty_list(self) -> None:
        registry, config_store, config_setter = _make_registry(vocab=["Gobby"])
        _call_tool(registry, "clear_vocab")

        config_store.set.assert_called_once()
        args = config_store.set.call_args
        assert args[0][0] == "voice.whisper_vocabulary"
        assert args[0][1] == []

        config_setter.assert_called_once()
