"""Comprehensive tests for MemoryManager class.

Tests cover:
- Memory creation (create_memory)
- Memory retrieval (search_memories)
- Memory deletion (delete_memory)
- Access statistics and debouncing
- Statistics retrieval
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from gobby.config.persistence import MemoryConfig
from gobby.memory.manager import MemoryManager
from gobby.memory.protocol import MemoryBackendProtocol
from gobby.storage.database import LocalDatabase
from gobby.storage.memories import LocalMemoryManager, Memory
from gobby.storage.migrations import run_migrations

pytestmark = pytest.mark.unit

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def db(tmp_path):
    """Create a temporary database for testing."""
    database = LocalDatabase(tmp_path / "gobby-hub.db")
    run_migrations(database)
    yield database
    database.close()


@pytest.fixture
def memory_config():
    """Create a default memory configuration with SQLite backend."""
    return MemoryConfig(
        enabled=True,
        backend="local",
        injection_limit=10,
        access_debounce_seconds=60,
    )


@pytest.fixture
def memory_manager(db, memory_config):
    """Create a MemoryManager with real database."""
    return MemoryManager(db=db, config=memory_config)


@pytest.fixture
def mock_storage():
    """Create a mock LocalMemoryManager."""
    return MagicMock(spec=LocalMemoryManager)


@pytest.fixture
def mock_config():
    """Create a mock MemoryConfig."""
    config = MagicMock(spec=MemoryConfig)
    config.access_debounce_seconds = 60
    config.backend = "sqlite"
    return config


@pytest.fixture
def mock_db():
    """Create a mock database."""
    return MagicMock(spec=LocalDatabase)


# =============================================================================
# Test: Initialization
# =============================================================================


class TestMemoryManagerInit:
    """Tests for MemoryManager initialization."""

    def test_init_creates_storage(self, db, memory_config) -> None:
        """Test that initialization creates a LocalMemoryManager."""
        manager = MemoryManager(db=db, config=memory_config)
        assert manager.db is db
        assert manager.config is memory_config
        assert isinstance(manager.storage, LocalMemoryManager)

    def test_init_creates_backend(self, db, memory_config) -> None:
        """Test that initialization creates a MemoryBackendProtocol instance."""
        manager = MemoryManager(db=db, config=memory_config)
        assert hasattr(manager, "_backend")
        assert isinstance(manager._backend, MemoryBackendProtocol)

    def test_init_with_null_backend(self, db) -> None:
        """Test that null backend can be used for testing."""
        config = MemoryConfig(backend="null")
        manager = MemoryManager(db=db, config=config)
        assert hasattr(manager, "_backend")
        assert isinstance(manager._backend, MemoryBackendProtocol)


# =============================================================================
# Test: create_memory (Memory Creation)
# =============================================================================


class TestCreateMemory:
    """Tests for the create_memory method."""

    @pytest.mark.asyncio
    async def test_create_memory_basic(self, memory_manager):
        """Test basic memory creation."""
        memory = await memory_manager.create_memory(
            content="Test fact",
            memory_type="fact",
        )

        assert memory.id.startswith("mm-")
        assert memory.content == "Test fact"
        assert memory.memory_type == "fact"

    @pytest.mark.asyncio
    async def test_create_memory_with_all_params(self, db, memory_config):
        """Test memory creation with all parameters."""
        db.execute(
            "INSERT INTO projects (id, name, repo_path) VALUES (?, ?, ?)",
            ("proj-123", "test-project", "/tmp/test"),
        )
        now = datetime.now(UTC).isoformat()
        db.execute(
            """INSERT INTO sessions (id, external_id, machine_id, source, project_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("sess-123", "ext-123", "machine-123", "claude", "proj-123", now),
        )

        manager = MemoryManager(db=db, config=memory_config)
        memory = await manager.create_memory(
            content="User prefers dark theme",
            memory_type="preference",
            project_id=None,
            source_type="user",
            source_session_id="sess-123",
            tags=["ui", "theme"],
        )

        assert memory.content == "User prefers dark theme"
        assert memory.memory_type == "preference"
        assert memory.source_type == "user"
        assert memory.source_session_id == "sess-123"
        assert memory.tags == ["ui", "theme"]

    @pytest.mark.asyncio
    async def test_create_memory_default_values(self, memory_manager):
        """Test memory creation uses correct defaults."""
        memory = await memory_manager.create_memory(content="Simple fact")

        assert memory.memory_type == "fact"
        assert memory.source_type == "user"
        assert memory.tags == []


# =============================================================================
# Test: search_memories (Memory Retrieval)
# =============================================================================


class TestSearchMemories:
    """Tests for the search_memories method."""

    @pytest.mark.asyncio
    async def test_search_memories_no_query_returns_top_memories(self, memory_manager):
        """Test search_memories without query returns top memories."""
        await memory_manager.create_memory(content="Low importance")
        await memory_manager.create_memory(content="High importance")
        await memory_manager.create_memory(content="Medium importance")

        memories = await memory_manager.search_memories(limit=2)

        assert len(memories) == 2

    @pytest.mark.asyncio
    async def test_search_memories_no_query_all_returned(self, memory_manager):
        """Test search_memories without query returns all memories (no VectorStore)."""
        await memory_manager.create_memory(content="Python is a programming language")
        await memory_manager.create_memory(content="JavaScript runs in browsers")

        memories = await memory_manager.search_memories(limit=10)

        assert len(memories) == 2

    @pytest.mark.asyncio
    async def test_search_memories_by_memory_type(self, memory_manager):
        """Test search_memories filters by memory type."""
        await memory_manager.create_memory(content="Fact 1", memory_type="fact")
        await memory_manager.create_memory(
            content="Pref 1", memory_type="preference"
        )

        memories = await memory_manager.search_memories(memory_type="preference")

        assert len(memories) == 1
        assert memories[0].memory_type == "preference"

    @pytest.mark.asyncio
    async def test_search_memories_limit(self, memory_manager):
        """Test search_memories respects limit parameter."""
        for i in range(5):
            await memory_manager.create_memory(content=f"Memory {i}")

        memories = await memory_manager.search_memories(limit=3)

        assert len(memories) == 3

    @pytest.mark.asyncio
    async def test_search_memories_updates_access_stats(self, memory_manager):
        """Test search_memories updates access statistics."""
        memory = await memory_manager.create_memory(content="Track access")
        original_count = memory.access_count

        _ = await memory_manager.search_memories(limit=10)

        updated = memory_manager.get_memory(memory.id)
        assert updated.access_count == original_count + 1
        assert updated.last_accessed_at is not None


# =============================================================================
# Test: Access Statistics
# =============================================================================


class TestAccessStats:
    """Tests for access statistics updates."""

    @pytest.mark.asyncio
    async def test_update_access_stats_debouncing(self, memory_manager):
        """Test access stats debouncing prevents rapid updates."""
        memory = await memory_manager.create_memory(content="Debounce test")

        # First search - should update
        _ = await memory_manager.search_memories(limit=10)
        updated = memory_manager.get_memory(memory.id)
        first_access_count = updated.access_count

        # Second immediate search - should be debounced
        _ = await memory_manager.search_memories(limit=10)
        updated_again = memory_manager.get_memory(memory.id)

        # Should still be same count due to debouncing
        assert updated_again.access_count == first_access_count

    def test_update_access_stats_empty_list(self, memory_manager) -> None:
        """Test _update_access_stats handles empty list."""
        memory_manager._update_access_stats([])

    def test_update_access_stats_invalid_timestamp(self, db, memory_config) -> None:
        """Test _update_access_stats handles invalid timestamps gracefully."""
        manager = MemoryManager(db=db, config=memory_config)

        memory = MagicMock(spec=Memory)
        memory.id = "mm-test"
        memory.last_accessed_at = "invalid-timestamp"

        # Should not raise, should proceed with update
        manager._update_access_stats([memory])

    def test_update_access_stats_no_timezone(self, db, memory_config) -> None:
        """Test _update_access_stats handles timestamps without timezone."""
        manager = MemoryManager(db=db, config=memory_config)

        real_memory = manager.storage.create_memory(content="Test timezone")

        memory = MagicMock(spec=Memory)
        memory.id = real_memory.id
        memory.last_accessed_at = "2024-01-01T00:00:00"

        manager._update_access_stats([memory])

        updated = manager.get_memory(real_memory.id)
        assert updated.access_count >= 1


# =============================================================================
# Test: delete_memory (Memory Deletion)
# =============================================================================


class TestDeleteMemory:
    """Tests for the delete_memory method."""

    @pytest.mark.asyncio
    async def test_delete_existing_memory(self, memory_manager):
        """Test deleting an existing memory."""
        memory = await memory_manager.create_memory(content="To delete")

        result = await memory_manager.delete_memory(memory.id)

        assert result is True
        assert memory_manager.get_memory(memory.id) is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_memory(self, memory_manager) -> None:
        """Test deleting a non-existent memory returns False."""
        result = await memory_manager.delete_memory("mm-nonexistent")
        assert result is False


# =============================================================================
# Test: List Memories
# =============================================================================


class TestListMemories:
    """Tests for list_memories method."""

    @pytest.mark.asyncio
    async def test_list_memories_basic(self, memory_manager):
        """Test basic memory listing."""
        await memory_manager.create_memory(content="Memory 1")
        await memory_manager.create_memory(content="Memory 2")

        memories = memory_manager.list_memories()

        assert len(memories) == 2

    @pytest.mark.asyncio
    async def test_list_memories_with_offset(self, memory_manager):
        """Test memory listing with offset."""
        for i in range(5):
            await memory_manager.create_memory(content=f"Memory {i}")

        memories = memory_manager.list_memories(limit=2, offset=2)

        assert len(memories) == 2

    @pytest.mark.asyncio
    async def test_list_memories_by_type(self, memory_manager):
        """Test memory listing filtered by type."""
        await memory_manager.create_memory(content="Fact", memory_type="fact")
        await memory_manager.create_memory(
            content="Preference", memory_type="preference"
        )

        memories = memory_manager.list_memories(memory_type="fact")

        assert len(memories) == 1
        assert memories[0].memory_type == "fact"


# =============================================================================
# Test: Content Exists
# =============================================================================


class TestContentExists:
    """Tests for content_exists method."""

    @pytest.mark.asyncio
    async def test_content_exists_true(self, memory_manager):
        """Test content_exists returns True for existing content."""
        await memory_manager.create_memory(content="Existing content")

        result = memory_manager.content_exists("Existing content")

        assert result is True

    def test_content_exists_false(self, memory_manager) -> None:
        """Test content_exists returns False for non-existing content."""
        result = memory_manager.content_exists("Non-existing content")

        assert result is False


# =============================================================================
# Test: Get Memory
# =============================================================================


class TestGetMemory:
    """Tests for get_memory method."""

    @pytest.mark.asyncio
    async def test_get_memory_exists(self, memory_manager):
        """Test getting an existing memory."""
        created = await memory_manager.create_memory(content="Get test")

        retrieved = memory_manager.get_memory(created.id)

        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.content == created.content

    def test_get_memory_not_found(self, memory_manager) -> None:
        """Test getting a non-existent memory returns None."""
        result = memory_manager.get_memory("mm-nonexistent")

        assert result is None


# =============================================================================
# Test: Update Memory
# =============================================================================


class TestUpdateMemory:
    """Tests for update_memory method."""

    @pytest.mark.asyncio
    async def test_update_memory_content(self, memory_manager):
        """Test updating memory content."""
        memory = await memory_manager.create_memory(content="Original")

        updated = await memory_manager.update_memory(memory.id, content="Updated")

        assert updated.content == "Updated"

    @pytest.mark.asyncio
    async def test_update_memory_tags(self, memory_manager):
        """Test updating memory tags."""
        memory = await memory_manager.create_memory(content="Test", tags=["old"])

        updated = await memory_manager.update_memory(memory.id, tags=["new", "tags"])

        assert updated.tags == ["new", "tags"]

    @pytest.mark.asyncio
    async def test_update_memory_not_found_raises(self, memory_manager):
        """Test updating non-existent memory raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            await memory_manager.update_memory("mm-nonexistent", content="New")


# =============================================================================
# Test: Get Stats
# =============================================================================


class TestGetStats:
    """Tests for get_stats method."""

    def test_get_stats_empty(self, memory_manager) -> None:
        """Test stats with no memories."""
        stats = memory_manager.get_stats()

        assert stats["total_count"] == 0
        assert stats["by_type"] == {}

    @pytest.mark.asyncio
    async def test_get_stats_with_memories(self, memory_manager):
        """Test stats with multiple memories."""
        await memory_manager.create_memory(content="Fact 1", memory_type="fact")
        await memory_manager.create_memory(content="Fact 2", memory_type="fact")
        await memory_manager.create_memory(
            content="Pref 1", memory_type="preference"
        )

        stats = memory_manager.get_stats()

        assert stats["total_count"] == 3
        assert stats["by_type"]["fact"] == 2
        assert stats["by_type"]["preference"] == 1




# =============================================================================
# Test: Edge Cases and Error Handling
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_duplicate_content_handling(self, memory_manager):
        """Test creating memory with duplicate content returns existing."""
        memory1 = await memory_manager.create_memory(content="Duplicate test")
        memory2 = await memory_manager.create_memory(content="Duplicate test")

        assert memory1.id == memory2.id

    @pytest.mark.asyncio
    async def test_search_memories_empty_database(self, memory_manager):
        """Test search_memories on empty database returns empty list."""
        memories = await memory_manager.search_memories()
        assert memories == []

    @pytest.mark.asyncio
    async def test_update_access_stats_exception_handling(self, db, memory_config):
        """Test _update_access_stats handles storage exceptions."""
        manager = MemoryManager(db=db, config=memory_config)

        memory = MagicMock(spec=Memory)
        memory.id = "mm-test"
        memory.last_accessed_at = None

        with patch.object(manager.storage, "update_access_stats") as mock_update:
            mock_update.side_effect = Exception("Database error")

            manager._update_access_stats([memory])



# =============================================================================
# Test: search_memories_as_context
# =============================================================================


class TestSearchMemoriesAsContext:
    """Tests for search_memories_as_context method."""

    @pytest.mark.asyncio
    async def test_search_memories_as_context_returns_formatted_context(self, db, memory_config):
        """Test search_memories_as_context returns properly formatted context string."""
        manager = MemoryManager(db=db, config=memory_config)

        await manager.create_memory(content="Test preference", memory_type="preference")
        await manager.create_memory(content="Test fact", memory_type="fact")

        context = await manager.search_memories_as_context()

        assert isinstance(context, str)
        assert "<project-memory>" in context
        assert "</project-memory>" in context
        assert "Test preference" in context
        assert "Test fact" in context

    @pytest.mark.asyncio
    async def test_search_memories_as_context_empty_memories(self, db, memory_config):
        """Test search_memories_as_context returns empty string when no memories."""
        manager = MemoryManager(db=db, config=memory_config)

        context = await manager.search_memories_as_context()

        assert context == ""

    @pytest.mark.asyncio
    async def test_search_memories_as_context_respects_limit(self, db, memory_config):
        """Test search_memories_as_context respects limit parameter."""
        manager = MemoryManager(db=db, config=memory_config)

        for i in range(10):
            await manager.create_memory(content=f"Memory {i}", memory_type="fact")

        context = await manager.search_memories_as_context(limit=3)

        assert isinstance(context, str)
        assert "<project-memory>" in context

    @pytest.mark.asyncio
    async def test_search_memories_as_context_respects_project_filter(self, db, memory_config):
        """Test search_memories_as_context filters by project_id."""
        manager = MemoryManager(db=db, config=memory_config)

        await manager.create_memory(content="Global memory")

        context = await manager.search_memories_as_context(project_id="proj-123")

        assert isinstance(context, str)
