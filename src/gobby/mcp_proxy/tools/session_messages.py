"""
Internal MCP tools for Gobby Message System.

Exposes functionality for:
- Session Message Retrieval
- Message Search (FTS)

These tools are registered with the InternalToolRegistry and accessed
via the downstream proxy pattern (call_tool, list_tools, get_tool_schema).
"""

from typing import Any

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.storage.session_messages import LocalSessionMessageManager


def create_session_messages_registry(
    message_manager: LocalSessionMessageManager,
) -> InternalToolRegistry:
    """
    Create a messages tool registry with all message-related tools.

    Args:
        message_manager: LocalSessionMessageManager instance

    Returns:
        InternalToolRegistry with all message tools registered
    """
    registry = InternalToolRegistry(
        name="gobby-sessions",
        description="Session message querying - retrieval, search",
    )

    @registry.tool(
        name="get_session_messages",
        description="Get messages for a specific session.",
    )
    async def get_session_messages(
        session_id: str,
        limit: int = 100,
        offset: int = 0,
        role: str | None = None,
    ) -> dict[str, Any]:
        """
        Get messages for a session.

        Args:
            session_id: Session ID
            limit: Max messages to return (default 100)
            offset: Pagination offset
            role: Filter by role (user, assistant, tool)

        Returns:
            List of messages and total count
        """
        messages = await message_manager.get_messages(
            session_id=session_id, limit=limit, offset=offset, role=role
        )
        session_total = await message_manager.count_messages(session_id)

        result: dict[str, Any] = {
            "session_id": session_id,
            "messages": messages,
            "total_count": session_total,
            "returned_count": len(messages),
            "limit": limit,
            "offset": offset,
        }

        # Add role filter info if filtering was applied
        if role:
            result["role_filter"] = role

        return result

    @registry.tool(
        name="search_messages",
        description="Search messages across all sessions using full-text search.",
    )
    async def search_messages(
        query: str,
        project_id: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """
        Search messages using FTS.

        Args:
            query: Search query
            project_id: Filter by project (optional)
            limit: Max results (default 20)

        Returns:
            List of matching messages with session context
        """
        results = await message_manager.search_messages(
            query_text=query, project_id=project_id, limit=limit
        )

        return {
            "query": query,
            "count": len(results),
            "results": results,
        }

    return registry
