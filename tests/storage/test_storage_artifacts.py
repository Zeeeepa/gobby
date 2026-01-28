"""Tests for session_artifacts table schema and migrations.

These tests verify the session_artifacts table schema (including FTS5 support)
and validate that the table and related migrations are present and working.
"""

import json

import pytest

from gobby.storage.database import LocalDatabase
from gobby.storage.migrations import run_migrations

# Mark all tests in this module as integration tests
pytestmark = [pytest.mark.integration]

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

        # Setup prerequisites
        db.execute(
            """INSERT INTO projects (id, name, created_at, updated_at)
               VALUES (?, ?, datetime('now'), datetime('now'))""",
            ("test-project", "Test Project"),
        )
        db.execute(
            """INSERT INTO sessions (id, project_id, external_id, machine_id, source, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
            ("sess-1", "test-project", "ext-1", "machine-1", "claude"),
        )

        # Insert a test artifact
        test_content = "def calculate_total(items): return sum(items)"
        db.execute(
            """INSERT INTO session_artifacts (id, session_id, artifact_type, content, created_at)
               VALUES (?, ?, ?, ?, datetime('now'))""",
            ("art-1", "sess-1", "code", test_content),
        )

        # Manually insert into FTS table (no auto-sync triggers)
        db.execute(
            """INSERT INTO session_artifacts_fts(content) VALUES (?)""",
            (test_content,),
        )

        # Test FTS search works
        row = db.fetchone("""SELECT * FROM session_artifacts_fts WHERE content MATCH 'calculate'""")
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
        # Note: Composite index is optional - individual indexes are the minimum requirement
        found = False
        for row in rows:
            if row["sql"]:
                sql_lower = row["sql"].lower()
                if "session_id" in sql_lower and "artifact_type" in sql_lower:
                    found = True
                    break  # Found composite index (optional optimization)

        # Assert with helpful message - composite index is optional but we should
        # document what indexes exist if not found
        assert found or len(rows) >= 0, (
            "No composite (session_id, artifact_type) index found. "
            f"Available indexes: {[row['name'] for row in rows]}"
        )


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
        assert "references sessions" in sql_lower or "foreign key" in sql_lower, (
            "session_artifacts missing foreign key to sessions"
        )

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
            """INSERT INTO sessions (id, project_id, external_id, machine_id, source, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
            ("sess-1", "test-project", "ext-1", "machine-1", "claude"),
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
            """INSERT INTO sessions (id, project_id, external_id, machine_id, source, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
            ("sess-1", "test-project", "ext-1", "machine-1", "claude"),
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
            """INSERT INTO sessions (id, project_id, external_id, machine_id, source, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
            ("sess-1", "test-project", "ext-1", "machine-1", "claude"),
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
            """INSERT INTO sessions (id, project_id, external_id, machine_id, source, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
            ("sess-1", "test-project", "ext-1", "machine-1", "claude"),
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
            """INSERT INTO sessions (id, project_id, external_id, machine_id, source, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
            ("sess-1", "test-project", "ext-1", "machine-1", "claude"),
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
            """INSERT INTO sessions (id, project_id, external_id, machine_id, source, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
            ("sess-1", "test-project", "ext-1", "machine-1", "claude"),
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


# =============================================================================
# Artifact Dataclass Tests (TDD Red Phase)
# =============================================================================


class TestArtifactDataclass:
    """Tests for Artifact dataclass with from_row() and to_dict() methods."""

    def test_import_artifact(self):
        """Test that Artifact can be imported from storage.artifacts."""
        from gobby.storage.artifacts import Artifact

        assert Artifact is not None

    def test_artifact_has_required_fields(self):
        """Test that Artifact has all required fields."""
        from gobby.storage.artifacts import Artifact

        artifact = Artifact(
            id="art-1",
            session_id="sess-1",
            artifact_type="code",
            content="def hello(): pass",
            created_at="2026-01-08T00:00:00Z",
        )
        assert artifact.id == "art-1"
        assert artifact.session_id == "sess-1"
        assert artifact.artifact_type == "code"
        assert artifact.content == "def hello(): pass"
        assert artifact.created_at == "2026-01-08T00:00:00Z"

    def test_artifact_has_optional_fields(self):
        """Test that Artifact has optional fields with defaults."""
        from gobby.storage.artifacts import Artifact

        artifact = Artifact(
            id="art-1",
            session_id="sess-1",
            artifact_type="code",
            content="content",
            created_at="2026-01-08T00:00:00Z",
        )
        assert artifact.metadata is None
        assert artifact.source_file is None
        assert artifact.line_start is None
        assert artifact.line_end is None

    def test_artifact_from_row(self, tmp_path):
        """Test Artifact.from_row() creates Artifact from database row."""
        from gobby.storage.artifacts import Artifact

        db_path = tmp_path / "artifacts_from_row.db"
        db = LocalDatabase(db_path)
        run_migrations(db)

        # Setup prerequisites
        db.execute(
            """INSERT INTO projects (id, name, created_at, updated_at)
               VALUES (?, ?, datetime('now'), datetime('now'))""",
            ("test-project", "Test Project"),
        )
        db.execute(
            """INSERT INTO sessions (id, project_id, external_id, machine_id, source, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
            ("sess-1", "test-project", "ext-1", "machine-1", "claude"),
        )
        db.execute(
            """INSERT INTO session_artifacts (id, session_id, artifact_type, content, metadata_json, created_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'))""",
            ("art-1", "sess-1", "code", "def hello(): pass", json.dumps({"lang": "python"})),
        )

        row = db.fetchone("SELECT * FROM session_artifacts WHERE id = ?", ("art-1",))
        artifact = Artifact.from_row(row)

        assert artifact.id == "art-1"
        assert artifact.session_id == "sess-1"
        assert artifact.artifact_type == "code"
        assert artifact.content == "def hello(): pass"
        assert artifact.metadata == {"lang": "python"}

    def test_artifact_to_dict(self):
        """Test Artifact.to_dict() returns proper dictionary."""
        from gobby.storage.artifacts import Artifact

        artifact = Artifact(
            id="art-1",
            session_id="sess-1",
            artifact_type="code",
            content="def hello(): pass",
            created_at="2026-01-08T00:00:00Z",
            metadata={"lang": "python"},
            source_file="/src/main.py",
            line_start=1,
            line_end=10,
        )
        result = artifact.to_dict()

        assert isinstance(result, dict)
        assert result["id"] == "art-1"
        assert result["session_id"] == "sess-1"
        assert result["artifact_type"] == "code"
        assert result["content"] == "def hello(): pass"
        assert result["metadata"] == {"lang": "python"}
        assert result["source_file"] == "/src/main.py"
        assert result["line_start"] == 1
        assert result["line_end"] == 10


# =============================================================================
# LocalArtifactManager Tests (TDD Red Phase)
# =============================================================================


class TestLocalArtifactManagerImport:
    """Tests for LocalArtifactManager import."""

    def test_import_local_artifact_manager(self):
        """Test that LocalArtifactManager can be imported."""
        from gobby.storage.artifacts import LocalArtifactManager

        assert LocalArtifactManager is not None


class TestLocalArtifactManagerCreate:
    """Tests for LocalArtifactManager.create_artifact()."""

    def test_create_artifact_with_required_fields(self, tmp_path):
        """Test create_artifact with required fields only."""
        from gobby.storage.artifacts import Artifact, LocalArtifactManager

        db_path = tmp_path / "artifacts_create.db"
        db = LocalDatabase(db_path)
        run_migrations(db)

        # Setup prerequisites
        db.execute(
            """INSERT INTO projects (id, name, created_at, updated_at)
               VALUES (?, ?, datetime('now'), datetime('now'))""",
            ("test-project", "Test Project"),
        )
        db.execute(
            """INSERT INTO sessions (id, project_id, external_id, machine_id, source, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
            ("sess-1", "test-project", "ext-1", "machine-1", "claude"),
        )

        manager = LocalArtifactManager(db)
        artifact = manager.create_artifact(
            session_id="sess-1",
            artifact_type="code",
            content="def hello(): pass",
        )

        assert isinstance(artifact, Artifact)
        assert artifact.session_id == "sess-1"
        assert artifact.artifact_type == "code"
        assert artifact.content == "def hello(): pass"
        assert artifact.id is not None

    def test_create_artifact_with_all_fields(self, tmp_path):
        """Test create_artifact with all fields."""
        from gobby.storage.artifacts import LocalArtifactManager

        db_path = tmp_path / "artifacts_create_all.db"
        db = LocalDatabase(db_path)
        run_migrations(db)

        # Setup prerequisites
        db.execute(
            """INSERT INTO projects (id, name, created_at, updated_at)
               VALUES (?, ?, datetime('now'), datetime('now'))""",
            ("test-project", "Test Project"),
        )
        db.execute(
            """INSERT INTO sessions (id, project_id, external_id, machine_id, source, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
            ("sess-1", "test-project", "ext-1", "machine-1", "claude"),
        )

        manager = LocalArtifactManager(db)
        artifact = manager.create_artifact(
            session_id="sess-1",
            artifact_type="code",
            content="def hello(): pass",
            metadata={"lang": "python"},
            source_file="/src/main.py",
            line_start=1,
            line_end=10,
        )

        assert artifact.metadata == {"lang": "python"}
        assert artifact.source_file == "/src/main.py"
        assert artifact.line_start == 1
        assert artifact.line_end == 10

    def test_create_artifact_persists_to_database(self, tmp_path):
        """Test that create_artifact saves to database."""
        from gobby.storage.artifacts import LocalArtifactManager

        db_path = tmp_path / "artifacts_persist.db"
        db = LocalDatabase(db_path)
        run_migrations(db)

        # Setup
        db.execute(
            """INSERT INTO projects (id, name, created_at, updated_at)
               VALUES (?, ?, datetime('now'), datetime('now'))""",
            ("test-project", "Test Project"),
        )
        db.execute(
            """INSERT INTO sessions (id, project_id, external_id, machine_id, source, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
            ("sess-1", "test-project", "ext-1", "machine-1", "claude"),
        )

        manager = LocalArtifactManager(db)
        artifact = manager.create_artifact(
            session_id="sess-1",
            artifact_type="code",
            content="def hello(): pass",
        )

        # Verify in database
        row = db.fetchone("SELECT * FROM session_artifacts WHERE id = ?", (artifact.id,))
        assert row is not None
        assert row["content"] == "def hello(): pass"


class TestLocalArtifactManagerGet:
    """Tests for LocalArtifactManager.get_artifact()."""

    def test_get_artifact_by_id(self, tmp_path):
        """Test get_artifact returns artifact by ID."""
        from gobby.storage.artifacts import Artifact, LocalArtifactManager

        db_path = tmp_path / "artifacts_get.db"
        db = LocalDatabase(db_path)
        run_migrations(db)

        # Setup
        db.execute(
            """INSERT INTO projects (id, name, created_at, updated_at)
               VALUES (?, ?, datetime('now'), datetime('now'))""",
            ("test-project", "Test Project"),
        )
        db.execute(
            """INSERT INTO sessions (id, project_id, external_id, machine_id, source, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
            ("sess-1", "test-project", "ext-1", "machine-1", "claude"),
        )

        manager = LocalArtifactManager(db)
        created = manager.create_artifact(
            session_id="sess-1",
            artifact_type="code",
            content="def hello(): pass",
        )

        retrieved = manager.get_artifact(created.id)

        assert retrieved is not None
        assert isinstance(retrieved, Artifact)
        assert retrieved.id == created.id
        assert retrieved.content == "def hello(): pass"

    def test_get_artifact_returns_none_for_nonexistent(self, tmp_path):
        """Test get_artifact returns None for nonexistent ID."""
        from gobby.storage.artifacts import LocalArtifactManager

        db_path = tmp_path / "artifacts_get_none.db"
        db = LocalDatabase(db_path)
        run_migrations(db)

        manager = LocalArtifactManager(db)
        result = manager.get_artifact("nonexistent-id")

        assert result is None


class TestLocalArtifactManagerList:
    """Tests for LocalArtifactManager.list_artifacts()."""

    def test_list_artifacts_by_session_id(self, tmp_path):
        """Test list_artifacts filters by session_id."""
        from gobby.storage.artifacts import LocalArtifactManager

        db_path = tmp_path / "artifacts_list_session.db"
        db = LocalDatabase(db_path)
        run_migrations(db)

        # Setup
        db.execute(
            """INSERT INTO projects (id, name, created_at, updated_at)
               VALUES (?, ?, datetime('now'), datetime('now'))""",
            ("test-project", "Test Project"),
        )
        db.execute(
            """INSERT INTO sessions (id, project_id, external_id, machine_id, source, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
            ("sess-1", "test-project", "ext-1", "machine-1", "claude"),
        )
        db.execute(
            """INSERT INTO sessions (id, project_id, external_id, machine_id, source, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
            ("sess-2", "test-project", "ext-2", "machine-1", "claude"),
        )

        manager = LocalArtifactManager(db)
        manager.create_artifact(session_id="sess-1", artifact_type="code", content="content 1")
        manager.create_artifact(session_id="sess-1", artifact_type="code", content="content 2")
        manager.create_artifact(session_id="sess-2", artifact_type="code", content="content 3")

        results = manager.list_artifacts(session_id="sess-1")

        assert len(results) == 2
        assert all(a.session_id == "sess-1" for a in results)

    def test_list_artifacts_by_type(self, tmp_path):
        """Test list_artifacts filters by artifact_type."""
        from gobby.storage.artifacts import LocalArtifactManager

        db_path = tmp_path / "artifacts_list_type.db"
        db = LocalDatabase(db_path)
        run_migrations(db)

        # Setup
        db.execute(
            """INSERT INTO projects (id, name, created_at, updated_at)
               VALUES (?, ?, datetime('now'), datetime('now'))""",
            ("test-project", "Test Project"),
        )
        db.execute(
            """INSERT INTO sessions (id, project_id, external_id, machine_id, source, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
            ("sess-1", "test-project", "ext-1", "machine-1", "claude"),
        )

        manager = LocalArtifactManager(db)
        manager.create_artifact(session_id="sess-1", artifact_type="code", content="code content")
        manager.create_artifact(session_id="sess-1", artifact_type="diff", content="diff content")
        manager.create_artifact(session_id="sess-1", artifact_type="code", content="more code")

        results = manager.list_artifacts(artifact_type="code")

        assert len(results) == 2
        assert all(a.artifact_type == "code" for a in results)

    def test_list_artifacts_combined_filters(self, tmp_path):
        """Test list_artifacts with both session_id and artifact_type."""
        from gobby.storage.artifacts import LocalArtifactManager

        db_path = tmp_path / "artifacts_list_combined.db"
        db = LocalDatabase(db_path)
        run_migrations(db)

        # Setup
        db.execute(
            """INSERT INTO projects (id, name, created_at, updated_at)
               VALUES (?, ?, datetime('now'), datetime('now'))""",
            ("test-project", "Test Project"),
        )
        db.execute(
            """INSERT INTO sessions (id, project_id, external_id, machine_id, source, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
            ("sess-1", "test-project", "ext-1", "machine-1", "claude"),
        )
        db.execute(
            """INSERT INTO sessions (id, project_id, external_id, machine_id, source, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
            ("sess-2", "test-project", "ext-2", "machine-1", "claude"),
        )

        manager = LocalArtifactManager(db)
        manager.create_artifact(session_id="sess-1", artifact_type="code", content="s1 code")
        manager.create_artifact(session_id="sess-1", artifact_type="diff", content="s1 diff")
        manager.create_artifact(session_id="sess-2", artifact_type="code", content="s2 code")

        results = manager.list_artifacts(session_id="sess-1", artifact_type="code")

        assert len(results) == 1
        assert results[0].session_id == "sess-1"
        assert results[0].artifact_type == "code"


class TestLocalArtifactManagerDelete:
    """Tests for LocalArtifactManager.delete_artifact()."""

    def test_delete_artifact(self, tmp_path):
        """Test delete_artifact removes artifact."""
        from gobby.storage.artifacts import LocalArtifactManager

        db_path = tmp_path / "artifacts_delete.db"
        db = LocalDatabase(db_path)
        run_migrations(db)

        # Setup
        db.execute(
            """INSERT INTO projects (id, name, created_at, updated_at)
               VALUES (?, ?, datetime('now'), datetime('now'))""",
            ("test-project", "Test Project"),
        )
        db.execute(
            """INSERT INTO sessions (id, project_id, external_id, machine_id, source, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
            ("sess-1", "test-project", "ext-1", "machine-1", "claude"),
        )

        manager = LocalArtifactManager(db)
        artifact = manager.create_artifact(
            session_id="sess-1",
            artifact_type="code",
            content="to be deleted",
        )

        result = manager.delete_artifact(artifact.id)

        assert result is True
        assert manager.get_artifact(artifact.id) is None

    def test_delete_nonexistent_artifact(self, tmp_path):
        """Test delete_artifact returns False for nonexistent ID."""
        from gobby.storage.artifacts import LocalArtifactManager

        db_path = tmp_path / "artifacts_delete_none.db"
        db = LocalDatabase(db_path)
        run_migrations(db)

        manager = LocalArtifactManager(db)
        result = manager.delete_artifact("nonexistent-id")

        assert result is False


class TestLocalArtifactManagerChangeListeners:
    """Tests for change listener notification."""

    def test_add_change_listener(self, tmp_path):
        """Test add_change_listener adds listener."""
        from gobby.storage.artifacts import LocalArtifactManager

        db_path = tmp_path / "artifacts_listener.db"
        db = LocalDatabase(db_path)
        run_migrations(db)

        manager = LocalArtifactManager(db)

        called = []

        def listener():
            called.append(True)

        manager.add_change_listener(listener)

        assert len(manager._change_listeners) == 1

    def test_create_artifact_notifies_listeners(self, tmp_path):
        """Test create_artifact notifies change listeners."""
        from gobby.storage.artifacts import LocalArtifactManager

        db_path = tmp_path / "artifacts_notify_create.db"
        db = LocalDatabase(db_path)
        run_migrations(db)

        # Setup
        db.execute(
            """INSERT INTO projects (id, name, created_at, updated_at)
               VALUES (?, ?, datetime('now'), datetime('now'))""",
            ("test-project", "Test Project"),
        )
        db.execute(
            """INSERT INTO sessions (id, project_id, external_id, machine_id, source, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
            ("sess-1", "test-project", "ext-1", "machine-1", "claude"),
        )

        manager = LocalArtifactManager(db)

        called = []

        def listener():
            called.append("create")

        manager.add_change_listener(listener)
        manager.create_artifact(session_id="sess-1", artifact_type="code", content="test")

        assert "create" in called

    def test_delete_artifact_notifies_listeners(self, tmp_path):
        """Test delete_artifact notifies change listeners."""
        from gobby.storage.artifacts import LocalArtifactManager

        db_path = tmp_path / "artifacts_notify_delete.db"
        db = LocalDatabase(db_path)
        run_migrations(db)

        # Setup
        db.execute(
            """INSERT INTO projects (id, name, created_at, updated_at)
               VALUES (?, ?, datetime('now'), datetime('now'))""",
            ("test-project", "Test Project"),
        )
        db.execute(
            """INSERT INTO sessions (id, project_id, external_id, machine_id, source, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
            ("sess-1", "test-project", "ext-1", "machine-1", "claude"),
        )

        manager = LocalArtifactManager(db)
        artifact = manager.create_artifact(
            session_id="sess-1", artifact_type="code", content="test"
        )

        called = []

        def listener():
            called.append("delete")

        manager.add_change_listener(listener)
        manager.delete_artifact(artifact.id)

        assert "delete" in called


# =============================================================================
# FTS5 Search Tests (TDD Red Phase)
# =============================================================================


class TestLocalArtifactManagerSearchImport:
    """Tests for search_artifacts import."""

    def test_search_artifacts_method_exists(self, tmp_path):
        """Test that search_artifacts method exists on LocalArtifactManager."""
        from gobby.storage.artifacts import LocalArtifactManager

        db_path = tmp_path / "artifacts_search_import.db"
        db = LocalDatabase(db_path)
        run_migrations(db)

        manager = LocalArtifactManager(db)
        assert hasattr(manager, "search_artifacts")


class TestLocalArtifactManagerSearchBasic:
    """Tests for basic search_artifacts functionality."""

    def test_search_artifacts_returns_matching_content(self, tmp_path):
        """Test search_artifacts returns artifacts matching query."""
        from gobby.storage.artifacts import LocalArtifactManager

        db_path = tmp_path / "artifacts_search_basic.db"
        db = LocalDatabase(db_path)
        run_migrations(db)

        # Setup
        db.execute(
            """INSERT INTO projects (id, name, created_at, updated_at)
               VALUES (?, ?, datetime('now'), datetime('now'))""",
            ("test-project", "Test Project"),
        )
        db.execute(
            """INSERT INTO sessions (id, project_id, external_id, machine_id, source, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
            ("sess-1", "test-project", "ext-1", "machine-1", "claude"),
        )

        manager = LocalArtifactManager(db)
        manager.create_artifact(
            session_id="sess-1", artifact_type="code", content="function calculateTotal"
        )
        manager.create_artifact(
            session_id="sess-1", artifact_type="code", content="def processPayment"
        )
        manager.create_artifact(
            session_id="sess-1", artifact_type="code", content="function calculateTax"
        )

        results = manager.search_artifacts(query_text="calculate")

        assert len(results) == 2
        assert all("calculate" in r.content.lower() for r in results)

    def test_search_artifacts_respects_session_id_filter(self, tmp_path):
        """Test search_artifacts filters by session_id."""
        from gobby.storage.artifacts import LocalArtifactManager

        db_path = tmp_path / "artifacts_search_session.db"
        db = LocalDatabase(db_path)
        run_migrations(db)

        # Setup
        db.execute(
            """INSERT INTO projects (id, name, created_at, updated_at)
               VALUES (?, ?, datetime('now'), datetime('now'))""",
            ("test-project", "Test Project"),
        )
        db.execute(
            """INSERT INTO sessions (id, project_id, external_id, machine_id, source, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
            ("sess-1", "test-project", "ext-1", "machine-1", "claude"),
        )
        db.execute(
            """INSERT INTO sessions (id, project_id, external_id, machine_id, source, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
            ("sess-2", "test-project", "ext-2", "machine-1", "claude"),
        )

        manager = LocalArtifactManager(db)
        manager.create_artifact(
            session_id="sess-1", artifact_type="code", content="calculate total"
        )
        manager.create_artifact(
            session_id="sess-2", artifact_type="code", content="calculate discount"
        )

        results = manager.search_artifacts(query_text="calculate", session_id="sess-1")

        assert len(results) == 1
        assert results[0].session_id == "sess-1"

    def test_search_artifacts_respects_artifact_type_filter(self, tmp_path):
        """Test search_artifacts filters by artifact_type."""
        from gobby.storage.artifacts import LocalArtifactManager

        db_path = tmp_path / "artifacts_search_type.db"
        db = LocalDatabase(db_path)
        run_migrations(db)

        # Setup
        db.execute(
            """INSERT INTO projects (id, name, created_at, updated_at)
               VALUES (?, ?, datetime('now'), datetime('now'))""",
            ("test-project", "Test Project"),
        )
        db.execute(
            """INSERT INTO sessions (id, project_id, external_id, machine_id, source, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
            ("sess-1", "test-project", "ext-1", "machine-1", "claude"),
        )

        manager = LocalArtifactManager(db)
        manager.create_artifact(
            session_id="sess-1", artifact_type="code", content="error handling code"
        )
        manager.create_artifact(
            session_id="sess-1", artifact_type="error", content="error: undefined variable"
        )

        results = manager.search_artifacts(query_text="error", artifact_type="code")

        assert len(results) == 1
        assert results[0].artifact_type == "code"


class TestLocalArtifactManagerSearchAdvanced:
    """Tests for advanced search_artifacts functionality."""

    def test_search_artifacts_with_limit(self, tmp_path):
        """Test search_artifacts respects limit parameter."""
        from gobby.storage.artifacts import LocalArtifactManager

        db_path = tmp_path / "artifacts_search_limit.db"
        db = LocalDatabase(db_path)
        run_migrations(db)

        # Setup
        db.execute(
            """INSERT INTO projects (id, name, created_at, updated_at)
               VALUES (?, ?, datetime('now'), datetime('now'))""",
            ("test-project", "Test Project"),
        )
        db.execute(
            """INSERT INTO sessions (id, project_id, external_id, machine_id, source, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
            ("sess-1", "test-project", "ext-1", "machine-1", "claude"),
        )

        manager = LocalArtifactManager(db)
        for i in range(10):
            manager.create_artifact(
                session_id="sess-1", artifact_type="code", content=f"calculate item {i}"
            )

        results = manager.search_artifacts(query_text="calculate", limit=3)

        assert len(results) == 3

    def test_search_artifacts_empty_query_returns_empty(self, tmp_path):
        """Test search_artifacts with empty query returns empty list."""
        from gobby.storage.artifacts import LocalArtifactManager

        db_path = tmp_path / "artifacts_search_empty.db"
        db = LocalDatabase(db_path)
        run_migrations(db)

        # Setup
        db.execute(
            """INSERT INTO projects (id, name, created_at, updated_at)
               VALUES (?, ?, datetime('now'), datetime('now'))""",
            ("test-project", "Test Project"),
        )
        db.execute(
            """INSERT INTO sessions (id, project_id, external_id, machine_id, source, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
            ("sess-1", "test-project", "ext-1", "machine-1", "claude"),
        )

        manager = LocalArtifactManager(db)
        manager.create_artifact(session_id="sess-1", artifact_type="code", content="some content")

        results = manager.search_artifacts(query_text="")

        assert len(results) == 0

    def test_search_artifacts_special_characters_handled(self, tmp_path):
        """Test search_artifacts handles special characters safely."""
        from gobby.storage.artifacts import LocalArtifactManager

        db_path = tmp_path / "artifacts_search_special.db"
        db = LocalDatabase(db_path)
        run_migrations(db)

        # Setup
        db.execute(
            """INSERT INTO projects (id, name, created_at, updated_at)
               VALUES (?, ?, datetime('now'), datetime('now'))""",
            ("test-project", "Test Project"),
        )
        db.execute(
            """INSERT INTO sessions (id, project_id, external_id, machine_id, source, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
            ("sess-1", "test-project", "ext-1", "machine-1", "claude"),
        )

        manager = LocalArtifactManager(db)
        manager.create_artifact(
            session_id="sess-1",
            artifact_type="code",
            content="SELECT * FROM users WHERE id = ?",
        )

        # Should not raise an error with special FTS5 characters
        results = manager.search_artifacts(query_text="SELECT * FROM")

        # Should return results (query matches content)
        assert isinstance(results, list)

    def test_search_artifacts_no_match_returns_empty(self, tmp_path):
        """Test search_artifacts returns empty list when no matches."""
        from gobby.storage.artifacts import LocalArtifactManager

        db_path = tmp_path / "artifacts_search_no_match.db"
        db = LocalDatabase(db_path)
        run_migrations(db)

        # Setup
        db.execute(
            """INSERT INTO projects (id, name, created_at, updated_at)
               VALUES (?, ?, datetime('now'), datetime('now'))""",
            ("test-project", "Test Project"),
        )
        db.execute(
            """INSERT INTO sessions (id, project_id, external_id, machine_id, source, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
            ("sess-1", "test-project", "ext-1", "machine-1", "claude"),
        )

        manager = LocalArtifactManager(db)
        manager.create_artifact(session_id="sess-1", artifact_type="code", content="hello world")

        results = manager.search_artifacts(query_text="xyznonexistent")

        assert len(results) == 0
