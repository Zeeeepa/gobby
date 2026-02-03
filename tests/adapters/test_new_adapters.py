"""Tests for new CLI adapters (Cursor, Windsurf, Copilot)."""

import pytest

from gobby.adapters.copilot import CopilotAdapter
from gobby.adapters.cursor import CursorAdapter
from gobby.adapters.windsurf import WindsurfAdapter
from gobby.hooks.events import HookEventType, HookResponse, SessionSource

pytestmark = pytest.mark.unit


# =============================================================================
# CopilotAdapter Tests
# =============================================================================


class TestCopilotAdapter:
    """Tests for CopilotAdapter translation logic."""

    def test_source(self) -> None:
        """CopilotAdapter reports COPILOT as source."""
        adapter = CopilotAdapter()
        assert adapter.source == SessionSource.COPILOT

    def test_event_map_session_start(self) -> None:
        """Maps sessionStart to SESSION_START."""
        adapter = CopilotAdapter()
        assert adapter.EVENT_MAP["sessionStart"] == HookEventType.SESSION_START

    def test_event_map_session_end(self) -> None:
        """Maps sessionEnd to SESSION_END."""
        adapter = CopilotAdapter()
        assert adapter.EVENT_MAP["sessionEnd"] == HookEventType.SESSION_END

    def test_event_map_user_prompt(self) -> None:
        """Maps userPromptSubmitted to BEFORE_AGENT."""
        adapter = CopilotAdapter()
        assert adapter.EVENT_MAP["userPromptSubmitted"] == HookEventType.BEFORE_AGENT

    def test_event_map_pre_tool(self) -> None:
        """Maps preToolUse to BEFORE_TOOL."""
        adapter = CopilotAdapter()
        assert adapter.EVENT_MAP["preToolUse"] == HookEventType.BEFORE_TOOL

    def test_event_map_post_tool(self) -> None:
        """Maps postToolUse to AFTER_TOOL."""
        adapter = CopilotAdapter()
        assert adapter.EVENT_MAP["postToolUse"] == HookEventType.AFTER_TOOL

    def test_event_map_error(self) -> None:
        """Maps errorOccurred to NOTIFICATION."""
        adapter = CopilotAdapter()
        assert adapter.EVENT_MAP["errorOccurred"] == HookEventType.NOTIFICATION

    def test_translate_camel_case_tool_name(self) -> None:
        """Translates toolName to tool_name."""
        adapter = CopilotAdapter()
        native_event = {
            "hook_type": "preToolUse",
            "input_data": {
                "session_id": "test-session",
                "toolName": "Read",
                "toolArgs": {"path": "/file.py"},
            },
        }
        hook_event = adapter.translate_to_hook_event(native_event)
        assert hook_event.data["tool_name"] == "Read"
        assert hook_event.data["tool_input"] == {"path": "/file.py"}

    def test_translate_tool_result(self) -> None:
        """Extracts toolResult.textResultForLlm to tool_output."""
        adapter = CopilotAdapter()
        native_event = {
            "hook_type": "postToolUse",
            "input_data": {
                "session_id": "test-session",
                "toolName": "Read",
                "toolResult": {
                    "resultType": "success",
                    "textResultForLlm": "file contents here",
                },
            },
        }
        hook_event = adapter.translate_to_hook_event(native_event)
        assert hook_event.data["tool_output"] == "file contents here"

    def test_translate_tool_error(self) -> None:
        """Detects error resultType and sets is_failure metadata."""
        adapter = CopilotAdapter()
        native_event = {
            "hook_type": "postToolUse",
            "input_data": {
                "session_id": "test-session",
                "toolName": "Read",
                "toolResult": {
                    "resultType": "error",
                    "textResultForLlm": "File not found",
                },
            },
        }
        hook_event = adapter.translate_to_hook_event(native_event)
        assert hook_event.metadata.get("is_failure") is True

    def test_translate_mcp_extraction(self) -> None:
        """Extracts MCP server and tool from call_tool toolArgs."""
        adapter = CopilotAdapter()
        native_event = {
            "hook_type": "preToolUse",
            "input_data": {
                "session_id": "test-session",
                "toolName": "call_tool",
                "toolArgs": {
                    "server_name": "gobby",
                    "tool_name": "create_task",
                    "arguments": {"title": "Test"},
                },
            },
        }
        hook_event = adapter.translate_to_hook_event(native_event)
        assert hook_event.data["mcp_server"] == "gobby"
        assert hook_event.data["mcp_tool"] == "create_task"

    def test_response_permission_allow(self) -> None:
        """Response uses permissionDecision: allow for allow decision."""
        adapter = CopilotAdapter()
        response = HookResponse(decision="allow")
        result = adapter.translate_from_hook_response(response, hook_type="preToolUse")
        assert result["permissionDecision"] == "allow"

    def test_response_permission_deny(self) -> None:
        """Response uses permissionDecision: deny for deny decision."""
        adapter = CopilotAdapter()
        response = HookResponse(decision="deny", reason="Not allowed")
        result = adapter.translate_from_hook_response(response, hook_type="preToolUse")
        assert result["permissionDecision"] == "deny"
        assert result["permissionDecisionReason"] == "Not allowed"

    def test_response_permission_block(self) -> None:
        """Response maps block to permissionDecision: deny."""
        adapter = CopilotAdapter()
        response = HookResponse(decision="block")
        result = adapter.translate_from_hook_response(response, hook_type="preToolUse")
        assert result["permissionDecision"] == "deny"

    def test_response_context_injection(self) -> None:
        """Response includes hookSpecificOutput with additionalContext."""
        adapter = CopilotAdapter()
        response = HookResponse(decision="allow", context="Important context here")
        result = adapter.translate_from_hook_response(response, hook_type="preToolUse")
        assert "hookSpecificOutput" in result
        assert result["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
        assert "Important context here" in result["hookSpecificOutput"]["additionalContext"]

    def test_unknown_event_maps_to_notification(self) -> None:
        """Unknown hook types fall back to NOTIFICATION."""
        adapter = CopilotAdapter()
        native_event = {
            "hook_type": "unknownEvent",
            "input_data": {"session_id": "test"},
        }
        hook_event = adapter.translate_to_hook_event(native_event)
        assert hook_event.event_type == HookEventType.NOTIFICATION


# =============================================================================
# WindsurfAdapter Tests
# =============================================================================


class TestWindsurfAdapter:
    """Tests for WindsurfAdapter translation logic."""

    def test_source(self) -> None:
        """WindsurfAdapter reports WINDSURF as source."""
        adapter = WindsurfAdapter()
        assert adapter.source == SessionSource.WINDSURF

    def test_event_map_pre_read(self) -> None:
        """Maps pre_read_code to BEFORE_TOOL."""
        adapter = WindsurfAdapter()
        assert adapter.EVENT_MAP["pre_read_code"] == HookEventType.BEFORE_TOOL

    def test_event_map_post_read(self) -> None:
        """Maps post_read_code to AFTER_TOOL."""
        adapter = WindsurfAdapter()
        assert adapter.EVENT_MAP["post_read_code"] == HookEventType.AFTER_TOOL

    def test_event_map_post_write(self) -> None:
        """Maps post_write_code to AFTER_TOOL."""
        adapter = WindsurfAdapter()
        assert adapter.EVENT_MAP["post_write_code"] == HookEventType.AFTER_TOOL

    def test_event_map_post_command(self) -> None:
        """Maps post_run_command to AFTER_TOOL."""
        adapter = WindsurfAdapter()
        assert adapter.EVENT_MAP["post_run_command"] == HookEventType.AFTER_TOOL

    def test_event_map_post_mcp(self) -> None:
        """Maps post_mcp_tool_use to AFTER_TOOL."""
        adapter = WindsurfAdapter()
        assert adapter.EVENT_MAP["post_mcp_tool_use"] == HookEventType.AFTER_TOOL

    def test_event_map_cascade_response(self) -> None:
        """Maps post_cascade_response to AFTER_AGENT."""
        adapter = WindsurfAdapter()
        assert adapter.EVENT_MAP["post_cascade_response"] == HookEventType.AFTER_AGENT

    def test_tool_map_read(self) -> None:
        """Maps read_code actions to Read tool."""
        adapter = WindsurfAdapter()
        assert adapter.TOOL_MAP["pre_read_code"] == "Read"
        assert adapter.TOOL_MAP["post_read_code"] == "Read"

    def test_tool_map_write(self) -> None:
        """Maps write_code actions to Write tool."""
        adapter = WindsurfAdapter()
        assert adapter.TOOL_MAP["pre_write_code"] == "Write"
        assert adapter.TOOL_MAP["post_write_code"] == "Write"

    def test_tool_map_bash(self) -> None:
        """Maps run_command actions to Bash tool."""
        adapter = WindsurfAdapter()
        assert adapter.TOOL_MAP["pre_run_command"] == "Bash"
        assert adapter.TOOL_MAP["post_run_command"] == "Bash"

    def test_translate_read_code(self) -> None:
        """Extracts file_path and content from read_code tool_info."""
        adapter = WindsurfAdapter()
        native_event = {
            "hook_type": "post_read_code",
            "input_data": {
                "session_id": "test-session",
                "tool_info": {
                    "file_path": "/path/to/file.py",
                    "content": "file contents here",
                },
            },
        }
        hook_event = adapter.translate_to_hook_event(native_event)
        assert hook_event.data["tool_name"] == "Read"
        assert hook_event.data["tool_input"]["file_path"] == "/path/to/file.py"
        assert hook_event.data["tool_output"] == "file contents here"

    def test_translate_write_code(self) -> None:
        """Extracts file_path and edits from write_code tool_info."""
        adapter = WindsurfAdapter()
        native_event = {
            "hook_type": "post_write_code",
            "input_data": {
                "session_id": "test-session",
                "tool_info": {
                    "file_path": "/path/to/file.py",
                    "edits": [{"old_string": "old", "new_string": "new"}],
                },
            },
        }
        hook_event = adapter.translate_to_hook_event(native_event)
        assert hook_event.data["tool_name"] == "Write"
        assert hook_event.data["tool_input"]["file_path"] == "/path/to/file.py"
        assert hook_event.data["tool_input"]["edits"] == [
            {"old_string": "old", "new_string": "new"}
        ]

    def test_translate_run_command(self) -> None:
        """Extracts command and output from run_command tool_info."""
        adapter = WindsurfAdapter()
        native_event = {
            "hook_type": "post_run_command",
            "input_data": {
                "session_id": "test-session",
                "tool_info": {
                    "command": "ls -la",
                    "output": "total 8\ndrwxr-xr-x...",
                    "exit_code": 0,
                },
            },
        }
        hook_event = adapter.translate_to_hook_event(native_event)
        assert hook_event.data["tool_name"] == "Bash"
        assert hook_event.data["tool_input"]["command"] == "ls -la"
        assert hook_event.data["tool_output"] == "total 8\ndrwxr-xr-x..."

    def test_translate_command_error(self) -> None:
        """Detects non-zero exit_code and sets is_failure metadata."""
        adapter = WindsurfAdapter()
        native_event = {
            "hook_type": "post_run_command",
            "input_data": {
                "session_id": "test-session",
                "tool_info": {
                    "command": "false",
                    "output": "",
                    "exit_code": 1,
                },
            },
        }
        hook_event = adapter.translate_to_hook_event(native_event)
        assert hook_event.metadata.get("is_failure") is True

    def test_translate_mcp_tool(self) -> None:
        """Extracts MCP details from mcp_tool_use tool_info."""
        adapter = WindsurfAdapter()
        native_event = {
            "hook_type": "post_mcp_tool_use",
            "input_data": {
                "session_id": "test-session",
                "tool_info": {
                    "server_name": "gobby",
                    "tool_name": "list_tasks",
                    "arguments": {"status": "open"},
                    "result": "[{...}]",
                },
            },
        }
        hook_event = adapter.translate_to_hook_event(native_event)
        assert hook_event.data["mcp_server"] == "gobby"
        assert hook_event.data["mcp_tool"] == "list_tasks"
        assert hook_event.data["tool_input"] == {"status": "open"}
        assert hook_event.data["tool_output"] == "[{...}]"

    def test_translate_agent_action_name(self) -> None:
        """Uses agent_action_name from input_data if hook_type missing."""
        adapter = WindsurfAdapter()
        native_event = {
            "input_data": {
                "session_id": "test-session",
                "agent_action_name": "post_write_code",
                "tool_info": {"file_path": "/test.py", "edits": []},
            },
        }
        hook_event = adapter.translate_to_hook_event(native_event)
        assert hook_event.event_type == HookEventType.AFTER_TOOL
        assert hook_event.data["tool_name"] == "Write"

    def test_response_allow(self) -> None:
        """Response uses decision: allow format."""
        adapter = WindsurfAdapter()
        response = HookResponse(decision="allow")
        result = adapter.translate_from_hook_response(response)
        assert result["decision"] == "allow"

    def test_response_deny(self) -> None:
        """Response uses decision: deny format."""
        adapter = WindsurfAdapter()
        response = HookResponse(decision="deny", reason="Blocked")
        result = adapter.translate_from_hook_response(response)
        assert result["decision"] == "deny"
        assert result["reason"] == "Blocked"

    def test_response_context(self) -> None:
        """Response includes context field."""
        adapter = WindsurfAdapter()
        response = HookResponse(decision="allow", context="Session context")
        result = adapter.translate_from_hook_response(response)
        assert "Session context" in result["context"]

    def test_unknown_action_maps_to_notification(self) -> None:
        """Unknown action names fall back to NOTIFICATION."""
        adapter = WindsurfAdapter()
        native_event = {
            "hook_type": "unknown_action",
            "input_data": {"session_id": "test"},
        }
        hook_event = adapter.translate_to_hook_event(native_event)
        assert hook_event.event_type == HookEventType.NOTIFICATION


# =============================================================================
# CursorAdapter Tests
# =============================================================================


class TestCursorAdapter:
    """Tests for CursorAdapter (documented stub)."""

    def test_source(self) -> None:
        """CursorAdapter reports CURSOR as source."""
        adapter = CursorAdapter()
        assert adapter.source == SessionSource.CURSOR

    def test_has_documentation(self) -> None:
        """Module has comprehensive documentation about NDJSON architecture."""
        import gobby.adapters.cursor as cursor_module

        docstring = cursor_module.__doc__
        assert docstring is not None
        assert "NDJSON" in docstring
        assert "streaming" in docstring.lower()
        assert "Future Integration Options" in docstring

    def test_event_map_ndjson_started(self) -> None:
        """Maps tool_call:started to BEFORE_TOOL."""
        adapter = CursorAdapter()
        assert adapter.EVENT_MAP["tool_call:started"] == HookEventType.BEFORE_TOOL

    def test_event_map_ndjson_completed(self) -> None:
        """Maps tool_call:completed to AFTER_TOOL."""
        adapter = CursorAdapter()
        assert adapter.EVENT_MAP["tool_call:completed"] == HookEventType.AFTER_TOOL

    def test_event_map_standard_hooks(self) -> None:
        """Has fallback mappings for standard hook names."""
        adapter = CursorAdapter()
        assert adapter.EVENT_MAP["session-start"] == HookEventType.SESSION_START
        assert adapter.EVENT_MAP["pre-tool-use"] == HookEventType.BEFORE_TOOL

    def test_translate_ndjson_format(self) -> None:
        """Translates NDJSON tool_call format."""
        adapter = CursorAdapter()
        native_event = {
            "type": "tool_call",
            "subtype": "started",
            "call_id": "abc123",
            "tool_call": {
                "name": "read_file",
                "arguments": {"path": "/file.py"},
            },
        }
        hook_event = adapter.translate_to_hook_event(native_event)
        assert hook_event.event_type == HookEventType.BEFORE_TOOL
        assert hook_event.data["tool_name"] == "Read"
        assert hook_event.data["tool_input"] == {"path": "/file.py"}

    def test_translate_ndjson_completed(self) -> None:
        """Translates NDJSON completed event with result."""
        adapter = CursorAdapter()
        native_event = {
            "type": "tool_call",
            "subtype": "completed",
            "call_id": "abc123",
            "tool_call": {
                "name": "read_file",
                "arguments": {"path": "/file.py"},
                "result": "file contents",
            },
        }
        hook_event = adapter.translate_to_hook_event(native_event)
        assert hook_event.event_type == HookEventType.AFTER_TOOL
        assert hook_event.data["tool_output"] == "file contents"

    def test_translate_standard_format(self) -> None:
        """Also handles standard hook format (for future compatibility)."""
        adapter = CursorAdapter()
        native_event = {
            "hook_type": "pre-tool-use",
            "input_data": {
                "session_id": "test-session",
                "tool_name": "Read",
            },
        }
        hook_event = adapter.translate_to_hook_event(native_event)
        assert hook_event.event_type == HookEventType.BEFORE_TOOL
        assert hook_event.session_id == "test-session"

    def test_response_minimal_format(self) -> None:
        """Response uses minimal allow/reason format."""
        adapter = CursorAdapter()
        response = HookResponse(decision="allow")
        result = adapter.translate_from_hook_response(response)
        assert result["allow"] is True

    def test_response_deny(self) -> None:
        """Response allow=False for deny decision."""
        adapter = CursorAdapter()
        response = HookResponse(decision="deny", reason="Blocked")
        result = adapter.translate_from_hook_response(response)
        assert result["allow"] is False
        assert result["reason"] == "Blocked"

    def test_tool_map_normalization(self) -> None:
        """TOOL_MAP normalizes Cursor tool names."""
        adapter = CursorAdapter()
        assert adapter.TOOL_MAP["read_file"] == "Read"
        assert adapter.TOOL_MAP["write_file"] == "Write"
        assert adapter.TOOL_MAP["run_command"] == "Bash"


# =============================================================================
# Integration / Round-trip Tests
# =============================================================================


class TestAdapterRoundTrips:
    """Test full translation round-trips for all adapters."""

    def test_copilot_round_trip(self) -> None:
        """CopilotAdapter translates event and response correctly."""
        adapter = CopilotAdapter()

        # Input event
        native_event = {
            "hook_type": "preToolUse",
            "input_data": {
                "session_id": "copilot-session-123",
                "cwd": "/projects/myapp",
                "toolName": "Read",
                "toolArgs": {"path": "/src/main.py"},
            },
        }

        # Translate to HookEvent
        hook_event = adapter.translate_to_hook_event(native_event)
        assert hook_event.event_type == HookEventType.BEFORE_TOOL
        assert hook_event.source == SessionSource.COPILOT
        assert hook_event.session_id == "copilot-session-123"
        assert hook_event.data["tool_name"] == "Read"

        # Translate response back
        response = HookResponse(decision="allow", context="Approved by workflow")
        result = adapter.translate_from_hook_response(response, hook_type="preToolUse")
        assert result["permissionDecision"] == "allow"
        assert "hookSpecificOutput" in result

    def test_windsurf_round_trip(self) -> None:
        """WindsurfAdapter translates event and response correctly."""
        adapter = WindsurfAdapter()

        # Input event
        native_event = {
            "hook_type": "post_write_code",
            "input_data": {
                "session_id": "windsurf-session-456",
                "cwd": "/projects/cascade",
                "tool_info": {
                    "file_path": "/src/app.ts",
                    "edits": [{"old_string": "const", "new_string": "let"}],
                },
            },
        }

        # Translate to HookEvent
        hook_event = adapter.translate_to_hook_event(native_event)
        assert hook_event.event_type == HookEventType.AFTER_TOOL
        assert hook_event.source == SessionSource.WINDSURF
        assert hook_event.session_id == "windsurf-session-456"
        assert hook_event.data["tool_name"] == "Write"

        # Translate response back
        response = HookResponse(decision="allow", context="Edit recorded")
        result = adapter.translate_from_hook_response(response)
        assert result["decision"] == "allow"
        assert "Edit recorded" in result["context"]

    def test_cursor_round_trip(self) -> None:
        """CursorAdapter translates NDJSON event and response."""
        adapter = CursorAdapter()

        # Input event (NDJSON format)
        native_event = {
            "type": "tool_call",
            "subtype": "started",
            "call_id": "cursor-call-789",
            "tool_call": {
                "name": "shell",
                "arguments": {"command": "npm test"},
            },
        }

        # Translate to HookEvent
        hook_event = adapter.translate_to_hook_event(native_event)
        assert hook_event.event_type == HookEventType.BEFORE_TOOL
        assert hook_event.source == SessionSource.CURSOR
        assert hook_event.data["tool_name"] == "Bash"

        # Translate response back
        response = HookResponse(decision="allow")
        result = adapter.translate_from_hook_response(response)
        assert result["allow"] is True
