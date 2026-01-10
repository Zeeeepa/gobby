from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from gobby.config.app import MemoryConfig
from gobby.memory.context import build_memory_context
from gobby.storage.database import LocalDatabase
from gobby.storage.memories import LocalMemoryManager, Memory

if TYPE_CHECKING:
    from gobby.compression import TextCompressor
    from gobby.memory.search import SearchBackend
    from gobby.memory.semantic_search import EmbedStats, SemanticMemorySearch

logger = logging.getLogger(__name__)


class MemoryManager:
    """
    High-level manager for memory operations.
    Handles storage, ranking, decay, and business logic.
    """

    def __init__(
        self,
        db: LocalDatabase,
        config: MemoryConfig,
        openai_api_key: str | None = None,
        compressor: TextCompressor | None = None,
    ):
        self.db = db
        self.storage = LocalMemoryManager(db)
        self.config = config
        self._openai_api_key = openai_api_key
        self._semantic_search: SemanticMemorySearch | None = None
        self._search_backend: SearchBackend | None = None
        self._search_backend_fitted = False
        self.compressor = compressor

    @property
    def semantic_search(self) -> SemanticMemorySearch:
        """Lazy-init semantic search to avoid import cycles."""
        if self._semantic_search is None:
            from gobby.memory.semantic_search import SemanticMemorySearch

            self._semantic_search = SemanticMemorySearch(
                db=self.db,
                openai_api_key=self._openai_api_key,
            )
        return self._semantic_search

    @property
    def search_backend(self) -> SearchBackend:
        """
        Lazy-init search backend based on configuration.

        The backend type is determined by config.search_backend:
        - "tfidf" (default): Zero-dependency TF-IDF search
        - "openai": Embedding-based semantic search
        - "hybrid": Combines TF-IDF and OpenAI with RRF
        - "text": Simple text substring matching
        """
        if self._search_backend is None:
            from gobby.memory.search import get_search_backend

            backend_type = getattr(self.config, "search_backend", "tfidf")
            logger.debug(f"Initializing search backend: {backend_type}")

            try:
                self._search_backend = get_search_backend(
                    backend_type=backend_type,
                    db=self.db,
                )
            except Exception as e:
                logger.warning(f"Failed to initialize {backend_type} backend: {e}")
                # Fall back to TF-IDF which has no external deps
                self._search_backend = get_search_backend("tfidf")

        return self._search_backend

    def _ensure_search_backend_fitted(self) -> None:
        """Ensure the search backend is fitted with current memories."""
        if self._search_backend_fitted:
            return

        backend = self.search_backend
        if not backend.needs_refit():
            self._search_backend_fitted = True
            return

        # Fit the backend with all memories
        memories = self.storage.list_memories(limit=10000)
        memory_tuples = [(m.id, m.content) for m in memories]

        try:
            backend.fit(memory_tuples)
            self._search_backend_fitted = True
            logger.info(f"Search backend fitted with {len(memory_tuples)} memories")
        except Exception as e:
            logger.error(f"Failed to fit search backend: {e}")
            raise

    def mark_search_refit_needed(self) -> None:
        """Mark that the search backend needs to be refitted."""
        self._search_backend_fitted = False

    async def remember(
        self,
        content: str,
        memory_type: str = "fact",
        importance: float = 0.5,
        project_id: str | None = None,
        source_type: str = "user",
        source_session_id: str | None = None,
        tags: list[str] | None = None,
    ) -> Memory:
        """
        Store a new memory.

        Args:
            content: The memory content
            memory_type: Type of memory (fact, preference, etc)
            importance: 0.0-1.0 importance score
            project_id: Optional project context
            source_type: Origin of memory
            source_session_id: Origin session
            tags: Optional tags
        """
        # Future: Duplicate detection via embeddings or fuzzy match?
        # For now, rely on storage layer (which uses content-hash ID for dedup)

        memory = self.storage.create_memory(
            content=content,
            memory_type=memory_type,
            importance=importance,
            project_id=project_id,
            source_type=source_type,
            source_session_id=source_session_id,
            tags=tags,
        )

        # Auto-embed if enabled
        if getattr(self.config, "auto_embed", False) and self._openai_api_key:
            try:
                await self.embed_memory(memory.id, force=False)
                logger.debug(f"Auto-embedded memory {memory.id}")
            except Exception as e:
                # Don't fail the remember if embedding fails
                logger.warning(f"Auto-embed failed for {memory.id}: {e}")

        return memory

    def recall(
        self,
        query: str | None = None,
        project_id: str | None = None,
        limit: int = 10,
        min_importance: float | None = None,
        memory_type: str | None = None,
        use_semantic: bool | None = None,
        search_mode: str | None = None,
    ) -> list[Memory]:
        """
        Retrieve memories.

        If query is provided, performs search/ranking.
        If no query, returns top important memories.

        Args:
            query: Optional search query for semantic/text search
            project_id: Filter by project
            limit: Maximum memories to return
            min_importance: Minimum importance threshold
            memory_type: Filter by memory type
            use_semantic: Use semantic search (deprecated, use search_mode instead)
            search_mode: Search mode - "auto" (default), "tfidf", "openai", "hybrid", "text"
        """
        threshold = (
            min_importance if min_importance is not None else self.config.importance_threshold
        )

        if query:
            memories = self._recall_with_search(
                query=query,
                project_id=project_id,
                limit=limit,
                min_importance=threshold,
                use_semantic=use_semantic,
                search_mode=search_mode,
            )
        else:
            # Just get top memories
            memories = self.storage.list_memories(
                project_id=project_id,
                memory_type=memory_type,
                min_importance=threshold,
                limit=limit,
            )

        # Update access stats for retrieved memories
        self._update_access_stats(memories)

        return memories

    def _recall_with_search(
        self,
        query: str,
        project_id: str | None = None,
        limit: int = 10,
        min_importance: float | None = None,
        use_semantic: bool | None = None,
        search_mode: str | None = None,
    ) -> list[Memory]:
        """
        Perform search using the configured search backend.

        Uses the new search backend by default (TF-IDF),
        falling back to legacy semantic search if configured.
        """
        # Determine search mode from config or parameters
        if search_mode is None:
            search_mode = getattr(self.config, "search_backend", "tfidf")

        # Legacy compatibility: use_semantic overrides search_mode
        if use_semantic is not None:
            if use_semantic:
                search_mode = "openai"
            else:
                search_mode = "text"
        elif getattr(self.config, "semantic_search_enabled", False) and search_mode == "tfidf":
            # If semantic_search_enabled is True but we're using tfidf,
            # upgrade to hybrid if possible
            search_mode = getattr(self.config, "search_backend", "tfidf")

        # Use the search backend
        try:
            self._ensure_search_backend_fitted()
            results = self.search_backend.search(query, top_k=limit * 2)

            # Get the actual Memory objects
            memory_ids = [mid for mid, _ in results]
            memories = []
            for mid in memory_ids:
                memory = self.get_memory(mid)
                if memory:
                    # Apply filters
                    if project_id and memory.project_id != project_id:
                        if memory.project_id is not None:  # Allow global memories
                            continue
                    if min_importance and memory.importance < min_importance:
                        continue
                    memories.append(memory)
                    if len(memories) >= limit:
                        break

            return memories

        except Exception as e:
            logger.warning(f"Search backend failed, falling back to text search: {e}")
            # Fall back to text search
            memories = self.storage.search_memories(
                query_text=query,
                project_id=project_id,
                limit=limit * 2,
            )
            if min_importance:
                memories = [m for m in memories if m.importance >= min_importance]
            return memories[:limit]

    def recall_as_context(
        self,
        project_id: str | None = None,
        limit: int = 10,
        min_importance: float | None = None,
        compression_threshold: int | None = None,
    ) -> str:
        """
        Retrieve memories and format them as context for LLM prompts.

        Convenience method that combines recall() with build_memory_context().
        If a compressor was provided at initialization and the content exceeds
        the compression threshold, the inner content will be compressed.

        Args:
            project_id: Filter by project
            limit: Maximum memories to return
            min_importance: Minimum importance threshold
            compression_threshold: Character threshold for compression (default: 4000)

        Returns:
            Formatted markdown string wrapped in <project-memory> tags,
            or empty string if no memories found
        """
        memories = self.recall(
            project_id=project_id,
            limit=limit,
            min_importance=min_importance,
        )

        kwargs: dict[str, Any] = {"compressor": self.compressor}
        if compression_threshold is not None:
            kwargs["compression_threshold"] = compression_threshold

        return build_memory_context(memories, **kwargs)

    def _recall_semantic(
        self,
        query: str,
        project_id: str | None = None,
        limit: int = 10,
        min_importance: float | None = None,
    ) -> list[Memory]:
        """
        Perform semantic search for memories.

        Uses embeddings for similarity search. Falls back to text search
        if embeddings unavailable or no results found.
        """
        import asyncio

        def _fallback_text_search() -> list[Memory]:
            """Fall back to text-based search."""
            memories = self.storage.search_memories(
                query_text=query,
                project_id=project_id,
                limit=limit,
            )
            if min_importance:
                memories = [m for m in memories if m.importance >= min_importance]
            return memories[:limit]

        # Check if we have any embeddings first
        stats = self.semantic_search.get_embedding_stats(project_id)
        if stats.get("embedded_memories", 0) == 0:
            # No embeddings, use text search
            logger.debug("No memory embeddings found, using text search")
            return _fallback_text_search()

        try:
            # Run async search in sync context
            try:
                asyncio.get_running_loop()
                # We're in an async context - this shouldn't happen in normal sync calls
                # Fall back to text search to avoid complexity
                logger.debug("In async context, using text search")
                return _fallback_text_search()
            except RuntimeError:
                # No running loop, we can create one
                pass

            results = asyncio.run(
                self.semantic_search.search(
                    query=query,
                    project_id=project_id,
                    top_k=limit,
                    min_importance=min_importance,
                )
            )

            if not results:
                # No semantic results, try text search
                logger.debug("No semantic results, trying text search")
                return _fallback_text_search()

            return [r.memory for r in results]

        except Exception as e:
            logger.warning(f"Semantic search failed, falling back to text search: {e}")
            return _fallback_text_search()

    def _update_access_stats(self, memories: list[Memory]) -> None:
        """
        Update access count and time for memories.

        Implements debouncing to avoid excessive database writes when the same
        memory is accessed multiple times in quick succession.
        """
        if not memories:
            return

        now = datetime.now(UTC)
        debounce_seconds = getattr(self.config, "access_debounce_seconds", 60)

        for memory in memories:
            # Check if we should debounce this update
            if memory.last_accessed_at:
                try:
                    last_access = datetime.fromisoformat(memory.last_accessed_at)
                    if last_access.tzinfo is None:
                        last_access = last_access.replace(tzinfo=UTC)
                    seconds_since = (now - last_access).total_seconds()
                    if seconds_since < debounce_seconds:
                        # Skip update - accessed too recently
                        continue
                except (ValueError, TypeError):
                    # Invalid timestamp, proceed with update
                    pass

            # Update access stats
            try:
                self.storage.update_access_stats(memory.id, now.isoformat())
            except Exception as e:
                logger.warning(f"Failed to update access stats for {memory.id}: {e}")

    def forget(self, memory_id: str) -> bool:
        """Forget a memory."""
        return self.storage.delete_memory(memory_id)

    def list_memories(
        self,
        project_id: str | None = None,
        memory_type: str | None = None,
        min_importance: float | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Memory]:
        """Passthrough to storage list."""
        return self.storage.list_memories(
            project_id=project_id,
            memory_type=memory_type,
            min_importance=min_importance,
            limit=limit,
            offset=offset,
        )

    def content_exists(self, content: str, project_id: str | None = None) -> bool:
        """Check if a memory with identical content already exists."""
        return self.storage.content_exists(content, project_id)

    def get_memory(self, memory_id: str) -> Memory | None:
        """Get a specific memory by ID."""
        try:
            return self.storage.get_memory(memory_id)
        except ValueError:
            return None

    def update_memory(
        self,
        memory_id: str,
        content: str | None = None,
        importance: float | None = None,
        tags: list[str] | None = None,
    ) -> Memory:
        """
        Update an existing memory.

        Args:
            memory_id: The memory to update
            content: New content (optional)
            importance: New importance (optional)
            tags: New tags (optional)

        Returns:
            Updated Memory object

        Raises:
            ValueError: If memory not found
        """
        return self.storage.update_memory(
            memory_id=memory_id,
            content=content,
            importance=importance,
            tags=tags,
        )

    def get_stats(self, project_id: str | None = None) -> dict[str, Any]:
        """
        Get statistics about stored memories.

        Args:
            project_id: Optional project to filter stats by

        Returns:
            Dictionary with memory statistics
        """
        # Get all memories (use large limit)
        memories = self.storage.list_memories(project_id=project_id, limit=10000)

        if not memories:
            return {
                "total_count": 0,
                "by_type": {},
                "avg_importance": 0.0,
                "project_id": project_id,
            }

        # Count by type
        by_type: dict[str, int] = {}
        total_importance = 0.0

        for m in memories:
            by_type[m.memory_type] = by_type.get(m.memory_type, 0) + 1
            total_importance += m.importance

        return {
            "total_count": len(memories),
            "by_type": by_type,
            "avg_importance": round(total_importance / len(memories), 3),
            "project_id": project_id,
        }

    def decay_memories(self) -> int:
        """
        Apply importance decay to all memories.

        Returns:
            Number of memories updated.
        """
        if not self.config.decay_enabled:
            return 0

        rate = self.config.decay_rate
        floor = self.config.decay_floor

        # This is a potentially expensive operation if there are many memories.
        # Ideally we'd do this in the database with SQL, but SQLite math functions
        # might be limited or we want Python control.
        # Or we only decay memories accessed > X days ago.

        # Simple implementation: fetch all > floor, decay them, update if changed.
        # Optimization: Only process a batch or do it entirely in SQL.

        # Let's do a SQL-based update for efficiency if possible, but
        # LocalMemoryManager doesn't expose a raw execute.
        # Let's iterate for now (simplest, robust), but limit to 100 at a time maybe?
        # Or better: Add a `decay_all` method to storage layer?

        # For now, let's just implement the logic here iterating over ALL memories
        # which is fine for < 1000 memories.

        # Use snapshot-based iteration to avoid pagination issues during updates
        count = 0

        # Note: listing all memories (limit=10000) to avoid pagination drift when modifying them.
        # If dataset grows larger, we should implement a cursor-based approach or add list_memories_ids.
        memories = self.storage.list_memories(min_importance=floor + 0.001, limit=10000)

        for memory in memories:
            # Calculate simple linear decay since last update
            last_update = datetime.fromisoformat(memory.updated_at)
            # Ensure last_update is timezone-aware for subtraction
            if last_update.tzinfo is None:
                last_update = last_update.replace(tzinfo=UTC)
            hours_since = (datetime.now(UTC) - last_update).total_seconds() / 3600

            # If it's been less than 24h, skip to avoid over-decaying if called frequently
            if hours_since < 24:
                continue

            # Decay factor: rate * (days since) / 30
            # Linear decay
            months_passed = hours_since / (24 * 30)
            decay_amount = rate * months_passed

            if decay_amount < 0.001:
                continue

            new_importance = max(floor, memory.importance - decay_amount)

            if new_importance != memory.importance:
                self.storage.update_memory(
                    memory.id,
                    importance=new_importance,
                )
                count += 1

        return count

    # --- Embedding Methods ---

    async def async_recall(
        self,
        query: str,
        project_id: str | None = None,
        limit: int = 10,
        min_importance: float | None = None,
    ) -> list[Memory]:
        """
        Async version of recall for semantic search.

        Args:
            query: Search query
            project_id: Optional project filter
            limit: Maximum results
            min_importance: Minimum importance threshold

        Returns:
            List of matching memories
        """
        threshold = (
            min_importance if min_importance is not None else self.config.importance_threshold
        )

        if getattr(self.config, "semantic_search_enabled", False):
            try:
                results = await self.semantic_search.search(
                    query=query,
                    project_id=project_id,
                    top_k=limit,
                    min_importance=threshold,
                )
                memories = [r.memory for r in results]
            except Exception as e:
                logger.warning(f"Semantic search failed: {e}")
                memories = self.storage.search_memories(
                    query_text=query,
                    project_id=project_id,
                    limit=limit,
                )
                memories = [m for m in memories if m.importance >= threshold]
        else:
            memories = self.storage.search_memories(
                query_text=query,
                project_id=project_id,
                limit=limit,
            )
            memories = [m for m in memories if m.importance >= threshold]

        self._update_access_stats(memories)
        return memories[:limit]

    async def embed_memory(self, memory_id: str, force: bool = False) -> bool:
        """
        Generate embedding for a single memory.

        Args:
            memory_id: Memory ID to embed
            force: Force re-embedding even if exists

        Returns:
            True if embedded, False if skipped
        """
        memory = self.get_memory(memory_id)
        if not memory:
            return False

        return await self.semantic_search.embed_memory(
            memory_id=memory_id,
            content=memory.content,
            force=force,
        )

    async def rebuild_embeddings(
        self,
        project_id: str | None = None,
        force: bool = False,
    ) -> EmbedStats:
        """
        Rebuild embeddings for all memories.

        Args:
            project_id: Optional project filter
            force: Force re-embedding all memories

        Returns:
            Dict with statistics
        """
        if force:
            # Clear existing embeddings first
            self.semantic_search.clear_embeddings(project_id)

        return await self.semantic_search.embed_all_memories(
            project_id=project_id,
            force=force,
        )

    def get_embedding_stats(self, project_id: str | None = None) -> dict[str, Any]:
        """
        Get statistics about memory embeddings.

        Args:
            project_id: Optional project filter

        Returns:
            Dict with embedding statistics
        """
        return self.semantic_search.get_embedding_stats(project_id)
