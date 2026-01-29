"""Tests for the shared TF-IDF search backend."""

import pytest

from gobby.search import TFIDFSearcher, get_search_backend

pytestmark = pytest.mark.unit

class TestTFIDFSearcher:
    """Tests for TFIDFSearcher class."""

    def test_fit_and_search(self) -> None:
        """Test basic fit and search functionality."""
        searcher = TFIDFSearcher()

        items = [
            ("id1", "implement user authentication with JWT tokens"),
            ("id2", "fix database connection bug"),
            ("id3", "add user login page"),
            ("id4", "refactor authentication logic"),
        ]

        searcher.fit(items)

        # Search for authentication-related items
        results = searcher.search("authentication", top_k=10)

        assert len(results) > 0
        # id1 and id4 should be top results
        result_ids = [r[0] for r in results]
        assert "id1" in result_ids or "id4" in result_ids

    def test_empty_fit(self) -> None:
        """Test fitting with empty items list."""
        searcher = TFIDFSearcher()
        searcher.fit([])

        assert not searcher._fitted
        assert searcher.search("anything") == []

    def test_search_unfitted(self) -> None:
        """Test searching without fitting returns empty results."""
        searcher = TFIDFSearcher()
        results = searcher.search("test query")
        assert results == []

    def test_needs_refit(self) -> None:
        """Test needs_refit flag behavior."""
        searcher = TFIDFSearcher()

        # Initially needs refit
        assert searcher.needs_refit()

        # After fitting, doesn't need refit
        searcher.fit([("id1", "content")])
        assert not searcher.needs_refit()

    def test_mark_update(self) -> None:
        """Test that mark_update increments pending updates."""
        searcher = TFIDFSearcher(refit_threshold=3)
        searcher.fit([("id1", "content")])

        assert not searcher.needs_refit()

        searcher.mark_update()
        searcher.mark_update()
        assert not searcher.needs_refit()

        # Third update triggers refit threshold
        searcher.mark_update()
        assert searcher.needs_refit()

    def test_search_returns_scores_in_range(self) -> None:
        """Test that similarity scores are in range [0, 1]."""
        searcher = TFIDFSearcher()
        items = [
            ("id1", "python programming language"),
            ("id2", "java programming language"),
        ]
        searcher.fit(items)

        results = searcher.search("python")
        for _, score in results:
            assert 0.0 <= score <= 1.0

    def test_search_with_no_matches(self) -> None:
        """Test search returns empty when no matches found."""
        searcher = TFIDFSearcher()
        items = [
            ("id1", "apple banana cherry"),
            ("id2", "dog cat elephant"),
        ]
        searcher.fit(items)

        # Search for something completely unrelated
        results = searcher.search("xyzabc123")
        assert results == []

    def test_top_k_limits_results(self) -> None:
        """Test that top_k parameter limits results."""
        searcher = TFIDFSearcher()
        items = [
            ("id1", "test content one"),
            ("id2", "test content two"),
            ("id3", "test content three"),
            ("id4", "test content four"),
            ("id5", "test content five"),
        ]
        searcher.fit(items)

        results = searcher.search("test", top_k=2)
        assert len(results) <= 2

    def test_get_stats(self) -> None:
        """Test get_stats returns expected keys."""
        searcher = TFIDFSearcher()
        searcher.fit([("id1", "test content")])

        stats = searcher.get_stats()

        assert "fitted" in stats
        assert stats["fitted"] is True
        assert "item_count" in stats
        assert stats["item_count"] == 1
        assert "pending_updates" in stats
        assert "vocabulary_size" in stats

    def test_clear(self) -> None:
        """Test clear resets the searcher."""
        searcher = TFIDFSearcher()
        searcher.fit([("id1", "content")])

        searcher.clear()

        assert not searcher._fitted
        assert searcher._item_ids == []
        assert searcher.search("content") == []


class TestGetSearchBackend:
    """Tests for get_search_backend factory function."""

    def test_get_tfidf_backend(self) -> None:
        """Test creating TF-IDF backend."""
        backend = get_search_backend("tfidf")
        assert isinstance(backend, TFIDFSearcher)

    def test_get_unknown_backend_raises(self) -> None:
        """Test that unknown backend type raises ValueError."""
        with pytest.raises(ValueError, match="Unknown search backend"):
            get_search_backend("unknown")

    def test_tfidf_backend_with_kwargs(self) -> None:
        """Test creating TF-IDF backend with custom configuration."""
        backend = get_search_backend(
            "tfidf",
            ngram_range=(1, 3),
            max_features=5000,
        )
        assert isinstance(backend, TFIDFSearcher)
        assert backend._ngram_range == (1, 3)
        assert backend._max_features == 5000
