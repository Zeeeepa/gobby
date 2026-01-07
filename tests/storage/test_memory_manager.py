from datetime import UTC, datetime, timedelta

import pytest

from gobby.config.app import MemoryConfig
from gobby.memory.manager import MemoryManager
from gobby.storage.database import LocalDatabase
from gobby.storage.migrations import run_migrations


@pytest.fixture
def db(tmp_path):
    database = LocalDatabase(tmp_path / "gobby.db")
    run_migrations(database)
    yield database
    database.close()


@pytest.fixture
def memory_manager(db):
    config = MemoryConfig()
    return MemoryManager(db, config)


@pytest.mark.asyncio
async def test_remember(memory_manager):
    memory = await memory_manager.remember(
        content="Test remember",
        memory_type="fact",
        importance=0.8,
        tags=["test"],
    )
    assert memory.id.startswith("mm-")
    assert memory.content == "Test remember"
    assert memory.importance == 0.8


@pytest.mark.asyncio
async def test_recall_no_query(memory_manager):
    await memory_manager.remember("Important", importance=0.9)
    await memory_manager.remember("Unimportant", importance=0.1)

    # Default threshold is 0.3
    memories = memory_manager.recall()
    assert len(memories) == 1
    assert memories[0].content == "Important"


@pytest.mark.asyncio
async def test_recall_with_query(memory_manager):
    await memory_manager.remember("The quick brown fox", importance=0.5)
    await memory_manager.remember("The lazy dog", importance=0.5)

    memories = memory_manager.recall(query="fox")
    assert len(memories) == 1
    assert memories[0].content == "The quick brown fox"


@pytest.mark.asyncio
async def test_forget(memory_manager):
    memory = await memory_manager.remember("To forget")
    assert memory_manager.forget(memory.id)
    assert memory_manager.recall(query="To forget") == []


@pytest.mark.asyncio
async def test_decay_memories(memory_manager):
    # Setup: Create a memory with high importance
    # We need to hack the updated_at to be in the past to trigger decay
    # Default decay is 0.05 per month -> ~0.0016 per day

    memory = await memory_manager.remember("Old memory", importance=0.9)

    # Manually update updated_at to 30 days ago
    past = datetime.now(UTC) - timedelta(days=30)

    # Access storage directly to manipulate DB
    with memory_manager.storage.db.transaction() as conn:
        conn.execute(
            "UPDATE memories SET updated_at = ? WHERE id = ?",
            (past.isoformat(), memory.id),
        )

    # Verify pre-decay state via direct DB fetch (manager.recall might update access stats if we implemented that)
    m_pre = memory_manager.storage.get_memory(memory.id)
    assert m_pre.importance == 0.9

    # Run decay
    # Expected decay: 0.05 (1 month * 0.05 rate)
    count = memory_manager.decay_memories()
    assert count == 1

    m_post = memory_manager.storage.get_memory(memory.id)
    assert m_post.importance < 0.9
    # Should be approx 0.85
    assert 0.84 < m_post.importance < 0.86


@pytest.mark.asyncio
async def test_content_exists(memory_manager):
    """Test duplicate content detection."""
    await memory_manager.remember("Unique content", importance=0.5)

    assert memory_manager.content_exists("Unique content")
    assert not memory_manager.content_exists("Different content")


@pytest.mark.asyncio
async def test_get_memory(memory_manager):
    """Test getting a specific memory by ID."""
    memory = await memory_manager.remember("Test memory")

    retrieved = memory_manager.get_memory(memory.id)
    assert retrieved is not None
    assert retrieved.content == "Test memory"

    # Non-existent memory
    assert memory_manager.get_memory("nonexistent-id") is None


@pytest.mark.asyncio
async def test_update_memory(memory_manager):
    """Test updating memory fields."""
    memory = await memory_manager.remember("Original", importance=0.5, tags=["old"])

    updated = memory_manager.update_memory(
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
    await memory_manager.remember("Fact 1", memory_type="fact", importance=0.8)
    await memory_manager.remember("Pref 1", memory_type="preference", importance=0.6)
    await memory_manager.remember("Fact 2", memory_type="fact", importance=0.4)

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
    await memory_manager.remember("Fact", memory_type="fact", importance=0.8)
    await memory_manager.remember("Preference", memory_type="preference", importance=0.6)

    stats = memory_manager.get_stats()

    assert stats["total_count"] == 2
    assert stats["by_type"]["fact"] == 1
    assert stats["by_type"]["preference"] == 1
    assert stats["avg_importance"] == 0.7


@pytest.mark.asyncio
async def test_get_embedding_stats(memory_manager):
    """Test embedding statistics (before any embeddings generated)."""
    await memory_manager.remember("Test 1")
    await memory_manager.remember("Test 2")

    stats = memory_manager.get_embedding_stats()

    assert stats["total_memories"] == 2
    assert stats["embedded_memories"] == 0
    assert stats["pending_embeddings"] == 2
    assert stats["embedding_model"] == "text-embedding-3-small"
    assert stats["embedding_dim"] == 1536


@pytest.mark.asyncio
async def test_recall_with_semantic_disabled(db):
    """Test that recall falls back to text search when semantic is disabled."""
    config = MemoryConfig(semantic_search_enabled=False)
    manager = MemoryManager(db, config)

    await manager.remember("The quick brown fox jumps", importance=0.5)
    await manager.remember("The lazy dog sleeps", importance=0.5)

    # Should use text search, not semantic
    memories = manager.recall(query="fox")
    assert len(memories) == 1
    assert "fox" in memories[0].content


@pytest.mark.asyncio
async def test_recall_semantic_fallback_no_embeddings(db):
    """Test that semantic recall falls back when no embeddings exist."""
    config = MemoryConfig(semantic_search_enabled=True)
    manager = MemoryManager(db, config)

    await manager.remember("The quick brown fox", importance=0.5)
    await manager.remember("The lazy dog", importance=0.5)

    # Semantic search enabled but no embeddings - should fall back to text search
    memories = manager.recall(query="fox", use_semantic=True)
    assert len(memories) == 1
    assert "fox" in memories[0].content


@pytest.mark.asyncio
async def test_auto_embed_when_enabled(db):
    """Test that embeddings are auto-generated when auto_embed=True."""
    from unittest.mock import AsyncMock, patch

    config = MemoryConfig(auto_embed=True)
    manager = MemoryManager(db, config, openai_api_key="test-key")

    # Mock the embed_memory method
    with patch.object(manager, "embed_memory", new_callable=AsyncMock) as mock_embed:
        mock_embed.return_value = True

        memory = await manager.remember("Test auto-embed", importance=0.5)

        # Verify embed_memory was called
        mock_embed.assert_called_once_with(memory.id, force=False)


@pytest.mark.asyncio
async def test_auto_embed_disabled(db):
    """Test that embeddings are not generated when auto_embed=False."""
    from unittest.mock import AsyncMock, patch

    config = MemoryConfig(auto_embed=False)
    manager = MemoryManager(db, config, openai_api_key="test-key")

    with patch.object(manager, "embed_memory", new_callable=AsyncMock) as mock_embed:
        await manager.remember("Test no auto-embed", importance=0.5)

        # Verify embed_memory was NOT called
        mock_embed.assert_not_called()


@pytest.mark.asyncio
async def test_auto_embed_no_api_key(db):
    """Test that embeddings are not generated without API key."""
    from unittest.mock import AsyncMock, patch

    config = MemoryConfig(auto_embed=True)
    manager = MemoryManager(db, config, openai_api_key=None)  # No API key

    with patch.object(manager, "embed_memory", new_callable=AsyncMock) as mock_embed:
        await manager.remember("Test no key", importance=0.5)

        # Verify embed_memory was NOT called (no API key)
        mock_embed.assert_not_called()


@pytest.mark.asyncio
async def test_access_tracking_increments_count(memory_manager):
    """Test that recall increments access_count."""
    memory = await memory_manager.remember("Track my access", importance=0.5)

    # Initial access_count should be 0
    assert memory.access_count == 0

    # Recall should update access stats
    memory_manager.recall(query="Track")

    # Fetch fresh from storage
    updated = memory_manager.get_memory(memory.id)
    assert updated.access_count == 1
    assert updated.last_accessed_at is not None


@pytest.mark.asyncio
async def test_access_tracking_updates_timestamp(memory_manager):
    """Test that recall updates last_accessed_at."""
    memory = await memory_manager.remember("Timestamp test", importance=0.5)

    # Initial last_accessed_at should be None
    assert memory.last_accessed_at is None

    # Recall triggers access update
    memory_manager.recall(query="Timestamp")

    updated = memory_manager.get_memory(memory.id)
    assert updated.last_accessed_at is not None


@pytest.mark.asyncio
async def test_access_tracking_debounce(db):
    """Test that rapid accesses are debounced."""

    # Use very short debounce for testing
    config = MemoryConfig(access_debounce_seconds=3600)  # 1 hour debounce
    manager = MemoryManager(db, config)

    memory = await manager.remember("Debounce test", importance=0.5)

    # First recall - should update
    manager.recall(query="Debounce")
    first_access = manager.get_memory(memory.id)
    assert first_access.access_count == 1

    # Second recall immediately - should be debounced
    manager.recall(query="Debounce")
    second_access = manager.get_memory(memory.id)
    assert second_access.access_count == 1  # Still 1, debounced


@pytest.mark.asyncio
async def test_access_tracking_independent_memories(memory_manager):
    """Test that access stats are tracked independently per memory."""
    memory1 = await memory_manager.remember("First memory", importance=0.5)
    memory2 = await memory_manager.remember("Second memory", importance=0.5)

    # Recall only first memory
    memory_manager.recall(query="First")

    updated1 = memory_manager.get_memory(memory1.id)
    updated2 = memory_manager.get_memory(memory2.id)

    assert updated1.access_count == 1
    assert updated2.access_count == 0  # Not accessed
