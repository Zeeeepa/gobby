"""
Memory search backend abstraction.

Provides pluggable search backends for memory recall:
- TF-IDF (default) - Zero-dependency local search using sklearn
- OpenAI - Embedding-based semantic search via OpenAI API
- Hybrid - Combines TF-IDF and OpenAI with RRF ranking

Usage:
    from gobby.memory.search import SearchBackend, get_search_backend

    backend = get_search_backend("tfidf")
    backend.fit([(id, content) for id, content in memories])
    results = backend.search("query text", top_k=10)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, cast, runtime_checkable

if TYPE_CHECKING:
    from gobby.storage.database import DatabaseProtocol

__all__ = [
    "SearchBackend",
    "SearchResult",
    "get_search_backend",
]


class SearchResult:
    """Result from a search query with memory ID and similarity score."""

    __slots__ = ("memory_id", "similarity")

    def __init__(self, memory_id: str, similarity: float):
        self.memory_id = memory_id
        self.similarity = similarity

    def __repr__(self) -> str:
        return f"SearchResult(memory_id={self.memory_id!r}, similarity={self.similarity:.4f})"

    def to_tuple(self) -> tuple[str, float]:
        """Convert to (memory_id, similarity) tuple for backwards compatibility."""
        return (self.memory_id, self.similarity)


@runtime_checkable
class SearchBackend(Protocol):
    """
    Protocol for pluggable memory search backends.

    Backends must implement:
    - fit(): Build/rebuild the search index from memory contents
    - search(): Find relevant memories for a query
    - needs_refit(): Check if index needs rebuilding

    The protocol uses structural typing, so any class with these methods
    will satisfy the protocol without inheritance.
    """

    def fit(self, memories: list[tuple[str, str]]) -> None:
        """
        Build or rebuild the search index.

        Args:
            memories: List of (memory_id, content) tuples to index

        This should be called:
        - On startup to build initial index
        - After bulk memory operations
        - When needs_refit() returns True
        """
        ...

    def search(self, query: str, top_k: int = 10) -> list[tuple[str, float]]:
        """
        Search for memories matching the query.

        Args:
            query: Search query text
            top_k: Maximum number of results to return

        Returns:
            List of (memory_id, similarity_score) tuples, sorted by
            relevance (highest similarity first). Similarity scores
            are typically in range [0, 1] but may vary by backend.
        """
        ...

    def needs_refit(self) -> bool:
        """
        Check if the search index needs rebuilding.

        Returns:
            True if fit() should be called before search()
        """
        ...


def get_search_backend(
    backend_type: str,
    db: DatabaseProtocol | None = None,
    **kwargs: Any,
) -> SearchBackend:
    """
    Factory function for search backends.

    Args:
        backend_type: Type of backend - "tfidf", "openai", "hybrid", or "text"
        db: Database connection (required for openai backend)
        **kwargs: Backend-specific configuration

    Returns:
        SearchBackend instance

    Raises:
        ValueError: If backend_type is unknown
        ImportError: If required dependencies are not installed
    """
    if backend_type == "tfidf":
        from gobby.memory.search.tfidf import TFIDFSearcher

        return cast(SearchBackend, TFIDFSearcher(**kwargs))

    elif backend_type == "openai":
        from gobby.memory.search.openai_adapter import OpenAISearchAdapter

        if db is None:
            raise ValueError("OpenAI search backend requires database connection")
        return cast(SearchBackend, OpenAISearchAdapter(db=db, **kwargs))

    elif backend_type == "hybrid":
        from gobby.memory.search.hybrid import HybridSearcher

        if db is None:
            raise ValueError("Hybrid search backend requires database connection")
        return cast(SearchBackend, HybridSearcher(db=db, **kwargs))

    elif backend_type == "text":
        from gobby.memory.search.text import TextSearcher

        return cast(SearchBackend, TextSearcher(**kwargs))

    else:
        raise ValueError(
            f"Unknown search backend: {backend_type}. "
            "Valid options: tfidf, openai, hybrid, text"
        )
