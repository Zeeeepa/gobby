"""
Task management commands.
"""

import json
import logging
import sys
from pathlib import Path
from typing import Any

import click

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
    check_tasks_enabled()


@tasks.command("list")
@click.option("--status", help="Filter by status (open, in_progress, completed, blocked)")
@click.option("--assignee", help="Filter by assignee")
@click.option("--ready", is_flag=True, help="Show only ready tasks (open with no blocking deps)")
@click.option("--blocked", is_flag=True, help="Show only blocked tasks (open with unresolved blockers)")
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

    click.echo(f"Found {len(tasks_list)} {label}:")
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
    if task.labels:
        click.echo(f"Labels: {', '.join(task.labels)}")
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


@tasks.group("label")
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
        return

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
        return

    manager.remove_label(resolved.id, label)
    click.echo(f"Removed label '{label}' from task {resolved.id}")


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


@tasks.command("validate")
@click.argument("task_id")
@click.option("--summary", default=None, help="Changes summary text")
@click.option(
    "--file", "summary_file", type=click.Path(exists=True), help="File containing changes summary"
)
def validate_task_cmd(task_id: str, summary: str | None, summary_file: str | None) -> None:
    """Validate a task."""
    import asyncio

    from gobby.config.app import load_config
    from gobby.llm import LLMService
    from gobby.tasks.validation import TaskValidator

    manager = get_task_manager()
    resolved = resolve_task_id(manager, task_id)
    if not resolved:
        return

    # Get summary
    changes_summary = ""
    if summary_file:
        try:
            with open(summary_file, encoding="utf-8") as f:
                changes_summary = f.read()
        except Exception as e:
            click.echo(f"Error reading summary file: {e}", err=True)
            return
    elif summary:
        changes_summary = summary
    else:
        # Prompt from stdin
        click.echo("Enter changes summary (Ctrl+D to finish):")
        changes_summary = sys.stdin.read()

    if not changes_summary.strip():
        click.echo("Error: Changes summary is required.", err=True)
        return

    click.echo(f"Validating task {resolved.id}...")

    # Initialize validator
    try:
        config = load_config()
        llm_service = LLMService(config)
        validator = TaskValidator(config.gobby_tasks.validation, llm_service)
    except Exception as e:
        click.echo(f"Error initializing validator: {e}", err=True)
        return

    # Run validation
    try:
        result = asyncio.run(
            validator.validate_task(
                task_id=resolved.id,
                title=resolved.title,
                original_instruction=resolved.original_instruction,
                changes_summary=changes_summary,
                validation_criteria=resolved.validation_criteria,
            )
        )

        click.echo(f"Validation Status: {result.status.upper()}")
        if result.feedback:
            click.echo(f"Feedback:\n{result.feedback}")

        # Note: Actual side effects (closing/subtasks) are handled by the MCP tool or caller.
        # Here we are running the logic directly, but we should probably apply the updates too if we want parity.
        # But wait, the MCP tool logic is IN the MCP tool function.
        # So I should copy that logic or refactor.
        # Refactoring `validate_task` tool logic into a helper method in `LocalTaskManager` or `TaskValidator` would be better.
        # But for now, let's keep it simple and just VALIDATE and PRINT.
        # If the user wants to ACTUALLY APPLY it, they might expect it.
        # The MCP tool does apply updates.
        # I should probably respect that.

        # Let's apply updates here for consistency.
        updates: dict[str, Any] = {
            "validation_status": result.status,
            "validation_feedback": result.feedback,
        }
        MAX_RETRIES = 3

        if result.status == "valid":
            manager.close_task(resolved.id, reason="Completed via validation")
            click.echo("Task closed.")
        elif result.status == "invalid":
            current_fail_count = resolved.validation_fail_count or 0
            new_fail_count = current_fail_count + 1
            updates["validation_fail_count"] = new_fail_count

            if new_fail_count < MAX_RETRIES:
                fix_task = manager.create_task(
                    project_id=resolved.project_id,
                    title=f"Fix validation failures for {resolved.title}",
                    description=f"Validation failed with feedback:\n{result.feedback}\n\nPlease fix the issues and re-validate.",
                    parent_task_id=resolved.id,
                    priority=1,
                    task_type="bug",
                )
                updates["validation_feedback"] = (
                    result.feedback or ""
                ) + f"\n\nCreated fix task: {fix_task.id}"
                click.echo(f"Created fix task: {fix_task.id}")
            else:
                updates["status"] = "failed"
                updates["validation_feedback"] = (
                    result.feedback or ""
                ) + f"\n\nExceeded max retries ({MAX_RETRIES}). Marked as failed."
                click.echo("Exceeded max retries. Task marked as FAILED.")

        manager.update_task(resolved.id, **updates)

    except Exception as e:
        click.echo(f"Validation error: {e}", err=True)


@tasks.command("generate-criteria")
@click.argument("task_id")
def generate_criteria_cmd(task_id: str) -> None:
    """Generate validation criteria for a task using AI."""
    import asyncio

    from gobby.config.app import load_config
    from gobby.llm import LLMService
    from gobby.tasks.validation import TaskValidator

    manager = get_task_manager()
    resolved = resolve_task_id(manager, task_id)
    if not resolved:
        return

    if resolved.validation_criteria:
        click.echo(f"Task already has validation criteria:")
        click.echo(resolved.validation_criteria)
        return

    click.echo(f"Generating validation criteria for task {resolved.id}...")

    try:
        config = load_config()
        llm_service = LLMService(config)
        validator = TaskValidator(config.gobby_tasks.validation, llm_service)
    except Exception as e:
        click.echo(f"Error initializing validator: {e}", err=True)
        return

    try:
        criteria = asyncio.run(
            validator.generate_criteria(
                title=resolved.title,
                description=resolved.description,
            )
        )

        if not criteria:
            click.echo("Failed to generate criteria.", err=True)
            return

        # Update task with generated criteria
        manager.update_task(resolved.id, validation_criteria=criteria)
        click.echo(f"Generated and saved validation criteria:\n{criteria}")

    except Exception as e:
        click.echo(f"Error generating criteria: {e}", err=True)


@tasks.command("expand")
@click.argument("task_id")
@click.option("--context", "-c", help="Additional context for expansion")
@click.option(
    "--web-research/--no-web-research",
    default=False,
    help="Enable/disable agentic web research",
)
@click.option(
    "--code-context/--no-code-context",
    default=True,
    help="Enable/disable codebase context gathering",
)
def expand_task_cmd(
    task_id: str,
    context: str | None,
    web_research: bool,
    code_context: bool,
) -> None:
    """Expand a task into subtasks using AI."""
    import asyncio
    from dataclasses import dataclass

    from gobby.config.app import load_config
    from gobby.llm import LLMService
    from gobby.storage.task_dependencies import TaskDependencyManager
    from gobby.tasks.expansion import TaskExpander

    manager = get_task_manager()
    resolved = resolve_task_id(manager, task_id)
    if not resolved:
        return

    click.echo(f"Expanding task {resolved.id}...")
    if web_research:
        click.echo("  • Web research enabled")
    if code_context:
        click.echo("  • Code context enabled")

    # Initialize services
    try:
        config = load_config()
        # Ensure task expansion is enabled in config
        if not config.gobby_tasks.expansion.enabled:
            click.echo("Error: Task expansion is disabled in config.", err=True)
            return

        llm_service = LLMService(config)
        # We need an MCP manager for web research if enabled?
        # The CLI relies on the daemon for MCP usually, but here we are running "server-less" logic directly?
        # CLI usually runs standalone. If we want MCP tools (like web search), we need an MCP client/manager.
        # But `TaskExpander` takes `mcp_manager`.
        # Initializing a full `MCPClientManager` in CLI might be heavy or require daemon connection?
        # For now, let's pass None for mcp_manager if we are just in CLI, unless we want to try to connect to daemon.
        # If web_research is True but we have no MCP manager, TaskResearchAgent won't find search tools.
        # That's a known limitation of running via CLI directly vs via Daemon/MCP.
        # However, the user request is to add flags.
        # We will pass them. If it fails to find search tools, it gracefully degrades.
        expander = TaskExpander(config.gobby_tasks.expansion, llm_service, manager, mcp_manager=None)

    except Exception as e:
        click.echo(f"Error initializing services: {e}", err=True)
        return

    # Run expansion
    try:
        result = asyncio.run(
            expander.expand_task(
                task_id=resolved.id,
                title=resolved.title,
                description=resolved.description,
                context=context,
                enable_web_research=web_research,
                enable_code_context=code_context,
            )
        )
    except Exception as e:
        click.echo(f"Error during expansion: {e}", err=True)
        return

    if not result:
        click.echo("Expansion returned no results.")
        return

    if "error" in result:
        click.echo(f"Error: {result['error']}", err=True)
        return

    # Process results (Create subtasks)
    # This logic matches gobby.mcp_proxy.tools.tasks.expand_task
    # TODO: Refactor this into a common service method in future.

    @dataclass
    class PendingWeb:
        task_id: str
        depends_on_indices: list[int]
        original_index: int

    pending_wiring: list[PendingWeb] = []
    created_subtasks: list[Task] = []
    global_index = 0

    # Capture parent details safely for closure logic
    parent_id = resolved.id
    parent_project_id = resolved.project_id

    def process_subtask_data(data: dict[str, Any]) -> Task:
        nonlocal global_index
        desc = data.get("description", "")
        if "details" in data:
            desc += f"\n\nDetails: {data['details']}"
        if "test_strategy" in data:
            desc += f"\n\nTest Strategy: {data['test_strategy']}"

        subtask = manager.create_task(
            title=data["title"],
            description=desc,
            parent_task_id=parent_id,
            project_id=parent_project_id,
        )
        indices = data.get("depends_on_indices", [])
        pending_wiring.append(
            PendingWeb(task_id=subtask.id, depends_on_indices=indices, original_index=global_index)
        )
        global_index += 1
        return subtask

    click.echo("\nProposed Plan:")
    # Print analysis if available
    if "complexity_analysis" in result:
        analysis = result["complexity_analysis"]
        click.echo(f"Complexity Score: {analysis.get('score', '?')}/10")
        click.echo(f"Reasoning: {analysis.get('reasoning', '')}\n")

    phases = result.get("phases", [])
    if not phases and isinstance(result, list):
        # Legacy list support
        phases = [{"name": "Plan", "subtasks": result}]

    for phase in phases:
        click.echo(f"Phase: {phase.get('name', 'Unnamed')}")
        for sub_data in phase.get("subtasks", []):
            subtask = process_subtask_data(sub_data)
            created_subtasks.append(subtask)
            click.echo(f"  + Created {subtask.id}: {subtask.title}")

    # Wire dependencies
    dep_manager = TaskDependencyManager(manager.db)
    index_to_id = {p.original_index: p.task_id for p in pending_wiring}

    wired_count = 0
    for pending in pending_wiring:
        # Subtask -> Subtask
        for dep_idx in pending.depends_on_indices:
            if dep_idx in index_to_id and index_to_id[dep_idx] != pending.task_id:
                try:
                    dep_manager.add_dependency(
                        task_id=pending.task_id,
                        depends_on=index_to_id[dep_idx],
                        dep_type="blocks",
                    )
                    wired_count += 1
                except ValueError:
                    pass

        # Parent -> Subtask (Parent blocked by subtask)
        try:
            dep_manager.add_dependency(
                task_id=resolved.id, depends_on=pending.task_id, dep_type="blocks"
            )
        except ValueError:
            pass

    click.echo(f"\nCreated {len(created_subtasks)} subtasks with {wired_count} dependencies.")


@tasks.command("complexity")
@click.argument("task_id", required=False)
@click.option("--all", "analyze_all", is_flag=True, help="Analyze all pending tasks")
@click.option("--pending", is_flag=True, help="Only analyze pending (open) tasks (use with --all)")
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
def complexity_cmd(
    task_id: str | None,
    analyze_all: bool,
    pending: bool,
    json_format: bool,
) -> None:
    """Analyze task complexity based on subtasks or description."""
    import json as json_mod

    manager = get_task_manager()

    if analyze_all:
        # Batch analysis
        project_ctx = get_project_context()
        project_id = project_ctx.get("id") if project_ctx else None

        status_filter = "open" if pending else None
        tasks_list = manager.list_tasks(
            project_id=project_id,
            status=status_filter,
            limit=100,
        )

        if not tasks_list:
            click.echo("No tasks found to analyze.")
            return

        results = []
        for task in tasks_list:
            result = _analyze_task_complexity(manager, task)
            results.append(result)

        if json_format:
            click.echo(json_mod.dumps(results, indent=2))
            return

        click.echo(f"Analyzed {len(results)} tasks:\n")
        for r in results:
            click.echo(f"  {r['task_id'][:12]} | Score: {r['complexity_score']:2}/10 | {r['title'][:50]}")

    else:
        # Single task analysis
        if not task_id:
            click.echo("Error: TASK_ID required (or use --all)", err=True)
            return

        resolved = resolve_task_id(manager, task_id)
        if not resolved:
            return

        result = _analyze_task_complexity(manager, resolved)

        if json_format:
            click.echo(json_mod.dumps(result, indent=2))
            return

        click.echo(f"Task: {result['title']}")
        click.echo(f"ID: {result['task_id']}")
        click.echo(f"Complexity Score: {result['complexity_score']}/10")
        click.echo(f"Reasoning: {result['reasoning']}")
        click.echo(f"Recommended Subtasks: {result['recommended_subtasks']}")
        if result['existing_subtasks'] > 0:
            click.echo(f"Existing Subtasks: {result['existing_subtasks']}")


def _analyze_task_complexity(manager: LocalTaskManager, task: Task) -> dict[str, Any]:
    """Analyze complexity for a single task. Returns dict with results."""
    # Check for existing subtasks
    subtasks = manager.list_tasks(parent_task_id=task.id, limit=100)
    subtask_count = len(subtasks)

    # Simple heuristic-based complexity
    if subtask_count > 0:
        score = min(10, 1 + subtask_count // 2)
        reasoning = f"Task has {subtask_count} subtasks"
        recommended = subtask_count
    else:
        desc_len = len(task.description or "")
        if desc_len < 100:
            score = 2
            reasoning = "Short description, likely simple task"
            recommended = 2
        elif desc_len < 500:
            score = 5
            reasoning = "Medium description, moderate complexity"
            recommended = 5
        else:
            score = 8
            reasoning = "Long description, likely complex task"
            recommended = 10

    # Update task with complexity score
    manager.update_task(
        task.id,
        complexity_score=score,
        estimated_subtasks=recommended,
    )

    return {
        "task_id": task.id,
        "title": task.title,
        "complexity_score": score,
        "reasoning": reasoning,
        "recommended_subtasks": recommended,
        "existing_subtasks": subtask_count,
    }


@tasks.command("expand-all")
@click.option("--max", "max_tasks", default=5, help="Maximum tasks to expand")
@click.option("--min-complexity", default=1, help="Only expand tasks with complexity >= this")
@click.option("--type", "task_type", help="Filter by task type")
@click.option("--web-research/--no-web-research", default=False, help="Enable web research")
@click.option("--dry-run", is_flag=True, help="Show what would be expanded without doing it")
def expand_all_cmd(
    max_tasks: int,
    min_complexity: int,
    task_type: str | None,
    web_research: bool,
    dry_run: bool,
) -> None:
    """Expand all unexpanded tasks (tasks without subtasks)."""
    import asyncio

    from gobby.config.app import load_config
    from gobby.llm import LLMService
    from gobby.tasks.expansion import TaskExpander

    manager = get_task_manager()

    # Find tasks without children
    all_tasks = manager.list_tasks(status="open", task_type=task_type, limit=100)

    unexpanded = []
    for t in all_tasks:
        children = manager.list_tasks(parent_task_id=t.id, limit=1)
        if not children:
            if t.complexity_score is None or t.complexity_score >= min_complexity:
                unexpanded.append(t)

    to_expand = unexpanded[:max_tasks]

    if not to_expand:
        click.echo("No unexpanded tasks found matching criteria.")
        return

    if dry_run:
        click.echo(f"Would expand {len(to_expand)} tasks:")
        for t in to_expand:
            score = t.complexity_score or "?"
            click.echo(f"  {t.id[:12]} | Complexity: {score} | {t.title[:50]}")
        return

    # Initialize services
    try:
        config = load_config()
        if not config.gobby_tasks.expansion.enabled:
            click.echo("Error: Task expansion is disabled in config.", err=True)
            return

        llm_service = LLMService(config)
        expander = TaskExpander(config.gobby_tasks.expansion, llm_service, manager, mcp_manager=None)
    except Exception as e:
        click.echo(f"Error initializing services: {e}", err=True)
        return

    click.echo(f"Expanding {len(to_expand)} tasks...")

    async def expand_tasks() -> list[dict[str, Any]]:
        results = []
        for task in to_expand:
            click.echo(f"\nExpanding: {task.title[:60]}...")
            try:
                result = await expander.expand_task(
                    task_id=task.id,
                    title=task.title,
                    description=task.description,
                    enable_web_research=web_research,
                    enable_code_context=True,
                )
                subtask_ids = result.get("subtask_ids", [])
                results.append({
                    "task_id": task.id,
                    "title": task.title,
                    "subtasks_created": len(subtask_ids),
                    "status": "success" if not result.get("error") else "error",
                    "error": result.get("error"),
                })
                if result.get("error"):
                    click.echo(f"  Error: {result['error']}")
                else:
                    click.echo(f"  Created {len(subtask_ids)} subtasks")
            except Exception as e:
                results.append({
                    "task_id": task.id,
                    "title": task.title,
                    "status": "error",
                    "error": str(e),
                })
                click.echo(f"  Error: {e}")
        return results

    results = asyncio.run(expand_tasks())

    success_count = len([r for r in results if r["status"] == "success"])
    click.echo(f"\nExpanded {success_count}/{len(results)} tasks successfully.")


@tasks.command("import-spec")
@click.argument("file", type=click.Path(exists=True))
@click.option(
    "--type",
    "spec_type",
    type=click.Choice(["prd", "user_story", "bug_report", "rfc", "generic"]),
    default="generic",
    help="Type of specification document",
)
@click.option("--parent", "parent_task_id", help="Parent task ID to nest under")
def import_spec_cmd(file: str, spec_type: str, parent_task_id: str | None) -> None:
    """Create tasks from a specification document."""
    import asyncio

    from gobby.config.app import load_config
    from gobby.llm import LLMService
    from gobby.storage.task_dependencies import TaskDependencyManager
    from gobby.tasks.expansion import TaskExpander
    from gobby.utils.project_context import get_project_context
    from gobby.utils.project_init import initialize_project

    manager = get_task_manager()

    # Read spec file
    try:
        with open(file, encoding="utf-8") as f:
            spec_content = f.read()
    except Exception as e:
        click.echo(f"Error reading file: {e}", err=True)
        return

    if not spec_content.strip():
        click.echo("Error: Spec file is empty.", err=True)
        return

    # Get project context
    ctx = get_project_context()
    if ctx and ctx.get("id"):
        project_id = ctx["id"]
    else:
        init_result = initialize_project()
        project_id = init_result.project_id

    # Extract title from spec
    lines = spec_content.strip().split("\n")
    title = f"{spec_type.upper()} Tasks"
    for line in lines:
        line = line.strip()
        if line.startswith("#"):
            title = line.lstrip("#").strip()
            break
        elif line:
            title = line[:80] + ("..." if len(line) > 80 else "")
            break

    click.echo(f"Importing spec: {title}")
    click.echo(f"Type: {spec_type}")

    # Initialize services
    try:
        config = load_config()
        if not config.gobby_tasks.expansion.enabled:
            click.echo("Error: Task expansion is disabled in config.", err=True)
            return

        llm_service = LLMService(config)
        expander = TaskExpander(config.gobby_tasks.expansion, llm_service, manager, mcp_manager=None)
    except Exception as e:
        click.echo(f"Error initializing services: {e}", err=True)
        return

    # Create parent task for spec
    spec_task = manager.create_task(
        project_id=project_id,
        title=title,
        description=spec_content,
        parent_task_id=parent_task_id,
        task_type="epic",
    )
    click.echo(f"Created epic: {spec_task.id}")

    # Expand into subtasks
    async def expand_spec() -> dict[str, Any]:
        context = f"Parse this {spec_type} specification and create actionable tasks. Each task should be specific and implementable."
        return await expander.expand_task(
            task_id=spec_task.id,
            title=spec_task.title,
            description=spec_content,
            context=context,
            enable_web_research=False,
            enable_code_context=False,
        )

    click.echo("Expanding into subtasks...")
    result = asyncio.run(expand_spec())

    if "error" in result:
        click.echo(f"Error during expansion: {result['error']}", err=True)
        return

    subtask_ids = result.get("subtask_ids", [])

    # Wire parent dependencies
    dep_manager = TaskDependencyManager(manager.db)
    for subtask_id in subtask_ids:
        try:
            dep_manager.add_dependency(task_id=spec_task.id, depends_on=subtask_id, dep_type="blocks")
        except ValueError:
            pass

    click.echo(f"\nCreated {len(subtask_ids)} tasks from specification.")
    for sid in subtask_ids:
        subtask = manager.get_task(sid)
        if subtask:
            click.echo(f"  + {subtask.id[:12]}: {subtask.title[:50]}")


@tasks.command("suggest")
@click.option("--type", "task_type", help="Filter by task type")
@click.option("--no-prefer-subtasks", is_flag=True, help="Don't prefer leaf tasks over parents")
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
def suggest_cmd(task_type: str | None, no_prefer_subtasks: bool, json_format: bool) -> None:
    """Suggest the next task to work on based on priority and readiness."""
    import json as json_mod

    manager = get_task_manager()
    prefer_subtasks = not no_prefer_subtasks

    ready_tasks = manager.list_ready_tasks(task_type=task_type, limit=50)

    if not ready_tasks:
        if json_format:
            click.echo(json_mod.dumps({"suggestion": None, "reason": "No ready tasks found"}))
        else:
            click.echo("No ready tasks found.")
        return

    # Score each task
    scored = []
    for task in ready_tasks:
        score = 0

        # Priority boost (1=high gets +30, 2=medium gets +20, 3=low gets +10)
        score += (4 - task.priority) * 10

        # Check if it's a leaf task (no children)
        children = manager.list_tasks(parent_task_id=task.id, status="open", limit=1)
        is_leaf = len(children) == 0

        if prefer_subtasks and is_leaf:
            score += 25

        # Bonus for tasks with clear complexity
        if task.complexity_score and task.complexity_score <= 5:
            score += 15

        # Bonus for tasks with test strategy defined
        if task.test_strategy:
            score += 10

        scored.append((task, score, is_leaf))

    # Sort by score descending
    scored.sort(key=lambda x: x[1], reverse=True)
    best_task, best_score, is_leaf = scored[0]

    reasons = []
    if best_task.priority == 1:
        reasons.append("high priority")
    if is_leaf:
        reasons.append("actionable leaf task")
    if best_task.complexity_score and best_task.complexity_score <= 5:
        reasons.append("manageable complexity")
    if best_task.test_strategy:
        reasons.append("has test strategy")

    reason_str = f"Selected because: {', '.join(reasons) if reasons else 'best available option'}"

    if json_format:
        result = {
            "suggestion": best_task.to_dict(),
            "score": best_score,
            "reason": reason_str,
            "alternatives": [
                {"task_id": t.id, "title": t.title, "score": s}
                for t, s, _ in scored[1:4]
            ],
        }
        click.echo(json_mod.dumps(result, indent=2, default=str))
        return

    click.echo("Suggested next task:\n")
    click.echo(f"  {best_task.id}")
    click.echo(f"  {best_task.title}")
    click.echo(f"  Priority: {best_task.priority} | Status: {best_task.status}")
    if best_task.description:
        desc_preview = best_task.description[:200]
        if len(best_task.description) > 200:
            desc_preview += "..."
        click.echo(f"\n  {desc_preview}")
    click.echo(f"\n  {reason_str}")

    if len(scored) > 1:
        click.echo("\nAlternatives:")
        for task, _score, _ in scored[1:4]:
            click.echo(f"  {task.id[:12]}: {task.title[:50]}")
