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
    from gobby.sessions.analyzer import HandoffContext
    from gobby.storage.session_messages import LocalSessionMessageManager
    from gobby.storage.sessions import LocalSessionManager


def _format_handoff_markdown(ctx: "HandoffContext", notes: str | None = None) -> str:
    """
    Format HandoffContext as markdown for session handoff.

    Args:
        ctx: HandoffContext with extracted session data
        notes: Optional additional notes to include

    Returns:
        Formatted markdown string
    """
    sections: list[str] = ["## Continuation Context", ""]

    # Active task section
    if ctx.active_gobby_task:
        task = ctx.active_gobby_task
        sections.append("### Active Task")
        sections.append(
            f"**{task.get('title', 'Untitled')}** ({task.get('id', 'unknown')})"
        )
        sections.append(f"Status: {task.get('status', 'unknown')}")
        sections.append("")

    # Todo state section
    if ctx.todo_state:
        sections.append("### In-Progress Work")
        for todo in ctx.todo_state:
            status = todo.get("status", "pending")
            marker = "x" if status == "completed" else ">" if status == "in_progress" else " "
            sections.append(f"- [{marker}] {todo.get('content', '')}")
        sections.append("")

    # Git commits section
    if ctx.git_commits:
        sections.append("### Commits This Session")
        for commit in ctx.git_commits:
            sections.append(f"- `{commit.get('hash', '')[:7]}` {commit.get('message', '')}")
        sections.append("")

    # Git status section
    if ctx.git_status:
        sections.append("### Uncommitted Changes")
        sections.append("```")
        sections.append(ctx.git_status)
        sections.append("```")
        sections.append("")

    # Files modified section
    if ctx.files_modified:
        sections.append("### Files Being Modified")
        for f in ctx.files_modified:
            sections.append(f"- {f}")
        sections.append("")

    # Initial goal section
    if ctx.initial_goal:
        sections.append("### Original Goal")
        sections.append(ctx.initial_goal)
        sections.append("")

    # Recent activity section
    if ctx.recent_activity:
        sections.append("### Recent Activity")
        for activity in ctx.recent_activity[-5:]:
            sections.append(f"- {activity}")
        sections.append("")

    # Notes section (if provided)
    if notes:
        sections.append("### Notes")
        sections.append(notes)
        sections.append("")

    return "\n".join(sections)


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

    # --- Handoff Tools ---
    # Only register if session_manager is available

    if session_manager is not None:

        @registry.tool(
            name="get_handoff_context",
            description="Get the handoff context (compact_markdown) for a session.",
        )
        def get_handoff_context(session_id: str) -> dict[str, Any]:
            """
            Retrieve stored handoff context.

            Args:
                session_id: Session ID

            Returns:
                Session ID, compact_markdown, and whether context exists
            """
            if session_manager is None:
                return {"error": "Session manager not available"}

            session = session_manager.get(session_id)
            if not session:
                return {"error": f"Session {session_id} not found", "found": False}

            return {
                "session_id": session_id,
                "compact_markdown": session.compact_markdown,
                "has_context": bool(session.compact_markdown),
            }

        @registry.tool(
            name="create_handoff",
            description="Create handoff context by extracting structured data from the session transcript.",
        )
        async def create_handoff(
            session_id: str | None = None,
            notes: str | None = None,
        ) -> dict[str, Any]:
            """
            Create handoff context for a session.

            Uses TranscriptAnalyzer to extract:
            - Active gobby-task
            - TodoWrite state
            - Files modified
            - Git commits and status
            - Initial goal
            - Recent activity

            Args:
                session_id: Session ID (optional, defaults to current active session)
                notes: Additional notes to include in handoff

            Returns:
                Success status, markdown length, and extracted context summary
            """
            import json
            import re
            import subprocess
            from pathlib import Path

            from gobby.sessions.analyzer import TranscriptAnalyzer

            if session_manager is None:
                return {"error": "Session manager not available"}

            # Find session
            if session_id:
                session = session_manager.get(session_id)
            else:
                # Get most recent active session
                sessions = session_manager.list(status="active", limit=1)
                session = sessions[0] if sessions else None

            if not session:
                return {"error": "No session found", "session_id": session_id}

            # Get transcript path
            transcript_path = session.jsonl_path
            if not transcript_path:
                return {"error": "No transcript path for session", "session_id": session.id}

            path = Path(transcript_path)
            if not path.exists():
                return {"error": "Transcript file not found", "path": transcript_path}

            # Read and parse transcript
            turns = []
            with open(path) as f:
                for line in f:
                    if line.strip():
                        turns.append(json.loads(line))

            # Analyze transcript
            analyzer = TranscriptAnalyzer()
            handoff_ctx = analyzer.extract_handoff_context(turns)

            # Enrich with real-time git status
            if not handoff_ctx.git_status:
                try:
                    result = subprocess.run(
                        ["git", "status", "--short"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                        cwd=path.parent,
                    )
                    handoff_ctx.git_status = result.stdout.strip() if result.returncode == 0 else ""
                except Exception:
                    pass

            # Get recent git commits
            try:
                result = subprocess.run(
                    ["git", "log", "--oneline", "-10", "--format=%H|%s"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    cwd=path.parent,
                )
                if result.returncode == 0:
                    commits = []
                    for line in result.stdout.strip().split("\n"):
                        if "|" in line:
                            hash_val, message = line.split("|", 1)
                            commits.append({"hash": hash_val, "message": message})
                    if commits:
                        handoff_ctx.git_commits = commits
            except Exception:
                pass

            # Format as markdown
            markdown = _format_handoff_markdown(handoff_ctx, notes)

            # Save to session
            session_manager.update_compact_markdown(session.id, markdown)

            return {
                "success": True,
                "session_id": session.id,
                "markdown_length": len(markdown),
                "context_summary": {
                    "has_active_task": bool(handoff_ctx.active_gobby_task),
                    "todo_count": len(handoff_ctx.todo_state),
                    "files_modified_count": len(handoff_ctx.files_modified),
                    "git_commits_count": len(handoff_ctx.git_commits),
                    "has_initial_goal": bool(handoff_ctx.initial_goal),
                },
            }

        @registry.tool(
            name="pickup",
            description="Restore context from a previous session's handoff. For CLIs/IDEs without hooks.",
        )
        def pickup(
            session_id: str | None = None,
            project_id: str | None = None,
            source: str | None = None,
            link_child_session_id: str | None = None,
        ) -> dict[str, Any]:
            """
            Restore context from a previous session's handoff.

            This tool is designed for CLIs and IDEs that don't have a hooks system.
            It finds the most recent handoff-ready session and returns its context
            for injection into a new session.

            Args:
                session_id: Specific session ID to pickup from (optional)
                project_id: Project ID to find parent session in (optional)
                source: Filter by CLI source - claude_code, gemini, codex (optional)
                link_child_session_id: If provided, links this session as a child

            Returns:
                Handoff context markdown and session metadata
            """
            from gobby.utils.machine_id import get_machine_id

            if session_manager is None:
                return {"error": "Session manager not available"}

            parent_session = None

            # Option 1: Direct session_id lookup
            if session_id:
                parent_session = session_manager.get(session_id)
                if not parent_session:
                    # Try prefix match
                    sessions = session_manager.list(limit=100)
                    matches = [s for s in sessions if s.id.startswith(session_id)]
                    if len(matches) == 1:
                        parent_session = matches[0]
                    elif len(matches) > 1:
                        return {
                            "error": f"Ambiguous session ID prefix '{session_id}'",
                            "matches": [s.id for s in matches[:5]],
                        }

            # Option 2: Find parent by project_id and source
            if not parent_session and project_id:
                machine_id = get_machine_id()
                parent_session = session_manager.find_parent(
                    machine_id=machine_id,
                    project_id=project_id,
                    source=source,
                    status="handoff_ready",
                )

            # Option 3: Find most recent handoff_ready session
            if not parent_session:
                sessions = session_manager.list(status="handoff_ready", limit=1)
                parent_session = sessions[0] if sessions else None

            if not parent_session:
                return {
                    "found": False,
                    "message": "No handoff-ready session found",
                    "filters": {
                        "session_id": session_id,
                        "project_id": project_id,
                        "source": source,
                    },
                }

            # Get handoff context (prefer compact_markdown, fall back to summary_markdown)
            context = parent_session.compact_markdown or parent_session.summary_markdown

            if not context:
                return {
                    "found": True,
                    "session_id": parent_session.id,
                    "has_context": False,
                    "message": "Session found but has no handoff context",
                }

            # Optionally link child session
            if link_child_session_id:
                session_manager.update_parent_session_id(
                    link_child_session_id, parent_session.id
                )

            return {
                "found": True,
                "session_id": parent_session.id,
                "has_context": True,
                "context": context,
                "context_type": (
                    "compact_markdown"
                    if parent_session.compact_markdown
                    else "summary_markdown"
                ),
                "parent_title": parent_session.title,
                "parent_status": parent_session.status,
                "linked_child": link_child_session_id,
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
