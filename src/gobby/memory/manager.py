import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from gobby.config.app import MemoryConfig
from gobby.storage.database import LocalDatabase
from gobby.storage.memories import LocalMemoryManager, Memory

if TYPE_CHECKING:
    from gobby.memory.semantic_search import SemanticMemorySearch

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
    ):
        self.db = db
        self.storage = LocalMemoryManager(db)
        self.config = config
        self._openai_api_key = openai_api_key
        self._semantic_search: "SemanticMemorySearch | None" = None

    @property
    def semantic_search(self) -> "SemanticMemorySearch":
        """Lazy-init semantic search to avoid import cycles."""
        if self._semantic_search is None:
            from gobby.memory.semantic_search import SemanticMemorySearch

            self._semantic_search = SemanticMemorySearch(
                db=self.db,
                openai_api_key=self._openai_api_key,
            )
        return self._semantic_search

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
            use_semantic: Use semantic search (default: True if config.semantic_search_enabled)
        """
        threshold = (
            min_importance if min_importance is not None else self.config.importance_threshold
        )

        # Determine if we should use semantic search
        should_use_semantic = use_semantic
        if should_use_semantic is None:
            should_use_semantic = getattr(self.config, "semantic_search_enabled", False)

        if query:
            if should_use_semantic:
                # Use semantic search
                memories = self._recall_semantic(
                    query=query,
                    project_id=project_id,
                    limit=limit,
                    min_importance=threshold,
                )
            else:
                # Fall back to text search
                memories = self.storage.search_memories(
                    query_text=query,
                    project_id=project_id,
                    limit=limit * 2,
                )
                # Filter by threshold
                memories = [m for m in memories if m.importance >= threshold]
                memories = memories[:limit]
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
                loop = asyncio.get_running_loop()
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

    def get_stats(self, project_id: str | None = None) -> dict:
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
    ) -> dict:
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

    def get_embedding_stats(self, project_id: str | None = None) -> dict:
        """
        Get statistics about memory embeddings.

        Args:
            project_id: Optional project filter

        Returns:
            Dict with embedding statistics
        """
        return self.semantic_search.get_embedding_stats(project_id)
