from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from gobby.config.persistence import MemoryConfig
from gobby.memory.backends import get_backend
from gobby.memory.components.ingestion import IngestionService
from gobby.memory.components.search import SearchService
from gobby.memory.context import build_memory_context
from gobby.memory.protocol import MemoryBackendProtocol
from gobby.storage.database import DatabaseProtocol
from gobby.storage.memories import LocalMemoryManager, Memory

if TYPE_CHECKING:
    from gobby.llm.service import LLMService

logger = logging.getLogger(__name__)


class MemoryManager:
    """
    High-level manager for memory operations.
    Handles storage, ranking, decay, and business logic.
    """

    def __init__(
        self,
        db: DatabaseProtocol,
        config: MemoryConfig,
        llm_service: LLMService | None = None,
    ):
        self.db = db
        self.config = config
        self._llm_service = llm_service

        # Initialize storage backend based on config
        # Note: SQLiteBackend wraps LocalMemoryManager internally
        backend_type = getattr(config, "backend", "sqlite")
        self._backend: MemoryBackendProtocol = get_backend(backend_type, database=db)

        # Keep storage reference for backward compatibility with sync methods
        # The SQLiteBackend uses LocalMemoryManager internally
        self.storage = LocalMemoryManager(db)

        # Initialize extracted components
        self._search_service = SearchService(
            storage=self.storage,
            config=config,
            db=db,
        )

        self._ingestion_service = IngestionService(
            storage=self.storage,
            backend=self._backend,
            llm_service=llm_service,
        )

    @property
    def llm_service(self) -> LLMService | None:
        """Get the LLM service for image description."""
        return self._ingestion_service.llm_service

    @llm_service.setter
    def llm_service(self, service: LLMService | None) -> None:
        """Set the LLM service for image description."""
        self._llm_service = service
        self._ingestion_service.llm_service = service

    @property
    def search_backend(self) -> Any:
        """
        Lazy-init search backend based on configuration.

        The backend type is determined by config.search_backend:
        - "tfidf" (default): Zero-dependency TF-IDF search
        - "text": Simple text substring matching
        """
        return self._search_service.backend

    def _ensure_search_backend_fitted(self) -> None:
        """Ensure the search backend is fitted with current memories."""
        self._search_service.ensure_fitted()

    def mark_search_refit_needed(self) -> None:
        """Mark that the search backend needs to be refitted."""
        self._search_service.mark_refit_needed()

    def reindex_search(self) -> dict[str, Any]:
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
        return self._search_service.reindex()

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
        # Check for existing memory with same content to avoid duplicates.
        # The storage layer also checks via content-hash ID, but this provides
        # an additional safeguard against race conditions and project_id mismatches.
        normalized_content = content.strip()
        if self.storage.content_exists(normalized_content, project_id):
            # Return existing memory by computing the same content-derived ID
            # that the storage layer uses, avoiding reliance on search ordering
            existing_memory = self.storage.get_memory_by_content(normalized_content, project_id)
            if existing_memory:
                logger.debug(f"Memory already exists: {existing_memory.id}")
                return existing_memory

        memory = self.storage.create_memory(
            content=content,
            memory_type=memory_type,
            importance=importance,
            project_id=project_id,
            source_type=source_type,
            source_session_id=source_session_id,
            tags=tags,
        )

        # Mark search index for refit since we added new content
        self.mark_search_refit_needed()

        # Auto cross-reference if enabled
        if getattr(self.config, "auto_crossref", False):
            try:
                await self._search_service.create_crossrefs(memory)
            except Exception as e:
                # Don't fail the remember if crossref fails
                logger.warning(f"Auto-crossref failed for {memory.id}: {e}")

        return memory

    async def remember_with_image(
        self,
        image_path: str,
        context: str | None = None,
        memory_type: str = "fact",
        importance: float = 0.5,
        project_id: str | None = None,
        source_type: str = "user",
        source_session_id: str | None = None,
        tags: list[str] | None = None,
    ) -> Memory:
        """
        Store a memory with an image attachment.

        Uses the configured LLM provider to generate a description of the image,
        then stores the memory with the description as content and the image
        as a media attachment.

        Args:
            image_path: Path to the image file
            context: Optional context to guide the image description
            memory_type: Type of memory (fact, preference, etc)
            importance: 0.0-1.0 importance score
            project_id: Optional project context
            source_type: Origin of memory
            source_session_id: Origin session
            tags: Optional tags

        Returns:
            The created Memory object

        Raises:
            ValueError: If LLM service is not configured or image not found
        """
        memory = await self._ingestion_service.remember_with_image(
            image_path=image_path,
            context=context,
            memory_type=memory_type,
            importance=importance,
            project_id=project_id,
            source_type=source_type,
            source_session_id=source_session_id,
            tags=tags,
        )
        # Mark search index for refit
        self.mark_search_refit_needed()
        return memory

    async def remember_screenshot(
        self,
        screenshot_bytes: bytes,
        context: str | None = None,
        memory_type: str = "observation",
        importance: float = 0.5,
        project_id: str | None = None,
        source_type: str = "user",
        source_session_id: str | None = None,
        tags: list[str] | None = None,
    ) -> Memory:
        """
        Store a memory from raw screenshot bytes.

        Saves the screenshot to .gobby/resources/ with a timestamp-based filename,
        then delegates to remember_with_image() for LLM description and storage.

        Args:
            screenshot_bytes: Raw PNG screenshot bytes (from Playwright/Puppeteer)
            context: Optional context to guide the image description
            memory_type: Type of memory (default: "observation")
            importance: 0.0-1.0 importance score
            project_id: Optional project context
            source_type: Origin of memory
            source_session_id: Origin session
            tags: Optional tags

        Returns:
            The created Memory object

        Raises:
            ValueError: If LLM service is not configured or screenshot bytes are empty
        """
        memory = await self._ingestion_service.remember_screenshot(
            screenshot_bytes=screenshot_bytes,
            context=context,
            memory_type=memory_type,
            importance=importance,
            project_id=project_id,
            source_type=source_type,
            source_session_id=source_session_id,
            tags=tags,
        )
        # Mark search index for refit
        self.mark_search_refit_needed()
        return memory

    async def _create_crossrefs(
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
        return await self._search_service.create_crossrefs(
            memory=memory,
            threshold=threshold,
            max_links=max_links,
        )

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
        return await self._search_service.get_related(
            memory_id=memory_id,
            limit=limit,
            min_similarity=min_similarity,
        )

    def recall(
        self,
        query: str | None = None,
        project_id: str | None = None,
        limit: int = 10,
        min_importance: float | None = None,
        memory_type: str | None = None,
        use_semantic: bool | None = None,
        search_mode: str | None = None,
        tags_all: list[str] | None = None,
        tags_any: list[str] | None = None,
        tags_none: list[str] | None = None,
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
            tags_all: Memory must have ALL of these tags
            tags_any: Memory must have at least ONE of these tags
            tags_none: Memory must have NONE of these tags
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
                tags_all=tags_all,
                tags_any=tags_any,
                tags_none=tags_none,
            )
        else:
            # Just get top memories
            memories = self.storage.list_memories(
                project_id=project_id,
                memory_type=memory_type,
                min_importance=threshold,
                limit=limit,
                tags_all=tags_all,
                tags_any=tags_any,
                tags_none=tags_none,
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
        tags_all: list[str] | None = None,
        tags_any: list[str] | None = None,
        tags_none: list[str] | None = None,
    ) -> list[Memory]:
        """
        Perform search using the configured search backend.

        Uses the new search backend by default (TF-IDF),
        falling back to legacy semantic search if configured.
        """
        # Legacy compatibility: use_semantic is deprecated
        if use_semantic is not None:
            logger.warning("use_semantic argument is deprecated and ignored")

        return self._search_service.search(
            query=query,
            project_id=project_id,
            limit=limit,
            min_importance=min_importance,
            search_mode=search_mode,
            tags_all=tags_all,
            tags_any=tags_any,
            tags_none=tags_none,
        )

    def recall_as_context(
        self,
        project_id: str | None = None,
        limit: int = 10,
        min_importance: float | None = None,
    ) -> str:
        """
        Retrieve memories and format them as context for LLM prompts.

        Convenience method that combines recall() with build_memory_context().

        Args:
            project_id: Filter by project
            limit: Maximum memories to return
            min_importance: Minimum importance threshold

        Returns:
            Formatted markdown string wrapped in <project-memory> tags,
            or empty string if no memories found
        """
        memories = self.recall(
            project_id=project_id,
            limit=limit,
            min_importance=min_importance,
        )

        return build_memory_context(memories)

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
        result = self.storage.delete_memory(memory_id)
        if result:
            # Mark search index for refit since we removed content
            self.mark_search_refit_needed()
        return result

    def list_memories(
        self,
        project_id: str | None = None,
        memory_type: str | None = None,
        min_importance: float | None = None,
        limit: int = 50,
        offset: int = 0,
        tags_all: list[str] | None = None,
        tags_any: list[str] | None = None,
        tags_none: list[str] | None = None,
    ) -> list[Memory]:
        """
        List memories with optional filtering.

        Args:
            project_id: Filter by project ID (or None for global)
            memory_type: Filter by memory type
            min_importance: Minimum importance threshold
            limit: Maximum results
            offset: Offset for pagination
            tags_all: Memory must have ALL of these tags
            tags_any: Memory must have at least ONE of these tags
            tags_none: Memory must have NONE of these tags
        """
        return self.storage.list_memories(
            project_id=project_id,
            memory_type=memory_type,
            min_importance=min_importance,
            limit=limit,
            offset=offset,
            tags_all=tags_all,
            tags_any=tags_any,
            tags_none=tags_none,
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

    def find_by_prefix(self, prefix: str, limit: int = 5) -> list[Memory]:
        """
        Find memories whose IDs start with the given prefix.

        Used for resolving short ID references (e.g., "abc123" -> full UUID).

        Args:
            prefix: ID prefix to search for
            limit: Maximum number of results

        Returns:
            List of Memory objects with matching ID prefixes
        """
        rows = self.db.fetchall(
            "SELECT * FROM memories WHERE id LIKE ? LIMIT ?",
            (f"{prefix}%", limit),
        )
        return [Memory.from_row(row) for row in rows]

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
        result = self.storage.update_memory(
            memory_id=memory_id,
            content=content,
            importance=importance,
            tags=tags,
        )

        # Mark search index for refit if content changed
        if content is not None:
            self.mark_search_refit_needed()

        return result

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

    def export_markdown(
        self,
        project_id: str | None = None,
        include_metadata: bool = True,
        include_stats: bool = True,
    ) -> str:
        """
        Export memories as a formatted markdown document.

        Creates a human-readable markdown export of memories, suitable for
        backup, documentation, or sharing.

        Args:
            project_id: Filter by project ID (None for all memories)
            include_metadata: Include memory metadata (type, importance, tags)
            include_stats: Include summary statistics at the top

        Returns:
            Formatted markdown string with all memories

        Example output:
            # Memory Export

            **Exported:** 2026-01-19 12:34:56 UTC
            **Total memories:** 42

            ---

            ## Memory: abc123

            User prefers dark mode for all applications.

            - **Type:** preference
            - **Importance:** 0.8
            - **Tags:** ui, settings
            - **Created:** 2026-01-15 10:00:00
        """
        memories = self.storage.list_memories(project_id=project_id, limit=10000)

        lines: list[str] = []

        # Header
        lines.append("# Memory Export")
        lines.append("")

        # Stats section
        if include_stats:
            now = datetime.now(UTC)
            lines.append(f"**Exported:** {now.strftime('%Y-%m-%d %H:%M:%S')} UTC")
            lines.append(f"**Total memories:** {len(memories)}")
            if project_id:
                lines.append(f"**Project:** {project_id}")

            # Type breakdown
            if memories:
                by_type: dict[str, int] = {}
                for m in memories:
                    by_type[m.memory_type] = by_type.get(m.memory_type, 0) + 1
                type_str = ", ".join(f"{k}: {v}" for k, v in sorted(by_type.items()))
                lines.append(f"**By type:** {type_str}")

            lines.append("")
            lines.append("---")
            lines.append("")

        # Individual memories
        for memory in memories:
            # Memory header with short ID
            short_id = memory.id[:8] if len(memory.id) > 8 else memory.id
            lines.append(f"## Memory: {short_id}")
            lines.append("")

            # Content
            lines.append(memory.content)
            lines.append("")

            # Metadata
            if include_metadata:
                lines.append(f"- **Type:** {memory.memory_type}")
                lines.append(f"- **Importance:** {memory.importance}")

                if memory.tags:
                    tags_str = ", ".join(memory.tags)
                    lines.append(f"- **Tags:** {tags_str}")

                if memory.source_type:
                    lines.append(f"- **Source:** {memory.source_type}")

                # Parse and format created_at
                try:
                    created = datetime.fromisoformat(memory.created_at)
                    created_str = created.strftime("%Y-%m-%d %H:%M:%S")
                except (ValueError, TypeError):
                    created_str = memory.created_at
                lines.append(f"- **Created:** {created_str}")

                if memory.access_count > 0:
                    lines.append(f"- **Accessed:** {memory.access_count} times")

                lines.append("")

            lines.append("---")
            lines.append("")

        return "\n".join(lines)
