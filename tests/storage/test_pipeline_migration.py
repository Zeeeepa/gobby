"""Tests for pipeline migration (migration 80).

TDD tests for pipeline_executions and step_executions tables.
"""

import pytest

from gobby.storage.database import LocalDatabase
from gobby.storage.migrations import get_current_version, run_migrations

pytestmark = pytest.mark.unit


class TestPipelineMigration:
    """Tests for migration 80: pipeline_executions and step_executions tables."""

    def test_migration_creates_pipeline_executions_table(self, tmp_path) -> None:
        """Test that migration creates pipeline_executions table with all columns."""
        db_path = tmp_path / "pipeline_test.db"
        db = LocalDatabase(db_path)
        run_migrations(db)

        # Verify table exists
        row = db.fetchone(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            ("pipeline_executions",),
        )
        assert row is not None, "pipeline_executions table not created"

        # Verify columns exist by checking table_info
        columns = db.fetchall("PRAGMA table_info(pipeline_executions)")
        column_names = {col["name"] for col in columns}

        expected_columns = {
            "id",
            "pipeline_name",
            "project_id",
            "status",
            "inputs_json",
            "outputs_json",
            "created_at",
            "updated_at",
            "completed_at",
            "resume_token",
            "session_id",
            "parent_execution_id",
        }
        assert expected_columns.issubset(
            column_names
        ), f"Missing columns: {expected_columns - column_names}"

    def test_migration_creates_step_executions_table(self, tmp_path) -> None:
        """Test that migration creates step_executions table with all columns."""
        db_path = tmp_path / "pipeline_test.db"
        db = LocalDatabase(db_path)
        run_migrations(db)

        # Verify table exists
        row = db.fetchone(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            ("step_executions",),
        )
        assert row is not None, "step_executions table not created"

        # Verify columns exist
        columns = db.fetchall("PRAGMA table_info(step_executions)")
        column_names = {col["name"] for col in columns}

        expected_columns = {
            "id",
            "execution_id",
            "step_id",
            "status",
            "started_at",
            "completed_at",
            "input_json",
            "output_json",
            "error",
            "approval_token",
            "approved_by",
            "approved_at",
        }
        assert expected_columns.issubset(
            column_names
        ), f"Missing columns: {expected_columns - column_names}"

    def test_migration_creates_pipeline_executions_indexes(self, tmp_path) -> None:
        """Test that required indexes are created on pipeline_executions."""
        db_path = tmp_path / "pipeline_test.db"
        db = LocalDatabase(db_path)
        run_migrations(db)

        # Get all indexes for pipeline_executions
        indexes = db.fetchall(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='pipeline_executions'"
        )
        index_names = {idx["name"] for idx in indexes}

        # Check expected indexes exist
        expected_indexes = {
            "idx_pipeline_executions_project",
            "idx_pipeline_executions_status",
            "idx_pipeline_executions_resume_token",
        }
        assert expected_indexes.issubset(
            index_names
        ), f"Missing indexes: {expected_indexes - index_names}"

    def test_migration_creates_step_executions_indexes(self, tmp_path) -> None:
        """Test that required indexes are created on step_executions."""
        db_path = tmp_path / "pipeline_test.db"
        db = LocalDatabase(db_path)
        run_migrations(db)

        # Get all indexes for step_executions
        indexes = db.fetchall(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='step_executions'"
        )
        index_names = {idx["name"] for idx in indexes}

        # Check expected indexes exist
        expected_indexes = {
            "idx_step_executions_execution",
            "idx_step_executions_approval_token",
        }
        assert expected_indexes.issubset(
            index_names
        ), f"Missing indexes: {expected_indexes - index_names}"

    def test_pipeline_executions_resume_token_unique(self, tmp_path) -> None:
        """Test that resume_token has a unique constraint."""
        db_path = tmp_path / "pipeline_test.db"
        db = LocalDatabase(db_path)
        run_migrations(db)

        # Create a project first (foreign key requirement)
        db.execute(
            "INSERT INTO projects (id, name, created_at, updated_at) VALUES (?, ?, datetime('now'), datetime('now'))",
            ("test-proj", "test"),
        )

        # Insert first execution with resume_token
        db.execute(
            """INSERT INTO pipeline_executions
               (id, pipeline_name, project_id, status, created_at, updated_at, resume_token)
               VALUES (?, ?, ?, ?, datetime('now'), datetime('now'), ?)""",
            ("pe-1", "test-pipe", "test-proj", "pending", "unique-token"),
        )

        # Try to insert duplicate resume_token - should fail
        with pytest.raises(Exception) as exc_info:
            db.execute(
                """INSERT INTO pipeline_executions
                   (id, pipeline_name, project_id, status, created_at, updated_at, resume_token)
                   VALUES (?, ?, ?, ?, datetime('now'), datetime('now'), ?)""",
                ("pe-2", "test-pipe", "test-proj", "pending", "unique-token"),
            )
        assert "UNIQUE" in str(exc_info.value).upper() or "unique" in str(exc_info.value).lower()

    def test_step_executions_approval_token_unique(self, tmp_path) -> None:
        """Test that approval_token has a unique constraint."""
        db_path = tmp_path / "pipeline_test.db"
        db = LocalDatabase(db_path)
        run_migrations(db)

        # Create project and execution first
        db.execute(
            "INSERT INTO projects (id, name, created_at, updated_at) VALUES (?, ?, datetime('now'), datetime('now'))",
            ("test-proj", "test"),
        )
        db.execute(
            """INSERT INTO pipeline_executions
               (id, pipeline_name, project_id, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))""",
            ("pe-1", "test-pipe", "test-proj", "pending"),
        )

        # Insert first step with approval_token
        db.execute(
            """INSERT INTO step_executions
               (execution_id, step_id, status, approval_token)
               VALUES (?, ?, ?, ?)""",
            ("pe-1", "step1", "pending", "approval-token-1"),
        )

        # Try to insert duplicate approval_token - should fail
        with pytest.raises(Exception) as exc_info:
            db.execute(
                """INSERT INTO step_executions
                   (execution_id, step_id, status, approval_token)
                   VALUES (?, ?, ?, ?)""",
                ("pe-1", "step2", "pending", "approval-token-1"),
            )
        assert "UNIQUE" in str(exc_info.value).upper() or "unique" in str(exc_info.value).lower()

    def test_step_executions_unique_execution_step(self, tmp_path) -> None:
        """Test that (execution_id, step_id) combination is unique."""
        db_path = tmp_path / "pipeline_test.db"
        db = LocalDatabase(db_path)
        run_migrations(db)

        # Create project and execution first
        db.execute(
            "INSERT INTO projects (id, name, created_at, updated_at) VALUES (?, ?, datetime('now'), datetime('now'))",
            ("test-proj", "test"),
        )
        db.execute(
            """INSERT INTO pipeline_executions
               (id, pipeline_name, project_id, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))""",
            ("pe-1", "test-pipe", "test-proj", "pending"),
        )

        # Insert first step
        db.execute(
            """INSERT INTO step_executions
               (execution_id, step_id, status)
               VALUES (?, ?, ?)""",
            ("pe-1", "step1", "pending"),
        )

        # Try to insert same execution_id + step_id - should fail
        with pytest.raises(Exception) as exc_info:
            db.execute(
                """INSERT INTO step_executions
                   (execution_id, step_id, status)
                   VALUES (?, ?, ?)""",
                ("pe-1", "step1", "running"),
            )
        assert "UNIQUE" in str(exc_info.value).upper() or "unique" in str(exc_info.value).lower()

    def test_step_executions_foreign_key(self, tmp_path) -> None:
        """Test that step_executions has foreign key to pipeline_executions."""
        db_path = tmp_path / "pipeline_test.db"
        db = LocalDatabase(db_path)
        run_migrations(db)

        # Enable foreign key enforcement
        db.execute("PRAGMA foreign_keys = ON")

        # Create project
        db.execute(
            "INSERT INTO projects (id, name, created_at, updated_at) VALUES (?, ?, datetime('now'), datetime('now'))",
            ("test-proj", "test"),
        )

        # Try to insert step without parent execution - should fail due to FK
        with pytest.raises(Exception) as exc_info:
            db.execute(
                """INSERT INTO step_executions
                   (execution_id, step_id, status)
                   VALUES (?, ?, ?)""",
                ("nonexistent-execution", "step1", "pending"),
            )
        assert "FOREIGN KEY" in str(exc_info.value).upper() or "foreign key" in str(exc_info.value).lower()

    def test_pipeline_executions_foreign_key_to_projects(self, tmp_path) -> None:
        """Test that pipeline_executions has foreign key to projects."""
        db_path = tmp_path / "pipeline_test.db"
        db = LocalDatabase(db_path)
        run_migrations(db)

        # Enable foreign key enforcement
        db.execute("PRAGMA foreign_keys = ON")

        # Try to insert execution without valid project - should fail due to FK
        with pytest.raises(Exception) as exc_info:
            db.execute(
                """INSERT INTO pipeline_executions
                   (id, pipeline_name, project_id, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))""",
                ("pe-1", "test-pipe", "nonexistent-project", "pending"),
            )
        assert "FOREIGN KEY" in str(exc_info.value).upper() or "foreign key" in str(exc_info.value).lower()

    def test_version_reaches_80(self, tmp_path) -> None:
        """Test that database version is at least 80 after migrations."""
        db_path = tmp_path / "pipeline_test.db"
        db = LocalDatabase(db_path)
        run_migrations(db)

        version = get_current_version(db)
        assert version >= 80, f"Expected version >= 80, got {version}"
