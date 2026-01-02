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

from typing import TYPE_CHECKING, Any

from gobby.mcp_proxy.tools.internal import InternalToolRegistry

if TYPE_CHECKING:
    from gobby.storage.session_messages import LocalSessionMessageManager
    from gobby.storage.sessions import LocalSessionManager


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
            if message_manager is None:
                return {"error": "Message manager not available"}

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
            if message_manager is None:
                return {"error": "Message manager not available"}

            results = await message_manager.search_messages(
                query_text=query, project_id=project_id, limit=limit
            )

            return {
                "query": query,
                "count": len(results),
                "results": results,
            }

    # --- Session CRUD Tools ---
    # Only register if session_manager is available

    if session_manager is not None:

        @registry.tool(
            name="get_session",
            description="Get session details by ID.",
        )
        def get_session(session_id: str) -> dict[str, Any]:
            """
            Get session details.

            Args:
                session_id: Session ID (supports prefix matching)

            Returns:
                Session dict with all fields, or error if not found
            """
            # Support prefix matching like CLI does
            if session_manager is None:
                return {"error": "Session manager not available"}

            session = session_manager.get(session_id)
            if not session:
                # Try prefix match
                sessions = session_manager.list(limit=100)
                matches = [s for s in sessions if s.id.startswith(session_id)]
                if len(matches) == 1:
                    session = matches[0]
                elif len(matches) > 1:
                    return {
                        "error": f"Ambiguous session ID prefix '{session_id}' matches {len(matches)} sessions",
                        "matches": [s.id for s in matches[:5]],
                    }
                else:
                    return {"error": f"Session {session_id} not found", "found": False}

            return {
                "found": True,
                **session.to_dict(),
            }

        @registry.tool(
            name="get_current_session",
            description="Get the current active session for a project.",
        )
        def get_current_session(
            project_id: str | None = None,
        ) -> dict[str, Any]:
            """
            Find the most recent active session for a project.

            Args:
                project_id: Project ID (optional, defaults to current project)

            Returns:
                Session dict or null if no active session
            """
            if session_manager is None:
                return {"error": "Session manager not available"}

            # Find active sessions for project
            sessions = session_manager.list(
                project_id=project_id,
                status="active",
                limit=1,
            )

            if sessions:
                return {
                    "found": True,
                    **sessions[0].to_dict(),
                }

            return {
                "found": False,
                "message": "No active session found",
                "project_id": project_id,
            }

        @registry.tool(
            name="list_sessions",
            description="List sessions with optional filtering.",
        )
        def list_sessions(
            project_id: str | None = None,
            status: str | None = None,
            source: str | None = None,
            limit: int = 20,
        ) -> dict[str, Any]:
            """
            List sessions with filters.

            Args:
                project_id: Filter by project ID
                status: Filter by status (active, paused, expired, archived, handoff_ready)
                source: Filter by CLI source (claude, gemini, codex)
                limit: Max results (default 20)

            Returns:
                List of sessions and count
            """
            if session_manager is None:
                return {"error": "Session manager not available"}

            sessions = session_manager.list(
                project_id=project_id,
                status=status,
                source=source,
                limit=limit,
            )

            total = session_manager.count(
                project_id=project_id,
                status=status,
                source=source,
            )

            return {
                "sessions": [s.to_dict() for s in sessions],
                "count": len(sessions),
                "total": total,
                "limit": limit,
                "filters": {
                    "project_id": project_id,
                    "status": status,
                    "source": source,
                },
            }

        @registry.tool(
            name="session_stats",
            description="Get session statistics for a project.",
        )
        def session_stats(project_id: str | None = None) -> dict[str, Any]:
            """
            Get session statistics.

            Args:
                project_id: Filter by project ID (optional)

            Returns:
                Statistics including total, by_status, by_source
            """
            if session_manager is None:
                return {"error": "Session manager not available"}

            total = session_manager.count(project_id=project_id)
            by_status = session_manager.count_by_status()

            # Count by source
            by_source: dict[str, int] = {}
            for src in ["claude_code", "gemini", "codex"]:
                count = session_manager.count(project_id=project_id, source=src)
                if count > 0:
                    by_source[src] = count

            return {
                "total": total,
                "by_status": by_status,
                "by_source": by_source,
                "project_id": project_id,
            }

    return registry
