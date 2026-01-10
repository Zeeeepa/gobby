"""Tests for DualWriteDatabase."""

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gobby.storage.database import LocalDatabase
from gobby.storage.dual_write import DualWriteDatabase


@pytest.fixture
def project_db(tmp_path: Path) -> LocalDatabase:
    """Create a project database."""
    db_path = tmp_path / "project.db"
    db = LocalDatabase(db_path)
    db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)")
    return db


@pytest.fixture
def hub_db(tmp_path: Path) -> LocalDatabase:
    """Create a hub database."""
    db_path = tmp_path / "hub.db"
    db = LocalDatabase(db_path)
    db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)")
    return db


@pytest.fixture
def dual_db(project_db: LocalDatabase, hub_db: LocalDatabase) -> DualWriteDatabase:
    """Create a dual-write database."""
    return DualWriteDatabase(project_db, hub_db)


class TestDualWriteDatabaseInit:
    """Tests for DualWriteDatabase initialization."""

    def test_constructor_accepts_two_databases(
        self, project_db: LocalDatabase, hub_db: LocalDatabase
    ):
        """Test that constructor accepts two LocalDatabase instances."""
        dual = DualWriteDatabase(project_db, hub_db)
        assert dual.project_db is project_db
        assert dual.hub_db is hub_db

    def test_db_path_returns_project_path(self, dual_db: DualWriteDatabase):
        """Test db_path returns project database path."""
        assert dual_db.db_path == dual_db.project_db.db_path

    def test_connection_returns_project_connection(self, dual_db: DualWriteDatabase):
        """Test connection returns project database connection."""
        assert dual_db.connection is dual_db.project_db.connection

    def test_hub_healthy_initially_true(self, dual_db: DualWriteDatabase):
        """Test hub_healthy is True initially."""
        assert dual_db.hub_healthy is True


class TestDualWriteDatabaseWrite:
    """Tests for write operations."""

    def test_execute_writes_to_both_databases(self, dual_db: DualWriteDatabase):
        """Test execute writes to both project and hub databases."""
        dual_db.execute("INSERT INTO test (id, value) VALUES (1, 'hello')")

        # Verify project has the data
        project_row = dual_db.project_db.fetchone("SELECT value FROM test WHERE id=1")
        assert project_row is not None
        assert project_row["value"] == "hello"

        # Verify hub has the data
        hub_row = dual_db.hub_db.fetchone("SELECT value FROM test WHERE id=1")
        assert hub_row is not None
        assert hub_row["value"] == "hello"

    def test_executemany_writes_to_both_databases(self, dual_db: DualWriteDatabase):
        """Test executemany writes to both databases."""
        params = [(1, "a"), (2, "b"), (3, "c")]
        dual_db.executemany("INSERT INTO test (id, value) VALUES (?, ?)", params)

        # Verify project
        project_rows = dual_db.project_db.fetchall("SELECT COUNT(*) as cnt FROM test")
        assert project_rows[0]["cnt"] == 3

        # Verify hub
        hub_rows = dual_db.hub_db.fetchall("SELECT COUNT(*) as cnt FROM test")
        assert hub_rows[0]["cnt"] == 3

    def test_safe_update_writes_to_both_databases(self, dual_db: DualWriteDatabase):
        """Test safe_update writes to both databases."""
        dual_db.execute("INSERT INTO test (id, value) VALUES (1, 'old')")
        dual_db.safe_update("test", {"value": "new"}, "id = ?", (1,))

        # Verify project
        project_row = dual_db.project_db.fetchone("SELECT value FROM test WHERE id=1")
        assert project_row["value"] == "new"

        # Verify hub
        hub_row = dual_db.hub_db.fetchone("SELECT value FROM test WHERE id=1")
        assert hub_row["value"] == "new"


class TestDualWriteDatabaseRead:
    """Tests for read operations."""

    def test_fetchone_reads_from_project_only(self, dual_db: DualWriteDatabase):
        """Test fetchone only reads from project database."""
        # Insert different values into each database
        dual_db.project_db.execute("INSERT INTO test (id, value) VALUES (1, 'project')")
        dual_db.hub_db.execute("INSERT INTO test (id, value) VALUES (1, 'hub')")

        # Read should return project value
        row = dual_db.fetchone("SELECT value FROM test WHERE id=1")
        assert row is not None
        assert row["value"] == "project"

    def test_fetchall_reads_from_project_only(self, dual_db: DualWriteDatabase):
        """Test fetchall only reads from project database."""
        # Insert into project only
        dual_db.project_db.execute("INSERT INTO test (id, value) VALUES (1, 'a')")
        dual_db.project_db.execute("INSERT INTO test (id, value) VALUES (2, 'b')")

        # Insert different data into hub
        dual_db.hub_db.execute("INSERT INTO test (id, value) VALUES (1, 'x')")
        dual_db.hub_db.execute("INSERT INTO test (id, value) VALUES (2, 'y')")
        dual_db.hub_db.execute("INSERT INTO test (id, value) VALUES (3, 'z')")

        # Read should return project data
        rows = dual_db.fetchall("SELECT value FROM test ORDER BY id")
        assert len(rows) == 2
        assert rows[0]["value"] == "a"
        assert rows[1]["value"] == "b"


class TestDualWriteDatabaseHubFailure:
    """Tests for hub database failure handling."""

    def test_hub_execute_failure_is_logged_not_raised(
        self, dual_db: DualWriteDatabase, caplog
    ):
        """Test hub execute failure is logged but doesn't raise."""
        # Make hub fail by dropping the table
        dual_db.hub_db.execute("DROP TABLE test")

        # This should succeed (project write) despite hub failure
        with caplog.at_level("WARNING"):
            dual_db.execute("INSERT INTO test (id, value) VALUES (1, 'hello')")

        # Verify project succeeded
        row = dual_db.project_db.fetchone("SELECT value FROM test WHERE id=1")
        assert row["value"] == "hello"

        # Verify hub failure was logged
        assert "Hub database" in caplog.text
        assert dual_db.hub_healthy is False

    def test_hub_safe_update_failure_is_logged_not_raised(
        self, dual_db: DualWriteDatabase, caplog
    ):
        """Test hub safe_update failure is logged but doesn't raise."""
        # Insert initial data
        dual_db.execute("INSERT INTO test (id, value) VALUES (1, 'old')")

        # Make hub fail
        dual_db.hub_db.execute("DROP TABLE test")

        # This should succeed despite hub failure
        with caplog.at_level("WARNING"):
            dual_db.safe_update("test", {"value": "new"}, "id = ?", (1,))

        # Verify project succeeded
        row = dual_db.project_db.fetchone("SELECT value FROM test WHERE id=1")
        assert row["value"] == "new"

        # Verify hub failure was logged
        assert "Hub database" in caplog.text

    def test_hub_recovers_after_failure(self, dual_db: DualWriteDatabase):
        """Test hub_healthy returns to True after successful write."""
        # Make hub fail
        dual_db.hub_db.execute("DROP TABLE test")
        dual_db.execute("INSERT INTO test (id, value) VALUES (1, 'test')")
        assert dual_db.hub_healthy is False

        # Recreate hub table
        dual_db.hub_db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)")

        # Next write should succeed and restore health
        dual_db.execute("INSERT INTO test (id, value) VALUES (2, 'recover')")
        assert dual_db.hub_healthy is True


class TestDualWriteDatabaseTransaction:
    """Tests for transaction handling.

    Note: Transactions yield the raw project connection, so writes inside
    the transaction context go to project only. Hub writes happen through
    the dual_db.execute() method, not conn.execute().
    """

    def test_transaction_commits_to_project(self, dual_db: DualWriteDatabase):
        """Test transaction commits to project database."""
        with dual_db.transaction() as conn:
            conn.execute("INSERT INTO test (id, value) VALUES (1, 'tx')")

        # Verify project has the data
        project_row = dual_db.project_db.fetchone("SELECT value FROM test WHERE id=1")
        assert project_row["value"] == "tx"

    def test_transaction_rollback_on_exception(self, dual_db: DualWriteDatabase):
        """Test transaction rolls back on exception."""
        try:
            with dual_db.transaction() as conn:
                conn.execute("INSERT INTO test (id, value) VALUES (1, 'rollback')")
                raise ValueError("Simulated error")
        except ValueError:
            pass

        # Verify project doesn't have the data (rolled back)
        project_row = dual_db.project_db.fetchone("SELECT value FROM test WHERE id=1")
        assert project_row is None


class TestDualWriteDatabaseClose:
    """Tests for close operation."""

    def test_close_closes_both_databases(
        self, project_db: LocalDatabase, hub_db: LocalDatabase
    ):
        """Test close closes both database connections."""
        dual = DualWriteDatabase(project_db, hub_db)
        dual.close()

        # Both should be closed (connection set to None)
        assert project_db._local.connection is None
        assert hub_db._local.connection is None
