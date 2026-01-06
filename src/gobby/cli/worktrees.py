"""
Worktree management CLI commands.

Commands for managing git worktrees:
- create: Create a new worktree
- list: List worktrees
- show: Show worktree details
- delete: Delete a worktree
- spawn: Spawn an agent in a worktree
- claim: Claim a worktree for a session
- release: Release a worktree
- sync: Sync worktree with main branch
- stale: Detect stale worktrees
- cleanup: Clean up stale worktrees
"""

import json

import click
import httpx

from gobby.storage.database import LocalDatabase
from gobby.storage.worktrees import LocalWorktreeManager


def get_worktree_manager() -> LocalWorktreeManager:
    """Get initialized worktree manager."""
    db = LocalDatabase()
    return LocalWorktreeManager(db)


def get_daemon_url() -> str:
    """Get daemon URL from config."""
    from gobby.config.app import load_config

    config = load_config()
    return f"http://localhost:{config.daemon_port}"


@click.group()
def worktrees() -> None:
    """Manage git worktrees for parallel development."""
    pass


@worktrees.command("create")
@click.argument("branch_name")
@click.option("--base", "-b", "base_branch", default="main", help="Base branch to create from")
@click.option("--task", "-t", "task_id", help="Link worktree to a task")
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
def create_worktree(
    branch_name: str,
    base_branch: str,
    task_id: str | None,
    json_format: bool,
) -> None:
    """Create a new worktree for parallel development.

    Examples:

        gobby worktrees create feature/my-feature

        gobby worktrees create bugfix/fix-123 --base develop --task gt-abc123
    """
    daemon_url = get_daemon_url()

    arguments = {
        "branch_name": branch_name,
        "base_branch": base_branch,
    }
    if task_id:
        arguments["task_id"] = task_id

    try:
        response = httpx.post(
            f"{daemon_url}/mcp/call_tool",
            json={
                "server_name": "gobby-worktrees",
                "tool_name": "create_worktree",
                "arguments": arguments,
            },
            timeout=60.0,
        )
        response.raise_for_status()
        result = response.json()
    except httpx.ConnectError:
        click.echo("Error: Cannot connect to Gobby daemon. Is it running?", err=True)
        return
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        return

    if json_format:
        click.echo(json.dumps(result, indent=2, default=str))
        return

    if result.get("success"):
        worktree = result.get("worktree", {})
        click.echo(f"Created worktree: {worktree.get('id')}")
        click.echo(f"  Path: {worktree.get('path')}")
        click.echo(f"  Branch: {worktree.get('branch_name')}")
    else:
        click.echo(f"Failed to create worktree: {result.get('error')}", err=True)


@worktrees.command("list")
@click.option("--status", "-s", help="Filter by status (active, stale, merged, abandoned)")
@click.option("--project", "-p", "project_id", help="Filter by project ID")
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
def list_worktrees(
    status: str | None,
    project_id: str | None,
    json_format: bool,
) -> None:
    """List worktrees."""
    manager = get_worktree_manager()

    worktrees_list = manager.list_worktrees(status=status, project_id=project_id)

    if json_format:
        click.echo(json.dumps([w.to_dict() for w in worktrees_list], indent=2, default=str))
        return

    if not worktrees_list:
        click.echo("No worktrees found.")
        return

    click.echo(f"Found {len(worktrees_list)} worktree(s):\n")
    for wt in worktrees_list:
        status_icon = {
            "active": "●",
            "stale": "○",
            "merged": "✓",
            "abandoned": "✗",
        }.get(wt.status, "?")

        session_info = f" (session: {wt.agent_session_id[:8]})" if wt.agent_session_id else ""
        click.echo(f"{status_icon} {wt.id}  {wt.branch_name:<30} {wt.status:<10}{session_info}")


@worktrees.command("show")
@click.argument("worktree_id")
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
def show_worktree(worktree_id: str, json_format: bool) -> None:
    """Show details for a worktree."""
    manager = get_worktree_manager()

    worktree = manager.get(worktree_id)
    if not worktree:
        # Try prefix match
        all_worktrees = manager.list_worktrees()
        matches = [w for w in all_worktrees if w.id.startswith(worktree_id)]
        if len(matches) == 1:
            worktree = matches[0]
        elif len(matches) > 1:
            click.echo(f"Ambiguous worktree ID '{worktree_id}'", err=True)
            return
        else:
            click.echo(f"Worktree not found: {worktree_id}", err=True)
            return

    if json_format:
        click.echo(json.dumps(worktree.to_dict(), indent=2, default=str))
        return

    click.echo(f"Worktree: {worktree.id}")
    click.echo(f"Status: {worktree.status}")
    click.echo(f"Branch: {worktree.branch_name}")
    click.echo(f"Path: {worktree.worktree_path}")
    click.echo(f"Base Branch: {worktree.base_branch}")
    if worktree.project_id:
        click.echo(f"Project: {worktree.project_id}")
    if worktree.agent_session_id:
        click.echo(f"Session: {worktree.agent_session_id}")
    click.echo(f"Created: {worktree.created_at}")
    click.echo(f"Updated: {worktree.updated_at}")


@worktrees.command("delete")
@click.argument("worktree_id")
@click.option("--force", is_flag=True, help="Force delete even if active")
@click.confirmation_option(prompt="Are you sure you want to delete this worktree?")
def delete_worktree(worktree_id: str, force: bool) -> None:
    """Delete a worktree."""
    daemon_url = get_daemon_url()

    try:
        response = httpx.post(
            f"{daemon_url}/mcp/call_tool",
            json={
                "server_name": "gobby-worktrees",
                "tool_name": "delete_worktree",
                "arguments": {"worktree_id": worktree_id, "force": force},
            },
            timeout=30.0,
        )
        response.raise_for_status()
        result = response.json()
    except httpx.ConnectError:
        click.echo("Error: Cannot connect to Gobby daemon. Is it running?", err=True)
        return
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        return

    if result.get("success"):
        click.echo(f"Deleted worktree: {worktree_id}")
    else:
        click.echo(f"Failed to delete worktree: {result.get('error')}", err=True)


@worktrees.command("spawn")
@click.argument("worktree_id")
@click.argument("prompt")
@click.option("--session", "-s", "parent_session_id", required=True, help="Parent session ID")
@click.option("--workflow", "-w", help="Workflow name to execute")
@click.option("--terminal", default="auto", help="Terminal to spawn in")
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
def spawn_in_worktree(
    worktree_id: str,
    prompt: str,
    parent_session_id: str,
    workflow: str | None,
    terminal: str,
    json_format: bool,
) -> None:
    """Spawn an agent in a worktree.

    Examples:

        gobby worktrees spawn wt-abc123 "Implement feature" -s sess-123
    """
    daemon_url = get_daemon_url()

    arguments = {
        "worktree_id": worktree_id,
        "prompt": prompt,
        "parent_session_id": parent_session_id,
        "terminal": terminal,
    }
    if workflow:
        arguments["workflow"] = workflow

    try:
        response = httpx.post(
            f"{daemon_url}/mcp/call_tool",
            json={
                "server_name": "gobby-worktrees",
                "tool_name": "spawn_agent_in_worktree",
                "arguments": arguments,
            },
            timeout=30.0,
        )
        response.raise_for_status()
        result = response.json()
    except httpx.ConnectError:
        click.echo("Error: Cannot connect to Gobby daemon. Is it running?", err=True)
        return
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        return

    if json_format:
        click.echo(json.dumps(result, indent=2, default=str))
        return

    if result.get("success"):
        click.echo(f"Spawned agent in worktree {worktree_id}")
        if result.get("run_id"):
            click.echo(f"  Run ID: {result['run_id']}")
        if result.get("message"):
            click.echo(f"  {result['message']}")
    else:
        click.echo(f"Failed to spawn agent: {result.get('error')}", err=True)


@worktrees.command("claim")
@click.argument("worktree_id")
@click.argument("session_id")
def claim_worktree(worktree_id: str, session_id: str) -> None:
    """Claim a worktree for a session."""
    manager = get_worktree_manager()

    result = manager.claim(worktree_id, session_id)
    if result:
        click.echo(f"Claimed worktree {worktree_id} for session {session_id}")
    else:
        click.echo(f"Failed to claim worktree {worktree_id}", err=True)


@worktrees.command("release")
@click.argument("worktree_id")
def release_worktree(worktree_id: str) -> None:
    """Release a worktree."""
    manager = get_worktree_manager()

    result = manager.release(worktree_id)
    if result:
        click.echo(f"Released worktree {worktree_id}")
    else:
        click.echo(f"Failed to release worktree {worktree_id}", err=True)


@worktrees.command("sync")
@click.argument("worktree_id")
@click.option(
    "--source", "-s", "source_branch", help="Source branch to sync from (default: base branch)"
)
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
def sync_worktree(worktree_id: str, source_branch: str | None, json_format: bool) -> None:
    """Sync worktree with its base branch."""
    daemon_url = get_daemon_url()

    arguments = {"worktree_id": worktree_id}
    if source_branch:
        arguments["source_branch"] = source_branch

    try:
        response = httpx.post(
            f"{daemon_url}/mcp/call_tool",
            json={
                "server_name": "gobby-worktrees",
                "tool_name": "sync_worktree",
                "arguments": arguments,
            },
            timeout=60.0,
        )
        response.raise_for_status()
        result = response.json()
    except httpx.ConnectError:
        click.echo("Error: Cannot connect to Gobby daemon. Is it running?", err=True)
        return
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        return

    if json_format:
        click.echo(json.dumps(result, indent=2, default=str))
        return

    if result.get("success"):
        click.echo(f"Synced worktree {worktree_id}")
        if result.get("commits_behind"):
            click.echo(f"  Commits merged: {result['commits_behind']}")
    else:
        click.echo(f"Failed to sync worktree: {result.get('error')}", err=True)


@worktrees.command("stale")
@click.option("--days", "-d", default=7, help="Days of inactivity to consider stale")
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
def detect_stale(days: int, json_format: bool) -> None:
    """Detect stale worktrees."""
    daemon_url = get_daemon_url()

    try:
        response = httpx.post(
            f"{daemon_url}/mcp/call_tool",
            json={
                "server_name": "gobby-worktrees",
                "tool_name": "detect_stale_worktrees",
                "arguments": {"days_inactive": days},
            },
            timeout=30.0,
        )
        response.raise_for_status()
        result = response.json()
    except httpx.ConnectError:
        click.echo("Error: Cannot connect to Gobby daemon. Is it running?", err=True)
        return
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        return

    if json_format:
        click.echo(json.dumps(result, indent=2, default=str))
        return

    stale = result.get("stale_worktrees", [])
    if not stale:
        click.echo(f"No stale worktrees found (inactive > {days} days)")
        return

    click.echo(f"Found {len(stale)} stale worktree(s) (inactive > {days} days):\n")
    for wt in stale:
        click.echo(
            f"  {wt['id']}: {wt['branch_name']} (last updated: {wt.get('updated_at', 'unknown')})"
        )


@worktrees.command("cleanup")
@click.option("--days", "-d", default=7, help="Days of inactivity to consider stale")
@click.option("--dry-run", is_flag=True, help="Show what would be cleaned up")
@click.confirmation_option(prompt="Are you sure you want to cleanup stale worktrees?")
def cleanup_worktrees(days: int, dry_run: bool) -> None:
    """Clean up stale worktrees."""
    daemon_url = get_daemon_url()

    if dry_run:
        # Just detect stale
        try:
            response = httpx.post(
                f"{daemon_url}/mcp/call_tool",
                json={
                    "server_name": "gobby-worktrees",
                    "tool_name": "detect_stale_worktrees",
                    "arguments": {"days_inactive": days},
                },
                timeout=30.0,
            )
            response.raise_for_status()
            result = response.json()
            stale = result.get("stale_worktrees", [])
            click.echo(f"Would cleanup {len(stale)} stale worktree(s)")
            for wt in stale:
                click.echo(f"  {wt['id']}: {wt['branch_name']}")
        except Exception as e:
            click.echo(f"Error: {e}", err=True)
        return

    try:
        response = httpx.post(
            f"{daemon_url}/mcp/call_tool",
            json={
                "server_name": "gobby-worktrees",
                "tool_name": "cleanup_stale_worktrees",
                "arguments": {"days_inactive": days},
            },
            timeout=120.0,
        )
        response.raise_for_status()
        result = response.json()
    except httpx.ConnectError:
        click.echo("Error: Cannot connect to Gobby daemon. Is it running?", err=True)
        return
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        return

    if result.get("success"):
        cleaned = result.get("cleaned_count", 0)
        click.echo(f"Cleaned up {cleaned} stale worktree(s)")
    else:
        click.echo(f"Failed to cleanup worktrees: {result.get('error')}", err=True)


@worktrees.command("stats")
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
def worktree_stats(json_format: bool) -> None:
    """Show worktree statistics."""
    daemon_url = get_daemon_url()

    try:
        response = httpx.post(
            f"{daemon_url}/mcp/call_tool",
            json={
                "server_name": "gobby-worktrees",
                "tool_name": "get_worktree_stats",
                "arguments": {},
            },
            timeout=10.0,
        )
        response.raise_for_status()
        result = response.json()
    except httpx.ConnectError:
        click.echo("Error: Cannot connect to Gobby daemon. Is it running?", err=True)
        return
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        return

    if json_format:
        click.echo(json.dumps(result, indent=2, default=str))
        return

    stats = result.get("stats", {})
    click.echo("Worktree Statistics:")
    click.echo(f"  Total: {stats.get('total', 0)}")
    click.echo(f"  Active: {stats.get('active', 0)}")
    click.echo(f"  Stale: {stats.get('stale', 0)}")
    click.echo(f"  Merged: {stats.get('merged', 0)}")
    click.echo(f"  Abandoned: {stats.get('abandoned', 0)}")
    click.echo(f"  With Sessions: {stats.get('with_sessions', 0)}")
