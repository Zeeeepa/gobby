"""Tests for memory backend factory.

Tests the pluggable backend system:
- get_backend() factory function
- SQLite backend type
- Null backend type for testing
- Error handling for unknown backend types

TDD RED phase: These tests define expected behavior before implementation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

# These imports should fail until backends/__init__.py is implemented
from gobby.memory.backends import get_backend
from gobby.memory.protocol import MemoryBackendProtocol, MemoryCapability

if TYPE_CHECKING:
    from gobby.storage.database import LocalDatabase

pytestmark = pytest.mark.unit

# =============================================================================
# Test: get_backend Factory Function
# =============================================================================


class TestGetBackend:
    """Tests for the get_backend factory function."""

    def test_get_backend_exists(self) -> None:
        """Test that get_backend function is importable."""
        assert callable(get_backend)

    def test_get_backend_returns_protocol(self, temp_db: LocalDatabase) -> None:
        """Test that get_backend returns a MemoryBackendProtocol instance."""
        backend = get_backend("sqlite", database=temp_db)
        assert isinstance(backend, MemoryBackendProtocol)

    def test_get_backend_unknown_type_raises(self) -> None:
        """Test that unknown backend type raises ValueError."""
        with pytest.raises(ValueError, match="Unknown backend type"):
            get_backend("unknown_backend_type")

    def test_get_backend_null_type(self) -> None:
        """Test that 'null' backend type returns a valid backend."""
        backend = get_backend("null")
        assert isinstance(backend, MemoryBackendProtocol)

    def test_get_backend_sqlite_type(self, temp_db: LocalDatabase) -> None:
        """Test that 'sqlite' backend type returns SQLite backend."""
        backend = get_backend("sqlite", database=temp_db)
        assert isinstance(backend, MemoryBackendProtocol)
        # SQLite backend should support full CRUD capabilities
        caps = backend.capabilities()
        assert MemoryCapability.CREATE in caps
        assert MemoryCapability.READ in caps
        assert MemoryCapability.UPDATE in caps
        assert MemoryCapability.DELETE in caps


# =============================================================================
# Test: NullBackend
# =============================================================================


class TestNullBackend:
    """Tests for the NullBackend implementation (for testing purposes)."""

    def test_null_backend_capabilities(self) -> None:
        """Test that NullBackend declares its capabilities."""
        backend = get_backend("null")
        caps = backend.capabilities()
        assert isinstance(caps, set)
        # NullBackend should support basic operations
        assert MemoryCapability.CREATE in caps
        assert MemoryCapability.READ in caps

    @pytest.mark.asyncio
    async def test_null_backend_create(self):
        """Test that NullBackend.create() works."""
        backend = get_backend("null")
        record = await backend.create("test memory content")
        assert record is not None
        assert record.content == "test memory content"
        assert record.id is not None

    @pytest.mark.asyncio
    async def test_null_backend_get_returns_none(self):
        """Test that NullBackend.get() returns None (no persistence)."""
        backend = get_backend("null")
        result = await backend.get("nonexistent-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_null_backend_search_returns_empty(self):
        """Test that NullBackend.search() returns empty list."""
        from gobby.memory.protocol import MemoryQuery

        backend = get_backend("null")
        query = MemoryQuery(text="test")
        results = await backend.search(query)
        assert results == []

    @pytest.mark.asyncio
    async def test_null_backend_delete_returns_false(self):
        """Test that NullBackend.delete() returns False (nothing to delete)."""
        backend = get_backend("null")
        result = await backend.delete("nonexistent-id")
        assert result is False

    @pytest.mark.asyncio
    async def test_null_backend_list_returns_empty(self):
        """Test that NullBackend.list_memories() returns empty list."""
        backend = get_backend("null")
        results = await backend.list_memories()
        assert results == []


# =============================================================================
# Test: SQLiteBackend
# =============================================================================


class TestSQLiteBackend:
    """Tests for the SQLiteBackend implementation."""

    def test_sqlite_backend_capabilities(self, temp_db: LocalDatabase) -> None:
        """Test that SQLiteBackend declares full capabilities."""
        backend = get_backend("sqlite", database=temp_db)
        caps = backend.capabilities()
        assert isinstance(caps, set)
        # SQLite should support all basic operations
        assert MemoryCapability.CREATE in caps
        assert MemoryCapability.READ in caps
        assert MemoryCapability.UPDATE in caps
        assert MemoryCapability.DELETE in caps
        assert MemoryCapability.SEARCH_TEXT in caps
        assert MemoryCapability.TAGS in caps
        assert MemoryCapability.IMPORTANCE in caps

    @pytest.mark.asyncio
    async def test_sqlite_backend_create_and_get(self, temp_db: LocalDatabase):
        """Test SQLiteBackend create and get operations."""
        backend = get_backend("sqlite", database=temp_db)

        # Create a memory
        record = await backend.create(
            content="Test memory for SQLite backend",
            memory_type="fact",
            importance=0.8,
            tags=["test", "sqlite"],
        )
        assert record is not None
        assert record.id is not None
        assert record.content == "Test memory for SQLite backend"
        assert record.importance == 0.8

        # Get the memory back
        retrieved = await backend.get(record.id)
        assert retrieved is not None
        assert retrieved.id == record.id
        assert retrieved.content == record.content

    @pytest.mark.asyncio
    async def test_sqlite_backend_update(self, temp_db: LocalDatabase):
        """Test SQLiteBackend update operation."""
        backend = get_backend("sqlite", database=temp_db)

        # Create a memory
        record = await backend.create(content="Original content")

        # Update it
        updated = await backend.update(
            record.id,
            content="Updated content",
            importance=0.9,
        )
        assert updated.content == "Updated content"
        assert updated.importance == 0.9

    @pytest.mark.asyncio
    async def test_sqlite_backend_delete(self, temp_db: LocalDatabase):
        """Test SQLiteBackend delete operation."""
        backend = get_backend("sqlite", database=temp_db)

        # Create a memory
        record = await backend.create(content="To be deleted")

        # Delete it
        result = await backend.delete(record.id)
        assert result is True

        # Verify it's gone
        retrieved = await backend.get(record.id)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_sqlite_backend_search(self, temp_db: LocalDatabase):
        """Test SQLiteBackend search operation."""
        from gobby.memory.protocol import MemoryQuery

        backend = get_backend("sqlite", database=temp_db)

        # Create some memories
        await backend.create(content="Python programming language")
        await backend.create(content="JavaScript for web development")
        await backend.create(content="Python web frameworks like Flask")

        # Search for Python
        query = MemoryQuery(text="Python")
        results = await backend.search(query)

        assert len(results) >= 2
        assert all("Python" in r.content for r in results)

    @pytest.mark.asyncio
    async def test_sqlite_backend_list_memories(self, temp_db: LocalDatabase):
        """Test SQLiteBackend list_memories operation."""
        backend = get_backend("sqlite", database=temp_db)

        # Create some memories
        await backend.create(content="Memory 1", memory_type="fact")
        await backend.create(content="Memory 2", memory_type="preference")
        await backend.create(content="Memory 3", memory_type="fact")

        # List all
        all_results = await backend.list_memories()
        assert len(all_results) >= 3

        # List by type
        facts = await backend.list_memories(memory_type="fact")
        assert all(r.memory_type == "fact" for r in facts)

    @pytest.mark.asyncio
    async def test_sqlite_backend_list_with_limit(self, temp_db: LocalDatabase):
        """Test SQLiteBackend list_memories with limit."""
        backend = get_backend("sqlite", database=temp_db)

        # Create several memories
        for i in range(5):
            await backend.create(content=f"Memory {i}")

        # List with limit
        results = await backend.list_memories(limit=3)
        assert len(results) == 3


# =============================================================================
# Test: Module Exports
# =============================================================================


class TestModuleExports:
    """Tests for module exports."""

    def test_get_backend_exported(self) -> None:
        """Test that get_backend is exported from backends module."""
        from gobby.memory import backends

        assert hasattr(backends, "get_backend")
        assert callable(backends.get_backend)

    def test_backend_classes_not_directly_exported(self) -> None:
        """Test that backend implementations are not directly exported.

        Users should use get_backend() factory, not import classes directly.
        """
        from gobby.memory import backends

        # NullBackend and SQLiteBackend should not be in __all__
        # (implementation detail, not public API)
        if hasattr(backends, "__all__"):
            assert "NullBackend" not in backends.__all__
            assert "SQLiteBackend" not in backends.__all__


# =============================================================================
# TDD Tests: SQLiteBackend Media Support (Phase 2 Multimodal)
# =============================================================================


class TestSQLiteBackendMediaSupport:
    """TDD tests for SQLiteBackend media attachment support.

    RED phase: These tests define expected behavior for storing/retrieving
    media attachments via the SQLiteBackend.
    """

    @pytest.mark.asyncio
    async def test_create_with_media_stores_attachment(self, temp_db: LocalDatabase):
        """Test that creating a memory with media stores the media attachment."""
        from gobby.memory.protocol import MediaAttachment

        backend = get_backend("sqlite", database=temp_db)

        media = [
            MediaAttachment(
                media_type="image",
                content_path="/path/to/screenshot.png",
                mime_type="image/png",
                description="Error screenshot",
            )
        ]

        record = await backend.create(
            content="Found an error in the login flow",
            memory_type="fact",
            media=media,
        )

        assert record is not None
        assert record.media is not None
        assert len(record.media) == 1
        assert record.media[0].content_path == "/path/to/screenshot.png"
        assert record.media[0].mime_type == "image/png"

    @pytest.mark.asyncio
    async def test_get_returns_media_attachment(self, temp_db: LocalDatabase):
        """Test that get() retrieves the stored media attachment."""
        from gobby.memory.protocol import MediaAttachment

        backend = get_backend("sqlite", database=temp_db)

        media = [
            MediaAttachment(
                media_type="image",
                content_path="/images/diagram.png",
                mime_type="image/png",
                description="Architecture diagram",
            )
        ]

        created = await backend.create(
            content="System architecture overview",
            media=media,
        )

        # Retrieve the memory
        retrieved = await backend.get(created.id)

        assert retrieved is not None
        assert retrieved.media is not None
        assert len(retrieved.media) == 1
        assert retrieved.media[0].content_path == "/images/diagram.png"
        assert retrieved.media[0].description == "Architecture diagram"

    @pytest.mark.asyncio
    async def test_list_memories_includes_media(self, temp_db: LocalDatabase):
        """Test that list_memories returns memories with their media attachments."""
        from gobby.memory.protocol import MediaAttachment

        backend = get_backend("sqlite", database=temp_db)

        # Create memory with media
        media = [
            MediaAttachment(
                media_type="image",
                content_path="/charts/performance.png",
                mime_type="image/png",
            )
        ]
        await backend.create(content="Performance metrics", media=media)

        # Create memory without media
        await backend.create(content="Simple text memory")

        # List all memories
        results = await backend.list_memories()

        # Find the memory with media
        with_media = next((r for r in results if r.content == "Performance metrics"), None)
        assert with_media is not None
        assert with_media.media is not None
        assert len(with_media.media) == 1
        assert with_media.media[0].content_path == "/charts/performance.png"

        # Find the memory without media
        without_media = next((r for r in results if r.content == "Simple text memory"), None)
        assert without_media is not None
        assert without_media.media == []

    @pytest.mark.asyncio
    async def test_search_returns_media_attachments(self, temp_db: LocalDatabase):
        """Test that search() returns memories with their media attachments."""
        from gobby.memory.protocol import MediaAttachment, MemoryQuery

        backend = get_backend("sqlite", database=temp_db)

        # Create memory with media
        media = [
            MediaAttachment(
                media_type="image",
                content_path="/screenshots/error.png",
                mime_type="image/png",
                description="Authentication error",
            )
        ]
        await backend.create(content="Authentication flow bug", media=media)

        # Search for it
        query = MemoryQuery(text="Authentication")
        results = await backend.search(query)

        assert len(results) >= 1
        auth_memory = next((r for r in results if "Authentication" in r.content), None)
        assert auth_memory is not None
        assert auth_memory.media is not None
        assert len(auth_memory.media) == 1
        assert auth_memory.media[0].description == "Authentication error"

    @pytest.mark.asyncio
    async def test_create_without_media_returns_empty_list(self, temp_db: LocalDatabase):
        """Test that creating without media returns empty media list."""
        backend = get_backend("sqlite", database=temp_db)

        record = await backend.create(content="No media attached")

        assert record.media == []

    @pytest.mark.asyncio
    async def test_multiple_media_attachments(self, temp_db: LocalDatabase):
        """Test that multiple media attachments can be stored and retrieved."""
        from gobby.memory.protocol import MediaAttachment

        backend = get_backend("sqlite", database=temp_db)

        media = [
            MediaAttachment(
                media_type="image",
                content_path="/images/before.png",
                mime_type="image/png",
                description="Before state",
            ),
            MediaAttachment(
                media_type="image",
                content_path="/images/after.png",
                mime_type="image/png",
                description="After state",
            ),
        ]

        created = await backend.create(
            content="UI comparison showing before and after states",
            media=media,
        )

        assert len(created.media) == 2

        # Verify retrieval
        retrieved = await backend.get(created.id)
        assert retrieved is not None
        assert len(retrieved.media) == 2
        paths = [m.content_path for m in retrieved.media]
        assert "/images/before.png" in paths
        assert "/images/after.png" in paths
