"""Search backend abstractions.

This module provides the protocol and implementations for search backends
used by UnifiedSearcher:

- AsyncSearchBackend: Protocol for async search backends
- TFIDFBackend: TF-IDF based search (always available)
- EmbeddingBackend: Embedding-based search (requires API)

Usage:
    from gobby.search.backends import AsyncSearchBackend, TFIDFBackend

    backend: AsyncSearchBackend = TFIDFBackend()
    await backend.fit_async([("id1", "content1"), ("id2", "content2")])
    results = await backend.search_async("query", top_k=10)
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

# Re-export sync TFIDFSearcher for backwards compatibility
from gobby.search.tfidf import TFIDFSearcher

__all__ = [
    "AsyncSearchBackend",
    "TFIDFBackend",
    "EmbeddingBackend",
    "TFIDFSearcher",
]


@runtime_checkable
class AsyncSearchBackend(Protocol):
    """Protocol for async search backends.

    All search backends must implement this interface. The protocol
    uses async methods to support embedding-based backends that need
    to call external APIs.

    Methods:
        fit_async: Build/rebuild the search index
        search_async: Find relevant items for a query
        needs_refit: Check if index needs rebuilding
        get_stats: Get backend statistics
        clear: Clear the search index
    """

    async def fit_async(self, items: list[tuple[str, str]]) -> None:
        """Build or rebuild the search index.

        Args:
            items: List of (item_id, content) tuples to index
        """
        ...

    async def search_async(
        self,
        query: str,
        top_k: int = 10,
    ) -> list[tuple[str, float]]:
        """Search for items matching the query.

        Args:
            query: Search query text
            top_k: Maximum number of results to return

        Returns:
            List of (item_id, similarity_score) tuples, sorted by
            relevance (highest similarity first).
        """
        ...

    def needs_refit(self) -> bool:
        """Check if the search index needs rebuilding.

        Returns:
            True if fit_async() should be called before search_async()
        """
        ...

    def get_stats(self) -> dict[str, Any]:
        """Get statistics about the search index.

        Returns:
            Dict with backend-specific statistics
        """
        ...

    def clear(self) -> None:
        """Clear the search index."""
        ...


class TFIDFBackend:
    """Async wrapper around TFIDFSearcher.

    Provides the AsyncSearchBackend interface for TF-IDF search.
    This is a thin wrapper that delegates to the sync TFIDFSearcher.
    """

    def __init__(
        self,
        ngram_range: tuple[int, int] = (1, 2),
        max_features: int = 10000,
        min_df: int = 1,
        stop_words: str | None = "english",
        refit_threshold: int = 10,
    ):
        """Initialize TF-IDF backend.

        Args:
            ngram_range: Min/max n-gram sizes for tokenization
            max_features: Maximum vocabulary size
            min_df: Minimum document frequency for inclusion
            stop_words: Language for stop words (None to disable)
            refit_threshold: Number of updates before automatic refit
        """
        self._searcher = TFIDFSearcher(
            ngram_range=ngram_range,
            max_features=max_features,
            min_df=min_df,
            stop_words=stop_words,
            refit_threshold=refit_threshold,
        )

    async def fit_async(self, items: list[tuple[str, str]]) -> None:
        """Build or rebuild the search index."""
        self._searcher.fit(items)

    async def search_async(
        self,
        query: str,
        top_k: int = 10,
    ) -> list[tuple[str, float]]:
        """Search for items matching the query."""
        return self._searcher.search(query, top_k)

    def needs_refit(self) -> bool:
        """Check if the search index needs rebuilding."""
        return self._searcher.needs_refit()

    def get_stats(self) -> dict[str, Any]:
        """Get statistics about the search index."""
        stats = self._searcher.get_stats()
        stats["backend_type"] = "tfidf"
        return stats

    def clear(self) -> None:
        """Clear the search index."""
        self._searcher.clear()

    def mark_update(self) -> None:
        """Mark that an item update occurred."""
        self._searcher.mark_update()


# Import EmbeddingBackend - needs to be at end to avoid circular imports
from gobby.search.backends.embedding import EmbeddingBackend  # noqa: E402
