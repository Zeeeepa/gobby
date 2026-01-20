"""SQLite memory backend.

This backend wraps the existing LocalMemoryManager to provide a
MemoryBackendProtocol-compliant interface for SQLite storage.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from gobby.memory.protocol import (
    MediaAttachment,
    MemoryCapability,
    MemoryQuery,
    MemoryRecord,
)
from gobby.storage.memories import LocalMemoryManager

if TYPE_CHECKING:
    from gobby.storage.database import DatabaseProtocol


class SQLiteBackend:
    """SQLite-based memory backend.

    Wraps LocalMemoryManager to provide MemoryBackendProtocol interface.
    Supports full CRUD operations and text-based search.
    """

    def __init__(self, database: DatabaseProtocol):
        """Initialize with a database connection.

        Args:
            database: Database protocol instance for SQLite operations
        """
        self._storage = LocalMemoryManager(database)
        self._db = database

    def capabilities(self) -> set[MemoryCapability]:
        """Return supported capabilities."""
        return {
            # Basic CRUD
            MemoryCapability.CREATE,
            MemoryCapability.READ,
            MemoryCapability.UPDATE,
            MemoryCapability.DELETE,
            # Search
            MemoryCapability.SEARCH_TEXT,
            MemoryCapability.SEARCH,
            # Advanced
            MemoryCapability.TAGS,
            MemoryCapability.IMPORTANCE,
            MemoryCapability.LIST,
            # MCP-aligned
            MemoryCapability.REMEMBER,
            MemoryCapability.RECALL,
            MemoryCapability.FORGET,
        }

    async def create(
        self,
        content: str,
        memory_type: str = "fact",
        importance: float = 0.5,
        project_id: str | None = None,
        user_id: str | None = None,
        tags: list[str] | None = None,
        source_type: str | None = None,
        source_session_id: str | None = None,
        media: list[MediaAttachment] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryRecord:
        """Create a new memory.

        Args:
            content: The memory content text
            memory_type: Type of memory (fact, preference, etc.)
            importance: Importance score (0.0 to 1.0)
            project_id: Associated project ID
            user_id: Associated user ID (stored in metadata for SQLite)
            tags: List of tags
            source_type: Origin of memory
            source_session_id: Session that created the memory
            media: List of media attachments (stored in metadata)
            metadata: Additional metadata

        Returns:
            The created MemoryRecord
        """
        # Serialize media list to JSON for storage
        media_json: str | None = None
        if media:
            media_json = json.dumps(
                [
                    {
                        "media_type": m.media_type,
                        "content_path": m.content_path,
                        "mime_type": m.mime_type,
                        "description": m.description,
                        "description_model": m.description_model,
                        "metadata": m.metadata,
                    }
                    for m in media
                ]
            )

        # Create via storage layer (wrap sync call to avoid blocking event loop)
        memory = await asyncio.to_thread(
            self._storage.create_memory,
            content=content,
            memory_type=memory_type,
            importance=importance,
            project_id=project_id,
            source_type=source_type or "user",
            source_session_id=source_session_id,
            tags=tags,
            media=media_json,
        )

        # Convert to MemoryRecord
        return self._memory_to_record(memory, user_id=user_id, metadata=metadata)

    async def get(self, memory_id: str) -> MemoryRecord | None:
        """Retrieve a memory by ID.

        Args:
            memory_id: The memory ID to retrieve

        Returns:
            The MemoryRecord if found, None otherwise
        """
        try:
            memory = await asyncio.to_thread(self._storage.get_memory, memory_id)
            return self._memory_to_record(memory)
        except ValueError:
            # Storage layer raises ValueError when memory not found
            return None

    async def update(
        self,
        memory_id: str,
        content: str | None = None,
        importance: float | None = None,
        tags: list[str] | None = None,
    ) -> MemoryRecord:
        """Update an existing memory.

        Args:
            memory_id: The memory ID to update
            content: New content (optional)
            importance: New importance score (optional)
            tags: New tags (optional)

        Returns:
            The updated MemoryRecord

        Raises:
            ValueError: If memory not found
        """
        memory = await asyncio.to_thread(
            self._storage.update_memory,
            memory_id=memory_id,
            content=content,
            importance=importance,
            tags=tags,
        )
        if memory is None:
            raise ValueError(f"Memory not found: {memory_id}")
        return self._memory_to_record(memory)

    async def delete(self, memory_id: str) -> bool:
        """Delete a memory.

        Args:
            memory_id: The memory ID to delete

        Returns:
            True if deleted, False if not found
        """
        return await asyncio.to_thread(self._storage.delete_memory, memory_id)

    async def search(self, query: MemoryQuery) -> list[MemoryRecord]:
        """Search for memories.

        Args:
            query: Search parameters

        Returns:
            List of matching MemoryRecords
        """
        # Use storage layer's search (wrap sync call to avoid blocking event loop)
        memories = await asyncio.to_thread(
            self._storage.search_memories,
            query_text=query.text,
            project_id=query.project_id,
            limit=query.limit,
            tags_all=query.tags_all,
            tags_any=query.tags_any,
            tags_none=query.tags_none,
        )

        # Apply additional filters not supported by storage layer
        if query.min_importance is not None:
            memories = [m for m in memories if m.importance >= query.min_importance]
        if query.memory_type is not None:
            memories = [m for m in memories if m.memory_type == query.memory_type]

        return [self._memory_to_record(m) for m in memories]

    async def list_memories(
        self,
        project_id: str | None = None,
        user_id: str | None = None,
        memory_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MemoryRecord]:
        """List memories with optional filtering.

        Args:
            project_id: Filter by project ID
            user_id: Filter by user ID (not supported in SQLite, ignored)
            memory_type: Filter by memory type
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of MemoryRecords
        """
        memories = await asyncio.to_thread(
            self._storage.list_memories,
            project_id=project_id,
            memory_type=memory_type,
            limit=limit,
            offset=offset,
        )

        return [self._memory_to_record(m) for m in memories]

    def _memory_to_record(
        self,
        memory: Any,
        user_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryRecord:
        """Convert a Memory object to MemoryRecord.

        Args:
            memory: Memory object from storage layer
            user_id: Optional user ID to include
            metadata: Optional additional metadata

        Returns:
            MemoryRecord instance
        """
        # Parse datetime strings
        created_at = (
            datetime.fromisoformat(memory.created_at) if memory.created_at else datetime.now(UTC)
        )
        updated_at = datetime.fromisoformat(memory.updated_at) if memory.updated_at else None
        last_accessed = (
            datetime.fromisoformat(memory.last_accessed_at) if memory.last_accessed_at else None
        )

        # Deserialize media from JSON string
        media_list: list[MediaAttachment] = []
        if memory.media:
            try:
                media_data = json.loads(memory.media)
                media_list = [
                    MediaAttachment(
                        media_type=m.get("media_type", "unknown"),
                        content_path=m.get("content_path", ""),
                        mime_type=m.get("mime_type", "application/octet-stream"),
                        description=m.get("description"),
                        description_model=m.get("description_model"),
                        metadata=m.get("metadata"),
                    )
                    for m in media_data
                ]
            except (json.JSONDecodeError, TypeError):
                # If media is malformed, log and continue with empty list
                media_list = []

        return MemoryRecord(
            id=memory.id,
            content=memory.content,
            created_at=created_at,
            memory_type=memory.memory_type,
            updated_at=updated_at,
            project_id=memory.project_id,
            user_id=user_id,
            importance=memory.importance,
            tags=memory.tags or [],
            source_type=memory.source_type,
            source_session_id=memory.source_session_id,
            access_count=memory.access_count,
            last_accessed_at=last_accessed,
            media=media_list,
            metadata=metadata or {},
        )
