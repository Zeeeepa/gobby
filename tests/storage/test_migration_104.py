"""Tests for migration 104: drop mem0_id column from memories table."""

import pytest

from gobby.storage.database import LocalDatabase
from gobby.storage.migrations import run_migrations

pytestmark = pytest.mark.unit


@pytest.fixture
def db(tmp_path):
    database = LocalDatabase(tmp_path / "gobby-hub.db")
    run_migrations(database)
    yield database
    database.close()


def test_mem0_id_column_dropped(db) -> None:
    """After migration 104, mem0_id column should not exist in memories."""
    columns = db.fetchall("PRAGMA table_info(memories)")
    column_names = [c["name"] for c in columns]
    assert "mem0_id" not in column_names


def test_mem0_id_index_dropped(db) -> None:
    """After migration 104, idx_memories_mem0_id index should not exist."""
    indexes = db.fetchall(
        "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_memories_mem0_id'"
    )
    assert len(indexes) == 0


def test_memories_table_still_exists(db) -> None:
    """memories table should still exist after migration."""
    tables = db.fetchall(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='memories'"
    )
    assert len(tables) == 1


def test_other_columns_preserved(db) -> None:
    """All non-mem0_id columns should still exist."""
    columns = db.fetchall("PRAGMA table_info(memories)")
    column_names = [c["name"] for c in columns]
    expected = [
        "id", "project_id", "memory_type", "content",
        "source_type", "source_session_id", "importance",
        "access_count", "last_accessed_at", "tags", "media",
        "created_at", "updated_at",
    ]
    for col in expected:
        assert col in column_names, f"Column {col} missing after migration"


def test_existing_data_preserved(tmp_path) -> None:
    """Existing memory rows should survive the migration."""
    db = LocalDatabase(tmp_path / "existing.db")

    # Simulate pre-migration state: run up to 103
    run_migrations(db)

    # Insert a memory row
    db.execute("""
        INSERT INTO memories (id, memory_type, content, created_at, updated_at)
        VALUES ('mem-test-1', 'fact', 'test content', datetime('now'), datetime('now'))
    """)

    # Verify data exists
    row = db.fetchone("SELECT * FROM memories WHERE id = 'mem-test-1'")
    assert row is not None
    assert row["content"] == "test content"

    db.close()


def test_migration_applies_to_existing_db(tmp_path) -> None:
    """Migration 104 should work on a db at version 103."""
    db = LocalDatabase(tmp_path / "existing.db")

    # Run all migrations up to current (includes 104)
    run_migrations(db)

    # Verify mem0_id is gone
    columns = db.fetchall("PRAGMA table_info(memories)")
    column_names = [c["name"] for c in columns]
    assert "mem0_id" not in column_names

    # Verify table still works
    db.execute("""
        INSERT INTO memories (id, memory_type, content, created_at, updated_at)
        VALUES ('mem-test-2', 'fact', 'works after migration', datetime('now'), datetime('now'))
    """)
    row = db.fetchone("SELECT * FROM memories WHERE id = 'mem-test-2'")
    assert row is not None

    db.close()
