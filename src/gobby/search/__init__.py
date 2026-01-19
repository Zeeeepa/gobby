"""
Shared search backend abstraction.

Provides pluggable search backends for semantic search:
- TF-IDF (default) - Zero-dependency local search using sklearn

Usage:
    from gobby.search import SearchBackend, get_search_backend, TFIDFSearcher

    backend = get_search_backend("tfidf")
    backend.fit([(id, content) for id, content in items])
    results = backend.search("query text", top_k=10)
"""

from gobby.search.protocol import SearchBackend, SearchResult, get_search_backend
from gobby.search.tfidf import TFIDFSearcher

__all__ = [
    "SearchBackend",
    "SearchResult",
    "TFIDFSearcher",
    "get_search_backend",
]
