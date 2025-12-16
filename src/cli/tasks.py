"""
Task management commands.
"""

import json
import logging
from datetime import datetime
from typing import Any

import click
from gobby.storage.database import LocalDatabase
from gobby.storage.tasks import LocalTaskManager, Task
from gobby.sync.tasks import TaskSyncManager
from gobby.utils.project_context import get_project_context

logger = logging.getLogger(__name__)


def get_task_manager() -> LocalTaskManager:
    """Get initialized task manager."""
    db = LocalDatabase()
    return LocalTaskManager(db)


def get_sync_manager() -> TaskSyncManager:
    """Get initialized sync manager."""
    manager = get_task_manager()
    return TaskSyncManager(manager)


def format_task_row(task: Task) -> str:
    """Format a task for list output."""
    status_icon = {
        "open": "○",
        "in_progress": "●",
        "completed": "✓",
        "blocked": "⊗",
    }.get(task.status, "?")

    priority_icon = {
        1: "🔴",  # High
        2: "🟡",  # Medium
        3: "🔵",  # Low
    }.get(task.priority, "⚪")

    # Show full ID for usability - users need complete IDs for commands
    return f"{task.id} {status_icon} {priority_icon} {task.title}"


@click.group()
def tasks() -> None:
    """Manage development tasks."""
    pass


@tasks.command("list")
@click.option("--status", help="Filter by status (open, in_progress, completed, blocked)")
@click.option("--assignee", help="Filter by assignee")
@click.option("--limit", default=50, help="Max tasks to show")
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
def list_tasks(status: str | None, assignee: str | None, limit: int, json_format: bool) -> None:
    """List tasks."""
    project_ctx = get_project_context()
    project_id = project_ctx.get("id") if project_ctx else None

    manager = get_task_manager()
    tasks_list = manager.list_tasks(
        project_id=project_id,
        status=status,
        assignee=assignee,
        limit=limit,
    )

    if json_format:
        click.echo(json.dumps([t.to_dict() for t in tasks_list], indent=2, default=str))
        return

    if not tasks_list:
        click.echo("No tasks found.")
        return

    click.echo(f"Found {len(tasks_list)} tasks:")
    for task in tasks_list:
        click.echo(format_task_row(task))


@tasks.command("create")
@click.argument("title")
@click.option("--description", "-d", help="Task description")
@click.option("--priority", "-p", type=int, default=2, help="Priority (1=High, 2=Med, 3=Low)")
@click.option("--type", "-t", "task_type", default="task", help="Task type")
def create_task(title: str, description: str | None, priority: int, task_type: str) -> None:
    """Create a new task."""
    project_ctx = get_project_context()
    if not project_ctx or "id" not in project_ctx:
        click.echo("Error: Not in a gobby project or project.json missing 'id'.", err=True)
        return

    manager = get_task_manager()
    task = manager.create_task(
        project_id=project_ctx["id"],
        title=title,
        description=description,
        priority=priority,
        task_type=task_type,
    )
    click.echo(f"Created task {task.id[:8]}: {task.title}")


def resolve_task_id(manager: LocalTaskManager, task_id: str) -> Task | None:
    """Resolve a task ID (exact or prefix match) with user-friendly errors."""
    # Try exact match first
    try:
        return manager.get_task(task_id)
    except ValueError:
        pass

    # Try prefix matching
    matches = manager.find_tasks_by_prefix(task_id)

    if len(matches) == 0:
        click.echo(f"Task '{task_id}' not found", err=True)
        return None
    elif len(matches) == 1:
        return matches[0]
    else:
        click.echo(f"Ambiguous task ID '{task_id}' matches {len(matches)} tasks:", err=True)
        for task in matches[:5]:
            click.echo(f"  {task.id}: {task.title}", err=True)
        if len(matches) > 5:
            click.echo(f"  ... and {len(matches) - 5} more", err=True)
        return None


@tasks.command("show")
@click.argument("task_id")
def show_task(task_id: str) -> None:
    """Show details for a task."""
    manager = get_task_manager()
    task = resolve_task_id(manager, task_id)

    if not task:
        return

    click.echo(f"Task: {task.title}")
    click.echo(f"ID: {task.id}")
    click.echo(f"Status: {task.status}")
    click.echo(f"Priority: {task.priority}")
    click.echo(f"Type: {task.task_type}")
    click.echo(f"Created: {task.created_at}")
    click.echo(f"Updated: {task.updated_at}")
    if task.assignee:
        click.echo(f"Assignee: {task.assignee}")
    if task.description:
        click.echo(f"\n{task.description}")


@tasks.command("update")
@click.argument("task_id")
@click.option("--title", help="New title")
@click.option("--status", help="New status")
@click.option("--priority", type=int, help="New priority")
@click.option("--assignee", help="New assignee")
def update_task(
    task_id: str, title: str | None, status: str | None, priority: int | None, assignee: str | None
) -> None:
    """Update a task."""
    manager = get_task_manager()
    resolved = resolve_task_id(manager, task_id)
    if not resolved:
        return

    task = manager.update_task(
        resolved.id,
        title=title,
        status=status,
        priority=priority,
        assignee=assignee,
    )
    click.echo(f"Updated task {task.id[:8]}")


@tasks.command("close")
@click.argument("task_id")
@click.option("--reason", default="completed", help="Reason for closing")
def close_task(task_id: str, reason: str) -> None:
    """Close a task."""
    manager = get_task_manager()
    resolved = resolve_task_id(manager, task_id)
    if not resolved:
        return

    task = manager.close_task(resolved.id, reason=reason)
    click.echo(f"Closed task {task.id[:8]} ({reason})")


@tasks.command("delete")
@click.argument("task_id")
@click.option("--cascade", is_flag=True, help="Delete child tasks")
@click.confirmation_option(prompt="Are you sure you want to delete this task?")
def delete_task(task_id: str, cascade: bool) -> None:
    """Delete a task."""
    manager = get_task_manager()
    resolved = resolve_task_id(manager, task_id)
    if not resolved:
        return

    manager.delete_task(resolved.id, cascade=cascade)
    click.echo(f"Deleted task {resolved.id}")


@tasks.command("sync")
@click.option("--direction", default="both", type=click.Choice(["import", "export", "both"]))
def sync_tasks(direction: str) -> None:
    """Sync tasks with .gobby/tasks.jsonl."""
    manager = get_sync_manager()

    if direction in ["import", "both"]:
        click.echo("Importing tasks...")
        manager.import_from_jsonl()

    if direction in ["export", "both"]:
        click.echo("Exporting tasks...")
        manager.export_to_jsonl()

    click.echo("Sync completed")
