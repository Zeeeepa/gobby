"""
Memory search backend abstraction.

Provides pluggable search backends for memory recall:
- TF-IDF (default) - Zero-dependency local search using sklearn
- Text - Simple substring matching fallback

This module re-exports the shared search components from gobby.search
and adds memory-specific TextSearcher backend.

Usage:
    from gobby.memory.search import SearchBackend, get_search_backend

    backend = get_search_backend("tfidf")
    backend.fit([(id, content) for id, content in memories])
    results = backend.search("query text", top_k=10)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

# Re-export shared search components for backwards compatibility
from gobby.search import SearchBackend, SearchResult, TFIDFSearcher

if TYPE_CHECKING:
    from gobby.storage.database import DatabaseProtocol

__all__ = [
    "SearchBackend",
    "SearchResult",
    "TFIDFSearcher",
    "SearchCoordinator",
    "get_search_backend",
]


# Lazy import for SearchCoordinator to avoid circular imports
def __getattr__(name: str) -> Any:
    if name == "SearchCoordinator":
        from gobby.memory.search.coordinator import SearchCoordinator

        return SearchCoordinator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def get_search_backend(
    backend_type: str,
    db: DatabaseProtocol | None = None,
    **kwargs: Any,
) -> SearchBackend:
    """
    Factory function for search backends.

    Args:
        backend_type: Type of backend - "tfidf" or "text"
        db: Database connection (unused, kept for backwards compatibility)
        **kwargs: Backend-specific configuration

    Returns:
        SearchBackend instance

    Raises:
        ValueError: If backend_type is unknown
        ImportError: If required dependencies are not installed
    """
    if backend_type == "tfidf":
        return cast(SearchBackend, TFIDFSearcher(**kwargs))

    elif backend_type == "text":
        from gobby.memory.search.text import TextSearcher

        return cast(SearchBackend, TextSearcher(**kwargs))

    else:
        raise ValueError(f"Unknown search backend: {backend_type}. Valid options: tfidf, text")
