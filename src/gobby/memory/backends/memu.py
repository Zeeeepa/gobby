"""MemU memory backend integration.

This backend wraps the MemU SDK (nevamind-ai/memu-sdk-py) to provide a
MemoryBackendProtocol-compliant interface. MemU offers conversation-based
memory storage with semantic search.

Requires: pip install memu-sdk

Example:
    from gobby.memory.backends import get_backend

    backend = get_backend("memu", api_key="your-memu-api-key")
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
    from memu_sdk import MemUClient


class MemUBackend:
    """MemU-based memory backend.

    Wraps the MemU SDK to provide MemoryBackendProtocol interface.
    Uses conversation-based memory storage and semantic search.

    Note: MemU SDK uses a conversation-based API (memorize/retrieve) rather
    than individual CRUD operations. This backend adapts that API to the
    MemoryBackendProtocol interface.

    Args:
        api_key: MemU API key for authentication
        user_id: Default user ID for memories (optional)
        agent_id: Agent ID for MemU API (default: "gobby")
    """

    def __init__(
        self,
        api_key: str,
        user_id: str | None = None,
        agent_id: str = "gobby",
        **kwargs: Any,
    ):
        """Initialize the MemU backend.

        Args:
            api_key: MemU API key
            user_id: Default user ID for operations
            agent_id: Agent ID for MemU API
            **kwargs: Additional MemUClient configuration
        """
        # Lazy import to avoid requiring memu-sdk when not used
        from memu_sdk import MemUClient

        self._client: MemUClient = MemUClient(api_key=api_key, **kwargs)
        self._default_user_id = user_id or "default"
        self._agent_id = agent_id

    def capabilities(self) -> set[MemoryCapability]:
        """Return supported capabilities.

        MemU uses conversation-based storage - supports create and semantic search.
        Individual get/update/delete not supported by the SDK.
        """
        return {
            # Basic operations
            MemoryCapability.CREATE,
            # Search
            MemoryCapability.SEARCH_SEMANTIC,
            MemoryCapability.SEARCH,
            # MCP-aligned
            MemoryCapability.REMEMBER,
            MemoryCapability.RECALL,
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
        """Create a new memory in MemU.

        Uses the memorize API with a synthetic conversation format.

        Args:
            content: The memory content text
            memory_type: Type of memory (stored in metadata)
            importance: Importance score (stored in metadata)
            project_id: Associated project ID
            user_id: User ID (uses default if not provided)
            tags: List of tags
            source_type: Origin of memory
            source_session_id: Session that created the memory
            media: List of media attachments (not supported by MemU)
            metadata: Additional metadata

        Returns:
            The created MemoryRecord
        """
        effective_user_id = user_id or self._default_user_id

        # Build metadata for tracking
        record_metadata: dict[str, Any] = {
            "memory_type": memory_type,
            "importance": importance,
            "source_type": source_type,
            "source_session_id": source_session_id,
            **(metadata or {}),
        }
        if project_id:
            record_metadata["project_id"] = project_id
        if tags:
            record_metadata["tags"] = tags

        # MemU uses conversation format - wrap content as a user message
        conversation_text = f"Remember: {content}"

        # Memorize via MemU API (synchronous call)
        result = self._client.memorize_sync(
            conversation_text=conversation_text,
            user_id=effective_user_id,
            agent_id=self._agent_id,
            wait_for_completion=True,
        )

        # Extract memory ID from result
        memory_id = "unknown"
        if result and result.items:
            first_item = result.items[0]
            memory_id = getattr(first_item, "memory_id", "unknown")

        return MemoryRecord(
            id=memory_id,
            content=content,
            created_at=datetime.now(UTC),
            memory_type=memory_type,
            importance=importance,
            project_id=project_id,
            user_id=effective_user_id,
            tags=tags or [],
            source_type=source_type,
            source_session_id=source_session_id,
            metadata=record_metadata,
        )

    async def get(self, memory_id: str) -> MemoryRecord | None:
        """Retrieve a memory by ID from MemU.

        Note: MemU SDK does not support direct memory retrieval by ID.
        Use search() instead.

        Args:
            memory_id: The memory ID to retrieve

        Returns:
            None (not supported)
        """
        # MemU SDK doesn't support direct get by ID
        return None

    async def update(
        self,
        memory_id: str,
        content: str | None = None,
        importance: float | None = None,
        tags: list[str] | None = None,
    ) -> MemoryRecord:
        """Update an existing memory in MemU.

        Note: MemU SDK does not support memory updates. Create a new memory instead.

        Args:
            memory_id: The memory ID to update
            content: New content (optional)
            importance: New importance score (optional)
            tags: New tags (optional)

        Raises:
            NotImplementedError: MemU SDK doesn't support updates
        """
        raise NotImplementedError("MemU backend does not support memory updates")

    async def delete(self, memory_id: str) -> bool:
        """Delete a memory from MemU.

        Note: MemU SDK does not support memory deletion.

        Args:
            memory_id: The memory ID to delete

        Returns:
            False (not supported)
        """
        # MemU SDK doesn't support deletion
        return False

    async def search(self, query: MemoryQuery) -> list[MemoryRecord]:
        """Search for memories using MemU's semantic search.

        Args:
            query: Search parameters

        Returns:
            List of matching MemoryRecords
        """
        user_id = query.user_id or self._default_user_id

        # Use retrieve API for semantic search
        result = self._client.retrieve_sync(
            query=query.text or "",
            user_id=user_id,
            agent_id=self._agent_id,
        )

        records = []
        if result and result.items:
            for item in result.items:
                record = self._memu_item_to_record(item)
                records.append(record)

        # Apply limit if specified
        if query.limit and len(records) > query.limit:
            records = records[: query.limit]

        return records

    async def list_memories(
        self,
        project_id: str | None = None,
        user_id: str | None = None,
        memory_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MemoryRecord]:
        """List memories from MemU with optional filtering.

        Note: MemU SDK uses semantic search, not listing. This performs
        a broad search to approximate listing behavior.

        Args:
            project_id: Filter by project ID (not supported)
            user_id: Filter by user ID
            memory_type: Filter by memory type
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of MemoryRecords
        """
        effective_user_id = user_id or self._default_user_id

        # MemU doesn't have a list API - use a broad search
        result = self._client.retrieve_sync(
            query="*",  # Broad query to get all memories
            user_id=effective_user_id,
            agent_id=self._agent_id,
        )

        records = []
        if result and result.items:
            for item in result.items:
                record = self._memu_item_to_record(item)

                # Apply memory_type filter if specified
                if memory_type is not None and record.memory_type != memory_type:
                    continue

                records.append(record)

        # Apply offset and limit
        if offset > 0:
            records = records[offset:]
        if limit and len(records) > limit:
            records = records[:limit]

        return records

    def close(self) -> None:
        """Clean up resources.

        Called when the backend is no longer needed.
        """
        # Close the sync connection
        self._client.close_sync()

    def _memu_item_to_record(
        self,
        item: Any,
    ) -> MemoryRecord:
        """Convert a MemU MemoryItem to MemoryRecord.

        Args:
            item: MemoryItem from MemU SDK

        Returns:
            MemoryRecord instance
        """
        # Extract fields from MemoryItem object
        memory_id = getattr(item, "memory_id", "unknown")
        content = getattr(item, "content", "")
        memory_type = getattr(item, "memory_type", "fact")
        created_at_str = getattr(item, "created_at", None)
        metadata = getattr(item, "metadata", {}) or {}

        if created_at_str:
            if isinstance(created_at_str, str):
                created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
            else:
                created_at = created_at_str
        else:
            created_at = datetime.now(UTC)

        return MemoryRecord(
            id=memory_id,
            content=content,
            created_at=created_at,
            memory_type=memory_type,
            importance=metadata.get("importance", 0.5),
            project_id=metadata.get("project_id"),
            user_id=self._default_user_id,
            tags=metadata.get("tags", []),
            source_type=metadata.get("source_type"),
            source_session_id=metadata.get("source_session_id"),
            metadata=metadata,
        )
