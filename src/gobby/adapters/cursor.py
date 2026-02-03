"""Cursor adapter for hook translation.

This adapter translates between Cursor's native hook format and the unified
HookEvent/HookResponse models.

Cursor Hook Types (17 total):
- sessionStart, sessionEnd: Session lifecycle
- beforeSubmitPrompt: Before user prompt validation
- preToolUse, postToolUse, postToolUseFailure: Generic tool lifecycle
- beforeShellExecution, afterShellExecution: Shell-specific hooks
- beforeMCPExecution, afterMCPExecution: MCP tool hooks
- beforeReadFile, afterFileEdit: File operation hooks
- preCompact: Context compaction
- stop: Agent stops
- subagentStart, subagentStop: Subagent lifecycle
- beforeTabFileRead, afterTabFileEdit: Tab completion hooks

Cursor Config Format (.cursor/hooks.json):
{
    "version": 1,
    "hooks": {
        "preToolUse": [{"command": "./script.sh", "matcher": {...}}],
        ...
    }
}

Key Differences from Claude Code:
- Uses camelCase event names (not kebab-case)
- Response uses decision: "allow"/"deny" (not "approve"/"block")
- Has more granular file/shell/MCP hooks
- Config requires "version": 1 field
- Loads Claude Code hooks from .claude/settings.json as fallback

Documentation: https://cursor.com/docs/agent/hooks
"""

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from gobby.adapters.base import BaseAdapter
from gobby.hooks.events import HookEvent, HookEventType, HookResponse, SessionSource

if TYPE_CHECKING:
    from gobby.hooks.hook_manager import HookManager


class CursorAdapter(BaseAdapter):
    """Adapter for Cursor CLI hook translation.

    This adapter:
    1. Translates Cursor's camelCase hook payloads to unified HookEvent
    2. Translates HookResponse back to Cursor's expected format
    3. Calls HookManager.handle() with unified HookEvent model

    Cursor's hooks system is very similar to Claude Code but uses camelCase
    event names and has additional granular hooks for file/shell/MCP operations.
    """

    source = SessionSource.CURSOR

    # Event type mapping: Cursor hook names -> unified HookEventType
    # Cursor uses camelCase hook names in the payload's "hook_type" field
    EVENT_MAP: dict[str, HookEventType] = {
        # Session lifecycle
        "sessionStart": HookEventType.SESSION_START,
        "sessionEnd": HookEventType.SESSION_END,
        # Prompt submission
        "beforeSubmitPrompt": HookEventType.BEFORE_AGENT,
        # Generic tool hooks
        "preToolUse": HookEventType.BEFORE_TOOL,
        "postToolUse": HookEventType.AFTER_TOOL,
        "postToolUseFailure": HookEventType.AFTER_TOOL,  # Same as AFTER_TOOL with error flag
        # Shell-specific hooks (map to generic BEFORE/AFTER_TOOL with tool_type)
        "beforeShellExecution": HookEventType.BEFORE_TOOL,
        "afterShellExecution": HookEventType.AFTER_TOOL,
        # MCP-specific hooks
        "beforeMCPExecution": HookEventType.BEFORE_TOOL,
        "afterMCPExecution": HookEventType.AFTER_TOOL,
        # File-specific hooks
        "beforeReadFile": HookEventType.BEFORE_TOOL,
        "afterFileEdit": HookEventType.AFTER_TOOL,
        # Compaction and stop
        "preCompact": HookEventType.PRE_COMPACT,
        "stop": HookEventType.STOP,
        # Subagent lifecycle
        "subagentStart": HookEventType.SUBAGENT_START,
        "subagentStop": HookEventType.SUBAGENT_STOP,
        # Tab completion hooks (treated as tool events)
        "beforeTabFileRead": HookEventType.BEFORE_TOOL,
        "afterTabFileEdit": HookEventType.AFTER_TOOL,
        # Response hooks (informational)
        "afterAgentResponse": HookEventType.NOTIFICATION,
        "afterAgentThought": HookEventType.NOTIFICATION,
    }

    # Map Cursor-specific hook types to their tool_type
    # This helps downstream code identify what kind of tool is being used
    HOOK_TO_TOOL_TYPE: dict[str, str] = {
        "beforeShellExecution": "Bash",
        "afterShellExecution": "Bash",
        "beforeMCPExecution": "mcp_call",
        "afterMCPExecution": "mcp_call",
        "beforeReadFile": "Read",
        "afterFileEdit": "Edit",
        "beforeTabFileRead": "Read",
        "afterTabFileEdit": "Edit",
    }

    def __init__(self, hook_manager: "HookManager | None" = None):
        """Initialize the Cursor adapter.

        Args:
            hook_manager: Reference to HookManager for delegation.
                         If None, the adapter can only translate (not handle events).
        """
        self._hook_manager = hook_manager

    def translate_to_hook_event(self, native_event: dict[str, Any]) -> HookEvent:
        """Convert Cursor native event to unified HookEvent.

        Cursor payloads have the structure:
        {
            "hook_type": "preToolUse",  # camelCase hook name
            "input_data": {
                "session_id": "abc123",
                "tool_name": "Shell",
                "tool_input": {"command": "npm install"},
                "tool_use_id": "xyz789",
                "cwd": "/path/to/project",
                "model": "claude-sonnet-4-20250514",
                "agent_message": "Installing dependencies..."
            }
        }

        Args:
            native_event: Raw payload from Cursor's hook dispatcher

        Returns:
            Unified HookEvent with normalized fields.
        """
        hook_type = native_event.get("hook_type", "")
        input_data = native_event.get("input_data", {})

        # Map Cursor hook type to unified event type
        # Fall back to NOTIFICATION for unknown types (fail-open)
        event_type = self.EVENT_MAP.get(hook_type, HookEventType.NOTIFICATION)

        # Extract session_id
        session_id = input_data.get("session_id", "")

        # Check for failure flag in postToolUseFailure
        is_failure = hook_type == "postToolUseFailure"
        metadata: dict[str, Any] = {"is_failure": is_failure} if is_failure else {}

        # Add tool_type for specific hooks
        if hook_type in self.HOOK_TO_TOOL_TYPE:
            metadata["tool_type"] = self.HOOK_TO_TOOL_TYPE[hook_type]

        # Normalize event data for CLI-agnostic processing
        normalized_data = self._normalize_event_data(input_data, hook_type)

        return HookEvent(
            event_type=event_type,
            session_id=session_id,
            source=self.source,
            timestamp=datetime.now(UTC),
            machine_id=input_data.get("machine_id"),
            cwd=input_data.get("cwd"),
            data=normalized_data,
            metadata=metadata,
        )

    def _normalize_event_data(
        self, input_data: dict[str, Any], hook_type: str = ""
    ) -> dict[str, Any]:
        """Normalize Cursor event data for CLI-agnostic processing.

        This method enriches the input_data with normalized fields so downstream
        code doesn't need to handle Cursor-specific formats.

        Normalizations performed:
        1. tool_input.server_name/tool_name → mcp_server/mcp_tool (for MCP calls)
        2. Infer tool_name from hook_type for specific hooks

        Args:
            input_data: Raw input data from Cursor
            hook_type: The hook type (used to infer tool_name for specific hooks)

        Returns:
            Enriched data dict with normalized fields added
        """
        # Start with a copy to avoid mutating original
        data = dict(input_data)

        # Get tool info
        tool_name = data.get("tool_name", "")
        tool_input = data.get("tool_input", {}) or {}

        # Infer tool_name from hook type for specific hooks
        if not tool_name and hook_type in self.HOOK_TO_TOOL_TYPE:
            data["tool_name"] = self.HOOK_TO_TOOL_TYPE[hook_type]

        # Extract MCP info from nested tool_input for MCP calls
        if hook_type in ("beforeMCPExecution", "afterMCPExecution") or tool_name in (
            "call_tool",
            "mcp__gobby__call_tool",
        ):
            if "mcp_server" not in data:
                data["mcp_server"] = tool_input.get("server_name")
            if "mcp_tool" not in data:
                data["mcp_tool"] = tool_input.get("tool_name")

        # Normalize tool_result → tool_output
        if "tool_result" in data and "tool_output" not in data:
            data["tool_output"] = data["tool_result"]

        return data

    # Map Cursor hook types to hookEventName for hookSpecificOutput
    HOOK_EVENT_NAME_MAP: dict[str, str] = {
        "sessionStart": "SessionStart",
        "sessionEnd": "SessionEnd",
        "beforeSubmitPrompt": "UserPromptSubmit",
        "preToolUse": "PreToolUse",
        "postToolUse": "PostToolUse",
        "postToolUseFailure": "PostToolUse",
        "beforeShellExecution": "PreToolUse",
        "afterShellExecution": "PostToolUse",
        "beforeMCPExecution": "PreToolUse",
        "afterMCPExecution": "PostToolUse",
        "beforeReadFile": "PreToolUse",
        "afterFileEdit": "PostToolUse",
        "preCompact": "PreCompact",
        "stop": "Stop",
        "subagentStart": "SubagentStart",
        "subagentStop": "SubagentStop",
        "beforeTabFileRead": "PreToolUse",
        "afterTabFileEdit": "PostToolUse",
        "afterAgentResponse": "Notification",
        "afterAgentThought": "Notification",
    }

    def translate_from_hook_response(
        self, response: HookResponse, hook_type: str | None = None
    ) -> dict[str, Any]:
        """Convert HookResponse to Cursor's expected format.

        Cursor expects responses in this format:
        {
            "decision": "allow"/"deny",       # Tool decision
            "reason": "...",                  # Reason if denied (optional)
            "updated_input": {...},           # Modified tool input (optional)
            "user_message": "...",            # Message to show user (optional)
            "agent_message": "...",           # Message to send to model (optional)
            "permission": "allow"/"deny"/"ask",  # For permission hooks
            "followup_message": "...",        # Auto-submit message (for stop hook)
            "env": {...},                     # Environment variables (sessionStart)
            "additional_context": "...",      # Context injection (sessionStart)
            "continue": true/false            # Whether to continue (sessionStart)
        }

        Args:
            response: Unified HookResponse from HookManager.
            hook_type: Original Cursor hook type (e.g., "preToolUse")
                      Used to determine response format.

        Returns:
            Dict in Cursor's expected format.
        """
        # Determine response format based on hook type
        hook_type = hook_type or ""

        # Base decision - Cursor uses "allow"/"deny"
        should_allow = response.decision not in ("deny", "block")

        result: dict[str, Any] = {}

        # Permission-based hooks (beforeShellExecution, beforeReadFile, etc.)
        if hook_type in (
            "beforeShellExecution",
            "beforeReadFile",
            "beforeMCPExecution",
        ):
            result["permission"] = "allow" if should_allow else "deny"
            if response.reason:
                result["user_message"] = response.reason
            if response.context:
                result["agent_message"] = response.context

        # Decision hooks (preToolUse, subagentStart)
        elif hook_type in ("preToolUse", "subagentStart"):
            result["decision"] = "allow" if should_allow else "deny"
            if response.reason:
                result["reason"] = response.reason

        # Continuation hooks (stop, subagentStop)
        elif hook_type in ("stop", "subagentStop"):
            if response.context:
                result["followup_message"] = response.context

        # Session hooks (sessionStart)
        elif hook_type == "sessionStart":
            result["continue"] = should_allow
            if response.reason:
                result["user_message"] = response.reason

            # Build additional_context from response context and metadata
            additional_context_parts: list[str] = []
            if response.context:
                additional_context_parts.append(response.context)

            # Add session identifiers from metadata
            if response.metadata:
                gobby_session_id = response.metadata.get("session_id")
                session_ref = response.metadata.get("session_ref")
                external_id = response.metadata.get("external_id")

                if gobby_session_id:
                    context_lines = []
                    if session_ref:
                        context_lines.append(
                            f"Gobby Session ID: {session_ref} (or {gobby_session_id})"
                        )
                    else:
                        context_lines.append(f"Gobby Session ID: {gobby_session_id}")
                    if external_id:
                        context_lines.append(
                            f"CLI-Specific Session ID (external_id): {external_id}"
                        )
                    if response.metadata.get("machine_id"):
                        context_lines.append(f"machine_id: {response.metadata['machine_id']}")
                    if response.metadata.get("project_id"):
                        context_lines.append(f"project_id: {response.metadata['project_id']}")
                    additional_context_parts.append("\n".join(context_lines))

            if additional_context_parts:
                result["additional_context"] = "\n\n".join(additional_context_parts)

        # Default format for other hooks
        else:
            result["decision"] = "allow" if should_allow else "deny"
            if response.reason:
                result["reason"] = response.reason

        # Add context to agent_message for tool hooks if not already set
        if response.context and "agent_message" not in result:
            result["agent_message"] = response.context

        # Add system_message if present
        if response.system_message:
            result["user_message"] = response.system_message

        return result

    def handle_native(
        self, native_event: dict[str, Any], hook_manager: "HookManager"
    ) -> dict[str, Any]:
        """Main entry point for HTTP endpoint.

        Args:
            native_event: Raw payload from Cursor's hook dispatcher
            hook_manager: HookManager instance for processing.

        Returns:
            Response dict in Cursor's expected format.
        """
        # Translate to HookEvent
        hook_event = self.translate_to_hook_event(native_event)

        # Use HookEvent-based handler
        hook_type = native_event.get("hook_type", "")
        hook_response = hook_manager.handle(hook_event)
        return self.translate_from_hook_response(hook_response, hook_type=hook_type)
