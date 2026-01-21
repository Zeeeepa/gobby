"""TDD tests for inter_session_messages storage module.

RED phase - these tests define expected behavior before implementation exists.
Tests cover:
- InterSessionMessage dataclass
- InterSessionMessageManager CRUD operations
"""


from gobby.storage.database import LocalDatabase


class TestInterSessionMessageDataclass:
    """TDD tests for InterSessionMessage dataclass."""

    def test_import_inter_session_message(self):
        """Test that InterSessionMessage can be imported from storage module."""
        from gobby.storage.inter_session_messages import InterSessionMessage

        assert InterSessionMessage is not None

    def test_dataclass_has_required_fields(self):
        """Test that InterSessionMessage has all required fields."""
        from gobby.storage.inter_session_messages import InterSessionMessage

        # Create an instance to verify fields exist
        msg = InterSessionMessage(
            id="msg-123",
            from_session="session-parent",
            to_session="session-child",
            content="Please work on subtask A",
            priority="normal",
            sent_at="2026-01-19T12:00:00Z",
            read_at=None,
        )

        assert msg.id == "msg-123"
        assert msg.from_session == "session-parent"
        assert msg.to_session == "session-child"
        assert msg.content == "Please work on subtask A"
        assert msg.priority == "normal"
        assert msg.sent_at == "2026-01-19T12:00:00Z"
        assert msg.read_at is None

    def test_from_row_creates_instance(self, temp_db: LocalDatabase):
        """Test that InterSessionMessage.from_row creates instance from DB row."""
        from gobby.storage.inter_session_messages import InterSessionMessage
        from gobby.storage.projects import LocalProjectManager
        from gobby.storage.sessions import LocalSessionManager

        # Create project first (needed for foreign key)
        project_mgr = LocalProjectManager(temp_db)
        project = project_mgr.create(name="test-project", repo_path="/tmp/test")

        # Create sessions (needed for foreign key)
        session_mgr = LocalSessionManager(temp_db)
        parent = session_mgr.register(
            external_id="parent-ext",
            machine_id="machine-1",
            source="claude",
            project_id=project.id,
        )
        child = session_mgr.register(
            external_id="child-ext",
            machine_id="machine-1",
            source="claude",
            project_id=project.id,
        )

        # Insert message directly
        import uuid

        msg_id = str(uuid.uuid4())
        temp_db.execute(
            """INSERT INTO inter_session_messages
               (id, from_session, to_session, content, priority, sent_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'))""",
            (msg_id, parent.id, child.id, "Test content", "normal"),
        )

        # Fetch and convert
        row = temp_db.fetchone(
            "SELECT * FROM inter_session_messages WHERE id = ?", (msg_id,)
        )
        assert row is not None

        msg = InterSessionMessage.from_row(row)
        assert msg.id == msg_id
        assert msg.from_session == parent.id
        assert msg.to_session == child.id
        assert msg.content == "Test content"
        assert msg.priority == "normal"

    def test_to_dict_returns_dictionary(self):
        """Test that to_dict returns a dictionary with all fields."""
        from gobby.storage.inter_session_messages import InterSessionMessage

        msg = InterSessionMessage(
            id="msg-456",
            from_session="session-1",
            to_session="session-2",
            content="Hello child agent",
            priority="urgent",
            sent_at="2026-01-19T12:30:00Z",
            read_at="2026-01-19T12:35:00Z",
        )

        d = msg.to_dict()
        assert d["id"] == "msg-456"
        assert d["from_session"] == "session-1"
        assert d["to_session"] == "session-2"
        assert d["content"] == "Hello child agent"
        assert d["priority"] == "urgent"
        assert d["sent_at"] == "2026-01-19T12:30:00Z"
        assert d["read_at"] == "2026-01-19T12:35:00Z"


class TestInterSessionMessageManagerImport:
    """TDD tests for InterSessionMessageManager import and instantiation."""

    def test_import_manager(self):
        """Test that InterSessionMessageManager can be imported."""
        from gobby.storage.inter_session_messages import InterSessionMessageManager

        assert InterSessionMessageManager is not None

    def test_manager_accepts_database(self, temp_db: LocalDatabase):
        """Test that manager can be instantiated with database."""
        from gobby.storage.inter_session_messages import InterSessionMessageManager

        manager = InterSessionMessageManager(temp_db)
        assert manager.db is temp_db


class TestInterSessionMessageManagerCreateMessage:
    """TDD tests for create_message method."""

    def test_create_message_returns_message(self, temp_db: LocalDatabase):
        """Test that create_message returns an InterSessionMessage."""
        from gobby.storage.inter_session_messages import (
            InterSessionMessage,
            InterSessionMessageManager,
        )
        from gobby.storage.projects import LocalProjectManager
        from gobby.storage.sessions import LocalSessionManager

        # Setup project and sessions
        project_mgr = LocalProjectManager(temp_db)
        project = project_mgr.create(name="test-project", repo_path="/tmp/test")

        session_mgr = LocalSessionManager(temp_db)
        parent = session_mgr.register(
            external_id="parent", machine_id="m1", source="claude", project_id=project.id
        )
        child = session_mgr.register(
            external_id="child", machine_id="m1", source="claude", project_id=project.id
        )

        manager = InterSessionMessageManager(temp_db)
        msg = manager.create_message(
            from_session=parent.id,
            to_session=child.id,
            content="Work on task X",
            priority="normal",
        )

        assert isinstance(msg, InterSessionMessage)
        assert msg.id is not None
        assert msg.from_session == parent.id
        assert msg.to_session == child.id
        assert msg.content == "Work on task X"
        assert msg.priority == "normal"
        assert msg.read_at is None

    def test_create_message_persists_to_database(self, temp_db: LocalDatabase):
        """Test that created message is persisted to database."""
        from gobby.storage.inter_session_messages import InterSessionMessageManager
        from gobby.storage.projects import LocalProjectManager
        from gobby.storage.sessions import LocalSessionManager

        project_mgr = LocalProjectManager(temp_db)
        project = project_mgr.create(name="test-project", repo_path="/tmp/test")

        session_mgr = LocalSessionManager(temp_db)
        parent = session_mgr.register(
            external_id="parent", machine_id="m1", source="claude", project_id=project.id
        )
        child = session_mgr.register(
            external_id="child", machine_id="m1", source="claude", project_id=project.id
        )

        manager = InterSessionMessageManager(temp_db)
        msg = manager.create_message(
            from_session=parent.id,
            to_session=child.id,
            content="Persistent message",
        )

        # Verify in database
        row = temp_db.fetchone(
            "SELECT * FROM inter_session_messages WHERE id = ?", (msg.id,)
        )
        assert row is not None
        assert row["content"] == "Persistent message"

    def test_create_message_defaults_priority_to_normal(self, temp_db: LocalDatabase):
        """Test that priority defaults to 'normal' if not specified."""
        from gobby.storage.inter_session_messages import InterSessionMessageManager
        from gobby.storage.projects import LocalProjectManager
        from gobby.storage.sessions import LocalSessionManager

        project_mgr = LocalProjectManager(temp_db)
        project = project_mgr.create(name="test-project", repo_path="/tmp/test")

        session_mgr = LocalSessionManager(temp_db)
        parent = session_mgr.register(
            external_id="parent", machine_id="m1", source="claude", project_id=project.id
        )
        child = session_mgr.register(
            external_id="child", machine_id="m1", source="claude", project_id=project.id
        )

        manager = InterSessionMessageManager(temp_db)
        msg = manager.create_message(
            from_session=parent.id,
            to_session=child.id,
            content="Default priority",
        )

        assert msg.priority == "normal"


class TestInterSessionMessageManagerGetMessages:
    """TDD tests for get_messages method."""

    def test_get_messages_returns_list(self, temp_db: LocalDatabase):
        """Test that get_messages returns a list of messages."""
        from gobby.storage.inter_session_messages import InterSessionMessageManager
        from gobby.storage.projects import LocalProjectManager
        from gobby.storage.sessions import LocalSessionManager

        project_mgr = LocalProjectManager(temp_db)
        project = project_mgr.create(name="test-project", repo_path="/tmp/test")

        session_mgr = LocalSessionManager(temp_db)
        parent = session_mgr.register(
            external_id="parent", machine_id="m1", source="claude", project_id=project.id
        )
        child = session_mgr.register(
            external_id="child", machine_id="m1", source="claude", project_id=project.id
        )

        manager = InterSessionMessageManager(temp_db)
        manager.create_message(
            from_session=parent.id,
            to_session=child.id,
            content="Message 1",
        )
        manager.create_message(
            from_session=parent.id,
            to_session=child.id,
            content="Message 2",
        )

        messages = manager.get_messages(to_session=child.id)
        assert isinstance(messages, list)
        assert len(messages) == 2

    def test_get_messages_filters_by_recipient(self, temp_db: LocalDatabase):
        """Test that get_messages only returns messages for specified recipient."""
        from gobby.storage.inter_session_messages import InterSessionMessageManager
        from gobby.storage.projects import LocalProjectManager
        from gobby.storage.sessions import LocalSessionManager

        project_mgr = LocalProjectManager(temp_db)
        project = project_mgr.create(name="test-project", repo_path="/tmp/test")

        session_mgr = LocalSessionManager(temp_db)
        parent = session_mgr.register(
            external_id="parent", machine_id="m1", source="claude", project_id=project.id
        )
        child1 = session_mgr.register(
            external_id="child1", machine_id="m1", source="claude", project_id=project.id
        )
        child2 = session_mgr.register(
            external_id="child2", machine_id="m1", source="claude", project_id=project.id
        )

        manager = InterSessionMessageManager(temp_db)
        manager.create_message(
            from_session=parent.id, to_session=child1.id, content="For child 1"
        )
        manager.create_message(
            from_session=parent.id, to_session=child2.id, content="For child 2"
        )

        messages = manager.get_messages(to_session=child1.id)
        assert len(messages) == 1
        assert messages[0].content == "For child 1"

    def test_get_messages_unread_only(self, temp_db: LocalDatabase):
        """Test that get_messages with unread_only=True filters read messages."""
        from gobby.storage.inter_session_messages import InterSessionMessageManager
        from gobby.storage.projects import LocalProjectManager
        from gobby.storage.sessions import LocalSessionManager

        project_mgr = LocalProjectManager(temp_db)
        project = project_mgr.create(name="test-project", repo_path="/tmp/test")

        session_mgr = LocalSessionManager(temp_db)
        parent = session_mgr.register(
            external_id="parent", machine_id="m1", source="claude", project_id=project.id
        )
        child = session_mgr.register(
            external_id="child", machine_id="m1", source="claude", project_id=project.id
        )

        manager = InterSessionMessageManager(temp_db)
        msg1 = manager.create_message(
            from_session=parent.id, to_session=child.id, content="Unread"
        )
        msg2 = manager.create_message(
            from_session=parent.id, to_session=child.id, content="Will be read"
        )

        # Mark one as read
        manager.mark_read(msg2.id)

        # Get unread only
        messages = manager.get_messages(to_session=child.id, unread_only=True)
        assert len(messages) == 1
        assert messages[0].id == msg1.id


class TestInterSessionMessageManagerMarkRead:
    """TDD tests for mark_read method."""

    def test_mark_read_sets_read_at(self, temp_db: LocalDatabase):
        """Test that mark_read sets the read_at timestamp."""
        from gobby.storage.inter_session_messages import InterSessionMessageManager
        from gobby.storage.projects import LocalProjectManager
        from gobby.storage.sessions import LocalSessionManager

        project_mgr = LocalProjectManager(temp_db)
        project = project_mgr.create(name="test-project", repo_path="/tmp/test")

        session_mgr = LocalSessionManager(temp_db)
        parent = session_mgr.register(
            external_id="parent", machine_id="m1", source="claude", project_id=project.id
        )
        child = session_mgr.register(
            external_id="child", machine_id="m1", source="claude", project_id=project.id
        )

        manager = InterSessionMessageManager(temp_db)
        msg = manager.create_message(
            from_session=parent.id, to_session=child.id, content="To be read"
        )
        assert msg.read_at is None

        manager.mark_read(msg.id)

        # Verify in database
        row = temp_db.fetchone(
            "SELECT read_at FROM inter_session_messages WHERE id = ?", (msg.id,)
        )
        assert row["read_at"] is not None

    def test_mark_read_returns_updated_message(self, temp_db: LocalDatabase):
        """Test that mark_read returns the updated message."""
        from gobby.storage.inter_session_messages import (
            InterSessionMessage,
            InterSessionMessageManager,
        )
        from gobby.storage.projects import LocalProjectManager
        from gobby.storage.sessions import LocalSessionManager

        project_mgr = LocalProjectManager(temp_db)
        project = project_mgr.create(name="test-project", repo_path="/tmp/test")

        session_mgr = LocalSessionManager(temp_db)
        parent = session_mgr.register(
            external_id="parent", machine_id="m1", source="claude", project_id=project.id
        )
        child = session_mgr.register(
            external_id="child", machine_id="m1", source="claude", project_id=project.id
        )

        manager = InterSessionMessageManager(temp_db)
        msg = manager.create_message(
            from_session=parent.id, to_session=child.id, content="Test"
        )

        updated = manager.mark_read(msg.id)
        assert isinstance(updated, InterSessionMessage)
        assert updated.read_at is not None


class TestInterSessionMessageManagerGetMessage:
    """TDD tests for get_message method."""

    def test_get_message_returns_message(self, temp_db: LocalDatabase):
        """Test that get_message returns the message by ID."""
        from gobby.storage.inter_session_messages import (
            InterSessionMessage,
            InterSessionMessageManager,
        )
        from gobby.storage.projects import LocalProjectManager
        from gobby.storage.sessions import LocalSessionManager

        project_mgr = LocalProjectManager(temp_db)
        project = project_mgr.create(name="test-project", repo_path="/tmp/test")

        session_mgr = LocalSessionManager(temp_db)
        parent = session_mgr.register(
            external_id="parent", machine_id="m1", source="claude", project_id=project.id
        )
        child = session_mgr.register(
            external_id="child", machine_id="m1", source="claude", project_id=project.id
        )

        manager = InterSessionMessageManager(temp_db)
        created = manager.create_message(
            from_session=parent.id, to_session=child.id, content="Fetch me"
        )

        fetched = manager.get_message(created.id)
        assert isinstance(fetched, InterSessionMessage)
        assert fetched.id == created.id
        assert fetched.content == "Fetch me"

    def test_get_message_returns_none_for_missing(self, temp_db: LocalDatabase):
        """Test that get_message returns None for non-existent message."""
        from gobby.storage.inter_session_messages import InterSessionMessageManager

        manager = InterSessionMessageManager(temp_db)
        result = manager.get_message("non-existent-id")
        assert result is None


class TestInterSessionMessageManagerExport:
    """TDD tests for module exports."""

    def test_exported_from_storage_init(self):
        """Test that InterSessionMessageManager is exported from storage package."""
        from gobby.storage import InterSessionMessageManager

        assert InterSessionMessageManager is not None
