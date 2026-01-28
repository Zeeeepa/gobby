"""Search coordination for memory recall operations."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from gobby.storage.memories import Memory

if TYPE_CHECKING:
    from gobby.config.persistence import MemoryConfig
    from gobby.memory.search import SearchBackend
    from gobby.storage.database import DatabaseProtocol
    from gobby.storage.memories import LocalMemoryManager

logger = logging.getLogger(__name__)


class SearchCoordinator:
    """
    Coordinates search operations for memory recall.

    Manages the search backend lifecycle, fitting, and query execution.
    Extracts search-related logic from MemoryManager for focused responsibility.
    """

    def __init__(
        self,
        storage: LocalMemoryManager,
        config: MemoryConfig,
        db: DatabaseProtocol,
    ):
        """
        Initialize the search coordinator.

        Args:
            storage: Memory storage manager for accessing memories
            config: Memory configuration for search settings
            db: Database connection for search backend initialization
        """
        self._storage = storage
        self._config = config
        self._db = db
        self._search_backend: SearchBackend | None = None
        self._search_backend_fitted = False

    @property
    def search_backend(self) -> SearchBackend:
        """
        Lazy-init search backend based on configuration.

        The backend type is determined by config.search_backend:
        - "tfidf" (default): Zero-dependency TF-IDF search
        - "text": Simple text substring matching
        """
        if self._search_backend is None:
            from gobby.memory.search import get_search_backend

            backend_type = getattr(self._config, "search_backend", "tfidf")
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

    def ensure_fitted(self) -> None:
        """Ensure the search backend is fitted with current memories."""
        if self._search_backend_fitted:
            return

        backend = self.search_backend
        if not backend.needs_refit():
            self._search_backend_fitted = True
            return

        # Fit the backend with all memories
        max_memories = getattr(self._config, "max_index_memories", 10000)
        memories = self._storage.list_memories(limit=max_memories)
        memory_tuples = [(m.id, m.content) for m in memories]

        try:
            backend.fit(memory_tuples)
            self._search_backend_fitted = True
            logger.info(f"Search backend fitted with {len(memory_tuples)} memories")
        except Exception as e:
            logger.error(f"Failed to fit search backend: {e}")
            raise

    def mark_refit_needed(self) -> None:
        """Mark that the search backend needs to be refitted."""
        self._search_backend_fitted = False

    def reindex(self) -> dict[str, Any]:
        """
        Force rebuild of the search index.

        This method explicitly rebuilds the TF-IDF (or other configured)
        search index from all stored memories. Useful for:
        - Initial index building
        - Recovery after corruption
        - After bulk memory operations

        Returns:
            Dict with index statistics including memory_count, backend_type, etc.
        """
        # Get all memories
        memories = self._storage.list_memories(limit=10000)
        memory_tuples = [(m.id, m.content) for m in memories]

        # Force refit the backend
        backend = self.search_backend
        backend_type = getattr(self._config, "search_backend", "tfidf")

        try:
            backend.fit(memory_tuples)
            self._search_backend_fitted = True

            # Get backend stats
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

        Uses the new search backend by default (TF-IDF),
        falling back to legacy semantic search if configured.

        Args:
            query: Search query text
            project_id: Filter by project
            limit: Maximum results to return
            min_importance: Minimum importance threshold
            search_mode: Search mode (tfidf, text, etc.)
            tags_all: Memory must have ALL of these tags
            tags_any: Memory must have at least ONE of these tags
            tags_none: Memory must have NONE of these tags

        Returns:
            List of matching Memory objects
        """
        # Determine search mode from config or parameters
        if search_mode is None:
            search_mode = getattr(self._config, "search_backend", "tfidf")

        # Use the search backend
        try:
            self.ensure_fitted()
            # Fetch more results to allow for filtering
            fetch_multiplier = 3 if (tags_all or tags_any or tags_none) else 2
            results = self.search_backend.search(query, top_k=limit * fetch_multiplier)

            # Get the actual Memory objects
            memory_ids = [mid for mid, _ in results]
            memories = []
            for mid in memory_ids:
                memory = self._storage.get_memory(mid)
                if memory:
                    # Apply filters - allow global memories (project_id is None) to pass through
                    if (
                        project_id
                        and memory.project_id is not None
                        and memory.project_id != project_id
                    ):
                        continue
                    if min_importance is not None and memory.importance < min_importance:
                        continue
                    # Apply tag filters
                    if not self._passes_tag_filter(memory, tags_all, tags_any, tags_none):
                        continue
                    memories.append(memory)
                    if len(memories) >= limit:
                        break

            return memories

        except Exception as e:
            logger.warning(f"Search backend failed, falling back to text search: {e}")
            # Fall back to text search with tag filtering
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

        # Check tags_all: memory must have ALL specified tags
        if tags_all and not set(tags_all).issubset(memory_tags):
            return False

        # Check tags_any: memory must have at least ONE specified tag
        if tags_any and not memory_tags.intersection(tags_any):
            return False

        # Check tags_none: memory must have NONE of the specified tags
        if tags_none and memory_tags.intersection(tags_none):
            return False

        return True
