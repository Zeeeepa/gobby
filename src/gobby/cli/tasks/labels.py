"""
Label management commands for tasks.
"""

import click

from gobby.cli.tasks._utils import get_task_manager, resolve_task_id


@click.group("label")
def label_cmd() -> None:
    """Manage task labels."""
    pass


@label_cmd.command("add")
@click.argument("task_id")
@click.argument("label")
def add_label(task_id: str, label: str) -> None:
    """Add a label to a task."""
    manager = get_task_manager()
    resolved = resolve_task_id(manager, task_id)
    if not resolved:
        click.secho(f"Error: Could not resolve task '{task_id}'", fg="red", err=True)
        raise SystemExit(1)

    manager.add_label(resolved.id, label)
    click.echo(f"Added label '{label}' to task {resolved.id}")


@label_cmd.command("remove")
@click.argument("task_id")
@click.argument("label")
def remove_label(task_id: str, label: str) -> None:
    """Remove a label from a task."""
    manager = get_task_manager()
    resolved = resolve_task_id(manager, task_id)
    if not resolved:
        click.secho(f"Error: Could not resolve task '{task_id}'", fg="red", err=True)
        raise SystemExit(1)

    manager.remove_label(resolved.id, label)
    click.echo(f"Removed label '{label}' from task {resolved.id}")
