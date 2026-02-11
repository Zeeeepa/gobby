from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from gobby.config.persistence import MemoryConfig
from gobby.memory.backends.storage_adapter import StorageAdapter
from gobby.memory.components.ingestion import IngestionService
from gobby.memory.components.search import SearchService
from gobby.memory.context import build_memory_context
from gobby.memory.mem0_client import Mem0Client, Mem0ConnectionError
from gobby.memory.neo4j_client import Neo4jClient
from gobby.memory.neo4j_client import Neo4jConnectionError as _Neo4jConnError
from gobby.memory.protocol import MemoryBackendProtocol, MemoryRecord
from gobby.search.embeddings import generate_embedding, generate_embeddings, is_embedding_available
from gobby.storage.database import DatabaseProtocol
from gobby.storage.memories import LocalMemoryManager, Memory
from gobby.storage.memory_embeddings import MemoryEmbeddingManager

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

        # Primary storage layer — always SQLite via LocalMemoryManager
        self.storage = LocalMemoryManager(db)

        # Backend for async protocol operations (always StorageAdapter)
        self._backend: MemoryBackendProtocol = StorageAdapter(self.storage)

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

        # Embedding manager for memory CRUD lifecycle
        self._embedding_mgr = MemoryEmbeddingManager(db)

        # Mem0 dual-mode: initialize client when mem0_url is configured
        if config.mem0_url:
            self._mem0_client: Mem0Client | None = Mem0Client(
                base_url=config.mem0_url,
                api_key=config.mem0_api_key,
            )
        else:
            self._mem0_client = None

        # Track background tasks to prevent GC and surface exceptions
        self._background_tasks: set[asyncio.Task[Any]] = set()

        # Neo4j knowledge graph: initialize client when neo4j_url is configured
        if config.neo4j_url:
            self._neo4j_client: Neo4jClient | None = Neo4jClient(
                url=config.neo4j_url,
                auth=config.neo4j_auth,
                database=config.neo4j_database,
            )
        else:
            self._neo4j_client = None

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

    @staticmethod
    def _record_to_memory(record: MemoryRecord) -> Memory:
        """Convert a MemoryRecord from the backend to a Memory for downstream compatibility."""
        return Memory(
            id=record.id,
            memory_type=record.memory_type,  # type: ignore[arg-type]  # MemoryRecord uses str, Memory uses Literal
            content=record.content,
            created_at=record.created_at.isoformat() if record.created_at else "",
            updated_at=record.updated_at.isoformat() if record.updated_at else "",
            project_id=record.project_id,
            source_type=record.source_type,  # type: ignore[arg-type]  # MemoryRecord uses str, Memory uses Literal
            source_session_id=record.source_session_id,
            importance=record.importance,
            access_count=record.access_count,
            last_accessed_at=(
                record.last_accessed_at.isoformat() if record.last_accessed_at else None
            ),
            tags=record.tags or [],
            media=None,  # Media handled separately via MemoryRecord
        )

    def _ensure_search_backend_fitted(self) -> None:
        """Ensure the search backend is fitted with current memories."""
        self._search_service.ensure_fitted()

    def mark_search_refit_needed(self) -> None:
        """Mark that the search backend needs to be refitted."""
        self._search_service.mark_refit_needed()

    def _store_embedding_sync(self, memory_id: str, content: str, project_id: str | None) -> None:
        """Generate and store an embedding for a memory (sync, non-blocking).

        Failures are logged but never propagated — CRUD operations must not
        be blocked by embedding generation errors.
        """
        if not is_embedding_available(model=self.config.embedding_model):
            return

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # We are in an event loop. Schedule as background task to avoid blocking/crashing.
            task = loop.create_task(self._store_embedding_async(memory_id, content, project_id))
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
            return

        try:
            embedding = asyncio.run(generate_embedding(content, model=self.config.embedding_model))

            text_hash = hashlib.sha256(content.encode()).hexdigest()
            self._embedding_mgr.store_embedding(
                memory_id=memory_id,
                project_id=project_id,
                embedding=embedding,
                embedding_model=self.config.embedding_model,
                text_hash=text_hash,
            )
        except Exception as e:
            logger.warning(f"Failed to generate embedding for memory {memory_id}: {e}")

    async def _store_embedding_async(
        self, memory_id: str, content: str, project_id: str | None
    ) -> None:
        """Generate and store an embedding for a memory (async, non-blocking)."""
        if not is_embedding_available(model=self.config.embedding_model):
            return

        try:
            embedding = await generate_embedding(content, model=self.config.embedding_model)
            text_hash = hashlib.sha256(content.encode()).hexdigest()
            self._embedding_mgr.store_embedding(
                memory_id=memory_id,
                project_id=project_id,
                embedding=embedding,
                embedding_model=self.config.embedding_model,
                text_hash=text_hash,
            )
        except Exception as e:
            logger.warning(f"Failed to generate embedding for memory {memory_id}: {e}")

    async def reindex_embeddings(self) -> dict[str, Any]:
        """Generate embeddings for all memories in batch.

        Returns:
            Dict with success status, total_memories, embeddings_generated.
        """
        if not is_embedding_available(model=self.config.embedding_model):
            return {
                "success": False,
                "error": "Embedding unavailable — no API key configured",
            }

        batch_size = 500
        total_memories = 0
        total_generated = 0
        offset = 0
        truncated = False

        while True:
            memories = self.storage.list_memories(limit=batch_size, offset=offset)
            if not memories:
                break

            total_memories += len(memories)
            if total_memories > 10000:
                truncated = True
                break

            texts = [m.content for m in memories]
            try:
                embeddings = await generate_embeddings(texts, model=self.config.embedding_model)
            except Exception as e:
                logger.error(f"Batch embedding generation failed at offset {offset}: {e}")
                return {"success": False, "error": str(e)}

            items = []
            for memory, embedding in zip(memories, embeddings, strict=True):
                items.append(
                    {
                        "memory_id": memory.id,
                        "project_id": memory.project_id,
                        "embedding": embedding,
                        "embedding_model": self.config.embedding_model,
                        "text_hash": hashlib.sha256(memory.content.encode()).hexdigest(),
                    }
                )

            total_generated += self._embedding_mgr.batch_store_embeddings(items)
            offset += batch_size

            if len(memories) < batch_size:
                break

        return {
            "success": True,
            "total_memories": total_memories,
            "embeddings_generated": total_generated,
            "truncated": truncated,
        }

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
        normalized_content = content.strip()
        if await self._backend.content_exists(normalized_content, project_id):
            existing_record = await self._backend.get_memory_by_content(
                normalized_content, project_id
            )
            if existing_record:
                logger.debug(f"Memory already exists: {existing_record.id}")
                return self._record_to_memory(existing_record)

        record = await self._backend.create(
            content=content,
            memory_type=memory_type,
            importance=importance,
            project_id=project_id,
            source_type=source_type,
            source_session_id=source_session_id,
            tags=tags,
        )
        memory = self._record_to_memory(record)

        # Mark search index for refit since we added new content
        self.mark_search_refit_needed()

        # Generate and store embedding (non-blocking)
        await self._store_embedding_async(memory.id, content, project_id)

        # Mem0 dual-mode: index in Mem0 after local storage
        await self._index_in_mem0(memory.id, content, project_id)

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
            search_mode: Search mode - "auto" (default), "tfidf", "openai", "hybrid", "text"
            tags_all: Memory must have ALL of these tags
            tags_any: Memory must have at least ONE of these tags
            tags_none: Memory must have NONE of these tags
        """
        threshold = (
            min_importance if min_importance is not None else self.config.importance_threshold
        )

        if query:
            # Mem0 dual-mode: try Mem0 search first if configured
            mem0_results = (
                self._search_mem0(query, project_id, limit) if self._mem0_client else None
            )

            if mem0_results is not None:
                memories = mem0_results
            else:
                memories = self._recall_with_search(
                    query=query,
                    project_id=project_id,
                    limit=limit,
                    min_importance=threshold,
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

    async def forget(self, memory_id: str) -> bool:
        """Forget a memory."""
        # Mem0 dual-mode: delete from Mem0 if memory has mem0_id
        if self._mem0_client:
            await self._delete_from_mem0(memory_id)

        result = self.storage.delete_memory(memory_id)
        if result:
            # Mark search index for refit since we removed content
            self.mark_search_refit_needed()
        return result

    async def aforget(self, memory_id: str) -> bool:
        """Forget a memory (async version)."""
        result = await self._backend.delete(memory_id)
        if result:
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

    async def alist_memories(
        self,
        project_id: str | None = None,
        memory_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Memory]:
        """List memories via backend (async, routes through backend)."""
        records = await self._backend.list_memories(
            project_id=project_id,
            memory_type=memory_type,
            limit=limit,
            offset=offset,
        )
        return [self._record_to_memory(r) for r in records]

    def content_exists(self, content: str, project_id: str | None = None) -> bool:
        """Check if a memory with identical content already exists."""
        return self.storage.content_exists(content, project_id)

    async def acontent_exists(self, content: str, project_id: str | None = None) -> bool:
        """Check if a memory with identical content already exists (async, routes through backend)."""
        return await self._backend.content_exists(content, project_id)

    def get_memory(self, memory_id: str) -> Memory | None:
        """Get a specific memory by ID."""
        try:
            return self.storage.get_memory(memory_id)
        except ValueError:
            return None

    async def aget_memory(self, memory_id: str) -> Memory | None:
        """Get a specific memory by ID (async, routes through backend)."""
        record = await self._backend.get(memory_id)
        if record:
            return self._record_to_memory(record)
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
            self._store_embedding_sync(memory_id, content, result.project_id)

        return result

    async def aupdate_memory(
        self,
        memory_id: str,
        content: str | None = None,
        importance: float | None = None,
        tags: list[str] | None = None,
    ) -> Memory:
        """Update an existing memory (async, routes through backend)."""
        record = await self._backend.update(
            memory_id=memory_id,
            content=content,
            importance=importance,
            tags=tags,
        )
        memory = self._record_to_memory(record)
        if content is not None:
            self.mark_search_refit_needed()
            await self._store_embedding_async(memory_id, content, memory.project_id)
        return memory

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

    # =========================================================================
    # Neo4j knowledge graph
    # =========================================================================

    async def get_entity_graph(self, limit: int = 500) -> dict[str, Any] | None:
        """Get the Neo4j entity graph for visualization.

        Returns None if Neo4j is not configured or unreachable.
        """
        if not self._neo4j_client:
            return None
        try:
            return await self._neo4j_client.get_entity_graph(limit=limit)
        except _Neo4jConnError as e:
            logger.warning(f"Neo4j unreachable: {e}")
            return None
        except Exception as e:
            logger.warning(f"Neo4j query failed: {e}")
            return None

    async def get_entity_neighbors(self, name: str) -> dict[str, Any] | None:
        """Get neighbors for a single Neo4j entity.

        Returns None if Neo4j is not configured or unreachable.
        """
        if not self._neo4j_client:
            return None
        try:
            return await self._neo4j_client.get_entity_neighbors(name)
        except _Neo4jConnError as e:
            logger.warning(f"Neo4j unreachable: {e}")
            return None
        except Exception as e:
            logger.warning(f"Neo4j query failed: {e}")
            return None

    # =========================================================================
    # Mem0 dual-mode helpers
    # =========================================================================

    async def _index_in_mem0(self, memory_id: str, content: str, project_id: str | None) -> None:
        """Index a memory in Mem0 after local storage. Non-blocking on failure."""
        if not self._mem0_client:
            return

        try:
            result = await self._mem0_client.create(
                content=content,
                project_id=project_id,
                metadata={"gobby_id": memory_id},
            )
            # Extract mem0_id from response and store it
            mem0_id = self._extract_mem0_id(result)
            if mem0_id:
                self.db.execute(
                    "UPDATE memories SET mem0_id = ? WHERE id = ?",
                    (mem0_id, memory_id),
                )
        except Mem0ConnectionError as e:
            logger.warning(f"Mem0 unreachable during index for {memory_id}: {e}")
        except Exception as e:
            logger.warning(f"Failed to index memory {memory_id} in Mem0: {e}")

    @staticmethod
    def _extract_mem0_id(response: Any) -> str | None:
        """Extract the mem0 memory ID from a create response."""
        if isinstance(response, dict):
            results = response.get("results", [])
            if results and isinstance(results[0], dict):
                return results[0].get("id")
        return None

    async def _delete_from_mem0(self, memory_id: str) -> None:
        """Delete a memory from Mem0 if it has a mem0_id. Non-blocking on failure."""
        memory = self.get_memory(memory_id)
        if not memory or not memory.mem0_id:
            return

        try:
            await self._mem0_client.delete(memory.mem0_id)  # type: ignore[union-attr]
        except Mem0ConnectionError as e:
            logger.warning(f"Mem0 unreachable during delete for {memory_id}: {e}")
        except Exception as e:
            logger.warning(f"Failed to delete memory {memory_id} from Mem0: {e}")

    def _search_mem0(self, query: str, project_id: str | None, limit: int) -> list[Memory] | None:
        """Search Mem0 and return local memories enriched by results.

        Returns None if Mem0 is unavailable (caller should fall back to local search).

        Warning: This method blocks the calling thread. When called from an
        async context, it spawns a thread pool to run the async Mem0 search.
        """
        if self._mem0_client is None:
            raise RuntimeError("Mem0 client is not initialized")

        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        try:
            if loop and loop.is_running():
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    result = pool.submit(
                        asyncio.run,
                        self._mem0_client.search(query=query, project_id=project_id, limit=limit),
                    ).result()
            else:
                result = asyncio.run(
                    self._mem0_client.search(query=query, project_id=project_id, limit=limit)
                )
        except Mem0ConnectionError as e:
            logger.warning(f"Mem0 unreachable during search, falling back to local: {e}")
            return None
        except Exception as e:
            logger.warning(f"Mem0 search failed, falling back to local: {e}")
            return None

        # Enrich mem0 results with local memory data
        memories: list[Memory] = []
        for item in result.get("results", []):
            gobby_id = (item.get("metadata") or {}).get("gobby_id")
            if gobby_id:
                local = self.get_memory(gobby_id)
                if local:
                    memories.append(local)

        return memories

    async def _lazy_sync(self) -> int:
        """Sync memories that have mem0_id IS NULL to Mem0.

        Returns the number of memories successfully synced.
        """
        if not self._mem0_client:
            return 0

        batch_size = 100
        synced = 0
        offset = 0

        while True:
            rows = self.db.fetchall(
                "SELECT id, content, project_id FROM memories WHERE mem0_id IS NULL LIMIT ? OFFSET ?",
                (batch_size, offset),
            )
            if not rows:
                break

            for row in rows:
                try:
                    result = await self._mem0_client.create(
                        content=row["content"],
                        project_id=row["project_id"],
                        metadata={"gobby_id": row["id"]},
                    )
                    mem0_id = self._extract_mem0_id(result)
                    if mem0_id:
                        self.db.execute(
                            "UPDATE memories SET mem0_id = ? WHERE id = ?",
                            (mem0_id, row["id"]),
                        )
                        synced += 1
                except Mem0ConnectionError as e:
                    logger.warning(f"Mem0 unreachable during lazy sync for {row['id']}: {e}")
                    return synced  # Stop on connection errors
                except Exception as e:
                    logger.warning(f"Failed to sync memory {row['id']} to Mem0: {e}")

            offset += batch_size

        return synced

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
