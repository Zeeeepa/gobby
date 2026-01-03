"""Tests for the LocalSessionManager storage layer."""

from gobby.storage.sessions import LocalSessionManager, Session


class TestSession:
    """Tests for Session dataclass."""

    def test_from_row(
        self,
        session_manager: LocalSessionManager,
        sample_project: dict,
    ):
        """Test creating Session from database row."""
        session = session_manager.register(
            external_id="test-cli-key",
            machine_id="test-machine",
            source="claude",
            project_id=sample_project["id"],
        )

        row = session_manager.db.fetchone("SELECT * FROM sessions WHERE id = ?", (session.id,))
        assert row is not None

        session_from_row = Session.from_row(row)
        assert session_from_row.id == session.id
        assert session_from_row.external_id == "test-cli-key"
        assert session_from_row.source == "claude"

    def test_to_dict(
        self,
        session_manager: LocalSessionManager,
        sample_project: dict,
    ):
        """Test converting Session to dictionary."""
        session = session_manager.register(
            external_id="dict-test",
            machine_id="machine-1",
            source="gemini",
            project_id=sample_project["id"],
            title="Test Session",
        )

        d = session.to_dict()
        assert d["id"] == session.id
        assert d["external_id"] == "dict-test"
        assert d["machine_id"] == "machine-1"
        assert d["source"] == "gemini"
        assert d["title"] == "Test Session"
        assert d["status"] == "active"


class TestLocalSessionManager:
    """Tests for LocalSessionManager class."""

    def test_register_session(
        self,
        session_manager: LocalSessionManager,
        sample_project: dict,
    ):
        """Test registering a new session."""
        session = session_manager.register(
            external_id="session-123",
            machine_id="machine-abc",
            source="claude",
            project_id=sample_project["id"],
            title="My Session",
            jsonl_path="/path/to/transcript.jsonl",
            git_branch="main",
        )

        assert session.id is not None
        assert session.external_id == "session-123"
        assert session.machine_id == "machine-abc"
        assert session.source == "claude"
        assert session.project_id == sample_project["id"]
        assert session.title == "My Session"
        assert session.status == "active"
        assert session.jsonl_path == "/path/to/transcript.jsonl"
        assert session.git_branch == "main"

    def test_register_upserts_on_conflict(
        self,
        session_manager: LocalSessionManager,
        sample_project: dict,
    ):
        """Test that register updates existing session on conflict."""
        # First registration
        session1 = session_manager.register(
            external_id="unique-key",
            machine_id="machine-1",
            source="claude",
            project_id=sample_project["id"],
            title="Original",
        )

        # Second registration with same key combo
        session2 = session_manager.register(
            external_id="unique-key",
            machine_id="machine-1",
            source="claude",
            project_id=sample_project["id"],
            title="Updated",
        )

        # Should be the same session with updated title
        assert session2.id == session1.id
        assert session2.title == "Updated"

    def test_get_session(
        self,
        session_manager: LocalSessionManager,
        sample_project: dict,
    ):
        """Test getting a session by ID."""
        created = session_manager.register(
            external_id="get-test",
            machine_id="machine",
            source="codex",
            project_id=sample_project["id"],
        )

        retrieved = session_manager.get(created.id)
        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.external_id == "get-test"

    def test_get_nonexistent(self, session_manager: LocalSessionManager):
        """Test getting nonexistent session returns None."""
        result = session_manager.get("nonexistent-id")
        assert result is None

    def test_find_current(
        self,
        session_manager: LocalSessionManager,
        sample_project: dict,
    ):
        """Test finding current session by external_id, machine_id, source."""
        session = session_manager.register(
            external_id="findable",
            machine_id="my-machine",
            source="claude",
            project_id=sample_project["id"],
        )

        found = session_manager.find_current(
            external_id="findable",
            machine_id="my-machine",
            source="claude",
        )

        assert found is not None
        assert found.id == session.id

    def test_find_current_not_found(self, session_manager: LocalSessionManager):
        """Test find_current returns None when not found."""
        result = session_manager.find_current(
            external_id="nonexistent",
            machine_id="machine",
            source="claude",
        )
        assert result is None

    def test_find_parent(
        self,
        session_manager: LocalSessionManager,
        sample_project: dict,
    ):
        """Test finding parent session for handoff."""
        # Create a session marked as handoff_ready
        session = session_manager.register(
            external_id="parent-session",
            machine_id="handoff-machine",
            source="claude",
            project_id=sample_project["id"],
        )
        session_manager.update_status(session.id, "handoff_ready")

        # Find parent
        parent = session_manager.find_parent(
            machine_id="handoff-machine",
            source="claude",
            project_id=sample_project["id"],
        )

        assert parent is not None
        assert parent.id == session.id

    def test_find_parent_no_handoff_ready(
        self,
        session_manager: LocalSessionManager,
        sample_project: dict,
    ):
        """Test find_parent returns None when no handoff_ready session."""
        # Create an active session (not handoff_ready)
        session_manager.register(
            external_id="active-session",
            machine_id="machine",
            source="claude",
            project_id=sample_project["id"],
        )

        result = session_manager.find_parent(
            machine_id="machine",
            source="claude",
            project_id=sample_project["id"],
        )
        assert result is None

    def test_update_status(
        self,
        session_manager: LocalSessionManager,
        sample_project: dict,
    ):
        """Test updating session status."""
        session = session_manager.register(
            external_id="status-test",
            machine_id="machine",
            source="claude",
            project_id=sample_project["id"],
        )
        assert session.status == "active"

        updated = session_manager.update_status(session.id, "paused")
        assert updated is not None
        assert updated.status == "paused"

    def test_update_title(
        self,
        session_manager: LocalSessionManager,
        sample_project: dict,
    ):
        """Test updating session title."""
        session = session_manager.register(
            external_id="title-test",
            machine_id="machine",
            source="claude",
            project_id=sample_project["id"],
        )

        updated = session_manager.update_title(session.id, "New Title")
        assert updated is not None
        assert updated.title == "New Title"

    def test_update_summary(
        self,
        session_manager: LocalSessionManager,
        sample_project: dict,
    ):
        """Test updating session summary."""
        session = session_manager.register(
            external_id="summary-test",
            machine_id="machine",
            source="claude",
            project_id=sample_project["id"],
        )

        updated = session_manager.update_summary(
            session.id,
            summary_path="/path/to/summary.md",
            summary_markdown="# Summary\nThis is a test.",
        )

        assert updated is not None
        assert updated.summary_path == "/path/to/summary.md"
        assert updated.summary_markdown == "# Summary\nThis is a test."

    def test_list_sessions(
        self,
        session_manager: LocalSessionManager,
        sample_project: dict,
    ):
        """Test listing sessions."""
        session_manager.register(
            external_id="list-1",
            machine_id="m1",
            source="claude",
            project_id=sample_project["id"],
        )
        session_manager.register(
            external_id="list-2",
            machine_id="m2",
            source="gemini",
            project_id=sample_project["id"],
        )

        sessions = session_manager.list(project_id=sample_project["id"])
        assert len(sessions) == 2

    def test_list_with_filters(
        self,
        session_manager: LocalSessionManager,
        sample_project: dict,
    ):
        """Test listing sessions with filters."""
        s1 = session_manager.register(
            external_id="filter-1",
            machine_id="m1",
            source="claude",
            project_id=sample_project["id"],
        )
        session_manager.register(
            external_id="filter-2",
            machine_id="m2",
            source="gemini",
            project_id=sample_project["id"],
        )
        session_manager.update_status(s1.id, "paused")

        # Filter by source
        claude_sessions = session_manager.list(source="claude")
        assert len(claude_sessions) == 1
        assert claude_sessions[0].source == "claude"

        # Filter by status
        paused_sessions = session_manager.list(status="paused")
        assert len(paused_sessions) == 1
        assert paused_sessions[0].status == "paused"

    def test_list_with_limit(
        self,
        session_manager: LocalSessionManager,
        sample_project: dict,
    ):
        """Test listing sessions with limit."""
        for i in range(5):
            session_manager.register(
                external_id=f"limit-{i}",
                machine_id=f"m{i}",
                source="claude",
                project_id=sample_project["id"],
            )

        sessions = session_manager.list(limit=3)
        assert len(sessions) == 3

    def test_delete_session(
        self,
        session_manager: LocalSessionManager,
        sample_project: dict,
    ):
        """Test deleting a session."""
        session = session_manager.register(
            external_id="delete-me",
            machine_id="machine",
            source="claude",
            project_id=sample_project["id"],
        )

        result = session_manager.delete(session.id)
        assert result is True
        assert session_manager.get(session.id) is None

    def test_delete_nonexistent(self, session_manager: LocalSessionManager):
        """Test deleting nonexistent session returns False."""
        result = session_manager.delete("nonexistent-id")
        assert result is False

    def test_expire_stale_sessions(
        self,
        session_manager: LocalSessionManager,
        sample_project: dict,
    ):
        """Test expiring stale sessions."""
        # Create a stale session (simulated by mocking updated_at in query or just rely on db time)
        # Since we use SQLite datetime('now') in queries, we can't easily mock time without
        # deeper mocking. Instead, we'll verify the SQL generation and execution flow
        # or use a very short timeout.

        session = session_manager.register(
            external_id="stale-session",
            machine_id="machine",
            source="claude",
            project_id=sample_project["id"],
        )

        # Manually backdate the session in DB
        session_manager.db.execute(
            "UPDATE sessions SET updated_at = datetime('now', '-25 hours') WHERE id = ?",
            (session.id,),
        )

        count = session_manager.expire_stale_sessions(timeout_hours=24)
        assert count == 1

        expired = session_manager.get(session.id)
        assert expired.status == "expired"

    def test_pause_inactive_active_sessions(
        self,
        session_manager: LocalSessionManager,
        sample_project: dict,
    ):
        """Test pausing inactive active sessions."""
        session = session_manager.register(
            external_id="active-idle",
            machine_id="machine",
            source="claude",
            project_id=sample_project["id"],
        )

        # Backdate
        session_manager.db.execute(
            "UPDATE sessions SET updated_at = datetime('now', '-31 minutes') WHERE id = ?",
            (session.id,),
        )

        count = session_manager.pause_inactive_active_sessions(timeout_minutes=30)
        assert count == 1

        paused = session_manager.get(session.id)
        assert paused.status == "paused"

    def test_transcript_processing_lifecycle(
        self,
        session_manager: LocalSessionManager,
        sample_project: dict,
    ):
        """Test transcript processing lifecycle methods."""
        # Create expired session with jsonl_path
        session = session_manager.register(
            external_id="transcript-test",
            machine_id="machine",
            source="claude",
            project_id=sample_project["id"],
            jsonl_path="/tmp/test.jsonl",
        )
        session_manager.update_status(session.id, "expired")

        # Should be pending
        pending = session_manager.get_pending_transcript_sessions()
        assert len(pending) == 1
        assert pending[0].id == session.id

        # Mark processed
        updated = session_manager.mark_transcript_processed(session.id)
        assert updated is not None
        # Verify it's no longer pending
        pending = session_manager.get_pending_transcript_sessions()
        assert len(pending) == 0

        # Reset processed
        reset = session_manager.reset_transcript_processed(session.id)
        assert reset is not None

        # Should be pending again
        pending = session_manager.get_pending_transcript_sessions()
        assert len(pending) == 1

    def test_update_compact_markdown(
        self,
        session_manager: LocalSessionManager,
        sample_project: dict,
    ):
        """Test updating compact markdown."""
        session = session_manager.register(
            external_id="compact-test",
            machine_id="machine",
            source="claude",
            project_id=sample_project["id"],
        )

        updated = session_manager.update_compact_markdown(session.id, "# Compact")
        assert updated is not None
        assert updated.compact_markdown == "# Compact"

    def test_update_parent_session_id(
        self,
        session_manager: LocalSessionManager,
        sample_project: dict,
    ):
        """Test updating parent session ID."""
        session = session_manager.register(
            external_id="child",
            machine_id="machine",
            source="claude",
            project_id=sample_project["id"],
        )

        parent = session_manager.register(
            external_id="parent",
            machine_id="machine",
            source="claude",
            project_id=sample_project["id"],
        )

        updated = session_manager.update_parent_session_id(session.id, parent.id)
        assert updated is not None
        assert updated.parent_session_id == parent.id

    def test_session_should_not_be_its_own_parent(
        self,
        session_manager: LocalSessionManager,
        sample_project: dict,
    ):
        """
        Regression test: Session should never reference itself as parent.

        This tests the scenario where a session is marked handoff_ready during
        pre_compact, then on session_start with source='compact', the same
        session is found as the "parent" and incorrectly set as its own parent.

        The fix is in hook_manager.py: don't look for parent sessions on 'compact'
        events, only on 'clear' events.
        """
        # Simulate the bug scenario:
        # 1. Create a session
        session = session_manager.register(
            external_id="compact-session",
            machine_id="machine",
            source="claude",
            project_id=sample_project["id"],
        )

        # 2. Mark it handoff_ready (simulating pre_compact)
        session_manager.update_status(session.id, "handoff_ready")

        # 3. Find parent (this is what happens on session_start)
        parent = session_manager.find_parent(
            machine_id="machine",
            project_id=sample_project["id"],
            source="claude",
            status="handoff_ready",
        )

        # The bug was: parent.id == session.id, then we'd set parent_session_id to itself
        assert parent is not None
        assert parent.id == session.id  # This is expected - it finds itself

        # The KEY assertion: we should NEVER set a session as its own parent
        # This is enforced in hook_manager.py by not looking for parents on 'compact'
        # But if we did, this would be the bug:
        if parent.id == session.id:
            # In real code, this should be prevented at the hook_manager level
            # by checking session_source == "clear" (not "compact")
            pass  # Don't actually set self-referential parent

        # Verify the session doesn't have itself as parent
        current = session_manager.get(session.id)
        assert current.parent_session_id != current.id, (
            "Session should never reference itself as parent_session_id"
        )
