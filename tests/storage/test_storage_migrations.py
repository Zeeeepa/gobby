import sqlite3
from unittest.mock import patch

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
    row = db.fetchone("SELECT sql FROM sqlite_master WHERE type='table' AND name='tasks'")
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
    row = db.fetchone("SELECT sql FROM sqlite_master WHERE type='table' AND name='tasks'")
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
        "id",
        "task_id",
        "iteration",
        "status",
        "feedback",
        "issues",
        "context_type",
        "context_summary",
        "validator_type",
        "created_at",
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
    assert (
        "references tasks" in sql_lower or "foreign key" in sql_lower
    ), "task_validation_history missing foreign key to tasks"


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


# =============================================================================
# GitHub Integration: GitHub Columns Migration Tests
# =============================================================================


def test_github_columns_exist_after_migration(tmp_path):
    """Test that GitHub integration columns are added to tasks table."""
    db_path = tmp_path / "github_cols.db"
    db = LocalDatabase(db_path)

    run_migrations(db)

    # Get tasks table info
    rows = db.fetchall("PRAGMA table_info(tasks)")
    columns = {row["name"] for row in rows}

    # Check for GitHub columns
    assert "github_issue_number" in columns, "github_issue_number column missing from tasks"
    assert "github_pr_number" in columns, "github_pr_number column missing from tasks"
    assert "github_repo" in columns, "github_repo column missing from tasks"


def test_github_columns_allow_null(tmp_path):
    """Test that GitHub columns allow NULL values (for existing tasks)."""
    db_path = tmp_path / "github_null.db"
    db = LocalDatabase(db_path)

    run_migrations(db)

    # Create a project first (required for task)
    db.execute(
        "INSERT INTO projects (id, name, created_at, updated_at) VALUES (?, ?, datetime('now'), datetime('now'))",
        ("test-project", "Test Project"),
    )

    # Insert a task without GitHub fields (NULL)
    db.execute(
        """INSERT INTO tasks (id, project_id, title, created_at, updated_at)
           VALUES (?, ?, ?, datetime('now'), datetime('now'))""",
        ("task-1", "test-project", "Test Task"),
    )

    # Verify task was created with NULL GitHub fields
    row = db.fetchone(
        "SELECT github_issue_number, github_pr_number, github_repo FROM tasks WHERE id = ?",
        ("task-1",),
    )
    assert row is not None
    assert row["github_issue_number"] is None
    assert row["github_pr_number"] is None
    assert row["github_repo"] is None


def test_github_columns_store_values(tmp_path):
    """Test that GitHub columns store integer and text values correctly."""
    db_path = tmp_path / "github_values.db"
    db = LocalDatabase(db_path)

    run_migrations(db)

    # Create project
    db.execute(
        "INSERT INTO projects (id, name, created_at, updated_at) VALUES (?, ?, datetime('now'), datetime('now'))",
        ("test-project", "Test Project"),
    )

    # Insert task with GitHub fields
    db.execute(
        """INSERT INTO tasks (id, project_id, title, github_issue_number, github_pr_number, github_repo, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
        ("task-1", "test-project", "Test Task", 123, 456, "owner/repo"),
    )

    # Verify GitHub fields stored correctly
    row = db.fetchone(
        "SELECT github_issue_number, github_pr_number, github_repo FROM tasks WHERE id = ?",
        ("task-1",),
    )
    assert row is not None
    assert row["github_issue_number"] == 123
    assert row["github_pr_number"] == 456
    assert row["github_repo"] == "owner/repo"


def test_github_migration_number_is_48(tmp_path):
    """Test that GitHub columns are added in migration 48."""
    from gobby.storage.migrations import MIGRATIONS

    # Find migration 48
    migration_48 = None
    for version, description, sql in MIGRATIONS:
        if version == 48:
            migration_48 = (version, description, sql)
            break

    assert migration_48 is not None, "Migration 48 not found in MIGRATIONS list"
    assert "github" in migration_48[1].lower(), "Migration 48 should be for GitHub columns"


# =============================================================================
# Task ID Redesign: seq_num and path_cache Migration Tests
# =============================================================================


def test_seq_num_and_path_cache_columns_exist(tmp_path):
    """Test that seq_num and path_cache columns are added to tasks table."""
    db_path = tmp_path / "seq_num_cols.db"
    db = LocalDatabase(db_path)

    run_migrations(db)

    # Get tasks table info
    rows = db.fetchall("PRAGMA table_info(tasks)")
    columns = {row["name"] for row in rows}

    # Check for new columns
    assert "seq_num" in columns, "seq_num column missing from tasks"
    assert "path_cache" in columns, "path_cache column missing from tasks"


def test_seq_num_unique_index_per_project(tmp_path):
    """Test that seq_num is unique per project via index."""
    db_path = tmp_path / "seq_num_index.db"
    db = LocalDatabase(db_path)

    run_migrations(db)

    # Check for unique index on (project_id, seq_num)
    rows = db.fetchall("SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='tasks'")
    index_names = {row["name"] for row in rows}

    assert "idx_tasks_seq_num" in index_names, "idx_tasks_seq_num index missing"

    # Verify it's unique
    for row in rows:
        if row["name"] == "idx_tasks_seq_num":
            assert "UNIQUE" in row["sql"].upper(), "idx_tasks_seq_num should be UNIQUE"


def test_path_cache_index_exists(tmp_path):
    """Test that path_cache index exists for efficient lookups."""
    db_path = tmp_path / "path_cache_index.db"
    db = LocalDatabase(db_path)

    run_migrations(db)

    # Check for index on path_cache
    rows = db.fetchall("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='tasks'")
    index_names = {row["name"] for row in rows}

    assert "idx_tasks_path_cache" in index_names, "idx_tasks_path_cache index missing"


def test_seq_num_allows_null(tmp_path):
    """Test that seq_num allows NULL values (for existing tasks pre-backfill)."""
    db_path = tmp_path / "seq_num_null.db"
    db = LocalDatabase(db_path)

    run_migrations(db)

    # Create a project first (required for task)
    db.execute(
        "INSERT INTO projects (id, name, created_at, updated_at) VALUES (?, ?, datetime('now'), datetime('now'))",
        ("test-project", "Test Project"),
    )

    # Insert task without seq_num (simulating pre-backfill state)
    db.execute(
        """INSERT INTO tasks (id, project_id, title, created_at, updated_at)
           VALUES (?, ?, ?, datetime('now'), datetime('now'))""",
        ("task-1", "test-project", "Test Task"),
    )

    # Should work without seq_num
    row = db.fetchone("SELECT seq_num, path_cache FROM tasks WHERE id = ?", ("task-1",))
    assert row is not None
    assert row["seq_num"] is None, "seq_num should be NULL when not set"
    assert row["path_cache"] is None, "path_cache should be NULL when not set"


def test_seq_num_stores_integer_values(tmp_path):
    """Test that seq_num stores integer values correctly."""
    db_path = tmp_path / "seq_num_values.db"
    db = LocalDatabase(db_path)

    run_migrations(db)

    # Create project
    db.execute(
        "INSERT INTO projects (id, name, created_at, updated_at) VALUES (?, ?, datetime('now'), datetime('now'))",
        ("test-project", "Test Project"),
    )

    # Insert task with seq_num
    db.execute(
        """INSERT INTO tasks (id, project_id, title, seq_num, path_cache, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
        ("task-1", "test-project", "Test Task", 42, "1.2.42"),
    )

    # Verify values stored correctly
    row = db.fetchone("SELECT seq_num, path_cache FROM tasks WHERE id = ?", ("task-1",))
    assert row is not None
    assert row["seq_num"] == 42
    assert row["path_cache"] == "1.2.42"


def test_seq_num_migration_number_is_52(tmp_path):
    """Test that seq_num and path_cache are added in migration 52."""
    from gobby.storage.migrations import MIGRATIONS

    # Find migration 52
    migration_52 = None
    for version, description, sql in MIGRATIONS:
        if version == 52:
            migration_52 = (version, description, sql)
            break

    assert migration_52 is not None, "Migration 52 not found in MIGRATIONS list"
    assert "seq_num" in migration_52[2].lower(), "Migration 52 should add seq_num column"
    assert "path_cache" in migration_52[2].lower(), "Migration 52 should add path_cache column"


# =============================================================================
# Task ID Redesign: gt-* to UUID Migration Tests
# =============================================================================


def test_uuid_migration_converts_task_ids(tmp_path):
    """Test that migration 53 converts gt-* IDs to UUIDs."""
    db_path = tmp_path / "uuid_convert.db"
    db = LocalDatabase(db_path)

    # Run migrations up to 52 (before UUID conversion)
    from gobby.storage.migrations import MIGRATIONS

    for version, _description, action in MIGRATIONS:
        if version <= 52:
            if callable(action):
                action(db)
            else:
                for stmt in action.strip().split(";"):
                    stmt = stmt.strip()
                    if stmt:
                        db.execute(stmt)
            db.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))

    # Create project and task with gt-* ID
    db.execute(
        "INSERT INTO projects (id, name, created_at, updated_at) VALUES (?, ?, datetime('now'), datetime('now'))",
        ("test-project", "Test Project"),
    )
    db.execute(
        """INSERT INTO tasks (id, project_id, title, created_at, updated_at)
           VALUES (?, ?, ?, datetime('now'), datetime('now'))""",
        ("gt-abc123", "test-project", "Test Task"),
    )

    # Run migration 53
    for version, _description, action in MIGRATIONS:
        if version == 53:
            if callable(action):
                action(db)
            db.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))

    # Verify task ID was converted to UUID format
    row = db.fetchone("SELECT id FROM tasks WHERE project_id = ?", ("test-project",))
    assert row is not None
    task_id = row["id"]

    # Should be UUID format (8-4-4-4-12)
    assert "-" in task_id, "Task ID should be UUID format with dashes"
    parts = task_id.split("-")
    assert len(parts) == 5, "UUID should have 5 parts separated by dashes"
    assert len(parts[0]) == 8, "First UUID segment should be 8 chars"
    assert len(parts[4]) == 12, "Last UUID segment should be 12 chars"

    # Original hash should be embedded in last segment
    assert parts[4].startswith("abc123"), "Original gt-* hash should be preserved in UUID"


def test_uuid_migration_updates_parent_task_id(tmp_path):
    """Test that migration 53 updates parent_task_id references."""
    db_path = tmp_path / "uuid_parent.db"
    db = LocalDatabase(db_path)

    # Run migrations up to 52
    from gobby.storage.migrations import MIGRATIONS

    for version, _description, action in MIGRATIONS:
        if version <= 52:
            if callable(action):
                action(db)
            else:
                for stmt in action.strip().split(";"):
                    stmt = stmt.strip()
                    if stmt:
                        db.execute(stmt)
            db.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))

    # Create project, parent task, and child task
    db.execute(
        "INSERT INTO projects (id, name, created_at, updated_at) VALUES (?, ?, datetime('now'), datetime('now'))",
        ("test-project", "Test Project"),
    )
    db.execute(
        """INSERT INTO tasks (id, project_id, title, created_at, updated_at)
           VALUES (?, ?, ?, datetime('now'), datetime('now'))""",
        ("gt-parent", "test-project", "Parent Task"),
    )
    db.execute(
        """INSERT INTO tasks (id, project_id, title, parent_task_id, created_at, updated_at)
           VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))""",
        ("gt-child1", "test-project", "Child Task", "gt-parent"),
    )

    # Run migration 53
    for version, _description, action in MIGRATIONS:
        if version == 53:
            if callable(action):
                action(db)
            db.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))

    # Get parent and child tasks
    parent = db.fetchone("SELECT id FROM tasks WHERE title = ?", ("Parent Task",))
    child = db.fetchone("SELECT id, parent_task_id FROM tasks WHERE title = ?", ("Child Task",))

    assert parent is not None
    assert child is not None

    # Child's parent_task_id should match parent's new UUID
    assert child["parent_task_id"] == parent["id"], "parent_task_id should be updated to new UUID"


def test_uuid_migration_skips_when_no_gt_ids(tmp_path):
    """Test that migration 53 handles empty database gracefully."""
    db_path = tmp_path / "uuid_empty.db"
    db = LocalDatabase(db_path)

    # Run all migrations (53 should be no-op when no gt-* IDs exist)
    run_migrations(db)

    # Verify migration completed without error
    version = get_current_version(db)
    assert version == 53, "Should complete all migrations including 53"


def test_uuid_migration_number_is_53(tmp_path):
    """Test that UUID conversion is migration 53."""
    from gobby.storage.migrations import MIGRATIONS

    # Find migration 53
    migration_53 = None
    for version, description, action in MIGRATIONS:
        if version == 53:
            migration_53 = (version, description, action)
            break

    assert migration_53 is not None, "Migration 53 not found in MIGRATIONS list"
    assert "uuid" in migration_53[1].lower(), "Migration 53 should be for UUID conversion"
    assert callable(migration_53[2]), "Migration 53 should be a callable (Python migration)"
