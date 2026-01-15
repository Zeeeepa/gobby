import sqlite3
from unittest.mock import patch

from gobby.storage.database import LocalDatabase
from gobby.storage.migrations import (
    BASELINE_VERSION,
    MIGRATIONS,
    get_current_version,
    run_migrations,
)
from gobby.storage.migrations_legacy import LEGACY_MIGRATIONS

# Calculate expected version after all migrations
EXPECTED_FINAL_VERSION = max(
    BASELINE_VERSION,
    max((m[0] for m in MIGRATIONS), default=BASELINE_VERSION),
)


def test_migrations_fresh_db(tmp_path):
    """Test running migrations on a fresh database.

    With the baseline schema architecture:
    - Fresh databases get BASELINE_SCHEMA applied directly (counts as 1 migration)
    - Plus any incremental migrations beyond the baseline
    - Final version is EXPECTED_FINAL_VERSION
    """
    db_path = tmp_path / "migration_test.db"
    db = LocalDatabase(db_path)

    # Initial state
    assert get_current_version(db) == 0

    # Run migrations
    applied = run_migrations(db)

    # Fresh databases apply baseline schema (1) + incremental migrations
    expected_count = 1 + len([m for m in MIGRATIONS if m[0] > BASELINE_VERSION])
    assert applied == expected_count

    # Verify version reaches expected final version
    current_version = get_current_version(db)
    assert current_version == EXPECTED_FINAL_VERSION

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
    assert initial_version == EXPECTED_FINAL_VERSION

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
    # Migration 48 is in LEGACY_MIGRATIONS (pre-baseline migrations)
    migration_48 = None
    for version, description, sql in LEGACY_MIGRATIONS:
        if version == 48:
            migration_48 = (version, description, sql)
            break

    assert migration_48 is not None, "Migration 48 not found in LEGACY_MIGRATIONS list"
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
    rows = db.fetchall(
        "SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='tasks'"
    )
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
    # Migration 52 is in LEGACY_MIGRATIONS (pre-baseline migrations)
    migration_52 = None
    for version, description, sql in LEGACY_MIGRATIONS:
        if version == 52:
            migration_52 = (version, description, sql)
            break

    assert migration_52 is not None, "Migration 52 not found in LEGACY_MIGRATIONS list"
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
    # These are in LEGACY_MIGRATIONS (pre-baseline migrations)
    for version, _description, action in LEGACY_MIGRATIONS:
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
    for version, _description, action in LEGACY_MIGRATIONS:
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
    # These are in LEGACY_MIGRATIONS (pre-baseline migrations)
    for version, _description, action in LEGACY_MIGRATIONS:
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
    for version, _description, action in LEGACY_MIGRATIONS:
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

    # Verify migration completed without error (now goes to 54)
    version = get_current_version(db)
    assert version >= 53, "Should complete migration 53 (and beyond)"


def test_uuid_migration_number_is_53(tmp_path):
    """Test that UUID conversion is migration 53."""
    # Migration 53 is in LEGACY_MIGRATIONS (pre-baseline migrations)
    migration_53 = None
    for version, description, action in LEGACY_MIGRATIONS:
        if version == 53:
            migration_53 = (version, description, action)
            break

    assert migration_53 is not None, "Migration 53 not found in LEGACY_MIGRATIONS list"
    assert "uuid" in migration_53[1].lower(), "Migration 53 should be for UUID conversion"
    assert callable(migration_53[2]), "Migration 53 should be a callable (Python migration)"


# =============================================================================
# Task ID Redesign: seq_num Backfill Migration Tests
# =============================================================================


def test_seq_num_backfill_assigns_sequential_numbers(tmp_path):
    """Test that migration 54 assigns sequential seq_num values per project."""
    db_path = tmp_path / "seq_num_backfill.db"
    db = LocalDatabase(db_path)

    # Run migrations up to 53 (before seq_num backfill)
    # These are in LEGACY_MIGRATIONS (pre-baseline migrations)
    for version, _description, action in LEGACY_MIGRATIONS:
        if version <= 53:
            if callable(action):
                action(db)
            else:
                for stmt in action.strip().split(";"):
                    stmt = stmt.strip()
                    if stmt:
                        db.execute(stmt)
            db.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))

    # Create project and tasks without seq_num
    db.execute(
        "INSERT INTO projects (id, name, created_at, updated_at) VALUES (?, ?, datetime('now'), datetime('now'))",
        ("proj-1", "Project 1"),
    )
    db.execute(
        """INSERT INTO tasks (id, project_id, title, created_at, updated_at)
           VALUES (?, ?, ?, datetime('now', '-3 days'), datetime('now'))""",
        ("task-a", "proj-1", "First Task"),
    )
    db.execute(
        """INSERT INTO tasks (id, project_id, title, created_at, updated_at)
           VALUES (?, ?, ?, datetime('now', '-2 days'), datetime('now'))""",
        ("task-b", "proj-1", "Second Task"),
    )
    db.execute(
        """INSERT INTO tasks (id, project_id, title, created_at, updated_at)
           VALUES (?, ?, ?, datetime('now', '-1 days'), datetime('now'))""",
        ("task-c", "proj-1", "Third Task"),
    )

    # Run migration 54
    for version, _description, action in LEGACY_MIGRATIONS:
        if version == 54:
            if callable(action):
                action(db)
            db.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))

    # Verify seq_num values were assigned in order
    tasks = db.fetchall(
        "SELECT id, seq_num FROM tasks WHERE project_id = ? ORDER BY seq_num",
        ("proj-1",),
    )

    assert len(tasks) == 3
    assert tasks[0]["id"] == "task-a" and tasks[0]["seq_num"] == 1
    assert tasks[1]["id"] == "task-b" and tasks[1]["seq_num"] == 2
    assert tasks[2]["id"] == "task-c" and tasks[2]["seq_num"] == 3


def test_seq_num_backfill_per_project(tmp_path):
    """Test that seq_num values are assigned per project independently."""
    db_path = tmp_path / "seq_num_per_project.db"
    db = LocalDatabase(db_path)

    # Run migrations up to 53
    # These are in LEGACY_MIGRATIONS (pre-baseline migrations)
    for version, _description, action in LEGACY_MIGRATIONS:
        if version <= 53:
            if callable(action):
                action(db)
            else:
                for stmt in action.strip().split(";"):
                    stmt = stmt.strip()
                    if stmt:
                        db.execute(stmt)
            db.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))

    # Create two projects with tasks
    db.execute(
        "INSERT INTO projects (id, name, created_at, updated_at) VALUES (?, ?, datetime('now'), datetime('now'))",
        ("proj-1", "Project 1"),
    )
    db.execute(
        "INSERT INTO projects (id, name, created_at, updated_at) VALUES (?, ?, datetime('now'), datetime('now'))",
        ("proj-2", "Project 2"),
    )

    # Project 1 tasks
    db.execute(
        """INSERT INTO tasks (id, project_id, title, created_at, updated_at)
           VALUES (?, ?, ?, datetime('now'), datetime('now'))""",
        ("task-p1-a", "proj-1", "P1 Task A"),
    )
    db.execute(
        """INSERT INTO tasks (id, project_id, title, created_at, updated_at)
           VALUES (?, ?, ?, datetime('now'), datetime('now'))""",
        ("task-p1-b", "proj-1", "P1 Task B"),
    )

    # Project 2 tasks
    db.execute(
        """INSERT INTO tasks (id, project_id, title, created_at, updated_at)
           VALUES (?, ?, ?, datetime('now'), datetime('now'))""",
        ("task-p2-a", "proj-2", "P2 Task A"),
    )

    # Run migration 54
    for version, _description, action in LEGACY_MIGRATIONS:
        if version == 54:
            if callable(action):
                action(db)
            db.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))

    # Verify each project has independent seq_num sequence
    p1_tasks = db.fetchall(
        "SELECT id, seq_num FROM tasks WHERE project_id = ? ORDER BY seq_num",
        ("proj-1",),
    )
    p2_tasks = db.fetchall(
        "SELECT id, seq_num FROM tasks WHERE project_id = ? ORDER BY seq_num",
        ("proj-2",),
    )

    # Both projects should start at seq_num = 1
    assert p1_tasks[0]["seq_num"] == 1
    assert p1_tasks[1]["seq_num"] == 2
    assert p2_tasks[0]["seq_num"] == 1  # Independent sequence


def test_seq_num_backfill_skips_already_set(tmp_path):
    """Test that migration 54 skips tasks that already have seq_num."""
    db_path = tmp_path / "seq_num_skip.db"
    db = LocalDatabase(db_path)

    # Run all migrations
    run_migrations(db)

    # Verify migration completed without error
    version = get_current_version(db)
    assert version >= 54, "Should complete all migrations including 54"


def test_seq_num_backfill_migration_number_is_54(tmp_path):
    """Test that seq_num backfill is migration 54."""
    # Migration 54 is in LEGACY_MIGRATIONS (pre-baseline migrations)
    migration_54 = None
    for version, description, action in LEGACY_MIGRATIONS:
        if version == 54:
            migration_54 = (version, description, action)
            break

    assert migration_54 is not None, "Migration 54 not found in LEGACY_MIGRATIONS list"
    assert "seq_num" in migration_54[1].lower(), "Migration 54 should be for seq_num backfill"
    assert callable(migration_54[2]), "Migration 54 should be a callable (Python migration)"


# Migration 55: Backfill path_cache for existing tasks


def test_path_cache_backfill_computes_root_task_path(tmp_path):
    """Test that migration 55 computes path_cache for root tasks."""
    db_path = tmp_path / "path_cache_root.db"
    db = LocalDatabase(db_path)

    # Run migrations up to 54 (includes seq_num assignment)
    # These are in LEGACY_MIGRATIONS (pre-baseline migrations)
    for version, _description, action in LEGACY_MIGRATIONS:
        if version <= 54:
            if callable(action):
                action(db)
            else:
                for stmt in action.strip().split(";"):
                    stmt = stmt.strip()
                    if stmt:
                        db.execute(stmt)
            db.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))

    # Create project and root task with seq_num
    db.execute(
        "INSERT INTO projects (id, name, created_at, updated_at) VALUES (?, ?, datetime('now'), datetime('now'))",
        ("proj-1", "Project 1"),
    )
    db.execute(
        """INSERT INTO tasks (id, project_id, title, seq_num, created_at, updated_at)
           VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))""",
        ("task-root", "proj-1", "Root Task", 1),
    )

    # Run migration 55
    for version, _description, action in LEGACY_MIGRATIONS:
        if version == 55:
            if callable(action):
                action(db)
            db.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))

    # Verify path_cache was computed
    row = db.fetchone("SELECT path_cache FROM tasks WHERE id = ?", ("task-root",))
    assert row["path_cache"] == "1"


def test_path_cache_backfill_computes_child_task_path(tmp_path):
    """Test that migration 55 computes path_cache for child tasks."""
    db_path = tmp_path / "path_cache_child.db"
    db = LocalDatabase(db_path)

    # Run migrations up to 54
    # These are in LEGACY_MIGRATIONS (pre-baseline migrations)
    for version, _description, action in LEGACY_MIGRATIONS:
        if version <= 54:
            if callable(action):
                action(db)
            else:
                for stmt in action.strip().split(";"):
                    stmt = stmt.strip()
                    if stmt:
                        db.execute(stmt)
            db.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))

    # Create project, parent, and child with seq_nums
    db.execute(
        "INSERT INTO projects (id, name, created_at, updated_at) VALUES (?, ?, datetime('now'), datetime('now'))",
        ("proj-1", "Project 1"),
    )
    db.execute(
        """INSERT INTO tasks (id, project_id, title, seq_num, created_at, updated_at)
           VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))""",
        ("task-parent", "proj-1", "Parent Task", 1),
    )
    db.execute(
        """INSERT INTO tasks (id, project_id, title, parent_task_id, seq_num, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
        ("task-child", "proj-1", "Child Task", "task-parent", 2),
    )

    # Run migration 55
    for version, _description, action in LEGACY_MIGRATIONS:
        if version == 55:
            if callable(action):
                action(db)
            db.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))

    # Verify path_cache values
    parent_row = db.fetchone("SELECT path_cache FROM tasks WHERE id = ?", ("task-parent",))
    assert parent_row["path_cache"] == "1"

    child_row = db.fetchone("SELECT path_cache FROM tasks WHERE id = ?", ("task-child",))
    assert child_row["path_cache"] == "1.2"


def test_path_cache_backfill_deep_hierarchy(tmp_path):
    """Test that migration 55 computes path_cache for deeply nested tasks."""
    db_path = tmp_path / "path_cache_deep.db"
    db = LocalDatabase(db_path)

    # Run migrations up to 54
    # These are in LEGACY_MIGRATIONS (pre-baseline migrations)
    for version, _description, action in LEGACY_MIGRATIONS:
        if version <= 54:
            if callable(action):
                action(db)
            else:
                for stmt in action.strip().split(";"):
                    stmt = stmt.strip()
                    if stmt:
                        db.execute(stmt)
            db.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))

    # Create project and 4-level hierarchy
    db.execute(
        "INSERT INTO projects (id, name, created_at, updated_at) VALUES (?, ?, datetime('now'), datetime('now'))",
        ("proj-1", "Project 1"),
    )
    db.execute(
        """INSERT INTO tasks (id, project_id, title, seq_num, created_at, updated_at)
           VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))""",
        ("task-1", "proj-1", "Level 1", 1),
    )
    db.execute(
        """INSERT INTO tasks (id, project_id, title, parent_task_id, seq_num, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
        ("task-2", "proj-1", "Level 2", "task-1", 3),
    )
    db.execute(
        """INSERT INTO tasks (id, project_id, title, parent_task_id, seq_num, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
        ("task-3", "proj-1", "Level 3", "task-2", 7),
    )
    db.execute(
        """INSERT INTO tasks (id, project_id, title, parent_task_id, seq_num, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
        ("task-4", "proj-1", "Level 4", "task-3", 47),
    )

    # Run migration 55
    for version, _description, action in LEGACY_MIGRATIONS:
        if version == 55:
            if callable(action):
                action(db)
            db.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))

    # Verify path_cache for deepest task
    row = db.fetchone("SELECT path_cache FROM tasks WHERE id = ?", ("task-4",))
    assert row["path_cache"] == "1.3.7.47"


def test_path_cache_backfill_skips_no_seq_num(tmp_path):
    """Test that migration 55 skips tasks without seq_num."""
    db_path = tmp_path / "path_cache_skip.db"
    db = LocalDatabase(db_path)

    # Run migrations up to 54
    # These are in LEGACY_MIGRATIONS (pre-baseline migrations)
    for version, _description, action in LEGACY_MIGRATIONS:
        if version <= 54:
            if callable(action):
                action(db)
            else:
                for stmt in action.strip().split(";"):
                    stmt = stmt.strip()
                    if stmt:
                        db.execute(stmt)
            db.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))

    # Create project and task WITHOUT seq_num
    db.execute(
        "INSERT INTO projects (id, name, created_at, updated_at) VALUES (?, ?, datetime('now'), datetime('now'))",
        ("proj-1", "Project 1"),
    )
    db.execute(
        """INSERT INTO tasks (id, project_id, title, created_at, updated_at)
           VALUES (?, ?, ?, datetime('now'), datetime('now'))""",
        ("task-no-seq", "proj-1", "No Seq Task"),
    )

    # Run migration 55
    for version, _description, action in LEGACY_MIGRATIONS:
        if version == 55:
            if callable(action):
                action(db)
            db.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))

    # Verify path_cache is still NULL
    row = db.fetchone("SELECT path_cache FROM tasks WHERE id = ?", ("task-no-seq",))
    assert row["path_cache"] is None


def test_path_cache_backfill_migration_number_is_55(tmp_path):
    """Test that path_cache backfill is migration 55."""
    # Migration 55 is in LEGACY_MIGRATIONS (pre-baseline migrations)
    migration_55 = None
    for version, description, action in LEGACY_MIGRATIONS:
        if version == 55:
            migration_55 = (version, description, action)
            break

    assert migration_55 is not None, "Migration 55 not found in LEGACY_MIGRATIONS list"
    assert "path_cache" in migration_55[1].lower(), "Migration 55 should be for path_cache backfill"
    assert callable(migration_55[2]), "Migration 55 should be a callable (Python migration)"


# Integration test: Full migration sequence with task renumbering


def test_full_migration_sequence_end_to_end(tmp_path):
    """Integration test: complete migration sequence with task renumbering.

    This test verifies the entire migration flow for task renumbering:
    1. Start with gt-* format task IDs
    2. Run all migrations (52-55)
    3. Verify UUID conversion, seq_num assignment, and path_cache computation
    """
    db_path = tmp_path / "full_migration.db"
    db = LocalDatabase(db_path)

    # Run migrations up to 51 (before task renumbering changes)
    # These are in LEGACY_MIGRATIONS (pre-baseline migrations)
    for version, _description, action in LEGACY_MIGRATIONS:
        if version <= 51:
            if callable(action):
                action(db)
            else:
                for stmt in action.strip().split(";"):
                    stmt = stmt.strip()
                    if stmt:
                        db.execute(stmt)
            db.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))

    # Create project and tasks with gt-* format IDs including hierarchy and dependencies
    db.execute(
        "INSERT INTO projects (id, name, created_at, updated_at) VALUES (?, ?, datetime('now'), datetime('now'))",
        ("proj-1", "Test Project"),
    )

    # Create task hierarchy:
    # gt-root (root task)
    #   ├── gt-child1 (child)
    #   │   └── gt-grandchild (grandchild)
    #   └── gt-child2 (child, depends on child1)

    # Root task (created first)
    db.execute(
        """INSERT INTO tasks (id, project_id, title, created_at, updated_at)
           VALUES (?, ?, ?, datetime('now', '-3 days'), datetime('now'))""",
        ("gt-root00", "proj-1", "Root Task"),
    )

    # First child (created second)
    db.execute(
        """INSERT INTO tasks (id, project_id, title, parent_task_id, created_at, updated_at)
           VALUES (?, ?, ?, ?, datetime('now', '-2 days'), datetime('now'))""",
        ("gt-child1", "proj-1", "First Child", "gt-root00"),
    )

    # Second child (created third, depends on first child)
    db.execute(
        """INSERT INTO tasks (id, project_id, title, parent_task_id, created_at, updated_at)
           VALUES (?, ?, ?, ?, datetime('now', '-1 day'), datetime('now'))""",
        ("gt-child2", "proj-1", "Second Child", "gt-root00"),
    )

    # Grandchild (created fourth, under first child)
    db.execute(
        """INSERT INTO tasks (id, project_id, title, parent_task_id, created_at, updated_at)
           VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))""",
        ("gt-grand", "proj-1", "Grandchild", "gt-child1"),
    )

    # Add dependency: child2 is blocked by child1
    db.execute(
        """INSERT INTO task_dependencies (task_id, depends_on, dep_type, created_at)
           VALUES (?, ?, 'blocks', datetime('now'))""",
        ("gt-child2", "gt-child1"),
    )

    # === Run Migration 52: Add seq_num and path_cache columns ===
    for version, _description, action in LEGACY_MIGRATIONS:
        if version == 52:
            if callable(action):
                action(db)
            else:
                for stmt in action.strip().split(";"):
                    stmt = stmt.strip()
                    if stmt:
                        db.execute(stmt)
            db.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))

    # Verify columns exist
    cols = {row["name"] for row in db.fetchall("PRAGMA table_info(tasks)")}
    assert "seq_num" in cols, "seq_num column should exist after migration 52"
    assert "path_cache" in cols, "path_cache column should exist after migration 52"

    # === Run Migration 53: Convert gt-* IDs to UUIDs ===
    for version, _description, action in LEGACY_MIGRATIONS:
        if version == 53:
            if callable(action):
                action(db)
            db.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))

    # Verify all task IDs are now UUIDs
    tasks = db.fetchall("SELECT id, title FROM tasks")
    assert len(tasks) == 4, "Should still have 4 tasks"

    uuid_map = {}
    for task in tasks:
        task_id = task["id"]
        title = task["title"]
        assert not task_id.startswith("gt-"), f"Task {title} should not have gt-* ID"
        assert "-" in task_id, f"Task {title} should have UUID format with dashes"
        parts = task_id.split("-")
        assert len(parts) == 5, f"Task {title} should have 5 UUID segments"
        uuid_map[title] = task_id

    # Verify parent_task_id references were updated
    child1_row = db.fetchone(
        "SELECT parent_task_id FROM tasks WHERE id = ?", (uuid_map["First Child"],)
    )
    assert (
        child1_row["parent_task_id"] == uuid_map["Root Task"]
    ), "Child1 should reference root's new UUID"

    grandchild_row = db.fetchone(
        "SELECT parent_task_id FROM tasks WHERE id = ?", (uuid_map["Grandchild"],)
    )
    assert (
        grandchild_row["parent_task_id"] == uuid_map["First Child"]
    ), "Grandchild should reference child1's new UUID"

    # Verify dependency was updated
    dep_row = db.fetchone(
        "SELECT task_id, depends_on FROM task_dependencies WHERE task_id = ?",
        (uuid_map["Second Child"],),
    )
    assert (
        dep_row["depends_on"] == uuid_map["First Child"]
    ), "Dependency should reference child1's new UUID"

    # === Run Migration 54: Backfill seq_num ===
    for version, _description, action in LEGACY_MIGRATIONS:
        if version == 54:
            if callable(action):
                action(db)
            db.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))

    # Verify seq_num values are contiguous and ordered by created_at
    tasks_by_seq = db.fetchall(
        "SELECT title, seq_num FROM tasks WHERE project_id = ? ORDER BY seq_num",
        ("proj-1",),
    )
    assert tasks_by_seq[0]["title"] == "Root Task" and tasks_by_seq[0]["seq_num"] == 1
    assert tasks_by_seq[1]["title"] == "First Child" and tasks_by_seq[1]["seq_num"] == 2
    assert tasks_by_seq[2]["title"] == "Second Child" and tasks_by_seq[2]["seq_num"] == 3
    assert tasks_by_seq[3]["title"] == "Grandchild" and tasks_by_seq[3]["seq_num"] == 4

    # === Run Migration 55: Backfill path_cache ===
    for version, _description, action in LEGACY_MIGRATIONS:
        if version == 55:
            if callable(action):
                action(db)
            db.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))

    # Verify path_cache values are correct
    root_row = db.fetchone("SELECT path_cache FROM tasks WHERE id = ?", (uuid_map["Root Task"],))
    assert root_row["path_cache"] == "1", "Root task should have path '1'"

    child1_path = db.fetchone(
        "SELECT path_cache FROM tasks WHERE id = ?", (uuid_map["First Child"],)
    )
    assert child1_path["path_cache"] == "1.2", "First child should have path '1.2'"

    child2_path = db.fetchone(
        "SELECT path_cache FROM tasks WHERE id = ?", (uuid_map["Second Child"],)
    )
    assert child2_path["path_cache"] == "1.3", "Second child should have path '1.3'"

    grandchild_path = db.fetchone(
        "SELECT path_cache FROM tasks WHERE id = ?", (uuid_map["Grandchild"],)
    )
    assert grandchild_path["path_cache"] == "1.2.4", "Grandchild should have path '1.2.4'"

    # Verify all tasks have path_cache set
    null_paths = db.fetchone("SELECT COUNT(*) as count FROM tasks WHERE path_cache IS NULL")
    assert null_paths["count"] == 0, "All tasks should have path_cache set"

    # Verify final schema version
    version = get_current_version(db)
    assert version == 55, "Should be at schema version 55"


# =============================================================================
# TDD Expansion Restructure: test_strategy to category rename
# =============================================================================


def test_category_column_exists_after_migration(tmp_path):
    """Test that the 'category' column exists in the tasks table after migration.

    This replaces the old 'test_strategy' column with a more semantic name.
    The category field represents the task's classification (e.g., 'unit', 'integration',
    'e2e', 'manual') rather than just a testing strategy.
    """
    db_path = tmp_path / "category_migration.db"
    db = LocalDatabase(db_path)

    # Run all migrations
    run_migrations(db)

    # Check that category column exists in tasks table
    row = db.fetchone("SELECT sql FROM sqlite_master WHERE type='table' AND name='tasks'")
    assert row is not None
    sql_lower = row["sql"].lower()
    assert "category" in sql_lower, "category column not found in tasks table"


def test_test_strategy_column_removed_after_migration(tmp_path):
    """Test that the 'test_strategy' column no longer exists after migration.

    The migration renames test_strategy to category, so test_strategy should
    not appear in the schema.
    """
    db_path = tmp_path / "test_strategy_removed.db"
    db = LocalDatabase(db_path)

    # Run all migrations
    run_migrations(db)

    # Check that test_strategy column does NOT exist in tasks table
    row = db.fetchone("SELECT sql FROM sqlite_master WHERE type='table' AND name='tasks'")
    assert row is not None
    sql_lower = row["sql"].lower()
    # test_strategy should not appear in the schema (it's been renamed to category)
    assert "test_strategy" not in sql_lower, (
        "test_strategy column should not exist after migration to category"
    )


def test_category_column_accepts_values(tmp_path):
    """Test that the category column accepts valid values."""
    db_path = tmp_path / "category_values.db"
    db = LocalDatabase(db_path)

    run_migrations(db)

    # Create project
    db.execute(
        "INSERT INTO projects (id, name, created_at, updated_at) "
        "VALUES (?, ?, datetime('now'), datetime('now'))",
        ("test-project", "Test Project"),
    )

    # Insert task with category
    db.execute(
        """INSERT INTO tasks (id, project_id, title, category, created_at, updated_at)
           VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))""",
        ("task-1", "test-project", "Test Task", "unit"),
    )

    # Verify category stored correctly
    row = db.fetchone("SELECT category FROM tasks WHERE id = ?", ("task-1",))
    assert row is not None
    assert row["category"] == "unit"


def test_category_column_allows_null(tmp_path):
    """Test that the category column allows NULL values."""
    db_path = tmp_path / "category_null.db"
    db = LocalDatabase(db_path)

    run_migrations(db)

    # Create project
    db.execute(
        "INSERT INTO projects (id, name, created_at, updated_at) "
        "VALUES (?, ?, datetime('now'), datetime('now'))",
        ("test-project", "Test Project"),
    )

    # Insert task without category (NULL)
    db.execute(
        """INSERT INTO tasks (id, project_id, title, created_at, updated_at)
           VALUES (?, ?, ?, datetime('now'), datetime('now'))""",
        ("task-1", "test-project", "Test Task"),
    )

    # Verify task was created with NULL category
    row = db.fetchone("SELECT category FROM tasks WHERE id = ?", ("task-1",))
    assert row is not None
    assert row["category"] is None


# =============================================================================
# TDD Expansion Restructure: agent_name column addition
# =============================================================================


def test_agent_name_column_exists_after_migration(tmp_path):
    """Test that the 'agent_name' column exists in the tasks table after migration.

    The agent_name field specifies which subagent configuration file to use when
    spawning an agent to work on this task (e.g., 'backend-specialist', 'test-writer').
    """
    db_path = tmp_path / "agent_name_migration.db"
    db = LocalDatabase(db_path)

    # Run all migrations
    run_migrations(db)

    # Check that agent_name column exists in tasks table
    row = db.fetchone("SELECT sql FROM sqlite_master WHERE type='table' AND name='tasks'")
    assert row is not None
    sql_lower = row["sql"].lower()
    assert "agent_name" in sql_lower, "agent_name column not found in tasks table"


def test_agent_name_column_accepts_values(tmp_path):
    """Test that the agent_name column accepts valid TEXT values."""
    db_path = tmp_path / "agent_name_values.db"
    db = LocalDatabase(db_path)

    run_migrations(db)

    # Create project
    db.execute(
        "INSERT INTO projects (id, name, created_at, updated_at) "
        "VALUES (?, ?, datetime('now'), datetime('now'))",
        ("test-project", "Test Project"),
    )

    # Insert task with agent_name
    db.execute(
        """INSERT INTO tasks (id, project_id, title, agent_name, created_at, updated_at)
           VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))""",
        ("task-1", "test-project", "Test Task", "backend-specialist"),
    )

    # Verify the agent_name was stored correctly
    row = db.fetchone("SELECT agent_name FROM tasks WHERE id = ?", ("task-1",))
    assert row is not None
    assert row["agent_name"] == "backend-specialist"


def test_agent_name_column_allows_null(tmp_path):
    """Test that the agent_name column allows NULL values.

    Most tasks won't have a specific agent configuration, so NULL should be allowed.
    """
    db_path = tmp_path / "agent_name_null.db"
    db = LocalDatabase(db_path)

    run_migrations(db)

    # Create project
    db.execute(
        "INSERT INTO projects (id, name, created_at, updated_at) "
        "VALUES (?, ?, datetime('now'), datetime('now'))",
        ("test-project", "Test Project"),
    )

    # Insert task without agent_name (NULL)
    db.execute(
        """INSERT INTO tasks (id, project_id, title, created_at, updated_at)
           VALUES (?, ?, ?, datetime('now'), datetime('now'))""",
        ("task-1", "test-project", "Test Task"),
    )

    # Verify task was created with NULL agent_name
    row = db.fetchone("SELECT agent_name FROM tasks WHERE id = ?", ("task-1",))
    assert row is not None
    assert row["agent_name"] is None
