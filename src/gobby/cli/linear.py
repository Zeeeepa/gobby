"""
CLI commands for Linear integration.

Provides commands for syncing gobby tasks with Linear issues.
"""

import asyncio
import json
import logging
from pathlib import Path

import click

from gobby.cli.tasks._utils import resolve_task_id
from gobby.integrations.linear import LinearIntegration
from gobby.mcp_proxy.manager import MCPClientManager
from gobby.storage.database import LocalDatabase
from gobby.storage.projects import LocalProjectManager
from gobby.storage.tasks import LocalTaskManager
from gobby.sync.linear import LinearSyncService
from gobby.utils.project_context import get_project_context

logger = logging.getLogger(__name__)


def get_linear_deps() -> tuple[LocalTaskManager, MCPClientManager, LocalProjectManager, str]:
    """Get dependencies for Linear commands."""
    db = LocalDatabase()
    task_manager = LocalTaskManager(db)
    project_manager = LocalProjectManager(db)
    mcp_manager = MCPClientManager()

    ctx = get_project_context(cwd=Path.cwd())
    if not ctx or not ctx.get("id"):
        raise click.ClickException("Not in a gobby project directory. Run 'gobby init' first.")

    project_id: str = ctx["id"]
    return task_manager, mcp_manager, project_manager, project_id


def get_sync_service(team_id: str | None = None) -> LinearSyncService:
    """Create LinearSyncService for CLI commands."""
    task_manager, mcp_manager, project_manager, project_id = get_linear_deps()
    return LinearSyncService(
        mcp_manager=mcp_manager,
        task_manager=task_manager,
        project_id=project_id,
        linear_team_id=team_id,
        project_manager=project_manager,
    )


@click.group()
def linear() -> None:
    """Linear integration commands."""
    pass


@linear.command("status")
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
def linear_status(json_format: bool) -> None:
    """Show Linear integration status."""
    try:
        task_manager, mcp_manager, project_manager, project_id = get_linear_deps()

        # Get project info
        project = project_manager.get(project_id)
        linear_team_id = project.linear_team_id if project else None

        # Check Linear MCP availability
        linear = LinearIntegration(mcp_manager)
        available = linear.is_available()
        unavailable_reason = linear.get_unavailable_reason() if not available else None

        # Count linked tasks
        row = task_manager.db.fetchone(
            "SELECT COUNT(*) as count FROM tasks WHERE project_id = ? AND linear_issue_id IS NOT NULL",
            (project_id,),
        )
        linked_count = row["count"] if row else 0

        if json_format:
            click.echo(
                json.dumps(
                    {
                        "project_id": project_id,
                        "linear_team_id": linear_team_id,
                        "linear_available": available,
                        "unavailable_reason": unavailable_reason,
                        "linked_tasks_count": linked_count,
                    },
                    indent=2,
                )
            )
        else:
            click.echo("Linear Integration Status")
            click.echo("=" * 40)
            click.echo(f"Project ID: {project_id}")
            click.echo(f"Linked team: {linear_team_id or '(not linked)'}")
            click.echo(f"Linear MCP available: {'✓' if available else '✗'}")
            if not available:
                click.echo(f"  Reason: {unavailable_reason}")
            click.echo(f"Linked tasks: {linked_count}")

    except click.ClickException:
        raise
    except Exception as e:
        raise click.ClickException(str(e)) from None


@linear.command("link")
@click.argument("team_id")
def linear_link(team_id: str) -> None:
    """Link a Linear team to this project.

    TEAM_ID is the Linear team identifier (e.g., 'ENG-123' or UUID).
    """
    try:
        _, _, project_manager, project_id = get_linear_deps()

        project_manager.update(project_id, linear_team_id=team_id)
        click.echo(f"✓ Linked project to Linear team: {team_id}")

    except click.ClickException:
        raise
    except Exception as e:
        raise click.ClickException(str(e)) from None


@linear.command("unlink")
def linear_unlink() -> None:
    """Remove Linear team link from this project."""
    try:
        _, _, project_manager, project_id = get_linear_deps()

        project_manager.update(project_id, linear_team_id=None)
        click.echo("✓ Unlinked Linear team from project")

    except click.ClickException:
        raise
    except Exception as e:
        raise click.ClickException(str(e)) from None


@linear.command("import")
@click.argument("team_id", required=False)
@click.option("--state", help="Issue state filter (e.g., 'Todo', 'In Progress')")
@click.option("--labels", help="Comma-separated labels to filter issues")
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
def linear_import(
    team_id: str | None, state: str | None, labels: str | None, json_format: bool
) -> None:
    """Import Linear issues as gobby tasks.

    If TEAM_ID is not specified, uses the linked team.
    """
    try:
        task_manager, mcp_manager, project_manager, project_id = get_linear_deps()

        # Get team from argument or project config
        if not team_id:
            project = project_manager.get(project_id)
            team_id = project.linear_team_id if project else None
            if not team_id:
                raise click.ClickException(
                    "No team specified and project not linked to a Linear team. "
                    "Use 'gobby linear link <team_id>' first or specify the team."
                )

        service = LinearSyncService(
            mcp_manager=mcp_manager,
            task_manager=task_manager,
            project_id=project_id,
            linear_team_id=team_id,
        )

        # Run async import
        label_list = labels.split(",") if labels else None
        tasks = asyncio.run(
            service.import_linear_issues(team_id=team_id, state=state, labels=label_list)
        )

        if json_format:
            click.echo(json.dumps({"tasks": tasks, "count": len(tasks)}, indent=2))
        else:
            click.echo(f"✓ Imported {len(tasks)} issues from Linear team {team_id}")
            for task in tasks:
                click.echo(f"  - {task.get('id', 'unknown')}: {task.get('title', 'Untitled')}")

    except click.ClickException:
        raise
    except Exception as e:
        raise click.ClickException(str(e)) from None


@linear.command("sync")
@click.argument("task_id")
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
def linear_sync(task_id: str, json_format: bool) -> None:
    """Sync a task to its linked Linear issue.

    Updates the Linear issue title, description, status, and priority to match the task.
    """
    try:
        task_manager, _, _, _ = get_linear_deps()
        resolved = resolve_task_id(task_manager, task_id)
        if not resolved:
            return

        service = get_sync_service()
        result = asyncio.run(service.sync_task_to_linear(resolved.id))

        if json_format:
            click.echo(json.dumps(result, indent=2))
        else:
            click.echo(f"✓ Synced task {task_id} to Linear")

    except click.ClickException:
        raise
    except ValueError as e:
        raise click.ClickException(str(e)) from None
    except Exception as e:
        raise click.ClickException(str(e)) from None


@linear.command("sync-all")
@click.argument("team_id", required=False)
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
def linear_sync_all(team_id: str | None, json_format: bool) -> None:
    """Bidirectional sync between gobby and Linear.

    Pulls updates from Linear first, then pushes dirty gobby tasks back.
    If TEAM_ID is not specified, uses the linked team.
    """
    try:
        _, _, project_manager, project_id = get_linear_deps()

        if not team_id:
            project = project_manager.get(project_id)
            team_id = project.linear_team_id if project else None
            if not team_id:
                raise click.ClickException(
                    "No team specified and project not linked to a Linear team. "
                    "Use 'gobby linear link <team_id>' first or specify the team."
                )

        service = get_sync_service(team_id)
        result = asyncio.run(service.sync_all(team_id=team_id))

        pull = result["pull"]
        push = result["push"]

        if json_format:
            click.echo(json.dumps(result, indent=2))
        else:
            click.echo("✓ Linear sync complete")
            click.echo(
                f"  Pull: {pull['updated']} updated, "
                f"{pull['skipped']} skipped, "
                f"{pull['errors']} errors"
            )
            click.echo(
                f"  Push: {push['pushed']} pushed, "
                f"{push['skipped']} skipped, "
                f"{push['errors']} errors"
            )

    except click.ClickException:
        raise
    except Exception as e:
        raise click.ClickException(str(e)) from None


@linear.command("auto-sync")
@click.option("--interval", default=300, show_default=True, help="Sync interval in seconds")
@click.option("--disable", is_flag=True, help="Disable the existing auto-sync job")
def linear_auto_sync(interval: int, disable: bool) -> None:
    """Create or manage a cron job for periodic Linear sync.

    Creates an interval-based cron job named 'gobby:linear-sync' that triggers
    bidirectional sync on the given interval. Use --disable to turn it off.
    """
    from gobby.storage.cron import CronJobStorage

    try:
        task_manager, _, _, project_id = get_linear_deps()
        cron_storage = CronJobStorage(task_manager.db)

        existing = cron_storage.get_job_by_name("gobby:linear-sync")

        if disable:
            if not existing:
                raise click.ClickException("No auto-sync job found to disable.")
            cron_storage.update_job(existing.id, enabled=0)
            click.echo("✓ Disabled Linear auto-sync job")
            return

        if existing:
            cron_storage.update_job(
                existing.id,
                interval_seconds=interval,
                enabled=1,
            )
            click.echo(f"✓ Updated Linear auto-sync job: interval={interval}s (id={existing.id})")
        else:
            job = cron_storage.create_job(
                project_id=project_id,
                name="gobby:linear-sync",
                description="Periodic bidirectional sync with Linear",
                schedule_type="interval",
                interval_seconds=interval,
                action_type="handler",
                action_config={"handler": "linear_sync"},
                enabled=True,
            )
            click.echo(f"✓ Created Linear auto-sync job: interval={interval}s (id={job.id})")

    except click.ClickException:
        raise
    except Exception as e:
        raise click.ClickException(str(e)) from None


@linear.command("create")
@click.argument("task_id")
@click.option("--team", "team_id", help="Linear team ID")
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
def linear_create(task_id: str, team_id: str | None, json_format: bool) -> None:
    """Create a Linear issue from a gobby task."""
    try:
        task_manager, _, _, _ = get_linear_deps()
        resolved = resolve_task_id(task_manager, task_id)
        if not resolved:
            return

        service = get_sync_service(team_id)
        result = asyncio.run(service.create_issue_for_task(task_id=resolved.id, team_id=team_id))

        if json_format:
            click.echo(json.dumps(result, indent=2))
        else:
            issue_id = result.get("id", "unknown")
            click.echo(f"✓ Created Linear issue {issue_id} for task {task_id}")

    except click.ClickException:
        raise
    except ValueError as e:
        raise click.ClickException(str(e)) from None
    except Exception as e:
        raise click.ClickException(str(e)) from None
