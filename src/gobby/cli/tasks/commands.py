"""
Task management commands.
"""

import json
import logging
import sys
from pathlib import Path
from typing import Any

import click

from gobby.cli.tasks._utils import (
    check_tasks_enabled,
    get_sync_manager,
    get_task_manager,
    pad_to_width,
    resolve_task_id,
)
from gobby.cli.tasks.ai import (
    complexity_cmd,
    expand_all_cmd,
    expand_task_cmd,
    generate_criteria_cmd,
    import_spec_cmd,
    suggest_cmd,
    validate_task_cmd,
)
from gobby.cli.tasks.crud import (
    blocked_tasks,
    close_task_cmd,
    create_task,
    delete_task,
    list_tasks,
    ready_tasks,
    reopen_task_cmd,
    show_task,
    task_stats,
    update_task,
)
from gobby.cli.tasks.deps import dep_cmd
from gobby.cli.tasks.labels import label_cmd
from gobby.config.app import load_config
from gobby.storage.tasks import LocalTaskManager, Task
from gobby.utils.project_context import get_project_context

logger = logging.getLogger(__name__)


@click.group()
def tasks() -> None:
    """Manage development tasks."""
    check_tasks_enabled()


# Register CRUD commands from extracted module
tasks.add_command(list_tasks)
tasks.add_command(ready_tasks)
tasks.add_command(blocked_tasks)
tasks.add_command(task_stats)
tasks.add_command(create_task)
tasks.add_command(show_task)
tasks.add_command(update_task)
tasks.add_command(close_task_cmd)
tasks.add_command(reopen_task_cmd)
tasks.add_command(delete_task)

# Register AI-powered commands from extracted module
tasks.add_command(validate_task_cmd)
tasks.add_command(generate_criteria_cmd)
tasks.add_command(expand_task_cmd)
tasks.add_command(complexity_cmd)
tasks.add_command(expand_all_cmd)
tasks.add_command(import_spec_cmd)
tasks.add_command(suggest_cmd)


@tasks.command("sync")
@click.option("--import", "do_import", is_flag=True, help="Import tasks from JSONL")
@click.option("--export", "do_export", is_flag=True, help="Export tasks to JSONL")
@click.option("--quiet", "-q", is_flag=True, help="Suppress output")
def sync_tasks(do_import: bool, do_export: bool, quiet: bool) -> None:
    """Sync tasks with .gobby/tasks.jsonl.

    If neither --import nor --export specified, does both.
    """
    manager = get_sync_manager()

    # Default to both if neither specified
    if not do_import and not do_export:
        do_import = True
        do_export = True

    if do_import:
        if not quiet:
            click.echo("Importing tasks...")
        manager.import_from_jsonl()

    if do_export:
        if not quiet:
            click.echo("Exporting tasks...")
        manager.export_to_jsonl()

    if not quiet:
        click.echo("Sync completed")


@tasks.group("compact")
def compact_cmd() -> None:
    """Task compaction commands."""
    pass


@compact_cmd.command("analyze")
@click.option("--days", type=int, default=30, help="Days blocked threshold")
def compact_analyze(days: int) -> None:
    """Find tasks eligible for compaction."""
    manager = get_task_manager()
    from gobby.storage.compaction import TaskCompactor

    compactor = TaskCompactor(manager)
    candidates = compactor.find_candidates(days_closed=days)

    if not candidates:
        click.echo("No compaction candidates found.")
        return

    click.echo(f"Found {len(candidates)} candidates closed > {days} days:")
    for task in candidates:
        click.echo(f"  {task['id']}: {task['title']} (Updated: {task['updated_at']})")


@compact_cmd.command("apply")
@click.option("--id", "task_id", required=True, help="Task ID to compact")
@click.option("--summary", required=True, help="Summary text or file path (@path)")
def compact_apply(task_id: str, summary: str) -> None:
    """Compact a task with a summary."""
    manager = get_task_manager()
    from gobby.storage.compaction import TaskCompactor

    # Handle file input for summary
    if summary.startswith("@"):
        path = summary[1:]
        try:
            with open(path) as f:
                summary_content = f.read()
        except Exception as e:
            click.echo(f"Error reading summary file: {e}", err=True)
            return
    else:
        summary_content = summary

    compactor = TaskCompactor(manager)
    try:
        compactor.compact_task(task_id, summary_content)
        click.echo(f"Compacted task {task_id}.")
    except Exception as e:
        click.echo(f"Error compacting task: {e}", err=True)


@compact_cmd.command("stats")
def compact_stats() -> None:
    """Show compaction statistics."""
    manager = get_task_manager()
    from gobby.storage.compaction import TaskCompactor

    compactor = TaskCompactor(manager)
    stats = compactor.get_stats()

    click.echo("Compaction Statistics:")
    click.echo(f"  Total Closed: {stats['total_closed']}")
    click.echo(f"  Compacted:    {stats['compacted']}")
    click.echo(f"  Rate:         {stats['rate']}%")


# Register subgroups from extracted modules
tasks.add_command(dep_cmd)
tasks.add_command(label_cmd)


@tasks.group("import")
def import_cmd() -> None:
    """Import tasks from external sources."""
    pass


@import_cmd.command("github")
@click.argument("url")
@click.option("--limit", default=50, help="Max issues to import")
def import_github(url: str, limit: int) -> None:
    """Import open issues from GitHub."""
    import asyncio

    manager = get_sync_manager()

    # We need to run async method
    async def run() -> dict[str, Any]:
        result: dict[str, Any] = await manager.import_from_github_issues(url, limit=limit)
        return result

    try:
        result = asyncio.run(run())

        if result["success"]:
            click.echo(result["message"])
            for issue_id in result["imported"]:
                click.echo(f"  Imported {issue_id}")
        else:
            click.echo(f"Error: {result['error']}", err=True)
    except Exception as e:
        click.echo(f"Failed to run import: {e}", err=True)


@tasks.command("stealth")
@click.option("--enable/--disable", default=None, help="Enable or disable stealth mode")
def stealth_cmd(enable: bool | None) -> None:
    """
    Manage stealth mode (store tasks outside repo).

    When enabled, tasks are stored in ~/.gobby/stealth_tasks/ instead of .gobby/tasks.jsonl.
    This prevents task updates from creating Git changes.
    """
    import json
    from pathlib import Path

    ctx = get_project_context()
    if not ctx or "project_path" not in ctx:
        click.echo("Error: Not in a gobby project.", err=True)
        return

    project_root = Path(ctx["project_path"])
    config_path = project_root / ".gobby" / "project.json"

    if not config_path.exists():
        click.echo("Error: project.json not found.", err=True)
        return

    # Read current config
    try:
        with open(config_path) as f:
            config = json.load(f)
    except Exception as e:
        click.echo(f"Error reading project config: {e}", err=True)
        return

    current_state = config.get("tasks_stealth", False)

    if enable is None:
        # Show status
        status = "ENABLED" if current_state else "DISABLED"
        click.echo(f"Stealth mode is currently {status}")
        if current_state:
            click.echo(f"Tasks stored in ~/.gobby/stealth_tasks/{ctx.get('id')}.jsonl")
        else:
            click.echo("Tasks stored in .gobby/tasks.jsonl")
        return

    if enable == current_state:
        click.echo(f"Stealth mode is already {'enabled' if enable else 'disabled'}.")
        return

    # Update config
    config["tasks_stealth"] = enable
    try:
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)
            # Add newline at end of file
            f.write("\n")

        click.echo(f"Stealth mode {'enabled' if enable else 'disabled'}.")
        if enable:
            click.echo("Future tasks will be synced to ~/.gobby/stealth_tasks/")
            click.echo(
                "Note: Existing tasks in .gobby/tasks.jsonl remain there but won't be updated."
            )
        else:
            click.echo("Future tasks will be synced to .gobby/tasks.jsonl")

    except Exception as e:
        click.echo(f"Failed to update config: {e}", err=True)


@tasks.command("doctor")
def doctor_cmd() -> None:
    """Validate task data integrity."""
    manager = get_task_manager()
    from gobby.utils.validation import TaskValidator

    validator = TaskValidator(manager)
    results = validator.validate_all()

    issues_found = False

    orphans = results["orphan_dependencies"]
    if orphans:
        issues_found = True
        click.echo(f"Found {len(orphans)} orphan dependencies:", err=True)
        for d in orphans:
            click.echo(f"  Dependency {d['id']}: {d['task_id']} -> {d['depends_on']}", err=True)
    else:
        click.echo("✓ No orphan dependencies")

    invalid_projects = results["invalid_projects"]
    if invalid_projects:
        issues_found = True
        click.echo(f"Found {len(invalid_projects)} tasks with invalid projects:", err=True)
        for t in invalid_projects:
            click.echo(f"  Task {t['id']}: {t['title']} (Project ID: {t['project_id']})", err=True)
    else:
        click.echo("✓ No invalid projects")

    cycles = results["cycles"]
    if cycles:
        issues_found = True
        click.echo(f"Found {len(cycles)} dependency cycles:", err=True)
        for cycle in cycles:
            click.echo(f"  Cycle: {' -> '.join(cycle)}", err=True)
    else:
        click.echo("✓ No dependency cycles")

    if issues_found:
        click.echo("\nIssues found. Run 'gobby tasks clean' to fix fixable issues.")
        # Exit with error code if issues found
        # (Click handles exit code but we can explicitly exit if needed, usually just return is fine unless we want non-zero)


@tasks.command("clean")
@click.confirmation_option(prompt="This will remove orphaned dependencies. Are you sure?")
def clean_cmd() -> None:
    """Fix data integrity issues (remove orphans)."""
    manager = get_task_manager()
    from gobby.utils.validation import TaskValidator

    validator = TaskValidator(manager)
    count = validator.clean_orphans()

    if count > 0:
        click.echo(f"Removed {count} orphan dependencies.")
    else:
        click.echo("No orphan dependencies found.")


# ============================================================================
# Git Hooks Group
# ============================================================================

GIT_HOOK_SCRIPTS = {
    "pre-commit": '''#!/bin/sh
# Gobby task sync hook - export tasks before commit
# Installed by: gobby tasks hooks install

# Only run if gobby is installed and daemon is running
if command -v gobby >/dev/null 2>&1; then
    gobby tasks sync --export --quiet 2>/dev/null || true
fi
''',
    "post-merge": '''#!/bin/sh
# Gobby task sync hook - import tasks after merge/pull
# Installed by: gobby tasks hooks install

# Only run if gobby is installed and daemon is running
if command -v gobby >/dev/null 2>&1; then
    gobby tasks sync --import --quiet 2>/dev/null || true
fi
''',
    "post-checkout": '''#!/bin/sh
# Gobby task sync hook - import tasks on branch switch
# Installed by: gobby tasks hooks install

# $3 is 1 if this was a branch checkout (vs file checkout)
if [ "$3" = "1" ]; then
    if command -v gobby >/dev/null 2>&1; then
        gobby tasks sync --import --quiet 2>/dev/null || true
    fi
fi
''',
}


@tasks.group("hooks")
def hooks_group() -> None:
    """Git hook management for automatic task sync."""
    pass


@hooks_group.command("install")
@click.option("--force", is_flag=True, help="Overwrite existing hooks")
def hooks_install(force: bool) -> None:
    """Install git hooks for automatic task sync.

    Installs hooks for:
    - pre-commit: Export tasks before commit
    - post-merge: Import tasks after pull/merge
    - post-checkout: Import tasks on branch switch
    """
    import os
    import stat

    # Find .git directory
    git_dir = Path(".git")
    if not git_dir.exists():
        # Try parent directories
        cwd = Path.cwd()
        for parent in [cwd] + list(cwd.parents):
            if (parent / ".git").exists():
                git_dir = parent / ".git"
                break
        else:
            click.echo("Error: Not in a git repository", err=True)
            raise SystemExit(1)

    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir(exist_ok=True)

    installed = []
    skipped = []

    for hook_name, script in GIT_HOOK_SCRIPTS.items():
        hook_path = hooks_dir / hook_name

        if hook_path.exists() and not force:
            # Check if it's our hook
            content = hook_path.read_text()
            if "gobby tasks" in content.lower():
                skipped.append(f"{hook_name} (already installed)")
            else:
                skipped.append(f"{hook_name} (existing hook, use --force to overwrite)")
            continue

        hook_path.write_text(script)
        # Make executable
        hook_path.chmod(hook_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        installed.append(hook_name)

    if installed:
        click.echo(f"Installed git hooks: {', '.join(installed)}")
    if skipped:
        click.echo(f"Skipped: {', '.join(skipped)}")
    if not installed and not skipped:
        click.echo("No hooks to install")


@hooks_group.command("uninstall")
def hooks_uninstall() -> None:
    """Remove gobby git hooks."""
    # Find .git directory
    git_dir = Path(".git")
    if not git_dir.exists():
        cwd = Path.cwd()
        for parent in [cwd] + list(cwd.parents):
            if (parent / ".git").exists():
                git_dir = parent / ".git"
                break
        else:
            click.echo("Error: Not in a git repository", err=True)
            raise SystemExit(1)

    hooks_dir = git_dir / "hooks"
    removed = []

    for hook_name in GIT_HOOK_SCRIPTS.keys():
        hook_path = hooks_dir / hook_name
        if hook_path.exists():
            content = hook_path.read_text()
            if "gobby tasks" in content.lower():
                hook_path.unlink()
                removed.append(hook_name)

    if removed:
        click.echo(f"Removed git hooks: {', '.join(removed)}")
    else:
        click.echo("No gobby hooks found to remove")


@hooks_group.command("status")
def hooks_status() -> None:
    """Show status of gobby git hooks."""
    # Find .git directory
    git_dir = Path(".git")
    if not git_dir.exists():
        cwd = Path.cwd()
        for parent in [cwd] + list(cwd.parents):
            if (parent / ".git").exists():
                git_dir = parent / ".git"
                break
        else:
            click.echo("Error: Not in a git repository", err=True)
            raise SystemExit(1)

    hooks_dir = git_dir / "hooks"
    click.echo(f"Git hooks directory: {hooks_dir}\n")

    for hook_name in GIT_HOOK_SCRIPTS.keys():
        hook_path = hooks_dir / hook_name
        if hook_path.exists():
            content = hook_path.read_text()
            if "gobby tasks" in content.lower():
                click.echo(f"  {hook_name}: installed (gobby)")
            else:
                click.echo(f"  {hook_name}: exists (not gobby)")
        else:
            click.echo(f"  {hook_name}: not installed")
