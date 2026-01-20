"""
TF-IDF based semantic search backend.

Provides local semantic search using scikit-learn's TfidfVectorizer.
No API calls required - works completely offline.

Requires: scikit-learn (pip install scikit-learn)

Features:
- Unigram + bigram matching for better phrase detection
- Cosine similarity ranking
- Fast sub-millisecond search for thousands of items

Note: Only full fit() is implemented. Incremental updates are tracked via
mark_update() and needs_refit() but require calling fit() to rebuild the index.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from scipy.sparse import csr_matrix
    from sklearn.feature_extraction.text import TfidfVectorizer

logger = logging.getLogger(__name__)


class TFIDFSearcher:
    """
    TF-IDF based search backend using sklearn.

    This is the default search backend for memory recall and task search.
    It uses TF-IDF (Term Frequency-Inverse Document Frequency) vectorization
    with cosine similarity for ranking.

    Configuration options:
    - ngram_range: Tuple of (min, max) n-gram sizes (default: (1, 2))
    - max_features: Maximum vocabulary size (default: 10000)
    - min_df: Minimum document frequency for terms (default: 1)
    - stop_words: Language for stop words removal (default: "english")

    Example:
        searcher = TFIDFSearcher()
        searcher.fit([("id1", "content1"), ("id2", "content2")])
        results = searcher.search("query", top_k=5)
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
        Initialize TF-IDF searcher.

        Args:
            ngram_range: Min/max n-gram sizes for tokenization
            max_features: Maximum vocabulary size
            min_df: Minimum document frequency for inclusion
            stop_words: Language for stop words (None to disable)
            refit_threshold: Number of updates before automatic refit
        """
        self._ngram_range = ngram_range
        self._max_features = max_features
        self._min_df = min_df
        self._stop_words = stop_words
        self._refit_threshold = refit_threshold

        # Lazy-loaded sklearn components
        self._vectorizer: TfidfVectorizer | None = None
        self._vectors: csr_matrix | None = None
        self._item_ids: list[str] = []
        self._fitted = False
        self._pending_updates = 0

    def _ensure_vectorizer(self) -> TfidfVectorizer:
        """Create or return the TF-IDF vectorizer."""
        if self._vectorizer is None:
            try:
                from sklearn.feature_extraction.text import (
                    TfidfVectorizer as SklearnTfidfVectorizer,
                )

                self._vectorizer = SklearnTfidfVectorizer(
                    ngram_range=self._ngram_range,
                    max_features=self._max_features,
                    min_df=self._min_df,
                    stop_words=self._stop_words,
                )
            except ImportError as e:
                raise ImportError(
                    "TF-IDF search requires scikit-learn. Install with: pip install scikit-learn"
                ) from e
        return self._vectorizer

    def fit(self, items: list[tuple[str, str]]) -> None:
        """
        Build TF-IDF index from all items.

        This should be called:
        - On startup to build initial index
        - After bulk item operations
        - When needs_refit() returns True

        Args:
            items: List of (item_id, content) tuples to index
        """
        if not items:
            self._fitted = False
            self._item_ids = []
            self._vectors = None
            self._pending_updates = 0
            logger.debug("TF-IDF index cleared (no items)")
            return

        vectorizer = self._ensure_vectorizer()

        self._item_ids = [item_id for item_id, _ in items]
        contents = [content for _, content in items]

        try:
            self._vectors = vectorizer.fit_transform(contents)
            self._fitted = True
            self._pending_updates = 0
            logger.info(f"TF-IDF index built with {len(items)} items")
        except Exception as e:
            logger.error(f"Failed to build TF-IDF index: {e}")
            self._fitted = False
            raise

    def search(self, query: str, top_k: int = 10) -> list[tuple[str, float]]:
        """
        Search for items matching the query.

        Args:
            query: Search query text
            top_k: Maximum number of results to return

        Returns:
            List of (item_id, similarity_score) tuples, sorted by
            similarity descending. Scores are in range [0, 1].
        """
        if not self._fitted or self._vectors is None or len(self._item_ids) == 0:
            return []

        try:
            import numpy as np
            from sklearn.metrics.pairwise import cosine_similarity

            vectorizer = self._ensure_vectorizer()

            # Transform query using fitted vocabulary
            query_vec = vectorizer.transform([query])

            # Compute cosine similarities
            similarities = cosine_similarity(query_vec, self._vectors)[0]

            # Get top-k indices (handling case where we have fewer results)
            k = min(top_k, len(similarities))
            if k == 0:
                return []

            # Get indices of top-k highest similarities
            top_indices = np.argsort(similarities)[-k:][::-1]

            # Return results with non-zero similarity
            results = [
                (self._item_ids[i], float(similarities[i]))
                for i in top_indices
                if similarities[i] > 0
            ]

            return results

        except ImportError as e:
            logger.error(f"TF-IDF search requires scikit-learn: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"TF-IDF search failed: {e}", exc_info=True)
            raise

    def needs_refit(self) -> bool:
        """
        Check if the index needs rebuilding.

        Returns:
            True if fit() should be called before search()
        """
        return not self._fitted or self._pending_updates >= self._refit_threshold

    def mark_update(self) -> None:
        """
        Mark that an item update occurred.

        Call this after adding/updating/removing items to track
        when a refit is needed.
        """
        self._pending_updates += 1

    def get_stats(self) -> dict[str, Any]:
        """
        Get statistics about the TF-IDF index.

        Returns:
            Dict with index statistics
        """
        stats: dict[str, Any] = {
            "fitted": self._fitted,
            "item_count": len(self._item_ids),
            "pending_updates": self._pending_updates,
            "refit_threshold": self._refit_threshold,
        }

        if self._vectorizer is not None and self._fitted:
            vocab = getattr(self._vectorizer, "vocabulary_", {})
            stats["vocabulary_size"] = len(vocab)
            stats["ngram_range"] = self._ngram_range
            stats["max_features"] = self._max_features

        return stats

    def clear(self) -> None:
        """Clear the search index."""
        self._item_ids = []
        self._vectors = None
        self._fitted = False
        self._pending_updates = 0
