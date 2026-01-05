"""
CRUD commands for task management.
"""

import json

import click

from gobby.cli.tasks._utils import (
    collect_ancestors,
    compute_tree_prefixes,
    format_task_header,
    format_task_row,
    get_task_manager,
    resolve_task_id,
    sort_tasks_for_tree,
)
from gobby.utils.project_context import get_project_context


@click.command("list")
@click.option("--status", help="Filter by status (open, in_progress, completed, blocked)")
@click.option("--assignee", help="Filter by assignee")
@click.option("--ready", is_flag=True, help="Show only ready tasks (open with no blocking deps)")
@click.option(
    "--blocked", is_flag=True, help="Show only blocked tasks (open with unresolved blockers)"
)
@click.option("--limit", default=50, help="Max tasks to show")
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
def list_tasks(
    status: str | None,
    assignee: str | None,
    ready: bool,
    blocked: bool,
    limit: int,
    json_format: bool,
) -> None:
    """List tasks."""
    if ready and blocked:
        click.echo("Error: --ready and --blocked are mutually exclusive.", err=True)
        return

    project_ctx = get_project_context()
    project_id = project_ctx.get("id") if project_ctx else None

    manager = get_task_manager()

    if ready:
        # Use ready task detection (open tasks with no unresolved blocking dependencies)
        tasks_list = manager.list_ready_tasks(
            project_id=project_id,
            assignee=assignee,
            limit=limit,
        )
        label = "ready tasks"
        empty_msg = "No ready tasks found."
    elif blocked:
        # Show tasks that are blocked by unresolved dependencies
        tasks_list = manager.list_blocked_tasks(
            project_id=project_id,
            limit=limit,
        )
        label = "blocked tasks"
        empty_msg = "No blocked tasks found."
    else:
        tasks_list = manager.list_tasks(
            project_id=project_id,
            status=status,
            assignee=assignee,
            limit=limit,
        )
        label = "tasks"
        empty_msg = "No tasks found."

    if json_format:
        click.echo(json.dumps([t.to_dict() for t in tasks_list], indent=2, default=str))
        return

    if not tasks_list:
        click.echo(empty_msg)
        return

    # For filtered views (ready/blocked), include ancestors for proper tree hierarchy
    primary_ids: set[str] | None = None
    display_tasks = tasks_list
    if ready or blocked:
        display_tasks, primary_ids = collect_ancestors(tasks_list, manager)

    # Sort for proper tree display order
    display_tasks = sort_tasks_for_tree(display_tasks)

    click.echo(f"Found {len(tasks_list)} {label}:")
    click.echo(format_task_header())
    prefixes = compute_tree_prefixes(display_tasks, primary_ids)
    for task in display_tasks:
        prefix_info = prefixes.get(task.id, ("", True))
        tree_prefix, is_primary = prefix_info
        click.echo(format_task_row(task, tree_prefix=tree_prefix, is_primary=is_primary))


@click.command("ready")
@click.option("--limit", "-n", default=10, help="Max results")
@click.option("--priority", "-p", type=int, help="Filter by priority")
@click.option("--type", "-t", "task_type", help="Filter by type")
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
@click.option("--flat", is_flag=True, help="Flat list without tree hierarchy")
def ready_tasks(
    limit: int, priority: int | None, task_type: str | None, json_format: bool, flat: bool
) -> None:
    """List tasks with no unresolved blocking dependencies."""
    manager = get_task_manager()
    tasks_list = manager.list_ready_tasks(
        priority=priority,
        task_type=task_type,
        limit=limit,
    )

    if json_format:
        click.echo(json.dumps([t.to_dict() for t in tasks_list], indent=2, default=str))
        return

    if not tasks_list:
        click.echo("No ready tasks found.")
        return

    click.echo(f"Found {len(tasks_list)} ready tasks:")
    click.echo(format_task_header())

    if flat:
        # Simple flat list without tree structure
        for task in tasks_list:
            click.echo(format_task_row(task))
    else:
        # Include ancestors for proper tree hierarchy
        display_tasks, primary_ids = collect_ancestors(tasks_list, manager)
        display_tasks = sort_tasks_for_tree(display_tasks)
        prefixes = compute_tree_prefixes(display_tasks, primary_ids)
        for task in display_tasks:
            prefix_info = prefixes.get(task.id, ("", True))
            tree_prefix, is_primary = prefix_info
            click.echo(format_task_row(task, tree_prefix=tree_prefix, is_primary=is_primary))


@click.command("blocked")
@click.option("--limit", "-n", default=20, help="Max results")
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
def blocked_tasks(limit: int, json_format: bool) -> None:
    """List blocked tasks with what blocks them."""
    from gobby.storage.task_dependencies import TaskDependencyManager

    manager = get_task_manager()
    dep_manager = TaskDependencyManager(manager.db)
    blocked_list = manager.list_blocked_tasks(limit=limit)

    if json_format:
        # Build detailed structure for JSON output
        result = []
        for task in blocked_list:
            tree = dep_manager.get_dependency_tree(task.id)
            result.append(
                {
                    "task": task.to_dict(),
                    "blocked_by": tree.get("blockers", []),
                }
            )
        click.echo(json.dumps(result, indent=2, default=str))
        return

    if not blocked_list:
        click.echo("No blocked tasks found.")
        return

    click.echo(f"Found {len(blocked_list)} blocked tasks:")
    for task in blocked_list:
        tree = dep_manager.get_dependency_tree(task.id)
        blocker_ids = tree.get("blockers", [])
        click.echo(f"\n○ {task.id[:8]}: {task.title}")
        if blocker_ids:
            click.echo("  Blocked by:")
            for b in blocker_ids:
                blocker_id = b.get("id") if isinstance(b, dict) else b
                if not blocker_id or not isinstance(blocker_id, str):
                    continue

                # Explicit cast to satisfy linter
                bid: str = blocker_id

                try:
                    blocker_task = manager.get_task(bid)
                    status_icon = "✓" if blocker_task.status == "closed" else "○"
                    click.echo(f"    {status_icon} {bid[:8]}: {blocker_task.title}")
                except Exception:
                    click.echo(f"    ? {bid[:8]}: (not found)")


@click.command("stats")
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
def task_stats(json_format: bool) -> None:
    """Show task statistics."""
    manager = get_task_manager()

    # Get counts by status
    all_tasks = manager.list_tasks(limit=10000)
    total = len(all_tasks)
    by_status = {"open": 0, "in_progress": 0, "closed": 0}
    by_priority = {1: 0, 2: 0, 3: 0}
    by_type: dict[str, int] = {}

    for task in all_tasks:
        by_status[task.status] = by_status.get(task.status, 0) + 1
        if task.priority:
            by_priority[task.priority] = by_priority.get(task.priority, 0) + 1
        if task.task_type:
            by_type[task.task_type] = by_type.get(task.task_type, 0) + 1

    # Get ready and blocked counts
    ready_count = len(manager.list_ready_tasks(limit=10000))
    blocked_count = len(manager.list_blocked_tasks(limit=10000))

    stats = {
        "total": total,
        "by_status": by_status,
        "by_priority": {
            "high": by_priority.get(1, 0),
            "medium": by_priority.get(2, 0),
            "low": by_priority.get(3, 0),
        },
        "by_type": by_type,
        "ready": ready_count,
        "blocked": blocked_count,
    }

    if json_format:
        click.echo(json.dumps(stats, indent=2))
        return

    click.echo("Task Statistics:")
    click.echo(f"  Total: {total}")
    click.echo(f"  Open: {by_status.get('open', 0)}")
    click.echo(f"  In Progress: {by_status.get('in_progress', 0)}")
    click.echo(f"  Closed: {by_status.get('closed', 0)}")
    click.echo(f"\n  Ready (no blockers): {ready_count}")
    click.echo(f"  Blocked: {blocked_count}")
    click.echo(f"\n  High Priority: {by_priority.get(1, 0)}")
    click.echo(f"  Medium Priority: {by_priority.get(2, 0)}")
    click.echo(f"  Low Priority: {by_priority.get(3, 0)}")
    if by_type:
        click.echo("\n  By Type:")
        for t, count in sorted(by_type.items(), key=lambda x: -x[1]):
            click.echo(f"    {t}: {count}")


@click.command("create")
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


@click.command("show")
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
    if task.labels:
        click.echo(f"Labels: {', '.join(task.labels)}")
    if task.description:
        click.echo(f"\n{task.description}")


@click.command("update")
@click.argument("task_id")
@click.option("--title", help="New title")
@click.option("--status", help="New status")
@click.option("--priority", type=int, help="New priority")
@click.option("--assignee", help="New assignee")
@click.option("--parent", "parent_task_id", help="Parent task ID (for re-parenting)")
def update_task(
    task_id: str,
    title: str | None,
    status: str | None,
    priority: int | None,
    assignee: str | None,
    parent_task_id: str | None,
) -> None:
    """Update a task."""
    manager = get_task_manager()
    resolved = resolve_task_id(manager, task_id)
    if not resolved:
        return

    # Resolve parent task ID if provided
    resolved_parent_id = None
    if parent_task_id:
        resolved_parent = resolve_task_id(manager, parent_task_id)
        if not resolved_parent:
            return
        resolved_parent_id = resolved_parent.id

    task = manager.update_task(
        resolved.id,
        title=title,
        status=status,
        priority=priority,
        assignee=assignee,
        parent_task_id=resolved_parent_id,
    )
    click.echo(f"Updated task {task.id[:8]}")


@click.command("close")
@click.argument("task_id")
@click.option("--reason", default="completed", help="Reason for closing")
@click.option("--skip-validation", is_flag=True, help="Skip validation checks")
@click.option("--force", "-f", is_flag=True, help="Alias for --skip-validation")
def close_task_cmd(task_id: str, reason: str, skip_validation: bool, force: bool) -> None:
    """Close a task.

    Parent tasks require all children to be closed first.
    Use --skip-validation or --force for wont_fix, duplicate, etc.
    """
    manager = get_task_manager()
    resolved = resolve_task_id(manager, task_id)
    if not resolved:
        return

    skip = skip_validation or force

    if not skip:
        # Check if task has children (is a parent task)
        children = manager.list_tasks(parent_task_id=resolved.id, limit=1000)

        if children:
            # Parent task: must have all children closed
            open_children = [c for c in children if c.status != "closed"]
            if open_children:
                click.echo(f"Cannot close: {len(open_children)} child tasks still open:", err=True)
                for c in open_children[:5]:
                    click.echo(f"  - {c.id}: {c.title}", err=True)
                if len(open_children) > 5:
                    click.echo(f"  ... and {len(open_children) - 5} more", err=True)
                click.echo("\nUse --force to close anyway.", err=True)
                return

    task = manager.close_task(resolved.id, reason=reason)
    click.echo(f"Closed task {task.id[:8]} ({reason})")


@click.command("reopen")
@click.argument("task_id")
@click.option("--reason", "-r", default=None, help="Reason for reopening")
def reopen_task_cmd(task_id: str, reason: str | None) -> None:
    """Reopen a closed task.

    Sets status back to 'open' and clears closed_at, closed_reason, etc.
    """
    manager = get_task_manager()
    resolved = resolve_task_id(manager, task_id)
    if not resolved:
        return

    if resolved.status != "closed":
        click.echo(f"Task {resolved.id[:8]} is not closed (status: {resolved.status})", err=True)
        return

    task = manager.reopen_task(resolved.id, reason=reason)
    if reason:
        click.echo(f"Reopened task {task.id[:8]} ({reason})")
    else:
        click.echo(f"Reopened task {task.id[:8]}")


@click.command("delete")
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


@click.command("de-escalate")
@click.argument("task_id")
@click.option("--reason", "-r", required=True, help="Reason for de-escalation")
@click.option("--reset-validation", is_flag=True, help="Reset validation fail count")
def de_escalate_cmd(task_id: str, reason: str, reset_validation: bool) -> None:
    """Return an escalated task to open status.

    Use after human intervention resolves the issue that caused escalation.
    """
    manager = get_task_manager()
    resolved = resolve_task_id(manager, task_id)
    if not resolved:
        return

    if resolved.status != "escalated":
        click.echo(
            f"Task {resolved.id[:8]} is not escalated (status: {resolved.status})",
            err=True,
        )
        return

    # Build update kwargs
    update_kwargs: dict[str, str | int | None] = {
        "status": "open",
        "escalated_at": None,
        "escalation_reason": None,
    }
    if reset_validation:
        update_kwargs["validation_fail_count"] = 0

    manager.update_task(resolved.id, **update_kwargs)
    click.echo(f"De-escalated task {resolved.id[:8]} ({reason})")
    if reset_validation:
        click.echo("  Validation fail count reset to 0")


@click.command("validation-history")
@click.argument("task_id")
@click.option("--clear", is_flag=True, help="Clear validation history")
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
def validation_history_cmd(task_id: str, clear: bool, json_format: bool) -> None:
    """View or clear validation history for a task."""
    from gobby.tasks.validation_history import ValidationHistoryManager

    manager = get_task_manager()
    resolved = resolve_task_id(manager, task_id)
    if not resolved:
        return

    history_manager = ValidationHistoryManager(manager.db)

    if clear:
        history_manager.clear_history(resolved.id)
        manager.update_task(resolved.id, validation_fail_count=0)
        click.echo(f"Cleared validation history for {resolved.id[:8]}")
        return

    iterations = history_manager.get_iteration_history(resolved.id)

    if json_format:
        result = {
            "task_id": resolved.id,
            "iterations": [
                {
                    "iteration": it.iteration,
                    "status": it.status,
                    "feedback": it.feedback,
                    "issues": [i.to_dict() for i in (it.issues or [])],
                    "created_at": it.created_at,
                }
                for it in iterations
            ],
        }
        click.echo(json.dumps(result, indent=2, default=str))
        return

    if not iterations:
        click.echo(f"No validation history for task {resolved.id[:8]}")
        return

    click.echo(f"Validation history for {resolved.id[:8]}:")
    for it in iterations:
        click.echo(f"\n  Iteration {it.iteration}: {it.status}")
        if it.feedback:
            feedback_preview = it.feedback[:100] + "..." if len(it.feedback) > 100 else it.feedback
            click.echo(f"    Feedback: {feedback_preview}")
        if it.issues:
            click.echo(f"    Issues: {len(it.issues)}")
        click.echo(f"    Created: {it.created_at}")
