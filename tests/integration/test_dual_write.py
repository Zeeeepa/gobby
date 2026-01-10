"""Integration tests for dual-write database architecture.

These tests verify the full dual-write lifecycle with real database operations,
including writes to both project-local and hub databases, and resilience to
hub database failures.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from gobby.storage.database import LocalDatabase
from gobby.storage.dual_write import DualWriteDatabase
from gobby.storage.migrations import run_migrations
from gobby.storage.projects import LocalProjectManager
from gobby.storage.sessions import LocalSessionManager

# Mark all tests in this module as integration tests
pytestmark = pytest.mark.integration


@pytest.fixture
def project_dir():
    """Create a temporary project directory with .gobby/project.json."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_path = Path(tmpdir)
        gobby_dir = project_path / ".gobby"
        gobby_dir.mkdir()

        # Create project.json
        project_json = gobby_dir / "project.json"
        project_json.write_text(
            json.dumps(
                {
                    "project_id": "test-project-id",
                    "name": "Test Project",
                    "repo_path": str(project_path),
                }
            )
        )

        yield project_path


@pytest.fixture
def hub_dir():
    """Create a temporary hub directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def dual_write_db(project_dir, hub_dir):
    """Create a dual-write database setup."""
    project_db_path = project_dir / ".gobby" / "gobby.db"
    hub_db_path = hub_dir / "gobby-hub.db"

    project_db = LocalDatabase(project_db_path)
    hub_db = LocalDatabase(hub_db_path)

    run_migrations(project_db)
    run_migrations(hub_db)

    db = DualWriteDatabase(project_db, hub_db)
    yield db, project_db_path, hub_db_path
    db.close()


class TestDualWriteIntegration:
    """Integration tests for dual-write database."""

    def test_direct_execute_written_to_both_databases(self, dual_write_db, project_dir):
        """Test that direct execute writes to both databases."""
        db, project_db_path, hub_db_path = dual_write_db

        # Create project first using direct execute
        db.execute(
            """
            INSERT INTO projects (id, name, repo_path, created_at, updated_at)
            VALUES (?, ?, ?, datetime('now'), datetime('now'))
            """,
            ("test-project-id", "test-project", str(project_dir)),
        )

        # Insert task directly
        db.execute(
            """
            INSERT INTO tasks (id, project_id, title, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))
            """,
            ("task-1", "test-project-id", "Test Task", "open"),
        )

        # Verify task exists in project database
        project_db_direct = LocalDatabase(project_db_path)
        row = project_db_direct.fetchone("SELECT id, title FROM tasks WHERE id = ?", ("task-1",))
        assert row is not None
        assert row["title"] == "Test Task"

        # Verify task exists in hub database
        hub_db_direct = LocalDatabase(hub_db_path)
        row = hub_db_direct.fetchone("SELECT id, title FROM tasks WHERE id = ?", ("task-1",))
        assert row is not None
        assert row["title"] == "Test Task"

    def test_session_written_to_both_databases(self, dual_write_db, project_dir):
        """Test that creating a session writes to both databases."""
        db, project_db_path, hub_db_path = dual_write_db

        # Create project first
        project_manager = LocalProjectManager(db)
        project = project_manager.create(
            name="test-project",
            repo_path=str(project_dir),
        )

        # Create session
        session_manager = LocalSessionManager(db)
        session = session_manager.register(
            machine_id="test-machine",
            source="claude",
            project_id=project.id,
            external_id="ext-test-123",
        )

        # Verify session in project database
        project_db_direct = LocalDatabase(project_db_path)
        row = project_db_direct.fetchone(
            "SELECT id, machine_id FROM sessions WHERE id = ?", (session.id,)
        )
        assert row is not None

        # Verify session in hub database
        hub_db_direct = LocalDatabase(hub_db_path)
        row = hub_db_direct.fetchone(
            "SELECT id, machine_id FROM sessions WHERE id = ?", (session.id,)
        )
        assert row is not None

    def test_project_data_accessible_without_hub(self, project_dir):
        """Test that project data remains accessible if hub database is deleted."""
        hub_dir = tempfile.mkdtemp()
        hub_db_path = Path(hub_dir) / "gobby-hub.db"
        project_db_path = project_dir / ".gobby" / "gobby.db"

        # Create databases and dual-write
        project_db = LocalDatabase(project_db_path)
        hub_db = LocalDatabase(hub_db_path)
        run_migrations(project_db)
        run_migrations(hub_db)

        db = DualWriteDatabase(project_db, hub_db)

        # Create project using direct execute
        db.execute(
            """
            INSERT INTO projects (id, name, repo_path, created_at, updated_at)
            VALUES (?, ?, ?, datetime('now'), datetime('now'))
            """,
            ("test-project-id", "test-project", str(project_dir)),
        )

        # Insert task directly
        db.execute(
            """
            INSERT INTO tasks (id, project_id, title, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))
            """,
            ("task-persist", "test-project-id", "Persistent Task", "open"),
        )

        db.close()

        # Delete hub database
        hub_db_path.unlink()

        # Reopen project database only
        project_db_fresh = LocalDatabase(project_db_path)

        # Verify task is still accessible
        row = project_db_fresh.fetchone(
            "SELECT id, title FROM tasks WHERE id = ?", ("task-persist",)
        )
        assert row is not None
        assert row["title"] == "Persistent Task"

    def test_hub_write_failure_does_not_affect_project(self, project_dir):
        """Test that hub write failures don't affect project database writes."""
        hub_dir = tempfile.mkdtemp()
        hub_db_path = Path(hub_dir) / "gobby-hub.db"
        project_db_path = project_dir / ".gobby" / "gobby.db"

        project_db = LocalDatabase(project_db_path)
        hub_db = LocalDatabase(hub_db_path)
        run_migrations(project_db)
        run_migrations(hub_db)

        db = DualWriteDatabase(project_db, hub_db)

        # Create project using direct execute
        db.execute(
            """
            INSERT INTO projects (id, name, repo_path, created_at, updated_at)
            VALUES (?, ?, ?, datetime('now'), datetime('now'))
            """,
            ("test-project-id", "test-project", str(project_dir)),
        )

        # Make hub db fail by replacing its execute method
        db.hub_db.execute = MagicMock(side_effect=Exception("Hub database unavailable"))  # type: ignore[method-assign]

        # Insert task - should still succeed in project db
        db.execute(
            """
            INSERT INTO tasks (id, project_id, title, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))
            """,
            ("task-failure", "test-project-id", "Task Despite Hub Failure", "open"),
        )

        # Verify task in project database
        project_db_direct = LocalDatabase(project_db_path)
        row = project_db_direct.fetchone(
            "SELECT id, title FROM tasks WHERE id = ?", ("task-failure",)
        )
        assert row is not None
        assert row["title"] == "Task Despite Hub Failure"

        # Verify hub is marked unhealthy
        assert db.hub_healthy is False

    def test_safe_update_written_to_both_databases(self, dual_write_db, project_dir):
        """Test that safe_update writes to both databases."""
        db, project_db_path, hub_db_path = dual_write_db

        # Create project using direct execute
        db.execute(
            """
            INSERT INTO projects (id, name, repo_path, created_at, updated_at)
            VALUES (?, ?, ?, datetime('now'), datetime('now'))
            """,
            ("test-project-id", "test-project", str(project_dir)),
        )

        # Insert task directly
        db.execute(
            """
            INSERT INTO tasks (id, project_id, title, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))
            """,
            ("task-update", "test-project-id", "Original Title", "open"),
        )

        # Update task using safe_update
        db.safe_update(
            "tasks",
            {"title": "Updated Title", "status": "in_progress"},
            "id = ?",
            ("task-update",),
        )

        # Verify update in project database
        project_db_direct = LocalDatabase(project_db_path)
        row = project_db_direct.fetchone(
            "SELECT title, status FROM tasks WHERE id = ?", ("task-update",)
        )
        assert row is not None
        assert row["title"] == "Updated Title"
        assert row["status"] == "in_progress"

        # Verify update in hub database
        hub_db_direct = LocalDatabase(hub_db_path)
        row = hub_db_direct.fetchone(
            "SELECT title, status FROM tasks WHERE id = ?", ("task-update",)
        )
        assert row is not None
        assert row["title"] == "Updated Title"
        assert row["status"] == "in_progress"


class TestHubQueryIntegration:
    """Integration tests for hub query functionality."""

    def test_cross_project_query_via_hub(self, hub_dir):
        """Test querying data across multiple projects via hub database."""
        hub_db_path = hub_dir / "gobby-hub.db"
        hub_db_initial = LocalDatabase(hub_db_path)
        run_migrations(hub_db_initial)
        hub_db_initial.close()

        # Create two separate projects writing to same hub
        for project_name in ["project-alpha", "project-beta"]:
            project_dir = tempfile.mkdtemp()
            project_db = LocalDatabase(Path(project_dir) / "gobby.db")
            run_migrations(project_db)

            # Create dual-write for each project
            hub_db_for_project = LocalDatabase(hub_db_path)
            dual_db = DualWriteDatabase(project_db, hub_db_for_project)

            # Insert project using direct execute
            dual_db.execute(
                """
                INSERT INTO projects (id, name, repo_path, created_at, updated_at)
                VALUES (?, ?, ?, datetime('now'), datetime('now'))
                """,
                (project_name, project_name, project_dir),
            )

            # Insert task directly
            dual_db.execute(
                """
                INSERT INTO tasks (id, project_id, title, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))
                """,
                (f"task-{project_name}", project_name, f"Task from {project_name}", "open"),
            )

            dual_db.close()

        # Query hub database directly for cross-project tasks
        hub_db_query = LocalDatabase(hub_db_path)
        rows = hub_db_query.fetchall("SELECT id, project_id, title FROM tasks ORDER BY title")

        assert len(rows) == 2
        assert rows[0]["title"] == "Task from project-alpha"
        assert rows[1]["title"] == "Task from project-beta"
