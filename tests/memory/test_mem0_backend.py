"""TDD tests for Mem0 memory backend.

RED phase - these tests define expected behavior before implementation exists.
Tests cover:
- Mem0Backend class import and instantiation
- MemoryBackendProtocol implementation
- CRUD operations (create, get, update, delete)
- Search and list operations
- Close method for cleanup

Note: Mem0 (mem0ai package) is a cloud-based semantic memory service,
distinct from MemU (memu-sdk) which is in a separate file (test_memu_backend.py).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from gobby.memory.protocol import MemoryBackendProtocol, MemoryCapability

# Check if mem0ai is available (optional dependency)
# Note: mem0ai depends on protobuf (>=5.29.0,<6.0.0) which is affected by
# CVE-2026-0994 in google.protobuf.json_format.ParseDict. The mem0 package
# itself is not vulnerable, but is optional here due to this supply-chain
# dependency concern until protobuf releases a patched version.
try:
    import mem0  # noqa: F401

    MEM0_AVAILABLE = True
except ImportError:
    MEM0_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not MEM0_AVAILABLE,
    reason="mem0ai package not installed (optional due to protobuf CVE-2026-0994)",
)

# =============================================================================
# Test: Mem0Backend Import and Factory
# =============================================================================


class TestMem0BackendImport:
    """TDD tests for Mem0Backend import and factory."""

    def test_mem0_backend_importable(self) -> None:
        """Test that Mem0Backend can be imported from backends module."""
        from gobby.memory.backends.mem0 import Mem0Backend

        assert Mem0Backend is not None

    def test_get_backend_supports_mem0_type(self) -> None:
        """Test that get_backend factory supports 'mem0' type."""
        from gobby.memory.backends import get_backend

        # Should not raise ValueError for 'mem0' type
        # (will need config/mock for actual instantiation)
        with patch("gobby.memory.backends.mem0.Mem0Backend") as MockBackend:
            MockBackend.return_value = MagicMock(spec=MemoryBackendProtocol)
            backend = get_backend("mem0", api_key="test-key")
            assert backend is not None


class TestMem0BackendInstantiation:
    """TDD tests for Mem0Backend instantiation."""

    def test_instantiate_with_api_key(self) -> None:
        """Test that Mem0Backend can be instantiated with API key."""
        from gobby.memory.backends.mem0 import Mem0Backend

        # Mock the underlying Mem0 client
        with patch("mem0.MemoryClient"):
            backend = Mem0Backend(api_key="test-api-key")
            assert backend is not None

    def test_instantiate_with_config(self) -> None:
        """Test that Mem0Backend can be instantiated with config dict."""
        from gobby.memory.backends.mem0 import Mem0Backend

        config = {
            "api_key": "test-key",
            "user_id": "default-user",
            "org_id": "test-org",
        }

        with patch("mem0.MemoryClient"):
            backend = Mem0Backend(**config)
            assert backend is not None


# =============================================================================
# Test: Mem0Backend Protocol Compliance
# =============================================================================


class TestMem0BackendProtocol:
    """TDD tests for MemoryBackendProtocol compliance."""

    def test_implements_protocol(self) -> None:
        """Test that Mem0Backend implements MemoryBackendProtocol."""
        from gobby.memory.backends.mem0 import Mem0Backend

        with patch("mem0.MemoryClient"):
            backend = Mem0Backend(api_key="test-key")
            assert isinstance(backend, MemoryBackendProtocol)

    def test_capabilities_returns_set(self) -> None:
        """Test that capabilities() returns a set of MemoryCapability."""
        from gobby.memory.backends.mem0 import Mem0Backend

        with patch("mem0.MemoryClient"):
            backend = Mem0Backend(api_key="test-key")
            caps = backend.capabilities()

            assert isinstance(caps, set)
            # Mem0 should support at least basic CRUD
            assert MemoryCapability.CREATE in caps
            assert MemoryCapability.READ in caps
            assert MemoryCapability.DELETE in caps
            # Mem0 has semantic search
            assert MemoryCapability.SEARCH_SEMANTIC in caps


# =============================================================================
# Test: Mem0Backend CRUD Operations
# =============================================================================


class TestMem0BackendCreate:
    """TDD tests for Mem0Backend.create() method."""

    @pytest.mark.asyncio
    async def test_create_returns_memory_record(self):
        """Test that create() returns a MemoryRecord."""
        from gobby.memory.backends.mem0 import Mem0Backend
        from gobby.memory.protocol import MemoryRecord

        with patch("mem0.MemoryClient") as MockClient:
            mock_client = MagicMock()
            mock_client.add.return_value = {"id": "mem-123"}
            MockClient.return_value = mock_client

            backend = Mem0Backend(api_key="test-key")
            record = await backend.create(
                content="Test memory content",
                memory_type="fact",
                importance=0.8,
            )

            assert isinstance(record, MemoryRecord)
            assert record.content == "Test memory content"
            assert record.id is not None

    @pytest.mark.asyncio
    async def test_create_with_user_id(self):
        """Test that create() passes user_id to Mem0."""
        from gobby.memory.backends.mem0 import Mem0Backend

        with patch("mem0.MemoryClient") as MockClient:
            mock_client = MagicMock()
            mock_client.add.return_value = {"id": "mem-456"}
            MockClient.return_value = mock_client

            backend = Mem0Backend(api_key="test-key")
            await backend.create(
                content="User preference",
                user_id="user-abc",
            )

            # Verify user_id was passed to Mem0 client
            mock_client.add.assert_called_once()
            call_kwargs = mock_client.add.call_args[1]
            assert call_kwargs.get("user_id") == "user-abc"

    @pytest.mark.asyncio
    async def test_create_with_metadata(self):
        """Test that create() passes metadata to Mem0."""
        from gobby.memory.backends.mem0 import Mem0Backend

        with patch("mem0.MemoryClient") as MockClient:
            mock_client = MagicMock()
            mock_client.add.return_value = {"id": "mem-789"}
            MockClient.return_value = mock_client

            backend = Mem0Backend(api_key="test-key")
            await backend.create(
                content="Memory with metadata",
                metadata={"custom_field": "value"},
            )

            mock_client.add.assert_called_once()


class TestMem0BackendGet:
    """TDD tests for Mem0Backend.get() method."""

    @pytest.mark.asyncio
    async def test_get_returns_memory_record(self):
        """Test that get() returns a MemoryRecord when found."""
        from gobby.memory.backends.mem0 import Mem0Backend
        from gobby.memory.protocol import MemoryRecord

        with patch("mem0.MemoryClient") as MockClient:
            mock_client = MagicMock()
            mock_client.get.return_value = {
                "id": "mem-123",
                "memory": "Test content",
                "created_at": "2026-01-19T12:00:00Z",
            }
            MockClient.return_value = mock_client

            backend = Mem0Backend(api_key="test-key")
            record = await backend.get("mem-123")

            assert isinstance(record, MemoryRecord)
            assert record.id == "mem-123"

    @pytest.mark.asyncio
    async def test_get_returns_none_when_not_found(self):
        """Test that get() returns None when memory not found."""
        from gobby.memory.backends.mem0 import Mem0Backend

        with patch("mem0.MemoryClient") as MockClient:
            mock_client = MagicMock()
            mock_client.get.return_value = None
            MockClient.return_value = mock_client

            backend = Mem0Backend(api_key="test-key")
            result = await backend.get("nonexistent-id")

            assert result is None


class TestMem0BackendUpdate:
    """TDD tests for Mem0Backend.update() method."""

    @pytest.mark.asyncio
    async def test_update_returns_updated_record(self):
        """Test that update() returns the updated MemoryRecord."""
        from gobby.memory.backends.mem0 import Mem0Backend
        from gobby.memory.protocol import MemoryRecord

        with patch("mem0.MemoryClient") as MockClient:
            mock_client = MagicMock()
            mock_client.update.return_value = {"id": "mem-123"}
            mock_client.get.return_value = {
                "id": "mem-123",
                "memory": "Updated content",
                "created_at": "2026-01-19T12:00:00Z",
            }
            MockClient.return_value = mock_client

            backend = Mem0Backend(api_key="test-key")
            record = await backend.update(
                memory_id="mem-123",
                content="Updated content",
            )

            assert isinstance(record, MemoryRecord)
            mock_client.update.assert_called_once()


class TestMem0BackendDelete:
    """TDD tests for Mem0Backend.delete() method."""

    @pytest.mark.asyncio
    async def test_delete_returns_true_on_success(self):
        """Test that delete() returns True when successful."""
        from gobby.memory.backends.mem0 import Mem0Backend

        with patch("mem0.MemoryClient") as MockClient:
            mock_client = MagicMock()
            mock_client.delete.return_value = {"status": "deleted"}
            MockClient.return_value = mock_client

            backend = Mem0Backend(api_key="test-key")
            result = await backend.delete("mem-123")

            assert result is True
            mock_client.delete.assert_called_once_with("mem-123")

    @pytest.mark.asyncio
    async def test_delete_returns_false_when_not_found(self):
        """Test that delete() returns False when memory not found."""
        from gobby.memory.backends.mem0 import Mem0Backend

        with patch("mem0.MemoryClient") as MockClient:
            mock_client = MagicMock()
            mock_client.delete.side_effect = Exception("Memory not found")
            MockClient.return_value = mock_client

            backend = Mem0Backend(api_key="test-key")
            result = await backend.delete("nonexistent-id")

            assert result is False


# =============================================================================
# Test: Mem0Backend Search and List Operations
# =============================================================================


class TestMem0BackendSearch:
    """TDD tests for Mem0Backend.search() method."""

    @pytest.mark.asyncio
    async def test_search_returns_list_of_records(self):
        """Test that search() returns a list of MemoryRecords."""
        from gobby.memory.backends.mem0 import Mem0Backend
        from gobby.memory.protocol import MemoryQuery, MemoryRecord

        with patch("mem0.MemoryClient") as MockClient:
            mock_client = MagicMock()
            mock_client.search.return_value = {
                "results": [
                    {"id": "mem-1", "memory": "Result 1", "score": 0.9},
                    {"id": "mem-2", "memory": "Result 2", "score": 0.8},
                ]
            }
            MockClient.return_value = mock_client

            backend = Mem0Backend(api_key="test-key")
            query = MemoryQuery(text="search query")
            results = await backend.search(query)

            assert isinstance(results, list)
            assert len(results) == 2
            assert all(isinstance(r, MemoryRecord) for r in results)

    @pytest.mark.asyncio
    async def test_search_with_user_id_filter(self):
        """Test that search() filters by user_id."""
        from gobby.memory.backends.mem0 import Mem0Backend
        from gobby.memory.protocol import MemoryQuery

        with patch("mem0.MemoryClient") as MockClient:
            mock_client = MagicMock()
            mock_client.search.return_value = {"results": []}
            MockClient.return_value = mock_client

            backend = Mem0Backend(api_key="test-key")
            query = MemoryQuery(text="query", user_id="user-123")
            await backend.search(query)

            mock_client.search.assert_called_once()
            call_kwargs = mock_client.search.call_args[1]
            assert call_kwargs.get("user_id") == "user-123"

    @pytest.mark.asyncio
    async def test_search_with_limit(self):
        """Test that search() respects limit parameter."""
        from gobby.memory.backends.mem0 import Mem0Backend
        from gobby.memory.protocol import MemoryQuery

        with patch("mem0.MemoryClient") as MockClient:
            mock_client = MagicMock()
            mock_client.search.return_value = {"results": []}
            MockClient.return_value = mock_client

            backend = Mem0Backend(api_key="test-key")
            query = MemoryQuery(text="query", limit=5)
            await backend.search(query)

            mock_client.search.assert_called_once()
            call_kwargs = mock_client.search.call_args[1]
            assert call_kwargs.get("limit") == 5


class TestMem0BackendListMemories:
    """TDD tests for Mem0Backend.list_memories() method."""

    @pytest.mark.asyncio
    async def test_list_memories_returns_list(self):
        """Test that list_memories() returns a list of MemoryRecords."""
        from gobby.memory.backends.mem0 import Mem0Backend
        from gobby.memory.protocol import MemoryRecord

        with patch("mem0.MemoryClient") as MockClient:
            mock_client = MagicMock()
            mock_client.get_all.return_value = {
                "results": [
                    {"id": "mem-1", "memory": "Memory 1"},
                    {"id": "mem-2", "memory": "Memory 2"},
                ]
            }
            MockClient.return_value = mock_client

            backend = Mem0Backend(api_key="test-key")
            results = await backend.list_memories()

            assert isinstance(results, list)
            assert all(isinstance(r, MemoryRecord) for r in results)

    @pytest.mark.asyncio
    async def test_list_memories_with_user_id(self):
        """Test that list_memories() filters by user_id."""
        from gobby.memory.backends.mem0 import Mem0Backend

        with patch("mem0.MemoryClient") as MockClient:
            mock_client = MagicMock()
            mock_client.get_all.return_value = {"results": []}
            MockClient.return_value = mock_client

            backend = Mem0Backend(api_key="test-key")
            await backend.list_memories(user_id="user-456")

            mock_client.get_all.assert_called_once()
            call_kwargs = mock_client.get_all.call_args[1]
            assert call_kwargs.get("user_id") == "user-456"

    @pytest.mark.asyncio
    async def test_list_memories_with_limit(self):
        """Test that list_memories() respects limit parameter."""
        from gobby.memory.backends.mem0 import Mem0Backend

        with patch("mem0.MemoryClient") as MockClient:
            mock_client = MagicMock()
            mock_client.get_all.return_value = {"results": []}
            MockClient.return_value = mock_client

            backend = Mem0Backend(api_key="test-key")
            await backend.list_memories(limit=10)

            mock_client.get_all.assert_called_once()


# =============================================================================
# Test: Mem0Backend Close Method
# =============================================================================


class TestMem0BackendClose:
    """TDD tests for Mem0Backend.close() method."""

    @pytest.mark.asyncio
    async def test_close_exists(self):
        """Test that close() method exists for cleanup."""
        from gobby.memory.backends.mem0 import Mem0Backend

        with patch("mem0.MemoryClient"):
            backend = Mem0Backend(api_key="test-key")

            # close() should exist and not raise
            assert hasattr(backend, "close")

    @pytest.mark.asyncio
    async def test_close_is_idempotent(self):
        """Test that close() can be called multiple times safely."""
        from gobby.memory.backends.mem0 import Mem0Backend

        with patch("mem0.MemoryClient"):
            backend = Mem0Backend(api_key="test-key")

            # Should not raise when called multiple times
            if hasattr(backend, "close"):
                backend.close()
                backend.close()  # Second call should be safe
