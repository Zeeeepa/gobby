"""Tests for session_artifacts table schema and migrations.

TDD RED PHASE: These tests verify the session_artifacts table with FTS5 support.
Tests should fail initially as the table does not exist yet.
"""

import json
import sqlite3

import pytest

from gobby.storage.database import LocalDatabase
from gobby.storage.migrations import run_migrations

# =============================================================================
# Session Artifacts Table Schema Tests
# =============================================================================


class TestSessionArtifactsTableExists:
    """Test that session_artifacts table is created."""

    def test_session_artifacts_table_created(self, tmp_path):
        """Test that session_artifacts table exists after migrations."""
        db_path = tmp_path / "artifacts.db"
        db = LocalDatabase(db_path)

        run_migrations(db)

        # Check table exists
        row = db.fetchone(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='session_artifacts'"
        )
        assert row is not None, "session_artifacts table not created"


class TestSessionArtifactsSchema:
    """Test session_artifacts table has correct columns."""

    def test_has_required_columns(self, tmp_path):
        """Test that session_artifacts has all required columns."""
        db_path = tmp_path / "artifacts_schema.db"
        db = LocalDatabase(db_path)

        run_migrations(db)

        # Get table info
        rows = db.fetchall("PRAGMA table_info(session_artifacts)")
        columns = {row["name"] for row in rows}

        # Verify required columns exist
        expected_columns = {
            "id",
            "session_id",
            "artifact_type",
            "content",
            "metadata_json",
            "created_at",
        }
        for col in expected_columns:
            assert col in columns, f"Column {col} missing from session_artifacts"

    def test_id_is_primary_key(self, tmp_path):
        """Test that id is the primary key."""
        db_path = tmp_path / "artifacts_pk.db"
        db = LocalDatabase(db_path)

        run_migrations(db)

        rows = db.fetchall("PRAGMA table_info(session_artifacts)")
        id_col = next((r for r in rows if r["name"] == "id"), None)
        assert id_col is not None
        assert id_col["pk"] == 1, "id column is not primary key"

    def test_session_id_not_null(self, tmp_path):
        """Test that session_id is NOT NULL."""
        db_path = tmp_path / "artifacts_notnull.db"
        db = LocalDatabase(db_path)

        run_migrations(db)

        rows = db.fetchall("PRAGMA table_info(session_artifacts)")
        session_id_col = next((r for r in rows if r["name"] == "session_id"), None)
        assert session_id_col is not None
        assert session_id_col["notnull"] == 1, "session_id should be NOT NULL"

    def test_artifact_type_not_null(self, tmp_path):
        """Test that artifact_type is NOT NULL."""
        db_path = tmp_path / "artifacts_type_notnull.db"
        db = LocalDatabase(db_path)

        run_migrations(db)

        rows = db.fetchall("PRAGMA table_info(session_artifacts)")
        type_col = next((r for r in rows if r["name"] == "artifact_type"), None)
        assert type_col is not None
        assert type_col["notnull"] == 1, "artifact_type should be NOT NULL"


# =============================================================================
# FTS5 Virtual Table Tests
# =============================================================================


class TestSessionArtifactsFTS5:
    """Test FTS5 virtual table for full-text search on content."""

    def test_fts5_table_exists(self, tmp_path):
        """Test that FTS5 virtual table is created for content search."""
        db_path = tmp_path / "artifacts_fts.db"
        db = LocalDatabase(db_path)

        run_migrations(db)

        # Check for FTS5 virtual table
        # FTS5 tables appear in sqlite_master with type='table' and sql containing 'fts5'
        row = db.fetchone(
            """SELECT name, sql FROM sqlite_master
               WHERE type='table' AND name LIKE 'session_artifacts_fts%'"""
        )
        assert row is not None, "FTS5 virtual table for session_artifacts not created"
        assert "fts5" in row["sql"].lower(), "Table is not an FTS5 virtual table"

    def test_fts5_indexes_content_column(self, tmp_path):
        """Test that FTS5 table indexes the content column."""
        db_path = tmp_path / "artifacts_fts_content.db"
        db = LocalDatabase(db_path)

        run_migrations(db)

        # Get FTS5 table definition
        row = db.fetchone(
            """SELECT sql FROM sqlite_master
               WHERE type='table' AND name LIKE 'session_artifacts_fts%'"""
        )
        assert row is not None, "FTS5 table not found"

        # Check that content column is indexed
        sql_lower = row["sql"].lower()
        assert "content" in sql_lower, "FTS5 table should index content column"

    def test_fts5_full_text_search_works(self, tmp_path):
        """Test that full-text search works on artifacts content."""
        db_path = tmp_path / "artifacts_fts_search.db"
        db = LocalDatabase(db_path)

        run_migrations(db)

        # Insert a test artifact
        db.execute(
            """INSERT INTO session_artifacts (id, session_id, artifact_type, content, created_at)
               VALUES (?, ?, ?, ?, datetime('now'))""",
            ("art-1", "sess-1", "code", "def calculate_total(items): return sum(items)"),
        )

        # Insert into FTS table (if using content sync or triggers)
        # The actual implementation may handle this differently
        # For now, test the FTS table can be queried
        row = db.fetchone(
            """SELECT * FROM session_artifacts_fts WHERE content MATCH 'calculate'"""
        )
        # Note: This test may fail if FTS is not properly synced with main table
        assert row is not None, "FTS search should find matching content"


# =============================================================================
# Index Tests
# =============================================================================


class TestSessionArtifactsIndexes:
    """Test index creation on session_id and artifact_type."""

    def test_session_id_index_exists(self, tmp_path):
        """Test that index on session_id exists."""
        db_path = tmp_path / "artifacts_idx_session.db"
        db = LocalDatabase(db_path)

        run_migrations(db)

        # Check for index on session_id
        rows = db.fetchall(
            """SELECT name FROM sqlite_master
               WHERE type='index' AND tbl_name='session_artifacts'"""
        )
        index_names = [row["name"] for row in rows]

        # Should have an index containing 'session' in the name
        has_session_index = any("session" in name.lower() for name in index_names)
        assert has_session_index, f"No session_id index found. Indexes: {index_names}"

    def test_artifact_type_index_exists(self, tmp_path):
        """Test that index on artifact_type exists."""
        db_path = tmp_path / "artifacts_idx_type.db"
        db = LocalDatabase(db_path)

        run_migrations(db)

        # Check for index on artifact_type
        rows = db.fetchall(
            """SELECT name FROM sqlite_master
               WHERE type='index' AND tbl_name='session_artifacts'"""
        )
        index_names = [row["name"] for row in rows]

        # Should have an index containing 'type' in the name
        has_type_index = any("type" in name.lower() for name in index_names)
        assert has_type_index, f"No artifact_type index found. Indexes: {index_names}"

    def test_composite_index_session_type(self, tmp_path):
        """Test that composite index on (session_id, artifact_type) may exist."""
        db_path = tmp_path / "artifacts_idx_composite.db"
        db = LocalDatabase(db_path)

        run_migrations(db)

        # Get index info - composite index will have multiple columns
        rows = db.fetchall(
            """SELECT name, sql FROM sqlite_master
               WHERE type='index' AND tbl_name='session_artifacts' AND sql IS NOT NULL"""
        )

        # First verify the table exists (prerequisite)
        table_row = db.fetchone(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='session_artifacts'"
        )
        assert table_row is not None, "session_artifacts table must exist first"

        # Check if any index covers both session_id and artifact_type
        has_composite = False
        for row in rows:
            if row["sql"]:
                sql_lower = row["sql"].lower()
                if "session_id" in sql_lower and "artifact_type" in sql_lower:
                    has_composite = True
                    break

        # Note: Composite index is optional - individual indexes are the minimum requirement
        # This test documents the possibility of optimization


# =============================================================================
# Migration Tests
# =============================================================================


class TestSessionArtifactsMigration:
    """Test migration applies cleanly to existing databases."""

    def test_migration_applies_cleanly(self, tmp_path):
        """Test that session_artifacts migration applies without errors."""
        db_path = tmp_path / "artifacts_migrate.db"
        db = LocalDatabase(db_path)

        # Run migrations - should not raise
        try:
            run_migrations(db)
        except Exception as e:
            pytest.fail(f"Migration failed with error: {e}")

        # Verify table was created
        row = db.fetchone(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='session_artifacts'"
        )
        assert row is not None

    def test_migration_idempotent(self, tmp_path):
        """Test that running migrations twice doesn't fail."""
        db_path = tmp_path / "artifacts_idempotent.db"
        db = LocalDatabase(db_path)

        # Run migrations twice
        run_migrations(db)
        applied = run_migrations(db)

        # Second run should apply 0 migrations
        assert applied == 0

        # Table should still exist and be valid
        row = db.fetchone(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='session_artifacts'"
        )
        assert row is not None

    def test_foreign_key_to_sessions(self, tmp_path):
        """Test that session_artifacts has foreign key to sessions table."""
        db_path = tmp_path / "artifacts_fk.db"
        db = LocalDatabase(db_path)

        run_migrations(db)

        # Get table SQL
        row = db.fetchone(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='session_artifacts'"
        )
        assert row is not None
        sql_lower = row["sql"].lower()

        # Check for foreign key reference to sessions
        assert (
            "references sessions" in sql_lower or "foreign key" in sql_lower
        ), "session_artifacts missing foreign key to sessions"

    def test_cascade_delete_on_session(self, tmp_path):
        """Test that deleting a session cascades to artifacts."""
        db_path = tmp_path / "artifacts_cascade.db"
        db = LocalDatabase(db_path)

        run_migrations(db)

        # Enable foreign keys
        db.execute("PRAGMA foreign_keys = ON")

        # Create project and session
        db.execute(
            """INSERT INTO projects (id, name, created_at, updated_at)
               VALUES (?, ?, datetime('now'), datetime('now'))""",
            ("test-project", "Test Project"),
        )
        db.execute(
            """INSERT INTO sessions (id, project_id, cli, created_at, updated_at)
               VALUES (?, ?, ?, datetime('now'), datetime('now'))""",
            ("sess-1", "test-project", "claude"),
        )

        # Insert artifact
        db.execute(
            """INSERT INTO session_artifacts (id, session_id, artifact_type, content, created_at)
               VALUES (?, ?, ?, ?, datetime('now'))""",
            ("art-1", "sess-1", "code", "print('hello')"),
        )

        # Verify artifact exists
        row = db.fetchone("SELECT * FROM session_artifacts WHERE id = ?", ("art-1",))
        assert row is not None

        # Delete the session
        db.execute("DELETE FROM sessions WHERE id = ?", ("sess-1",))

        # Verify artifact was cascade deleted
        row = db.fetchone("SELECT * FROM session_artifacts WHERE id = ?", ("art-1",))
        assert row is None, "Artifact not cascade deleted with session"


# =============================================================================
# Data Integrity Tests
# =============================================================================


class TestSessionArtifactsDataIntegrity:
    """Test data integrity for session_artifacts table."""

    def test_can_insert_artifact(self, tmp_path):
        """Test that artifacts can be inserted."""
        db_path = tmp_path / "artifacts_insert.db"
        db = LocalDatabase(db_path)

        run_migrations(db)

        # Create project and session first (for foreign key)
        db.execute(
            """INSERT INTO projects (id, name, created_at, updated_at)
               VALUES (?, ?, datetime('now'), datetime('now'))""",
            ("test-project", "Test Project"),
        )
        db.execute(
            """INSERT INTO sessions (id, project_id, cli, created_at, updated_at)
               VALUES (?, ?, ?, datetime('now'), datetime('now'))""",
            ("sess-1", "test-project", "claude"),
        )

        # Insert artifact
        db.execute(
            """INSERT INTO session_artifacts (id, session_id, artifact_type, content, metadata_json, created_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'))""",
            ("art-1", "sess-1", "code", "def hello(): pass", json.dumps({"language": "python"})),
        )

        # Verify insert
        row = db.fetchone("SELECT * FROM session_artifacts WHERE id = ?", ("art-1",))
        assert row is not None
        assert row["session_id"] == "sess-1"
        assert row["artifact_type"] == "code"
        assert row["content"] == "def hello(): pass"

    def test_metadata_json_stores_valid_json(self, tmp_path):
        """Test that metadata_json stores valid JSON."""
        db_path = tmp_path / "artifacts_json.db"
        db = LocalDatabase(db_path)

        run_migrations(db)

        # Setup
        db.execute(
            """INSERT INTO projects (id, name, created_at, updated_at)
               VALUES (?, ?, datetime('now'), datetime('now'))""",
            ("test-project", "Test Project"),
        )
        db.execute(
            """INSERT INTO sessions (id, project_id, cli, created_at, updated_at)
               VALUES (?, ?, ?, datetime('now'), datetime('now'))""",
            ("sess-1", "test-project", "claude"),
        )

        # Insert with complex metadata
        metadata = {
            "file_path": "/src/main.py",
            "lines": [1, 50],
            "symbols": ["calculate", "process"],
            "nested": {"key": "value"},
        }
        db.execute(
            """INSERT INTO session_artifacts (id, session_id, artifact_type, content, metadata_json, created_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'))""",
            ("art-1", "sess-1", "code", "# code", json.dumps(metadata)),
        )

        # Verify JSON roundtrip
        row = db.fetchone("SELECT metadata_json FROM session_artifacts WHERE id = ?", ("art-1",))
        assert row is not None
        parsed = json.loads(row["metadata_json"])
        assert parsed == metadata

    def test_content_can_be_large(self, tmp_path):
        """Test that content column can store large text."""
        db_path = tmp_path / "artifacts_large.db"
        db = LocalDatabase(db_path)

        run_migrations(db)

        # Setup
        db.execute(
            """INSERT INTO projects (id, name, created_at, updated_at)
               VALUES (?, ?, datetime('now'), datetime('now'))""",
            ("test-project", "Test Project"),
        )
        db.execute(
            """INSERT INTO sessions (id, project_id, cli, created_at, updated_at)
               VALUES (?, ?, ?, datetime('now'), datetime('now'))""",
            ("sess-1", "test-project", "claude"),
        )

        # Insert large content (100KB of text)
        large_content = "x" * (100 * 1024)
        db.execute(
            """INSERT INTO session_artifacts (id, session_id, artifact_type, content, created_at)
               VALUES (?, ?, ?, ?, datetime('now'))""",
            ("art-1", "sess-1", "file", large_content),
        )

        # Verify content stored correctly
        row = db.fetchone("SELECT content FROM session_artifacts WHERE id = ?", ("art-1",))
        assert row is not None
        assert len(row["content"]) == 100 * 1024

    def test_multiple_artifacts_per_session(self, tmp_path):
        """Test that multiple artifacts can be stored per session."""
        db_path = tmp_path / "artifacts_multi.db"
        db = LocalDatabase(db_path)

        run_migrations(db)

        # Setup
        db.execute(
            """INSERT INTO projects (id, name, created_at, updated_at)
               VALUES (?, ?, datetime('now'), datetime('now'))""",
            ("test-project", "Test Project"),
        )
        db.execute(
            """INSERT INTO sessions (id, project_id, cli, created_at, updated_at)
               VALUES (?, ?, ?, datetime('now'), datetime('now'))""",
            ("sess-1", "test-project", "claude"),
        )

        # Insert multiple artifacts
        for i in range(5):
            db.execute(
                """INSERT INTO session_artifacts (id, session_id, artifact_type, content, created_at)
                   VALUES (?, ?, ?, ?, datetime('now'))""",
                (f"art-{i}", "sess-1", "code", f"content {i}"),
            )

        # Verify all were inserted
        rows = db.fetchall("SELECT * FROM session_artifacts WHERE session_id = ?", ("sess-1",))
        assert len(rows) == 5

    def test_artifact_types(self, tmp_path):
        """Test various artifact types can be stored."""
        db_path = tmp_path / "artifacts_types.db"
        db = LocalDatabase(db_path)

        run_migrations(db)

        # Setup
        db.execute(
            """INSERT INTO projects (id, name, created_at, updated_at)
               VALUES (?, ?, datetime('now'), datetime('now'))""",
            ("test-project", "Test Project"),
        )
        db.execute(
            """INSERT INTO sessions (id, project_id, cli, created_at, updated_at)
               VALUES (?, ?, ?, datetime('now'), datetime('now'))""",
            ("sess-1", "test-project", "claude"),
        )

        # Test different artifact types
        artifact_types = ["code", "file", "diff", "error", "command", "output", "summary"]
        for i, art_type in enumerate(artifact_types):
            db.execute(
                """INSERT INTO session_artifacts (id, session_id, artifact_type, content, created_at)
                   VALUES (?, ?, ?, ?, datetime('now'))""",
                (f"art-{i}", "sess-1", art_type, f"content for {art_type}"),
            )

        # Verify all types stored
        rows = db.fetchall("SELECT artifact_type FROM session_artifacts ORDER BY artifact_type")
        stored_types = [row["artifact_type"] for row in rows]
        assert sorted(stored_types) == sorted(artifact_types)
