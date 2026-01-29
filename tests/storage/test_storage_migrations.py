import sqlite3
from unittest.mock import patch

import pytest

from gobby.storage.database import LocalDatabase
from gobby.storage.migrations import (
    BASELINE_VERSION,
    MIGRATIONS,
    get_current_version,
    run_migrations,
)

pytestmark = pytest.mark.unit

# Calculate expected version after all migrations
EXPECTED_FINAL_VERSION = max(
    BASELINE_VERSION,
    max((m[0] for m in MIGRATIONS), default=BASELINE_VERSION),
)


def test_migrations_fresh_db(tmp_path) -> None:
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

    # Fresh databases apply baseline schema (v75) + incremental migrations
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


def test_migrations_idempotency(tmp_path) -> None:
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


def test_get_current_version_error(tmp_path) -> None:
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


def test_commits_column_exists_after_migration(tmp_path) -> None:
    """Test that the 'commits' column is added to the tasks table."""
    db_path = tmp_path / "commits_migration.db"
    db = LocalDatabase(db_path)

    # Run all migrations
    run_migrations(db)

    # Check that commits column exists in tasks table
    row = db.fetchone("SELECT sql FROM sqlite_master WHERE type='table' AND name='tasks'")
    assert row is not None
    assert "commits" in row["sql"].lower(), "commits column not found in tasks table"


def test_commits_column_allows_null(tmp_path) -> None:
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


def test_commits_column_accepts_json_array(tmp_path) -> None:
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


def test_commits_migration_idempotent(tmp_path) -> None:
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


def test_validation_history_table_exists(tmp_path) -> None:
    """Test that task_validation_history table is created."""
    db_path = tmp_path / "validation_history.db"
    db = LocalDatabase(db_path)

    run_migrations(db)

    # Check table exists
    row = db.fetchone(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='task_validation_history'"
    )
    assert row is not None, "task_validation_history table not created"


def test_validation_history_schema(tmp_path) -> None:
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


def test_validation_history_foreign_key(tmp_path) -> None:
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
    assert "references tasks" in sql_lower or "foreign key" in sql_lower, (
        "task_validation_history missing foreign key to tasks"
    )


def test_validation_history_index_exists(tmp_path) -> None:
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


def test_validation_history_cascade_delete(tmp_path) -> None:
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


def test_tasks_escalation_columns(tmp_path) -> None:
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


def test_github_columns_exist_after_migration(tmp_path) -> None:
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


def test_github_columns_allow_null(tmp_path) -> None:
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


def test_github_columns_store_values(tmp_path) -> None:
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


# =============================================================================
# Task ID Redesign: seq_num and path_cache Migration Tests
# =============================================================================


def test_seq_num_and_path_cache_columns_exist(tmp_path) -> None:
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


def test_seq_num_unique_index_per_project(tmp_path) -> None:
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


def test_path_cache_index_exists(tmp_path) -> None:
    """Test that path_cache index exists for efficient lookups."""
    db_path = tmp_path / "path_cache_index.db"
    db = LocalDatabase(db_path)

    run_migrations(db)

    # Check for index on path_cache
    rows = db.fetchall("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='tasks'")
    index_names = {row["name"] for row in rows}

    assert "idx_tasks_path_cache" in index_names, "idx_tasks_path_cache index missing"


def test_seq_num_allows_null(tmp_path) -> None:
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


def test_seq_num_stores_integer_values(tmp_path) -> None:
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


# =============================================================================
# TDD Expansion Restructure: Category Migration Tests
# =============================================================================


def test_category_column_exists_after_migration(tmp_path) -> None:
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


def test_test_strategy_column_removed_after_migration(tmp_path) -> None:
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


def test_category_column_accepts_values(tmp_path) -> None:
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


def test_category_column_allows_null(tmp_path) -> None:
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


def test_agent_name_column_exists_after_migration(tmp_path) -> None:
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


def test_agent_name_column_accepts_values(tmp_path) -> None:
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


def test_agent_name_column_allows_null(tmp_path) -> None:
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


# =============================================================================
# TDD Expansion Restructure: reference_doc column addition
# =============================================================================


def test_reference_doc_column_exists_after_migration(tmp_path) -> None:
    """Test that the 'reference_doc' column exists in the tasks table after migration.

    The reference_doc field stores the path to the source specification document
    for traceability, linking tasks back to their origin in PRDs or design docs.
    """
    db_path = tmp_path / "reference_doc_migration.db"
    db = LocalDatabase(db_path)

    # Run all migrations
    run_migrations(db)

    # Check that reference_doc column exists in tasks table
    row = db.fetchone("SELECT sql FROM sqlite_master WHERE type='table' AND name='tasks'")
    assert row is not None
    sql_lower = row["sql"].lower()
    assert "reference_doc" in sql_lower, "reference_doc column not found in tasks table"


def test_reference_doc_column_accepts_values(tmp_path) -> None:
    """Test that the reference_doc column accepts valid TEXT values."""
    db_path = tmp_path / "reference_doc_values.db"
    db = LocalDatabase(db_path)

    run_migrations(db)

    # Create project
    db.execute(
        "INSERT INTO projects (id, name, created_at, updated_at) "
        "VALUES (?, ?, datetime('now'), datetime('now'))",
        ("test-project", "Test Project"),
    )

    # Insert task with reference_doc
    db.execute(
        """INSERT INTO tasks (id, project_id, title, reference_doc, created_at, updated_at)
           VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))""",
        ("task-1", "test-project", "Test Task", "docs/specs/auth-design.md"),
    )

    # Verify the reference_doc was stored correctly
    row = db.fetchone("SELECT reference_doc FROM tasks WHERE id = ?", ("task-1",))
    assert row is not None
    assert row["reference_doc"] == "docs/specs/auth-design.md"


def test_reference_doc_column_allows_null(tmp_path) -> None:
    """Test that the reference_doc column allows NULL values.

    Most tasks won't have a reference document, so NULL should be allowed.
    """
    db_path = tmp_path / "reference_doc_null.db"
    db = LocalDatabase(db_path)

    run_migrations(db)

    # Create project
    db.execute(
        "INSERT INTO projects (id, name, created_at, updated_at) "
        "VALUES (?, ?, datetime('now'), datetime('now'))",
        ("test-project", "Test Project"),
    )

    # Insert task without reference_doc (NULL)
    db.execute(
        """INSERT INTO tasks (id, project_id, title, created_at, updated_at)
           VALUES (?, ?, ?, datetime('now'), datetime('now'))""",
        ("task-1", "test-project", "Test Task"),
    )

    # Verify task was created with NULL reference_doc
    row = db.fetchone("SELECT reference_doc FROM tasks WHERE id = ?", ("task-1",))
    assert row is not None
    assert row["reference_doc"] is None


# =============================================================================
# Task Expansion: boolean columns (is_expanded, expansion_status)
# =============================================================================


def test_boolean_columns_exist_after_migration(tmp_path) -> None:
    """Test that the boolean columns exist in the tasks table after migration.

    These flags enable idempotent batch operations:
    - is_expanded: subtasks have been created
    """
    db_path = tmp_path / "boolean_columns_migration.db"
    db = LocalDatabase(db_path)

    # Run all migrations
    run_migrations(db)

    # Check that is_expanded column exists in tasks table
    row = db.fetchone("SELECT sql FROM sqlite_master WHERE type='table' AND name='tasks'")
    assert row is not None
    sql_lower = row["sql"].lower()
    assert "is_expanded" in sql_lower, "is_expanded column not found in tasks table"
    # is_enriched was dropped in migration 66
    # is_tdd_applied was dropped in migration 74


def test_boolean_columns_accept_values(tmp_path) -> None:
    """Test that the boolean columns accept INTEGER values (0/1)."""
    db_path = tmp_path / "boolean_columns_values.db"
    db = LocalDatabase(db_path)

    run_migrations(db)

    # Create project
    db.execute(
        "INSERT INTO projects (id, name, created_at, updated_at) "
        "VALUES (?, ?, datetime('now'), datetime('now'))",
        ("test-project", "Test Project"),
    )

    # Insert task with boolean values set to true (1)
    db.execute(
        """INSERT INTO tasks (id, project_id, title, is_expanded, created_at, updated_at)
           VALUES (?, ?, ?, 1, datetime('now'), datetime('now'))""",
        ("task-1", "test-project", "Test Task"),
    )

    # Verify the boolean values were stored correctly
    row = db.fetchone(
        "SELECT is_expanded FROM tasks WHERE id = ?",
        ("task-1",),
    )
    assert row is not None
    assert row["is_expanded"] == 1


def test_boolean_columns_default_to_zero(tmp_path) -> None:
    """Test that the boolean columns default to 0 (false).

    New tasks should have all processing flags set to false by default.
    """
    db_path = tmp_path / "boolean_columns_default.db"
    db = LocalDatabase(db_path)

    run_migrations(db)

    # Create project
    db.execute(
        "INSERT INTO projects (id, name, created_at, updated_at) "
        "VALUES (?, ?, datetime('now'), datetime('now'))",
        ("test-project", "Test Project"),
    )

    # Insert task without specifying boolean values
    db.execute(
        """INSERT INTO tasks (id, project_id, title, created_at, updated_at)
           VALUES (?, ?, ?, datetime('now'), datetime('now'))""",
        ("task-1", "test-project", "Test Task"),
    )

    # Verify task was created with default values of 0
    row = db.fetchone(
        "SELECT is_expanded FROM tasks WHERE id = ?",
        ("task-1",),
    )
    assert row is not None
    assert row["is_expanded"] == 0


# =============================================================================
# Inter-Session Messaging: inter_session_messages table migration
# =============================================================================


def test_inter_session_messages_table_exists(tmp_path) -> None:
    """Test that inter_session_messages table is created after migration.

    This table enables communication between parent and child agent sessions,
    allowing agents to coordinate work without using the filesystem.
    """
    db_path = tmp_path / "inter_session_messages.db"
    db = LocalDatabase(db_path)

    run_migrations(db)

    # Check table exists
    row = db.fetchone(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='inter_session_messages'"
    )
    assert row is not None, "inter_session_messages table not created"


def test_inter_session_messages_schema(tmp_path) -> None:
    """Test that inter_session_messages has correct columns."""
    db_path = tmp_path / "inter_session_schema.db"
    db = LocalDatabase(db_path)

    run_migrations(db)

    # Get table info
    rows = db.fetchall("PRAGMA table_info(inter_session_messages)")
    columns = {row["name"] for row in rows}

    # Verify required columns exist
    expected_columns = {
        "id",
        "from_session",
        "to_session",
        "content",
        "priority",
        "sent_at",
        "read_at",
    }
    for col in expected_columns:
        assert col in columns, f"Column {col} missing from inter_session_messages"


def test_inter_session_messages_foreign_keys(tmp_path) -> None:
    """Test that inter_session_messages has foreign keys to sessions table."""
    db_path = tmp_path / "inter_session_fk.db"
    db = LocalDatabase(db_path)

    run_migrations(db)

    # Get table SQL
    row = db.fetchone(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='inter_session_messages'"
    )
    assert row is not None
    sql_lower = row["sql"].lower()

    # Check for foreign key references to sessions
    assert "references sessions" in sql_lower or "foreign key" in sql_lower, (
        "inter_session_messages missing foreign key to sessions"
    )


def test_inter_session_messages_indexes(tmp_path) -> None:
    """Test that inter_session_messages has proper indexes for queries."""
    db_path = tmp_path / "inter_session_index.db"
    db = LocalDatabase(db_path)

    run_migrations(db)

    # Check for indexes
    rows = db.fetchall(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='inter_session_messages'"
    )
    index_names = [row["name"] for row in rows]

    # Should have indexes on to_session for efficient message retrieval
    has_to_session_index = any("to_session" in name.lower() for name in index_names)
    assert has_to_session_index, f"No to_session index found. Indexes: {index_names}"


def test_inter_session_messages_insert_and_query(tmp_path) -> None:
    """Test that inter_session_messages can store and retrieve messages."""
    db_path = tmp_path / "inter_session_insert.db"
    db = LocalDatabase(db_path)

    run_migrations(db)

    # Create project and sessions first (required for foreign keys)
    db.execute(
        "INSERT INTO projects (id, name, created_at, updated_at) "
        "VALUES (?, ?, datetime('now'), datetime('now'))",
        ("test-project", "Test Project"),
    )
    db.execute(
        "INSERT INTO sessions (id, external_id, machine_id, source, project_id, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
        ("session-parent", "ext-parent", "machine-1", "claude", "test-project"),
    )
    db.execute(
        "INSERT INTO sessions (id, external_id, machine_id, source, project_id, parent_session_id, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
        ("session-child", "ext-child", "machine-1", "claude", "test-project", "session-parent"),
    )

    # Insert a message from parent to child
    import uuid

    msg_id = str(uuid.uuid4())
    db.execute(
        """INSERT INTO inter_session_messages
           (id, from_session, to_session, content, priority, sent_at)
           VALUES (?, ?, ?, ?, ?, datetime('now'))""",
        (msg_id, "session-parent", "session-child", "Please work on subtask A", "normal"),
    )

    # Query messages for child session
    row = db.fetchone(
        "SELECT * FROM inter_session_messages WHERE to_session = ?",
        ("session-child",),
    )
    assert row is not None
    assert row["from_session"] == "session-parent"
    assert row["content"] == "Please work on subtask A"
    assert row["priority"] == "normal"
    assert row["read_at"] is None  # Not read yet


def test_inter_session_messages_read_at_nullable(tmp_path) -> None:
    """Test that read_at is nullable for unread messages."""
    db_path = tmp_path / "inter_session_read.db"
    db = LocalDatabase(db_path)

    run_migrations(db)

    # Create required parent records
    db.execute(
        "INSERT INTO projects (id, name, created_at, updated_at) "
        "VALUES (?, ?, datetime('now'), datetime('now'))",
        ("test-project", "Test Project"),
    )
    db.execute(
        "INSERT INTO sessions (id, external_id, machine_id, source, project_id, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
        ("session-1", "ext-1", "machine-1", "claude", "test-project"),
    )
    db.execute(
        "INSERT INTO sessions (id, external_id, machine_id, source, project_id, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
        ("session-2", "ext-2", "machine-1", "claude", "test-project"),
    )

    import uuid

    msg_id = str(uuid.uuid4())

    # Insert message without read_at (NULL)
    db.execute(
        """INSERT INTO inter_session_messages
           (id, from_session, to_session, content, priority, sent_at)
           VALUES (?, ?, ?, ?, ?, datetime('now'))""",
        (msg_id, "session-1", "session-2", "Test message", "normal"),
    )

    row = db.fetchone("SELECT read_at FROM inter_session_messages WHERE id = ?", (msg_id,))
    assert row is not None
    assert row["read_at"] is None

    # Update to mark as read
    db.execute(
        "UPDATE inter_session_messages SET read_at = datetime('now') WHERE id = ?",
        (msg_id,),
    )

    row = db.fetchone("SELECT read_at FROM inter_session_messages WHERE id = ?", (msg_id,))
    assert row["read_at"] is not None


def test_inter_session_messages_priority_values(tmp_path) -> None:
    """Test that priority accepts expected values (normal, urgent)."""
    db_path = tmp_path / "inter_session_priority.db"
    db = LocalDatabase(db_path)

    run_migrations(db)

    # Create required parent records
    db.execute(
        "INSERT INTO projects (id, name, created_at, updated_at) "
        "VALUES (?, ?, datetime('now'), datetime('now'))",
        ("test-project", "Test Project"),
    )
    db.execute(
        "INSERT INTO sessions (id, external_id, machine_id, source, project_id, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
        ("session-1", "ext-1", "machine-1", "claude", "test-project"),
    )
    db.execute(
        "INSERT INTO sessions (id, external_id, machine_id, source, project_id, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
        ("session-2", "ext-2", "machine-1", "claude", "test-project"),
    )

    import uuid

    # Insert with normal priority
    db.execute(
        """INSERT INTO inter_session_messages
           (id, from_session, to_session, content, priority, sent_at)
           VALUES (?, ?, ?, ?, ?, datetime('now'))""",
        (str(uuid.uuid4()), "session-1", "session-2", "Normal message", "normal"),
    )

    # Insert with urgent priority
    db.execute(
        """INSERT INTO inter_session_messages
           (id, from_session, to_session, content, priority, sent_at)
           VALUES (?, ?, ?, ?, ?, datetime('now'))""",
        (str(uuid.uuid4()), "session-1", "session-2", "Urgent message", "urgent"),
    )

    # Verify both were stored
    rows = db.fetchall("SELECT priority FROM inter_session_messages ORDER BY priority")
    priorities = [row["priority"] for row in rows]
    assert "normal" in priorities
    assert "urgent" in priorities


def test_inter_session_messages_cascade_delete(tmp_path) -> None:
    """Test that deleting a session cascades to inter_session_messages."""
    db_path = tmp_path / "inter_session_cascade.db"
    db = LocalDatabase(db_path)

    run_migrations(db)

    # Enable foreign keys
    db.execute("PRAGMA foreign_keys = ON")

    # Create required parent records
    db.execute(
        "INSERT INTO projects (id, name, created_at, updated_at) "
        "VALUES (?, ?, datetime('now'), datetime('now'))",
        ("test-project", "Test Project"),
    )
    db.execute(
        "INSERT INTO sessions (id, external_id, machine_id, source, project_id, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
        ("session-1", "ext-1", "machine-1", "claude", "test-project"),
    )
    db.execute(
        "INSERT INTO sessions (id, external_id, machine_id, source, project_id, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
        ("session-2", "ext-2", "machine-1", "claude", "test-project"),
    )

    import uuid

    msg_id = str(uuid.uuid4())
    db.execute(
        """INSERT INTO inter_session_messages
           (id, from_session, to_session, content, priority, sent_at)
           VALUES (?, ?, ?, ?, ?, datetime('now'))""",
        (msg_id, "session-1", "session-2", "Test message", "normal"),
    )

    # Verify message exists
    row = db.fetchone("SELECT * FROM inter_session_messages WHERE id = ?", (msg_id,))
    assert row is not None

    # Delete the sender session
    db.execute("DELETE FROM sessions WHERE id = ?", ("session-1",))

    # Verify message was cascade deleted
    row = db.fetchone("SELECT * FROM inter_session_messages WHERE id = ?", (msg_id,))
    assert row is None, "Message should be cascade deleted when sender session is deleted"
