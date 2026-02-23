"""Shared MCP field normalization for hook events.

Extracts and normalizes MCP server/tool fields from tool call data so rules
can match consistently regardless of whether the event originates from a CLI
adapter or the web chat UI.

Used by:
- ``claude_code.py`` (ClaudeCodeAdapter._normalize_event_data)
- ``chat.py`` (ChatMixin._fire_lifecycle)
"""

from typing import Any


def normalize_mcp_fields(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize MCP-related fields in hook event data.

    Enriches *data* with ``mcp_server``, ``mcp_tool``, and ``tool_output``
    so downstream rule matching doesn't need to handle adapter-specific
    naming conventions.

    Normalizations performed:

    1a. ``mcp__<server>__<tool>`` prefix → ``mcp_server`` / ``mcp_tool``
    1b. For ``call_tool`` / ``mcp__gobby__call_tool``, extract inner
        ``server_name`` / ``tool_name`` from ``tool_input`` (with override
        logic when the ``mcp__`` prefix is present).
    2.  Normalize both ``tool_result`` and ``tool_response`` → ``tool_output``
        (CLI uses ``tool_result``; chat SDK uses ``tool_response``).

    Args:
        data: Event data dict (mutated in place for efficiency, caller
              should pass a copy if the original must be preserved).

    Returns:
        The same *data* dict, enriched with normalized fields.
    """
    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {}) or {}

    # 1a. Parse mcp__<server>__<tool> prefix for ALL native MCP calls
    if tool_name.startswith("mcp__") and "mcp_tool" not in data:
        parts = tool_name.split("__", 2)  # ["mcp", "server", "tool"]
        if len(parts) == 3:
            data.setdefault("mcp_server", parts[1])
            data.setdefault("mcp_tool", parts[2])

    # 1b. Extract MCP info from nested tool_input for call_tool calls
    if tool_name in ("call_tool", "mcp__gobby__call_tool"):
        inner_server = tool_input.get("server_name")
        inner_tool = tool_input.get("tool_name")
        if tool_name.startswith("mcp__"):
            # Override prefix-parsed values with actual inner target
            if inner_server:
                data["mcp_server"] = inner_server
            if inner_tool:
                data["mcp_tool"] = inner_tool
        else:
            # Plain call_tool — don't overwrite externally-set values
            if inner_server and "mcp_server" not in data:
                data["mcp_server"] = inner_server
            if inner_tool and "mcp_tool" not in data:
                data["mcp_tool"] = inner_tool

    # 2. Normalize tool_result → tool_output (CLI path)
    if "tool_result" in data and "tool_output" not in data:
        data["tool_output"] = data["tool_result"]

    # 2b. Normalize tool_response → tool_output (chat SDK path)
    if "tool_response" in data and "tool_output" not in data:
        data["tool_output"] = data["tool_response"]

    return data
