"""Tests for SearchCoordinator with TF-IDF and text search backends.

Note: UnifiedSearcher (auto/embedding/hybrid) modes were removed along with
the search_backend config field as part of the VectorStore migration.
The coordinator now always uses tfidf or text backends.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gobby.config.persistence import MemoryConfig
from gobby.memory.search.coordinator import SearchCoordinator
from gobby.storage.database import LocalDatabase
from gobby.storage.memories import LocalMemoryManager
from gobby.storage.migrations import run_migrations

pytestmark = pytest.mark.unit


TEST_MEMORIES = [
    ("User prefers dark mode for all applications", "preference"),
    ("The API uses REST endpoints at /api/v1", "fact"),
    ("Database migrations run on startup automatically", "fact"),
]


def create_coordinator(
    tmp_path: Path,
) -> tuple[SearchCoordinator, LocalMemoryManager]:
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
    config = MemoryConfig()
    coordinator = SearchCoordinator(storage=storage, config=config, db=db)
    return coordinator, storage


def add_test_memories(storage: LocalMemoryManager, project_id: str = "test-project") -> list[str]:
    """Add some test memories and return their IDs."""
    ids = []
    for content, mtype in TEST_MEMORIES:
        m = storage.create_memory(
            project_id=project_id,
            content=content,
            memory_type=mtype,
        )
        ids.append(m.id)
    return ids


# =============================================================================
# TF-IDF search tests
# =============================================================================


class TestTFIDFSearch:
    """Test that the default tfidf mode works correctly."""

    def test_tfidf_search_returns_results(self, tmp_path) -> None:
        """Coordinator should use TFIDFSearcher by default."""
        coordinator, storage = create_coordinator(tmp_path)
        add_test_memories(storage)

        # Search should work with TF-IDF
        results = coordinator.search("dark mode", project_id="test-project")
        assert len(results) >= 1
        assert any("dark mode" in m.content.lower() for m in results)

    def test_no_unified_searcher_by_default(self, tmp_path) -> None:
        """Coordinator should NOT create UnifiedSearcher by default."""
        coordinator, _ = create_coordinator(tmp_path)
        assert coordinator._unified_searcher is None

    def test_search_with_project_filter(self, tmp_path) -> None:
        """Search should filter by project_id."""
        coordinator, storage = create_coordinator(tmp_path)
        add_test_memories(storage, project_id="test-project")

        results = coordinator.search("dark mode", project_id="other-project")
        assert len(results) == 0

    def test_search_returns_relevant_results(self, tmp_path) -> None:
        """Search should rank relevant results higher."""
        coordinator, storage = create_coordinator(tmp_path)
        add_test_memories(storage)

        results = coordinator.search("REST API endpoints", project_id="test-project")
        assert len(results) >= 1
        assert any("REST" in m.content for m in results)


# =============================================================================
# Reindex
# =============================================================================


class TestReindex:
    """Test that reindex rebuilds the search index."""

    def test_reindex_succeeds(self, tmp_path) -> None:
        """Reindex should rebuild the index and report stats."""
        coordinator, storage = create_coordinator(tmp_path)
        add_test_memories(storage)

        stats = coordinator.reindex()
        assert stats["success"] is True
        assert stats["memory_count"] == 3
        assert stats["backend_type"] == "tfidf"

    def test_mark_refit_needed_triggers_refit(self, tmp_path) -> None:
        """After mark_refit_needed, next search should refit."""
        coordinator, storage = create_coordinator(tmp_path)
        add_test_memories(storage)

        coordinator.ensure_fitted()
        coordinator.mark_refit_needed()

        # Should refit on next search
        results = coordinator.search("dark mode", project_id="test-project")
        assert len(results) >= 1


# =============================================================================
# Tag filtering
# =============================================================================


class TestTagFiltering:
    """Test tag-based search filtering."""

    def test_tags_all_filter(self, tmp_path) -> None:
        """Search should support tags_all filtering."""
        coordinator, storage = create_coordinator(tmp_path)

        storage.create_memory(
            content="Python programming language",
            memory_type="fact",
            project_id="test-project",
            tags=["python", "programming"],
        )
        storage.create_memory(
            content="JavaScript programming language",
            memory_type="fact",
            project_id="test-project",
            tags=["javascript", "programming"],
        )

        results = coordinator.search(
            "programming",
            project_id="test-project",
            tags_all=["python", "programming"],
        )
        assert len(results) == 1
        assert "Python" in results[0].content

    def test_tags_none_filter(self, tmp_path) -> None:
        """Search should support tags_none exclusion."""
        coordinator, storage = create_coordinator(tmp_path)

        storage.create_memory(
            content="Python programming language",
            memory_type="fact",
            project_id="test-project",
            tags=["python", "programming"],
        )
        storage.create_memory(
            content="JavaScript programming language",
            memory_type="fact",
            project_id="test-project",
            tags=["javascript", "programming"],
        )

        results = coordinator.search(
            "programming",
            project_id="test-project",
            tags_none=["python"],
        )
        assert len(results) == 1
        assert "JavaScript" in results[0].content
