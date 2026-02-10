"""Tests for SearchCoordinator with UnifiedSearcher integration."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from gobby.config.persistence import MemoryConfig
from gobby.memory.search.coordinator import SearchCoordinator
from gobby.storage.database import LocalDatabase
from gobby.storage.memories import LocalMemoryManager
from gobby.storage.migrations import run_migrations

pytestmark = pytest.mark.unit


def _setup(tmp_path, search_backend: str = "tfidf") -> tuple[SearchCoordinator, LocalMemoryManager]:
    """Create a coordinator with a fresh database and some test memories."""
    db_path = tmp_path / "test.db"
    db = LocalDatabase(db_path)
    run_migrations(db)

    # Create project
    db.execute(
        "INSERT INTO projects (id, name, created_at, updated_at) "
        "VALUES (?, ?, datetime('now'), datetime('now'))",
        ("test-project", "Test Project"),
    )

    storage = LocalMemoryManager(db)
    config = MemoryConfig(search_backend=search_backend)
    coordinator = SearchCoordinator(storage=storage, config=config, db=db)
    return coordinator, storage


def _add_memories(storage: LocalMemoryManager, project_id: str = "test-project") -> list[str]:
    """Add some test memories and return their IDs."""
    ids = []
    memories = [
        ("User prefers dark mode for all applications", "preference"),
        ("The API uses REST endpoints at /api/v1", "fact"),
        ("Database migrations run on startup automatically", "fact"),
    ]
    for content, mtype in memories:
        m = storage.create_memory(
            project_id=project_id,
            content=content,
            memory_type=mtype,
        )
        ids.append(m.id)
    return ids


# =============================================================================
# Backward compatibility with tfidf mode
# =============================================================================


class TestTFIDFBackwardCompat:
    """Test that tfidf mode continues to work as before."""

    def test_tfidf_mode_uses_tfidf_backend(self, tmp_path) -> None:
        """Coordinator with tfidf search_backend should use TFIDFSearcher."""
        coordinator, storage = _setup(tmp_path, "tfidf")
        _add_memories(storage)

        # Search should work with TF-IDF
        results = coordinator.search("dark mode", project_id="test-project")
        assert len(results) >= 1
        assert any("dark mode" in m.content.lower() for m in results)

    def test_text_mode_uses_text_backend(self, tmp_path) -> None:
        """Coordinator with text search_backend should use TextSearcher."""
        coordinator, storage = _setup(tmp_path, "text")
        _add_memories(storage)

        results = coordinator.search("dark mode", project_id="test-project")
        assert len(results) >= 1


# =============================================================================
# UnifiedSearcher initialization for new modes
# =============================================================================


class TestUnifiedSearcherInit:
    """Test that coordinator initializes UnifiedSearcher for auto/embedding/hybrid."""

    def test_auto_mode_creates_unified_searcher(self, tmp_path) -> None:
        """Coordinator with auto search_backend should use UnifiedSearcher."""
        coordinator, storage = _setup(tmp_path, "auto")
        _add_memories(storage)

        # Should have a unified searcher, not a plain SearchBackend
        assert coordinator._unified_searcher is not None

    def test_hybrid_mode_creates_unified_searcher(self, tmp_path) -> None:
        """Coordinator with hybrid search_backend should use UnifiedSearcher."""
        coordinator, storage = _setup(tmp_path, "hybrid")
        assert coordinator._unified_searcher is not None

    def test_embedding_mode_creates_unified_searcher(self, tmp_path) -> None:
        """Coordinator with embedding search_backend should use UnifiedSearcher."""
        coordinator, storage = _setup(tmp_path, "embedding")
        assert coordinator._unified_searcher is not None

    def test_tfidf_mode_does_not_create_unified_searcher(self, tmp_path) -> None:
        """Coordinator with tfidf search_backend should NOT use UnifiedSearcher."""
        coordinator, _ = _setup(tmp_path, "tfidf")
        assert coordinator._unified_searcher is None


# =============================================================================
# Config mapping to SearchConfig
# =============================================================================


class TestConfigMapping:
    """Test that MemoryConfig fields map to SearchConfig correctly."""

    def test_maps_embedding_model(self, tmp_path) -> None:
        """embedding_model should map from MemoryConfig to SearchConfig."""
        db_path = tmp_path / "test.db"
        db = LocalDatabase(db_path)
        run_migrations(db)
        db.execute(
            "INSERT INTO projects (id, name, created_at, updated_at) "
            "VALUES (?, ?, datetime('now'), datetime('now'))",
            ("p", "P"),
        )
        storage = LocalMemoryManager(db)
        config = MemoryConfig(
            search_backend="auto",
            embedding_model="text-embedding-3-large",
            embedding_weight=0.7,
            tfidf_weight=0.3,
        )
        coordinator = SearchCoordinator(storage=storage, config=config, db=db)
        searcher = coordinator._unified_searcher

        assert searcher is not None
        assert searcher.config.embedding_model == "text-embedding-3-large"
        assert searcher.config.embedding_weight == 0.7
        assert searcher.config.tfidf_weight == 0.3
        assert searcher.config.mode == "auto"


# =============================================================================
# Search with UnifiedSearcher (auto mode fallback to TF-IDF)
# =============================================================================


class TestSearchWithUnifiedSearcher:
    """Test search operations through UnifiedSearcher (auto mode falls back to TF-IDF)."""

    def test_auto_mode_search_returns_results(self, tmp_path) -> None:
        """Auto mode should return search results (falls back to TF-IDF without API key)."""
        coordinator, storage = _setup(tmp_path, "auto")
        _add_memories(storage)

        results = coordinator.search("dark mode preference", project_id="test-project")
        assert len(results) >= 1

    def test_auto_mode_fallback_to_tfidf(self, tmp_path) -> None:
        """Auto mode without embedding API should fallback to TF-IDF gracefully."""
        coordinator, storage = _setup(tmp_path, "auto")
        _add_memories(storage)

        # Mock embedding unavailable so auto mode falls back to TF-IDF
        with patch(
            "gobby.search.unified.is_embedding_available", return_value=False
        ):
            coordinator.ensure_fitted()

        searcher = coordinator._unified_searcher
        assert searcher is not None
        assert searcher.is_using_fallback()

    def test_hybrid_mode_search_returns_results(self, tmp_path) -> None:
        """Hybrid mode should return results (TF-IDF component works without API key)."""
        coordinator, storage = _setup(tmp_path, "hybrid")
        _add_memories(storage)

        results = coordinator.search("REST API endpoints", project_id="test-project")
        assert len(results) >= 1


# =============================================================================
# Reindex with UnifiedSearcher
# =============================================================================


class TestReindex:
    """Test that reindex rebuilds the UnifiedSearcher index."""

    def test_reindex_with_unified_searcher(self, tmp_path) -> None:
        """Reindex should rebuild the UnifiedSearcher index and report stats."""
        coordinator, storage = _setup(tmp_path, "auto")
        _add_memories(storage)

        stats = coordinator.reindex()
        assert stats["success"] is True
        assert stats["memory_count"] == 3
        assert stats["backend_type"] == "auto"

    def test_reindex_with_tfidf_mode(self, tmp_path) -> None:
        """Reindex in tfidf mode should work as before."""
        coordinator, storage = _setup(tmp_path, "tfidf")
        _add_memories(storage)

        stats = coordinator.reindex()
        assert stats["success"] is True
        assert stats["memory_count"] == 3

    def test_mark_refit_needed_triggers_refit(self, tmp_path) -> None:
        """After mark_refit_needed, next search should refit."""
        coordinator, storage = _setup(tmp_path, "auto")
        _add_memories(storage)

        coordinator.ensure_fitted()
        coordinator.mark_refit_needed()

        # Should refit on next search
        results = coordinator.search("dark mode", project_id="test-project")
        assert len(results) >= 1
