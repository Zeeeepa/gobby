"""Mem0 memory backend integration.

This backend wraps the Mem0 AI memory service to provide a
MemoryBackendProtocol-compliant interface. Mem0 offers semantic
search and automatic memory organization.

Requires: pip install mem0ai

Example:
    from gobby.memory.backends import get_backend

    backend = get_backend("memu", api_key="your-mem0-api-key")
    record = await backend.create("User prefers dark mode")
"""

from __future__ import annotations

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


class MemUBackend:
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
        from mem0 import MemoryClient

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
        raise NotImplementedError("MemUBackend.create not yet implemented")

    async def get(self, memory_id: str) -> MemoryRecord | None:
        """Retrieve a memory by ID from Mem0.

        Args:
            memory_id: The memory ID to retrieve

        Returns:
            The MemoryRecord if found, None otherwise
        """
        raise NotImplementedError("MemUBackend.get not yet implemented")

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
        raise NotImplementedError("MemUBackend.update not yet implemented")

    async def delete(self, memory_id: str) -> bool:
        """Delete a memory from Mem0.

        Args:
            memory_id: The memory ID to delete

        Returns:
            True if deleted, False if not found
        """
        raise NotImplementedError("MemUBackend.delete not yet implemented")

    async def search(self, query: MemoryQuery) -> list[MemoryRecord]:
        """Search for memories using Mem0's semantic search.

        Args:
            query: Search parameters

        Returns:
            List of matching MemoryRecords
        """
        raise NotImplementedError("MemUBackend.search not yet implemented")

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
        raise NotImplementedError("MemUBackend.list_memories not yet implemented")

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

        return MemoryRecord(
            id=mem0_memory["id"],
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
