"""
Internal MCP tools for Gobby Session System.

Exposes functionality for:
- Session CRUD Operations
- Session Message Retrieval
- Message Search (FTS)
- Handoff Context Management

These tools are registered with the InternalToolRegistry and accessed
via the downstream proxy pattern (call_tool, list_tools, get_tool_schema).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.mcp_proxy.tools.sessions._commits import register_commits_tools
from gobby.mcp_proxy.tools.sessions._crud import register_crud_tools
from gobby.mcp_proxy.tools.sessions._handoff import (
    _format_handoff_markdown,
    _format_turns_for_llm,
    register_handoff_tools,
)
from gobby.mcp_proxy.tools.sessions._messages import register_message_tools

if TYPE_CHECKING:
    from gobby.storage.session_messages import LocalSessionMessageManager
    from gobby.storage.sessions import LocalSessionManager


# Re-export for backward compatibility
__all__ = ["create_session_messages_registry", "_format_handoff_markdown", "_format_turns_for_llm"]


def create_session_messages_registry(
    message_manager: LocalSessionMessageManager | None = None,
    session_manager: LocalSessionManager | None = None,
) -> InternalToolRegistry:
    """
    Create a sessions tool registry with session and message tools.

    Args:
        message_manager: LocalSessionMessageManager instance for message operations
        session_manager: LocalSessionManager instance for session CRUD

    Returns:
        InternalToolRegistry with all session tools registered
    """
    registry = InternalToolRegistry(
        name="gobby-sessions",
        description="Session management and message querying - CRUD, retrieval, search",
    )

    # --- Message Tools ---
    # Only register if message_manager is available
    if message_manager is not None:
        register_message_tools(registry, message_manager)

    # --- Handoff Tools ---
    # Only register if session_manager is available
    if session_manager is not None:
        register_handoff_tools(registry, session_manager)

    # --- Session CRUD Tools ---
    # Only register if session_manager is available
    if session_manager is not None:
        register_crud_tools(registry, session_manager)

    # --- Commits Tools ---
    # Only register if session_manager is available
    if session_manager is not None:
        register_commits_tools(registry, session_manager)

    return registry
