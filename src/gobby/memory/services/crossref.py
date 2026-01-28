"""Cross-reference service for linking related memories."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from gobby.storage.memories import Memory

if TYPE_CHECKING:
    from gobby.config.persistence import MemoryConfig
    from gobby.memory.search import SearchBackend
    from gobby.storage.memories import LocalMemoryManager

logger = logging.getLogger(__name__)


class CrossrefService:
    """
    Service for creating and managing cross-references between memories.

    Cross-references link related memories based on content similarity,
    enabling navigation between conceptually connected items.
    """

    def __init__(
        self,
        storage: LocalMemoryManager,
        config: MemoryConfig,
        search_backend_getter: Callable[[], SearchBackend],
        ensure_fitted: Callable[[], None],
    ):
        """
        Initialize the cross-reference service.

        Args:
            storage: Memory storage manager for persistence
            config: Memory configuration for thresholds
            search_backend_getter: Callable that returns the search backend
            ensure_fitted: Callable that ensures search backend is fitted
        """
        self._storage = storage
        self._config = config
        self._get_search_backend = search_backend_getter
        self._ensure_fitted = ensure_fitted

    async def create_crossrefs(
        self,
        memory: Memory,
        threshold: float | None = None,
        max_links: int | None = None,
    ) -> int:
        """
        Find and link similar memories.

        Uses the search backend to find memories similar to the given one
        and creates cross-references for those above the threshold.

        Args:
            memory: The memory to find links for
            threshold: Minimum similarity to create link (default from config)
            max_links: Maximum links to create (default from config)

        Returns:
            Number of cross-references created
        """
        # Get thresholds from config or use defaults
        if threshold is None:
            threshold = getattr(self._config, "crossref_threshold", None)
            if threshold is None:
                threshold = 0.3
        if max_links is None:
            max_links = getattr(self._config, "crossref_max_links", None)
            if max_links is None:
                max_links = 5

        # Ensure search backend is fitted (sync check is fine - just checks a flag)
        self._ensure_fitted()

        # Search for similar memories (wrap sync I/O in to_thread)
        search_backend = self._get_search_backend()
        similar = await asyncio.to_thread(search_backend.search, memory.content, max_links + 1)

        # Create cross-references
        created = 0
        for other_id, score in similar:
            # Skip self-reference
            if other_id == memory.id:
                continue

            # Skip below threshold
            if score < threshold:
                continue

            # Create the crossref (wrap sync I/O in to_thread)
            await asyncio.to_thread(self._storage.create_crossref, memory.id, other_id, score)
            created += 1

            if created >= max_links:
                break

        if created > 0:
            logger.debug(f"Created {created} crossrefs for memory {memory.id}")

        return created

    async def get_related(
        self,
        memory_id: str,
        limit: int = 5,
        min_similarity: float = 0.0,
    ) -> list[Memory]:
        """
        Get memories linked to this one via cross-references.

        Args:
            memory_id: The memory ID to find related memories for
            limit: Maximum number of results
            min_similarity: Minimum similarity threshold

        Returns:
            List of related Memory objects, sorted by similarity
        """
        crossrefs = await asyncio.to_thread(
            self._storage.get_crossrefs,
            memory_id,
            limit=limit,
            min_similarity=min_similarity,
        )

        # Get the actual Memory objects
        memories = []
        for ref in crossrefs:
            # Get the "other" memory in the relationship
            other_id = ref.target_id if ref.source_id == memory_id else ref.source_id
            memory = await asyncio.to_thread(self._storage.get_memory, other_id)
            if memory:
                memories.append(memory)

        return memories
