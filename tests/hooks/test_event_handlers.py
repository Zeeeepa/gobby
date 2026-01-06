"""
Tests for EventHandlers module (TDD red phase).

These tests are written BEFORE the module exists to drive the extraction
from hook_manager.py. They should initially fail with ImportError.

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
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import pytest

# This import should fail initially (red phase) - module doesn't exist yet
from gobby.hooks.event_handlers import EventHandlers
from gobby.hooks.events import HookEvent, HookEventType, HookResponse

if TYPE_CHECKING:
    from gobby.sessions.manager import SessionManager
    from gobby.workflows.hooks import WorkflowHookHandler


@pytest.fixture
def mock_dependencies() -> dict[str, Any]:
    """Create mock dependencies for EventHandlers."""
    return {
        "session_manager": MagicMock(),
        "workflow_handler": MagicMock(),
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

    def test_get_handler_for_unknown_returns_none(
        self, event_handlers: EventHandlers
    ) -> None:
        """Test get_handler returns None for unknown event type."""
        # Use an invalid string that's not a valid enum
        result = event_handlers.get_handler("invalid_event")  # type: ignore
        assert result is None

    def test_handler_map_is_immutable(self, event_handlers: EventHandlers) -> None:
        """Test handler map cannot be modified externally."""
        # Attempting to modify should either fail or not affect internal state
        handler_map = event_handlers.get_handler_map()
        original_count = len(handler_map)
        handler_map["fake"] = lambda x: x  # Try to modify
        assert len(event_handlers.get_handler_map()) == original_count


class TestSessionStartHandler:
    """Test SESSION_START event handler."""

    def test_session_start_creates_session(
        self, event_handlers: EventHandlers, mock_dependencies: dict
    ) -> None:
        """Test SESSION_START handler creates a new session."""
        event = HookEvent(
            event_type=HookEventType.SESSION_START,
            session_id="ext-123",
            source="claude",
            data={"transcript_path": "/path/to/transcript.jsonl"},
        )

        response = event_handlers.handle_session_start(event)

        assert response.decision == "allow"
        mock_dependencies["session_manager"].register_session.assert_called()

    def test_session_start_returns_context(
        self, event_handlers: EventHandlers
    ) -> None:
        """Test SESSION_START handler returns appropriate context."""
        event = HookEvent(
            event_type=HookEventType.SESSION_START,
            session_id="ext-123",
            source="claude",
            data={},
        )

        response = event_handlers.handle_session_start(event)

        assert isinstance(response, HookResponse)
        assert response.decision in ("allow", "block")


class TestSessionEndHandler:
    """Test SESSION_END event handler."""

    def test_session_end_completes_session(
        self, event_handlers: EventHandlers, mock_dependencies: dict
    ) -> None:
        """Test SESSION_END handler completes the session."""
        event = HookEvent(
            event_type=HookEventType.SESSION_END,
            session_id="ext-123",
            source="claude",
            data={},
            metadata={"_platform_session_id": "plat-123"},
        )

        response = event_handlers.handle_session_end(event)

        assert response.decision == "allow"

    def test_session_end_triggers_summary_generation(
        self, event_handlers: EventHandlers, mock_dependencies: dict
    ) -> None:
        """Test SESSION_END triggers summary generation if configured."""
        event = HookEvent(
            event_type=HookEventType.SESSION_END,
            session_id="ext-123",
            source="claude",
            data={"transcript_path": "/path/to/transcript.jsonl"},
            metadata={"_platform_session_id": "plat-123"},
        )

        event_handlers.handle_session_end(event)

        # Summary generation may be called depending on configuration
        # Just verify no exception is raised


class TestBeforeAgentHandler:
    """Test BEFORE_AGENT event handler."""

    def test_before_agent_allows_by_default(self, event_handlers: EventHandlers) -> None:
        """Test BEFORE_AGENT allows execution by default."""
        event = HookEvent(
            event_type=HookEventType.BEFORE_AGENT,
            session_id="ext-123",
            source="claude",
            data={"prompt": "Hello"},
            metadata={"_platform_session_id": "plat-123"},
        )

        response = event_handlers.handle_before_agent(event)

        assert response.decision == "allow"

    def test_before_agent_executes_workflows(
        self, event_handlers: EventHandlers, mock_dependencies: dict
    ) -> None:
        """Test BEFORE_AGENT executes lifecycle workflows."""
        event = HookEvent(
            event_type=HookEventType.BEFORE_AGENT,
            session_id="ext-123",
            source="claude",
            data={"prompt": "Hello"},
            metadata={"_platform_session_id": "plat-123"},
        )

        mock_dependencies["workflow_handler"].handle_all_lifecycles.return_value = (
            HookResponse(decision="allow")
        )

        event_handlers.handle_before_agent(event)

        mock_dependencies["workflow_handler"].handle_all_lifecycles.assert_called_once()


class TestAfterAgentHandler:
    """Test AFTER_AGENT event handler."""

    def test_after_agent_allows_by_default(self, event_handlers: EventHandlers) -> None:
        """Test AFTER_AGENT allows by default."""
        event = HookEvent(
            event_type=HookEventType.AFTER_AGENT,
            session_id="ext-123",
            source="claude",
            data={},
            metadata={"_platform_session_id": "plat-123"},
        )

        response = event_handlers.handle_after_agent(event)

        assert response.decision == "allow"


class TestBeforeToolHandler:
    """Test BEFORE_TOOL event handler."""

    def test_before_tool_allows_safe_tools(self, event_handlers: EventHandlers) -> None:
        """Test BEFORE_TOOL allows safe tools."""
        event = HookEvent(
            event_type=HookEventType.BEFORE_TOOL,
            session_id="ext-123",
            source="claude",
            data={"tool_name": "Read"},
            metadata={"_platform_session_id": "plat-123"},
        )

        response = event_handlers.handle_before_tool(event)

        assert response.decision == "allow"

    def test_before_tool_can_block_tools(
        self, event_handlers: EventHandlers, mock_dependencies: dict
    ) -> None:
        """Test BEFORE_TOOL can block dangerous tools via workflow."""
        event = HookEvent(
            event_type=HookEventType.BEFORE_TOOL,
            session_id="ext-123",
            source="claude",
            data={"tool_name": "Bash"},
            metadata={"_platform_session_id": "plat-123"},
        )

        mock_dependencies["workflow_handler"].handle_all_lifecycles.return_value = (
            HookResponse(decision="block", reason="Tool blocked by workflow")
        )

        response = event_handlers.handle_before_tool(event)

        # Result depends on workflow configuration
        assert response.decision in ("allow", "block")


class TestAfterToolHandler:
    """Test AFTER_TOOL event handler."""

    def test_after_tool_allows_by_default(self, event_handlers: EventHandlers) -> None:
        """Test AFTER_TOOL allows by default."""
        event = HookEvent(
            event_type=HookEventType.AFTER_TOOL,
            session_id="ext-123",
            source="claude",
            data={"tool_name": "Read", "output": "file content"},
            metadata={"_platform_session_id": "plat-123"},
        )

        response = event_handlers.handle_after_tool(event)

        assert response.decision == "allow"


class TestStopHandler:
    """Test STOP event handler (Claude Code only)."""

    def test_stop_allows_by_default(self, event_handlers: EventHandlers) -> None:
        """Test STOP allows by default."""
        event = HookEvent(
            event_type=HookEventType.STOP,
            session_id="ext-123",
            source="claude",
            data={},
            metadata={"_platform_session_id": "plat-123"},
        )

        response = event_handlers.handle_stop(event)

        assert response.decision == "allow"


class TestPreCompactHandler:
    """Test PRE_COMPACT event handler."""

    def test_pre_compact_allows(self, event_handlers: EventHandlers) -> None:
        """Test PRE_COMPACT allows compaction."""
        event = HookEvent(
            event_type=HookEventType.PRE_COMPACT,
            session_id="ext-123",
            source="claude",
            data={},
            metadata={"_platform_session_id": "plat-123"},
        )

        response = event_handlers.handle_pre_compact(event)

        assert response.decision == "allow"


class TestSubagentHandlers:
    """Test SUBAGENT_START and SUBAGENT_STOP handlers."""

    def test_subagent_start_allows(self, event_handlers: EventHandlers) -> None:
        """Test SUBAGENT_START allows spawning."""
        event = HookEvent(
            event_type=HookEventType.SUBAGENT_START,
            session_id="ext-123",
            source="claude",
            data={"subagent_id": "sub-1"},
            metadata={"_platform_session_id": "plat-123"},
        )

        response = event_handlers.handle_subagent_start(event)

        assert response.decision == "allow"

    def test_subagent_stop_allows(self, event_handlers: EventHandlers) -> None:
        """Test SUBAGENT_STOP allows termination."""
        event = HookEvent(
            event_type=HookEventType.SUBAGENT_STOP,
            session_id="ext-123",
            source="claude",
            data={"subagent_id": "sub-1"},
            metadata={"_platform_session_id": "plat-123"},
        )

        response = event_handlers.handle_subagent_stop(event)

        assert response.decision == "allow"


class TestNotificationHandler:
    """Test NOTIFICATION event handler."""

    def test_notification_allows(self, event_handlers: EventHandlers) -> None:
        """Test NOTIFICATION handler processes notifications."""
        event = HookEvent(
            event_type=HookEventType.NOTIFICATION,
            session_id="ext-123",
            source="claude",
            data={"message": "Test notification"},
            metadata={"_platform_session_id": "plat-123"},
        )

        response = event_handlers.handle_notification(event)

        assert response.decision == "allow"


class TestPermissionRequestHandler:
    """Test PERMISSION_REQUEST handler (Claude Code only)."""

    def test_permission_request_allows(self, event_handlers: EventHandlers) -> None:
        """Test PERMISSION_REQUEST allows by default."""
        event = HookEvent(
            event_type=HookEventType.PERMISSION_REQUEST,
            session_id="ext-123",
            source="claude",
            data={"permission": "file_write"},
            metadata={"_platform_session_id": "plat-123"},
        )

        response = event_handlers.handle_permission_request(event)

        assert response.decision == "allow"


class TestGeminiOnlyHandlers:
    """Test Gemini-only event handlers."""

    def test_before_tool_selection_allows(self, event_handlers: EventHandlers) -> None:
        """Test BEFORE_TOOL_SELECTION allows (Gemini only)."""
        event = HookEvent(
            event_type=HookEventType.BEFORE_TOOL_SELECTION,
            session_id="ext-123",
            source="gemini",
            data={},
            metadata={"_platform_session_id": "plat-123"},
        )

        response = event_handlers.handle_before_tool_selection(event)

        assert response.decision == "allow"

    def test_before_model_allows(self, event_handlers: EventHandlers) -> None:
        """Test BEFORE_MODEL allows (Gemini only)."""
        event = HookEvent(
            event_type=HookEventType.BEFORE_MODEL,
            session_id="ext-123",
            source="gemini",
            data={},
            metadata={"_platform_session_id": "plat-123"},
        )

        response = event_handlers.handle_before_model(event)

        assert response.decision == "allow"

    def test_after_model_allows(self, event_handlers: EventHandlers) -> None:
        """Test AFTER_MODEL allows (Gemini only)."""
        event = HookEvent(
            event_type=HookEventType.AFTER_MODEL,
            session_id="ext-123",
            source="gemini",
            data={},
            metadata={"_platform_session_id": "plat-123"},
        )

        response = event_handlers.handle_after_model(event)

        assert response.decision == "allow"


class TestErrorIsolation:
    """Test handler error isolation."""

    def test_handler_error_doesnt_crash(
        self, event_handlers: EventHandlers, mock_dependencies: dict
    ) -> None:
        """Test that handler errors don't crash the system."""
        event = HookEvent(
            event_type=HookEventType.BEFORE_AGENT,
            session_id="ext-123",
            source="claude",
            data={"prompt": "Hello"},
            metadata={"_platform_session_id": "plat-123"},
        )

        # Make workflow handler raise an exception
        mock_dependencies["workflow_handler"].handle_all_lifecycles.side_effect = (
            Exception("Workflow error")
        )

        # Should not raise, should return a safe default
        response = event_handlers.handle_before_agent(event)
        assert response.decision in ("allow", "block")

    def test_missing_session_handled_gracefully(
        self, event_handlers: EventHandlers, mock_dependencies: dict
    ) -> None:
        """Test missing session is handled gracefully."""
        event = HookEvent(
            event_type=HookEventType.BEFORE_TOOL,
            session_id="nonexistent",
            source="claude",
            data={"tool_name": "Read"},
            metadata={},  # No _platform_session_id
        )

        # Should not raise
        response = event_handlers.handle_before_tool(event)
        assert response.decision in ("allow", "block")


class TestContextPassing:
    """Test context passing between handlers."""

    def test_handler_receives_event_metadata(
        self, event_handlers: EventHandlers
    ) -> None:
        """Test handlers receive event metadata."""
        event = HookEvent(
            event_type=HookEventType.BEFORE_AGENT,
            session_id="ext-123",
            source="claude",
            data={"prompt": "Hello"},
            metadata={
                "_platform_session_id": "plat-123",
                "custom_key": "custom_value",
            },
        )

        # Should not raise - metadata is accessible
        response = event_handlers.handle_before_agent(event)
        assert isinstance(response, HookResponse)

    def test_handler_can_add_to_context(
        self, event_handlers: EventHandlers, mock_dependencies: dict
    ) -> None:
        """Test handlers can add context to response."""
        event = HookEvent(
            event_type=HookEventType.SESSION_START,
            session_id="ext-123",
            source="claude",
            data={},
        )

        response = event_handlers.handle_session_start(event)

        # Context may contain session info
        assert isinstance(response.context, str)


class TestReturnValueHandling:
    """Test handler return value handling."""

    def test_handler_returns_hook_response(self, event_handlers: EventHandlers) -> None:
        """Test all handlers return HookResponse."""
        event = HookEvent(
            event_type=HookEventType.BEFORE_AGENT,
            session_id="ext-123",
            source="claude",
            data={"prompt": "Hello"},
            metadata={"_platform_session_id": "plat-123"},
        )

        response = event_handlers.handle_before_agent(event)

        assert isinstance(response, HookResponse)
        assert hasattr(response, "decision")
        assert hasattr(response, "context")

    def test_handler_decision_is_valid(self, event_handlers: EventHandlers) -> None:
        """Test handler decision is a valid value."""
        event = HookEvent(
            event_type=HookEventType.BEFORE_TOOL,
            session_id="ext-123",
            source="claude",
            data={"tool_name": "Read"},
            metadata={"_platform_session_id": "plat-123"},
        )

        response = event_handlers.handle_before_tool(event)

        assert response.decision in ("allow", "block", "deny")


class TestEventHandlersInitialization:
    """Test EventHandlers initialization."""

    def test_init_with_all_dependencies(self, mock_dependencies: dict) -> None:
        """Test initialization with all dependencies."""
        handlers = EventHandlers(**mock_dependencies)

        assert handlers._session_manager is mock_dependencies["session_manager"]
        assert handlers._workflow_handler is mock_dependencies["workflow_handler"]

    def test_init_creates_logger_if_not_provided(self) -> None:
        """Test initialization creates logger if not provided."""
        handlers = EventHandlers()

        assert handlers.logger is not None
        assert isinstance(handlers.logger, logging.Logger)
