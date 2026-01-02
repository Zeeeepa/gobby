"""
Session management CLI commands.
"""

import asyncio
import json

import click

from gobby.storage.database import LocalDatabase
from gobby.storage.session_messages import LocalSessionMessageManager
from gobby.storage.sessions import LocalSessionManager


def get_session_manager() -> LocalSessionManager:
    """Get initialized session manager."""
    db = LocalDatabase()
    return LocalSessionManager(db)


def get_message_manager() -> LocalSessionMessageManager:
    """Get initialized message manager."""
    db = LocalDatabase()
    return LocalSessionMessageManager(db)


@click.group()
def sessions() -> None:
    """Manage Gobby sessions."""
    pass


@sessions.command("list")
@click.option("--project", "-p", "project_id", help="Filter by project ID")
@click.option("--status", "-s", help="Filter by status (active, completed, handoff_ready)")
@click.option("--source", help="Filter by source (claude_code, gemini, codex)")
@click.option("--limit", "-n", default=20, help="Max sessions to show")
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
def list_sessions(
    project_id: str | None,
    status: str | None,
    source: str | None,
    limit: int,
    json_format: bool,
) -> None:
    """List sessions with optional filtering."""
    manager = get_session_manager()
    sessions_list = manager.list(
        project_id=project_id,
        status=status,
        source=source,
        limit=limit,
    )

    if json_format:
        click.echo(json.dumps([s.to_dict() for s in sessions_list], indent=2, default=str))
        return

    if not sessions_list:
        click.echo("No sessions found.")
        return

    click.echo(f"Found {len(sessions_list)} sessions:\n")
    for session in sessions_list:
        status_icon = {
            "active": "●",
            "completed": "✓",
            "handoff_ready": "→",
            "expired": "○",
        }.get(session.status, "?")

        title = session.title or "(no title)"
        if len(title) > 50:
            title = title[:47] + "..."

        click.echo(f"{status_icon} {session.id[:12]}  {session.source:<12} {title}")


@sessions.command("show")
@click.argument("session_id")
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
def show_session(session_id: str, json_format: bool) -> None:
    """Show details for a session."""
    manager = get_session_manager()

    # Try exact match first, then prefix match
    session = manager.get(session_id)
    if not session:
        # Try prefix match
        all_sessions = manager.list(limit=1000)
        matches = [s for s in all_sessions if s.id.startswith(session_id)]
        if len(matches) == 1:
            session = matches[0]
        elif len(matches) > 1:
            click.echo(f"Ambiguous session ID '{session_id}' matches {len(matches)} sessions:", err=True)
            for s in matches[:5]:
                click.echo(f"  {s.id}: {s.title or '(no title)'}", err=True)
            return
        else:
            click.echo(f"Session not found: {session_id}", err=True)
            return

    if json_format:
        click.echo(json.dumps(session.to_dict(), indent=2, default=str))
        return

    click.echo(f"Session: {session.id}")
    click.echo(f"Status: {session.status}")
    click.echo(f"Source: {session.source}")
    click.echo(f"Project: {session.project_id}")
    if session.title:
        click.echo(f"Title: {session.title}")
    if session.git_branch:
        click.echo(f"Branch: {session.git_branch}")
    click.echo(f"Created: {session.created_at}")
    click.echo(f"Updated: {session.updated_at}")
    if session.parent_session_id:
        click.echo(f"Parent: {session.parent_session_id}")
    if session.summary_markdown:
        click.echo(f"\nSummary:\n{session.summary_markdown[:500]}")
        if len(session.summary_markdown) > 500:
            click.echo("...")


@sessions.command("messages")
@click.argument("session_id")
@click.option("--limit", "-n", default=50, help="Max messages to show")
@click.option("--role", "-r", help="Filter by role (user, assistant, tool)")
@click.option("--offset", default=0, help="Skip first N messages")
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
def show_messages(
    session_id: str,
    limit: int,
    role: str | None,
    offset: int,
    json_format: bool,
) -> None:
    """Show messages for a session."""
    session_manager = get_session_manager()
    message_manager = get_message_manager()

    # Resolve session ID
    session = session_manager.get(session_id)
    if not session:
        all_sessions = session_manager.list(limit=1000)
        matches = [s for s in all_sessions if s.id.startswith(session_id)]
        if len(matches) == 1:
            session = matches[0]
        elif len(matches) > 1:
            click.echo(f"Ambiguous session ID '{session_id}'", err=True)
            return
        else:
            click.echo(f"Session not found: {session_id}", err=True)
            return

    # Fetch messages
    messages = asyncio.run(
        message_manager.get_messages(
            session_id=session.id,
            limit=limit,
            offset=offset,
            role=role,
        )
    )

    if json_format:
        click.echo(json.dumps(messages, indent=2, default=str))
        return

    if not messages:
        click.echo("No messages found.")
        return

    total = asyncio.run(message_manager.count_messages(session.id))
    click.echo(f"Messages for session {session.id[:12]} ({len(messages)}/{total}):\n")

    for msg in messages:
        role_icon = {"user": "👤", "assistant": "🤖", "tool": "🔧"}.get(msg["role"], "?")
        content = msg.get("content") or ""

        if msg.get("tool_name"):
            click.echo(f"{role_icon} [{msg['message_index']}] {msg['role']}: {msg['tool_name']}")
        else:
            # Truncate long content
            if len(content) > 200:
                content = content[:197] + "..."
            click.echo(f"{role_icon} [{msg['message_index']}] {msg['role']}: {content}")


@sessions.command("search")
@click.argument("query")
@click.option("--session", "-s", "session_id", help="Search within specific session")
@click.option("--project", "-p", "project_id", help="Search within project")
@click.option("--limit", "-n", default=20, help="Max results")
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
def search_messages(
    query: str,
    session_id: str | None,
    project_id: str | None,
    limit: int,
    json_format: bool,
) -> None:
    """Search messages across sessions."""
    message_manager = get_message_manager()

    results = asyncio.run(
        message_manager.search_messages(
            query_text=query,
            limit=limit,
            session_id=session_id,
            project_id=project_id,
        )
    )

    if json_format:
        click.echo(json.dumps(results, indent=2, default=str))
        return

    if not results:
        click.echo(f"No messages found matching '{query}'")
        return

    click.echo(f"Found {len(results)} messages matching '{query}':\n")

    for msg in results:
        content = msg.get("content") or ""
        if len(content) > 100:
            content = content[:97] + "..."

        session_short = msg["session_id"][:8]
        role_icon = {"user": "👤", "assistant": "🤖", "tool": "🔧"}.get(msg["role"], "?")
        click.echo(f"{role_icon} [{session_short}] {content}")


@sessions.command("delete")
@click.argument("session_id")
@click.confirmation_option(prompt="Are you sure you want to delete this session?")
def delete_session(session_id: str) -> None:
    """Delete a session."""
    manager = get_session_manager()

    # Resolve session ID
    session = manager.get(session_id)
    if not session:
        all_sessions = manager.list(limit=1000)
        matches = [s for s in all_sessions if s.id.startswith(session_id)]
        if len(matches) == 1:
            session = matches[0]
        elif len(matches) > 1:
            click.echo(f"Ambiguous session ID '{session_id}'", err=True)
            return
        else:
            click.echo(f"Session not found: {session_id}", err=True)
            return

    success = manager.delete(session.id)
    if success:
        click.echo(f"Deleted session: {session.id}")
    else:
        click.echo(f"Failed to delete session: {session.id}", err=True)


@sessions.command("stats")
@click.option("--project", "-p", "project_id", help="Filter by project")
def session_stats(project_id: str | None) -> None:
    """Show session statistics."""
    manager = get_session_manager()
    message_manager = get_message_manager()

    sessions_list = manager.list(project_id=project_id, limit=10000)

    if not sessions_list:
        click.echo("No sessions found.")
        return

    # Count by status
    by_status: dict[str, int] = {}
    by_source: dict[str, int] = {}

    for session in sessions_list:
        by_status[session.status] = by_status.get(session.status, 0) + 1
        by_source[session.source] = by_source.get(session.source, 0) + 1

    # Get message counts
    message_counts = asyncio.run(message_manager.get_all_counts())
    total_messages = sum(message_counts.values())

    click.echo("Session Statistics:")
    click.echo(f"  Total Sessions: {len(sessions_list)}")
    click.echo(f"  Total Messages: {total_messages}")

    click.echo("\n  By Status:")
    for status, count in sorted(by_status.items()):
        click.echo(f"    {status}: {count}")

    click.echo("\n  By Source:")
    for source, count in sorted(by_source.items()):
        click.echo(f"    {source}: {count}")


@sessions.command("handoff")
@click.option("--session-id", "-s", help="Session ID (defaults to current active session)")
@click.argument("notes", required=False)
def create_handoff(session_id: str | None, notes: str | None) -> None:
    """Create handoff context for a session.

    Extracts structured context from the session transcript:
    - Active gobby-task
    - TodoWrite state
    - Files modified
    - Git commits and status
    - Initial goal
    - Recent activity

    If no session ID is provided, uses the current project's most recent active session.
    """
    import subprocess
    from pathlib import Path

    from gobby.mcp_proxy.tools.session_messages import _format_handoff_markdown
    from gobby.sessions.analyzer import TranscriptAnalyzer

    manager = get_session_manager()

    # Find session
    if session_id:
        session = manager.get(session_id)
        if not session:
            # Try prefix match
            all_sessions = manager.list(limit=1000)
            matches = [s for s in all_sessions if s.id.startswith(session_id)]
            if len(matches) == 1:
                session = matches[0]
            elif len(matches) > 1:
                click.echo(f"Ambiguous session ID '{session_id}'", err=True)
                return
            else:
                click.echo(f"Session not found: {session_id}", err=True)
                return
    else:
        # Get most recent active session
        sessions_list = manager.list(status="active", limit=1)
        if not sessions_list:
            click.echo("No active session found. Specify --session-id.", err=True)
            return
        session = sessions_list[0]

    # Check for transcript
    if not session.jsonl_path:
        click.echo(f"Session {session.id[:12]} has no transcript path.", err=True)
        return

    path = Path(session.jsonl_path)
    if not path.exists():
        click.echo(f"Transcript file not found: {path}", err=True)
        return

    # Read and parse transcript
    turns = []
    with open(path) as f:
        for line in f:
            if line.strip():
                turns.append(json.loads(line))

    if not turns:
        click.echo("Transcript is empty.", err=True)
        return

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

    # Format and save
    markdown = _format_handoff_markdown(handoff_ctx, notes)
    manager.update_compact_markdown(session.id, markdown)

    # Output summary
    click.echo(f"Created handoff context for session {session.id[:12]}")
    click.echo(f"  Markdown length: {len(markdown)} chars")
    click.echo(f"  Active task: {'Yes' if handoff_ctx.active_gobby_task else 'No'}")
    click.echo(f"  Todo items: {len(handoff_ctx.todo_state)}")
    click.echo(f"  Files modified: {len(handoff_ctx.files_modified)}")
    click.echo(f"  Git commits: {len(handoff_ctx.git_commits)}")
    click.echo(f"  Initial goal: {'Yes' if handoff_ctx.initial_goal else 'No'}")

    if notes:
        click.echo(f"  Notes: {notes[:50]}{'...' if len(notes) > 50 else ''}")
