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
from datetime import UTC, datetime, timezone
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
    workflow_handler.handle_all_lifecycles.return_value = HookResponse(
        decision="allow", context=""
    )
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

    def test_get_handler_for_unknown_returns_none(
        self, event_handlers: EventHandlers
    ) -> None:
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
        mock_dependencies["workflow_handler"].handle_all_lifecycles.side_effect = (
            Exception("Workflow error")
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
