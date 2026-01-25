"""Tests for the unified search module."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from gobby.search import (
    EmbeddingBackend,
    FallbackEvent,
    SearchConfig,
    SearchMode,
    TFIDFBackend,
    UnifiedSearcher,
)


class TestSearchConfig:
    """Tests for SearchConfig."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = SearchConfig()

        assert config.mode == "auto"
        assert config.embedding_model == "text-embedding-3-small"
        assert config.embedding_api_base is None
        assert config.embedding_api_key is None
        assert config.tfidf_weight == 0.4
        assert config.embedding_weight == 0.6
        assert config.notify_on_fallback is True

    def test_custom_config(self) -> None:
        """Test custom configuration values."""
        config = SearchConfig(
            mode="hybrid",
            embedding_model="openai/nomic-embed-text",
            embedding_api_base="http://localhost:11434/v1",
            tfidf_weight=0.5,
            embedding_weight=0.5,
        )

        assert config.mode == "hybrid"
        assert config.embedding_model == "openai/nomic-embed-text"
        assert config.embedding_api_base == "http://localhost:11434/v1"

    def test_get_mode_enum(self) -> None:
        """Test get_mode_enum returns correct SearchMode."""
        config = SearchConfig(mode="auto")
        assert config.get_mode_enum() == SearchMode.AUTO

        config = SearchConfig(mode="tfidf")
        assert config.get_mode_enum() == SearchMode.TFIDF

        config = SearchConfig(mode="embedding")
        assert config.get_mode_enum() == SearchMode.EMBEDDING

        config = SearchConfig(mode="hybrid")
        assert config.get_mode_enum() == SearchMode.HYBRID

    def test_get_normalized_weights(self) -> None:
        """Test weight normalization."""
        config = SearchConfig(tfidf_weight=0.4, embedding_weight=0.6)
        tfidf, embedding = config.get_normalized_weights()
        assert tfidf == 0.4
        assert embedding == 0.6

        # Test non-standard weights
        config = SearchConfig(tfidf_weight=1.0, embedding_weight=1.0)
        tfidf, embedding = config.get_normalized_weights()
        assert tfidf == 0.5
        assert embedding == 0.5

        # Test zero weights fallback
        config = SearchConfig(tfidf_weight=0.0, embedding_weight=0.0)
        tfidf, embedding = config.get_normalized_weights()
        assert tfidf == 0.5
        assert embedding == 0.5


class TestSearchMode:
    """Tests for SearchMode enum."""

    def test_enum_values(self) -> None:
        """Test SearchMode enum values."""
        assert SearchMode.TFIDF.value == "tfidf"
        assert SearchMode.EMBEDDING.value == "embedding"
        assert SearchMode.AUTO.value == "auto"
        assert SearchMode.HYBRID.value == "hybrid"

    def test_string_equality(self) -> None:
        """Test SearchMode string comparison."""
        assert SearchMode.TFIDF == "tfidf"
        assert SearchMode.AUTO == "auto"


class TestFallbackEvent:
    """Tests for FallbackEvent dataclass."""

    def test_basic_event(self) -> None:
        """Test basic fallback event creation."""
        event = FallbackEvent(reason="API key not configured")

        assert event.reason == "API key not configured"
        assert event.original_error is None
        assert event.mode == "auto"
        assert event.items_reindexed == 0

    def test_event_with_error(self) -> None:
        """Test fallback event with error."""
        error = RuntimeError("Connection failed")
        event = FallbackEvent(
            reason="Embedding failed",
            original_error=error,
            mode="auto",
            items_reindexed=10,
        )

        assert event.reason == "Embedding failed"
        assert event.original_error is error
        assert event.items_reindexed == 10

    def test_to_dict(self) -> None:
        """Test to_dict serialization."""
        event = FallbackEvent(reason="Test reason", mode="hybrid")
        data = event.to_dict()

        assert data["reason"] == "Test reason"
        assert data["mode"] == "hybrid"
        assert "timestamp" in data

    def test_str_representation(self) -> None:
        """Test string representation."""
        event = FallbackEvent(reason="Test")
        assert "FallbackEvent: Test" in str(event)

        error = ValueError("bad value")
        event = FallbackEvent(reason="With error", original_error=error)
        assert "FallbackEvent: With error" in str(event)
        assert "bad value" in str(event)


class TestTFIDFBackend:
    """Tests for TFIDFBackend async wrapper."""

    @pytest.mark.asyncio
    async def test_fit_and_search(self) -> None:
        """Test basic fit and search."""
        backend = TFIDFBackend()

        items = [
            ("id1", "python programming language"),
            ("id2", "javascript web development"),
            ("id3", "python data science"),
        ]

        await backend.fit_async(items)
        results = await backend.search_async("python", top_k=5)

        assert len(results) > 0
        result_ids = [r[0] for r in results]
        assert "id1" in result_ids or "id3" in result_ids

    @pytest.mark.asyncio
    async def test_empty_fit(self) -> None:
        """Test fitting with empty items."""
        backend = TFIDFBackend()
        await backend.fit_async([])

        results = await backend.search_async("anything")
        assert results == []

    def test_get_stats(self) -> None:
        """Test get_stats includes backend_type."""
        backend = TFIDFBackend()
        stats = backend.get_stats()

        assert stats["backend_type"] == "tfidf"
        assert "fitted" in stats


class TestUnifiedSearcher:
    """Tests for UnifiedSearcher."""

    @pytest.mark.asyncio
    async def test_tfidf_mode(self) -> None:
        """Test TF-IDF only mode."""
        config = SearchConfig(mode="tfidf")
        searcher = UnifiedSearcher(config)

        items = [
            ("id1", "hello world"),
            ("id2", "foo bar baz"),
        ]

        await searcher.fit_async(items)
        results = await searcher.search_async("hello")

        assert len(results) > 0
        assert searcher.get_active_backend() == "tfidf"
        assert not searcher.is_using_fallback()

    @pytest.mark.asyncio
    async def test_auto_mode_no_api_key(self) -> None:
        """Test auto mode falls back when no API key."""
        config = SearchConfig(
            mode="auto",
            embedding_model="text-embedding-3-small",
            embedding_api_key=None,  # No key
        )

        # Mock is_embedding_available to return False
        with patch(
            "gobby.search.unified.is_embedding_available",
            return_value=False,
        ):
            fallback_events: list[FallbackEvent] = []
            searcher = UnifiedSearcher(
                config,
                event_callback=lambda e: fallback_events.append(e),
            )

            items = [("id1", "test content")]
            await searcher.fit_async(items)

            assert searcher.get_active_backend() == "tfidf"
            assert searcher.is_using_fallback()
            assert len(fallback_events) == 1
            assert "unavailable" in fallback_events[0].reason.lower()

    @pytest.mark.asyncio
    async def test_auto_mode_embedding_available(self) -> None:
        """Test auto mode uses embedding when available."""
        config = SearchConfig(mode="auto")

        # Mock embedding availability and generation
        mock_embeddings = [[0.1, 0.2, 0.3]] * 2

        with (
            patch("gobby.search.unified.is_embedding_available", return_value=True),
            patch(
                "gobby.search.embeddings.generate_embeddings",
                new_callable=AsyncMock,
                return_value=mock_embeddings,
            ),
        ):
            searcher = UnifiedSearcher(config)
            items = [("id1", "hello"), ("id2", "world")]

            await searcher.fit_async(items)

            assert searcher.get_active_backend() == "embedding"
            assert not searcher.is_using_fallback()

    @pytest.mark.asyncio
    async def test_auto_mode_embedding_fails_at_runtime(self) -> None:
        """Test auto mode falls back when embedding fails at runtime."""
        config = SearchConfig(mode="auto")

        with (
            patch("gobby.search.unified.is_embedding_available", return_value=True),
            patch(
                "gobby.search.embeddings.generate_embeddings",
                new_callable=AsyncMock,
                side_effect=RuntimeError("API error"),
            ),
        ):
            fallback_events: list[FallbackEvent] = []
            searcher = UnifiedSearcher(
                config,
                event_callback=lambda e: fallback_events.append(e),
            )

            items = [("id1", "test")]
            await searcher.fit_async(items)

            assert searcher.is_using_fallback()
            assert len(fallback_events) == 1

    @pytest.mark.asyncio
    async def test_embedding_mode_fails_without_key(self) -> None:
        """Test embedding mode raises when unavailable."""
        config = SearchConfig(mode="embedding")

        with patch("gobby.search.unified.is_embedding_available", return_value=False):
            searcher = UnifiedSearcher(config)

            with pytest.raises(RuntimeError, match="Embedding unavailable"):
                await searcher.fit_async([("id1", "test")])

    @pytest.mark.asyncio
    async def test_hybrid_mode(self) -> None:
        """Test hybrid mode combines both backends."""
        config = SearchConfig(
            mode="hybrid",
            tfidf_weight=0.5,
            embedding_weight=0.5,
        )

        mock_embeddings = [[0.1, 0.2, 0.3]] * 2
        mock_query_embedding = [0.1, 0.2, 0.3]

        with (
            patch("gobby.search.unified.is_embedding_available", return_value=True),
            patch(
                "gobby.search.embeddings.generate_embeddings",
                new_callable=AsyncMock,
                return_value=mock_embeddings,
            ),
            patch(
                "gobby.search.embeddings.generate_embedding",
                new_callable=AsyncMock,
                return_value=mock_query_embedding,
            ),
        ):
            searcher = UnifiedSearcher(config)
            items = [("id1", "hello world"), ("id2", "goodbye world")]

            await searcher.fit_async(items)
            results = await searcher.search_async("hello")

            assert searcher.get_active_backend() == "hybrid"
            # Results should exist (combined from both backends)
            assert len(results) > 0

    @pytest.mark.asyncio
    async def test_get_stats(self) -> None:
        """Test get_stats returns comprehensive info."""
        config = SearchConfig(mode="tfidf")
        searcher = UnifiedSearcher(config)

        items = [("id1", "test content")]
        await searcher.fit_async(items)

        stats = searcher.get_stats()

        assert stats["mode"] == "tfidf"
        assert stats["fitted"] is True
        assert stats["active_backend"] == "tfidf"
        assert stats["using_fallback"] is False
        assert stats["item_count"] == 1

    @pytest.mark.asyncio
    async def test_clear(self) -> None:
        """Test clear resets all state."""
        config = SearchConfig(mode="tfidf")
        searcher = UnifiedSearcher(config)

        await searcher.fit_async([("id1", "test")])
        searcher.clear()

        assert not searcher._fitted
        assert searcher.get_active_backend() == "none"
        assert not searcher.is_using_fallback()

    @pytest.mark.asyncio
    async def test_needs_refit(self) -> None:
        """Test needs_refit tracking."""
        config = SearchConfig(mode="tfidf")
        searcher = UnifiedSearcher(config)

        assert searcher.needs_refit()

        await searcher.fit_async([("id1", "test")])
        assert not searcher.needs_refit()

    @pytest.mark.asyncio
    async def test_mark_update(self) -> None:
        """Test mark_update triggers refit need."""
        config = SearchConfig(mode="tfidf")
        searcher = UnifiedSearcher(config)

        await searcher.fit_async([("id1", "test")])

        # After many updates, should need refit
        for _ in range(15):
            searcher.mark_update()

        assert searcher.needs_refit()

    @pytest.mark.asyncio
    async def test_search_unfitted_returns_empty(self) -> None:
        """Test search before fitting returns empty."""
        config = SearchConfig(mode="tfidf")
        searcher = UnifiedSearcher(config)

        results = await searcher.search_async("test")
        assert results == []

    @pytest.mark.asyncio
    async def test_fallback_event_callback(self) -> None:
        """Test fallback event callback is called."""
        config = SearchConfig(mode="auto", notify_on_fallback=True)

        events: list[FallbackEvent] = []

        def callback(event: FallbackEvent) -> None:
            events.append(event)

        with patch("gobby.search.unified.is_embedding_available", return_value=False):
            searcher = UnifiedSearcher(config, event_callback=callback)
            await searcher.fit_async([("id1", "test")])

        assert len(events) == 1
        assert events[0].mode == "auto"

    @pytest.mark.asyncio
    async def test_hybrid_partial_failure(self) -> None:
        """Test hybrid mode continues with TF-IDF when embedding fails."""
        config = SearchConfig(mode="hybrid")

        # Embedding available for check but fails during fit
        with (
            patch("gobby.search.unified.is_embedding_available", return_value=True),
            patch(
                "gobby.search.embeddings.generate_embeddings",
                new_callable=AsyncMock,
                side_effect=RuntimeError("API error"),
            ),
        ):
            searcher = UnifiedSearcher(config)
            await searcher.fit_async([("id1", "test")])

            # Should have fallen back to TF-IDF only
            assert searcher.get_active_backend() == "tfidf"

            # Search should still work via TF-IDF
            results = await searcher.search_async("test")
            assert len(results) > 0


class TestEmbeddingBackend:
    """Tests for EmbeddingBackend."""

    def test_from_config(self) -> None:
        """Test creating backend from config."""
        config = SearchConfig(
            embedding_model="openai/nomic-embed-text",
            embedding_api_base="http://localhost:11434/v1",
        )

        backend = EmbeddingBackend.from_config(config)

        assert backend._model == "openai/nomic-embed-text"
        assert backend._api_base == "http://localhost:11434/v1"

    @pytest.mark.asyncio
    async def test_fit_and_search(self) -> None:
        """Test fit and search with mocked embeddings."""
        backend = EmbeddingBackend()

        mock_fit_embeddings = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
        mock_query_embedding = [0.1, 0.2, 0.3]  # Similar to first item

        with (
            patch(
                "gobby.search.embeddings.generate_embeddings",
                new_callable=AsyncMock,
                return_value=mock_fit_embeddings,
            ),
            patch(
                "gobby.search.embeddings.generate_embedding",
                new_callable=AsyncMock,
                return_value=mock_query_embedding,
            ),
        ):
            items = [("id1", "hello"), ("id2", "world")]
            await backend.fit_async(items)

            results = await backend.search_async("greeting", top_k=5)

            assert len(results) == 2
            # id1 should have higher similarity (identical embedding)
            assert results[0][0] == "id1"

    @pytest.mark.asyncio
    async def test_empty_fit(self) -> None:
        """Test fitting with empty items."""
        backend = EmbeddingBackend()
        await backend.fit_async([])

        assert not backend._fitted
        results = await backend.search_async("test")
        assert results == []

    def test_get_stats(self) -> None:
        """Test get_stats returns expected keys."""
        backend = EmbeddingBackend(model="test-model")
        stats = backend.get_stats()

        assert stats["backend_type"] == "embedding"
        assert stats["model"] == "test-model"
        assert "fitted" in stats
        assert "item_count" in stats

    def test_clear(self) -> None:
        """Test clear resets state."""
        backend = EmbeddingBackend()
        backend._item_ids = ["id1", "id2"]
        backend._fitted = True

        backend.clear()

        assert backend._item_ids == []
        assert not backend._fitted
