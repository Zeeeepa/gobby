"""Message retrieval and search tools for session management.

This module contains MCP tools for:
- Getting messages for a session (get_session_messages)
- Searching messages using FTS (search_messages)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gobby.mcp_proxy.tools.internal import InternalToolRegistry
    from gobby.storage.session_messages import LocalSessionMessageManager
    from gobby.storage.sessions import LocalSessionManager


def register_message_tools(
    registry: InternalToolRegistry,
    message_manager: LocalSessionMessageManager,
    session_manager: LocalSessionManager | None = None,
) -> None:
    """
    Register message retrieval and search tools with a registry.

    Args:
        registry: The InternalToolRegistry to register tools with
        message_manager: LocalSessionMessageManager instance for message operations
        session_manager: LocalSessionManager for resolving session references
    """

    def _resolve_session_id(session_id: str) -> str:
        """Resolve session reference (#N, N, UUID, or prefix) to UUID.

        Returns:
            str: Resolved UUID on success

        Raises:
            ValueError: If session reference cannot be resolved (when session_manager exists)
        """
        if not session_manager:
            return session_id  # Fall back to raw value if no manager (backward compat)

        from gobby.utils.project_context import get_project_context

        project_ctx = get_project_context()
        project_id = project_ctx.get("id") if project_ctx else None

        return session_manager.resolve_session_reference(session_id, project_id)

    @registry.tool(
        name="get_session_messages",
        description="Get messages for a session. Accepts #N, N, UUID, or prefix for session_id.",
    )
    async def get_session_messages(
        session_id: str,
        limit: int = 50,
        offset: int = 0,
        full_content: bool = False,
    ) -> dict[str, Any]:
        """
        Get messages for a session.

        Args:
            session_id: Session reference - supports #N, N (seq_num), UUID, or prefix
            limit: Max messages to return
            offset: Offset for pagination
            full_content: If True, returns full content. If False (default), truncates large content.
        """
        try:
            if not message_manager:
                raise RuntimeError("Message manager not available")

            resolved_id = _resolve_session_id(session_id)
            messages = await message_manager.get_messages(
                session_id=resolved_id,
                limit=limit,
                offset=offset,
            )

            # Truncate content if not full_content
            if not full_content:
                for msg in messages:
                    if "content" in msg and msg["content"] and isinstance(msg["content"], str):
                        if len(msg["content"]) > 500:
                            msg["content"] = msg["content"][:500] + "... (truncated)"

                    if "tool_calls" in msg and msg["tool_calls"]:
                        for tc in msg["tool_calls"]:
                            if (
                                "input" in tc
                                and isinstance(tc["input"], str)
                                and len(tc["input"]) > 200
                            ):
                                tc["input"] = tc["input"][:200] + "... (truncated)"

                    if "tool_result" in msg and msg["tool_result"]:
                        tr = msg["tool_result"]
                        if (
                            "content" in tr
                            and isinstance(tr["content"], str)
                            and len(tr["content"]) > 200
                        ):
                            tr["content"] = tr["content"][:200] + "... (truncated)"

            session_total = await message_manager.count_messages(resolved_id)

            return {
                "success": True,
                "messages": messages,
                "total_count": session_total,
                "returned_count": len(messages),
                "limit": limit,
                "offset": offset,
                "truncated": not full_content,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @registry.tool(
        name="search_messages",
        description="Search messages using Full Text Search (FTS). Accepts #N, N, UUID, or prefix for session_id.",
    )
    async def search_messages(
        query: str,
        session_id: str | None = None,
        limit: int = 20,
        full_content: bool = False,
    ) -> dict[str, Any]:
        """
        Search messages.

        Args:
            query: Search query
            session_id: Optional session filter - supports #N, N (seq_num), UUID, or prefix
            limit: Max results
            full_content: If True, returns full content. If False (default), truncates large content.
        """
        try:
            if not message_manager:
                raise RuntimeError("Message manager not available")

            resolved_session_id = None
            if session_id:
                resolved_session_id = _resolve_session_id(session_id)
            results = await message_manager.search_messages(
                query_text=query,
                session_id=resolved_session_id,
                limit=limit,
            )

            # Truncate content if not full_content
            if not full_content:
                for msg in results:
                    if "content" in msg and msg["content"] and isinstance(msg["content"], str):
                        if len(msg["content"]) > 500:
                            msg["content"] = msg["content"][:500] + "... (truncated)"

            return {
                "success": True,
                "results": results,
                "count": len(results),
                "truncated": not full_content,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
