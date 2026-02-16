"""Tests for migration 103: drop memory_embeddings table."""

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


def test_memory_embeddings_table_dropped(db) -> None:
    """After migration 103, memory_embeddings table should not exist."""
    tables = db.fetchall(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='memory_embeddings'"
    )
    assert len(tables) == 0


def test_memories_table_still_exists(db) -> None:
    """memories table should still exist after migration."""
    tables = db.fetchall("SELECT name FROM sqlite_master WHERE type='table' AND name='memories'")
    assert len(tables) == 1


def test_memories_no_importance_column(db) -> None:
    """memories table should not have importance column (removed in migration 105)."""
    columns = db.fetchall("PRAGMA table_info(memories)")
    column_names = [c["name"] for c in columns]
    assert "importance" not in column_names


def test_memory_embeddings_indexes_dropped(db) -> None:
    """Indexes on memory_embeddings should not exist."""
    indexes = db.fetchall(
        "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_memory_embeddings%'"
    )
    assert len(indexes) == 0


def test_migration_applies_to_existing_db(tmp_path) -> None:
    """Migration should work on an existing database that had memory_embeddings."""
    db = LocalDatabase(tmp_path / "existing.db")

    # Simulate pre-migration state: create the table manually
    db.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER)")
    db.execute("INSERT INTO schema_version (version) VALUES (102)")
    db.execute("""
        CREATE TABLE IF NOT EXISTS memory_embeddings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            memory_id TEXT NOT NULL,
            embedding BLOB NOT NULL,
            embedding_model TEXT NOT NULL,
            embedding_dim INTEGER NOT NULL,
            text_hash TEXT NOT NULL
        )
    """)
    # Create agent_definitions table as it would exist at v102 (created by migration 92).
    # Required for migration 107 which alters this table.
    db.execute("""
        CREATE TABLE IF NOT EXISTS agent_definitions (
            id TEXT PRIMARY KEY,
            project_id TEXT,
            name TEXT NOT NULL,
            description TEXT,
            definition_json TEXT NOT NULL,
            source TEXT DEFAULT 'custom',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    # Verify table exists before migration
    tables = db.fetchall(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='memory_embeddings'"
    )
    assert len(tables) == 1

    # Run migrations (should apply 103)
    run_migrations(db)

    # Table should be gone
    tables = db.fetchall(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='memory_embeddings'"
    )
    assert len(tables) == 0

    db.close()
