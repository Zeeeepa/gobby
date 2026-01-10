"""
OpenAI embedding-based search adapter.

Wraps the existing SemanticMemorySearch class to implement the
SearchBackend protocol, enabling it to be used interchangeably
with TF-IDF search.

Requires:
- OpenAI API key configured
- litellm package installed
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gobby.storage.database import LocalDatabase

logger = logging.getLogger(__name__)


class OpenAISearchAdapter:
    """
    Adapter for OpenAI embedding-based search.

    Wraps SemanticMemorySearch to implement the SearchBackend protocol.
    Uses OpenAI's text-embedding-3-small model by default.

    Configuration options:
    - embedding_model: Model to use for embeddings
    - embedding_dim: Dimension of embedding vectors
    - api_key: OpenAI API key (or set OPENAI_API_KEY env var)

    Note: This adapter requires a database connection to store
    and retrieve embeddings. Unlike TFIDFSearcher, it stores
    embeddings persistently in the database.
    """

    def __init__(
        self,
        db: LocalDatabase,
        embedding_model: str = "text-embedding-3-small",
        embedding_dim: int = 1536,
        api_key: str | None = None,
    ):
        """
        Initialize OpenAI search adapter.

        Args:
            db: Database connection for embedding storage
            embedding_model: OpenAI model for embeddings
            embedding_dim: Dimension of embedding vectors
            api_key: OpenAI API key (optional, uses env var if not provided)
        """
        from gobby.memory.semantic_search import SemanticMemorySearch

        self._db = db
        self._search = SemanticMemorySearch(
            db=db,
            embedding_model=embedding_model,
            embedding_dim=embedding_dim,
            openai_api_key=api_key,
        )
        self._fitted = False
        self._memory_ids: list[str] = []

    def fit(self, memories: list[tuple[str, str]]) -> None:
        """
        Build embedding index for all memories.

        This generates embeddings for all memories that don't have them,
        storing them in the database for future searches.

        Args:
            memories: List of (memory_id, content) tuples to embed
        """
        if not memories:
            self._fitted = False
            self._memory_ids = []
            logger.debug("OpenAI search index cleared (no memories)")
            return

        self._memory_ids = [mid for mid, _ in memories]

        # Run async embedding in sync context
        loop = asyncio.new_event_loop()
        try:
            for memory_id, content in memories:
                try:
                    loop.run_until_complete(
                        self._search.embed_memory(memory_id, content, force=False)
                    )
                except Exception as e:
                    logger.warning(f"Failed to embed memory {memory_id}: {e}")

            self._fitted = True
            logger.info(f"OpenAI search index ready with {len(memories)} memories")
        finally:
            loop.close()

    def search(self, query: str, top_k: int = 10) -> list[tuple[str, float]]:
        """
        Search for memories semantically similar to the query.

        Args:
            query: Search query text
            top_k: Maximum number of results to return

        Returns:
            List of (memory_id, similarity_score) tuples, sorted by
            similarity descending. Scores are in range [0, 1].
        """
        if not self._fitted or not self._memory_ids:
            return []

        # Run async search in sync context
        loop = asyncio.new_event_loop()
        try:
            results = loop.run_until_complete(
                self._search.search(
                    query=query,
                    top_k=top_k,
                    min_similarity=0.0,
                )
            )

            return [(r.memory.id, r.similarity) for r in results]
        except Exception as e:
            logger.error(f"OpenAI search failed: {e}")
            return []
        finally:
            loop.close()

    def needs_refit(self) -> bool:
        """
        Check if the index needs rebuilding.

        For OpenAI embeddings, this checks if there are memories
        without embeddings in the database.
        """
        return not self._fitted

    def get_stats(self) -> dict:
        """
        Get statistics about the embedding index.

        Returns:
            Dict with index statistics
        """
        return {
            "fitted": self._fitted,
            "memory_count": len(self._memory_ids),
            **self._search.get_embedding_stats(),
        }

    def clear(self) -> None:
        """Clear the search index (embeddings remain in database)."""
        self._memory_ids = []
        self._fitted = False

    async def async_fit(self, memories: list[tuple[str, str]]) -> None:
        """
        Async version of fit() for use in async contexts.

        Args:
            memories: List of (memory_id, content) tuples to embed
        """
        if not memories:
            self._fitted = False
            self._memory_ids = []
            return

        self._memory_ids = [mid for mid, _ in memories]

        for memory_id, content in memories:
            try:
                await self._search.embed_memory(memory_id, content, force=False)
            except Exception as e:
                logger.warning(f"Failed to embed memory {memory_id}: {e}")

        self._fitted = True
        logger.info(f"OpenAI search index ready with {len(memories)} memories")

    async def async_search(
        self,
        query: str,
        top_k: int = 10,
        min_similarity: float = 0.0,
    ) -> list[tuple[str, float]]:
        """
        Async version of search() for use in async contexts.

        Args:
            query: Search query text
            top_k: Maximum number of results
            min_similarity: Minimum similarity threshold

        Returns:
            List of (memory_id, similarity_score) tuples
        """
        if not self._fitted or not self._memory_ids:
            return []

        try:
            results = await self._search.search(
                query=query,
                top_k=top_k,
                min_similarity=min_similarity,
            )
            return [(r.memory.id, r.similarity) for r in results]
        except Exception as e:
            logger.error(f"OpenAI search failed: {e}")
            return []
