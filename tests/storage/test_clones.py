"""Tests for local clone storage manager."""

from unittest.mock import MagicMock

import pytest

from gobby.storage.clones import Clone, CloneStatus, LocalCloneManager


class TestCloneStatus:
    """Tests for CloneStatus enum."""

    def test_values(self):
        """CloneStatus has expected values."""
        assert CloneStatus.ACTIVE.value == "active"
        assert CloneStatus.SYNCING.value == "syncing"
        assert CloneStatus.STALE.value == "stale"
        assert CloneStatus.CLEANUP.value == "cleanup"

    def test_is_string_enum(self):
        """CloneStatus values are strings."""
        for status in CloneStatus:
            assert isinstance(status.value, str)


class TestClone:
    """Tests for Clone dataclass."""

    def test_from_row(self):
        """from_row creates Clone from database row."""
        row = {
            "id": "clone-123456",
            "project_id": "proj-abc",
            "branch_name": "feature/test",
            "clone_path": "/tmp/clones/test",
            "base_branch": "main",
            "task_id": "gt-task123",
            "agent_session_id": "sess-xyz",
            "status": "active",
            "remote_url": "https://github.com/user/repo.git",
            "last_sync_at": "2026-01-22T12:00:00+00:00",
            "cleanup_after": "2026-01-23T12:00:00+00:00",
            "created_at": "2026-01-22T00:00:00+00:00",
            "updated_at": "2026-01-22T00:00:00+00:00",
        }

        clone = Clone.from_row(row)

        assert clone.id == "clone-123456"
        assert clone.project_id == "proj-abc"
        assert clone.branch_name == "feature/test"
        assert clone.clone_path == "/tmp/clones/test"
        assert clone.base_branch == "main"
        assert clone.task_id == "gt-task123"
        assert clone.agent_session_id == "sess-xyz"
        assert clone.status == "active"
        assert clone.remote_url == "https://github.com/user/repo.git"
        assert clone.last_sync_at == "2026-01-22T12:00:00+00:00"
        assert clone.cleanup_after == "2026-01-23T12:00:00+00:00"

    def test_from_row_with_nulls(self):
        """from_row handles NULL values correctly."""
        row = {
            "id": "clone-123456",
            "project_id": "proj-abc",
            "branch_name": "feature/test",
            "clone_path": "/tmp/clones/test",
            "base_branch": "main",
            "task_id": None,
            "agent_session_id": None,
            "status": "active",
            "remote_url": None,
            "last_sync_at": None,
            "cleanup_after": None,
            "created_at": "2026-01-22T00:00:00+00:00",
            "updated_at": "2026-01-22T00:00:00+00:00",
        }

        clone = Clone.from_row(row)

        assert clone.task_id is None
        assert clone.agent_session_id is None
        assert clone.remote_url is None
        assert clone.last_sync_at is None
        assert clone.cleanup_after is None

    def test_to_dict(self):
        """to_dict converts Clone to dictionary."""
        clone = Clone(
            id="clone-123456",
            project_id="proj-abc",
            branch_name="feature/test",
            clone_path="/tmp/clones/test",
            base_branch="main",
            task_id="gt-task123",
            agent_session_id="sess-xyz",
            status="active",
            remote_url="https://github.com/user/repo.git",
            last_sync_at="2026-01-22T12:00:00+00:00",
            cleanup_after="2026-01-23T12:00:00+00:00",
            created_at="2026-01-22T00:00:00+00:00",
            updated_at="2026-01-22T00:00:00+00:00",
        )

        result = clone.to_dict()

        assert result["id"] == "clone-123456"
        assert result["project_id"] == "proj-abc"
        assert result["branch_name"] == "feature/test"
        assert result["clone_path"] == "/tmp/clones/test"
        assert result["base_branch"] == "main"
        assert result["task_id"] == "gt-task123"
        assert result["agent_session_id"] == "sess-xyz"
        assert result["status"] == "active"
        assert result["remote_url"] == "https://github.com/user/repo.git"


class TestLocalCloneManagerInit:
    """Tests for LocalCloneManager initialization."""

    def test_init_stores_db(self):
        """Manager stores database reference."""
        mock_db = MagicMock()

        manager = LocalCloneManager(db=mock_db)

        assert manager.db is mock_db


class TestLocalCloneManagerCreate:
    """Tests for LocalCloneManager.create method."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database."""
        return MagicMock()

    @pytest.fixture
    def manager(self, mock_db):
        """Create manager with mock database."""
        return LocalCloneManager(db=mock_db)

    def test_create_minimal(self, manager, mock_db):
        """Create clone with minimal required fields."""
        clone = manager.create(
            project_id="proj-abc",
            branch_name="feature/test",
            clone_path="/tmp/clones/test",
        )

        assert clone.project_id == "proj-abc"
        assert clone.branch_name == "feature/test"
        assert clone.clone_path == "/tmp/clones/test"
        assert clone.base_branch == "main"
        assert clone.task_id is None
        assert clone.agent_session_id is None
        assert clone.status == "active"
        assert clone.id.startswith("clone-")
        mock_db.execute.assert_called_once()

    def test_create_with_all_fields(self, manager, mock_db):
        """Create clone with all optional fields."""
        clone = manager.create(
            project_id="proj-abc",
            branch_name="feature/test",
            clone_path="/tmp/clones/test",
            base_branch="develop",
            task_id="gt-task123",
            agent_session_id="sess-xyz",
            remote_url="https://github.com/user/repo.git",
            cleanup_after="2026-01-23T12:00:00+00:00",
        )

        assert clone.base_branch == "develop"
        assert clone.task_id == "gt-task123"
        assert clone.agent_session_id == "sess-xyz"
        assert clone.remote_url == "https://github.com/user/repo.git"
        assert clone.cleanup_after == "2026-01-23T12:00:00+00:00"

    def test_create_generates_unique_id(self, manager, mock_db):
        """Create generates unique clone ID."""
        clone1 = manager.create(
            project_id="proj-abc",
            branch_name="feature/one",
            clone_path="/tmp/clones/one",
        )
        clone2 = manager.create(
            project_id="proj-abc",
            branch_name="feature/two",
            clone_path="/tmp/clones/two",
        )

        assert clone1.id != clone2.id
        assert clone1.id.startswith("clone-")
        assert clone2.id.startswith("clone-")


class TestLocalCloneManagerGet:
    """Tests for LocalCloneManager.get method."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database."""
        return MagicMock()

    @pytest.fixture
    def manager(self, mock_db):
        """Create manager with mock database."""
        return LocalCloneManager(db=mock_db)

    def test_get_existing(self, manager, mock_db):
        """Get returns Clone for existing ID."""
        mock_db.fetchone.return_value = {
            "id": "clone-123456",
            "project_id": "proj-abc",
            "branch_name": "feature/test",
            "clone_path": "/tmp/clones/test",
            "base_branch": "main",
            "task_id": None,
            "agent_session_id": None,
            "status": "active",
            "remote_url": None,
            "last_sync_at": None,
            "cleanup_after": None,
            "created_at": "2026-01-22T00:00:00+00:00",
            "updated_at": "2026-01-22T00:00:00+00:00",
        }

        clone = manager.get("clone-123456")

        assert clone is not None
        assert clone.id == "clone-123456"
        mock_db.fetchone.assert_called_once()

    def test_get_nonexistent(self, manager, mock_db):
        """Get returns None for nonexistent ID."""
        mock_db.fetchone.return_value = None

        clone = manager.get("clone-nonexistent")

        assert clone is None


class TestLocalCloneManagerGetByTask:
    """Tests for LocalCloneManager.get_by_task method."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database."""
        return MagicMock()

    @pytest.fixture
    def manager(self, mock_db):
        """Create manager with mock database."""
        return LocalCloneManager(db=mock_db)

    def test_get_by_task_existing(self, manager, mock_db):
        """Get clone linked to task."""
        mock_db.fetchone.return_value = {
            "id": "clone-123456",
            "project_id": "proj-abc",
            "branch_name": "feature/test",
            "clone_path": "/tmp/clones/test",
            "base_branch": "main",
            "task_id": "gt-task123",
            "agent_session_id": None,
            "status": "active",
            "remote_url": None,
            "last_sync_at": None,
            "cleanup_after": None,
            "created_at": "2026-01-22T00:00:00+00:00",
            "updated_at": "2026-01-22T00:00:00+00:00",
        }

        clone = manager.get_by_task("gt-task123")

        assert clone is not None
        assert clone.task_id == "gt-task123"

    def test_get_by_task_nonexistent(self, manager, mock_db):
        """Returns None if no clone linked to task."""
        mock_db.fetchone.return_value = None

        clone = manager.get_by_task("gt-nonexistent")

        assert clone is None


class TestLocalCloneManagerList:
    """Tests for LocalCloneManager.list_clones method."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database."""
        return MagicMock()

    @pytest.fixture
    def manager(self, mock_db):
        """Create manager with mock database."""
        return LocalCloneManager(db=mock_db)

    def test_list_all(self, manager, mock_db):
        """List returns all clones."""
        mock_db.fetchall.return_value = [
            {
                "id": "clone-1",
                "project_id": "proj-abc",
                "branch_name": "feature/one",
                "clone_path": "/tmp/clones/one",
                "base_branch": "main",
                "task_id": None,
                "agent_session_id": None,
                "status": "active",
                "remote_url": None,
                "last_sync_at": None,
                "cleanup_after": None,
                "created_at": "2026-01-22T00:00:00+00:00",
                "updated_at": "2026-01-22T00:00:00+00:00",
            },
            {
                "id": "clone-2",
                "project_id": "proj-abc",
                "branch_name": "feature/two",
                "clone_path": "/tmp/clones/two",
                "base_branch": "main",
                "task_id": None,
                "agent_session_id": None,
                "status": "stale",
                "remote_url": None,
                "last_sync_at": None,
                "cleanup_after": None,
                "created_at": "2026-01-22T00:00:00+00:00",
                "updated_at": "2026-01-22T00:00:00+00:00",
            },
        ]

        clones = manager.list_clones()

        assert len(clones) == 2
        assert clones[0].id == "clone-1"
        assert clones[1].id == "clone-2"

    def test_list_with_filters(self, manager, mock_db):
        """List with project_id and status filters."""
        mock_db.fetchall.return_value = []

        manager.list_clones(project_id="proj-abc", status="active")

        # Verify query includes filters
        call_args = mock_db.fetchall.call_args
        query = call_args[0][0]
        assert "project_id = ?" in query
        assert "status = ?" in query


class TestLocalCloneManagerUpdate:
    """Tests for LocalCloneManager.update method."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database."""
        return MagicMock()

    @pytest.fixture
    def manager(self, mock_db):
        """Create manager with mock database."""
        return LocalCloneManager(db=mock_db)

    def test_update_status(self, manager, mock_db):
        """Update clone status."""
        manager.update("clone-123", status="stale")

        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args
        query = call_args[0][0]
        assert "UPDATE clones SET" in query
        assert "status = ?" in query

    def test_update_agent_session(self, manager, mock_db):
        """Update clone agent session."""
        manager.update("clone-123", agent_session_id="sess-new")

        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args
        query = call_args[0][0]
        assert "agent_session_id = ?" in query

    def test_update_last_sync(self, manager, mock_db):
        """Update clone last_sync_at."""
        manager.update("clone-123", last_sync_at="2026-01-22T12:00:00+00:00")

        mock_db.execute.assert_called_once()


class TestLocalCloneManagerDelete:
    """Tests for LocalCloneManager.delete method."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database."""
        return MagicMock()

    @pytest.fixture
    def manager(self, mock_db):
        """Create manager with mock database."""
        return LocalCloneManager(db=mock_db)

    def test_delete(self, manager, mock_db):
        """Delete removes clone record."""
        # Mock cursor with rowcount
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 1
        mock_db.execute.return_value = mock_cursor

        result = manager.delete("clone-123")

        assert result is True
        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args
        query = call_args[0][0]
        assert "DELETE FROM clones" in query
        assert "id = ?" in query


class TestLocalCloneManagerStatusMethods:
    """Tests for LocalCloneManager status helper methods."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database."""
        return MagicMock()

    @pytest.fixture
    def manager(self, mock_db):
        """Create manager with mock database."""
        return LocalCloneManager(db=mock_db)

    def test_mark_syncing(self, manager, mock_db):
        """mark_syncing updates status to syncing."""
        manager.mark_syncing("clone-123")

        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args
        params = call_args[0][1]
        assert "syncing" in params

    def test_mark_stale(self, manager, mock_db):
        """mark_stale updates status to stale."""
        manager.mark_stale("clone-123")

        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args
        params = call_args[0][1]
        assert "stale" in params

    def test_mark_cleanup(self, manager, mock_db):
        """mark_cleanup updates status to cleanup."""
        manager.mark_cleanup("clone-123")

        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args
        params = call_args[0][1]
        assert "cleanup" in params
