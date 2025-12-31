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


def test_remember(memory_manager):
    memory = memory_manager.remember(
        content="Test remember",
        memory_type="fact",
        importance=0.8,
        tags=["test"],
    )
    assert memory.id.startswith("mm-")
    assert memory.content == "Test remember"
    assert memory.importance == 0.8


def test_recall_no_query(memory_manager):
    memory_manager.remember("Important", importance=0.9)
    memory_manager.remember("Unimportant", importance=0.1)

    # Default threshold is 0.3
    memories = memory_manager.recall()
    assert len(memories) == 1
    assert memories[0].content == "Important"


def test_recall_with_query(memory_manager):
    memory_manager.remember("The quick brown fox", importance=0.5)
    memory_manager.remember("The lazy dog", importance=0.5)

    memories = memory_manager.recall(query="fox")
    assert len(memories) == 1
    assert memories[0].content == "The quick brown fox"


def test_forget(memory_manager):
    memory = memory_manager.remember("To forget")
    assert memory_manager.forget(memory.id)
    assert memory_manager.recall(query="To forget") == []


def test_decay_memories(memory_manager):
    # Setup: Create a memory with high importance
    # We need to hack the updated_at to be in the past to trigger decay
    # Default decay is 0.05 per month -> ~0.0016 per day

    memory = memory_manager.remember("Old memory", importance=0.9)

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


def test_content_exists(memory_manager):
    """Test duplicate content detection."""
    memory_manager.remember("Unique content", importance=0.5)

    assert memory_manager.content_exists("Unique content")
    assert not memory_manager.content_exists("Different content")


def test_get_memory(memory_manager):
    """Test getting a specific memory by ID."""
    memory = memory_manager.remember("Test memory")

    retrieved = memory_manager.get_memory(memory.id)
    assert retrieved is not None
    assert retrieved.content == "Test memory"

    # Non-existent memory
    assert memory_manager.get_memory("nonexistent-id") is None


def test_update_memory(memory_manager):
    """Test updating memory fields."""
    memory = memory_manager.remember("Original", importance=0.5, tags=["old"])

    updated = memory_manager.update_memory(
        memory.id,
        content="Updated",
        importance=0.9,
        tags=["new", "updated"],
    )

    assert updated.content == "Updated"
    assert updated.importance == 0.9
    assert updated.tags == ["new", "updated"]


def test_list_memories(memory_manager):
    """Test listing memories with filters."""
    memory_manager.remember("Fact 1", memory_type="fact", importance=0.8)
    memory_manager.remember("Pref 1", memory_type="preference", importance=0.6)
    memory_manager.remember("Fact 2", memory_type="fact", importance=0.4)

    # Filter by type
    facts = memory_manager.list_memories(memory_type="fact")
    assert len(facts) == 2
    assert all(m.memory_type == "fact" for m in facts)

    # Filter by importance
    high_importance = memory_manager.list_memories(min_importance=0.7)
    assert len(high_importance) == 1
    assert high_importance[0].importance == 0.8


def test_get_stats(memory_manager):
    """Test memory statistics."""
    memory_manager.remember("Fact", memory_type="fact", importance=0.8)
    memory_manager.remember("Preference", memory_type="preference", importance=0.6)

    stats = memory_manager.get_stats()

    assert stats["total_count"] == 2
    assert stats["by_type"]["fact"] == 1
    assert stats["by_type"]["preference"] == 1
    assert stats["avg_importance"] == 0.7


def test_get_embedding_stats(memory_manager):
    """Test embedding statistics (before any embeddings generated)."""
    memory_manager.remember("Test 1")
    memory_manager.remember("Test 2")

    stats = memory_manager.get_embedding_stats()

    assert stats["total_memories"] == 2
    assert stats["embedded_memories"] == 0
    assert stats["pending_embeddings"] == 2
    assert stats["embedding_model"] == "text-embedding-3-small"
    assert stats["embedding_dim"] == 1536


def test_recall_with_semantic_disabled(db):
    """Test that recall falls back to text search when semantic is disabled."""
    config = MemoryConfig(semantic_search_enabled=False)
    manager = MemoryManager(db, config)

    manager.remember("The quick brown fox jumps", importance=0.5)
    manager.remember("The lazy dog sleeps", importance=0.5)

    # Should use text search, not semantic
    memories = manager.recall(query="fox")
    assert len(memories) == 1
    assert "fox" in memories[0].content


def test_recall_semantic_fallback_no_embeddings(db):
    """Test that semantic recall falls back when no embeddings exist."""
    config = MemoryConfig(semantic_search_enabled=True)
    manager = MemoryManager(db, config)

    manager.remember("The quick brown fox", importance=0.5)
    manager.remember("The lazy dog", importance=0.5)

    # Semantic search enabled but no embeddings - should fall back to text search
    memories = manager.recall(query="fox", use_semantic=True)
    assert len(memories) == 1
    assert "fox" in memories[0].content
