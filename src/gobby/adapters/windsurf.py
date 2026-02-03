"""Windsurf adapter for hook translation.

This adapter translates between Windsurf's Cascade hooks format and the unified
HookEvent/HookResponse models.

Windsurf Cascade Hook Types:
- pre_read_code: Before reading a file
- post_read_code: After reading a file
- post_write_code: After writing/editing a file
- post_run_command: After running a shell command
- post_mcp_tool_use: After using an MCP tool
- post_cascade_response: After agent response

Key differences from Claude Code:
- Uses `agent_action_name` instead of `hook_type`
- Uses nested `tool_info` object for tool details
- Action-specific field names (file_path, edits, command, etc.)
- Different response format
"""

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from gobby.adapters.base import BaseAdapter
from gobby.hooks.events import HookEvent, HookEventType, HookResponse, SessionSource

if TYPE_CHECKING:
    from gobby.hooks.hook_manager import HookManager


class WindsurfAdapter(BaseAdapter):
    """Adapter for Windsurf Cascade hook translation.

    This adapter:
    1. Translates Windsurf's action-based hook payloads to unified HookEvent
    2. Extracts tool details from nested `tool_info` structures
    3. Translates HookResponse back to Windsurf's expected format
    """

    source = SessionSource.WINDSURF

    # Event type mapping: Windsurf action names -> unified HookEventType
    # Windsurf uses agent_action_name field with underscore-separated names
    EVENT_MAP: dict[str, HookEventType] = {
        # Pre-action hooks (before tool execution)
        "pre_read_code": HookEventType.BEFORE_TOOL,
        "pre_write_code": HookEventType.BEFORE_TOOL,
        "pre_run_command": HookEventType.BEFORE_TOOL,
        "pre_mcp_tool_use": HookEventType.BEFORE_TOOL,
        # Post-action hooks (after tool execution)
        "post_read_code": HookEventType.AFTER_TOOL,
        "post_write_code": HookEventType.AFTER_TOOL,
        "post_run_command": HookEventType.AFTER_TOOL,
        "post_mcp_tool_use": HookEventType.AFTER_TOOL,
        # Agent lifecycle
        "post_cascade_response": HookEventType.AFTER_AGENT,
        "pre_cascade_request": HookEventType.BEFORE_AGENT,
        # Session lifecycle
        "session_start": HookEventType.SESSION_START,
        "session_end": HookEventType.SESSION_END,
    }

    # Map action names to normalized tool names
    # This allows workflows to use consistent tool names across CLIs
    TOOL_MAP: dict[str, str] = {
        "pre_read_code": "Read",
        "post_read_code": "Read",
        "pre_write_code": "Write",
        "post_write_code": "Write",
        "pre_run_command": "Bash",
        "post_run_command": "Bash",
        "pre_mcp_tool_use": "mcp_call",
        "post_mcp_tool_use": "mcp_call",
    }

    # Map unified event types back to Windsurf action names for response
    HOOK_EVENT_NAME_MAP: dict[str, str] = {
        "session_start": "SessionStart",
        "session_end": "SessionEnd",
        "before_agent": "PreCascadeRequest",
        "after_agent": "PostCascadeResponse",
        "before_tool": "PreToolUse",
        "after_tool": "PostToolUse",
    }

    def __init__(self, hook_manager: "HookManager | None" = None):
        """Initialize the Windsurf adapter.

        Args:
            hook_manager: Reference to HookManager for handling events.
                         If None, the adapter can only translate (not handle events).
        """
        self._hook_manager = hook_manager

    def _extract_tool_info(self, action_name: str, tool_info: dict[str, Any]) -> dict[str, Any]:
        """Extract and normalize tool information based on action type.

        Different actions have different structures in tool_info:
        - read_code: file_path, content (post only)
        - write_code: file_path, edits[{old_string, new_string}]
        - run_command: command, output (post only), exit_code (post only)
        - mcp_tool_use: server_name, tool_name, arguments, result (post only)

        Args:
            action_name: The Windsurf action name (e.g., "post_write_code")
            tool_info: The nested tool_info dict from the payload

        Returns:
            Normalized dict with tool_name, tool_input, tool_output
        """
        result: dict[str, Any] = {}

        # Get normalized tool name
        result["tool_name"] = self.TOOL_MAP.get(action_name, action_name)

        # Extract action-specific fields
        if "read_code" in action_name:
            # Read file action
            result["tool_input"] = {"file_path": tool_info.get("file_path")}
            if "content" in tool_info:
                result["tool_output"] = tool_info["content"]

        elif "write_code" in action_name:
            # Write/edit file action
            file_path = tool_info.get("file_path")
            edits = tool_info.get("edits", [])
            result["tool_input"] = {
                "file_path": file_path,
                "edits": edits,
            }
            # For post, indicate success
            if action_name.startswith("post_"):
                result["tool_output"] = f"Successfully edited {file_path}"

        elif "run_command" in action_name:
            # Shell command action
            result["tool_input"] = {"command": tool_info.get("command")}
            if "output" in tool_info:
                result["tool_output"] = tool_info["output"]
            if "exit_code" in tool_info:
                result["exit_code"] = tool_info["exit_code"]
                if tool_info["exit_code"] != 0:
                    result["is_error"] = True

        elif "mcp_tool_use" in action_name:
            # MCP tool call
            result["mcp_server"] = tool_info.get("server_name")
            result["mcp_tool"] = tool_info.get("tool_name")
            result["tool_input"] = tool_info.get("arguments", {})
            if "result" in tool_info:
                result["tool_output"] = tool_info["result"]

        return result

    def _normalize_event_data(self, action_name: str, input_data: dict[str, Any]) -> dict[str, Any]:
        """Normalize Windsurf event data for CLI-agnostic processing.

        Windsurf nests tool details in `tool_info` which needs to be flattened
        and normalized for unified processing.

        Args:
            action_name: The Windsurf action name
            input_data: Raw input data from Windsurf

        Returns:
            Enriched data dict with normalized fields added
        """
        # Start with a copy to avoid mutating original
        data = dict(input_data)

        # Extract and normalize tool_info if present
        tool_info = data.get("tool_info", {})
        if tool_info:
            normalized = self._extract_tool_info(action_name, tool_info)
            # Merge normalized fields (don't overwrite existing)
            for key, value in normalized.items():
                if key not in data:
                    data[key] = value

        # Store original action name for reference
        data["original_action"] = action_name

        return data

    def translate_to_hook_event(self, native_event: dict[str, Any]) -> HookEvent:
        """Convert Windsurf native event to unified HookEvent.

        Windsurf payloads have the structure:
        {
            "hook_type": "post_write_code",  # or via agent_action_name
            "input_data": {
                "session_id": "abc123",
                "cwd": "/path/to/project",
                "agent_action_name": "post_write_code",
                "tool_info": {
                    "file_path": "/path/to/file.py",
                    "edits": [{"old_string": "...", "new_string": "..."}]
                }
            }
        }

        Args:
            native_event: Raw payload from Windsurf hook dispatcher

        Returns:
            Unified HookEvent with normalized fields.
        """
        # Get hook type - could be in hook_type or agent_action_name
        hook_type = native_event.get("hook_type", "")
        input_data = native_event.get("input_data", {})

        # Windsurf might use agent_action_name in input_data
        if not hook_type:
            hook_type = input_data.get("agent_action_name", "")

        # Map Windsurf action to unified event type
        # Fall back to NOTIFICATION for unknown types (fail-open)
        event_type = self.EVENT_MAP.get(hook_type, HookEventType.NOTIFICATION)

        # Extract session_id
        session_id = input_data.get("session_id", "")

        # Check for errors
        tool_info = input_data.get("tool_info", {})
        is_error = False
        if isinstance(tool_info, dict):
            exit_code = tool_info.get("exit_code")
            if exit_code is not None and exit_code != 0:
                is_error = True

        metadata = {"is_failure": is_error} if is_error else {}

        # Normalize event data for CLI-agnostic processing
        normalized_data = self._normalize_event_data(hook_type, input_data)

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

    def translate_from_hook_response(
        self, response: HookResponse, hook_type: str | None = None
    ) -> dict[str, Any]:
        """Convert HookResponse to Windsurf's expected format.

        Windsurf expects responses in this format:
        {
            "decision": "allow" | "deny",
            "reason": "...",
            "context": "..."  # Context to inject
        }

        Args:
            response: Unified HookResponse from HookManager.
            hook_type: Original Windsurf action name (e.g., "post_write_code")

        Returns:
            Dict in Windsurf's expected format.
        """
        # Map decision - Windsurf uses allow/deny
        if response.decision in ("deny", "block"):
            decision = "deny"
        else:
            decision = "allow"

        result: dict[str, Any] = {
            "decision": decision,
        }

        # Add reason if present
        if response.reason:
            result["reason"] = response.reason

        # Add system message if present
        if response.system_message:
            result["systemMessage"] = response.system_message

        # Build context for injection
        context_parts: list[str] = []

        # Add workflow-injected context
        if response.context:
            context_parts.append(response.context)

        # Add session identifiers from metadata
        if response.metadata:
            gobby_session_id = response.metadata.get("session_id")
            session_ref = response.metadata.get("session_ref")
            external_id = response.metadata.get("external_id")
            is_first_hook = response.metadata.get("_first_hook_for_session", False)

            if gobby_session_id:
                if is_first_hook:
                    # First hook: inject full metadata
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
                    if response.metadata.get("parent_session_id"):
                        context_lines.append(
                            f"parent_session_id: {response.metadata['parent_session_id']}"
                        )
                    if response.metadata.get("machine_id"):
                        context_lines.append(f"machine_id: {response.metadata['machine_id']}")
                    if response.metadata.get("project_id"):
                        context_lines.append(f"project_id: {response.metadata['project_id']}")
                    context_parts.append("\n".join(context_lines))
                else:
                    # Subsequent hooks: inject minimal session ref only
                    if session_ref:
                        context_parts.append(f"Gobby Session ID: {session_ref}")

        # Add context if we have any
        if context_parts:
            result["context"] = "\n\n".join(context_parts)

        return result

    def handle_native(
        self, native_event: dict[str, Any], hook_manager: "HookManager"
    ) -> dict[str, Any]:
        """Main entry point for HTTP endpoint.

        Translates native Windsurf event, processes through HookManager,
        and returns response in Windsurf's expected format.

        Args:
            native_event: Raw payload from Windsurf hook dispatcher
            hook_manager: HookManager instance for processing.

        Returns:
            Response dict in Windsurf's expected format.
        """
        # Translate to unified HookEvent
        hook_event = self.translate_to_hook_event(native_event)

        # Get original hook type for response formatting
        hook_type = native_event.get("hook_type", "")
        if not hook_type:
            hook_type = native_event.get("input_data", {}).get("agent_action_name", "")

        # Process through HookManager
        hook_response = hook_manager.handle(hook_event)

        # Translate response back to Windsurf format
        return self.translate_from_hook_response(hook_response, hook_type=hook_type)
