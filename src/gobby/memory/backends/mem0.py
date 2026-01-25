"""Mem0 memory backend integration.

This backend wraps the Mem0 AI memory service to provide a
MemoryBackendProtocol-compliant interface. Mem0 offers semantic
search and automatic memory organization.

Requires: pip install mem0ai

Example:
    from gobby.memory.backends import get_backend

    backend = get_backend("mem0", api_key="your-mem0-api-key")
    record = await backend.create("User prefers dark mode")
"""

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from gobby.memory.protocol import (
    MediaAttachment,
    MemoryCapability,
    MemoryQuery,
    MemoryRecord,
)

if TYPE_CHECKING:
    from mem0 import MemoryClient


class Mem0Backend:
    """Mem0-based memory backend.

    Wraps the Mem0 MemoryClient to provide MemoryBackendProtocol interface.
    Supports semantic search and automatic memory organization.

    Args:
        api_key: Mem0 API key for authentication
        user_id: Default user ID for memories (optional)
        org_id: Organization ID for multi-tenant use (optional)
        **kwargs: Additional configuration passed to MemoryClient
    """

    def __init__(
        self,
        api_key: str,
        user_id: str | None = None,
        org_id: str | None = None,
        **kwargs: Any,
    ):
        """Initialize the Mem0 backend.

        Args:
            api_key: Mem0 API key
            user_id: Default user ID for operations
            org_id: Organization ID
            **kwargs: Additional MemoryClient configuration
        """
        # Lazy import to avoid requiring mem0ai when not used
        try:
            from mem0 import MemoryClient
        except ImportError as e:
            raise ImportError(
                "Mem0 backend requires 'mem0ai' package. Install it with: pip install gobby[mem0]"
            ) from e

        self._client: MemoryClient = MemoryClient(api_key=api_key, **kwargs)
        self._default_user_id = user_id
        self._org_id = org_id

    def capabilities(self) -> set[MemoryCapability]:
        """Return supported capabilities.

        Mem0 supports semantic search and basic CRUD operations.
        """
        return {
            # Basic CRUD
            MemoryCapability.CREATE,
            MemoryCapability.READ,
            MemoryCapability.UPDATE,
            MemoryCapability.DELETE,
            # Search
            MemoryCapability.SEARCH_SEMANTIC,
            MemoryCapability.SEARCH,
            # Advanced
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
        """Create a new memory in Mem0.

        Args:
            content: The memory content text
            memory_type: Type of memory (stored in metadata)
            importance: Importance score (stored in metadata)
            project_id: Associated project ID
            user_id: User ID (uses default if not provided)
            tags: List of tags (stored in metadata)
            source_type: Origin of memory
            source_session_id: Session that created the memory
            media: List of media attachments (stored in metadata)
            metadata: Additional metadata

        Returns:
            The created MemoryRecord
        """
        effective_user_id = user_id or self._default_user_id or "default"

        # Build metadata for Mem0
        mem0_metadata: dict[str, Any] = {
            "memory_type": memory_type,
            "importance": importance,
            "source_type": source_type,
            "source_session_id": source_session_id,
            **(metadata or {}),
        }
        if project_id:
            mem0_metadata["project_id"] = project_id
        if tags:
            mem0_metadata["tags"] = tags
        if media:
            # Serialize media attachments
            mem0_metadata["media"] = [
                {
                    "media_type": m.media_type,
                    "content_path": m.content_path,
                    "mime_type": m.mime_type,
                    "description": m.description,
                }
                for m in media
            ]

        # Mem0 add() expects messages in OpenAI chat format
        messages = [{"role": "user", "content": content}]

        # Add memory via Mem0 API (run in thread to avoid blocking event loop)
        result = await asyncio.to_thread(
            self._client.add,
            messages=messages,
            user_id=effective_user_id,
            metadata=mem0_metadata,
        )

        # Extract memory ID from result
        # Mem0 returns {"results": [{"id": "...", "memory": "...", ...}]}
        if result and "results" in result and len(result["results"]) > 0:
            mem0_memory = result["results"][0]
            return self._mem0_to_record(mem0_memory)

        # Fallback: create a synthetic record
        return MemoryRecord(
            id=result.get("id", "unknown"),
            content=content,
            created_at=datetime.now(UTC),
            memory_type=memory_type,
            importance=importance,
            project_id=project_id,
            user_id=effective_user_id,
            tags=tags or [],
            source_type=source_type,
            source_session_id=source_session_id,
            metadata=mem0_metadata,
        )

    async def get(self, memory_id: str) -> MemoryRecord | None:
        """Retrieve a memory by ID from Mem0.

        Args:
            memory_id: The memory ID to retrieve

        Returns:
            The MemoryRecord if found, None otherwise
        """
        try:
            # Run in thread to avoid blocking event loop
            result = await asyncio.to_thread(self._client.get, memory_id)
            if result:
                return self._mem0_to_record(result)
            return None
        except Exception:
            # Memory not found or API error
            return None

    async def update(
        self,
        memory_id: str,
        content: str | None = None,
        importance: float | None = None,
        tags: list[str] | None = None,
    ) -> MemoryRecord:
        """Update an existing memory in Mem0.

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
        # Get existing memory first
        existing = await self.get(memory_id)
        if not existing:
            raise ValueError(f"Memory not found: {memory_id}")

        # Note: Mem0's update API only supports content updates.
        # Importance and tags changes are reflected in the returned record
        # but not persisted to Mem0 (they're stored in metadata which Mem0
        # doesn't allow updating via the update endpoint).

        # Update via Mem0 API (run in thread to avoid blocking event loop)
        result = await asyncio.to_thread(
            self._client.update, memory_id, data=content or existing.content
        )

        # Return updated record
        if result:
            return self._mem0_to_record(result)

        # Fallback: return synthetic updated record
        return MemoryRecord(
            id=memory_id,
            content=content or existing.content,
            created_at=existing.created_at,
            memory_type=existing.memory_type,
            importance=importance if importance is not None else existing.importance,
            project_id=existing.project_id,
            user_id=existing.user_id,
            tags=tags if tags is not None else existing.tags,
            source_type=existing.source_type,
            source_session_id=existing.source_session_id,
            metadata=existing.metadata,
        )

    async def delete(self, memory_id: str) -> bool:
        """Delete a memory from Mem0.

        Args:
            memory_id: The memory ID to delete

        Returns:
            True if deleted, False if not found
        """
        try:
            # Run in thread to avoid blocking event loop
            await asyncio.to_thread(self._client.delete, memory_id)
            return True
        except Exception:
            return False

    async def search(self, query: MemoryQuery) -> list[MemoryRecord]:
        """Search for memories using Mem0's semantic search.

        Args:
            query: Search parameters

        Returns:
            List of matching MemoryRecords
        """
        user_id = query.user_id or self._default_user_id or "default"

        # Build search kwargs
        search_kwargs: dict[str, Any] = {
            "query": query.text or "",
            "user_id": user_id,
        }
        if query.limit:
            search_kwargs["limit"] = query.limit

        # Execute search via Mem0 API (run in thread to avoid blocking event loop)
        results = await asyncio.to_thread(lambda: self._client.search(**search_kwargs))

        # Convert results to MemoryRecords
        records = []
        for mem0_memory in results.get("results", []):
            record = self._mem0_to_record(mem0_memory)

            # Apply additional filters not supported by Mem0 API
            if query.min_importance is not None and record.importance < query.min_importance:
                continue
            if query.memory_type is not None and record.memory_type != query.memory_type:
                continue
            if query.project_id is not None and record.project_id != query.project_id:
                continue

            records.append(record)

        return records

    async def list_memories(
        self,
        project_id: str | None = None,
        user_id: str | None = None,
        memory_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MemoryRecord]:
        """List memories from Mem0 with optional filtering.

        Args:
            project_id: Filter by project ID (stored in metadata)
            user_id: Filter by user ID
            memory_type: Filter by memory type
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of MemoryRecords
        """
        effective_user_id = user_id or self._default_user_id or "default"

        # Get all memories for user via Mem0 API (run in thread to avoid blocking event loop)
        results = await asyncio.to_thread(self._client.get_all, user_id=effective_user_id)

        # Convert and filter results
        records = []
        skipped = 0
        for mem0_memory in results.get("results", []):
            record = self._mem0_to_record(mem0_memory)

            # Apply filters
            if project_id is not None and record.project_id != project_id:
                continue
            if memory_type is not None and record.memory_type != memory_type:
                continue

            # Handle offset
            if skipped < offset:
                skipped += 1
                continue

            records.append(record)

            # Handle limit
            if len(records) >= limit:
                break

        return records

    def close(self) -> None:
        """Clean up resources.

        Called when the backend is no longer needed.
        """
        # Mem0 client doesn't require explicit cleanup
        pass

    def _mem0_to_record(
        self,
        mem0_memory: dict[str, Any],
    ) -> MemoryRecord:
        """Convert a Mem0 memory dict to MemoryRecord.

        Args:
            mem0_memory: Memory dict from Mem0 API

        Returns:
            MemoryRecord instance
        """
        # Parse created_at if present
        created_at_str = mem0_memory.get("created_at")
        if created_at_str:
            created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        else:
            created_at = datetime.now(UTC)

        # Extract metadata fields
        metadata = mem0_memory.get("metadata", {})

        # Generate deterministic ID from memory content if not provided
        memory_id = mem0_memory.get("id")
        if not memory_id:
            # Create stable hash from memory content for deterministic ID
            content_for_hash = mem0_memory.get("memory", "") + str(mem0_memory.get("user_id", ""))
            hash_digest = hashlib.sha256(content_for_hash.encode()).hexdigest()[:8]
            memory_id = f"mem0-{hash_digest}"

        return MemoryRecord(
            id=memory_id,
            content=mem0_memory.get("memory", ""),
            created_at=created_at,
            memory_type=metadata.get("memory_type", "fact"),
            importance=metadata.get("importance", 0.5),
            project_id=metadata.get("project_id"),
            user_id=mem0_memory.get("user_id"),
            tags=metadata.get("tags", []),
            source_type=metadata.get("source_type"),
            source_session_id=metadata.get("source_session_id"),
            metadata=metadata,
        )
