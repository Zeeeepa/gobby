"""Tests for Codex notify field mapping and kebab-case normalization.

Covers:
1. _normalize_input_data() with kebab-case Codex payloads
2. Field name variant coverage (snake_case, camelCase, kebab-case)
3. cwd and turn_id propagation through CodexNotifyAdapter
4. Integration: Codex payload -> HookEvent with correct fields
"""

from __future__ import annotations

import pytest

from gobby.adapters.codex_impl.adapter import CodexNotifyAdapter
from gobby.hooks.events import HookEventType, SessionSource
from gobby.install.codex.hooks.hook_dispatcher import _normalize_input_data

pytestmark = pytest.mark.unit


# =============================================================================
# _normalize_input_data() — kebab-case field mapping
# =============================================================================


class TestNormalizeInputDataKebabCase:
    """Tests for kebab-case field normalization in hook_dispatcher."""

    def test_codex_payload_kebab_case(self) -> None:
        """Full Codex payload with kebab-case fields is normalized correctly."""
        event = {
            "type": "agent-turn-complete",
            "thread-id": "thr_abc123",
            "turn-id": "turn_1",
            "cwd": "/path/to/project",
            "input-messages": [{"role": "user", "text": "Help me"}],
            "last-assistant-message": "Done.",
        }

        result = _normalize_input_data(event)

        assert result["session_id"] == "thr_abc123"
        assert result["event_type"] == "agent-turn-complete"
        assert result["last_message"] == "Done."
        assert result["input_messages"] == [{"role": "user", "text": "Help me"}]
        assert result["cwd"] == "/path/to/project"
        assert result["turn_id"] == "turn_1"

    def test_thread_id_kebab_case(self) -> None:
        """thread-id (kebab-case) is extracted as session_id."""
        result = _normalize_input_data({"thread-id": "thr_kebab"})
        assert result["session_id"] == "thr_kebab"

    def test_thread_id_snake_case(self) -> None:
        """thread_id (snake_case) is extracted as session_id."""
        result = _normalize_input_data({"thread_id": "thr_snake"})
        assert result["session_id"] == "thr_snake"

    def test_thread_id_camel_case(self) -> None:
        """threadId (camelCase) is extracted as session_id."""
        result = _normalize_input_data({"threadId": "thr_camel"})
        assert result["session_id"] == "thr_camel"

    def test_session_id_takes_priority(self) -> None:
        """session_id takes priority over thread-id."""
        result = _normalize_input_data({
            "session_id": "priority_one",
            "thread-id": "should_not_win",
        })
        assert result["session_id"] == "priority_one"

    def test_thread_id_from_nested_thread_object(self) -> None:
        """thread.id is extracted when no top-level ID field exists."""
        result = _normalize_input_data({"thread": {"id": "thr_nested"}})
        assert result["session_id"] == "thr_nested"


class TestNormalizeInputDataMessages:
    """Tests for message field normalization."""

    def test_input_messages_kebab_case(self) -> None:
        """input-messages (kebab-case) is extracted."""
        msgs = [{"role": "user", "text": "Hello"}]
        result = _normalize_input_data({"input-messages": msgs})
        assert result["input_messages"] == msgs

    def test_input_messages_snake_case(self) -> None:
        """input_messages (snake_case) is extracted."""
        msgs = [{"role": "user", "text": "Hello"}]
        result = _normalize_input_data({"input_messages": msgs})
        assert result["input_messages"] == msgs

    def test_input_messages_camel_case(self) -> None:
        """inputMessages (camelCase) is extracted."""
        msgs = [{"role": "user", "text": "Hello"}]
        result = _normalize_input_data({"inputMessages": msgs})
        assert result["input_messages"] == msgs

    def test_last_message_kebab_case(self) -> None:
        """last-assistant-message (kebab-case) is extracted."""
        result = _normalize_input_data({"last-assistant-message": "Done."})
        assert result["last_message"] == "Done."

    def test_last_message_snake_case(self) -> None:
        """last_message (snake_case) is extracted."""
        result = _normalize_input_data({"last_message": "Done."})
        assert result["last_message"] == "Done."

    def test_last_message_camel_case(self) -> None:
        """lastMessage (camelCase) is extracted."""
        result = _normalize_input_data({"lastMessage": "Done."})
        assert result["last_message"] == "Done."

    def test_last_message_fallback_from_messages(self) -> None:
        """Falls back to extracting text from input messages."""
        result = _normalize_input_data({
            "input-messages": [{"role": "user", "text": "Extracted fallback"}],
        })
        assert result["last_message"] == "Extracted fallback"

    def test_non_list_messages_returns_empty_list(self) -> None:
        """Non-list messages field returns empty list."""
        result = _normalize_input_data({"input-messages": "not a list"})
        assert result["input_messages"] == []


class TestNormalizeInputDataTurnId:
    """Tests for turn_id field normalization."""

    def test_turn_id_kebab_case(self) -> None:
        """turn-id (kebab-case) is extracted."""
        result = _normalize_input_data({"turn-id": "turn_1"})
        assert result["turn_id"] == "turn_1"

    def test_turn_id_snake_case(self) -> None:
        """turn_id (snake_case) is extracted."""
        result = _normalize_input_data({"turn_id": "turn_2"})
        assert result["turn_id"] == "turn_2"

    def test_turn_id_camel_case(self) -> None:
        """turnId (camelCase) is extracted."""
        result = _normalize_input_data({"turnId": "turn_3"})
        assert result["turn_id"] == "turn_3"

    def test_turn_id_missing_returns_empty_string(self) -> None:
        """Missing turn_id defaults to empty string."""
        result = _normalize_input_data({})
        assert result["turn_id"] == ""


class TestNormalizeInputDataCwd:
    """Tests for cwd field normalization."""

    def test_cwd_present(self) -> None:
        """cwd is passed through when present."""
        result = _normalize_input_data({"cwd": "/home/user/project"})
        assert result["cwd"] == "/home/user/project"

    def test_cwd_missing_returns_empty_string(self) -> None:
        """Missing cwd defaults to empty string."""
        result = _normalize_input_data({})
        assert result["cwd"] == ""


class TestNormalizeInputDataEventType:
    """Tests for event_type field normalization."""

    def test_type_field(self) -> None:
        """type field is extracted as event_type."""
        result = _normalize_input_data({"type": "agent-turn-complete"})
        assert result["event_type"] == "agent-turn-complete"

    def test_event_type_field(self) -> None:
        """event_type field is extracted."""
        result = _normalize_input_data({"event_type": "custom-event"})
        assert result["event_type"] == "custom-event"

    def test_default_event_type(self) -> None:
        """Missing event type defaults to agent-turn-complete."""
        result = _normalize_input_data({})
        assert result["event_type"] == "agent-turn-complete"

    def test_none_event_defaults(self) -> None:
        """None input returns default values."""
        result = _normalize_input_data(None)
        assert result["session_id"] == ""
        assert result["event_type"] == "agent-turn-complete"
        assert result["last_message"] == ""
        assert result["input_messages"] == []
        assert result["cwd"] == ""
        assert result["turn_id"] == ""


# =============================================================================
# CodexNotifyAdapter — cwd and turn_id propagation
# =============================================================================


class TestCodexNotifyAdapterCwdPropagation:
    """Tests for cwd propagation through CodexNotifyAdapter."""

    def test_cwd_propagates_to_hook_event(self) -> None:
        """cwd from input_data reaches HookEvent.data."""
        adapter = CodexNotifyAdapter()

        native_event = {
            "hook_type": "AgentTurnComplete",
            "input_data": {
                "session_id": "thr-cwd-1",
                "event_type": "agent-turn-complete",
                "cwd": "/my/project",
            },
            "source": "codex",
        }

        hook_event = adapter.translate_to_hook_event(native_event)

        assert hook_event is not None
        assert hook_event.data["cwd"] == "/my/project"

    def test_missing_cwd_is_none(self) -> None:
        """Missing cwd results in None (not daemon's os.getcwd())."""
        adapter = CodexNotifyAdapter()

        native_event = {
            "hook_type": "AgentTurnComplete",
            "input_data": {
                "session_id": "thr-no-cwd",
                "event_type": "agent-turn-complete",
            },
            "source": "codex",
        }

        hook_event = adapter.translate_to_hook_event(native_event)

        assert hook_event is not None
        assert hook_event.data["cwd"] is None

    def test_turn_id_propagates_to_hook_event(self) -> None:
        """turn_id from input_data reaches HookEvent.data."""
        adapter = CodexNotifyAdapter()

        native_event = {
            "hook_type": "AgentTurnComplete",
            "input_data": {
                "session_id": "thr-turn-1",
                "event_type": "agent-turn-complete",
                "cwd": "/project",
                "turn_id": "turn_7",
            },
            "source": "codex",
        }

        hook_event = adapter.translate_to_hook_event(native_event)

        assert hook_event is not None
        assert hook_event.data["turn_id"] == "turn_7"


# =============================================================================
# End-to-end: Codex kebab-case payload -> normalized -> HookEvent
# =============================================================================


class TestCodexEndToEndKebabCase:
    """Integration test: kebab-case Codex payload flows through normalization
    and adapter to produce a correct HookEvent."""

    def test_full_codex_payload_through_adapter(self) -> None:
        """Simulate the complete flow: Codex kebab-case -> normalize -> adapter."""
        # Step 1: Normalize the raw Codex payload (as hook_dispatcher.py does)
        raw_codex_event = {
            "type": "agent-turn-complete",
            "thread-id": "thr_e2e_123",
            "turn-id": "turn_5",
            "cwd": "/users/dev/myproject",
            "input-messages": [{"role": "user", "text": "Fix the bug"}],
            "last-assistant-message": "Bug fixed in main.py",
        }

        normalized = _normalize_input_data(raw_codex_event)

        # Step 2: Build the native_event as hook_dispatcher.py sends to /api/hooks/execute
        native_event = {
            "hook_type": "AgentTurnComplete",
            "input_data": normalized,
            "source": "codex",
        }

        # Step 3: Translate through CodexNotifyAdapter
        adapter = CodexNotifyAdapter()
        hook_event = adapter.translate_to_hook_event(native_event)

        # Verify all fields made it through
        assert hook_event is not None
        assert hook_event.event_type == HookEventType.AFTER_AGENT
        assert hook_event.session_id == "thr_e2e_123"
        assert hook_event.source == SessionSource.CODEX
        assert hook_event.data["cwd"] == "/users/dev/myproject"
        assert hook_event.data["turn_id"] == "turn_5"
        assert hook_event.data["last_message"] == "Bug fixed in main.py"
        assert hook_event.data["input_messages"] == [{"role": "user", "text": "Fix the bug"}]
        assert hook_event.data["is_first_event"] is True
        assert hook_event.data["prompt"] == "Fix the bug"

    def test_second_event_same_thread(self) -> None:
        """Second event for same thread has is_first_event=False."""
        adapter = CodexNotifyAdapter()

        raw_codex_event = {
            "type": "agent-turn-complete",
            "thread-id": "thr_repeat",
            "turn-id": "turn_1",
            "cwd": "/project",
            "input-messages": [{"role": "user", "text": "First"}],
            "last-assistant-message": "OK",
        }

        normalized = _normalize_input_data(raw_codex_event)
        native_event = {
            "hook_type": "AgentTurnComplete",
            "input_data": normalized,
            "source": "codex",
        }

        # First event
        event1 = adapter.translate_to_hook_event(native_event)
        assert event1.data["is_first_event"] is True

        # Second event (update turn_id)
        raw_codex_event["turn-id"] = "turn_2"
        raw_codex_event["last-assistant-message"] = "Still here"
        normalized2 = _normalize_input_data(raw_codex_event)
        native_event2 = {
            "hook_type": "AgentTurnComplete",
            "input_data": normalized2,
            "source": "codex",
        }

        event2 = adapter.translate_to_hook_event(native_event2)
        assert event2.data["is_first_event"] is False
        assert event2.data["prompt"] is None
