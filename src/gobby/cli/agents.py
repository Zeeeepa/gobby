"""
Agent management CLI commands.

Commands for managing subagent runs:
- start: Start a new agent
- list: List agent runs for a session
- show: Show details for an agent run
- status: Check status of a running agent
- cancel: Cancel a running agent
"""

import json

import click
import httpx

from gobby.storage.agents import LocalAgentRunManager
from gobby.storage.database import LocalDatabase


def get_agent_run_manager() -> LocalAgentRunManager:
    """Get initialized agent run manager."""
    db = LocalDatabase()
    return LocalAgentRunManager(db)


def get_daemon_url() -> str:
    """Get daemon URL from config."""
    from gobby.config.app import load_config

    config = load_config()
    return f"http://localhost:{config.daemon_port}"


@click.group()
def agents() -> None:
    """Manage subagent runs."""
    pass


@agents.command("start")
@click.argument("prompt")
@click.option("--session", "-s", "parent_session_id", required=True, help="Parent session ID")
@click.option("--workflow", "-w", help="Workflow name to execute")
@click.option("--task", "-t", help="Task ID or 'next' for auto-select")
@click.option(
    "--mode",
    "-m",
    type=click.Choice(["in_process", "terminal", "embedded", "headless"]),
    default="terminal",
    help="Execution mode (default: terminal)",
)
@click.option(
    "--terminal",
    type=click.Choice(["auto", "ghostty", "iterm", "kitty", "wezterm", "terminal"]),
    default="auto",
    help="Terminal for terminal/embedded modes",
)
@click.option("--provider", "-p", default="claude", help="LLM provider (claude, gemini, etc.)")
@click.option("--model", help="Model override")
@click.option("--timeout", default=120.0, help="Execution timeout in seconds")
@click.option("--max-turns", default=10, help="Maximum turns")
@click.option(
    "--context",
    "session_context",
    default="summary_markdown",
    help="Context source (summary_markdown, compact_markdown, transcript:<n>, file:<path>)",
)
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
def start_agent_cmd(
    prompt: str,
    parent_session_id: str,
    workflow: str | None,
    task: str | None,
    mode: str,
    terminal: str,
    provider: str,
    model: str | None,
    timeout: float,
    max_turns: int,
    session_context: str,
    json_format: bool,
) -> None:
    """Start a new agent with the given prompt.

    Examples:

        gobby agents start "Implement feature X" --session sess-abc123

        gobby agents start "Fix the bug" -s sess-abc123 --mode terminal

        gobby agents start "Run tests" -s sess-abc123 --mode headless
    """
    daemon_url = get_daemon_url()

    # Build arguments for the MCP tool call
    arguments = {
        "prompt": prompt,
        "parent_session_id": parent_session_id,
        "mode": mode,
        "terminal": terminal,
        "provider": provider,
        "timeout": timeout,
        "max_turns": max_turns,
        "session_context": session_context,
    }

    if workflow:
        arguments["workflow"] = workflow
    if task:
        arguments["task"] = task
    if model:
        arguments["model"] = model

    # Call the daemon's MCP tool endpoint
    try:
        response = httpx.post(
            f"{daemon_url}/mcp/gobby-agents/tools/start_agent",
            json=arguments,
            timeout=30.0,
        )
        response.raise_for_status()
        result = response.json()
    except httpx.ConnectError:
        click.echo("Error: Cannot connect to Gobby daemon. Is it running?", err=True)
        click.echo("Start with: gobby start", err=True)
        return
    except httpx.HTTPStatusError as e:
        click.echo(f"Error: Daemon returned {e.response.status_code}", err=True)
        click.echo(e.response.text, err=True)
        return
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        return

    if json_format:
        click.echo(json.dumps(result, indent=2, default=str))
        return

    # Check result
    if result.get("success"):
        run_id = result.get("run_id", "unknown")
        child_session_id = result.get("child_session_id", "unknown")
        status = result.get("status", "unknown")

        click.echo(f"Started agent run: {run_id}")
        click.echo(f"  Child session: {child_session_id}")
        click.echo(f"  Status: {status}")

        if result.get("message"):
            click.echo(f"  {result['message']}")

        if mode == "in_process" and result.get("output"):
            click.echo(f"\nOutput:\n{result['output']}")
    else:
        error = result.get("error", "Unknown error")
        click.echo(f"Failed to start agent: {error}", err=True)


@agents.command("list")
@click.option("--session", "-s", "session_id", help="Filter by parent session ID")
@click.option(
    "--status",
    type=click.Choice(["pending", "running", "success", "error", "timeout", "cancelled"]),
    help="Filter by status",
)
@click.option("--limit", "-n", default=20, help="Max runs to show")
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
def list_agents(
    session_id: str | None,
    status: str | None,
    limit: int,
    json_format: bool,
) -> None:
    """List agent runs."""
    manager = get_agent_run_manager()

    if session_id:
        runs = manager.list_by_session(session_id, status=status, limit=limit)  # type: ignore
    elif status == "running":
        runs = manager.list_running(limit=limit)
    else:
        # List recent runs across all sessions
        # Note: This requires querying without session filter
        db = LocalDatabase()
        query = "SELECT * FROM agent_runs"
        params: list[str | int] = []

        if status:
            query += " WHERE status = ?"
            params.append(status)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = db.fetchall(query, tuple(params))
        from gobby.storage.agents import AgentRun

        runs = [AgentRun.from_row(row) for row in rows]

    if json_format:
        click.echo(json.dumps([r.to_dict() for r in runs], indent=2, default=str))
        return

    if not runs:
        click.echo("No agent runs found.")
        return

    click.echo(f"Found {len(runs)} agent run(s):\n")
    for run in runs:
        status_icon = {
            "pending": "○",
            "running": "◐",
            "success": "✓",
            "error": "✗",
            "timeout": "⏱",
            "cancelled": "⊘",
        }.get(run.status, "?")

        # Truncate prompt
        prompt = run.prompt[:40] + "..." if len(run.prompt) > 40 else run.prompt
        prompt = prompt.replace("\n", " ")

        click.echo(f"{status_icon} {run.id[:12]}  {run.status:<10} {run.provider:<8} {prompt}")


@agents.command("show")
@click.argument("run_id")
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
def show_agent(run_id: str, json_format: bool) -> None:
    """Show details for an agent run."""
    manager = get_agent_run_manager()

    # Try exact match first, then prefix match
    run = manager.get(run_id)
    if not run:
        # Try prefix match
        db = LocalDatabase()
        rows = db.fetchall(
            "SELECT * FROM agent_runs WHERE id LIKE ? LIMIT 10",
            (f"{run_id}%",),
        )
        from gobby.storage.agents import AgentRun

        matches = [AgentRun.from_row(row) for row in rows]

        if len(matches) == 1:
            run = matches[0]
        elif len(matches) > 1:
            click.echo(f"Ambiguous run ID '{run_id}' matches {len(matches)} runs:", err=True)
            for r in matches[:5]:
                click.echo(f"  {r.id}: {r.status}", err=True)
            return
        else:
            click.echo(f"Agent run not found: {run_id}", err=True)
            return

    if json_format:
        click.echo(json.dumps(run.to_dict(), indent=2, default=str))
        return

    click.echo(f"Agent Run: {run.id}")
    click.echo(f"Status: {run.status}")
    click.echo(f"Provider: {run.provider}")
    if run.model:
        click.echo(f"Model: {run.model}")
    click.echo(f"Parent Session: {run.parent_session_id}")
    if run.child_session_id:
        click.echo(f"Child Session: {run.child_session_id}")
    if run.workflow_name:
        click.echo(f"Workflow: {run.workflow_name}")

    click.echo(f"\nPrompt:\n{run.prompt[:500]}")
    if len(run.prompt) > 500:
        click.echo("...")

    if run.result:
        click.echo(f"\nResult:\n{run.result[:500]}")
        if len(run.result) > 500:
            click.echo("...")

    if run.error:
        click.echo(f"\nError: {run.error}")

    click.echo(f"\nTurns Used: {run.turns_used}")
    click.echo(f"Tool Calls: {run.tool_calls_count}")
    click.echo(f"Created: {run.created_at}")
    if run.started_at:
        click.echo(f"Started: {run.started_at}")
    if run.completed_at:
        click.echo(f"Completed: {run.completed_at}")


@agents.command("status")
@click.argument("run_id")
def agent_status(run_id: str) -> None:
    """Check status of an agent run."""
    manager = get_agent_run_manager()

    run = manager.get(run_id)
    if not run:
        # Try prefix match
        db = LocalDatabase()
        rows = db.fetchall(
            "SELECT * FROM agent_runs WHERE id LIKE ? LIMIT 2",
            (f"{run_id}%",),
        )
        from gobby.storage.agents import AgentRun

        matches = [AgentRun.from_row(row) for row in rows]

        if len(matches) == 1:
            run = matches[0]
        else:
            click.echo(f"Agent run not found: {run_id}", err=True)
            return

    status_icon = {
        "pending": "○",
        "running": "◐",
        "success": "✓",
        "error": "✗",
        "timeout": "⏱",
        "cancelled": "⊘",
    }.get(run.status, "?")

    click.echo(f"{status_icon} {run.id}: {run.status}")

    if run.status == "running" and run.started_at:
        click.echo(f"   Running since: {run.started_at}")
        click.echo(f"   Turns used: {run.turns_used}")
    elif run.status in ("success", "error", "timeout", "cancelled"):
        if run.completed_at:
            click.echo(f"   Completed: {run.completed_at}")
        if run.error:
            click.echo(f"   Error: {run.error}")


@agents.command("cancel")
@click.argument("run_id")
@click.confirmation_option(prompt="Are you sure you want to cancel this agent run?")
def cancel_agent(run_id: str) -> None:
    """Cancel a running agent."""
    manager = get_agent_run_manager()

    run = manager.get(run_id)
    if not run:
        # Try prefix match
        db = LocalDatabase()
        rows = db.fetchall(
            "SELECT * FROM agent_runs WHERE id LIKE ? LIMIT 2",
            (f"{run_id}%",),
        )
        from gobby.storage.agents import AgentRun

        matches = [AgentRun.from_row(row) for row in rows]

        if len(matches) == 1:
            run = matches[0]
        else:
            click.echo(f"Agent run not found: {run_id}", err=True)
            return

    if run.status not in ("pending", "running"):
        click.echo(f"Cannot cancel agent in status: {run.status}", err=True)
        return

    manager.cancel(run.id)
    click.echo(f"Cancelled agent run: {run.id}")


@agents.command("stats")
@click.option("--session", "-s", "session_id", help="Filter by parent session ID")
def agent_stats(session_id: str | None) -> None:
    """Show agent run statistics."""
    db = LocalDatabase()

    if session_id:
        manager = get_agent_run_manager()
        counts = manager.count_by_session(session_id)
        total = sum(counts.values())

        click.echo(f"Agent Statistics for session {session_id[:12]}:")
        click.echo(f"  Total Runs: {total}")
    else:
        # Global stats
        row = db.fetchone(
            """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success,
                SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as error,
                SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) as running,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN status = 'timeout' THEN 1 ELSE 0 END) as timeout,
                SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) as cancelled
            FROM agent_runs
            """
        )

        if row:
            click.echo("Agent Run Statistics:")
            click.echo(f"  Total Runs: {row['total']}")
            click.echo(f"  Running: {row['running']}")
            click.echo(f"  Pending: {row['pending']}")
            click.echo(f"  Success: {row['success']}")
            click.echo(f"  Error: {row['error']}")
            click.echo(f"  Timeout: {row['timeout']}")
            click.echo(f"  Cancelled: {row['cancelled']}")

            if row["total"] > 0:
                success_rate = (row["success"] / row["total"]) * 100
                click.echo(f"\n  Success Rate: {success_rate:.1f}%")
        else:
            click.echo("No agent runs found.")


@agents.command("cleanup")
@click.option("--timeout", "-t", default=30, help="Timeout in minutes for stale runs")
@click.option("--dry-run", is_flag=True, help="Show what would be cleaned up")
def cleanup_agents(timeout: int, dry_run: bool) -> None:
    """Clean up stale agent runs."""
    manager = get_agent_run_manager()

    if dry_run:
        # Show what would be cleaned up
        db = LocalDatabase()
        stale_running = db.fetchall(
            """
            SELECT * FROM agent_runs
            WHERE status = 'running'
            AND datetime(started_at) < datetime('now', 'utc', ? || ' minutes')
            """,
            (f"-{timeout}",),
        )
        stale_pending = db.fetchall(
            """
            SELECT * FROM agent_runs
            WHERE status = 'pending'
            AND datetime(created_at) < datetime('now', 'utc', '-60 minutes')
            """
        )

        click.echo(f"Stale running runs (>{timeout}m): {len(stale_running)}")
        for row in stale_running[:5]:
            click.echo(f"  {row['id']}: started {row['started_at']}")

        click.echo(f"Stale pending runs (>60m): {len(stale_pending)}")
        for row in stale_pending[:5]:
            click.echo(f"  {row['id']}: created {row['created_at']}")
    else:
        timed_out = manager.cleanup_stale_runs(timeout_minutes=timeout)
        failed = manager.cleanup_stale_pending_runs(timeout_minutes=60)

        click.echo(f"Cleaned up {timed_out} timed-out runs and {failed} stale pending runs.")
