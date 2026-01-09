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

if TYPE_CHECKING:
    from gobby.sessions.analyzer import HandoffContext
    from gobby.storage.session_messages import LocalSessionMessageManager
    from gobby.storage.sessions import LocalSessionManager


def _format_handoff_markdown(ctx: HandoffContext, notes: str | None = None) -> str:
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
        sections.append(f"**{task.get('title', 'Untitled')}** ({task.get('id', 'unknown')})")
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


def _format_turns_for_llm(turns: list[dict[str, Any]]) -> str:
    """Format transcript turns for LLM analysis."""
    formatted: list[str] = []
    for i, turn in enumerate(turns):
        message = turn.get("message", {})
        role = message.get("role", "unknown")
        content = message.get("content", "")

        if isinstance(content, list):
            text_parts: list[str] = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(str(block.get("text", "")))
                    elif block.get("type") == "tool_use":
                        text_parts.append(f"[Tool: {block.get('name', 'unknown')}]")
            content = " ".join(text_parts)

        formatted.append(f"[Turn {i + 1} - {role}]: {content}")

    return "\n\n".join(formatted)


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
            description="Get messages for a session.",
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
                session_id: The session ID
                limit: Max messages to return
                offset: Offset for pagination
                full_content: If True, returns full content. If False (default), truncates large content.
            """
            try:
                assert message_manager, "Message manager not available"
                messages = await message_manager.get_messages(
                    session_id=session_id,
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

                session_total = await message_manager.count_messages(session_id)

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
            description="Search messages using Full Text Search (FTS).",
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
                session_id: Optional session filter
                limit: Max results
                full_content: If True, returns full content. If False (default), truncates large content.
            """
            try:
                assert message_manager, "Message manager not available"
                results = await message_manager.search_messages(
                    query_text=query,
                    session_id=session_id,
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
            assert session_manager, "Session manager not available"
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
            compact: bool = False,
            full: bool = False,
            write_file: bool = True,
            output_path: str = ".gobby/session_summaries/",
        ) -> dict[str, Any]:
            """
            Create handoff context for a session.

            Generates compact (TranscriptAnalyzer) and/or full (LLM) summaries.
            Always saves to database. Optionally writes to file.

            Args:
                session_id: Session ID (optional, defaults to current active session)
                notes: Additional notes to include in handoff
                compact: Generate compact summary only (default: False, neither = both)
                full: Generate full LLM summary only (default: False, neither = both)
                write_file: Also write to file (default: True). DB is always written.
                output_path: Directory for file output (default: .gobby/session_summaries/ in project)

            Returns:
                Success status, markdown lengths, and extracted context summary
            """
            import json
            import subprocess
            import time
            from pathlib import Path

            from gobby.sessions.analyzer import TranscriptAnalyzer

            if session_manager is None:
                return {"success": False, "error": "Session manager not available"}

            # Find session
            session = None
            if session_id:
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
                # Get most recent active session
                sessions = session_manager.list(status="active", limit=1)
                session = sessions[0] if sessions else None

            if not session:
                return {"success": False, "error": "No session found", "session_id": session_id}

            # Get transcript path
            transcript_path = session.jsonl_path
            if not transcript_path:
                return {
                    "success": False,
                    "error": "No transcript path for session",
                    "session_id": session.id,
                }

            path = Path(transcript_path)
            if not path.exists():
                return {
                    "success": False,
                    "error": "Transcript file not found",
                    "path": transcript_path,
                }

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

            # Determine what to generate (neither flag = both)
            generate_compact = compact or not full
            generate_full = full or not compact

            # Generate content
            compact_markdown = None
            full_markdown = None
            full_error = None

            if generate_compact:
                compact_markdown = _format_handoff_markdown(handoff_ctx, notes)

            if generate_full:
                try:
                    from gobby.config.app import load_config
                    from gobby.llm.claude import ClaudeLLMProvider
                    from gobby.sessions.transcripts.claude import ClaudeTranscriptParser

                    config = load_config()
                    provider = ClaudeLLMProvider(config)
                    transcript_parser = ClaudeTranscriptParser()

                    # Get prompt template from config
                    prompt_template = None
                    if hasattr(config, "session_summary") and config.session_summary:
                        prompt_template = getattr(config.session_summary, "prompt", None)

                    if not prompt_template:
                        raise ValueError(
                            "No prompt template configured. "
                            "Set 'session_summary.prompt' in ~/.gobby/config.yaml"
                        )

                    # Prepare context for LLM
                    last_turns = transcript_parser.extract_turns_since_clear(turns, max_turns=50)
                    last_messages = transcript_parser.extract_last_messages(turns, num_pairs=2)

                    context = {
                        "transcript_summary": _format_turns_for_llm(last_turns),
                        "last_messages": last_messages,
                        "git_status": handoff_ctx.git_status or "",
                        "file_changes": "",
                        "external_id": session.id[:12],
                        "session_id": session.id,
                        "session_source": session.source,
                    }

                    full_markdown = await provider.generate_summary(
                        context, prompt_template=prompt_template
                    )

                except Exception as e:
                    full_error = str(e)
                    if full and not compact:
                        return {
                            "success": False,
                            "error": f"Failed to generate full summary: {e}",
                            "session_id": session.id,
                        }

            # Always save to database
            if compact_markdown:
                session_manager.update_compact_markdown(session.id, compact_markdown)
            if full_markdown:
                session_manager.update_summary(session.id, summary_markdown=full_markdown)

            # Save to file if requested
            files_written = []
            if write_file:
                try:
                    summary_dir = Path(output_path)
                    if not summary_dir.is_absolute():
                        summary_dir = Path.cwd() / summary_dir
                    summary_dir.mkdir(parents=True, exist_ok=True)
                    timestamp = int(time.time())

                    if full_markdown:
                        full_file = summary_dir / f"session_{timestamp}_{session.id[:12]}.md"
                        full_file.write_text(full_markdown, encoding="utf-8")
                        files_written.append(str(full_file))

                    if compact_markdown:
                        compact_file = (
                            summary_dir / f"session_compact_{timestamp}_{session.id[:12]}.md"
                        )
                        compact_file.write_text(compact_markdown, encoding="utf-8")
                        files_written.append(str(compact_file))

                except Exception as e:
                    return {
                        "success": False,
                        "error": f"Failed to write file: {e}",
                        "session_id": session.id,
                    }

            return {
                "success": True,
                "session_id": session.id,
                "compact_length": len(compact_markdown) if compact_markdown else 0,
                "full_length": len(full_markdown) if full_markdown else 0,
                "full_error": full_error,
                "files_written": files_written,
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
                if machine_id:
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
                session_manager.update_parent_session_id(link_child_session_id, parent_session.id)

            return {
                "found": True,
                "session_id": parent_session.id,
                "has_context": True,
                "context": context,
                "context_type": (
                    "compact_markdown" if parent_session.compact_markdown else "summary_markdown"
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
            description="Look up the current session by its external identifiers.",
        )
        def get_current_session(
            external_id: str,
            source: str,
            machine_id: str,
            project_id: str,
        ) -> dict[str, Any]:
            """
            Look up the current session by its external identifiers.

            This is a deterministic lookup - it finds the exact session matching
            the provided identifiers rather than guessing based on "most recent".

            Args:
                external_id: External session identifier (e.g., Claude Code's session ID)
                source: CLI source ("claude", "gemini", "codex")
                machine_id: Machine identifier
                project_id: Project identifier

            Returns:
                Session dict with internal 'id' field, or error if not found
            """
            if session_manager is None:
                return {"error": "Session manager not available"}

            # Deterministic lookup by all four identifiers
            session = session_manager.find_by_external_id(
                external_id=external_id,
                machine_id=machine_id,
                project_id=project_id,
                source=source,
            )

            if session:
                return {
                    "found": True,
                    **session.to_dict(),
                }

            return {
                "found": False,
                "message": "Session not found for provided identifiers",
                "external_id": external_id,
                "source": source,
                "machine_id": machine_id,
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
            import subprocess
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

                result = subprocess.run(
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
            description="Mark the autonomous loop as complete, preventing session chaining.",
        )
        def mark_loop_complete(session_id: str | None = None) -> dict[str, Any]:
            """
            Mark the autonomous loop as complete for a session.

            This sets stop_reason='completed' in the workflow state, which
            signals the autonomous-loop workflow to NOT chain a new session
            when this session ends.

            Use this when:
            - A task is fully complete and no more work is needed
            - You want to exit the autonomous loop gracefully
            - The user has explicitly asked to stop

            Args:
                session_id: Session ID (optional, defaults to current active session)

            Returns:
                Success status and session details
            """
            assert session_manager, "Session manager not available"

            # Find session
            if session_id:
                session = session_manager.get(session_id)
            else:
                # Get most recent active session
                sessions = session_manager.list(status="active", limit=1)
                session = sessions[0] if sessions else None

            if not session:
                return {"error": "No session found", "session_id": session_id}

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
                    workflow_name="autonomous-loop",
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
