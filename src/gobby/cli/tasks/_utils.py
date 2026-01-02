"""
Shared utilities for task CLI commands.
"""

import logging
import sys
from pathlib import Path

import click
from wcwidth import wcswidth

from gobby.config.app import load_config
from gobby.storage.database import LocalDatabase
from gobby.storage.tasks import LocalTaskManager, Task
from gobby.sync.tasks import TaskSyncManager
from gobby.utils.project_context import get_project_context

logger = logging.getLogger(__name__)


def check_tasks_enabled() -> None:
    """Check if gobby-tasks is enabled, exit if not."""
    try:
        config = load_config()
        if not config.gobby_tasks.enabled:
            click.echo("Error: gobby-tasks is disabled in config.yaml", err=True)
            sys.exit(1)
    except (FileNotFoundError, AttributeError, ImportError):
        # Expected errors if config missing or invalid
        # Fail open to allow CLI to work even if config is borked
        pass
    except Exception as e:
        # Unexpected errors handling config
        logger.warning(f"Error checking tasks config: {e}")
        pass


def get_task_manager() -> LocalTaskManager:
    """Get initialized task manager."""
    db = LocalDatabase()
    return LocalTaskManager(db)


def get_sync_manager() -> TaskSyncManager:
    """Get initialized sync manager."""
    manager = get_task_manager()

    # Check for stealth mode in project config
    project_ctx = get_project_context()
    export_path = ".gobby/tasks.jsonl"

    if project_ctx and project_ctx.get("tasks_stealth"):
        # Use home directory storage for stealth mode
        project_id = project_ctx.get("id")
        if project_id:
            home = Path.home()
            stealth_dir = home / ".gobby" / "stealth_tasks"
            stealth_dir.mkdir(parents=True, exist_ok=True)
            export_path = str(stealth_dir / f"{project_id}.jsonl")

    return TaskSyncManager(manager, export_path=export_path)


def pad_to_width(text: str, width: int) -> str:
    """Pad a string to a visual width, accounting for wide characters like emoji."""
    visual_width = wcswidth(text)
    if visual_width < 0:
        visual_width = len(text)  # Fallback if wcswidth fails
    padding = width - visual_width
    return text + " " * max(0, padding)


def compute_tree_prefixes(tasks: list[Task]) -> dict[str, str]:
    """Compute tree-style prefixes for each task in the hierarchy.

    Returns a dict mapping task_id -> prefix string (e.g., "├── ", "│   └── ").
    """
    task_by_id = {t.id: t for t in tasks}

    # Group children by parent
    children_by_parent: dict[str | None, list[Task]] = {}
    for task in tasks:
        parent_id = task.parent_task_id
        if parent_id and parent_id not in task_by_id:
            parent_id = None
        if parent_id not in children_by_parent:
            children_by_parent[parent_id] = []
        children_by_parent[parent_id].append(task)

    prefixes: dict[str, str] = {}

    def compute_prefix(task: Task, ancestor_continues: list[bool]) -> None:
        """Recursively compute prefix for task and its children."""
        if not task.parent_task_id or task.parent_task_id not in task_by_id:
            # Root task - no prefix
            prefixes[task.id] = ""
        else:
            # Build prefix from ancestor continuation markers
            prefix_parts = []
            for continues in ancestor_continues[:-1]:
                prefix_parts.append("│   " if continues else "    ")
            # Add the branch for this task
            if ancestor_continues:
                is_last = not ancestor_continues[-1]
                prefix_parts.append("└── " if is_last else "├── ")
            prefixes[task.id] = "".join(prefix_parts)

        # Process children
        children = children_by_parent.get(task.id, [])
        for i, child in enumerate(children):
            is_last_child = i == len(children) - 1
            compute_prefix(child, ancestor_continues + [not is_last_child])

    # Start with root tasks
    for root_task in children_by_parent.get(None, []):
        compute_prefix(root_task, [])

    return prefixes


# Column widths for task table
COL_STATUS = 1  # Status icon
COL_PRIORITY = 2  # Priority emoji (2 visual chars)
COL_ID = 9  # gt-xxxxxx


def format_task_row(task: Task, tree_prefix: str = "") -> str:
    """Format a task for list output.

    Args:
        task: The task to format
        tree_prefix: Tree-style prefix (e.g., "├── ", "│   └── ")
    """
    status_icon = {
        "open": "○",
        "in_progress": "●",
        "completed": "✓",
        "closed": "✓",
        "blocked": "⊗",
    }.get(task.status, "?")

    priority_icon = {
        1: "🔴",  # High
        2: "🟡",  # Medium
        3: "🔵",  # Low
    }.get(task.priority, "⚪")

    # Build row with proper visual width padding
    status_col = pad_to_width(status_icon, COL_STATUS)
    priority_col = pad_to_width(priority_icon, COL_PRIORITY)
    id_col = pad_to_width(task.id, COL_ID)

    return f"{status_col} {priority_col} {id_col} {tree_prefix}{task.title}"


def format_task_header() -> str:
    """Return header row for task list."""
    status_col = pad_to_width("", COL_STATUS)
    priority_col = pad_to_width("", COL_PRIORITY)
    id_col = pad_to_width("ID", COL_ID)

    return f"{status_col} {priority_col} {id_col} TITLE"


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
