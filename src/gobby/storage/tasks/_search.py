"""Task search module using TF-IDF.

Provides semantic search capabilities for tasks using the shared TF-IDF backend.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from gobby.search import TFIDFSearcher

if TYPE_CHECKING:
    from gobby.storage.tasks._models import Task

logger = logging.getLogger(__name__)


def build_searchable_content(task: Task) -> str:
    """
    Build searchable text content from a task.

    Combines title + description + labels into a single searchable string.
    This ensures all relevant text is indexed for search.

    Args:
        task: Task object to extract content from

    Returns:
        Concatenated searchable text
    """
    parts: list[str] = []

    # Title is always present and most important
    if task.title:
        parts.append(task.title)

    # Description provides additional context
    if task.description:
        parts.append(task.description)

    # Labels can contain useful keywords
    if task.labels:
        parts.append(" ".join(task.labels))

    # Task type can be useful for filtering
    if task.task_type:
        parts.append(task.task_type)

    # Category can help with domain filtering
    if task.category:
        parts.append(task.category)

    return " ".join(parts)


class TaskSearcher:
    """
    TF-IDF based search for tasks.

    Wraps the generic TFIDFSearcher with task-specific content building.
    Supports lazy fitting and dirty tracking for efficient reindexing.
    """

    def __init__(
        self,
        ngram_range: tuple[int, int] = (1, 2),
        max_features: int = 10000,
        min_df: int = 1,
        stop_words: str | None = "english",
        refit_threshold: int = 10,
    ):
        """
        Initialize task searcher.

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
        self._dirty = True

    def fit(self, tasks: list[Task]) -> None:
        """
        Build the search index from tasks.

        Args:
            tasks: List of Task objects to index
        """
        if not tasks:
            self._searcher.fit([])
            self._dirty = False
            return

        # Build (task_id, content) tuples
        items = [(task.id, build_searchable_content(task)) for task in tasks]

        self._searcher.fit(items)
        self._dirty = False
        logger.info(f"Task search index built with {len(tasks)} tasks")

    def search(self, query: str, top_k: int = 20) -> list[tuple[str, float]]:
        """
        Search for tasks matching the query.

        Args:
            query: Search query text
            top_k: Maximum number of results to return

        Returns:
            List of (task_id, similarity_score) tuples, sorted by
            similarity descending.
        """
        return self._searcher.search(query, top_k)

    def needs_refit(self) -> bool:
        """Check if the index needs rebuilding."""
        return self._dirty or self._searcher.needs_refit()

    def mark_dirty(self) -> None:
        """Mark the index as needing a refit."""
        self._dirty = True
        self._searcher.mark_update()

    def get_stats(self) -> dict[str, Any]:
        """Get statistics about the search index."""
        stats = self._searcher.get_stats()
        stats["dirty"] = self._dirty
        return stats

    def clear(self) -> None:
        """Clear the search index."""
        self._searcher.clear()
        self._dirty = True
