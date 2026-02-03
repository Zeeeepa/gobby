"""Cursor adapter for hook translation.

IMPORTANT: Cursor uses a fundamentally different architecture than other CLIs.

Cursor Architecture:
- Uses NDJSON streaming output, NOT hook interception
- Tool calls are streamed as JSON objects with type/subtype markers
- No hook dispatcher or permission system like Claude Code/Copilot

Example Cursor NDJSON output:
```json
{"type":"tool_call","subtype":"started","call_id":"abc123","tool_call":{"name":"Read","arguments":{"path":"/file.py"}}}
{"type":"tool_call","subtype":"completed","call_id":"abc123","tool_call":{"name":"Read","result":"..."}}
{"type":"message","content":"Here's the file content..."}
```

Current Status:
- This adapter is a STUB that provides minimal functionality
- It can track sessions if hook events are somehow forwarded to it
- Full integration would require a stream parser wrapper

Future Integration Options:
1. Stream Parser: Wrap Cursor's output stream and parse NDJSON events
2. Wrapper Script: Use a shell wrapper that intercepts and forwards events
3. Native Support: Wait for Cursor to add hook support

For now, this adapter:
- Reports CURSOR as source for session differentiation
- Provides minimal event mapping for any events that arrive
- Returns pass-through allow responses
"""

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from gobby.adapters.base import BaseAdapter
from gobby.hooks.events import HookEvent, HookEventType, HookResponse, SessionSource

if TYPE_CHECKING:
    from gobby.hooks.hook_manager import HookManager


class CursorAdapter(BaseAdapter):
    """Stub adapter for Cursor CLI.

    Cursor uses NDJSON streaming rather than hook interception, so this adapter
    provides minimal functionality for potential future integration.

    See module docstring for architecture details and integration options.
    """

    source = SessionSource.CURSOR

    # Minimal event mapping for any events that might be forwarded
    # These map Cursor's NDJSON type/subtype patterns to unified events
    EVENT_MAP: dict[str, HookEventType] = {
        # NDJSON type markers (if translated by a wrapper)
        "tool_call:started": HookEventType.BEFORE_TOOL,
        "tool_call:completed": HookEventType.AFTER_TOOL,
        "message": HookEventType.NOTIFICATION,
        "error": HookEventType.NOTIFICATION,
        # Standard hook names (if Cursor adds hook support)
        "session-start": HookEventType.SESSION_START,
        "session-end": HookEventType.SESSION_END,
        "pre-tool-use": HookEventType.BEFORE_TOOL,
        "post-tool-use": HookEventType.AFTER_TOOL,
    }

    # Map NDJSON tool names to normalized names
    TOOL_MAP: dict[str, str] = {
        "read_file": "Read",
        "write_file": "Write",
        "edit_file": "Edit",
        "run_command": "Bash",
        "shell": "Bash",
    }

    def __init__(self, hook_manager: "HookManager | None" = None):
        """Initialize the Cursor adapter.

        Args:
            hook_manager: Reference to HookManager for handling events.
                         If None, the adapter can only translate (not handle events).
        """
        self._hook_manager = hook_manager

    def _normalize_event_data(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Normalize Cursor event data for CLI-agnostic processing.

        Cursor NDJSON has a different structure than hook-based CLIs:
        - tool_call.name -> tool_name
        - tool_call.arguments -> tool_input
        - tool_call.result -> tool_output

        Args:
            input_data: Raw input data (either from NDJSON wrapper or direct)

        Returns:
            Enriched data dict with normalized fields added
        """
        data = dict(input_data)

        # Handle NDJSON tool_call structure
        tool_call = data.get("tool_call", {})
        if tool_call:
            if "tool_name" not in data:
                raw_name = tool_call.get("name", "")
                data["tool_name"] = self.TOOL_MAP.get(raw_name, raw_name)
            if "tool_input" not in data:
                data["tool_input"] = tool_call.get("arguments", {})
            if "tool_output" not in data and "result" in tool_call:
                data["tool_output"] = tool_call["result"]

        return data

    def translate_to_hook_event(self, native_event: dict[str, Any]) -> HookEvent:
        """Convert Cursor native event to unified HookEvent.

        Cursor events could arrive in two formats:
        1. NDJSON format (from stream parser wrapper):
           {"type": "tool_call", "subtype": "started", "call_id": "...", "tool_call": {...}}
        2. Standard hook format (if Cursor adds hook support):
           {"hook_type": "pre-tool-use", "input_data": {...}}

        Args:
            native_event: Raw payload (format depends on integration method)

        Returns:
            Unified HookEvent with normalized fields.
        """
        # Try standard hook format first
        hook_type = native_event.get("hook_type", "")
        input_data = native_event.get("input_data", {})

        # If not standard format, try NDJSON format
        if not hook_type:
            ndjson_type = native_event.get("type", "")
            ndjson_subtype = native_event.get("subtype", "")
            if ndjson_type:
                # Combine type:subtype for event mapping
                hook_type = f"{ndjson_type}:{ndjson_subtype}" if ndjson_subtype else ndjson_type
                input_data = native_event  # NDJSON is flat, not nested

        # Map to unified event type
        event_type = self.EVENT_MAP.get(hook_type, HookEventType.NOTIFICATION)

        # Extract session_id (could be in various places)
        session_id = (
            input_data.get("session_id", "")
            or native_event.get("session_id", "")
            or native_event.get("call_id", "")  # NDJSON uses call_id
        )

        # Normalize event data
        normalized_data = self._normalize_event_data(input_data)

        return HookEvent(
            event_type=event_type,
            session_id=session_id,
            source=self.source,
            timestamp=datetime.now(UTC),
            machine_id=input_data.get("machine_id"),
            cwd=input_data.get("cwd"),
            data=normalized_data,
            metadata={},
        )

    def translate_from_hook_response(
        self, response: HookResponse, hook_type: str | None = None
    ) -> dict[str, Any]:
        """Convert HookResponse to Cursor's expected format.

        Since Cursor doesn't use hooks natively, this returns a minimal response
        that could be used by a wrapper script or future hook support.

        Args:
            response: Unified HookResponse from HookManager.
            hook_type: Original event type (for logging/debugging)

        Returns:
            Minimal response dict.
        """
        # Cursor doesn't have a defined response format for hooks
        # Return a minimal structure that could be parsed by a wrapper
        result: dict[str, Any] = {
            "allow": response.decision not in ("deny", "block"),
        }

        if response.reason:
            result["reason"] = response.reason

        if response.context:
            result["context"] = response.context

        if response.system_message:
            result["message"] = response.system_message

        return result

    def handle_native(
        self, native_event: dict[str, Any], hook_manager: "HookManager"
    ) -> dict[str, Any]:
        """Main entry point for HTTP endpoint.

        Since Cursor uses NDJSON streaming, this method is primarily for:
        1. Testing the adapter
        2. Future hook support if Cursor adds it
        3. Events forwarded by a wrapper script

        Args:
            native_event: Raw payload
            hook_manager: HookManager instance for processing.

        Returns:
            Response dict (minimal format).
        """
        hook_event = self.translate_to_hook_event(native_event)
        hook_type = native_event.get("hook_type") or native_event.get("type", "")
        hook_response = hook_manager.handle(hook_event)
        return self.translate_from_hook_response(hook_response, hook_type=hook_type)
