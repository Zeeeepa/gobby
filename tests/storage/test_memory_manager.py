from datetime import UTC, datetime, timedelta

import pytest

from gobby.config.persistence import MemoryConfig
from gobby.memory.manager import MemoryManager
from gobby.storage.database import LocalDatabase
from gobby.storage.migrations import run_migrations

pytestmark = pytest.mark.unit


@pytest.fixture
def db(tmp_path):
    database = LocalDatabase(tmp_path / "gobby-hub.db")
    run_migrations(database)
    yield database
    database.close()


@pytest.fixture
def memory_manager(db):
    config = MemoryConfig()
    return MemoryManager(db, config)


@pytest.mark.asyncio
async def test_create_memory(memory_manager):
    memory = await memory_manager.create_memory(
        content="Test remember",
        memory_type="fact",
        importance=0.8,
        tags=["test"],
    )
    assert memory.id.startswith("mm-")
    assert memory.content == "Test remember"
    assert memory.importance == 0.8


@pytest.mark.asyncio
async def test_search_memories_no_query(memory_manager):
    await memory_manager.create_memory("Important", importance=0.9)
    await memory_manager.create_memory("Unimportant", importance=0.1)

    # No query returns all, sorted by importance
    memories = await memory_manager.search_memories()
    assert len(memories) >= 1


@pytest.mark.asyncio
async def test_search_memories_with_query(memory_manager):
    """Without VectorStore, query param is ignored and all memories are listed."""
    await memory_manager.create_memory("The quick brown fox", importance=0.8)
    await memory_manager.create_memory("The lazy dog", importance=0.8)

    # Without VectorStore, search falls back to listing all memories
    memories = await memory_manager.search_memories(query="fox")
    assert len(memories) == 2


@pytest.mark.asyncio
async def test_delete_memory(memory_manager):
    memory = await memory_manager.create_memory("To forget")
    assert await memory_manager.delete_memory(memory.id)
    assert await memory_manager.search_memories(query="To forget") == []


@pytest.mark.asyncio
async def test_decay_memories(db):
    """Test importance decay with decay_enabled config."""
    from unittest.mock import MagicMock

    # Create config with decay enabled
    config = MagicMock()
    config.enabled = True
    config.backend = "local"
    config.decay_enabled = True
    config.decay_rate = 0.05
    config.decay_floor = 0.1
    config.auto_crossref = False
    config.neo4j_url = None

    manager = MemoryManager(db, config)

    memory = await manager.create_memory("Old memory", importance=0.9)

    # Manually update updated_at to 30 days ago
    past = datetime.now(UTC) - timedelta(days=30)

    with manager.storage.db.transaction() as conn:
        conn.execute(
            "UPDATE memories SET updated_at = ? WHERE id = ?",
            (past.isoformat(), memory.id),
        )

    # Verify pre-decay state
    m_pre = manager.storage.get_memory(memory.id)
    assert m_pre.importance == 0.9

    # Run decay - expected: 0.05 (1 month * 0.05 rate)
    count = manager.decay_memories()
    assert count == 1

    m_post = manager.storage.get_memory(memory.id)
    assert m_post.importance < 0.9
    # Should be approx 0.85
    assert 0.84 < m_post.importance < 0.86


@pytest.mark.asyncio
async def test_content_exists(memory_manager):
    """Test duplicate content detection."""
    await memory_manager.create_memory("Unique content", importance=0.8)

    assert memory_manager.content_exists("Unique content")
    assert not memory_manager.content_exists("Different content")


@pytest.mark.asyncio
async def test_get_memory(memory_manager):
    """Test getting a specific memory by ID."""
    memory = await memory_manager.create_memory("Test memory")

    retrieved = memory_manager.get_memory(memory.id)
    assert retrieved is not None
    assert retrieved.content == "Test memory"

    # Non-existent memory
    assert memory_manager.get_memory("nonexistent-id") is None


@pytest.mark.asyncio
async def test_update_memory(memory_manager):
    """Test updating memory fields."""
    memory = await memory_manager.create_memory("Original", importance=0.8, tags=["old"])

    updated = await memory_manager.update_memory(
        memory.id,
        content="Updated",
        importance=0.9,
        tags=["new", "updated"],
    )

    assert updated.content == "Updated"
    assert updated.importance == 0.9
    assert updated.tags == ["new", "updated"]


@pytest.mark.asyncio
async def test_list_memories(memory_manager):
    """Test listing memories with filters."""
    await memory_manager.create_memory("Fact 1", memory_type="fact", importance=0.8)
    await memory_manager.create_memory("Pref 1", memory_type="preference", importance=0.6)
    await memory_manager.create_memory("Fact 2", memory_type="fact", importance=0.4)

    # Filter by type
    facts = memory_manager.list_memories(memory_type="fact")
    assert len(facts) == 2
    assert all(m.memory_type == "fact" for m in facts)

    # Filter by importance
    high_importance = memory_manager.list_memories(min_importance=0.7)
    assert len(high_importance) == 1
    assert high_importance[0].importance == 0.8


@pytest.mark.asyncio
async def test_get_stats(memory_manager):
    """Test memory statistics."""
    await memory_manager.create_memory("Fact", memory_type="fact", importance=0.8)
    await memory_manager.create_memory("Preference", memory_type="preference", importance=0.6)

    stats = memory_manager.get_stats()

    assert stats["total_count"] == 2
    assert stats["by_type"]["fact"] == 1
    assert stats["by_type"]["preference"] == 1
    assert stats["avg_importance"] == 0.7


@pytest.mark.asyncio
async def test_access_tracking_increments_count(memory_manager):
    """Test that search_memories increments access_count."""
    memory = await memory_manager.create_memory("Track my access", importance=0.8)

    # Initial access_count should be 0
    assert memory.access_count == 0

    # search_memories should update access stats
    await memory_manager.search_memories(query="Track")

    # Fetch fresh from storage
    updated = memory_manager.get_memory(memory.id)
    assert updated.access_count == 1
    assert updated.last_accessed_at is not None


@pytest.mark.asyncio
async def test_access_tracking_updates_timestamp(memory_manager):
    """Test that search_memories updates last_accessed_at."""
    memory = await memory_manager.create_memory("Timestamp test", importance=0.8)

    # Initial last_accessed_at should be None
    assert memory.last_accessed_at is None

    # search_memories triggers access update
    await memory_manager.search_memories(query="Timestamp")

    updated = memory_manager.get_memory(memory.id)
    assert updated.last_accessed_at is not None


@pytest.mark.asyncio
async def test_access_tracking_debounce(db):
    """Test that rapid accesses are debounced."""

    # Use very short debounce for testing
    config = MemoryConfig(access_debounce_seconds=3600)  # 1 hour debounce
    manager = MemoryManager(db, config)

    memory = await manager.create_memory("Debounce test", importance=0.8)

    # First search - should update
    await manager.search_memories(query="Debounce")
    first_access = manager.get_memory(memory.id)
    assert first_access.access_count == 1

    # Second search immediately - should be debounced
    await manager.search_memories(query="Debounce")
    second_access = manager.get_memory(memory.id)
    assert second_access.access_count == 1  # Still 1, debounced


@pytest.mark.asyncio
async def test_access_tracking_independent_memories(memory_manager):
    """Test that access stats are tracked independently per memory.

    Without VectorStore, search returns all memories so both get accessed.
    We test independence by accessing via get_memory instead.
    """
    memory1 = await memory_manager.create_memory("Alpha memory", importance=0.8)
    memory2 = await memory_manager.create_memory("Beta memory", importance=0.8)

    # Access only the first memory directly
    memory_manager._update_access_stats([memory_manager.get_memory(memory1.id)])

    updated1 = memory_manager.get_memory(memory1.id)
    updated2 = memory_manager.get_memory(memory2.id)

    assert updated1.access_count == 1
    assert updated2.access_count == 0  # Not accessed
