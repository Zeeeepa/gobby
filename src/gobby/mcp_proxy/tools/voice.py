"""
Internal MCP tools for Whisper custom vocabulary management.

Exposes functionality for:
- add_vocab(terms): Add terms to Whisper vocabulary (comma-separated, deduped)
- remove_vocab(terms): Remove terms from Whisper vocabulary (case-insensitive)
- list_vocab(): List current vocabulary and whisper_prompt
- clear_vocab(): Clear all vocabulary terms
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from gobby.mcp_proxy.tools.internal import InternalToolRegistry

if TYPE_CHECKING:
    from gobby.config.app import DaemonConfig
    from gobby.storage.config_store import ConfigStore

logger = logging.getLogger(__name__)

__all__ = ["create_voice_registry"]


def create_voice_registry(
    config: DaemonConfig,
    config_store: ConfigStore,
    config_setter: Callable[[DaemonConfig], None],
) -> InternalToolRegistry:
    """
    Create a voice tool registry for managing Whisper custom vocabulary.

    Args:
        config: Current in-memory DaemonConfig
        config_store: DB-backed config key-value store
        config_setter: Callback to update in-memory config on ServiceContainer

    Returns:
        InternalToolRegistry with voice tools registered
    """
    registry = InternalToolRegistry(
        name="gobby-voice",
        description="Whisper custom vocabulary - add_vocab, remove_vocab, list_vocab, clear_vocab",
    )

    # Mutable reference so tools always read the latest config
    _state: dict[str, DaemonConfig] = {"config": config}

    def _current_vocab() -> list[str]:
        return list(_state["config"].voice.whisper_vocabulary)

    def _persist(terms: list[str]) -> None:
        """Persist vocabulary to DB and update in-memory config."""
        from gobby.config.app import DaemonConfig as DaemonConfigCls
        from gobby.config.app import deep_merge
        from gobby.storage.config_store import unflatten_config

        config_store.set("voice.whisper_vocabulary", terms, source="mcp")

        update_nested = unflatten_config({"voice.whisper_vocabulary": terms})
        current_dict = _state["config"].model_dump(mode="json")
        deep_merge(current_dict, update_nested)
        new_config = DaemonConfigCls(**current_dict)
        _state["config"] = new_config
        config_setter(new_config)

    @registry.tool(
        name="add_vocab",
        description="Add terms to Whisper STT vocabulary. Comma-separated, deduplicates case-insensitively. Example: add_vocab(terms='Kubernetes, FastAPI')",
    )
    def add_vocab(terms: str) -> dict[str, Any]:
        """Add one or more terms to the vocabulary."""
        new_terms = [t.strip() for t in terms.split(",") if t.strip()]
        if not new_terms:
            return {"success": False, "error": "No valid terms provided"}

        current = _current_vocab()
        existing_lower = {t.lower() for t in current}
        added = []
        for term in new_terms:
            if term.lower() not in existing_lower:
                current.append(term)
                existing_lower.add(term.lower())
                added.append(term)

        if added:
            _persist(current)

        return {
            "success": True,
            "added": added,
            "already_existed": len(new_terms) - len(added),
            "total": len(current),
        }

    @registry.tool(
        name="remove_vocab",
        description="Remove terms from Whisper STT vocabulary. Comma-separated, case-insensitive matching.",
    )
    def remove_vocab(terms: str) -> dict[str, Any]:
        """Remove one or more terms from the vocabulary."""
        to_remove = {t.strip().lower() for t in terms.split(",") if t.strip()}
        if not to_remove:
            return {"success": False, "error": "No valid terms provided"}

        current = _current_vocab()
        original_count = len(current)
        remaining = [t for t in current if t.lower() not in to_remove]
        removed_count = original_count - len(remaining)

        if removed_count > 0:
            _persist(remaining)

        return {
            "success": True,
            "removed": removed_count,
            "not_found": len(to_remove) - removed_count,
            "total": len(remaining),
        }

    @registry.tool(
        name="list_vocab",
        description="List current Whisper STT vocabulary terms and prompt.",
    )
    def list_vocab() -> dict[str, Any]:
        """List the current vocabulary and whisper_prompt."""
        vocab = _current_vocab()
        return {
            "success": True,
            "vocabulary": vocab,
            "count": len(vocab),
            "whisper_prompt": _state["config"].voice.whisper_prompt,
        }

    @registry.tool(
        name="clear_vocab",
        description="Clear all Whisper STT vocabulary terms.",
    )
    def clear_vocab() -> dict[str, Any]:
        """Clear all vocabulary terms."""
        current_count = len(_current_vocab())
        _persist([])
        return {
            "success": True,
            "cleared": current_count,
        }

    return registry
