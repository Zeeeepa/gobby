"""
Simple text-based search backend (fallback).

Provides basic substring matching when no other backend is available.
This is the fallback when sklearn is not installed.
"""

from __future__ import annotations


class TextSearcher:
    """
    Simple text-based search using substring matching.

    This is a fallback backend that works without any dependencies.
    It provides basic relevance scoring based on:
    - Exact phrase match (highest score)
    - Word overlap (proportional score)
    """

    def __init__(self) -> None:
        self._memories: dict[str, str] = {}  # id -> content
        self._fitted = False

    def fit(self, memories: list[tuple[str, str]]) -> None:
        """
        Build index from memories.

        Args:
            memories: List of (memory_id, content) tuples
        """
        self._memories = {mid: content.lower() for mid, content in memories}
        self._fitted = True

    def search(self, query: str, top_k: int = 10) -> list[tuple[str, float]]:
        """
        Search for memories containing query terms.

        Args:
            query: Search query text
            top_k: Maximum results to return

        Returns:
            List of (memory_id, similarity_score) tuples
        """
        if not self._fitted or not self._memories:
            return []

        query_lower = query.lower()
        query_words = set(query_lower.split())
        results: list[tuple[str, float]] = []

        for memory_id, content in self._memories.items():
            score = self._score_match(query_lower, query_words, content)
            if score > 0:
                results.append((memory_id, score))

        # Sort by score descending
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def _score_match(
        self,
        query: str,
        query_words: set[str],
        content: str,
    ) -> float:
        """
        Score a content match against query.

        Scoring:
        - Exact phrase match: 1.0
        - All words present: 0.8
        - Partial word match: proportion of words found * 0.6
        """
        # Exact phrase match
        if query in content:
            return 1.0

        # Word-based matching
        content_words = set(content.split())
        matching_words = query_words & content_words

        if not matching_words:
            return 0.0

        # All words present
        if matching_words == query_words:
            return 0.8

        # Partial match - proportion of query words found
        match_ratio = len(matching_words) / len(query_words)
        return match_ratio * 0.6

    def needs_refit(self) -> bool:
        """Check if index needs rebuilding."""
        return not self._fitted

    def add_memory(self, memory_id: str, content: str) -> None:
        """
        Add a single memory to the index (incremental update).

        Args:
            memory_id: Memory ID
            content: Memory content
        """
        self._memories[memory_id] = content.lower()

    def remove_memory(self, memory_id: str) -> bool:
        """
        Remove a memory from the index.

        Args:
            memory_id: Memory ID to remove

        Returns:
            True if memory was removed, False if not found
        """
        if memory_id in self._memories:
            del self._memories[memory_id]
            return True
        return False

    def clear(self) -> None:
        """Clear the search index."""
        self._memories.clear()
        self._fitted = False
