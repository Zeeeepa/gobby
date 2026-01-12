"""
Shared utilities for task CLI commands.
"""

import json
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import click
from wcwidth import wcswidth

from gobby.config.app import load_config
from gobby.storage.database import LocalDatabase
from gobby.storage.tasks import LocalTaskManager, Task
from gobby.sync.tasks import TaskSyncManager
from gobby.utils.project_context import get_project_context

if TYPE_CHECKING:
    pass  # LocalTaskManager already imported above

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


def normalize_status(status: str) -> str:
    """Normalize status values for user-friendly CLI input.

    Converts hyphen-separated status names to underscore format:
      in-progress -> in_progress
      needs-decomposition -> needs_decomposition

    Also handles common variations.
    """
    # Replace hyphens with underscores for user convenience
    return status.replace("-", "_")


def get_claimed_task_ids() -> set[str]:
    """Get task IDs that are claimed by active sessions via session_task variable.

    Queries workflow_states for active sessions that have a session_task variable set,
    indicating the task is being actively worked on by that session.

    Supports session_task in multiple formats:
      - #N: Resolved to UUID via seq_num lookup
      - UUID: Used directly
      - Partial UUID prefix: Used for prefix matching

    Returns:
        Set of task UUIDs claimed by active sessions
    """
    try:
        db = LocalDatabase()
        # Join workflow_states with sessions to find active sessions with session_task
        rows = db.fetchall(
            """
            SELECT ws.variables, s.project_id
            FROM workflow_states ws
            JOIN sessions s ON ws.session_id = s.id
            WHERE s.status = 'active'
            AND ws.variables IS NOT NULL
            AND ws.variables != '{}'
            """
        )

        claimed_ids: set[str] = set()
        task_manager = None  # Lazy init

        def resolve_task_ref(ref: str, project_id: str | None) -> str | None:
            """Resolve a task reference to UUID."""
            nonlocal task_manager
            if not ref or ref == "*":
                return None

            # #N format - resolve via seq_num
            if ref.startswith("#"):
                try:
                    seq_num = int(ref[1:])
                    row = db.fetchone(
                        "SELECT id FROM tasks WHERE project_id = ? AND seq_num = ?",
                        (project_id, seq_num),
                    )
                    return row["id"] if row else None
                except (ValueError, TypeError):
                    return None

            # Check if it looks like a UUID (36 chars with dashes)
            if len(ref) == 36 and ref.count("-") == 4:
                return ref

            # Partial UUID prefix - find matching task
            row = db.fetchone(
                "SELECT id FROM tasks WHERE id LIKE ? AND project_id = ?",
                (f"%{ref}%", project_id),
            )
            return row["id"] if row else None

        for row in rows:
            try:
                variables = json.loads(row["variables"]) if row["variables"] else {}
                project_id = row["project_id"]
                if session_task := variables.get("session_task"):
                    # session_task can be: string, list of strings, or "*" (wildcard)
                    if isinstance(session_task, list):
                        for task_ref in session_task:
                            if resolved := resolve_task_ref(task_ref, project_id):
                                claimed_ids.add(resolved)
                    elif session_task != "*":
                        if resolved := resolve_task_ref(session_task, project_id):
                            claimed_ids.add(resolved)
            except (json.JSONDecodeError, TypeError):
                continue

        return claimed_ids
    except Exception as e:
        logger.debug(f"Failed to get claimed task IDs: {e}")
        return set()


def pad_to_width(text: str, width: int) -> str:
    """Pad a string to a visual width, accounting for wide characters like emoji."""
    visual_width: int = wcswidth(text)
    if visual_width < 0:
        visual_width = len(text)  # Fallback if wcswidth fails
    padding: int = width - visual_width
    return text + " " * max(0, padding)


def collect_ancestors(
    tasks: list[Task], task_manager: "LocalTaskManager"
) -> tuple[list[Task], set[str]]:
    """Collect ancestor tasks to maintain tree hierarchy.

    When filtering tasks (e.g., --ready), we may have tasks whose parents
    are not in the filtered list. This function fetches those ancestors
    so the tree structure is preserved.

    Args:
        tasks: The filtered list of tasks
        task_manager: Task manager for fetching ancestors

    Returns:
        Tuple of (combined task list with ancestors, set of original task IDs)
    """
    task_by_id = {t.id: t for t in tasks}
    original_ids = set(task_by_id.keys())
    ancestors_to_fetch: set[str] = set()

    # Find all ancestors that are missing from the list
    for task in tasks:
        parent_id = task.parent_task_id
        while parent_id and parent_id not in task_by_id:
            ancestors_to_fetch.add(parent_id)
            # We need to fetch the parent to check its parent
            try:
                parent = task_manager.get_task(parent_id)
                task_by_id[parent_id] = parent
                parent_id = parent.parent_task_id
            except (ValueError, Exception):
                break

    # Combine original tasks with ancestors
    combined = list(tasks)
    for ancestor_id in ancestors_to_fetch:
        if ancestor_id in task_by_id:
            combined.append(task_by_id[ancestor_id])

    return combined, original_ids


def sort_tasks_for_tree(tasks: list[Task]) -> list[Task]:
    """Sort tasks for tree display (parent before children, depth-first).

    Returns a new list with tasks sorted in tree traversal order.
    Preserves the input order within each parent group (respecting
    topological sort from storage layer).
    """
    task_by_id = {t.id: t for t in tasks}
    # Preserve input order via index lookup
    input_order = {t.id: i for i, t in enumerate(tasks)}

    # Group children by parent
    children_by_parent: dict[str | None, list[Task]] = {}
    for task in tasks:
        parent_id = task.parent_task_id
        if parent_id and parent_id not in task_by_id:
            parent_id = None
        if parent_id not in children_by_parent:
            children_by_parent[parent_id] = []
        children_by_parent[parent_id].append(task)

    # Sort children within each parent by input order (preserves topological sort)
    for children in children_by_parent.values():
        children.sort(key=lambda t: input_order.get(t.id, float("inf")))

    # Build sorted list via depth-first traversal
    sorted_tasks: list[Task] = []

    def traverse(task: Task) -> None:
        sorted_tasks.append(task)
        for child in children_by_parent.get(task.id, []):
            traverse(child)

    for root_task in children_by_parent.get(None, []):
        traverse(root_task)

    return sorted_tasks


def compute_tree_prefixes(
    tasks: list[Task], primary_ids: set[str] | None = None
) -> dict[str, tuple[str, bool]]:
    """Compute tree-style prefixes for each task in the hierarchy.

    Args:
        tasks: List of tasks to compute prefixes for
        primary_ids: Optional set of "primary" task IDs. Tasks not in this set
                     are considered ancestors (shown muted). If None, all tasks
                     are considered primary.

    Returns:
        Dict mapping task_id -> (prefix string, is_primary).
        prefix is e.g., "├── ", "│   └── "
        is_primary is True if task is in primary_ids (or primary_ids is None)
    """
    task_by_id = {t.id: t for t in tasks}
    # Preserve input order via index lookup
    input_order = {t.id: i for i, t in enumerate(tasks)}
    if primary_ids is None:
        primary_ids = set(task_by_id.keys())

    # Group children by parent
    children_by_parent: dict[str | None, list[Task]] = {}
    for task in tasks:
        parent_id = task.parent_task_id
        if parent_id and parent_id not in task_by_id:
            parent_id = None
        if parent_id not in children_by_parent:
            children_by_parent[parent_id] = []
        children_by_parent[parent_id].append(task)

    # Sort children within each parent by input order (preserves topological sort)
    for children in children_by_parent.values():
        children.sort(key=lambda t: input_order.get(t.id, float("inf")))

    prefixes: dict[str, tuple[str, bool]] = {}

    def compute_prefix(task: Task, ancestor_continues: list[bool]) -> None:
        """Recursively compute prefix for task and its children."""
        is_primary = task.id in primary_ids

        if not task.parent_task_id or task.parent_task_id not in task_by_id:
            # Root task - no prefix
            prefixes[task.id] = ("", is_primary)
        else:
            # Build prefix from ancestor continuation markers
            prefix_parts = []
            for continues in ancestor_continues[:-1]:
                prefix_parts.append("│   " if continues else "    ")
            # Add the branch for this task
            if ancestor_continues:
                is_last = not ancestor_continues[-1]
                prefix_parts.append("└── " if is_last else "├── ")
            prefixes[task.id] = ("".join(prefix_parts), is_primary)

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
COL_ID = 6  # #N format (e.g., #1234)


def format_task_row(
    task: Task,
    tree_prefix: str = "",
    is_primary: bool = True,
    muted: bool = False,
    claimed_task_ids: set[str] | None = None,
) -> str:
    """Format a task for list output.

    Args:
        task: The task to format
        tree_prefix: Tree-style prefix (e.g., "├── ", "│   └── ")
        is_primary: If False, task is an ancestor shown for context (muted style)
        muted: Explicit muted flag (overrides is_primary)
        claimed_task_ids: Set of task IDs claimed by active sessions
    """
    show_muted = muted or not is_primary
    is_claimed = claimed_task_ids is not None and task.id in claimed_task_ids

    # Status icons:
    # ○ = open, unclaimed
    # ◐ = open, claimed by active session
    # ● = in_progress
    # ✓ = completed/closed
    # ⊗ = blocked
    # ⚠ = escalated
    if task.status == "open" and is_claimed:
        status_icon = "◐"  # Open but claimed by active session
    else:
        status_icon = {
            "open": "○",
            "in_progress": "●",
            "completed": "✓",
            "closed": "✓",
            "blocked": "⊗",
            "escalated": "⚠",
        }.get(task.status, "?")

    priority_icon = {
        0: "🟣",  # Critical
        1: "🔴",  # High
        2: "🟡",  # Medium
        3: "🔵",  # Low
        4: "⚪",  # Backlog
    }.get(task.priority, "⚪")

    # Build row with proper visual width padding
    status_col = pad_to_width(status_icon, COL_STATUS)
    priority_col = pad_to_width(priority_icon, COL_PRIORITY)
    # Use #N format for display (seq_num), fallback to short UUID prefix
    task_ref = f"#{task.seq_num}" if task.seq_num else task.id[:8]
    id_col = pad_to_width(task_ref, COL_ID)

    title = task.title
    if show_muted:
        # Use dim ANSI escape for muted ancestors
        # \033[2m = dim, \033[0m = reset
        title = f"\033[2m{task.title}\033[0m"

    return f"{status_col} {priority_col} {id_col} {tree_prefix}{title}"


def format_task_header() -> str:
    """Return header row for task list."""
    status_col = pad_to_width("", COL_STATUS)
    priority_col = pad_to_width("", COL_PRIORITY)
    id_col = pad_to_width("#", COL_ID)

    return f"{status_col} {priority_col} {id_col} TITLE"


def resolve_task_id(
    manager: LocalTaskManager, task_id: str, project_id: str | None = None
) -> Task | None:
    """Resolve a task ID to a Task with user-friendly errors.

    Supports multiple reference formats:
      - #N: Project-scoped seq_num (e.g., #1, #47) - requires project_id
      - 1.2.3: Path cache format - requires project_id
      - UUID: Direct UUID lookup
      - Prefix: ID prefix matching for partial UUIDs

    Args:
        manager: The task manager
        task_id: Task reference in any supported format
        project_id: Project ID for scoped lookups (#N and path formats).
                   If not provided, will try to get from project context.

    Returns:
        The resolved Task, or None if not found (with error message printed)
    """
    from gobby.storage.tasks import TaskNotFoundError

    # Get project_id from context if not provided
    if project_id is None:
        ctx = get_project_context()
        project_id = ctx.get("id") if ctx else None

    # Try #N format, numeric format (treated as #N), or path format (requires project_id)
    if project_id and (task_id.startswith("#") or task_id.isdigit() or _is_path_format(task_id)):
        # Auto-prefix numeric IDs with #
        if task_id.isdigit():
            task_id = f"#{task_id}"

        try:
            resolved_uuid = manager.resolve_task_reference(task_id, project_id)
            return manager.get_task(resolved_uuid)
        except TaskNotFoundError as e:
            click.echo(f"Task '{task_id}' not found: {e}", err=True)
            return None
        except ValueError as e:
            # Deprecation or format errors
            click.echo(f"Error: {e}", err=True)
            return None

    # Try exact UUID match
    try:
        return manager.get_task(task_id)
    except ValueError:
        pass

    # Try prefix matching for partial UUIDs
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


def _is_path_format(ref: str) -> bool:
    """Check if a reference is in path format (e.g., 1.2.3)."""
    if "." not in ref:
        return False
    parts = ref.split(".")
    return all(part.isdigit() for part in parts)
