"""Async Mem0 REST client.

Provides a direct HTTP client for the Mem0 Platform API using httpx,
without requiring the mem0ai Python package.

Supports both the hosted platform (api.mem0.ai) and self-hosted instances.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class Mem0ConnectionError(Exception):
    """Raised when unable to connect to the Mem0 API."""


class Mem0APIError(Exception):
    """Raised when the Mem0 API returns an error response (4xx/5xx)."""

    def __init__(self, message: str, status_code: int, response_body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class Mem0Client:
    """Async HTTP client for the Mem0 REST API.

    Args:
        base_url: Mem0 API base URL (default: https://api.mem0.ai)
        api_key: API key for authentication (optional for local instances)
        user_id: Default user_id for operations (default: "gobby")
        timeout: Request timeout in seconds (default: 30.0)
    """

    def __init__(
        self,
        base_url: str = "https://api.mem0.ai",
        api_key: str | None = None,
        user_id: str = "gobby",
        timeout: float = 30.0,
    ):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._user_id = user_id
        self._timeout = timeout

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Token {api_key}"

        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers=headers,
            timeout=timeout,
        )

    async def __aenter__(self) -> Mem0Client:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    async def create(
        self,
        content: str,
        project_id: str | None = None,
        user_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        """Create a new memory.

        Args:
            content: Memory content text
            project_id: Associated project ID
            user_id: User ID (uses default if not provided)
            metadata: Additional metadata

        Returns:
            API response dict with created memory details
        """
        body: dict[str, Any] = {
            "messages": [{"role": "user", "content": content}],
            "user_id": user_id or self._user_id,
        }

        mem_metadata = dict(metadata or {})
        if project_id:
            mem_metadata["project_id"] = project_id
        if mem_metadata:
            body["metadata"] = mem_metadata

        return await self._request("POST", "/v1/memories/", json=body)

    async def search(
        self,
        query: str,
        user_id: str | None = None,
        limit: int = 10,
        project_id: str | None = None,
    ) -> Any:
        """Search memories by query.

        Args:
            query: Search query text
            user_id: User ID filter
            limit: Maximum results
            project_id: Project ID filter

        Returns:
            API response dict with search results
        """
        body: dict[str, Any] = {
            "query": query,
            "user_id": user_id or self._user_id,
            "limit": limit,
        }
        if project_id:
            body["filters"] = {"project_id": project_id}

        return await self._request("POST", "/v1/memories/search/", json=body)

    async def get(self, memory_id: str) -> Any:
        """Retrieve a single memory by ID.

        Args:
            memory_id: The memory ID

        Returns:
            Memory dict from the API
        """
        return await self._request("GET", f"/v1/memories/{memory_id}/")

    async def update(
        self,
        memory_id: str,
        content: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        """Update a memory.

        Args:
            memory_id: The memory ID to update
            content: New content text
            metadata: Updated metadata

        Returns:
            Updated memory dict
        """
        body: dict[str, Any] = {}
        if content is not None:
            body["text"] = content
        if metadata is not None:
            body["metadata"] = metadata

        return await self._request("PUT", f"/v1/memories/{memory_id}/", json=body)

    async def delete(self, memory_id: str) -> bool:
        """Delete a memory.

        Args:
            memory_id: The memory ID to delete

        Returns:
            True if deleted successfully
        """
        await self._request("DELETE", f"/v1/memories/{memory_id}/")
        return True

    async def list_all(
        self,
        user_id: str | None = None,
        limit: int = 100,
    ) -> Any:
        """List all memories.

        Args:
            user_id: Filter by user ID
            limit: Maximum results

        Returns:
            API response dict with memory list
        """
        params: dict[str, Any] = {
            "user_id": user_id or self._user_id,
            "limit": limit,
        }
        return await self._request("GET", "/v1/memories/", params=params)

    async def get_history(self, memory_id: str) -> Any:
        """Get version history for a memory.

        Args:
            memory_id: The memory ID

        Returns:
            List of history entries
        """
        return await self._request("GET", f"/v1/memories/{memory_id}/history/")

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Execute an HTTP request with error handling.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            path: API path
            json: Request body (for POST/PUT)
            params: Query parameters (for GET)

        Returns:
            Parsed JSON response

        Raises:
            Mem0ConnectionError: On connection or timeout errors
            Mem0APIError: On HTTP 4xx/5xx responses
        """
        try:
            response = await self._client.request(
                method,
                path,
                json=json,
                params=params,
            )
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            raise Mem0ConnectionError(f"Connection refused: {e}") from e
        except httpx.TimeoutException as e:
            raise Mem0ConnectionError(f"Request timed out: {e}") from e

        if not response.is_success:
            try:
                body = response.json()
            except Exception:
                body = response.text
            raise Mem0APIError(
                f"Mem0 API error: HTTP {response.status_code}",
                status_code=response.status_code,
                response_body=body,
            )

        return response.json()
