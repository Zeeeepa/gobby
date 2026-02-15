"""Tests for migration 105: drop importance column from memories table."""

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


def test_importance_column_dropped(db) -> None:
    """After migration 105, importance column should not exist in memories."""
    columns = db.fetchall("PRAGMA table_info(memories)")
    column_names = [c["name"] for c in columns]
    assert "importance" not in column_names


def test_importance_index_dropped(db) -> None:
    """After migration 105, idx_memories_importance index should not exist."""
    indexes = db.fetchall(
        "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_memories_importance'"
    )
    assert len(indexes) == 0


def test_memories_table_still_exists(db) -> None:
    """memories table should still exist after migration."""
    tables = db.fetchall("SELECT name FROM sqlite_master WHERE type='table' AND name='memories'")
    assert len(tables) == 1


def test_other_columns_preserved(db) -> None:
    """All non-importance columns should still exist."""
    columns = db.fetchall("PRAGMA table_info(memories)")
    column_names = [c["name"] for c in columns]
    expected = [
        "id",
        "project_id",
        "memory_type",
        "content",
        "source_type",
        "source_session_id",
        "access_count",
        "last_accessed_at",
        "tags",
        "media",
        "created_at",
        "updated_at",
    ]
    for col in expected:
        assert col in column_names, f"Column {col} missing after migration"


def test_existing_data_preserved(tmp_path) -> None:
    """Existing memory rows should survive the migration."""
    db = LocalDatabase(tmp_path / "existing.db")
    run_migrations(db)

    db.execute("""
        INSERT INTO memories (id, memory_type, content, created_at, updated_at)
        VALUES ('mem-test-1', 'fact', 'test content', datetime('now'), datetime('now'))
    """)

    row = db.fetchone("SELECT * FROM memories WHERE id = 'mem-test-1'")
    assert row is not None
    assert row["content"] == "test content"

    db.close()
