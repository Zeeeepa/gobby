"""OpenMemory REST API backend integration.

This backend connects to a self-hosted OpenMemory server to provide
embedding-based semantic memory storage and search.

OpenMemory is a self-hosted memory system that provides:
- REST API for CRUD operations on memories
- Embedding-based semantic search
- Local storage (no cloud dependency)

Example:
    from gobby.memory.backends import get_backend

    backend = get_backend("openmemory", base_url="http://localhost:8080")
    record = await backend.create("User prefers dark mode")
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import httpx

from gobby.memory.protocol import (
    MediaAttachment,
    MemoryCapability,
    MemoryQuery,
    MemoryRecord,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class OpenMemoryError(Exception):
    """Base exception for OpenMemory backend errors."""

    pass


class OpenMemoryConnectionError(OpenMemoryError):
    """Raised when connection to OpenMemory server fails."""

    pass


class OpenMemoryAPIError(OpenMemoryError):
    """Raised when OpenMemory API returns an error."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class OpenMemoryBackend:
    """OpenMemory REST API backend.

    Connects to a self-hosted OpenMemory server for embedding-based
    memory storage and semantic search.

    Args:
        base_url: OpenMemory server base URL (e.g., "http://localhost:8080")
        api_key: Optional API key for authentication
        user_id: Default user ID for memories
        timeout: HTTP request timeout in seconds
    """

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        user_id: str | None = None,
        timeout: float = 30.0,
    ):
        """Initialize the OpenMemory backend.

        Args:
            base_url: Server base URL (no trailing slash)
            api_key: Optional API key for authentication
            user_id: Default user ID for operations
            timeout: Request timeout in seconds
        """
        # Normalize base URL
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._default_user_id = user_id or "default"
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None or self._client.is_closed:
            headers = {"Content-Type": "application/json"}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers=headers,
                timeout=self._timeout,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> OpenMemoryBackend:
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()

    def capabilities(self) -> set[MemoryCapability]:
        """Return supported capabilities.

        OpenMemory supports semantic search and basic CRUD operations.
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
            MemoryCapability.TAGS,
            MemoryCapability.IMPORTANCE,
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
        """Create a new memory in OpenMemory.

        Args:
            content: The memory content text
            memory_type: Type of memory (stored in metadata)
            importance: Importance score (stored in metadata)
            project_id: Associated project ID
            user_id: User ID (uses default if not provided)
            tags: List of tags
            source_type: Origin of memory
            source_session_id: Session that created the memory
            media: List of media attachments (stored in metadata)
            metadata: Additional metadata

        Returns:
            The created MemoryRecord
        """
        client = await self._get_client()
        effective_user_id = user_id or self._default_user_id

        # Build request payload
        payload: dict[str, Any] = {
            "content": content,
            "user_id": effective_user_id,
            "metadata": {
                "memory_type": memory_type,
                "importance": importance,
                "source_type": source_type,
                "source_session_id": source_session_id,
                **(metadata or {}),
            },
        }
        if project_id:
            payload["metadata"]["project_id"] = project_id
        if tags:
            payload["tags"] = tags
        if media:
            payload["metadata"]["media"] = [
                {
                    "media_type": m.media_type,
                    "content_path": m.content_path,
                    "mime_type": m.mime_type,
                    "description": m.description,
                }
                for m in media
            ]

        try:
            response = await client.post("/api/v1/memories", json=payload)
            response.raise_for_status()
            data = response.json()
            return self._response_to_record(data)
        except httpx.ConnectError as e:
            raise OpenMemoryConnectionError(
                f"Failed to connect to OpenMemory at {self._base_url}: {e}"
            ) from e
        except httpx.HTTPStatusError as e:
            raise OpenMemoryAPIError(
                f"OpenMemory API error: {e.response.text}",
                status_code=e.response.status_code,
            ) from e
        except Exception as e:
            # Log and re-raise - callers should handle failures explicitly
            logger.error(
                f"OpenMemory create failed: {e}",
                exc_info=True,
            )
            raise

    async def get(self, memory_id: str) -> MemoryRecord | None:
        """Retrieve a memory by ID from OpenMemory.

        Args:
            memory_id: The memory ID to retrieve

        Returns:
            The MemoryRecord if found, None otherwise
        """
        client = await self._get_client()
        try:
            response = await client.get(f"/api/v1/memories/{memory_id}")
            if response.status_code == 404:
                return None
            response.raise_for_status()
            data = response.json()
            return self._response_to_record(data)
        except httpx.ConnectError as e:
            raise OpenMemoryConnectionError(
                f"Failed to connect to OpenMemory at {self._base_url}: {e}"
            ) from e
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise OpenMemoryAPIError(
                f"OpenMemory API error: {e.response.text}",
                status_code=e.response.status_code,
            ) from e
        except Exception as e:
            logger.error(f"OpenMemory get failed for {memory_id}: {e}", exc_info=True)
            return None

    async def update(
        self,
        memory_id: str,
        content: str | None = None,
        importance: float | None = None,
        tags: list[str] | None = None,
    ) -> MemoryRecord:
        """Update an existing memory in OpenMemory.

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
        client = await self._get_client()

        # Build update payload
        payload: dict[str, Any] = {}
        if content is not None:
            payload["content"] = content
        if importance is not None:
            payload["metadata"] = {"importance": importance}
        if tags is not None:
            payload["tags"] = tags

        try:
            response = await client.patch(f"/api/v1/memories/{memory_id}", json=payload)
            if response.status_code == 404:
                raise ValueError(f"Memory not found: {memory_id}")
            response.raise_for_status()
            data = response.json()
            return self._response_to_record(data)
        except httpx.ConnectError as e:
            raise OpenMemoryConnectionError(
                f"Failed to connect to OpenMemory at {self._base_url}: {e}"
            ) from e
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise ValueError(f"Memory not found: {memory_id}") from e
            raise OpenMemoryAPIError(
                f"OpenMemory API error: {e.response.text}",
                status_code=e.response.status_code,
            ) from e

    async def delete(self, memory_id: str) -> bool:
        """Delete a memory from OpenMemory.

        Args:
            memory_id: The memory ID to delete

        Returns:
            True if deleted, False if not found
        """
        client = await self._get_client()
        try:
            response = await client.delete(f"/api/v1/memories/{memory_id}")
            if response.status_code == 404:
                return False
            response.raise_for_status()
            return True
        except httpx.ConnectError as e:
            raise OpenMemoryConnectionError(
                f"Failed to connect to OpenMemory at {self._base_url}: {e}"
            ) from e
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return False
            raise OpenMemoryAPIError(
                f"OpenMemory API error: {e.response.text}",
                status_code=e.response.status_code,
            ) from e
        except Exception as e:
            logger.error(f"OpenMemory delete failed for {memory_id}: {e}", exc_info=True)
            return False

    async def search(self, query: MemoryQuery) -> list[MemoryRecord]:
        """Search for memories using OpenMemory's semantic search.

        Args:
            query: Search parameters

        Returns:
            List of matching MemoryRecords
        """
        client = await self._get_client()
        user_id = query.user_id or self._default_user_id

        # Build search params
        params: dict[str, Any] = {
            "q": query.text,
            "user_id": user_id,
            "limit": query.limit,
        }
        if query.project_id:
            params["project_id"] = query.project_id
        if query.min_importance is not None:
            params["min_importance"] = query.min_importance
        if query.memory_type:
            params["memory_type"] = query.memory_type
        if query.tags_any:
            params["tags"] = ",".join(query.tags_any)

        try:
            response = await client.get("/api/v1/memories/search", params=params)
            response.raise_for_status()
            data = response.json()

            records = []
            for item in data.get("results", data.get("memories", [])):
                record = self._response_to_record(item)

                # Apply additional filters not supported by API
                if query.tags_all:
                    if not all(t in record.tags for t in query.tags_all):
                        continue
                if query.tags_none:
                    if any(t in record.tags for t in query.tags_none):
                        continue

                records.append(record)

            return records
        except httpx.ConnectError as e:
            raise OpenMemoryConnectionError(
                f"Failed to connect to OpenMemory at {self._base_url}: {e}"
            ) from e
        except httpx.HTTPStatusError as e:
            raise OpenMemoryAPIError(
                f"OpenMemory API error: {e.response.text}",
                status_code=e.response.status_code,
            ) from e
        except Exception as e:
            logger.error(f"OpenMemory search failed for query '{query.text}': {e}", exc_info=True)
            return []

    async def list_memories(
        self,
        project_id: str | None = None,
        user_id: str | None = None,
        memory_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MemoryRecord]:
        """List memories from OpenMemory with optional filtering.

        Args:
            project_id: Filter by project ID
            user_id: Filter by user ID
            memory_type: Filter by memory type
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of MemoryRecords
        """
        client = await self._get_client()
        effective_user_id = user_id or self._default_user_id

        # Build params
        params: dict[str, Any] = {
            "user_id": effective_user_id,
            "limit": limit,
            "offset": offset,
        }
        if project_id:
            params["project_id"] = project_id
        if memory_type:
            params["memory_type"] = memory_type

        try:
            response = await client.get("/api/v1/memories", params=params)
            response.raise_for_status()
            data = response.json()

            records = []
            for item in data.get("results", data.get("memories", [])):
                records.append(self._response_to_record(item))

            return records
        except httpx.ConnectError as e:
            raise OpenMemoryConnectionError(
                f"Failed to connect to OpenMemory at {self._base_url}: {e}"
            ) from e
        except httpx.HTTPStatusError as e:
            raise OpenMemoryAPIError(
                f"OpenMemory API error: {e.response.text}",
                status_code=e.response.status_code,
            ) from e
        except Exception as e:
            logger.error(
                f"OpenMemory list_memories failed (project={project_id}, user={user_id}): {e}",
                exc_info=True,
            )
            return []

    async def health_check(self) -> bool:
        """Check if the OpenMemory server is healthy.

        Returns:
            True if server is reachable and healthy, False otherwise
        """
        client = await self._get_client()
        try:
            response = await client.get("/health")
            return response.status_code == 200
        except Exception:
            return False

    def _response_to_record(self, data: dict[str, Any]) -> MemoryRecord:
        """Convert OpenMemory API response to MemoryRecord.

        Args:
            data: Response dict from OpenMemory API

        Returns:
            MemoryRecord instance

        Raises:
            ValueError: If response is missing required 'id' field
        """
        # Validate that id exists - don't generate synthetic IDs
        if "id" not in data:
            raise ValueError("OpenMemory API response missing required 'id' field")

        # Parse created_at
        created_at_str = data.get("created_at")
        if created_at_str:
            if isinstance(created_at_str, str):
                created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
            else:
                created_at = datetime.now(UTC)
        else:
            created_at = datetime.now(UTC)

        # Parse updated_at
        updated_at_str = data.get("updated_at")
        updated_at = None
        if updated_at_str and isinstance(updated_at_str, str):
            updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))

        # Extract metadata
        metadata = data.get("metadata", {})

        # Restore media attachments from metadata
        media_list: list[MediaAttachment] = []
        raw_media = metadata.get("media", [])
        for m in raw_media:
            if isinstance(m, dict):
                media_list.append(
                    MediaAttachment(
                        media_type=m.get("media_type", ""),
                        content_path=m.get("content_path", ""),
                        mime_type=m.get("mime_type", ""),
                        description=m.get("description"),
                    )
                )

        return MemoryRecord(
            id=data["id"],
            content=data.get("content", ""),
            created_at=created_at,
            updated_at=updated_at,
            memory_type=metadata.get("memory_type", "fact"),
            importance=metadata.get("importance", 0.5),
            project_id=metadata.get("project_id"),
            user_id=data.get("user_id"),
            tags=data.get("tags", []),
            source_type=metadata.get("source_type"),
            source_session_id=metadata.get("source_session_id"),
            media=media_list,
            metadata=metadata,
        )
