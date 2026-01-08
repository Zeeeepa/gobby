"""
Tests for EventHandlers module (TDD green phase).

Test categories:
1. Handler registration and lookup
2. Individual event type handlers (15 total)
3. Handler execution order
4. Error isolation
5. Context passing
6. Return value handling
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest

from gobby.hooks.event_handlers import EventHandlers
from gobby.hooks.events import HookEvent, HookEventType, HookResponse, SessionSource

if TYPE_CHECKING:
    pass


def make_event(
    event_type: HookEventType,
    session_id: str = "test-session",
    source: str = "claude",
    data: dict | None = None,
    metadata: dict | None = None,
) -> HookEvent:
    """Helper to create HookEvent with required fields."""
    return HookEvent(
        event_type=event_type,
        session_id=session_id,
        source=SessionSource(source),
        timestamp=datetime.now(UTC),
        data=data or {},
        metadata=metadata or {},
    )


@pytest.fixture
def mock_dependencies() -> dict[str, Any]:
    """Create mock dependencies for EventHandlers."""
    # Configure workflow_handler to return a proper HookResponse
    workflow_handler = MagicMock()
    workflow_handler.handle_all_lifecycles.return_value = HookResponse(decision="allow", context="")
    return {
        "session_manager": MagicMock(),
        "workflow_handler": workflow_handler,
        "session_storage": MagicMock(),
        "message_processor": MagicMock(),
        "summary_file_generator": MagicMock(),
        "task_manager": MagicMock(),
        "session_coordinator": MagicMock(),
        "logger": logging.getLogger("test"),
    }


@pytest.fixture
def event_handlers(mock_dependencies: dict[str, Any]) -> EventHandlers:
    """Create EventHandlers instance with mocks."""
    return EventHandlers(**mock_dependencies)


class TestHandlerRegistration:
    """Test handler registration and lookup."""

    def test_all_event_types_have_handlers(self, event_handlers: EventHandlers) -> None:
        """Test that all HookEventType values have registered handlers."""
        for event_type in HookEventType:
            handler = event_handlers.get_handler(event_type)
            assert handler is not None, f"No handler for {event_type}"
            assert callable(handler)

    def test_get_handler_returns_callable(self, event_handlers: EventHandlers) -> None:
        """Test get_handler returns a callable."""
        handler = event_handlers.get_handler(HookEventType.SESSION_START)
        assert callable(handler)

    def test_get_handler_for_unknown_returns_none(self, event_handlers: EventHandlers) -> None:
        """Test get_handler returns None for unknown event type."""
        result = event_handlers.get_handler("invalid_event")  # type: ignore
        assert result is None

    def test_handler_map_is_immutable(self, event_handlers: EventHandlers) -> None:
        """Test handler map cannot be modified externally."""
        handler_map = event_handlers.get_handler_map()
        original_count = len(handler_map)
        handler_map["fake"] = lambda x: x
        assert len(event_handlers.get_handler_map()) == original_count


class TestSessionHandlers:
    """Test SESSION_START and SESSION_END handlers."""

    def test_session_start_allows(
        self, event_handlers: EventHandlers, mock_dependencies: dict
    ) -> None:
        """Test SESSION_START handler allows by default."""
        event = make_event(HookEventType.SESSION_START, session_id="ext-123")
        response = event_handlers.handle_session_start(event)
        assert response.decision == "allow"

    def test_session_end_allows(self, event_handlers: EventHandlers) -> None:
        """Test SESSION_END handler allows by default."""
        event = make_event(
            HookEventType.SESSION_END,
            metadata={"_platform_session_id": "plat-123"},
        )
        response = event_handlers.handle_session_end(event)
        assert response.decision == "allow"


class TestAgentHandlers:
    """Test BEFORE_AGENT and AFTER_AGENT handlers."""

    def test_before_agent_allows(self, event_handlers: EventHandlers) -> None:
        """Test BEFORE_AGENT allows by default."""
        event = make_event(
            HookEventType.BEFORE_AGENT,
            data={"prompt": "Hello"},
            metadata={"_platform_session_id": "plat-123"},
        )
        response = event_handlers.handle_before_agent(event)
        assert response.decision == "allow"

    def test_after_agent_allows(self, event_handlers: EventHandlers) -> None:
        """Test AFTER_AGENT allows by default."""
        event = make_event(
            HookEventType.AFTER_AGENT,
            metadata={"_platform_session_id": "plat-123"},
        )
        response = event_handlers.handle_after_agent(event)
        assert response.decision == "allow"


class TestToolHandlers:
    """Test BEFORE_TOOL and AFTER_TOOL handlers."""

    def test_before_tool_allows(self, event_handlers: EventHandlers) -> None:
        """Test BEFORE_TOOL allows by default."""
        event = make_event(
            HookEventType.BEFORE_TOOL,
            data={"tool_name": "Read"},
            metadata={"_platform_session_id": "plat-123"},
        )
        response = event_handlers.handle_before_tool(event)
        assert response.decision == "allow"

    def test_after_tool_allows(self, event_handlers: EventHandlers) -> None:
        """Test AFTER_TOOL allows by default."""
        event = make_event(
            HookEventType.AFTER_TOOL,
            data={"tool_name": "Read"},
            metadata={"_platform_session_id": "plat-123"},
        )
        response = event_handlers.handle_after_tool(event)
        assert response.decision == "allow"


class TestOtherHandlers:
    """Test remaining event handlers."""

    def test_stop_allows(self, event_handlers: EventHandlers) -> None:
        """Test STOP allows by default."""
        event = make_event(HookEventType.STOP)
        response = event_handlers.handle_stop(event)
        assert response.decision == "allow"

    def test_pre_compact_allows(self, event_handlers: EventHandlers) -> None:
        """Test PRE_COMPACT allows by default."""
        event = make_event(HookEventType.PRE_COMPACT)
        response = event_handlers.handle_pre_compact(event)
        assert response.decision == "allow"

    def test_subagent_start_allows(self, event_handlers: EventHandlers) -> None:
        """Test SUBAGENT_START allows by default."""
        event = make_event(HookEventType.SUBAGENT_START, data={"subagent_id": "sub-1"})
        response = event_handlers.handle_subagent_start(event)
        assert response.decision == "allow"

    def test_subagent_stop_allows(self, event_handlers: EventHandlers) -> None:
        """Test SUBAGENT_STOP allows by default."""
        event = make_event(HookEventType.SUBAGENT_STOP, data={"subagent_id": "sub-1"})
        response = event_handlers.handle_subagent_stop(event)
        assert response.decision == "allow"

    def test_notification_allows(self, event_handlers: EventHandlers) -> None:
        """Test NOTIFICATION allows by default."""
        event = make_event(HookEventType.NOTIFICATION, data={"message": "test"})
        response = event_handlers.handle_notification(event)
        assert response.decision == "allow"

    def test_permission_request_allows(self, event_handlers: EventHandlers) -> None:
        """Test PERMISSION_REQUEST allows by default."""
        event = make_event(HookEventType.PERMISSION_REQUEST, data={"permission": "write"})
        response = event_handlers.handle_permission_request(event)
        assert response.decision == "allow"


class TestGeminiOnlyHandlers:
    """Test Gemini-only event handlers."""

    def test_before_tool_selection_allows(self, event_handlers: EventHandlers) -> None:
        """Test BEFORE_TOOL_SELECTION allows (Gemini only)."""
        event = make_event(HookEventType.BEFORE_TOOL_SELECTION, source="gemini")
        response = event_handlers.handle_before_tool_selection(event)
        assert response.decision == "allow"

    def test_before_model_allows(self, event_handlers: EventHandlers) -> None:
        """Test BEFORE_MODEL allows (Gemini only)."""
        event = make_event(HookEventType.BEFORE_MODEL, source="gemini")
        response = event_handlers.handle_before_model(event)
        assert response.decision == "allow"

    def test_after_model_allows(self, event_handlers: EventHandlers) -> None:
        """Test AFTER_MODEL allows (Gemini only)."""
        event = make_event(HookEventType.AFTER_MODEL, source="gemini")
        response = event_handlers.handle_after_model(event)
        assert response.decision == "allow"


class TestErrorIsolation:
    """Test handler error isolation."""

    def test_workflow_error_handled(
        self, event_handlers: EventHandlers, mock_dependencies: dict
    ) -> None:
        """Test workflow errors are handled gracefully."""
        mock_dependencies["workflow_handler"].handle_all_lifecycles.side_effect = Exception(
            "Workflow error"
        )
        event = make_event(HookEventType.BEFORE_AGENT, data={"prompt": "Hello"})
        response = event_handlers.handle_before_agent(event)
        assert response.decision in ("allow", "block")

    def test_missing_metadata_handled(self, event_handlers: EventHandlers) -> None:
        """Test missing metadata is handled gracefully."""
        event = make_event(HookEventType.BEFORE_TOOL, data={"tool_name": "Read"})
        response = event_handlers.handle_before_tool(event)
        assert response.decision in ("allow", "block")


class TestReturnValues:
    """Test handler return values."""

    def test_returns_hook_response(self, event_handlers: EventHandlers) -> None:
        """Test handlers return HookResponse."""
        event = make_event(HookEventType.BEFORE_AGENT, data={"prompt": "Hello"})
        response = event_handlers.handle_before_agent(event)
        assert isinstance(response, HookResponse)
        assert hasattr(response, "decision")
        assert hasattr(response, "context")

    def test_context_is_string(self, event_handlers: EventHandlers) -> None:
        """Test context is always a string."""
        event = make_event(HookEventType.SESSION_START)
        response = event_handlers.handle_session_start(event)
        assert isinstance(response.context, str)


class TestEventHandlersInit:
    """Test EventHandlers initialization."""

    def test_init_creates_logger(self) -> None:
        """Test init creates logger if not provided."""
        handlers = EventHandlers()
        assert handlers.logger is not None

    def test_init_with_dependencies(self, mock_dependencies: dict) -> None:
        """Test init with dependencies."""
        handlers = EventHandlers(**mock_dependencies)
        assert handlers._session_manager is mock_dependencies["session_manager"]

    def test_init_default_get_machine_id(self) -> None:
        """Test default get_machine_id function returns unknown-machine."""
        handlers = EventHandlers()
        assert handlers._get_machine_id() == "unknown-machine"

    def test_init_default_resolve_project_id(self) -> None:
        """Test default resolve_project_id function returns project_id or empty string."""
        handlers = EventHandlers()
        assert handlers._resolve_project_id("proj-123", None) == "proj-123"
        assert handlers._resolve_project_id(None, "/some/path") == ""

    def test_init_custom_get_machine_id(self) -> None:
        """Test custom get_machine_id function is used."""
        handlers = EventHandlers(get_machine_id=lambda: "custom-machine")
        assert handlers._get_machine_id() == "custom-machine"

    def test_init_custom_resolve_project_id(self) -> None:
        """Test custom resolve_project_id function is used."""
        handlers = EventHandlers(resolve_project_id=lambda p, c: f"resolved-{p or 'none'}")
        assert handlers._resolve_project_id("proj-1", None) == "resolved-proj-1"


class TestSessionStartPreCreatedSession:
    """Test SESSION_START handling for pre-created sessions (terminal mode agents)."""

    def test_pre_created_session_found_and_updated(self, mock_dependencies: dict) -> None:
        """Test pre-created session is found and updated."""
        # Create a mock session object
        mock_session = MagicMock()
        mock_session.id = "sess-pre-123"
        mock_session.project_id = "proj-123"
        mock_session.parent_session_id = None
        mock_session.agent_depth = 0
        mock_session.agent_run_id = None

        # Configure session_storage.get to return the session
        mock_dependencies["session_storage"].get.return_value = mock_session

        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.SESSION_START,
            session_id="sess-pre-123",
            data={"transcript_path": "/path/to/transcript.jsonl", "cwd": "/some/dir"},
        )

        response = handlers.handle_session_start(event)

        assert response.decision == "allow"
        assert response.metadata.get("is_pre_created") is True
        assert response.metadata.get("session_id") == "sess-pre-123"
        mock_dependencies["session_storage"].update.assert_called_once()

    def test_pre_created_session_with_parent(self, mock_dependencies: dict) -> None:
        """Test pre-created session with parent session ID includes parent context."""
        mock_session = MagicMock()
        mock_session.id = "sess-child-123"
        mock_session.project_id = "proj-123"
        mock_session.parent_session_id = "sess-parent-456"
        mock_session.agent_depth = 1
        mock_session.agent_run_id = None

        mock_dependencies["session_storage"].get.return_value = mock_session

        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.SESSION_START,
            session_id="sess-child-123",
            data={"transcript_path": "/path/to/transcript.jsonl"},
        )

        response = handlers.handle_session_start(event)

        assert response.decision == "allow"
        assert "Parent ID: sess-parent-456" in response.system_message
        assert "Agent depth: 1" in response.system_message

    def test_pre_created_session_with_agent_run_id(self, mock_dependencies: dict) -> None:
        """Test pre-created session with agent_run_id starts the agent run."""
        mock_session = MagicMock()
        mock_session.id = "sess-agent-123"
        mock_session.project_id = "proj-123"
        mock_session.parent_session_id = None
        mock_session.agent_depth = 0
        mock_session.agent_run_id = "run-456"

        mock_dependencies["session_storage"].get.return_value = mock_session

        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.SESSION_START,
            session_id="sess-agent-123",
            data={"transcript_path": "/path/to/transcript.jsonl"},
        )

        response = handlers.handle_session_start(event)

        assert response.decision == "allow"
        mock_dependencies["session_coordinator"].start_agent_run.assert_called_once_with("run-456")

    def test_pre_created_session_agent_run_start_error(self, mock_dependencies: dict) -> None:
        """Test error starting agent run is handled gracefully."""
        mock_session = MagicMock()
        mock_session.id = "sess-agent-123"
        mock_session.project_id = "proj-123"
        mock_session.parent_session_id = None
        mock_session.agent_depth = 0
        mock_session.agent_run_id = "run-456"

        mock_dependencies["session_storage"].get.return_value = mock_session
        mock_dependencies["session_coordinator"].start_agent_run.side_effect = Exception(
            "Failed to start"
        )

        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.SESSION_START,
            session_id="sess-agent-123",
            data={"transcript_path": "/path/to/transcript.jsonl"},
        )

        response = handlers.handle_session_start(event)

        # Should still allow despite error
        assert response.decision == "allow"

    def test_pre_created_session_registers_with_message_processor(
        self, mock_dependencies: dict
    ) -> None:
        """Test pre-created session registers with message processor."""
        mock_session = MagicMock()
        mock_session.id = "sess-123"
        mock_session.project_id = "proj-123"
        mock_session.parent_session_id = None
        mock_session.agent_depth = 0
        mock_session.agent_run_id = None

        mock_dependencies["session_storage"].get.return_value = mock_session

        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.SESSION_START,
            session_id="sess-123",
            data={"transcript_path": "/path/to/transcript.jsonl"},
        )

        handlers.handle_session_start(event)

        mock_dependencies["message_processor"].register_session.assert_called_once_with(
            "sess-123", "/path/to/transcript.jsonl", source="claude"
        )

    def test_pre_created_session_message_processor_error(self, mock_dependencies: dict) -> None:
        """Test error registering with message processor is handled gracefully."""
        mock_session = MagicMock()
        mock_session.id = "sess-123"
        mock_session.project_id = "proj-123"
        mock_session.parent_session_id = None
        mock_session.agent_depth = 0
        mock_session.agent_run_id = None

        mock_dependencies["session_storage"].get.return_value = mock_session
        mock_dependencies["message_processor"].register_session.side_effect = Exception(
            "Registration failed"
        )

        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.SESSION_START,
            session_id="sess-123",
            data={"transcript_path": "/path/to/transcript.jsonl"},
        )

        response = handlers.handle_session_start(event)

        # Should still allow despite error
        assert response.decision == "allow"

    def test_pre_created_session_workflow_context(self, mock_dependencies: dict) -> None:
        """Test pre-created session merges workflow context."""
        mock_session = MagicMock()
        mock_session.id = "sess-123"
        mock_session.project_id = "proj-123"
        mock_session.parent_session_id = None
        mock_session.agent_depth = 0
        mock_session.agent_run_id = None

        mock_dependencies["session_storage"].get.return_value = mock_session
        mock_dependencies["workflow_handler"].handle_all_lifecycles.return_value = HookResponse(
            decision="allow",
            context="Workflow context here",
            system_message="Workflow system message",
        )

        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.SESSION_START,
            session_id="sess-123",
            data={"transcript_path": "/path/to/transcript.jsonl"},
        )

        response = handlers.handle_session_start(event)

        assert "Workflow context here" in response.context
        assert "Workflow system message" in response.system_message

    def test_pre_created_session_workflow_error(self, mock_dependencies: dict) -> None:
        """Test error in workflow handler is handled gracefully."""
        mock_session = MagicMock()
        mock_session.id = "sess-123"
        mock_session.project_id = "proj-123"
        mock_session.parent_session_id = None
        mock_session.agent_depth = 0
        mock_session.agent_run_id = None

        mock_dependencies["session_storage"].get.return_value = mock_session
        mock_dependencies["workflow_handler"].handle_all_lifecycles.side_effect = Exception(
            "Workflow error"
        )

        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.SESSION_START,
            session_id="sess-123",
            data={"transcript_path": "/path/to/transcript.jsonl"},
        )

        response = handlers.handle_session_start(event)

        # Should still allow despite error
        assert response.decision == "allow"

    def test_pre_created_session_coordinator_error(self, mock_dependencies: dict) -> None:
        """Test error registering session with coordinator is handled."""
        mock_session = MagicMock()
        mock_session.id = "sess-123"
        mock_session.project_id = "proj-123"
        mock_session.parent_session_id = None
        mock_session.agent_depth = 0
        mock_session.agent_run_id = None

        mock_dependencies["session_storage"].get.return_value = mock_session
        mock_dependencies["session_coordinator"].register_session.side_effect = Exception(
            "Coordinator error"
        )

        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.SESSION_START,
            session_id="sess-123",
            data={"transcript_path": "/path/to/transcript.jsonl"},
        )

        response = handlers.handle_session_start(event)

        # Should still allow despite error
        assert response.decision == "allow"


class TestSessionStartNewSession:
    """Test SESSION_START handling for new sessions."""

    def test_new_session_with_parent_on_handoff(self, mock_dependencies: dict) -> None:
        """Test new session finds parent when source is 'clear'."""
        mock_parent = MagicMock()
        mock_parent.id = "parent-sess-123"

        # No pre-created session found
        mock_dependencies["session_storage"].get.return_value = None
        mock_dependencies["session_storage"].find_parent.return_value = mock_parent
        mock_dependencies["session_manager"].register_session.return_value = "new-sess-456"

        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.SESSION_START,
            session_id="ext-123",
            data={"source": "clear", "cwd": "/some/dir"},
            metadata={},
        )
        event.machine_id = "machine-123"

        response = handlers.handle_session_start(event)

        assert response.decision == "allow"
        assert "Parent session: parent-sess-123" in response.context
        mock_dependencies["session_storage"].find_parent.assert_called_once()
        mock_dependencies["session_manager"].mark_session_expired.assert_called_once_with(
            "parent-sess-123"
        )

    def test_new_session_parent_lookup_error(self, mock_dependencies: dict) -> None:
        """Test error looking up parent session is handled gracefully."""
        mock_dependencies["session_storage"].get.return_value = None
        mock_dependencies["session_storage"].find_parent.side_effect = Exception("Lookup error")
        mock_dependencies["session_manager"].register_session.return_value = "new-sess-456"

        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.SESSION_START,
            session_id="ext-123",
            data={"source": "clear", "cwd": "/some/dir"},
        )

        response = handlers.handle_session_start(event)

        # Should still allow despite error
        assert response.decision == "allow"

    def test_new_session_mark_parent_expired_error(self, mock_dependencies: dict) -> None:
        """Test error marking parent as expired is handled gracefully."""
        mock_parent = MagicMock()
        mock_parent.id = "parent-sess-123"

        mock_dependencies["session_storage"].get.return_value = None
        mock_dependencies["session_storage"].find_parent.return_value = mock_parent
        mock_dependencies["session_manager"].register_session.return_value = "new-sess-456"
        mock_dependencies["session_manager"].mark_session_expired.side_effect = Exception(
            "Failed to expire"
        )

        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.SESSION_START,
            session_id="ext-123",
            data={"source": "clear"},
        )

        response = handlers.handle_session_start(event)

        # Should still allow despite error
        assert response.decision == "allow"

    def test_new_session_coordinator_registration_error(self, mock_dependencies: dict) -> None:
        """Test error registering session with coordinator is handled."""
        mock_dependencies["session_storage"].get.return_value = None
        mock_dependencies["session_manager"].register_session.return_value = "new-sess-456"
        mock_dependencies["session_coordinator"].register_session.side_effect = Exception(
            "Coordinator error"
        )

        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.SESSION_START,
            session_id="ext-123",
            data={"transcript_path": "/path/to/transcript.jsonl"},
        )

        response = handlers.handle_session_start(event)

        # Should still allow despite error
        assert response.decision == "allow"

    def test_new_session_message_processor_registration(self, mock_dependencies: dict) -> None:
        """Test new session registers with message processor."""
        mock_dependencies["session_storage"].get.return_value = None
        mock_dependencies["session_manager"].register_session.return_value = "new-sess-456"

        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.SESSION_START,
            session_id="ext-123",
            data={"transcript_path": "/path/to/transcript.jsonl"},
        )

        handlers.handle_session_start(event)

        mock_dependencies["message_processor"].register_session.assert_called_once_with(
            "new-sess-456", "/path/to/transcript.jsonl", source="claude"
        )

    def test_new_session_message_processor_error(self, mock_dependencies: dict) -> None:
        """Test error registering with message processor is handled."""
        mock_dependencies["session_storage"].get.return_value = None
        mock_dependencies["session_manager"].register_session.return_value = "new-sess-456"
        mock_dependencies["message_processor"].register_session.side_effect = Exception(
            "Registration failed"
        )

        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.SESSION_START,
            session_id="ext-123",
            data={"transcript_path": "/path/to/transcript.jsonl"},
        )

        response = handlers.handle_session_start(event)

        # Should still allow despite error
        assert response.decision == "allow"

    def test_new_session_workflow_context(self, mock_dependencies: dict) -> None:
        """Test new session merges workflow context."""
        mock_dependencies["session_storage"].get.return_value = None
        mock_dependencies["session_manager"].register_session.return_value = "new-sess-456"
        mock_dependencies["workflow_handler"].handle_all_lifecycles.return_value = HookResponse(
            decision="allow",
            context="Workflow context",
            system_message="System message",
        )

        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.SESSION_START,
            session_id="ext-123",
            data={},
        )

        response = handlers.handle_session_start(event)

        assert "Workflow context" in response.context
        assert "System message" in response.system_message

    def test_new_session_workflow_error(self, mock_dependencies: dict) -> None:
        """Test workflow error during new session is handled."""
        mock_dependencies["session_storage"].get.return_value = None
        mock_dependencies["session_manager"].register_session.return_value = "new-sess-456"
        mock_dependencies["workflow_handler"].handle_all_lifecycles.side_effect = Exception(
            "Workflow error"
        )

        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.SESSION_START,
            session_id="ext-123",
            data={},
        )

        response = handlers.handle_session_start(event)

        # Should still allow despite error
        assert response.decision == "allow"

    def test_new_session_with_task_id_context(self, mock_dependencies: dict) -> None:
        """Test new session includes task context when task_id present."""
        mock_dependencies["session_storage"].get.return_value = None
        mock_dependencies["session_manager"].register_session.return_value = "new-sess-456"

        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.SESSION_START,
            session_id="ext-123",
            data={},
        )
        event.task_id = "task-789"
        event.metadata["_task_title"] = "Implement feature X"

        response = handlers.handle_session_start(event)

        assert "Active Task Context" in response.context
        assert "task-789" in response.context
        assert "Implement feature X" in response.context


class TestSessionEndHandling:
    """Test SESSION_END handler edge cases and error paths."""

    def test_session_end_lookup_from_database(self, mock_dependencies: dict) -> None:
        """Test session_id lookup from database when not in metadata."""
        mock_dependencies["session_manager"].lookup_session_id.return_value = "found-sess-123"

        # Mock session for auto-link
        mock_session = MagicMock()
        mock_session.created_at = "2024-01-01T00:00:00Z"
        mock_session.agent_run_id = None
        mock_dependencies["session_storage"].get.return_value = mock_session

        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.SESSION_END,
            session_id="ext-123",
            metadata={},  # No _platform_session_id
        )
        event.machine_id = "machine-123"

        response = handlers.handle_session_end(event)

        assert response.decision == "allow"
        mock_dependencies["session_manager"].lookup_session_id.assert_called_once()

    def test_session_end_workflow_error(self, mock_dependencies: dict) -> None:
        """Test workflow error during session end is handled."""
        mock_dependencies["workflow_handler"].handle_all_lifecycles.side_effect = Exception(
            "Workflow error"
        )

        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.SESSION_END,
            metadata={"_platform_session_id": "sess-123"},
        )

        response = handlers.handle_session_end(event)

        # Should still allow despite error
        assert response.decision == "allow"

    def test_session_end_auto_link_commits(self, mock_dependencies: dict) -> None:
        """Test auto-linking commits on session end."""
        from unittest.mock import patch

        mock_session = MagicMock()
        mock_session.created_at = "2024-01-01T00:00:00Z"
        mock_session.agent_run_id = None
        mock_dependencies["session_storage"].get.return_value = mock_session

        mock_link_result = MagicMock()
        mock_link_result.total_linked = 2
        mock_link_result.linked_tasks = {"task-1": ["abc123"], "task-2": ["def456"]}

        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.SESSION_END,
            metadata={"_platform_session_id": "sess-123"},
            data={"cwd": "/some/dir"},
        )

        with patch("gobby.tasks.commits.auto_link_commits", return_value=mock_link_result):
            response = handlers.handle_session_end(event)

        assert response.decision == "allow"

    def test_session_end_auto_link_error(self, mock_dependencies: dict) -> None:
        """Test error auto-linking commits is handled gracefully."""
        from unittest.mock import patch

        mock_session = MagicMock()
        mock_session.created_at = "2024-01-01T00:00:00Z"
        mock_session.agent_run_id = None
        mock_dependencies["session_storage"].get.return_value = mock_session

        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.SESSION_END,
            metadata={"_platform_session_id": "sess-123"},
            data={"cwd": "/some/dir"},
        )

        with patch(
            "gobby.tasks.commits.auto_link_commits",
            side_effect=Exception("Link error"),
        ):
            response = handlers.handle_session_end(event)

        # Should still allow despite error
        assert response.decision == "allow"

    def test_session_end_complete_agent_run(self, mock_dependencies: dict) -> None:
        """Test completing agent run on session end."""
        mock_session = MagicMock()
        mock_session.created_at = "2024-01-01T00:00:00Z"
        mock_session.agent_run_id = "run-456"
        mock_dependencies["session_storage"].get.return_value = mock_session

        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.SESSION_END,
            metadata={"_platform_session_id": "sess-123"},
        )

        handlers.handle_session_end(event)

        mock_dependencies["session_coordinator"].complete_agent_run.assert_called_once()

    def test_session_end_complete_agent_run_error(self, mock_dependencies: dict) -> None:
        """Test error completing agent run is handled gracefully."""
        mock_session = MagicMock()
        mock_session.created_at = "2024-01-01T00:00:00Z"
        mock_session.agent_run_id = "run-456"
        mock_dependencies["session_storage"].get.return_value = mock_session
        mock_dependencies["session_coordinator"].complete_agent_run.side_effect = Exception(
            "Completion error"
        )

        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.SESSION_END,
            metadata={"_platform_session_id": "sess-123"},
        )

        response = handlers.handle_session_end(event)

        # Should still allow despite error
        assert response.decision == "allow"

    def test_session_end_summary_generation(self, mock_dependencies: dict) -> None:
        """Test summary file generation on session end."""
        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.SESSION_END,
            session_id="ext-123",
            metadata={"_platform_session_id": "sess-123"},
            data={"transcript_path": "/path/to/transcript.jsonl"},
        )

        handlers.handle_session_end(event)

        mock_dependencies["summary_file_generator"].generate_session_summary.assert_called_once()

    def test_session_end_summary_generation_error(self, mock_dependencies: dict) -> None:
        """Test error in summary generation is handled."""
        mock_dependencies[
            "summary_file_generator"
        ].generate_session_summary.side_effect = Exception("Summary error")

        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.SESSION_END,
            session_id="ext-123",
            metadata={"_platform_session_id": "sess-123"},
        )

        response = handlers.handle_session_end(event)

        # Should still allow despite error
        assert response.decision == "allow"

    def test_session_end_unregister_message_processor(self, mock_dependencies: dict) -> None:
        """Test unregistering from message processor on session end."""
        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.SESSION_END,
            session_id="ext-123",
            metadata={"_platform_session_id": "sess-123"},
        )

        handlers.handle_session_end(event)

        mock_dependencies["message_processor"].unregister_session.assert_called_once_with(
            "sess-123"
        )

    def test_session_end_unregister_uses_external_id_as_fallback(
        self, mock_dependencies: dict
    ) -> None:
        """Test unregister uses external_id when session_id lookup returns None."""
        # Make lookup return None so external_id is used as fallback
        mock_dependencies["session_manager"].lookup_session_id.return_value = None

        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.SESSION_END,
            session_id="ext-123",
            metadata={},  # No _platform_session_id
        )

        handlers.handle_session_end(event)

        # When session_id is None, external_id is used as fallback for unregister
        mock_dependencies["message_processor"].unregister_session.assert_called_once_with("ext-123")

    def test_session_end_unregister_error(self, mock_dependencies: dict) -> None:
        """Test error unregistering from message processor is handled."""
        mock_dependencies["message_processor"].unregister_session.side_effect = Exception(
            "Unregister error"
        )

        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.SESSION_END,
            session_id="ext-123",
            metadata={"_platform_session_id": "sess-123"},
        )

        response = handlers.handle_session_end(event)

        # Should still allow despite error
        assert response.decision == "allow"


class TestBeforeAgentHandling:
    """Test BEFORE_AGENT handler edge cases."""

    def test_before_agent_updates_session_status(self, mock_dependencies: dict) -> None:
        """Test BEFORE_AGENT updates session status to active."""
        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.BEFORE_AGENT,
            data={"prompt": "Hello world"},
            metadata={"_platform_session_id": "sess-123"},
        )

        handlers.handle_before_agent(event)

        mock_dependencies["session_manager"].update_session_status.assert_called_once_with(
            "sess-123", "active"
        )

    def test_before_agent_skips_status_update_for_clear(self, mock_dependencies: dict) -> None:
        """Test BEFORE_AGENT skips status update for /clear command."""
        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.BEFORE_AGENT,
            data={"prompt": "/clear"},
            metadata={"_platform_session_id": "sess-123"},
        )

        handlers.handle_before_agent(event)

        mock_dependencies["session_manager"].update_session_status.assert_not_called()

    def test_before_agent_skips_status_update_for_exit(self, mock_dependencies: dict) -> None:
        """Test BEFORE_AGENT skips status update for /exit command."""
        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.BEFORE_AGENT,
            data={"prompt": "/exit"},
            metadata={"_platform_session_id": "sess-123"},
        )

        handlers.handle_before_agent(event)

        mock_dependencies["session_manager"].update_session_status.assert_not_called()

    def test_before_agent_resets_transcript_processed(self, mock_dependencies: dict) -> None:
        """Test BEFORE_AGENT resets transcript processed flag."""
        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.BEFORE_AGENT,
            data={"prompt": "Hello"},
            metadata={"_platform_session_id": "sess-123"},
        )

        handlers.handle_before_agent(event)

        mock_dependencies["session_storage"].reset_transcript_processed.assert_called_once_with(
            "sess-123"
        )

    def test_before_agent_status_update_error(self, mock_dependencies: dict) -> None:
        """Test error updating session status is handled."""
        mock_dependencies["session_manager"].update_session_status.side_effect = Exception(
            "Update error"
        )

        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.BEFORE_AGENT,
            data={"prompt": "Hello"},
            metadata={"_platform_session_id": "sess-123"},
        )

        response = handlers.handle_before_agent(event)

        # Should still allow despite error
        assert response.decision == "allow"

    def test_before_agent_workflow_deny(self, mock_dependencies: dict) -> None:
        """Test BEFORE_AGENT returns workflow deny response."""
        mock_dependencies["workflow_handler"].handle_all_lifecycles.return_value = HookResponse(
            decision="deny", reason="Not allowed"
        )

        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.BEFORE_AGENT,
            data={"prompt": "Hello"},
        )

        response = handlers.handle_before_agent(event)

        assert response.decision == "deny"
        assert response.reason == "Not allowed"

    def test_before_agent_workflow_context(self, mock_dependencies: dict) -> None:
        """Test BEFORE_AGENT merges workflow context."""
        mock_dependencies["workflow_handler"].handle_all_lifecycles.return_value = HookResponse(
            decision="allow", context="Some context"
        )

        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.BEFORE_AGENT,
            data={"prompt": "Hello"},
        )

        response = handlers.handle_before_agent(event)

        assert "Some context" in response.context

    def test_before_agent_handles_clear_with_transcript(self, mock_dependencies: dict) -> None:
        """Test BEFORE_AGENT handles /clear with transcript path."""
        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.BEFORE_AGENT,
            data={"prompt": "/clear", "transcript_path": "/path/to/transcript.jsonl"},
            metadata={"_platform_session_id": "sess-123"},
        )

        response = handlers.handle_before_agent(event)

        assert response.decision == "allow"


class TestAfterAgentHandling:
    """Test AFTER_AGENT handler edge cases."""

    def test_after_agent_updates_session_status(self, mock_dependencies: dict) -> None:
        """Test AFTER_AGENT updates session status to paused."""
        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.AFTER_AGENT,
            metadata={"_platform_session_id": "sess-123"},
        )

        handlers.handle_after_agent(event)

        mock_dependencies["session_manager"].update_session_status.assert_called_once_with(
            "sess-123", "paused"
        )

    def test_after_agent_status_update_error(self, mock_dependencies: dict) -> None:
        """Test error updating session status is handled."""
        mock_dependencies["session_manager"].update_session_status.side_effect = Exception(
            "Update error"
        )

        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.AFTER_AGENT,
            metadata={"_platform_session_id": "sess-123"},
        )

        response = handlers.handle_after_agent(event)

        # Should still allow despite error
        assert response.decision == "allow"

    def test_after_agent_workflow_deny(self, mock_dependencies: dict) -> None:
        """Test AFTER_AGENT returns workflow deny response."""
        mock_dependencies["workflow_handler"].handle_all_lifecycles.return_value = HookResponse(
            decision="deny", reason="Not allowed"
        )

        handlers = EventHandlers(**mock_dependencies)
        event = make_event(HookEventType.AFTER_AGENT)

        response = handlers.handle_after_agent(event)

        assert response.decision == "deny"

    def test_after_agent_workflow_context(self, mock_dependencies: dict) -> None:
        """Test AFTER_AGENT returns workflow context response."""
        mock_dependencies["workflow_handler"].handle_all_lifecycles.return_value = HookResponse(
            decision="allow", context="Context from workflow"
        )

        handlers = EventHandlers(**mock_dependencies)
        event = make_event(HookEventType.AFTER_AGENT)

        response = handlers.handle_after_agent(event)

        assert "Context from workflow" in response.context

    def test_after_agent_no_session_id(self, mock_dependencies: dict) -> None:
        """Test AFTER_AGENT handles missing session_id."""
        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.AFTER_AGENT,
            metadata={},  # No _platform_session_id
        )

        response = handlers.handle_after_agent(event)

        assert response.decision == "allow"
        mock_dependencies["session_manager"].update_session_status.assert_not_called()


class TestToolHandlerEdgeCases:
    """Test BEFORE_TOOL and AFTER_TOOL edge cases."""

    def test_before_tool_workflow_deny(self, mock_dependencies: dict) -> None:
        """Test BEFORE_TOOL returns workflow deny response."""
        mock_dependencies["workflow_handler"].handle_all_lifecycles.return_value = HookResponse(
            decision="deny", reason="Tool blocked"
        )

        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.BEFORE_TOOL,
            data={"tool_name": "Write"},
        )

        response = handlers.handle_before_tool(event)

        assert response.decision == "deny"
        assert response.reason == "Tool blocked"

    def test_before_tool_workflow_context(self, mock_dependencies: dict) -> None:
        """Test BEFORE_TOOL merges workflow context."""
        mock_dependencies["workflow_handler"].handle_all_lifecycles.return_value = HookResponse(
            decision="allow", context="Tool context"
        )

        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.BEFORE_TOOL,
            data={"tool_name": "Read"},
        )

        response = handlers.handle_before_tool(event)

        assert "Tool context" in response.context

    def test_before_tool_no_session_id(self, mock_dependencies: dict) -> None:
        """Test BEFORE_TOOL handles missing session_id."""
        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.BEFORE_TOOL,
            data={"tool_name": "Read"},
            metadata={},
        )

        response = handlers.handle_before_tool(event)

        assert response.decision == "allow"

    def test_after_tool_failure_status(self, mock_dependencies: dict) -> None:
        """Test AFTER_TOOL handles is_failure metadata."""
        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.AFTER_TOOL,
            data={"tool_name": "Write"},
            metadata={"_platform_session_id": "sess-123", "is_failure": True},
        )

        response = handlers.handle_after_tool(event)

        assert response.decision == "allow"

    def test_after_tool_workflow_deny(self, mock_dependencies: dict) -> None:
        """Test AFTER_TOOL returns workflow deny response."""
        mock_dependencies["workflow_handler"].handle_all_lifecycles.return_value = HookResponse(
            decision="deny", reason="Blocked"
        )

        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.AFTER_TOOL,
            data={"tool_name": "Write"},
        )

        response = handlers.handle_after_tool(event)

        assert response.decision == "deny"

    def test_after_tool_workflow_context(self, mock_dependencies: dict) -> None:
        """Test AFTER_TOOL merges workflow context."""
        mock_dependencies["workflow_handler"].handle_all_lifecycles.return_value = HookResponse(
            decision="allow", context="After tool context"
        )

        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.AFTER_TOOL,
            data={"tool_name": "Read"},
        )

        response = handlers.handle_after_tool(event)

        assert "After tool context" in response.context

    def test_after_tool_no_session_id(self, mock_dependencies: dict) -> None:
        """Test AFTER_TOOL handles missing session_id."""
        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.AFTER_TOOL,
            data={"tool_name": "Read"},
            metadata={},
        )

        response = handlers.handle_after_tool(event)

        assert response.decision == "allow"


class TestStopHandlerEdgeCases:
    """Test STOP handler edge cases."""

    def test_stop_workflow_deny(self, mock_dependencies: dict) -> None:
        """Test STOP returns workflow deny response."""
        mock_dependencies["workflow_handler"].handle_all_lifecycles.return_value = HookResponse(
            decision="deny", reason="Cannot stop"
        )

        handlers = EventHandlers(**mock_dependencies)
        event = make_event(HookEventType.STOP)

        response = handlers.handle_stop(event)

        assert response.decision == "deny"

    def test_stop_workflow_context(self, mock_dependencies: dict) -> None:
        """Test STOP returns workflow context response."""
        mock_dependencies["workflow_handler"].handle_all_lifecycles.return_value = HookResponse(
            decision="allow", context="Stop context"
        )

        handlers = EventHandlers(**mock_dependencies)
        event = make_event(HookEventType.STOP)

        response = handlers.handle_stop(event)

        assert "Stop context" in response.context


class TestPreCompactHandlerEdgeCases:
    """Test PRE_COMPACT handler edge cases."""

    def test_pre_compact_updates_session_status(self, mock_dependencies: dict) -> None:
        """Test PRE_COMPACT updates session status to handoff_ready."""
        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.PRE_COMPACT,
            data={"trigger": "user"},
            metadata={"_platform_session_id": "sess-123"},
        )

        handlers.handle_pre_compact(event)

        mock_dependencies["session_manager"].update_session_status.assert_called_once_with(
            "sess-123", "handoff_ready"
        )

    def test_pre_compact_no_session_id(self, mock_dependencies: dict) -> None:
        """Test PRE_COMPACT handles missing session_id."""
        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.PRE_COMPACT,
            data={"trigger": "auto"},
            metadata={},
        )

        response = handlers.handle_pre_compact(event)

        assert response.decision == "allow"
        mock_dependencies["session_manager"].update_session_status.assert_not_called()

    def test_pre_compact_workflow_response(self, mock_dependencies: dict) -> None:
        """Test PRE_COMPACT returns workflow response."""
        mock_dependencies["workflow_handler"].handle_all_lifecycles.return_value = HookResponse(
            decision="allow", context="Compact context"
        )

        handlers = EventHandlers(**mock_dependencies)
        event = make_event(HookEventType.PRE_COMPACT)

        response = handlers.handle_pre_compact(event)

        assert "Compact context" in response.context


class TestSubagentHandlerEdgeCases:
    """Test SUBAGENT_START and SUBAGENT_STOP edge cases."""

    def test_subagent_start_with_agent_id(self, mock_dependencies: dict) -> None:
        """Test SUBAGENT_START logs agent_id."""
        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.SUBAGENT_START,
            data={"agent_id": "agent-123", "subagent_id": "subagent-456"},
            metadata={"_platform_session_id": "sess-123"},
        )

        response = handlers.handle_subagent_start(event)

        assert response.decision == "allow"

    def test_subagent_start_no_session_id(self, mock_dependencies: dict) -> None:
        """Test SUBAGENT_START handles missing session_id."""
        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.SUBAGENT_START,
            data={"subagent_id": "sub-1"},
            metadata={},
        )

        response = handlers.handle_subagent_start(event)

        assert response.decision == "allow"

    def test_subagent_stop_no_session_id(self, mock_dependencies: dict) -> None:
        """Test SUBAGENT_STOP handles missing session_id."""
        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.SUBAGENT_STOP,
            metadata={},
        )

        response = handlers.handle_subagent_stop(event)

        assert response.decision == "allow"


class TestNotificationHandlerEdgeCases:
    """Test NOTIFICATION handler edge cases."""

    def test_notification_updates_session_status(self, mock_dependencies: dict) -> None:
        """Test NOTIFICATION updates session status to paused."""
        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.NOTIFICATION,
            data={"notification_type": "info"},
            metadata={"_platform_session_id": "sess-123"},
        )

        handlers.handle_notification(event)

        mock_dependencies["session_manager"].update_session_status.assert_called_once_with(
            "sess-123", "paused"
        )

    def test_notification_status_update_error(self, mock_dependencies: dict) -> None:
        """Test error updating session status is handled."""
        mock_dependencies["session_manager"].update_session_status.side_effect = Exception(
            "Update error"
        )

        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.NOTIFICATION,
            data={"notification_type": "info"},
            metadata={"_platform_session_id": "sess-123"},
        )

        response = handlers.handle_notification(event)

        # Should still allow despite error
        assert response.decision == "allow"

    def test_notification_type_variants(self, mock_dependencies: dict) -> None:
        """Test NOTIFICATION handles different type field names."""
        handlers = EventHandlers(**mock_dependencies)

        # Test notificationType field
        event1 = make_event(
            HookEventType.NOTIFICATION,
            data={"notificationType": "warning"},
        )
        response1 = handlers.handle_notification(event1)
        assert response1.decision == "allow"

        # Test type field
        event2 = make_event(
            HookEventType.NOTIFICATION,
            data={"type": "error"},
        )
        response2 = handlers.handle_notification(event2)
        assert response2.decision == "allow"

        # Test no type field (defaults to general)
        event3 = make_event(
            HookEventType.NOTIFICATION,
            data={},
        )
        response3 = handlers.handle_notification(event3)
        assert response3.decision == "allow"

    def test_notification_no_session_id(self, mock_dependencies: dict) -> None:
        """Test NOTIFICATION handles missing session_id."""
        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.NOTIFICATION,
            data={"message": "test"},
            metadata={},
        )

        response = handlers.handle_notification(event)

        assert response.decision == "allow"
        mock_dependencies["session_manager"].update_session_status.assert_not_called()


class TestPermissionRequestEdgeCases:
    """Test PERMISSION_REQUEST handler edge cases."""

    def test_permission_request_with_session_id(self, mock_dependencies: dict) -> None:
        """Test PERMISSION_REQUEST with session_id."""
        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.PERMISSION_REQUEST,
            data={"permission_type": "write"},
            metadata={"_platform_session_id": "sess-123"},
        )

        response = handlers.handle_permission_request(event)

        assert response.decision == "allow"

    def test_permission_request_no_session_id(self, mock_dependencies: dict) -> None:
        """Test PERMISSION_REQUEST handles missing session_id."""
        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.PERMISSION_REQUEST,
            data={"permission_type": "execute"},
            metadata={},
        )

        response = handlers.handle_permission_request(event)

        assert response.decision == "allow"


class TestGeminiHandlerEdgeCases:
    """Test Gemini-only handler edge cases."""

    def test_before_tool_selection_with_session_id(self, mock_dependencies: dict) -> None:
        """Test BEFORE_TOOL_SELECTION with session_id."""
        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.BEFORE_TOOL_SELECTION,
            source="gemini",
            metadata={"_platform_session_id": "sess-123"},
        )

        response = handlers.handle_before_tool_selection(event)

        assert response.decision == "allow"

    def test_before_tool_selection_no_session_id(self, mock_dependencies: dict) -> None:
        """Test BEFORE_TOOL_SELECTION handles missing session_id."""
        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.BEFORE_TOOL_SELECTION,
            source="gemini",
            metadata={},
        )

        response = handlers.handle_before_tool_selection(event)

        assert response.decision == "allow"

    def test_before_model_with_session_id(self, mock_dependencies: dict) -> None:
        """Test BEFORE_MODEL with session_id."""
        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.BEFORE_MODEL,
            source="gemini",
            metadata={"_platform_session_id": "sess-123"},
        )

        response = handlers.handle_before_model(event)

        assert response.decision == "allow"

    def test_before_model_no_session_id(self, mock_dependencies: dict) -> None:
        """Test BEFORE_MODEL handles missing session_id."""
        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.BEFORE_MODEL,
            source="gemini",
            metadata={},
        )

        response = handlers.handle_before_model(event)

        assert response.decision == "allow"

    def test_after_model_with_session_id(self, mock_dependencies: dict) -> None:
        """Test AFTER_MODEL with session_id."""
        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.AFTER_MODEL,
            source="gemini",
            metadata={"_platform_session_id": "sess-123"},
        )

        response = handlers.handle_after_model(event)

        assert response.decision == "allow"

    def test_after_model_no_session_id(self, mock_dependencies: dict) -> None:
        """Test AFTER_MODEL handles missing session_id."""
        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.AFTER_MODEL,
            source="gemini",
            metadata={},
        )

        response = handlers.handle_after_model(event)

        assert response.decision == "allow"


class TestWorkflowErrorHandling:
    """Test workflow error handling across handlers."""

    def test_after_agent_workflow_error(self, mock_dependencies: dict) -> None:
        """Test AFTER_AGENT handles workflow errors gracefully."""
        mock_dependencies["workflow_handler"].handle_all_lifecycles.side_effect = Exception(
            "Workflow error"
        )

        handlers = EventHandlers(**mock_dependencies)
        event = make_event(HookEventType.AFTER_AGENT)

        response = handlers.handle_after_agent(event)

        # Should still allow despite error
        assert response.decision == "allow"

    def test_before_tool_workflow_error(self, mock_dependencies: dict) -> None:
        """Test BEFORE_TOOL handles workflow errors gracefully."""
        mock_dependencies["workflow_handler"].handle_all_lifecycles.side_effect = Exception(
            "Workflow error"
        )

        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.BEFORE_TOOL,
            data={"tool_name": "Read"},
        )

        response = handlers.handle_before_tool(event)

        # Should still allow despite error
        assert response.decision == "allow"

    def test_after_tool_workflow_error(self, mock_dependencies: dict) -> None:
        """Test AFTER_TOOL handles workflow errors gracefully."""
        mock_dependencies["workflow_handler"].handle_all_lifecycles.side_effect = Exception(
            "Workflow error"
        )

        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.AFTER_TOOL,
            data={"tool_name": "Read"},
        )

        response = handlers.handle_after_tool(event)

        # Should still allow despite error
        assert response.decision == "allow"

    def test_stop_workflow_error(self, mock_dependencies: dict) -> None:
        """Test STOP handles workflow errors gracefully."""
        mock_dependencies["workflow_handler"].handle_all_lifecycles.side_effect = Exception(
            "Workflow error"
        )

        handlers = EventHandlers(**mock_dependencies)
        event = make_event(HookEventType.STOP)

        response = handlers.handle_stop(event)

        # Should still allow despite error
        assert response.decision == "allow"

    def test_pre_compact_workflow_error(self, mock_dependencies: dict) -> None:
        """Test PRE_COMPACT handles workflow errors gracefully."""
        mock_dependencies["workflow_handler"].handle_all_lifecycles.side_effect = Exception(
            "Workflow error"
        )

        handlers = EventHandlers(**mock_dependencies)
        event = make_event(HookEventType.PRE_COMPACT)

        response = handlers.handle_pre_compact(event)

        # Should still allow despite error
        assert response.decision == "allow"


class TestSubagentHandlerWithSessionId:
    """Test SUBAGENT handlers with session_id for log coverage."""

    def test_subagent_stop_with_session_id(self, mock_dependencies: dict) -> None:
        """Test SUBAGENT_STOP with session_id present."""
        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.SUBAGENT_STOP,
            metadata={"_platform_session_id": "sess-123"},
        )

        response = handlers.handle_subagent_stop(event)

        assert response.decision == "allow"

    def test_subagent_start_without_subagent_id(self, mock_dependencies: dict) -> None:
        """Test SUBAGENT_START without subagent_id."""
        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.SUBAGENT_START,
            data={"agent_id": "agent-123"},  # No subagent_id
            metadata={"_platform_session_id": "sess-123"},
        )

        response = handlers.handle_subagent_start(event)

        assert response.decision == "allow"

    def test_subagent_start_without_agent_id(self, mock_dependencies: dict) -> None:
        """Test SUBAGENT_START without agent_id."""
        handlers = EventHandlers(**mock_dependencies)
        event = make_event(
            HookEventType.SUBAGENT_START,
            data={},  # No agent_id or subagent_id
            metadata={"_platform_session_id": "sess-123"},
        )

        response = handlers.handle_subagent_start(event)

        assert response.decision == "allow"


class TestNoManagerDependencies:
    """Test handlers when dependencies are None."""

    def test_session_start_no_dependencies(self) -> None:
        """Test SESSION_START works without dependencies."""
        handlers = EventHandlers()
        event = make_event(HookEventType.SESSION_START)

        response = handlers.handle_session_start(event)

        assert response.decision == "allow"

    def test_session_end_no_dependencies(self) -> None:
        """Test SESSION_END works without dependencies."""
        handlers = EventHandlers()
        event = make_event(HookEventType.SESSION_END)

        response = handlers.handle_session_end(event)

        assert response.decision == "allow"

    def test_before_agent_no_dependencies(self) -> None:
        """Test BEFORE_AGENT works without dependencies."""
        handlers = EventHandlers()
        event = make_event(
            HookEventType.BEFORE_AGENT,
            data={"prompt": "Hello"},
        )

        response = handlers.handle_before_agent(event)

        assert response.decision == "allow"

    def test_after_agent_no_dependencies(self) -> None:
        """Test AFTER_AGENT works without dependencies."""
        handlers = EventHandlers()
        event = make_event(HookEventType.AFTER_AGENT)

        response = handlers.handle_after_agent(event)

        assert response.decision == "allow"

    def test_before_tool_no_dependencies(self) -> None:
        """Test BEFORE_TOOL works without dependencies."""
        handlers = EventHandlers()
        event = make_event(
            HookEventType.BEFORE_TOOL,
            data={"tool_name": "Read"},
        )

        response = handlers.handle_before_tool(event)

        assert response.decision == "allow"

    def test_after_tool_no_dependencies(self) -> None:
        """Test AFTER_TOOL works without dependencies."""
        handlers = EventHandlers()
        event = make_event(
            HookEventType.AFTER_TOOL,
            data={"tool_name": "Read"},
        )

        response = handlers.handle_after_tool(event)

        assert response.decision == "allow"

    def test_pre_compact_no_dependencies(self) -> None:
        """Test PRE_COMPACT works without dependencies."""
        handlers = EventHandlers()
        event = make_event(HookEventType.PRE_COMPACT)

        response = handlers.handle_pre_compact(event)

        assert response.decision == "allow"

    def test_stop_no_dependencies(self) -> None:
        """Test STOP works without dependencies."""
        handlers = EventHandlers()
        event = make_event(HookEventType.STOP)

        response = handlers.handle_stop(event)

        assert response.decision == "allow"

    def test_notification_no_dependencies(self) -> None:
        """Test NOTIFICATION works without dependencies."""
        handlers = EventHandlers()
        event = make_event(HookEventType.NOTIFICATION)

        response = handlers.handle_notification(event)

        assert response.decision == "allow"
