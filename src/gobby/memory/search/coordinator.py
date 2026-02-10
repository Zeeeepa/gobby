"""Search coordination for memory recall operations."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from gobby.storage.memories import Memory

if TYPE_CHECKING:
    from gobby.config.persistence import MemoryConfig
    from gobby.memory.search import SearchBackend
    from gobby.search.unified import UnifiedSearcher
    from gobby.storage.database import DatabaseProtocol
    from gobby.storage.memories import LocalMemoryManager

logger = logging.getLogger(__name__)

# Modes that use UnifiedSearcher instead of the simple sync SearchBackend
_UNIFIED_MODES = {"auto", "embedding", "hybrid"}


def _run_async(coro: Any) -> Any:
    """Bridge async coroutine to sync, handling existing event loops."""
    try:
        asyncio.get_running_loop()
        # Already in an async context — run in a new thread
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    except RuntimeError:
        # No running loop — safe to use asyncio.run()
        return asyncio.run(coro)


class SearchCoordinator:
    """
    Coordinates search operations for memory recall.

    Manages the search backend lifecycle, fitting, and query execution.
    For tfidf/text modes, uses the simple sync SearchBackend.
    For auto/embedding/hybrid modes, delegates to UnifiedSearcher.
    """

    def __init__(
        self,
        storage: LocalMemoryManager,
        config: MemoryConfig,
        db: DatabaseProtocol,
    ):
        self._storage = storage
        self._config = config
        self._db = db
        self._search_backend: SearchBackend | None = None
        self._search_backend_fitted = False

        # UnifiedSearcher for auto/embedding/hybrid modes
        self._unified_searcher: UnifiedSearcher | None = None
        self._unified_fitted = False

        backend_type = getattr(self._config, "search_backend", "tfidf")
        if backend_type in _UNIFIED_MODES:
            self._init_unified_searcher(backend_type)

    def _init_unified_searcher(self, mode: str) -> None:
        """Create a UnifiedSearcher from MemoryConfig settings."""
        from gobby.search.models import SearchConfig
        from gobby.search.unified import UnifiedSearcher

        search_config = SearchConfig(
            mode=mode,
            embedding_model=getattr(self._config, "embedding_model", "text-embedding-3-small"),
            tfidf_weight=getattr(self._config, "tfidf_weight", 0.4),
            embedding_weight=getattr(self._config, "embedding_weight", 0.6),
        )
        self._unified_searcher = UnifiedSearcher(config=search_config)

    @property
    def search_backend(self) -> SearchBackend:
        """
        Lazy-init search backend based on configuration.

        Only used for tfidf/text modes. For auto/embedding/hybrid,
        the UnifiedSearcher is used directly.
        """
        if self._search_backend is None:
            from gobby.memory.search import get_search_backend

            backend_type = getattr(self._config, "search_backend", "tfidf")
            # If unified mode, fall back to tfidf for the sync backend
            if backend_type in _UNIFIED_MODES:
                backend_type = "tfidf"

            logger.debug(f"Initializing search backend: {backend_type}")

            try:
                self._search_backend = get_search_backend(
                    backend_type=backend_type,
                    db=self._db,
                )
            except Exception as e:
                logger.warning(
                    f"Failed to initialize {backend_type} backend: {e}. Falling back to tfidf"
                )
                self._search_backend = get_search_backend("tfidf")

        return self._search_backend

    def _get_memory_tuples(self, max_memories: int = 10000) -> list[tuple[str, str]]:
        """Get all memories as (id, content) tuples for indexing."""
        memories = self._storage.list_memories(limit=max_memories)
        return [(m.id, m.content) for m in memories]

    def ensure_fitted(self) -> None:
        """Ensure the search backend is fitted with current memories."""
        if self._unified_searcher is not None:
            self._ensure_unified_fitted()

        if self._search_backend_fitted:
            return

        backend = self.search_backend
        max_memories = getattr(self._config, "max_index_memories", 10000)
        memory_tuples = self._get_memory_tuples(max_memories)

        try:
            backend.fit(memory_tuples)
            self._search_backend_fitted = True
            logger.info(f"Search backend fitted with {len(memory_tuples)} memories")
        except Exception as e:
            logger.error(f"Failed to fit search backend: {e}")
            raise

    def _ensure_unified_fitted(self) -> None:
        """Ensure UnifiedSearcher is fitted."""
        if self._unified_fitted:
            return
        if self._unified_searcher is None:
            return

        max_memories = getattr(self._config, "max_index_memories", 10000)
        memory_tuples = self._get_memory_tuples(max_memories)

        try:
            _run_async(self._unified_searcher.fit_async(memory_tuples))
            self._unified_fitted = True
            logger.info(f"UnifiedSearcher fitted with {len(memory_tuples)} memories")
        except Exception as e:
            logger.error(f"Failed to fit UnifiedSearcher: {e}")
            raise

    def mark_refit_needed(self) -> None:
        """Mark that the search backend needs to be refitted."""
        self._search_backend_fitted = False
        self._unified_fitted = False

    def reindex(self) -> dict[str, Any]:
        """
        Force rebuild of the search index.

        Returns:
            Dict with index statistics including memory_count, backend_type, etc.
        """
        memories = self._storage.list_memories(limit=10000)
        memory_tuples = [(m.id, m.content) for m in memories]
        backend_type = getattr(self._config, "search_backend", "tfidf")

        if self._unified_searcher is not None:
            return self._reindex_unified(memory_tuples, backend_type)

        # Sync backend path
        backend = self.search_backend

        try:
            backend.fit(memory_tuples)
            self._search_backend_fitted = True

            stats = backend.get_stats() if hasattr(backend, "get_stats") else {}

            return {
                "success": True,
                "memory_count": len(memory_tuples),
                "backend_type": backend_type,
                "fitted": True,
                **stats,
            }
        except Exception as e:
            logger.error(f"Failed to reindex search backend: {e}")
            return {
                "success": False,
                "error": str(e),
                "memory_count": len(memory_tuples),
                "backend_type": backend_type,
            }

    def _reindex_unified(
        self, memory_tuples: list[tuple[str, str]], backend_type: str
    ) -> dict[str, Any]:
        """Reindex using UnifiedSearcher."""
        if self._unified_searcher is None:
            raise RuntimeError("UnifiedSearcher is not initialized")
        try:
            _run_async(self._unified_searcher.fit_async(memory_tuples))
            self._unified_fitted = True

            stats = self._unified_searcher.get_stats()

            return {
                "success": True,
                "memory_count": len(memory_tuples),
                "backend_type": backend_type,
                "fitted": True,
                **stats,
            }
        except Exception as e:
            logger.error(f"Failed to reindex UnifiedSearcher: {e}")
            return {
                "success": False,
                "error": str(e),
                "memory_count": len(memory_tuples),
                "backend_type": backend_type,
            }

    def search(
        self,
        query: str,
        project_id: str | None = None,
        limit: int = 10,
        min_importance: float | None = None,
        search_mode: str | None = None,
        tags_all: list[str] | None = None,
        tags_any: list[str] | None = None,
        tags_none: list[str] | None = None,
    ) -> list[Memory]:
        """
        Perform search using the configured search backend.

        Args:
            query: Search query text
            project_id: Filter by project
            limit: Maximum results to return
            min_importance: Minimum importance threshold
            search_mode: Search mode override
            tags_all: Memory must have ALL of these tags
            tags_any: Memory must have at least ONE of these tags
            tags_none: Memory must have NONE of these tags

        Returns:
            List of matching Memory objects
        """
        # Direct text search mode bypasses TF-IDF/unified backends
        if search_mode == "text":
            return self._storage.search_memories(
                query_text=query,
                project_id=project_id,
                limit=limit,
                tags_all=tags_all,
                tags_any=tags_any,
                tags_none=tags_none,
            )

        try:
            self.ensure_fitted()
            fetch_multiplier = 3 if (tags_all or tags_any or tags_none) else 2

            # Get raw search results
            if self._unified_searcher is not None:
                results = _run_async(
                    self._unified_searcher.search_async(query, top_k=limit * fetch_multiplier)
                )
            else:
                results = self.search_backend.search(query, top_k=limit * fetch_multiplier)

            # Get the actual Memory objects and apply filters
            memory_ids = [mid for mid, _ in results]
            memories = []
            for mid in memory_ids:
                memory = self._storage.get_memory(mid)
                if memory:
                    if (
                        project_id
                        and memory.project_id is not None
                        and memory.project_id != project_id
                    ):
                        continue
                    if min_importance is not None and memory.importance < min_importance:
                        continue
                    if not self._passes_tag_filter(memory, tags_all, tags_any, tags_none):
                        continue
                    memories.append(memory)
                    if len(memories) >= limit:
                        break

            return memories

        except Exception as e:
            logger.warning(f"Search backend failed, falling back to text search: {e}")
            memories = self._storage.search_memories(
                query_text=query,
                project_id=project_id,
                limit=limit * 2,
                tags_all=tags_all,
                tags_any=tags_any,
                tags_none=tags_none,
            )
            if min_importance:
                memories = [m for m in memories if m.importance >= min_importance]
            return memories[:limit]

    def _passes_tag_filter(
        self,
        memory: Memory,
        tags_all: list[str] | None = None,
        tags_any: list[str] | None = None,
        tags_none: list[str] | None = None,
    ) -> bool:
        """Check if a memory passes the tag filter criteria."""
        memory_tags = set(memory.tags) if memory.tags else set()

        if tags_all and not set(tags_all).issubset(memory_tags):
            return False

        if tags_any and not memory_tags.intersection(tags_any):
            return False

        if tags_none and memory_tags.intersection(tags_none):
            return False

        return True
