"""Tool blocking helpers for workflow engine.

Provides discovery-tool checks and schema-unlock tracking used by the
rule engine's blocking conditions.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# MCP discovery tools that don't require prior schema lookup
DISCOVERY_TOOLS = {
    "list_mcp_servers",
    "list_tools",
    "get_tool_schema",
    "search_tools",
    "recommend_tools",
    "list_skills",
    "get_skill",
    "search_skills",
}


MESSAGE_DELIVERY_TOOLS = {"deliver_pending_messages"}


def is_message_delivery_tool(tool_name: str | None) -> bool:
    """Check if the tool is a message delivery tool.

    These tools are excluded from the notify-unread-mail context injection
    so agents aren't nudged while already reading their mail.

    Args:
        tool_name: The MCP tool name (from event.data.mcp_tool)

    Returns:
        True if this is a message delivery tool
    """
    return tool_name in MESSAGE_DELIVERY_TOOLS if tool_name else False


def is_discovery_tool(tool_name: str | None) -> bool:
    """Check if the tool is a discovery/introspection tool.

    These tools are allowed without prior schema lookup since they ARE
    the discovery mechanism.

    Args:
        tool_name: The MCP tool name (from tool_input.tool_name)

    Returns:
        True if this is a discovery tool that doesn't need schema unlock
    """
    return tool_name in DISCOVERY_TOOLS if tool_name else False


def is_tool_unlocked(
    tool_input: dict[str, Any],
    variables: dict[str, Any],
) -> bool:
    """Check if a tool has been unlocked via prior get_tool_schema call.

    Args:
        tool_input: The tool input containing server_name and tool_name
        variables: Workflow state variables containing unlocked_tools list

    Returns:
        True if the server:tool combo was previously unlocked via get_tool_schema
    """
    # Support 'server' alias for 'server_name' and 'tool' alias for 'tool_name'
    server = tool_input.get("server_name") or tool_input.get("server") or ""
    tool = tool_input.get("tool_name") or tool_input.get("tool") or ""

    if not server or not tool:
        # Don't log here as it might be called speculatively
        return False

    key = f"{server}:{tool}"
    unlocked = variables.get("unlocked_tools", [])

    is_unlocked = key in unlocked
    if not is_unlocked:
        logger.debug(f"is_tool_unlocked check failed for {key}. Unlocked tools: {unlocked}")

    return is_unlocked


def is_server_listed(
    tool_input: dict[str, Any],
    variables: dict[str, Any],
) -> bool:
    """Check if list_tools has been called for this server.

    Args:
        tool_input: The tool input containing server_name or server
        variables: Workflow state variables containing listed_servers list

    Returns:
        True if the server was previously listed via list_tools
    """
    server = tool_input.get("server_name") or tool_input.get("server") or ""
    if not server:
        return False
    return server in variables.get("listed_servers", [])


# Plan file directories that are exempt from task-before-edit enforcement.
# .gobby/plans/ is universal; ~/.claude/plans/ is Claude Code specific.
_PLAN_DIR_SEGMENTS = (
    f"{os.sep}.gobby{os.sep}plans{os.sep}",
    f"{os.sep}.claude{os.sep}plans{os.sep}",
)


def is_plan_file(file_path: str, source: str | None = None) -> bool:
    """Check if a file is a plan file that may be edited without a task.

    Plan files live in ``.gobby/plans/`` (any adapter) or
    ``~/.claude/plans/`` (Claude Code).  Only ``.md`` files in those
    directories qualify.

    Args:
        file_path: Absolute or relative path to the file being edited.
        source: Adapter source (e.g. ``"claude_code"``).  Currently unused
            but accepted for forward-compatibility with the rule signature.

    Returns:
        True if *file_path* is a recognised plan file.
    """
    if not file_path:
        return False

    # Normalise so segment matching works on any platform
    normalised = os.path.normpath(file_path)

    if not normalised.endswith(".md"):
        return False

    # Append a trailing separator so the segment search can match the
    # directory itself when the file sits directly inside it.
    check = normalised + os.sep
    return any(seg in check for seg in _PLAN_DIR_SEGMENTS)
