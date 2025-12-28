import logging
from datetime import UTC, datetime

from gobby.config.app import MemoryConfig
from gobby.storage.database import LocalDatabase
from gobby.storage.memories import LocalMemoryManager, Memory

logger = logging.getLogger(__name__)


class MemoryManager:
    """
    High-level manager for memory operations.
    Handles storage, ranking, decay, and business logic.
    """

    def __init__(self, db: LocalDatabase, config: MemoryConfig):
        self.storage = LocalMemoryManager(db)
        self.config = config

    def remember(
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

        return self.storage.create_memory(
            content=content,
            memory_type=memory_type,
            importance=importance,
            project_id=project_id,
            source_type=source_type,
            source_session_id=source_session_id,
            tags=tags,
        )

    def recall(
        self,
        query: str | None = None,
        project_id: str | None = None,
        limit: int = 10,
        min_importance: float | None = None,
        memory_type: str | None = None,
    ) -> list[Memory]:
        """
        Retrieve memories.

        If query is provided, performs search/ranking.
        If no query, returns top important memories.
        """
        threshold = (
            min_importance if min_importance is not None else self.config.importance_threshold
        )

        if query:
            # TODO: Add semantic search when embeddings are implemented
            # For now, use text search
            memories = self.storage.search_memories(
                query_text=query,
                project_id=project_id,
                limit=limit * 2,  # Fetch more for re-ranking if needed
            )
        else:
            # Just get top memories
            memories = self.storage.list_memories(
                project_id=project_id,
                memory_type=memory_type,
                min_importance=threshold,
                limit=limit,
            )

        # Apply decay logic on retrieval?
        # Or filtering based on effective importance?
        # For now, basic list is fine.

        # Filter by threshold if search didn't (search just orders by match+importance)
        if query:
            memories = [m for m in memories if m.importance >= threshold]
            memories = memories[:limit]

        # Update access stats for retrieved memories
        self._update_access_stats(memories)

        return memories

    def _update_access_stats(self, memories: list[Memory]) -> None:
        """Update access count and time for memories."""
        # This could be async or batched in future
        # For now, simple synchronous update (careful of perf)
        # Maybe only update if it hasn't been updated recently?
        # Or just do it. SQLite is fast enough for single-user CLI.
        pass  # TODO: Implement efficient access tracking

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

        count = 0
        limit = 500
        offset = 0

        while True:
            # Get next batch
            memories = self.storage.list_memories(
                min_importance=floor + 0.001,  # Only decay those above floor
                limit=limit,
                offset=offset,
            )

            if not memories:
                break

            for memory in memories:
                # Calculate simple linear decay since last update?
                # Or just apply the rate once per call (assuming called monthly)?
                # The config says "decay_rate per month".
                # We need to know when it was last decayed.
                # `updated_at` tells us last update.

                last_update = datetime.fromisoformat(memory.updated_at)
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

            offset += limit

        return count
