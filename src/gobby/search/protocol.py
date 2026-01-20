"""Search backend protocol definition.

Defines the interface that all search backends must implement.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class SearchBackend(Protocol):
    """
    Protocol for pluggable search backends.

    Backends must implement:
    - fit(): Build/rebuild the search index from item contents
    - search(): Find relevant items for a query
    - needs_refit(): Check if index needs rebuilding

    The protocol uses structural typing, so any class with these methods
    will satisfy the protocol without inheritance.
    """

    def fit(self, items: list[tuple[str, str]]) -> None:
        """
        Build or rebuild the search index.

        Args:
            items: List of (item_id, content) tuples to index

        This should be called:
        - On startup to build initial index
        - After bulk item operations
        - When needs_refit() returns True
        """
        ...

    def search(self, query: str, top_k: int = 10) -> list[tuple[str, float]]:
        """
        Search for items matching the query.

        Args:
            query: Search query text
            top_k: Maximum number of results to return

        Returns:
            List of (item_id, similarity_score) tuples, sorted by
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


class SearchResult:
    """Result from a search query with item ID and similarity score."""

    __slots__ = ("item_id", "similarity")

    def __init__(self, item_id: str, similarity: float):
        self.item_id = item_id
        self.similarity = similarity

    def __repr__(self) -> str:
        return f"SearchResult(item_id={self.item_id!r}, similarity={self.similarity:.4f})"

    def to_tuple(self) -> tuple[str, float]:
        """Convert to (item_id, similarity) tuple for backwards compatibility."""
        return (self.item_id, self.similarity)


def get_search_backend(backend_type: str, **kwargs: Any) -> SearchBackend:
    """
    Factory function for search backends.

    Args:
        backend_type: Type of backend - currently only "tfidf" is supported
        **kwargs: Backend-specific configuration

    Returns:
        SearchBackend instance

    Raises:
        ValueError: If backend_type is not "tfidf"
        ImportError: If required dependencies are not installed
    """
    from typing import cast

    if backend_type == "tfidf":
        from gobby.search.tfidf import TFIDFSearcher

        return cast(SearchBackend, TFIDFSearcher(**kwargs))

    else:
        raise ValueError(f"Unknown search backend: {backend_type}. Valid options: tfidf")
