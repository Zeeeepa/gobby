"""Handoff helper functions and tools for session management.

This module contains:
- Helper functions for formatting handoff context
- MCP tools for creating and retrieving handoffs
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gobby.mcp_proxy.tools.internal import InternalToolRegistry
    from gobby.sessions.analyzer import HandoffContext
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


def register_handoff_tools(
    registry: InternalToolRegistry,
    session_manager: LocalSessionManager,
) -> None:
    """
    Register handoff tools with a registry.

    Args:
        registry: The InternalToolRegistry to register tools with
        session_manager: LocalSessionManager instance for session operations
    """
    from gobby.utils.project_context import get_project_context

    def _resolve_session_id(ref: str) -> str:
        """Resolve session reference (#N, N, UUID, or prefix) to UUID."""
        project_ctx = get_project_context()
        project_id = project_ctx.get("id") if project_ctx else None

        return session_manager.resolve_session_reference(ref, project_id)

    @registry.tool(
        name="get_handoff_context",
        description="Get the handoff context (compact_markdown) for a session. Accepts #N, N, UUID, or prefix.",
    )
    def get_handoff_context(session_id: str) -> dict[str, Any]:
        """
        Retrieve stored handoff context.

        Args:
            session_id: Session reference - supports #N, N (seq_num), UUID, or prefix

        Returns:
            Session ID, compact_markdown, and whether context exists
        """
        if not session_manager:
            raise RuntimeError("Session manager not available")

        # Get project_id for project-scoped resolution
        project_ctx = get_project_context()
        project_id = project_ctx.get("id") if project_ctx else None

        # Resolve #N format, UUID, or prefix
        try:
            resolved_id = session_manager.resolve_session_reference(session_id, project_id)
            session = session_manager.get(resolved_id)
        except ValueError:
            session = None
        if not session:
            return {"error": f"Session {session_id} not found", "found": False}

        return {
            "session_id": session.id,
            "ref": f"#{session.seq_num}" if session.seq_num else session.id[:8],
            "compact_markdown": session.compact_markdown,
            "has_context": bool(session.compact_markdown),
        }

    @registry.tool(
        name="create_handoff",
        description="""Create handoff context by extracting structured data from the session transcript. Accepts #N, N, UUID, or prefix for session_id.

Args:
    session_id: (REQUIRED) Your session ID. Accepts #N, N, UUID, or prefix. Get it from:
        1. Your injected context (look for 'Session Ref: #N' or 'session_id: xxx')
        2. Or call get_current_session(external_id, source) first""",
    )
    async def create_handoff(
        session_id: str,
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
            session_id: Session reference - supports #N, N (seq_num), UUID, or prefix (REQUIRED)
            notes: Additional notes to include in handoff
            compact: Generate compact summary only (default: False, neither = both)
            full: Generate full LLM summary only (default: False, neither = both)
            write_file: Also write to file (default: True). DB is always written.
            output_path: Directory for file output (default: .gobby/session_summaries/ in project)

        Returns:
            Success status, markdown lengths, and extracted context summary
        """
        import json
        import subprocess  # nosec B404 - subprocess needed for git commands
        import time
        from pathlib import Path

        from gobby.sessions.analyzer import TranscriptAnalyzer

        if session_manager is None:
            return {"success": False, "error": "Session manager not available"}

        # Resolve session reference (#N, N, UUID, or prefix)
        try:
            resolved_id = _resolve_session_id(session_id)
            session = session_manager.get(resolved_id)
        except ValueError as e:
            return {"success": False, "error": str(e), "session_id": session_id}

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
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    turns.append(json.loads(line))

        # Analyze transcript
        analyzer = TranscriptAnalyzer()
        handoff_ctx = analyzer.extract_handoff_context(turns)

        # Enrich with real-time git status
        if not handoff_ctx.git_status:
            try:
                result = subprocess.run(  # nosec B603 B607 - hardcoded git command
                    ["git", "status", "--short"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    cwd=path.parent,
                )
                handoff_ctx.git_status = result.stdout.strip() if result.returncode == 0 else ""
            except Exception:
                pass  # nosec B110 - git status is optional, ignore failures

        # Get recent git commits
        try:
            result = subprocess.run(  # nosec B603 B607 - hardcoded git command
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
            pass  # nosec B110 - git log is optional, ignore failures

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
                    compact_file = summary_dir / f"session_compact_{timestamp}_{session.id[:12]}.md"
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
        description="Restore context from a previous session's handoff. For CLIs/IDEs without hooks. Accepts #N, N, UUID, or prefix for session_id.",
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
            session_id: Session reference - supports #N, N (seq_num), UUID, or prefix (optional)
            project_id: Project ID to find parent session in (optional)
            source: Filter by CLI source - claude_code, gemini, codex (optional)
            link_child_session_id: Session to link as child - supports #N, N, UUID, or prefix (optional)

        Returns:
            Handoff context markdown and session metadata
        """
        from gobby.utils.machine_id import get_machine_id

        if session_manager is None:
            return {"error": "Session manager not available"}

        parent_session = None

        # Option 1: Direct session_id lookup with resolution
        if session_id:
            try:
                resolved_id = _resolve_session_id(session_id)
                parent_session = session_manager.get(resolved_id)
            except ValueError as e:
                return {"error": str(e)}

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

        # Optionally link child session (resolve if using #N format)
        resolved_child_id = None
        if link_child_session_id:
            try:
                resolved_child_id = _resolve_session_id(link_child_session_id)
                session_manager.update_parent_session_id(resolved_child_id, parent_session.id)
            except ValueError as e:
                # Do not fallback to raw reference - propagate the error
                return {
                    "found": True,
                    "session_id": parent_session.id,
                    "has_context": True,
                    "error": f"Failed to resolve child session '{link_child_session_id}': {e}",
                    "context": context,
                }

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
            "linked_child": resolved_child_id or link_child_session_id,
        }
