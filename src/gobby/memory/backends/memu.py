"""MemU memory backend integration.

This backend wraps the MemU SDK (NevaMind-AI/memU via memu-py) to provide a
MemoryBackendProtocol-compliant interface. MemU offers structured memory
storage with semantic search and categorization.

Requires: pip install memu-py

Example:
    from gobby.memory.backends import get_backend

    backend = get_backend("memu", database_type="inmemory")
    record = await backend.create("User prefers dark mode")
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from gobby.memory.protocol import (
    MediaAttachment,
    MemoryCapability,
    MemoryQuery,
    MemoryRecord,
)

if TYPE_CHECKING:
    from memu.app.service import MemoryService


class MemUBackend:
    """MemU-based memory backend.

    Wraps the MemU SDK (memu-py) to provide MemoryBackendProtocol interface.
    Supports structured memory storage with semantic search.

    Args:
        database_type: Database type - "inmemory", "sqlite", or "postgres"
        database_url: Database URL (for sqlite/postgres)
        llm_api_key: API key for LLM provider (OpenAI, etc.)
        llm_base_url: Base URL for LLM API
        embedding_api_key: API key for embedding provider
        embedding_base_url: Base URL for embedding API
        user_id: Default user ID for memories
    """

    def __init__(
        self,
        database_type: str = "inmemory",
        database_url: str | None = None,
        llm_api_key: str | None = None,
        llm_base_url: str | None = None,
        embedding_api_key: str | None = None,
        embedding_base_url: str | None = None,
        user_id: str | None = None,
        **kwargs: Any,
    ):
        """Initialize the MemU backend.

        Args:
            database_type: Database backend type
            database_url: Connection URL for database
            llm_api_key: LLM API key
            llm_base_url: LLM API base URL
            embedding_api_key: Embedding API key
            embedding_base_url: Embedding API base URL
            user_id: Default user ID for operations
            **kwargs: Additional configuration
        """
        # Lazy import to avoid circular dependencies
        from memu.app.service import MemoryService

        # Build configuration
        config: dict[str, Any] = {}

        # Database configuration
        if database_type == "inmemory":
            config["database_config"] = {"type": "inmemory"}
        elif database_type == "sqlite":
            config["database_config"] = {
                "type": "sqlite",
                "url": database_url or "sqlite:///memu.db",
            }
        elif database_type == "postgres":
            if not database_url:
                raise ValueError(
                    "database_url is required when database_type is 'postgres'. "
                    "Please provide a valid PostgreSQL connection URL."
                )
            config["database_config"] = {
                "type": "postgres",
                "url": database_url,
            }

        # LLM configuration (optional - uses OpenAI by default)
        if llm_api_key or llm_base_url:
            config["llm_profiles"] = {
                "default": {
                    "api_key": llm_api_key,
                    "base_url": llm_base_url,
                }
            }

        # Embedding configuration (optional - uses OpenAI by default)
        if embedding_api_key or embedding_base_url:
            config["embedding_profiles"] = {
                "default": {
                    "api_key": embedding_api_key,
                    "base_url": embedding_base_url,
                }
            }

        self._service: MemoryService = MemoryService(**config)
        self._default_user_id = user_id

    def capabilities(self) -> set[MemoryCapability]:
        """Return supported capabilities.

        MemU supports semantic search and structured CRUD operations.
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
        """Create a new memory in MemU.

        Args:
            content: The memory content text
            memory_type: Type of memory (mapped to MemU memory types)
            importance: Importance score (stored in metadata)
            project_id: Associated project ID
            user_id: User ID (uses default if not provided)
            tags: List of tags (used as categories)
            source_type: Origin of memory
            source_session_id: Session that created the memory
            media: List of media attachments (stored in metadata)
            metadata: Additional metadata

        Returns:
            The created MemoryRecord
        """
        effective_user_id = user_id or self._default_user_id or "default"

        # Map memory_type to MemU MemoryType
        memu_type = self._map_memory_type(memory_type)

        # Use tags as categories, or create from memory_type
        categories = tags if tags else [memory_type]

        # Create user scope
        user_scope = {"user_id": effective_user_id}
        if project_id:
            user_scope["project_id"] = project_id

        # Create memory via MemU service (run in thread to avoid blocking event loop)
        result = await asyncio.to_thread(
            self._service.create_memory_item,
            memory_type=memu_type,
            memory_content=content,
            memory_categories=categories,
            user=user_scope,
        )

        # Extract memory ID from result
        memory_id = result.get("id") or result.get("memory_id") or str(uuid4())

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
            metadata=metadata or {},
        )

    async def get(self, memory_id: str) -> MemoryRecord | None:
        """Retrieve a memory by ID from MemU.

        Args:
            memory_id: The memory ID to retrieve

        Returns:
            The MemoryRecord if found, None otherwise
        """
        # Try direct lookup first (O(1) if SDK supports it)
        try:
            # Run in thread to avoid blocking event loop
            result = await asyncio.to_thread(self._service.get_memory_item, memory_id=memory_id)
            if result:
                return self._memu_to_record(result)
            return None
        except AttributeError:
            # SDK may not have get_memory_item, fall back to list scan
            pass
        except Exception:
            return None

        # Fallback: list and filter (O(n))
        try:
            # Run in thread to avoid blocking event loop
            result = await asyncio.to_thread(self._service.list_memory_items)
            items = result.get("items", result.get("memories", []))

            for item in items:
                if item.get("id") == memory_id or item.get("memory_id") == memory_id:
                    return self._memu_to_record(item)

            return None
        except Exception:
            return None

    async def update(
        self,
        memory_id: str,
        content: str | None = None,
        importance: float | None = None,
        tags: list[str] | None = None,
    ) -> MemoryRecord:
        """Update an existing memory in MemU.

        Args:
            memory_id: The memory ID to update
            content: New content (optional)
            importance: New importance score (optional, stored in metadata)
            tags: New tags/categories (optional)

        Returns:
            The updated MemoryRecord

        Raises:
            ValueError: If memory not found
        """
        existing = await self.get(memory_id)
        if not existing:
            raise ValueError(f"Memory not found: {memory_id}")

        # Build update kwargs
        update_kwargs: dict[str, Any] = {"memory_id": memory_id}
        if content is not None:
            update_kwargs["memory_content"] = content
        if tags is not None:
            update_kwargs["memory_categories"] = tags

        # Run in thread to avoid blocking event loop
        result = await asyncio.to_thread(lambda: self._service.update_memory_item(**update_kwargs))

        if result:
            # Re-fetch to get updated record
            updated = await self.get(memory_id)
            if updated:
                return updated

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
        """Delete a memory from MemU.

        Args:
            memory_id: The memory ID to delete

        Returns:
            True if deleted, False if not found
        """
        try:
            # Run in thread to avoid blocking event loop
            await asyncio.to_thread(self._service.delete_memory_item, memory_id=memory_id)
            return True
        except Exception:
            return False

    async def search(self, query: MemoryQuery) -> list[MemoryRecord]:
        """Search for memories using MemU's semantic search.

        Args:
            query: Search parameters

        Returns:
            List of matching MemoryRecords
        """
        user_id = query.user_id or self._default_user_id or "default"

        # Build query for MemU retrieve
        queries = [{"role": "user", "content": query.text or ""}]

        # Build where filter
        where_filter: dict[str, Any] = {"user_id": user_id}
        if query.project_id:
            where_filter["project_id"] = query.project_id

        # Run in thread to avoid blocking event loop
        results = await asyncio.to_thread(
            self._service.retrieve, queries=queries, where=where_filter
        )

        records = []
        items = results.get("items", results.get("memories", []))

        for memu_item in items:  # Don't slice here - filter first, then limit
            record = self._memu_to_record(memu_item)

            # Apply additional filters not supported by MemU API
            if query.min_importance is not None and record.importance < query.min_importance:
                continue
            if query.memory_type is not None and record.memory_type != query.memory_type:
                continue

            records.append(record)

            # Apply limit after filtering
            if query.limit and len(records) >= query.limit:
                break

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

        Args:
            project_id: Filter by project ID
            user_id: Filter by user ID
            memory_type: Filter by memory type
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of MemoryRecords
        """
        effective_user_id = user_id or self._default_user_id or "default"

        # Build where filter
        where_filter: dict[str, Any] = {"user_id": effective_user_id}
        if project_id:
            where_filter["project_id"] = project_id

        # Run in thread to avoid blocking event loop
        results = await asyncio.to_thread(self._service.list_memory_items, where=where_filter)

        items = results.get("items", results.get("memories", []))

        # First filter all items by memory_type
        filtered_items = []
        for memu_item in items:
            record = self._memu_to_record(memu_item)
            if memory_type is not None and record.memory_type != memory_type:
                continue
            filtered_items.append(record)

        # Then apply pagination
        return filtered_items[offset : offset + limit]

    def close(self) -> None:
        """Clean up resources.

        Called when the backend is no longer needed.
        """
        # MemU service doesn't require explicit cleanup
        pass

    def _map_memory_type(self, memory_type: str) -> str:
        """Map our memory types to MemU MemoryType strings.

        Args:
            memory_type: Our memory type string

        Returns:
            MemU MemoryType string (one of: profile, event, knowledge, behavior, skill)
        """
        # MemU uses Literal type: Literal["profile", "event", "knowledge", "behavior", "skill"]
        type_mapping = {
            "fact": "knowledge",
            "knowledge": "knowledge",
            "preference": "profile",
            "profile": "profile",
            "event": "event",
            "skill": "skill",
            "behavior": "behavior",
        }
        return type_mapping.get(memory_type, "knowledge")

    def _memu_to_record(
        self,
        memu_item: dict[str, Any],
    ) -> MemoryRecord:
        """Convert a MemU memory dict to MemoryRecord.

        Args:
            memu_item: Memory dict from MemU API

        Returns:
            MemoryRecord instance
        """
        created_at_str = memu_item.get("created_at")
        if created_at_str:
            if isinstance(created_at_str, str):
                created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
            else:
                created_at = created_at_str
        else:
            created_at = datetime.now(UTC)

        # Extract memory type from MemU's memory_type field
        memu_type = memu_item.get("memory_type", "knowledge")
        if hasattr(memu_type, "value"):
            memu_type = memu_type.value

        # Map MemU types back to our types
        type_mapping = {
            "knowledge": "fact",
            "profile": "preference",
            "event": "event",
            "skill": "skill",
            "behavior": "behavior",
        }
        memory_type = type_mapping.get(str(memu_type), "fact")

        # Get categories as tags
        categories = memu_item.get("categories", memu_item.get("memory_categories", []))

        return MemoryRecord(
            id=memu_item.get("id") or memu_item.get("memory_id", "unknown"),
            content=memu_item.get("content") or memu_item.get("memory_content", ""),
            created_at=created_at,
            memory_type=memory_type,
            importance=memu_item.get("importance", 0.5),
            project_id=memu_item.get("project_id"),
            user_id=memu_item.get("user_id"),
            tags=categories if isinstance(categories, list) else [],
            source_type=memu_item.get("source_type"),
            source_session_id=memu_item.get("source_session_id"),
            metadata=memu_item.get("metadata", {}),
        )
