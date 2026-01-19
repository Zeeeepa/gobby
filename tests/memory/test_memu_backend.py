"""TDD tests for MemU (Mem0) memory backend.

RED phase - these tests define expected behavior before implementation exists.
Tests cover:
- MemUBackend class import and instantiation
- MemoryBackendProtocol implementation
- CRUD operations (create, get, update, delete)
- Search and list operations
- Close method for cleanup
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.memory.protocol import MemoryBackendProtocol, MemoryCapability


# =============================================================================
# Test: MemUBackend Import and Factory
# =============================================================================


class TestMemUBackendImport:
    """TDD tests for MemUBackend import and factory."""

    def test_memu_backend_importable(self):
        """Test that MemUBackend can be imported from backends module."""
        from gobby.memory.backends.memu import MemUBackend

        assert MemUBackend is not None

    def test_get_backend_supports_memu_type(self):
        """Test that get_backend factory supports 'memu' type."""
        from gobby.memory.backends import get_backend

        # Should not raise ValueError for 'memu' type
        # (will need config/mock for actual instantiation)
        with patch("gobby.memory.backends.memu.MemUBackend") as MockBackend:
            MockBackend.return_value = MagicMock(spec=MemoryBackendProtocol)
            backend = get_backend("memu", api_key="test-key")
            assert backend is not None


class TestMemUBackendInstantiation:
    """TDD tests for MemUBackend instantiation."""

    def test_instantiate_with_api_key(self):
        """Test that MemUBackend can be instantiated with API key."""
        from gobby.memory.backends.memu import MemUBackend

        # Mock the underlying Mem0 client
        with patch("gobby.memory.backends.memu.MemoryClient"):
            backend = MemUBackend(api_key="test-api-key")
            assert backend is not None

    def test_instantiate_with_config(self):
        """Test that MemUBackend can be instantiated with config dict."""
        from gobby.memory.backends.memu import MemUBackend

        config = {
            "api_key": "test-key",
            "user_id": "default-user",
            "org_id": "test-org",
        }

        with patch("gobby.memory.backends.memu.MemoryClient"):
            backend = MemUBackend(**config)
            assert backend is not None


# =============================================================================
# Test: MemUBackend Protocol Compliance
# =============================================================================


class TestMemUBackendProtocol:
    """TDD tests for MemoryBackendProtocol compliance."""

    def test_implements_protocol(self):
        """Test that MemUBackend implements MemoryBackendProtocol."""
        from gobby.memory.backends.memu import MemUBackend

        with patch("gobby.memory.backends.memu.MemoryClient"):
            backend = MemUBackend(api_key="test-key")
            assert isinstance(backend, MemoryBackendProtocol)

    def test_capabilities_returns_set(self):
        """Test that capabilities() returns a set of MemoryCapability."""
        from gobby.memory.backends.memu import MemUBackend

        with patch("gobby.memory.backends.memu.MemoryClient"):
            backend = MemUBackend(api_key="test-key")
            caps = backend.capabilities()

            assert isinstance(caps, set)
            # MemU should support at least basic CRUD
            assert MemoryCapability.CREATE in caps
            assert MemoryCapability.READ in caps
            assert MemoryCapability.DELETE in caps
            # MemU has semantic search
            assert MemoryCapability.SEARCH_SEMANTIC in caps


# =============================================================================
# Test: MemUBackend CRUD Operations
# =============================================================================


class TestMemUBackendCreate:
    """TDD tests for MemUBackend.create() method."""

    @pytest.mark.asyncio
    async def test_create_returns_memory_record(self):
        """Test that create() returns a MemoryRecord."""
        from gobby.memory.backends.memu import MemUBackend
        from gobby.memory.protocol import MemoryRecord

        with patch("gobby.memory.backends.memu.MemoryClient") as MockClient:
            mock_client = MagicMock()
            mock_client.add.return_value = {"id": "mem-123"}
            MockClient.return_value = mock_client

            backend = MemUBackend(api_key="test-key")
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
        from gobby.memory.backends.memu import MemUBackend

        with patch("gobby.memory.backends.memu.MemoryClient") as MockClient:
            mock_client = MagicMock()
            mock_client.add.return_value = {"id": "mem-456"}
            MockClient.return_value = mock_client

            backend = MemUBackend(api_key="test-key")
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
        from gobby.memory.backends.memu import MemUBackend

        with patch("gobby.memory.backends.memu.MemoryClient") as MockClient:
            mock_client = MagicMock()
            mock_client.add.return_value = {"id": "mem-789"}
            MockClient.return_value = mock_client

            backend = MemUBackend(api_key="test-key")
            await backend.create(
                content="Memory with metadata",
                metadata={"custom_field": "value"},
            )

            mock_client.add.assert_called_once()


class TestMemUBackendGet:
    """TDD tests for MemUBackend.get() method."""

    @pytest.mark.asyncio
    async def test_get_returns_memory_record(self):
        """Test that get() returns a MemoryRecord when found."""
        from gobby.memory.backends.memu import MemUBackend
        from gobby.memory.protocol import MemoryRecord

        with patch("gobby.memory.backends.memu.MemoryClient") as MockClient:
            mock_client = MagicMock()
            mock_client.get.return_value = {
                "id": "mem-123",
                "memory": "Test content",
                "created_at": "2026-01-19T12:00:00Z",
            }
            MockClient.return_value = mock_client

            backend = MemUBackend(api_key="test-key")
            record = await backend.get("mem-123")

            assert isinstance(record, MemoryRecord)
            assert record.id == "mem-123"

    @pytest.mark.asyncio
    async def test_get_returns_none_when_not_found(self):
        """Test that get() returns None when memory not found."""
        from gobby.memory.backends.memu import MemUBackend

        with patch("gobby.memory.backends.memu.MemoryClient") as MockClient:
            mock_client = MagicMock()
            mock_client.get.return_value = None
            MockClient.return_value = mock_client

            backend = MemUBackend(api_key="test-key")
            result = await backend.get("nonexistent-id")

            assert result is None


class TestMemUBackendUpdate:
    """TDD tests for MemUBackend.update() method."""

    @pytest.mark.asyncio
    async def test_update_returns_updated_record(self):
        """Test that update() returns the updated MemoryRecord."""
        from gobby.memory.backends.memu import MemUBackend
        from gobby.memory.protocol import MemoryRecord

        with patch("gobby.memory.backends.memu.MemoryClient") as MockClient:
            mock_client = MagicMock()
            mock_client.update.return_value = {"id": "mem-123"}
            mock_client.get.return_value = {
                "id": "mem-123",
                "memory": "Updated content",
                "created_at": "2026-01-19T12:00:00Z",
            }
            MockClient.return_value = mock_client

            backend = MemUBackend(api_key="test-key")
            record = await backend.update(
                memory_id="mem-123",
                content="Updated content",
            )

            assert isinstance(record, MemoryRecord)
            mock_client.update.assert_called_once()


class TestMemUBackendDelete:
    """TDD tests for MemUBackend.delete() method."""

    @pytest.mark.asyncio
    async def test_delete_returns_true_on_success(self):
        """Test that delete() returns True when successful."""
        from gobby.memory.backends.memu import MemUBackend

        with patch("gobby.memory.backends.memu.MemoryClient") as MockClient:
            mock_client = MagicMock()
            mock_client.delete.return_value = {"status": "deleted"}
            MockClient.return_value = mock_client

            backend = MemUBackend(api_key="test-key")
            result = await backend.delete("mem-123")

            assert result is True
            mock_client.delete.assert_called_once_with(memory_id="mem-123")

    @pytest.mark.asyncio
    async def test_delete_returns_false_when_not_found(self):
        """Test that delete() returns False when memory not found."""
        from gobby.memory.backends.memu import MemUBackend

        with patch("gobby.memory.backends.memu.MemoryClient") as MockClient:
            mock_client = MagicMock()
            mock_client.delete.side_effect = Exception("Memory not found")
            MockClient.return_value = mock_client

            backend = MemUBackend(api_key="test-key")
            result = await backend.delete("nonexistent-id")

            assert result is False


# =============================================================================
# Test: MemUBackend Search and List Operations
# =============================================================================


class TestMemUBackendSearch:
    """TDD tests for MemUBackend.search() method."""

    @pytest.mark.asyncio
    async def test_search_returns_list_of_records(self):
        """Test that search() returns a list of MemoryRecords."""
        from gobby.memory.backends.memu import MemUBackend
        from gobby.memory.protocol import MemoryQuery, MemoryRecord

        with patch("gobby.memory.backends.memu.MemoryClient") as MockClient:
            mock_client = MagicMock()
            mock_client.search.return_value = [
                {"id": "mem-1", "memory": "Result 1", "score": 0.9},
                {"id": "mem-2", "memory": "Result 2", "score": 0.8},
            ]
            MockClient.return_value = mock_client

            backend = MemUBackend(api_key="test-key")
            query = MemoryQuery(text="search query")
            results = await backend.search(query)

            assert isinstance(results, list)
            assert len(results) == 2
            assert all(isinstance(r, MemoryRecord) for r in results)

    @pytest.mark.asyncio
    async def test_search_with_user_id_filter(self):
        """Test that search() filters by user_id."""
        from gobby.memory.backends.memu import MemUBackend
        from gobby.memory.protocol import MemoryQuery

        with patch("gobby.memory.backends.memu.MemoryClient") as MockClient:
            mock_client = MagicMock()
            mock_client.search.return_value = []
            MockClient.return_value = mock_client

            backend = MemUBackend(api_key="test-key")
            query = MemoryQuery(text="query", user_id="user-123")
            await backend.search(query)

            mock_client.search.assert_called_once()
            call_kwargs = mock_client.search.call_args[1]
            assert call_kwargs.get("user_id") == "user-123"

    @pytest.mark.asyncio
    async def test_search_with_limit(self):
        """Test that search() respects limit parameter."""
        from gobby.memory.backends.memu import MemUBackend
        from gobby.memory.protocol import MemoryQuery

        with patch("gobby.memory.backends.memu.MemoryClient") as MockClient:
            mock_client = MagicMock()
            mock_client.search.return_value = []
            MockClient.return_value = mock_client

            backend = MemUBackend(api_key="test-key")
            query = MemoryQuery(text="query", limit=5)
            await backend.search(query)

            mock_client.search.assert_called_once()
            call_kwargs = mock_client.search.call_args[1]
            assert call_kwargs.get("limit") == 5


class TestMemUBackendListMemories:
    """TDD tests for MemUBackend.list_memories() method."""

    @pytest.mark.asyncio
    async def test_list_memories_returns_list(self):
        """Test that list_memories() returns a list of MemoryRecords."""
        from gobby.memory.backends.memu import MemUBackend
        from gobby.memory.protocol import MemoryRecord

        with patch("gobby.memory.backends.memu.MemoryClient") as MockClient:
            mock_client = MagicMock()
            mock_client.get_all.return_value = [
                {"id": "mem-1", "memory": "Memory 1"},
                {"id": "mem-2", "memory": "Memory 2"},
            ]
            MockClient.return_value = mock_client

            backend = MemUBackend(api_key="test-key")
            results = await backend.list_memories()

            assert isinstance(results, list)
            assert all(isinstance(r, MemoryRecord) for r in results)

    @pytest.mark.asyncio
    async def test_list_memories_with_user_id(self):
        """Test that list_memories() filters by user_id."""
        from gobby.memory.backends.memu import MemUBackend

        with patch("gobby.memory.backends.memu.MemoryClient") as MockClient:
            mock_client = MagicMock()
            mock_client.get_all.return_value = []
            MockClient.return_value = mock_client

            backend = MemUBackend(api_key="test-key")
            await backend.list_memories(user_id="user-456")

            mock_client.get_all.assert_called_once()
            call_kwargs = mock_client.get_all.call_args[1]
            assert call_kwargs.get("user_id") == "user-456"

    @pytest.mark.asyncio
    async def test_list_memories_with_limit(self):
        """Test that list_memories() respects limit parameter."""
        from gobby.memory.backends.memu import MemUBackend

        with patch("gobby.memory.backends.memu.MemoryClient") as MockClient:
            mock_client = MagicMock()
            mock_client.get_all.return_value = []
            MockClient.return_value = mock_client

            backend = MemUBackend(api_key="test-key")
            await backend.list_memories(limit=10)

            mock_client.get_all.assert_called_once()


# =============================================================================
# Test: MemUBackend Close Method
# =============================================================================


class TestMemUBackendClose:
    """TDD tests for MemUBackend.close() method."""

    @pytest.mark.asyncio
    async def test_close_exists(self):
        """Test that close() method exists for cleanup."""
        from gobby.memory.backends.memu import MemUBackend

        with patch("gobby.memory.backends.memu.MemoryClient"):
            backend = MemUBackend(api_key="test-key")

            # close() should exist and not raise
            assert hasattr(backend, "close")

    @pytest.mark.asyncio
    async def test_close_is_idempotent(self):
        """Test that close() can be called multiple times safely."""
        from gobby.memory.backends.memu import MemUBackend

        with patch("gobby.memory.backends.memu.MemoryClient"):
            backend = MemUBackend(api_key="test-key")

            # Should not raise when called multiple times
            if hasattr(backend, "close"):
                backend.close()
                backend.close()  # Second call should be safe
