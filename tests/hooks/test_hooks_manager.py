"""Tests for the HookManager coordinator."""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gobby.hooks.events import HookEvent, HookEventType, HookResponse, SessionSource
from gobby.hooks.hook_manager import HookManager
from gobby.storage.database import LocalDatabase
from gobby.storage.migrations import run_migrations
from gobby.storage.projects import LocalProjectManager


@pytest.fixture
def mock_daemon_client():
    """Create a mock daemon client."""
    client = MagicMock()
    # Mock check_status to return (is_ready, message, status, error)
    client.check_status.return_value = (True, "Daemon ready", "ready", None)
    return client


@pytest.fixture
def hook_manager_with_mocks(temp_dir: Path, mock_daemon_client: MagicMock):
    """Create a HookManager with mocked dependencies."""
    # Create temp database
    db_path = temp_dir / "test.db"
    db = LocalDatabase(db_path)
    run_migrations(db)

    # Create a test project
    project_mgr = LocalProjectManager(db)
    project = project_mgr.create(name="test-project", repo_path=str(temp_dir))

    # Create project.json for auto-discovery
    gobby_dir = temp_dir / ".gobby"
    gobby_dir.mkdir()
    (gobby_dir / "project.json").write_text(f'{{"id": "{project.id}", "name": "test-project"}}')

    with patch("gobby.hooks.hook_manager.DaemonClient") as MockDaemonClient:
        MockDaemonClient.return_value = mock_daemon_client

        manager = HookManager(
            daemon_host="localhost",
            daemon_port=8765,
            log_file=str(temp_dir / "logs" / "hook-manager.log"),
        )

        # Pre-warm the daemon status cache
        manager._cached_daemon_is_ready = True
        manager._cached_daemon_status = "ready"

        yield manager

        # Cleanup: Remove test sessions from HookManager's database (uses production DB)
        # The HookManager creates its own LocalDatabase() connection to ~/.gobby/gobby.db
        test_external_ids = [
            "test-external-id-123",
            "test-resume-session-123",
            "test",
        ]
        try:
            manager._database.execute(
                f"DELETE FROM sessions WHERE external_id IN ({','.join('?' * len(test_external_ids))})",
                tuple(test_external_ids),
            )
        except Exception:
            pass  # Best effort cleanup

        manager.shutdown()
        db.close()


@pytest.fixture
def sample_session_start_event(temp_dir: Path) -> HookEvent:
    """Create a sample session start event."""
    return HookEvent(
        event_type=HookEventType.SESSION_START,
        session_id="test-external-id-123",
        source=SessionSource.CLAUDE,
        timestamp=datetime.utcnow(),
        data={
            "source": "startup",
            "cwd": str(temp_dir),
            "transcript_path": str(temp_dir / "transcript.jsonl"),
        },
        machine_id="test-machine-id",
    )


class TestHookManagerInit:
    """Tests for HookManager initialization."""

    def test_init_creates_subsystems(self, hook_manager_with_mocks: HookManager):
        """Test that initialization creates all subsystems."""
        manager = hook_manager_with_mocks

        assert manager._daemon_client is not None
        assert manager._transcript_processor is not None
        assert manager._session_manager is not None
        assert manager._summary_file_generator is not None
        assert manager._database is not None

    def test_init_sets_daemon_url(self, hook_manager_with_mocks: HookManager):
        """Test that daemon URL is set correctly."""
        manager = hook_manager_with_mocks
        assert manager.daemon_url == "http://localhost:8765"

    def test_init_creates_event_handlers(self, hook_manager_with_mocks: HookManager):
        """Test that event handlers are created."""
        manager = hook_manager_with_mocks
        handler_map = manager._event_handlers.get_handler_map()

        # Check key event types have handlers
        assert HookEventType.SESSION_START in handler_map
        assert HookEventType.SESSION_END in handler_map
        assert HookEventType.BEFORE_AGENT in handler_map
        assert HookEventType.AFTER_AGENT in handler_map
        assert HookEventType.BEFORE_TOOL in handler_map
        assert HookEventType.AFTER_TOOL in handler_map


class TestHookManagerHandle:
    """Tests for the handle() method."""

    def test_handle_returns_hook_response(
        self,
        hook_manager_with_mocks: HookManager,
        sample_session_start_event: HookEvent,
    ):
        """Test that handle returns a HookResponse."""
        response = hook_manager_with_mocks.handle(sample_session_start_event)

        assert isinstance(response, HookResponse)
        assert response.decision == "allow"

    def test_handle_daemon_not_ready(
        self,
        hook_manager_with_mocks: HookManager,
        sample_session_start_event: HookEvent,
    ):
        """Test handling when daemon is not ready."""
        from unittest.mock import patch

        manager = hook_manager_with_mocks

        # Simulate daemon not ready by mocking HealthMonitor's get_cached_status
        with patch.object(
            manager._health_monitor,
            "get_cached_status",
            return_value=(False, None, "not_running", "Connection refused"),
        ):
            response = manager.handle(sample_session_start_event)

        # Should fail open
        assert response.decision == "allow"
        assert response.reason is not None
        assert "not_running" in response.reason

    def test_handle_unknown_event_type(self, hook_manager_with_mocks: HookManager):
        """Test handling unknown event type fails open."""
        from unittest.mock import patch

        manager = hook_manager_with_mocks

        event = HookEvent(
            event_type=HookEventType.NOTIFICATION,
            session_id="test",
            source=SessionSource.CLAUDE,
            timestamp=datetime.utcnow(),
            data={},
        )

        # Mock the event handlers to return None for any event type
        with patch.object(manager._event_handlers, "get_handler", return_value=None):
            response = manager.handle(event)

        # Should fail open
        assert response.decision == "allow"


class TestHookManagerSessionStart:
    """Tests for session start handling."""

    def test_session_start_registers_session(
        self,
        hook_manager_with_mocks: HookManager,
        sample_session_start_event: HookEvent,
    ):
        """Test that session start registers a new session."""
        response = hook_manager_with_mocks.handle(sample_session_start_event)

        assert response.decision == "allow"
        assert response.metadata.get("session_id") is not None
        assert response.metadata.get("external_id") == "test-external-id-123"

    def test_session_start_returns_response(
        self,
        hook_manager_with_mocks: HookManager,
        sample_session_start_event: HookEvent,
    ):
        """Test that session start returns a valid response with system_message."""
        response = hook_manager_with_mocks.handle(sample_session_start_event)

        assert response.decision == "allow"
        # Response should include session ID in system_message
        assert response.system_message is not None
        assert "Session ID:" in response.system_message

    def test_session_resume_no_handoff_message(
        self,
        hook_manager_with_mocks: HookManager,
        temp_dir: Path,
    ):
        """Test that resume source doesn't show 'Context restored' system_message.

        Parent session finding only happens on source='clear' (handoff scenario).
        On resume we get basic session info only, no parent context.
        """
        # Create a resume event (source="resume" means continuing same session)
        resume_event = HookEvent(
            event_type=HookEventType.SESSION_START,
            session_id="test-resume-session-123",
            source=SessionSource.CLAUDE,
            timestamp=datetime.utcnow(),
            data={
                "source": "resume",  # Key: this is a resume, not startup
                "cwd": str(temp_dir),
                "transcript_path": str(temp_dir / "transcript.jsonl"),
            },
            machine_id="test-machine-id",
        )

        response = hook_manager_with_mocks.handle(resume_event)

        # Should be allowed
        assert response.decision == "allow"

        # Should have basic session info but NOT "Context restored" message
        # Parent finding only runs on source='clear'
        assert response.system_message is not None
        assert "Session ID:" in response.system_message
        assert "Context restored" not in (response.system_message or "")


class TestHookManagerSessionEnd:
    """Tests for session end handling."""

    def test_session_end_allows(
        self,
        hook_manager_with_mocks: HookManager,
        sample_session_start_event: HookEvent,
        temp_dir: Path,
    ):
        """Test that session end is allowed."""
        # First start a session
        hook_manager_with_mocks.handle(sample_session_start_event)

        # Create transcript file in temp directory
        transcript_path = temp_dir / "transcript.jsonl"
        transcript_path.touch()

        # Then end it
        end_event = HookEvent(
            event_type=HookEventType.SESSION_END,
            session_id="test-external-id-123",
            source=SessionSource.CLAUDE,
            timestamp=datetime.utcnow(),
            data={"transcript_path": str(transcript_path)},
            machine_id="test-machine-id",
        )

        response = hook_manager_with_mocks.handle(end_event)
        assert response.decision == "allow"

    @pytest.mark.integration
    def test_session_end_auto_links_commits(
        self,
        hook_manager_with_mocks: HookManager,
        temp_dir: Path,
    ):
        """Test that session end auto-links commits made during session."""
        from gobby.storage.sessions import Session
        from gobby.tasks.commits import AutoLinkResult

        # Create transcript file in temp directory
        transcript_path = temp_dir / "transcript.jsonl"
        transcript_path.touch()

        # Mock session storage to return a session with created_at
        mock_session = Session(
            id="test-session-id",
            external_id="test-external-id-123",
            machine_id="test-machine-id",
            source="claude",
            project_id="test-project-id",
            title="Test Session",
            status="active",
            jsonl_path=None,
            summary_path=None,
            summary_markdown=None,
            compact_markdown=None,
            git_branch=None,
            parent_session_id=None,
            created_at="2026-01-04T00:00:00+00:00",
            updated_at="2026-01-04T00:00:00+00:00",
        )

        # Mock auto_link_commits to verify it's called
        mock_result = AutoLinkResult(
            linked_tasks={"gt-123abc": ["abc1234", "def5678"]},
            total_linked=2,
            skipped=1,
        )

        with (
            patch.object(
                hook_manager_with_mocks._session_storage, "get", return_value=mock_session
            ),
            patch(
                "gobby.tasks.commits.auto_link_commits", return_value=mock_result
            ) as mock_auto_link,
        ):
            end_event = HookEvent(
                event_type=HookEventType.SESSION_END,
                session_id="test-external-id-123",
                source=SessionSource.CLAUDE,
                timestamp=datetime.utcnow(),
                data={"transcript_path": str(transcript_path), "cwd": str(temp_dir)},
                machine_id="test-machine-id",
                metadata={"_platform_session_id": "test-session-id"},
            )

            response = hook_manager_with_mocks.handle(end_event)

            assert response.decision == "allow"

            # Verify auto_link_commits was called
            mock_auto_link.assert_called_once()
            call_kwargs = mock_auto_link.call_args.kwargs
            assert "task_manager" in call_kwargs
            assert call_kwargs["since"] == "2026-01-04T00:00:00+00:00"
            assert call_kwargs["cwd"] == str(temp_dir)


class TestHookManagerBeforeAgent:
    """Tests for before agent (user prompt submit) handling."""

    def test_before_agent_allows(
        self,
        hook_manager_with_mocks: HookManager,
        sample_session_start_event: HookEvent,
    ):
        """Test that before agent is allowed."""
        # Start session first
        hook_manager_with_mocks.handle(sample_session_start_event)

        event = HookEvent(
            event_type=HookEventType.BEFORE_AGENT,
            session_id="test-external-id-123",
            source=SessionSource.CLAUDE,
            timestamp=datetime.utcnow(),
            data={"prompt": "Help me write a function"},
            machine_id="test-machine-id",
        )

        response = hook_manager_with_mocks.handle(event)
        assert response.decision == "allow"


class TestHookManagerToolEvents:
    """Tests for tool event handling."""

    def test_before_tool_allows(
        self,
        hook_manager_with_mocks: HookManager,
        sample_session_start_event: HookEvent,
    ):
        """Test that before tool use is allowed."""
        hook_manager_with_mocks.handle(sample_session_start_event)

        event = HookEvent(
            event_type=HookEventType.BEFORE_TOOL,
            session_id="test-external-id-123",
            source=SessionSource.CLAUDE,
            timestamp=datetime.utcnow(),
            data={"tool_name": "bash", "tool_input": {"command": "ls"}},
            machine_id="test-machine-id",
        )

        response = hook_manager_with_mocks.handle(event)
        assert response.decision == "allow"

    def test_after_tool_allows(
        self,
        hook_manager_with_mocks: HookManager,
        sample_session_start_event: HookEvent,
    ):
        """Test that after tool use is allowed."""
        hook_manager_with_mocks.handle(sample_session_start_event)

        event = HookEvent(
            event_type=HookEventType.AFTER_TOOL,
            session_id="test-external-id-123",
            source=SessionSource.CLAUDE,
            timestamp=datetime.utcnow(),
            data={"tool_name": "bash", "tool_output": "file1.txt\nfile2.txt"},
            machine_id="test-machine-id",
        )

        response = hook_manager_with_mocks.handle(event)
        assert response.decision == "allow"


class TestHookManagerShutdown:
    """Tests for HookManager shutdown."""

    def test_shutdown_stops_health_check(self, hook_manager_with_mocks: HookManager):
        """Test that shutdown stops health check monitoring."""
        manager = hook_manager_with_mocks

        # Should have a health monitor with timer running or already shutdown
        assert (
            manager._health_monitor._health_check_timer is not None
            or manager._health_monitor._is_shutdown
        )

        manager.shutdown()

        # Should be marked as shutdown in the health monitor
        assert manager._health_monitor._is_shutdown is True


class TestHookManagerGetEventHandler:
    """Tests for event handler lookup."""

    def test_get_handler_for_known_event(self, hook_manager_with_mocks: HookManager):
        """Test getting handler for known event type."""
        handler = hook_manager_with_mocks._get_event_handler(HookEventType.SESSION_START)
        assert handler is not None
        assert callable(handler)

    def test_get_handler_for_all_event_types(self, hook_manager_with_mocks: HookManager):
        """Test that all event types in map have handlers."""
        handler_map = hook_manager_with_mocks._event_handlers.get_handler_map()
        for event_type in handler_map:
            handler = hook_manager_with_mocks._get_event_handler(event_type)
            assert handler is not None


class TestHookManagerMachineId:
    """Tests for machine ID functionality."""

    def test_get_machine_id(self, hook_manager_with_mocks: HookManager):
        """Test getting machine ID returns a string."""
        result = hook_manager_with_mocks.get_machine_id()
        # Should return a string (either from cache, config, or generated)
        assert result is None or isinstance(result, str)


class TestHookManagerCachedDaemonStatus:
    """Tests for cached daemon status."""

    def test_get_cached_daemon_status(self, hook_manager_with_mocks: HookManager):
        """Test getting cached daemon status."""
        manager = hook_manager_with_mocks

        # Set cached values on the health monitor (delegation target)
        manager._health_monitor._cached_daemon_is_ready = True
        manager._health_monitor._cached_daemon_message = "Ready"
        manager._health_monitor._cached_daemon_status = "healthy"
        manager._health_monitor._cached_daemon_error = None

        is_ready, message, status, error = manager._get_cached_daemon_status()

        assert is_ready is True
        assert message == "Ready"
        assert status == "healthy"
        assert error is None
