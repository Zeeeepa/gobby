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

from datetime import UTC
from typing import TYPE_CHECKING, Any

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
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

        @registry.tool(
            name="get_session_commits",
            description="Get git commits made during a session timeframe.",
        )
        def get_session_commits(
            session_id: str,
            max_commits: int = 20,
        ) -> dict[str, Any]:
            """
            Get git commits made during a session's active timeframe.

            Uses session.created_at and session.updated_at to filter
            git log within that timeframe.

            Args:
                session_id: Session ID
                max_commits: Maximum commits to return (default 20)

            Returns:
                Session ID, list of commits, and count
            """
            import subprocess  # nosec B404 - subprocess needed for git commands
            from datetime import datetime
            from pathlib import Path

            if session_manager is None:
                return {"error": "Session manager not available"}

            # Get session
            session = session_manager.get(session_id)
            if not session:
                # Try prefix match
                sessions = session_manager.list(limit=100)
                matches = [s for s in sessions if s.id.startswith(session_id)]
                if len(matches) == 1:
                    session = matches[0]
                elif len(matches) > 1:
                    return {
                        "error": f"Ambiguous session ID prefix '{session_id}'",
                        "matches": [s.id for s in matches[:5]],
                    }
                else:
                    return {"error": f"Session {session_id} not found"}

            # Get working directory from transcript path or project
            cwd = None
            if session.jsonl_path:
                cwd = str(Path(session.jsonl_path).parent)

            # Format timestamps for git --since/--until
            # Git expects ISO format or relative dates
            # Session timestamps may be ISO strings or datetime objects
            if isinstance(session.created_at, str):
                since_time = datetime.fromisoformat(session.created_at.replace("Z", "+00:00"))
            else:
                since_time = session.created_at

            if session.updated_at:
                if isinstance(session.updated_at, str):
                    until_time = datetime.fromisoformat(session.updated_at.replace("Z", "+00:00"))
                else:
                    until_time = session.updated_at
            else:
                until_time = datetime.now(UTC)

            # Format as ISO 8601 for git
            since_str = since_time.strftime("%Y-%m-%dT%H:%M:%S")
            until_str = until_time.strftime("%Y-%m-%dT%H:%M:%S")

            try:
                # Get commits within timeframe
                cmd = [
                    "git",
                    "log",
                    f"--since={since_str}",
                    f"--until={until_str}",
                    f"-{max_commits}",
                    "--format=%H|%s|%aI",  # hash|subject|author-date-iso
                ]

                result = subprocess.run(  # nosec B603 - cmd built from hardcoded git arguments
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=10,
                    cwd=cwd,
                )

                if result.returncode != 0:
                    return {
                        "session_id": session.id,
                        "error": "Git command failed",
                        "stderr": result.stderr.strip(),
                    }

                commits = []
                for line in result.stdout.strip().split("\n"):
                    if "|" in line:
                        parts = line.split("|", 2)
                        if len(parts) >= 2:
                            commit = {
                                "hash": parts[0],
                                "message": parts[1],
                            }
                            if len(parts) >= 3:
                                commit["timestamp"] = parts[2]
                            commits.append(commit)

                return {
                    "session_id": session.id,
                    "commits": commits,
                    "count": len(commits),
                    "timeframe": {
                        "since": since_str,
                        "until": until_str,
                    },
                }

            except subprocess.TimeoutExpired:
                return {
                    "session_id": session.id,
                    "error": "Git command timed out",
                }
            except FileNotFoundError:
                return {
                    "session_id": session.id,
                    "error": "Git not found or not a git repository",
                }
            except Exception as e:
                return {
                    "session_id": session.id,
                    "error": f"Failed to get commits: {e!s}",
                }

        @registry.tool(
            name="mark_loop_complete",
            description="""Mark the autonomous loop as complete, preventing session chaining.

Args:
    session_id: (REQUIRED) Your session ID. Get it from:
        1. Your injected context (look for 'session_id: xxx')
        2. Or call get_current(external_id, source) first""",
        )
        def mark_loop_complete(session_id: str) -> dict[str, Any]:
            """
            Mark the autonomous loop as complete for a session.

            This sets stop_reason='completed' in the workflow state, which
            signals the auto-loop workflow to NOT chain a new session
            when this session ends.

            Use this when:
            - A task is fully complete and no more work is needed
            - You want to exit the autonomous loop gracefully
            - The user has explicitly asked to stop

            Args:
                session_id: Session ID (REQUIRED)

            Returns:
                Success status and session details
            """
            assert session_manager, "Session manager not available"  # nosec B101

            # Find session - session_id is now required
            session = session_manager.get(session_id)

            if not session:
                return {"error": f"Session {session_id} not found", "session_id": session_id}

            # Load and update workflow state
            from gobby.storage.database import LocalDatabase
            from gobby.workflows.definitions import WorkflowState
            from gobby.workflows.state_manager import WorkflowStateManager

            db = LocalDatabase()
            state_manager = WorkflowStateManager(db)

            # Get or create state for session
            state = state_manager.get_state(session.id)
            if not state:
                # Create minimal state just to hold the variable
                state = WorkflowState(
                    session_id=session.id,
                    workflow_name="auto-loop",
                    step="active",
                )

            # Mark loop complete using the action function
            from gobby.workflows.state_actions import mark_loop_complete as action_mark_complete

            action_mark_complete(state)

            # Save updated state
            state_manager.save_state(state)

            return {
                "success": True,
                "session_id": session.id,
                "stop_reason": "completed",
                "message": "Autonomous loop marked complete - session will not chain",
            }

    return registry
