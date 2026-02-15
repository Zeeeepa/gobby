"""Tests for updated maintenance.py — no decay, Qdrant stats."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from gobby.memory.services.maintenance import get_stats

pytestmark = pytest.mark.unit


def _make_storage(memories=None):
    """Create a mock storage with configurable memories."""
    storage = MagicMock()
    storage.list_memories.return_value = memories or []
    return storage


def _make_memory(memory_type="fact"):
    """Create a mock memory."""
    m = MagicMock()
    m.memory_type = memory_type
    return m


class TestGetStatsNoDecay:
    """Tests that decay_memories is removed."""

    def test_decay_memories_not_importable(self) -> None:
        """decay_memories function should not exist in maintenance module."""
        from gobby.memory.services import maintenance

        assert not hasattr(maintenance, "decay_memories")


class TestGetStatsNoMem0Sync:
    """Tests that mem0 sync stats are removed."""

    def test_no_mem0_sync_in_stats(self) -> None:
        """get_stats should not include mem0_sync in output."""
        storage = _make_storage([_make_memory()])
        db = MagicMock()

        stats = get_stats(storage, db, project_id=None)

        assert "mem0_sync" not in stats

    def test_get_stats_no_mem0_client_param(self) -> None:
        """get_stats should not accept mem0_client parameter."""
        import inspect

        sig = inspect.signature(get_stats)
        assert "mem0_client" not in sig.parameters


class TestGetStatsVectorCount:
    """Tests for vector_count in get_stats."""

    def test_vector_count_included_when_vector_store_provided(self) -> None:
        """get_stats includes vector_count when vector_store is given."""
        storage = _make_storage([_make_memory()])
        db = MagicMock()
        vector_store = MagicMock()
        vector_store.count = AsyncMock(return_value=42)

        stats = get_stats(storage, db, project_id=None, vector_store=vector_store)

        assert stats["vector_count"] == 42

    def test_no_vector_count_without_vector_store(self) -> None:
        """get_stats omits vector_count when no vector_store."""
        storage = _make_storage([_make_memory()])
        db = MagicMock()

        stats = get_stats(storage, db, project_id=None)

        assert "vector_count" not in stats

    def test_vector_count_graceful_on_error(self) -> None:
        """get_stats handles vector_store errors gracefully."""
        storage = _make_storage([_make_memory()])
        db = MagicMock()
        vector_store = MagicMock()
        vector_store.count = AsyncMock(side_effect=Exception("Qdrant down"))

        stats = get_stats(storage, db, project_id=None, vector_store=vector_store)

        assert stats["vector_count"] == -1


class TestGetStatsBasicBehavior:
    """Tests that basic stats behavior is preserved."""

    def test_empty_memories(self) -> None:
        """get_stats returns zeros for empty memory store."""
        storage = _make_storage([])
        db = MagicMock()

        stats = get_stats(storage, db, project_id=None)

        assert stats["total_count"] == 0
        assert stats["by_type"] == {}

    def test_counts_by_type(self) -> None:
        """get_stats counts memories by type."""
        storage = _make_storage([
            _make_memory("fact"),
            _make_memory("fact"),
            _make_memory("preference"),
        ])
        db = MagicMock()

        stats = get_stats(storage, db, project_id=None)

        assert stats["total_count"] == 3
        assert stats["by_type"]["fact"] == 2
        assert stats["by_type"]["preference"] == 1

    def test_project_id_passed_through(self) -> None:
        """get_stats passes project_id to storage."""
        storage = _make_storage([])
        db = MagicMock()

        get_stats(storage, db, project_id="proj-1")

        storage.list_memories.assert_called_with(project_id="proj-1", limit=10000)
