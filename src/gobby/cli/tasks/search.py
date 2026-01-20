"""
Search commands for task management.
"""

import json

import click

from gobby.cli.tasks._utils import (
    get_task_manager,
    normalize_status,
)
from gobby.cli.utils import resolve_project_ref


@click.command("search")
@click.argument("query")
@click.option(
    "--status",
    "-s",
    help="Filter by status (open, in_progress, review, closed). Comma-separated for multiple.",
)
@click.option(
    "--type",
    "-t",
    "task_type",
    help="Filter by task type (task, bug, feature, epic)",
)
@click.option(
    "--priority",
    "-p",
    type=int,
    help="Filter by priority (1=High, 2=Medium, 3=Low)",
)
@click.option(
    "--project",
    "project_ref",
    help="Filter by project (name or UUID). Default: current project.",
)
@click.option(
    "--all-projects",
    "-a",
    is_flag=True,
    help="Search all projects instead of just the current project",
)
@click.option(
    "--limit",
    "-n",
    default=20,
    help="Maximum number of results (default: 20)",
)
@click.option(
    "--min-score",
    type=float,
    default=0.0,
    help="Minimum similarity score threshold (0.0-1.0)",
)
@click.option(
    "--json",
    "json_format",
    is_flag=True,
    help="Output as JSON",
)
def search_tasks(
    query: str,
    status: str | None,
    task_type: str | None,
    priority: int | None,
    project_ref: str | None,
    all_projects: bool,
    limit: int,
    min_score: float,
    json_format: bool,
) -> None:
    """Search tasks using semantic TF-IDF search.

    QUERY is the natural language search query.

    Examples:

        gobby tasks search "authentication"

        gobby tasks search "database migration" --status open

        gobby tasks search "refactor" --type bug --limit 10
    """
    if not query.strip():
        click.echo("Error: Query cannot be empty.", err=True)
        return

    # Parse comma-separated statuses
    status_filter: str | list[str] | None = None
    if status:
        if "," in status:
            status_filter = [normalize_status(s.strip()) for s in status.split(",")]
        else:
            status_filter = normalize_status(status)

    # Resolve project
    project_id = None
    if not all_projects:
        project_id = resolve_project_ref(project_ref)

    manager = get_task_manager()

    # Perform search
    results = manager.search_tasks(
        query=query.strip(),
        project_id=project_id,
        status=status_filter,
        task_type=task_type,
        priority=priority,
        limit=limit,
        min_score=min_score,
    )

    if json_format:
        output = {
            "query": query.strip(),
            "count": len(results),
            "tasks": [
                {
                    **task.to_dict(),
                    "score": round(score, 4),
                }
                for task, score in results
            ],
        }
        click.echo(json.dumps(output, indent=2, default=str))
        return

    if not results:
        click.echo(f"No tasks found matching '{query}'.")
        return

    click.echo(f"Found {len(results)} task(s) matching '{query}':\n")

    # Print header
    click.echo(f"{'#':<6} {'Score':<7} {'Status':<12} {'Pri':<4} {'Title'}")
    click.echo("-" * 70)

    for task, score in results:
        # Format similar to list_tasks but with score
        seq_ref = f"#{task.seq_num}" if task.seq_num else task.id[:8]
        status_display = task.status[:11] if task.status else ""
        pri_display = str(task.priority) if task.priority else ""
        title_display = task.title[:45] if task.title else ""

        click.echo(
            f"{seq_ref:<6} {score:<7.3f} {status_display:<12} {pri_display:<4} {title_display}"
        )


@click.command("reindex")
@click.option(
    "--all-projects",
    "-a",
    is_flag=True,
    help="Reindex all projects instead of just the current project",
)
def reindex_tasks(all_projects: bool) -> None:
    """Rebuild the task search index.

    Use this after bulk operations or if search results seem stale.
    """
    # Resolve project
    project_id = None
    if not all_projects:
        project_id = resolve_project_ref(None)

    manager = get_task_manager()

    click.echo("Rebuilding task search index...")
    stats = manager.reindex_search(project_id)

    click.echo(f"Search index rebuilt with {stats.get('item_count', 0)} tasks.")
    if stats.get("vocabulary_size"):
        click.echo(f"Vocabulary size: {stats['vocabulary_size']}")
