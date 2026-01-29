"""Tests for MemU memory backend.

Tests cover:
- MemUBackend class import and instantiation
- MemoryBackendProtocol implementation
- CRUD operations (create, get, update, delete)
- Search and list operations
- Close method for cleanup

Note: MemU (NevaMind-AI/memU via memu-py) is a structured memory service
with semantic search, distinct from Mem0 (mem0ai) which is in a separate file.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from gobby.memory.protocol import MemoryBackendProtocol, MemoryCapability

pytestmark = pytest.mark.unit

# =============================================================================
# Test: MemUBackend Import and Factory
# =============================================================================


class TestMemUBackendImport:
    """Tests for MemUBackend import and factory."""

    def test_memu_backend_importable(self) -> None:
        """Test that MemUBackend can be imported from backends module."""
        from gobby.memory.backends.memu import MemUBackend

        assert MemUBackend is not None

    def test_get_backend_supports_memu_type(self) -> None:
        """Test that get_backend factory supports 'memu' type."""
        from gobby.memory.backends import get_backend

        # Should not raise ValueError for 'memu' type
        # (will need config/mock for actual instantiation)
        with patch("gobby.memory.backends.memu.MemUBackend") as MockBackend:
            MockBackend.return_value = MagicMock(spec=MemoryBackendProtocol)
            backend = get_backend("memu", database_type="inmemory")
            assert backend is not None


class TestMemUBackendInstantiation:
    """Tests for MemUBackend instantiation."""

    def test_instantiate_with_defaults(self) -> None:
        """Test that MemUBackend can be instantiated with defaults."""
        from gobby.memory.backends.memu import MemUBackend

        # Mock the underlying MemU service
        with patch("memu.app.service.MemoryService"):
            backend = MemUBackend()
            assert backend is not None

    def test_instantiate_with_config(self) -> None:
        """Test that MemUBackend can be instantiated with config dict."""
        from gobby.memory.backends.memu import MemUBackend

        config = {
            "database_type": "inmemory",
            "user_id": "default-user",
        }

        with patch("memu.app.service.MemoryService"):
            backend = MemUBackend(**config)
            assert backend is not None

    def test_instantiate_with_sqlite(self) -> None:
        """Test MemUBackend with SQLite configuration."""
        from gobby.memory.backends.memu import MemUBackend

        with patch("memu.app.service.MemoryService") as MockService:
            backend = MemUBackend(database_type="sqlite", database_url="sqlite:///test.db")
            assert backend is not None
            # Verify database config was passed
            call_kwargs = MockService.call_args[1]
            assert call_kwargs.get("database_config", {}).get("type") == "sqlite"


# =============================================================================
# Test: MemUBackend Protocol Compliance
# =============================================================================


class TestMemUBackendProtocol:
    """Tests for MemoryBackendProtocol compliance."""

    def test_implements_protocol(self) -> None:
        """Test that MemUBackend implements MemoryBackendProtocol."""
        from gobby.memory.backends.memu import MemUBackend

        with patch("memu.app.service.MemoryService"):
            backend = MemUBackend()
            assert isinstance(backend, MemoryBackendProtocol)

    def test_capabilities_returns_set(self) -> None:
        """Test that capabilities() returns a set of MemoryCapability."""
        from gobby.memory.backends.memu import MemUBackend

        with patch("memu.app.service.MemoryService"):
            backend = MemUBackend()
            caps = backend.capabilities()

            assert isinstance(caps, set)
            # MemU should support basic CRUD
            assert MemoryCapability.CREATE in caps
            assert MemoryCapability.READ in caps
            assert MemoryCapability.DELETE in caps
            # MemU has semantic search
            assert MemoryCapability.SEARCH_SEMANTIC in caps


# =============================================================================
# Test: MemUBackend CRUD Operations
# =============================================================================


class TestMemUBackendCreate:
    """Tests for MemUBackend.create() method."""

    @pytest.mark.asyncio
    async def test_create_returns_memory_record(self):
        """Test that create() returns a MemoryRecord."""
        from gobby.memory.backends.memu import MemUBackend
        from gobby.memory.protocol import MemoryRecord

        with patch("memu.app.service.MemoryService") as MockService:
            mock_service = MagicMock()
            mock_service.create_memory_item.return_value = {"id": "mem-123"}
            MockService.return_value = mock_service

            backend = MemUBackend()
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
        """Test that create() passes user_id to MemU."""
        from gobby.memory.backends.memu import MemUBackend

        with patch("memu.app.service.MemoryService") as MockService:
            mock_service = MagicMock()
            mock_service.create_memory_item.return_value = {"id": "mem-456"}
            MockService.return_value = mock_service

            backend = MemUBackend()
            await backend.create(
                content="User preference",
                user_id="user-abc",
            )

            # Verify user was passed to MemU service
            mock_service.create_memory_item.assert_called_once()
            call_kwargs = mock_service.create_memory_item.call_args[1]
            assert call_kwargs.get("user", {}).get("user_id") == "user-abc"

    @pytest.mark.asyncio
    async def test_create_with_tags_as_categories(self):
        """Test that create() passes tags as categories to MemU."""
        from gobby.memory.backends.memu import MemUBackend

        with patch("memu.app.service.MemoryService") as MockService:
            mock_service = MagicMock()
            mock_service.create_memory_item.return_value = {"id": "mem-789"}
            MockService.return_value = mock_service

            backend = MemUBackend()
            await backend.create(
                content="Memory with tags",
                tags=["tag1", "tag2"],
            )

            mock_service.create_memory_item.assert_called_once()
            call_kwargs = mock_service.create_memory_item.call_args[1]
            assert call_kwargs.get("memory_categories") == ["tag1", "tag2"]


class TestMemUBackendGet:
    """Tests for MemUBackend.get() method."""

    @pytest.mark.asyncio
    async def test_get_returns_memory_record(self):
        """Test that get() returns a MemoryRecord when found."""
        from gobby.memory.backends.memu import MemUBackend
        from gobby.memory.protocol import MemoryRecord

        with patch("memu.app.service.MemoryService") as MockService:
            mock_service = MagicMock()
            # Mock get_memory_item to raise AttributeError so fallback to list is used
            mock_service.get_memory_item.side_effect = AttributeError()
            mock_service.list_memory_items.return_value = {
                "items": [
                    {
                        "id": "mem-123",
                        "memory_content": "Test content",
                        "created_at": "2026-01-19T12:00:00Z",
                    }
                ]
            }
            MockService.return_value = mock_service

            backend = MemUBackend()
            record = await backend.get("mem-123")

            assert isinstance(record, MemoryRecord)
            assert record.id == "mem-123"

    @pytest.mark.asyncio
    async def test_get_returns_none_when_not_found(self):
        """Test that get() returns None when memory not found."""
        from gobby.memory.backends.memu import MemUBackend

        with patch("memu.app.service.MemoryService") as MockService:
            mock_service = MagicMock()
            # Mock get_memory_item to raise AttributeError so fallback to list is used
            mock_service.get_memory_item.side_effect = AttributeError()
            mock_service.list_memory_items.return_value = {"items": []}
            MockService.return_value = mock_service

            backend = MemUBackend()
            result = await backend.get("nonexistent-id")

            assert result is None


class TestMemUBackendUpdate:
    """Tests for MemUBackend.update() method."""

    @pytest.mark.asyncio
    async def test_update_returns_updated_record(self):
        """Test that update() returns the updated MemoryRecord."""
        from gobby.memory.backends.memu import MemUBackend
        from gobby.memory.protocol import MemoryRecord

        with patch("memu.app.service.MemoryService") as MockService:
            mock_service = MagicMock()
            mock_service.update_memory_item.return_value = {"id": "mem-123"}
            mock_service.list_memory_items.return_value = {
                "items": [
                    {
                        "id": "mem-123",
                        "memory_content": "Updated content",
                        "created_at": "2026-01-19T12:00:00Z",
                    }
                ]
            }
            MockService.return_value = mock_service

            backend = MemUBackend()
            record = await backend.update(
                memory_id="mem-123",
                content="Updated content",
            )

            assert isinstance(record, MemoryRecord)
            mock_service.update_memory_item.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_raises_when_not_found(self):
        """Test that update() raises ValueError when memory not found."""
        from gobby.memory.backends.memu import MemUBackend

        with patch("memu.app.service.MemoryService") as MockService:
            mock_service = MagicMock()
            # Mock get_memory_item to raise AttributeError so fallback to list is used
            mock_service.get_memory_item.side_effect = AttributeError()
            mock_service.list_memory_items.return_value = {"items": []}
            MockService.return_value = mock_service

            backend = MemUBackend()
            with pytest.raises(ValueError, match="Memory not found"):
                await backend.update(memory_id="nonexistent", content="New content")


class TestMemUBackendDelete:
    """Tests for MemUBackend.delete() method."""

    @pytest.mark.asyncio
    async def test_delete_returns_true_on_success(self):
        """Test that delete() returns True when successful."""
        from gobby.memory.backends.memu import MemUBackend

        with patch("memu.app.service.MemoryService") as MockService:
            mock_service = MagicMock()
            mock_service.delete_memory_item.return_value = {"status": "deleted"}
            MockService.return_value = mock_service

            backend = MemUBackend()
            result = await backend.delete("mem-123")

            assert result is True
            mock_service.delete_memory_item.assert_called_once_with(memory_id="mem-123")

    @pytest.mark.asyncio
    async def test_delete_returns_false_when_not_found(self):
        """Test that delete() returns False when memory not found."""
        from gobby.memory.backends.memu import MemUBackend

        with patch("memu.app.service.MemoryService") as MockService:
            mock_service = MagicMock()
            mock_service.delete_memory_item.side_effect = Exception("Memory not found")
            MockService.return_value = mock_service

            backend = MemUBackend()
            result = await backend.delete("nonexistent-id")

            assert result is False


# =============================================================================
# Test: MemUBackend Search and List Operations
# =============================================================================


class TestMemUBackendSearch:
    """Tests for MemUBackend.search() method."""

    @pytest.mark.asyncio
    async def test_search_returns_list_of_records(self):
        """Test that search() returns a list of MemoryRecords."""
        from gobby.memory.backends.memu import MemUBackend
        from gobby.memory.protocol import MemoryQuery, MemoryRecord

        with patch("memu.app.service.MemoryService") as MockService:
            mock_service = MagicMock()
            mock_service.retrieve.return_value = {
                "items": [
                    {"id": "mem-1", "memory_content": "Result 1"},
                    {"id": "mem-2", "memory_content": "Result 2"},
                ]
            }
            MockService.return_value = mock_service

            backend = MemUBackend()
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

        with patch("memu.app.service.MemoryService") as MockService:
            mock_service = MagicMock()
            mock_service.retrieve.return_value = {"items": []}
            MockService.return_value = mock_service

            backend = MemUBackend()
            query = MemoryQuery(text="query", user_id="user-123")
            await backend.search(query)

            mock_service.retrieve.assert_called_once()
            call_kwargs = mock_service.retrieve.call_args[1]
            assert call_kwargs.get("where", {}).get("user_id") == "user-123"

    @pytest.mark.asyncio
    async def test_search_with_limit(self):
        """Test that search() respects limit parameter."""
        from gobby.memory.backends.memu import MemUBackend
        from gobby.memory.protocol import MemoryQuery

        with patch("memu.app.service.MemoryService") as MockService:
            mock_service = MagicMock()
            mock_service.retrieve.return_value = {
                "items": [{"id": f"mem-{i}", "memory_content": f"Result {i}"} for i in range(10)]
            }
            MockService.return_value = mock_service

            backend = MemUBackend()
            query = MemoryQuery(text="query", limit=5)
            results = await backend.search(query)

            # Should be limited to 5 results
            assert len(results) <= 5


class TestMemUBackendListMemories:
    """Tests for MemUBackend.list_memories() method."""

    @pytest.mark.asyncio
    async def test_list_memories_returns_list(self):
        """Test that list_memories() returns a list of MemoryRecords."""
        from gobby.memory.backends.memu import MemUBackend
        from gobby.memory.protocol import MemoryRecord

        with patch("memu.app.service.MemoryService") as MockService:
            mock_service = MagicMock()
            mock_service.list_memory_items.return_value = {
                "items": [
                    {"id": "mem-1", "memory_content": "Memory 1"},
                    {"id": "mem-2", "memory_content": "Memory 2"},
                ]
            }
            MockService.return_value = mock_service

            backend = MemUBackend()
            results = await backend.list_memories()

            assert isinstance(results, list)
            assert all(isinstance(r, MemoryRecord) for r in results)

    @pytest.mark.asyncio
    async def test_list_memories_with_user_id(self):
        """Test that list_memories() filters by user_id."""
        from gobby.memory.backends.memu import MemUBackend

        with patch("memu.app.service.MemoryService") as MockService:
            mock_service = MagicMock()
            mock_service.list_memory_items.return_value = {"items": []}
            MockService.return_value = mock_service

            backend = MemUBackend()
            await backend.list_memories(user_id="user-456")

            mock_service.list_memory_items.assert_called_once()
            call_kwargs = mock_service.list_memory_items.call_args[1]
            assert call_kwargs.get("where", {}).get("user_id") == "user-456"

    @pytest.mark.asyncio
    async def test_list_memories_with_limit(self):
        """Test that list_memories() respects limit parameter."""
        from gobby.memory.backends.memu import MemUBackend

        with patch("memu.app.service.MemoryService") as MockService:
            mock_service = MagicMock()
            mock_service.list_memory_items.return_value = {
                "items": [{"id": f"mem-{i}", "memory_content": f"Memory {i}"} for i in range(20)]
            }
            MockService.return_value = mock_service

            backend = MemUBackend()
            results = await backend.list_memories(limit=10)

            # Should be limited to 10 results
            assert len(results) <= 10


# =============================================================================
# Test: MemUBackend Close Method
# =============================================================================


class TestMemUBackendClose:
    """Tests for MemUBackend.close() method."""

    def test_close_exists(self) -> None:
        """Test that close() method exists for cleanup."""
        from gobby.memory.backends.memu import MemUBackend

        with patch("memu.app.service.MemoryService"):
            backend = MemUBackend()

            # close() should exist and not raise
            assert hasattr(backend, "close")

    def test_close_is_idempotent(self) -> None:
        """Test that close() can be called multiple times safely."""
        from gobby.memory.backends.memu import MemUBackend

        with patch("memu.app.service.MemoryService"):
            backend = MemUBackend()

            # Should not raise when called multiple times
            if hasattr(backend, "close"):
                backend.close()
                backend.close()  # Second call should be safe
