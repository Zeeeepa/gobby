"""
Hybrid search backend combining TF-IDF and OpenAI embeddings.

Uses Reciprocal Rank Fusion (RRF) to combine results from both
search backends, getting the best of fast local search and
deep semantic matching.

RRF Formula: score(d) = sum(1 / (k + rank_i(d))) for each ranking i
where k is a constant (default 60) and rank_i(d) is the rank of
document d in ranking i.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gobby.storage.database import DatabaseProtocol

logger = logging.getLogger(__name__)


class HybridSearcher:
    """
    Hybrid search backend combining TF-IDF and OpenAI embeddings.

    This backend runs both TF-IDF and OpenAI searches in parallel
    and combines results using Reciprocal Rank Fusion (RRF).

    Configuration options:
    - tfidf_weight: Weight for TF-IDF results (default: 0.5)
    - openai_weight: Weight for OpenAI results (default: 0.5)
    - rrf_k: RRF constant k (default: 60)
    - fallback_to_tfidf: If True, use only TF-IDF when OpenAI fails

    Example:
        searcher = HybridSearcher(db)
        searcher.fit([("id1", "content1"), ("id2", "content2")])
        results = searcher.search("query", top_k=5)
    """

    def __init__(
        self,
        db: DatabaseProtocol,
        tfidf_weight: float = 0.5,
        openai_weight: float = 0.5,
        rrf_k: int = 60,
        fallback_to_tfidf: bool = True,
        tfidf_config: dict | None = None,
        openai_config: dict | None = None,
    ):
        """
        Initialize hybrid searcher.

        Args:
            db: Database connection for OpenAI embedding storage
            tfidf_weight: Weight for TF-IDF results (0-1)
            openai_weight: Weight for OpenAI results (0-1)
            rrf_k: RRF constant (higher = smoother fusion)
            fallback_to_tfidf: Use TF-IDF only if OpenAI fails
            tfidf_config: Configuration dict for TFIDFSearcher
            openai_config: Configuration dict for OpenAISearchAdapter
        """
        from gobby.memory.search.openai_adapter import OpenAISearchAdapter
        from gobby.memory.search.tfidf import TFIDFSearcher

        self._tfidf_weight = tfidf_weight
        self._openai_weight = openai_weight
        self._rrf_k = rrf_k
        self._fallback_to_tfidf = fallback_to_tfidf

        # Initialize backends
        tfidf_config = tfidf_config or {}
        openai_config = openai_config or {}

        self._tfidf = TFIDFSearcher(**tfidf_config)
        self._openai = OpenAISearchAdapter(db=db, **openai_config)

        self._fitted = False
        self._memory_ids: list[str] = []

    def fit(self, memories: list[tuple[str, str]]) -> None:
        """
        Build search indices for both backends.

        Args:
            memories: List of (memory_id, content) tuples to index
        """
        if not memories:
            self._fitted = False
            self._memory_ids = []
            logger.debug("Hybrid search index cleared (no memories)")
            return

        self._memory_ids = [mid for mid, _ in memories]

        # Fit TF-IDF (always succeeds)
        self._tfidf.fit(memories)

        # Try to fit OpenAI (may fail if no API key)
        try:
            self._openai.fit(memories)
        except Exception as e:
            logger.warning(f"OpenAI search backend failed to initialize: {e}")
            if not self._fallback_to_tfidf:
                raise

        self._fitted = True
        logger.info(f"Hybrid search index ready with {len(memories)} memories")

    def search(self, query: str, top_k: int = 10) -> list[tuple[str, float]]:
        """
        Search using both backends and combine results with RRF.

        Args:
            query: Search query text
            top_k: Maximum number of results to return

        Returns:
            List of (memory_id, rrf_score) tuples, sorted by score descending
        """
        if not self._fitted or not self._memory_ids:
            return []

        # Get results from TF-IDF
        tfidf_results = self._tfidf.search(query, top_k=top_k * 2)

        # Try to get results from OpenAI
        openai_results: list[tuple[str, float]] = []
        try:
            openai_results = self._openai.search(query, top_k=top_k * 2)
        except Exception as e:
            logger.warning(f"OpenAI search failed, using TF-IDF only: {e}")
            if not self._fallback_to_tfidf:
                raise

        # If only one backend returned results, use those
        if not openai_results:
            return tfidf_results[:top_k]
        if not tfidf_results:
            return openai_results[:top_k]

        # Combine using RRF
        combined = self._reciprocal_rank_fusion(
            rankings=[tfidf_results, openai_results],
            weights=[self._tfidf_weight, self._openai_weight],
        )

        return combined[:top_k]

    def _reciprocal_rank_fusion(
        self,
        rankings: list[list[tuple[str, float]]],
        weights: list[float],
    ) -> list[tuple[str, float]]:
        """
        Combine rankings using weighted Reciprocal Rank Fusion.

        RRF Formula: score(d) = sum(weight_i / (k + rank_i(d)))

        Args:
            rankings: List of rankings, each a list of (id, score) tuples
            weights: Weight for each ranking

        Returns:
            Combined ranking as list of (id, rrf_score) tuples
        """
        scores: dict[str, float] = defaultdict(float)

        for ranking, weight in zip(rankings, weights, strict=True):
            for rank, (memory_id, _) in enumerate(ranking, start=1):
                # RRF score contribution
                rrf_score = weight / (self._rrf_k + rank)
                scores[memory_id] += rrf_score

        # Sort by combined RRF score
        sorted_results = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        return sorted_results

    def needs_refit(self) -> bool:
        """Check if either backend needs refitting."""
        return not self._fitted or self._tfidf.needs_refit()

    def get_stats(self) -> dict:
        """
        Get statistics about both search backends.

        Returns:
            Dict with combined statistics
        """
        return {
            "fitted": self._fitted,
            "memory_count": len(self._memory_ids),
            "tfidf_weight": self._tfidf_weight,
            "openai_weight": self._openai_weight,
            "rrf_k": self._rrf_k,
            "tfidf": self._tfidf.get_stats(),
            "openai": self._openai.get_stats(),
        }

    def clear(self) -> None:
        """Clear both search indices."""
        self._tfidf.clear()
        self._openai.clear()
        self._memory_ids = []
        self._fitted = False

    async def async_fit(self, memories: list[tuple[str, str]]) -> None:
        """
        Async version of fit() for use in async contexts.

        Args:
            memories: List of (memory_id, content) tuples to index
        """
        if not memories:
            self._fitted = False
            self._memory_ids = []
            return

        self._memory_ids = [mid for mid, _ in memories]

        # Fit TF-IDF synchronously (it's fast)
        self._tfidf.fit(memories)

        # Fit OpenAI asynchronously
        try:
            await self._openai.async_fit(memories)
        except Exception as e:
            logger.warning(f"OpenAI search backend failed to initialize: {e}")
            if not self._fallback_to_tfidf:
                raise

        self._fitted = True
        logger.info(f"Hybrid search index ready with {len(memories)} memories")

    async def async_search(
        self,
        query: str,
        top_k: int = 10,
    ) -> list[tuple[str, float]]:
        """
        Async version of search() for use in async contexts.

        Runs both searches concurrently for better performance.

        Args:
            query: Search query text
            top_k: Maximum number of results

        Returns:
            List of (memory_id, rrf_score) tuples
        """
        if not self._fitted or not self._memory_ids:
            return []

        # Run TF-IDF in thread pool (sync) and OpenAI search concurrently
        loop = asyncio.get_event_loop()

        tfidf_task = loop.run_in_executor(
            None, lambda: self._tfidf.search(query, top_k=top_k * 2)
        )

        try:
            openai_task = self._openai.async_search(query, top_k=top_k * 2)
            tfidf_results, openai_results = await asyncio.gather(
                tfidf_task, openai_task
            )
        except Exception as e:
            logger.warning(f"OpenAI search failed: {e}")
            tfidf_results = await tfidf_task
            openai_results = []

        # Combine results
        if not openai_results:
            return tfidf_results[:top_k]
        if not tfidf_results:
            return openai_results[:top_k]

        combined = self._reciprocal_rank_fusion(
            rankings=[tfidf_results, openai_results],
            weights=[self._tfidf_weight, self._openai_weight],
        )

        return combined[:top_k]
