import sqlite3
from unittest.mock import patch

import pytest

from gobby.storage.database import LocalDatabase
from gobby.storage.migrations import (
    MIGRATIONS,
    get_current_version,
    run_migrations,
)


def test_migrations_fresh_db(tmp_path):
    """Test running migrations on a fresh database."""
    db_path = tmp_path / "migration_test.db"
    db = LocalDatabase(db_path)

    # Initial state
    assert get_current_version(db) == 0

    # Run migrations
    applied = run_migrations(db)

    # Should apply all migrations
    expected_count = len(MIGRATIONS)
    assert applied == expected_count

    # Verify version
    current_version = get_current_version(db)
    assert current_version == expected_count

    # Check tables exist (sample check)
    tables = [
        "schema_version",
        "projects",
        "sessions",
        "mcp_servers",
        "tools",
        "tasks",
        "task_dependencies",
        "session_tasks",
        "session_messages",
        "memories",
        "skills",
        "tool_embeddings",
        "task_validation_history",
    ]
    for table in tables:
        # Check if table exists in sqlite_master
        row = db.fetchone("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
        assert row is not None, f"Table {table} not created"


def test_migrations_idempotency(tmp_path):
    """Test that running migrations again does nothing."""
    db_path = tmp_path / "idempotency.db"
    db = LocalDatabase(db_path)

    run_migrations(db)
    initial_version = get_current_version(db)

    # Run again
    applied = run_migrations(db)
    assert applied == 0
    assert get_current_version(db) == initial_version


def test_get_current_version_error(tmp_path):
    """Test get_current_version handles errors (e.g. missing table)."""
    db_path = tmp_path / "error.db"
    db = LocalDatabase(db_path)

    # schema_version doesn't exist yet
    assert get_current_version(db) == 0

    # Mock execute to raise exception even if table exists logic was reached
    with patch.object(db, "fetchone", side_effect=sqlite3.OperationalError("Boom")):
        assert get_current_version(db) == 0


# =============================================================================
# Task System V2: Commit Linking Migration Tests
# =============================================================================


def test_commits_column_exists_after_migration(tmp_path):
    """Test that the 'commits' column is added to the tasks table."""
    db_path = tmp_path / "commits_migration.db"
    db = LocalDatabase(db_path)

    # Run all migrations
    run_migrations(db)

    # Check that commits column exists in tasks table
    row = db.fetchone(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='tasks'"
    )
    assert row is not None
    assert "commits" in row["sql"].lower(), "commits column not found in tasks table"


def test_commits_column_allows_null(tmp_path):
    """Test that the commits column allows NULL values (for existing tasks)."""
    db_path = tmp_path / "commits_null.db"
    db = LocalDatabase(db_path)

    run_migrations(db)

    # Create a project first (required for task)
    db.execute(
        "INSERT INTO projects (id, name, created_at, updated_at) VALUES (?, ?, datetime('now'), datetime('now'))",
        ("test-project", "Test Project"),
    )

    # Insert a task without commits (NULL)
    db.execute(
        """INSERT INTO tasks (id, project_id, title, created_at, updated_at)
           VALUES (?, ?, ?, datetime('now'), datetime('now'))""",
        ("task-1", "test-project", "Test Task"),
    )

    # Verify task was created with NULL commits
    row = db.fetchone("SELECT commits FROM tasks WHERE id = ?", ("task-1",))
    assert row is not None
    assert row["commits"] is None


def test_commits_column_accepts_json_array(tmp_path):
    """Test that commits column stores JSON array of commit SHAs."""
    db_path = tmp_path / "commits_json.db"
    db = LocalDatabase(db_path)

    run_migrations(db)

    # Create project
    db.execute(
        "INSERT INTO projects (id, name, created_at, updated_at) VALUES (?, ?, datetime('now'), datetime('now'))",
        ("test-project", "Test Project"),
    )

    # Insert task with commits as JSON array
    import json
    commits = json.dumps(["abc123", "def456", "789ghi"])
    db.execute(
        """INSERT INTO tasks (id, project_id, title, commits, created_at, updated_at)
           VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))""",
        ("task-1", "test-project", "Test Task", commits),
    )

    # Verify commits stored correctly
    row = db.fetchone("SELECT commits FROM tasks WHERE id = ?", ("task-1",))
    assert row is not None
    assert row["commits"] == commits
    parsed = json.loads(row["commits"])
    assert parsed == ["abc123", "def456", "789ghi"]


def test_commits_migration_idempotent(tmp_path):
    """Test that running migrations twice doesn't fail or duplicate columns."""
    db_path = tmp_path / "commits_idempotent.db"
    db = LocalDatabase(db_path)

    # Run migrations twice
    run_migrations(db)
    applied = run_migrations(db)

    # Second run should apply 0 migrations
    assert applied == 0

    # commits column should still exist and work
    row = db.fetchone(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='tasks'"
    )
    assert row is not None
    # Count occurrences of 'commits' - should be exactly 1
    sql_lower = row["sql"].lower()
    assert sql_lower.count("commits") == 1, "commits column duplicated or missing"


# =============================================================================
# Task System V2: Validation History Table Migration Tests
# =============================================================================


def test_validation_history_table_exists(tmp_path):
    """Test that task_validation_history table is created."""
    db_path = tmp_path / "validation_history.db"
    db = LocalDatabase(db_path)

    run_migrations(db)

    # Check table exists
    row = db.fetchone(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='task_validation_history'"
    )
    assert row is not None, "task_validation_history table not created"


def test_validation_history_schema(tmp_path):
    """Test that task_validation_history has correct columns."""
    db_path = tmp_path / "validation_schema.db"
    db = LocalDatabase(db_path)

    run_migrations(db)

    # Get table info
    rows = db.fetchall("PRAGMA table_info(task_validation_history)")
    columns = {row["name"] for row in rows}

    # Verify required columns exist
    expected_columns = {
        "id", "task_id", "iteration", "status", "feedback",
        "issues", "context_type", "context_summary", "validator_type", "created_at"
    }
    for col in expected_columns:
        assert col in columns, f"Column {col} missing from task_validation_history"


def test_validation_history_foreign_key(tmp_path):
    """Test that task_validation_history has foreign key to tasks."""
    db_path = tmp_path / "validation_fk.db"
    db = LocalDatabase(db_path)

    run_migrations(db)

    # Get table SQL
    row = db.fetchone(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='task_validation_history'"
    )
    assert row is not None
    sql_lower = row["sql"].lower()

    # Check for foreign key reference to tasks
    assert "references tasks" in sql_lower or "foreign key" in sql_lower, \
        "task_validation_history missing foreign key to tasks"


def test_validation_history_index_exists(tmp_path):
    """Test that index on task_id exists for task_validation_history."""
    db_path = tmp_path / "validation_index.db"
    db = LocalDatabase(db_path)

    run_migrations(db)

    # Check for index on task_id
    rows = db.fetchall(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='task_validation_history'"
    )
    index_names = [row["name"] for row in rows]

    # Should have an index containing 'task' in the name
    has_task_index = any("task" in name.lower() for name in index_names)
    assert has_task_index, f"No task_id index found. Indexes: {index_names}"


def test_validation_history_cascade_delete(tmp_path):
    """Test that deleting a task cascades to validation history."""
    db_path = tmp_path / "validation_cascade.db"
    db = LocalDatabase(db_path)

    run_migrations(db)

    # Enable foreign keys
    db.execute("PRAGMA foreign_keys = ON")

    # Create project and task
    db.execute(
        "INSERT INTO projects (id, name, created_at, updated_at) VALUES (?, ?, datetime('now'), datetime('now'))",
        ("test-project", "Test Project"),
    )
    db.execute(
        """INSERT INTO tasks (id, project_id, title, created_at, updated_at)
           VALUES (?, ?, ?, datetime('now'), datetime('now'))""",
        ("task-1", "test-project", "Test Task"),
    )

    # Insert validation history record
    db.execute(
        """INSERT INTO task_validation_history
           (task_id, iteration, status, created_at)
           VALUES (?, ?, ?, datetime('now'))""",
        ("task-1", 1, "invalid"),
    )

    # Verify record exists
    row = db.fetchone("SELECT * FROM task_validation_history WHERE task_id = ?", ("task-1",))
    assert row is not None

    # Delete the task
    db.execute("DELETE FROM tasks WHERE id = ?", ("task-1",))

    # Verify validation history was cascade deleted
    row = db.fetchone("SELECT * FROM task_validation_history WHERE task_id = ?", ("task-1",))
    assert row is None, "Validation history not cascade deleted"


def test_tasks_escalation_columns(tmp_path):
    """Test that escalation columns are added to tasks table."""
    db_path = tmp_path / "escalation_cols.db"
    db = LocalDatabase(db_path)

    run_migrations(db)

    # Get tasks table info
    rows = db.fetchall("PRAGMA table_info(tasks)")
    columns = {row["name"] for row in rows}

    # Check for escalation columns
    assert "escalated_at" in columns, "escalated_at column missing from tasks"
    assert "escalation_reason" in columns, "escalation_reason column missing from tasks"
