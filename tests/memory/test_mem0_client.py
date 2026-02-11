"""Tests for the async Mem0 REST client."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from gobby.memory.mem0_client import (
    Mem0APIError,
    Mem0Client,
    Mem0ConnectionError,
)

pytestmark = pytest.mark.unit


def _mock_response(status_code: int = 200, json_data: dict | list | None = None) -> MagicMock:
    """Create a mock httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data if json_data is not None else {}
    resp.is_success = 200 <= status_code < 300
    resp.text = str(json_data)
    return resp


# =============================================================================
# Initialization
# =============================================================================


class TestMem0ClientInit:
    """Test Mem0Client initialization."""

    def test_init_with_defaults(self) -> None:
        """Client initializes with base_url and api_key."""
        client = Mem0Client(api_key="test-key")
        assert client._base_url == "https://api.mem0.ai"
        assert client._api_key == "test-key"

    def test_init_custom_base_url(self) -> None:
        """Client accepts custom base_url for self-hosted instances."""
        client = Mem0Client(base_url="http://localhost:8000", api_key="key")
        assert client._base_url == "http://localhost:8000"

    def test_init_no_api_key(self) -> None:
        """Client works without api_key (for local/unauthenticated instances)."""
        client = Mem0Client(base_url="http://localhost:8000")
        assert client._api_key is None

    def test_init_custom_timeout(self) -> None:
        """Client accepts custom timeout."""
        client = Mem0Client(api_key="key", timeout=60.0)
        assert client._timeout == 60.0


class TestMem0ClientClose:
    """Test closing the client."""

    @pytest.mark.asyncio
    async def test_close(self) -> None:
        """close() should close the underlying httpx client."""
        client = Mem0Client(api_key="test-key")
        client._client.aclose = AsyncMock()

        await client.close()

        client._client.aclose.assert_called_once()


# =============================================================================
# Create memory
# =============================================================================


class TestCreateMemory:
    """Test creating memories via the REST API."""

    @pytest.mark.asyncio
    async def test_create_sends_correct_payload(self) -> None:
        """create() should POST to /v1/memories/ with messages format."""
        client = Mem0Client(api_key="test-key")
        mock_resp = _mock_response(
            200,
            {"results": [{"id": "mem-abc", "memory": "User likes dark mode"}]},
        )

        client._client.request = AsyncMock(return_value=mock_resp)
        result = await client.create(
            content="User likes dark mode",
            project_id="proj-1",
            metadata={"importance": 0.8},
        )

        client._client.request.assert_called_once()
        args, kwargs = client._client.request.call_args
        assert args[0] == "POST"
        assert args[1] == "/v1/memories/"
        body = kwargs["json"]
        assert body["messages"] == [{"role": "user", "content": "User likes dark mode"}]
        assert body["user_id"] == "gobby"
        assert body["metadata"]["project_id"] == "proj-1"
        assert body["metadata"]["importance"] == 0.8
        assert result["results"][0]["id"] == "mem-abc"

    @pytest.mark.asyncio
    async def test_create_with_custom_user_id(self) -> None:
        """create() should use provided user_id."""
        client = Mem0Client(api_key="test-key", user_id="custom-user")
        mock_resp = _mock_response(200, {"results": [{"id": "mem-1"}]})

        client._client.request = AsyncMock(return_value=mock_resp)
        await client.create(content="test")
        body = client._client.request.call_args.kwargs["json"]
        assert body["user_id"] == "custom-user"


# =============================================================================
# Search memories
# =============================================================================


class TestSearchMemories:
    """Test searching memories via the REST API."""

    @pytest.mark.asyncio
    async def test_search_sends_correct_payload(self) -> None:
        """search() should POST to /v1/memories/search/ with query."""
        client = Mem0Client(api_key="test-key")
        mock_resp = _mock_response(
            200,
            {"results": [{"id": "mem-1", "memory": "dark mode", "score": 0.9}]},
        )

        client._client.request = AsyncMock(return_value=mock_resp)
        result = await client.search(query="dark mode", limit=5)

        args, kwargs = client._client.request.call_args
        assert args[0] == "POST"
        assert args[1] == "/v1/memories/search/"
        body = kwargs["json"]
        assert body["query"] == "dark mode"
        assert body["limit"] == 5
        assert len(result["results"]) == 1


# =============================================================================
# Get / Update / Delete single memory
# =============================================================================


class TestCRUDOperations:
    """Test get, update, and delete operations."""

    @pytest.mark.asyncio
    async def test_get_memory(self) -> None:
        """get() should GET /v1/memories/{id}/."""
        client = Mem0Client(api_key="test-key")
        mock_resp = _mock_response(200, {"id": "mem-1", "memory": "test content"})

        client._client.request = AsyncMock(return_value=mock_resp)
        result = await client.get("mem-1")

        args, kwargs = client._client.request.call_args
        assert args[0] == "GET"
        assert args[1] == "/v1/memories/mem-1/"
        assert result["id"] == "mem-1"

    @pytest.mark.asyncio
    async def test_update_memory(self) -> None:
        """update() should PUT /v1/memories/{id}/."""
        client = Mem0Client(api_key="test-key")
        mock_resp = _mock_response(200, {"id": "mem-1", "memory": "updated content"})

        client._client.request = AsyncMock(return_value=mock_resp)
        result = await client.update("mem-1", content="updated content")

        args, kwargs = client._client.request.call_args
        assert args[0] == "PUT"
        assert args[1] == "/v1/memories/mem-1/"
        body = kwargs["json"]
        assert body["text"] == "updated content"
        assert result["memory"] == "updated content"

    @pytest.mark.asyncio
    async def test_delete_memory(self) -> None:
        """delete() should DELETE /v1/memories/{id}/."""
        client = Mem0Client(api_key="test-key")
        mock_resp = _mock_response(200, {"message": "Memory deleted successfully"})

        client._client.request = AsyncMock(return_value=mock_resp)
        result = await client.delete("mem-1")

        args, kwargs = client._client.request.call_args
        assert args[0] == "DELETE"
        assert args[1] == "/v1/memories/mem-1/"
        assert result is True


# =============================================================================
# List memories
# =============================================================================


class TestListMemories:
    """Test listing memories."""

    @pytest.mark.asyncio
    async def test_list_memories(self) -> None:
        """list_all() should GET /v1/memories/ with user_id param."""
        client = Mem0Client(api_key="test-key")
        mock_resp = _mock_response(
            200,
            {"results": [{"id": "m1"}, {"id": "m2"}]},
        )

        client._client.request = AsyncMock(return_value=mock_resp)
        result = await client.list_all()

        args, kwargs = client._client.request.call_args
        assert args[0] == "GET"
        assert args[1] == "/v1/memories/"
        assert kwargs["params"]["user_id"] == "gobby"
        assert len(result["results"]) == 2


# =============================================================================
# History
# =============================================================================


class TestHistory:
    """Test getting memory history."""

    @pytest.mark.asyncio
    async def test_get_history(self) -> None:
        """get_history() should GET /v1/memories/{id}/history/."""
        client = Mem0Client(api_key="test-key")
        mock_resp = _mock_response(
            200,
            [{"id": "h1", "old_value": "v1", "new_value": "v2"}],
        )

        client._client.request = AsyncMock(return_value=mock_resp)
        result = await client.get_history("mem-1")

        args, kwargs = client._client.request.call_args
        assert args[1] == "/v1/memories/mem-1/history/"
        assert len(result) == 1
        assert result[0]["old_value"] == "v1"


# =============================================================================
# Error handling
# =============================================================================


class TestErrorHandling:
    """Test error handling for connection and API errors."""

    @pytest.mark.asyncio
    async def test_connection_error(self) -> None:
        """Connection errors should raise Mem0ConnectionError."""
        client = Mem0Client(api_key="test-key")
        client._client.request = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
        with pytest.raises(Mem0ConnectionError, match="Connection refused"):
            await client.get("mem-1")

    @pytest.mark.asyncio
    async def test_http_4xx_raises_api_error(self) -> None:
        """HTTP 4xx should raise Mem0APIError."""
        client = Mem0Client(api_key="test-key")
        mock_resp = _mock_response(404, {"detail": "Not found"})

        client._client.request = AsyncMock(return_value=mock_resp)
        with pytest.raises(Mem0APIError) as exc_info:
            await client.get("nonexistent")
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_http_5xx_raises_api_error(self) -> None:
        """HTTP 5xx should raise Mem0APIError."""
        client = Mem0Client(api_key="test-key")
        mock_resp = _mock_response(500, {"detail": "Internal server error"})

        client._client.request = AsyncMock(return_value=mock_resp)
        with pytest.raises(Mem0APIError) as exc_info:
            await client.create(content="test")
        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_timeout_raises_connection_error(self) -> None:
        """Timeout should raise Mem0ConnectionError."""
        client = Mem0Client(api_key="test-key", timeout=0.001)
        client._client.request = AsyncMock(side_effect=httpx.TimeoutException("Request timed out"))
        with pytest.raises(Mem0ConnectionError, match="timed out"):
            await client.get("mem-1")
