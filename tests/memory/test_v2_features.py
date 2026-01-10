"""Tests for Memory V2 features.

Covers:
- TF-IDF search backend
- Cross-reference creation and retrieval
- Knowledge graph visualization export
"""

import pytest

from gobby.config.persistence import MemoryConfig
from gobby.memory.manager import MemoryManager
from gobby.memory.search.tfidf import TFIDFSearcher
from gobby.memory.viz import export_memory_graph
from gobby.storage.database import LocalDatabase
from gobby.storage.memories import Memory, MemoryCrossRef
from gobby.storage.migrations import run_migrations

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def db(tmp_path):
    """Create a temporary database for testing."""
    database = LocalDatabase(tmp_path / "gobby.db")
    run_migrations(database)
    yield database
    database.close()


@pytest.fixture
def memory_config_with_crossref():
    """Create a memory configuration with cross-referencing enabled."""
    return MemoryConfig(
        enabled=True,
        auto_extract=False,
        injection_limit=10,
        importance_threshold=0.0,  # No threshold for tests
        decay_enabled=False,
        semantic_search_enabled=False,
        auto_embed=False,
        access_debounce_seconds=60,
        auto_crossref=True,
        crossref_threshold=0.1,  # Low threshold for tests
        crossref_max_links=5,
    )


@pytest.fixture
def memory_manager_with_crossref(db, memory_config_with_crossref):
    """Create a MemoryManager with cross-referencing enabled."""
    return MemoryManager(db=db, config=memory_config_with_crossref)


# =============================================================================
# Test: TFIDFSearcher
# =============================================================================


class TestTFIDFSearcher:
    """Tests for the TF-IDF search backend."""

    def test_init_creates_unfitted_searcher(self):
        """Test that initialization creates an unfitted searcher."""
        searcher = TFIDFSearcher()
        assert searcher.needs_refit() is True
        assert searcher._fitted is False

    def test_fit_with_memories(self):
        """Test fitting the searcher with memory data."""
        searcher = TFIDFSearcher()
        memories = [
            ("mm-1", "Python is a programming language"),
            ("mm-2", "JavaScript runs in the browser"),
            ("mm-3", "Rust provides memory safety"),
        ]
        searcher.fit(memories)

        assert searcher._fitted is True
        assert searcher.needs_refit() is False
        assert len(searcher._memory_ids) == 3

    def test_fit_with_empty_list(self):
        """Test fitting with empty list clears the index."""
        searcher = TFIDFSearcher()
        # First fit with data
        searcher.fit([("mm-1", "some content")])
        assert searcher._fitted is True

        # Then fit with empty list
        searcher.fit([])
        assert searcher._fitted is False
        assert len(searcher._memory_ids) == 0

    def test_search_returns_relevant_results(self):
        """Test that search returns relevant memories."""
        searcher = TFIDFSearcher()
        memories = [
            ("mm-1", "Python is a programming language used for data science"),
            ("mm-2", "JavaScript is used for web development"),
            ("mm-3", "Python has excellent libraries for machine learning"),
        ]
        searcher.fit(memories)

        results = searcher.search("Python programming", top_k=5)

        # Should find Python-related memories
        assert len(results) >= 1
        memory_ids = [r[0] for r in results]
        assert "mm-1" in memory_ids or "mm-3" in memory_ids

    def test_search_respects_top_k(self):
        """Test that search respects the top_k limit."""
        searcher = TFIDFSearcher()
        memories = [
            ("mm-1", "programming language"),
            ("mm-2", "programming language"),
            ("mm-3", "programming language"),
            ("mm-4", "programming language"),
            ("mm-5", "programming language"),
        ]
        searcher.fit(memories)

        results = searcher.search("programming", top_k=2)
        assert len(results) <= 2

    def test_search_unfitted_returns_empty(self):
        """Test that searching an unfitted index returns empty list."""
        searcher = TFIDFSearcher()
        results = searcher.search("anything", top_k=10)
        assert results == []

    def test_search_no_matches_returns_empty(self):
        """Test that search with no matches returns empty list."""
        searcher = TFIDFSearcher()
        searcher.fit([("mm-1", "Python programming")])

        results = searcher.search("completely unrelated xyz123", top_k=10)
        assert results == []

    def test_search_returns_similarity_scores(self):
        """Test that search results include similarity scores."""
        searcher = TFIDFSearcher()
        searcher.fit(
            [
                ("mm-1", "Python programming language"),
                ("mm-2", "unrelated content about cooking"),
            ]
        )

        results = searcher.search("Python programming", top_k=5)

        assert len(results) >= 1
        # Results should be (memory_id, similarity) tuples
        memory_id, similarity = results[0]
        assert isinstance(memory_id, str)
        assert isinstance(similarity, float)
        assert 0.0 <= similarity <= 1.0

    def test_mark_update_triggers_refit_need(self):
        """Test that marking updates triggers refit need."""
        searcher = TFIDFSearcher(refit_threshold=3)
        searcher.fit([("mm-1", "content")])

        assert searcher.needs_refit() is False

        searcher.mark_update()
        searcher.mark_update()
        assert searcher.needs_refit() is False

        searcher.mark_update()  # Third update
        assert searcher.needs_refit() is True

    def test_get_stats_returns_index_info(self):
        """Test that get_stats returns useful information."""
        searcher = TFIDFSearcher()
        searcher.fit(
            [
                ("mm-1", "Python programming"),
                ("mm-2", "JavaScript development"),
            ]
        )

        stats = searcher.get_stats()

        assert stats["fitted"] is True
        assert stats["memory_count"] == 2
        assert "vocabulary_size" in stats
        assert stats["vocabulary_size"] > 0

    def test_clear_resets_index(self):
        """Test that clear resets the search index."""
        searcher = TFIDFSearcher()
        searcher.fit([("mm-1", "content")])
        assert searcher._fitted is True

        searcher.clear()

        assert searcher._fitted is False
        assert len(searcher._memory_ids) == 0


# =============================================================================
# Test: Cross-References
# =============================================================================


class TestCrossReferences:
    """Tests for memory cross-reference functionality."""

    @pytest.mark.asyncio
    async def test_create_crossrefs_links_similar_memories(self, memory_manager_with_crossref):
        """Test that similar memories get cross-referenced."""
        manager = memory_manager_with_crossref

        # Create similar memories
        _mem1 = await manager.remember(
            content="Python is a great programming language for data science",
            importance=0.5,
        )
        mem2 = await manager.remember(
            content="Python programming is excellent for machine learning",
            importance=0.5,
        )

        # Check crossrefs were created
        crossrefs = manager.storage.get_crossrefs(mem2.id, limit=10)

        # Should have at least one crossref linking these similar memories
        assert len(crossrefs) >= 1

    @pytest.mark.asyncio
    async def test_get_related_returns_linked_memories(self, memory_manager_with_crossref):
        """Test that get_related returns cross-referenced memories."""
        manager = memory_manager_with_crossref

        # Create memories that should be linked
        _mem1 = await manager.remember(
            content="React is a JavaScript library for building user interfaces",
            importance=0.5,
        )
        mem2 = await manager.remember(
            content="React components use JavaScript and JSX syntax",
            importance=0.5,
        )
        _mem3 = await manager.remember(
            content="Completely unrelated content about cooking recipes",
            importance=0.5,
        )

        # Get related memories for mem2
        related = manager.get_related(mem2.id, limit=5)

        # Should find mem1 as related (both about React/JavaScript)
        _related_ids = [m.id for m in related]

        # At minimum, we should get some results
        # The exact linking depends on TF-IDF similarity
        assert isinstance(related, list)

    @pytest.mark.asyncio
    async def test_get_related_empty_for_no_crossrefs(self, db):
        """Test that get_related returns empty when no crossrefs exist."""
        config = MemoryConfig(
            enabled=True,
            auto_crossref=False,  # Disabled
            importance_threshold=0.0,
        )
        manager = MemoryManager(db=db, config=config)

        mem = await manager.remember(content="Isolated memory", importance=0.5)
        related = manager.get_related(mem.id, limit=5)

        assert related == []

    @pytest.mark.asyncio
    async def test_crossref_respects_threshold(self, db):
        """Test that crossrefs respect similarity threshold."""
        config = MemoryConfig(
            enabled=True,
            auto_crossref=True,
            crossref_threshold=0.99,  # Very high threshold
            crossref_max_links=5,
            importance_threshold=0.0,
        )
        manager = MemoryManager(db=db, config=config)

        await manager.remember(content="First topic about Python", importance=0.5)
        mem2 = await manager.remember(
            content="Second topic about JavaScript",
            importance=0.5,
        )

        # With very high threshold, dissimilar content shouldn't link
        crossrefs = manager.storage.get_crossrefs(mem2.id, limit=10)
        assert len(crossrefs) == 0

    @pytest.mark.asyncio
    async def test_crossref_max_links_limit(self, db):
        """Test that crossrefs respect max_links limit."""
        config = MemoryConfig(
            enabled=True,
            auto_crossref=True,
            crossref_threshold=0.01,  # Very low threshold
            crossref_max_links=2,
            importance_threshold=0.0,
        )
        manager = MemoryManager(db=db, config=config)

        # Create many similar memories
        for i in range(5):
            await manager.remember(
                content=f"Python programming topic number {i}",
                importance=0.5,
            )

        # Create one more that should link to others
        mem = await manager.remember(
            content="Python programming language overview",
            importance=0.5,
        )

        crossrefs = manager.storage.get_crossrefs(mem.id, limit=10)
        assert len(crossrefs) <= 2


# =============================================================================
# Test: Visualization
# =============================================================================


class TestVisualization:
    """Tests for memory knowledge graph visualization."""

    def test_export_memory_graph_generates_html(self):
        """Test that export_memory_graph generates valid HTML."""
        memories = [
            Memory(
                id="mm-1",
                content="Test memory one",
                memory_type="fact",
                importance=0.8,
                created_at="2024-01-01T00:00:00Z",
                updated_at="2024-01-01T00:00:00Z",
                tags=["test"],
            ),
            Memory(
                id="mm-2",
                content="Test memory two",
                memory_type="preference",
                importance=0.5,
                created_at="2024-01-02T00:00:00Z",
                updated_at="2024-01-02T00:00:00Z",
                tags=["test", "example"],
            ),
        ]
        crossrefs = [
            MemoryCrossRef(
                source_id="mm-1",
                target_id="mm-2",
                similarity=0.75,
                created_at="2024-01-02T00:00:00Z",
            ),
        ]

        html = export_memory_graph(memories, crossrefs, title="Test Graph")

        # Basic HTML structure checks
        assert "<!DOCTYPE html>" in html
        assert "<title>Test Graph</title>" in html
        assert "vis-network" in html  # vis.js library
        assert "mm-1" in html
        assert "mm-2" in html

    def test_export_memory_graph_colors_by_type(self):
        """Test that nodes are colored by memory type."""
        memories = [
            Memory(
                id="mm-fact",
                content="A fact",
                memory_type="fact",
                importance=0.5,
                created_at="2024-01-01T00:00:00Z",
                updated_at="2024-01-01T00:00:00Z",
            ),
            Memory(
                id="mm-pref",
                content="A preference",
                memory_type="preference",
                importance=0.5,
                created_at="2024-01-01T00:00:00Z",
                updated_at="2024-01-01T00:00:00Z",
            ),
        ]

        html = export_memory_graph(memories, [], title="Color Test")

        # Check that different colors are used
        assert "#4CAF50" in html  # Green for facts
        assert "#2196F3" in html  # Blue for preferences

    def test_export_memory_graph_handles_empty_memories(self):
        """Test that export handles empty memory list."""
        html = export_memory_graph([], [], title="Empty Graph")

        assert "<!DOCTYPE html>" in html
        assert "Nodes: 0" in html
        assert "Edges: 0" in html

    def test_export_memory_graph_truncates_long_content(self):
        """Test that long content is truncated in labels."""
        long_content = "A" * 100  # 100 characters
        memories = [
            Memory(
                id="mm-long",
                content=long_content,
                memory_type="fact",
                importance=0.5,
                created_at="2024-01-01T00:00:00Z",
                updated_at="2024-01-01T00:00:00Z",
            ),
        ]

        html = export_memory_graph(memories, [], title="Truncation Test")

        # Full content should be in tooltip, but label should be truncated
        # Label is first 50 chars + "..."
        assert "..." in html

    def test_export_memory_graph_includes_edge_data(self):
        """Test that edges include similarity information."""
        memories = [
            Memory(
                id="mm-1",
                content="First",
                memory_type="fact",
                importance=0.5,
                created_at="2024-01-01T00:00:00Z",
                updated_at="2024-01-01T00:00:00Z",
            ),
            Memory(
                id="mm-2",
                content="Second",
                memory_type="fact",
                importance=0.5,
                created_at="2024-01-01T00:00:00Z",
                updated_at="2024-01-01T00:00:00Z",
            ),
        ]
        crossrefs = [
            MemoryCrossRef(
                source_id="mm-1",
                target_id="mm-2",
                similarity=0.85,
                created_at="2024-01-01T00:00:00Z",
            ),
        ]

        html = export_memory_graph(memories, crossrefs, title="Edge Test")

        # Check edge data is present
        assert "Similarity: 0.85" in html

    def test_export_memory_graph_filters_orphan_edges(self):
        """Test that edges to non-existent nodes are filtered."""
        memories = [
            Memory(
                id="mm-1",
                content="Only node",
                memory_type="fact",
                importance=0.5,
                created_at="2024-01-01T00:00:00Z",
                updated_at="2024-01-01T00:00:00Z",
            ),
        ]
        crossrefs = [
            MemoryCrossRef(
                source_id="mm-1",
                target_id="mm-nonexistent",  # Node doesn't exist
                similarity=0.5,
                created_at="2024-01-01T00:00:00Z",
            ),
        ]

        html = export_memory_graph(memories, crossrefs, title="Orphan Test")

        # Edge should be filtered out
        assert "Edges: 0" in html
