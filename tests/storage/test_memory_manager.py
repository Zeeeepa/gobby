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
