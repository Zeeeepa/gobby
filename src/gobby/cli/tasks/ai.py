"""
AI-powered task commands (expand, validate, suggest, etc.)
"""

import sys
from typing import Any

import click

from gobby.cli.tasks._utils import get_task_manager, resolve_task_id
from gobby.storage.tasks import LocalTaskManager, Task
from gobby.utils.project_context import get_project_context


@click.command("validate")
@click.argument("task_id", metavar="TASK")
@click.option(
    "--summary", "-s", default=None, help="Changes summary text (required for leaf tasks)"
)
@click.option(
    "--file",
    "-f",
    "summary_file",
    type=click.Path(exists=True),
    help="File containing changes summary",
)
@click.option("--max-iterations", "-i", type=int, default=1, help="Max validation retry attempts")
@click.option("--external", is_flag=True, help="Use external validator agent")
@click.option("--skip-build", is_flag=True, help="Skip build verification before validation")
@click.option("--history", is_flag=True, help="Show validation history instead of validating")
@click.option("--recurring", is_flag=True, help="Show recurring issues instead of validating")
def validate_task_cmd(
    task_id: str,
    summary: str | None,
    summary_file: str | None,
    max_iterations: int,
    external: bool,
    skip_build: bool,
    history: bool,
    recurring: bool,
) -> None:
    """Validate a task.

    TASK can be: #N (e.g., #1, #47), path (e.g., 1.2.3), or UUID.

    For parent tasks (with children), validates that all children are closed.
    For leaf tasks, uses LLM-based validation against criteria.

    Use --history to view past validation iterations.
    Use --recurring to see issues that keep appearing.
    """
    import asyncio

    from gobby.config.app import load_config
    from gobby.llm import LLMService
    from gobby.tasks.validation import TaskValidator, ValidationResult
    from gobby.tasks.validation_history import ValidationHistoryManager

    manager = get_task_manager()
    resolved = resolve_task_id(manager, task_id)
    if not resolved:
        return

    # Handle --history flag: show validation history
    if history:
        history_manager = ValidationHistoryManager(manager.db)
        iterations = history_manager.get_iteration_history(resolved.id)
        if not iterations:
            click.echo(f"No validation history for task {resolved.id}")
            return
        click.echo(f"Validation history for {resolved.id}:")
        for it in iterations:
            click.echo(f"\n  Iteration {it.iteration}: {it.status}")
            if it.feedback:
                click.echo(f"    Feedback: {it.feedback[:100]}...")
            if it.issues:
                click.echo(f"    Issues: {len(it.issues)}")
        return

    # Handle --recurring flag: show recurring issues
    if recurring:
        history_manager = ValidationHistoryManager(manager.db)
        summary_data = history_manager.get_recurring_issue_summary(resolved.id)
        has_recurring = history_manager.has_recurring_issues(resolved.id)
        click.echo(f"Recurring issues for {resolved.id}:")
        click.echo(f"  Has recurring issues: {has_recurring}")
        click.echo(f"  Total iterations: {summary_data['total_iterations']}")
        if summary_data["recurring_issues"]:
            for issue in summary_data["recurring_issues"]:
                click.echo(f"  - {issue['title']} (count: {issue['count']})")
        else:
            click.echo("  No recurring issues found.")
        return

    # Check if task has children (is a parent task)
    children = manager.list_tasks(parent_task_id=resolved.id, limit=1000)

    if children:
        # Parent task: validate based on child completion
        open_children = [c for c in children if c.status != "closed"]
        all_closed = len(open_children) == 0

        if all_closed:
            result = ValidationResult(
                status="valid",
                feedback=f"All {len(children)} child tasks are completed.",
            )
        else:
            open_titles = [f"- {c.id}: {c.title}" for c in open_children[:5]]
            remaining = len(open_children) - 5 if len(open_children) > 5 else 0
            feedback = f"{len(open_children)} of {len(children)} child tasks still open:\n"
            feedback += "\n".join(open_titles)
            if remaining > 0:
                feedback += f"\n... and {remaining} more"
            result = ValidationResult(status="invalid", feedback=feedback)

        click.echo(f"Validation Status: {result.status.upper()}")
        if result.feedback:
            click.echo(f"Feedback:\n{result.feedback}")

        # Update validation status
        updates: dict[str, Any] = {
            "validation_status": result.status,
            "validation_feedback": result.feedback,
        }
        if result.status == "valid":
            manager.close_task(resolved.id, reason="All child tasks completed")
            click.echo("Task closed.")
        manager.update_task(resolved.id, **updates)
        return

    # Leaf task: need changes summary
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
        click.echo("Error: Changes summary is required for leaf tasks.", err=True)
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
                description=resolved.description,
                changes_summary=changes_summary,
                validation_criteria=resolved.validation_criteria,
            )
        )

        click.echo(f"Validation Status: {result.status.upper()}")
        if result.feedback:
            click.echo(f"Feedback:\n{result.feedback}")

        # Apply validation updates
        validation_updates: dict[str, Any] = {
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
            validation_updates["validation_fail_count"] = new_fail_count

            if new_fail_count < MAX_RETRIES:
                fix_task = manager.create_task(
                    project_id=resolved.project_id,
                    title=f"Fix validation failures for {resolved.title}",
                    description=f"Validation failed with feedback:\n{result.feedback}\n\nPlease fix the issues and re-validate.",
                    parent_task_id=resolved.id,
                    priority=1,
                    task_type="bug",
                )
                validation_updates["validation_feedback"] = (
                    result.feedback or ""
                ) + f"\n\nCreated fix task: {fix_task.id}"
                click.echo(f"Created fix task: {fix_task.id}")
            else:
                validation_updates["status"] = "failed"
                validation_updates["validation_feedback"] = (
                    result.feedback or ""
                ) + f"\n\nExceeded max retries ({MAX_RETRIES}). Marked as failed."
                click.echo("Exceeded max retries. Task marked as FAILED.")

        manager.update_task(resolved.id, **validation_updates)

    except Exception as e:
        click.echo(f"Validation error: {e}", err=True)


@click.command("generate-criteria")
@click.argument("task_id", required=False)
@click.option(
    "--all", "generate_all", is_flag=True, help="Generate criteria for all tasks missing it"
)
def generate_criteria_cmd(task_id: str | None, generate_all: bool) -> None:
    """Generate validation criteria for a task.

    For parent tasks (with children), sets criteria to 'All child tasks completed'.
    For leaf tasks, uses AI to generate criteria from title/description.

    Use --all to generate criteria for all tasks that don't have it set.
    """
    import asyncio

    from gobby.config.app import load_config
    from gobby.llm import LLMService
    from gobby.tasks.validation import TaskValidator

    manager = get_task_manager()

    if generate_all:
        _generate_criteria_for_all(manager)
        return

    if not task_id:
        click.echo("Error: TASK_ID is required (or use --all)", err=True)
        return

    resolved = resolve_task_id(manager, task_id)
    if not resolved:
        return

    if resolved.validation_criteria:
        click.echo("Task already has validation criteria:")
        click.echo(resolved.validation_criteria)
        return

    # Check if task has children (is a parent task)
    children = manager.list_tasks(parent_task_id=resolved.id, limit=1)

    if children:
        # Parent task: criteria is child completion
        criteria = "All child tasks must be completed (status: closed)."
        manager.update_task(resolved.id, validation_criteria=criteria)
        click.echo(f"Parent task detected. Set validation criteria:\n{criteria}")
        return

    # Leaf task: use LLM to generate criteria
    click.echo(f"Generating validation criteria for task {resolved.id}...")

    try:
        config = load_config()
        llm_service = LLMService(config)
        validator = TaskValidator(config.gobby_tasks.validation, llm_service)
    except Exception as e:
        click.echo(f"Error initializing validator: {e}", err=True)
        return

    try:
        generated_criteria: str | None = asyncio.run(
            validator.generate_criteria(
                title=resolved.title,
                description=resolved.description,
            )
        )

        if not generated_criteria:
            click.echo("Failed to generate criteria.", err=True)
            return

        # Update task with generated criteria
        manager.update_task(resolved.id, validation_criteria=generated_criteria)
        click.echo(f"Generated and saved validation criteria:\n{generated_criteria}")

    except Exception as e:
        click.echo(f"Error generating criteria: {e}", err=True)


def _generate_criteria_for_all(manager: LocalTaskManager) -> None:
    """Generate validation criteria for all tasks missing it."""
    import asyncio

    from gobby.config.app import load_config
    from gobby.llm import LLMService
    from gobby.tasks.validation import TaskValidator

    # Get all open tasks without validation criteria
    all_tasks = manager.list_tasks(status="open", limit=1000)
    tasks_needing_criteria = [t for t in all_tasks if not t.validation_criteria]

    if not tasks_needing_criteria:
        click.echo("All tasks already have validation criteria.")
        return

    click.echo(f"Found {len(tasks_needing_criteria)} tasks without validation criteria.")

    # Initialize validator for leaf tasks
    try:
        config = load_config()
        llm_service = LLMService(config)
        validator = TaskValidator(config.gobby_tasks.validation, llm_service)
    except Exception as e:
        click.echo(f"Error initializing validator: {e}", err=True)
        return

    parent_count = 0
    leaf_count = 0
    error_count = 0

    # Get project context for display
    project_ctx = get_project_context()
    project_name = project_ctx.get("name") if project_ctx else None

    for task in tasks_needing_criteria:
        # Format task ref
        task_ref = task.id
        if task.seq_num:
            if project_name:
                task_ref = f"{project_name}-#{task.seq_num}"
            else:
                task_ref = f"#{task.seq_num}"

        # Check if task has children (is a parent task)
        children = manager.list_tasks(parent_task_id=task.id, limit=1)

        if children:
            # Parent task: criteria is child completion
            parent_criteria = "All child tasks must be completed (status: closed)."
            manager.update_task(task.id, validation_criteria=parent_criteria)
            click.echo(f"\n[parent] {task_ref}: {task.title}")
            click.echo(f"  → {parent_criteria}")
            parent_count += 1
        else:
            # Leaf task: use LLM to generate criteria
            try:
                leaf_criteria: str | None = asyncio.run(
                    validator.generate_criteria(
                        title=task.title,
                        description=task.description,
                    )
                )
                if leaf_criteria:
                    manager.update_task(task.id, validation_criteria=leaf_criteria)
                    click.echo(f"\n[leaf] {task_ref}: {task.title}")
                    # Indent each line of criteria
                    for line in leaf_criteria.strip().split("\n"):
                        click.echo(f"  {line}")
                    leaf_count += 1
                else:
                    click.echo(f"\n[error] {task_ref}: {task.title}")
                    click.echo("  Failed to generate criteria", err=True)
                    error_count += 1
            except Exception as e:
                click.echo(f"\n[error] {task_ref}: {task.title}")
                click.echo(f"  {e}", err=True)
                error_count += 1

    click.echo(
        f"\nDone: {parent_count} parent tasks, {leaf_count} leaf tasks, {error_count} errors"
    )


@click.command("enrich")
@click.argument("task_refs", nargs=-1, required=True, metavar="TASKS...")
@click.option("--cascade", "-c", is_flag=True, help="Also enrich subtasks")
@click.option(
    "--web-research/--no-web-research",
    default=False,
    help="Enable web research for additional context",
)
@click.option(
    "--mcp-tools/--no-mcp-tools",
    default=False,
    help="Enable MCP tools for research",
)
@click.option("--force", "-f", is_flag=True, help="Re-enrich already enriched tasks")
@click.option("--project", "-p", "_project_name", help="Project name or ID (reserved for future use)")
def enrich_cmd(
    task_refs: tuple[str, ...],
    cascade: bool,
    web_research: bool,
    mcp_tools: bool,
    force: bool,
    _project_name: str | None,
) -> None:
    """Enrich tasks with additional context and metadata.

    TASKS can be: #N (e.g., #1, #47), comma-separated (#1,#2,#3), or UUIDs.
    Multiple tasks can be specified separated by spaces or commas.

    Examples:
        gobby tasks enrich #42
        gobby tasks enrich #42,#43,#44
        gobby tasks enrich #42 --web-research --mcp-tools
        gobby tasks enrich #42 --cascade  # Include subtasks
    """
    import asyncio

    from gobby.cli.tasks._utils import parse_task_refs
    from gobby.config.app import load_config
    from gobby.llm import LLMService
    from gobby.tasks.enrich import TaskEnricher

    # Parse task references
    refs = parse_task_refs(task_refs)
    if not refs:
        click.echo("Error: No task references provided", err=True)
        return

    manager = get_task_manager()

    # Resolve all tasks
    tasks_to_enrich: list[Task] = []
    for ref in refs:
        task = resolve_task_id(manager, ref)
        if not task:
            # Error already printed by resolve_task_id
            continue
        tasks_to_enrich.append(task)

        # If cascade, get subtasks too
        if cascade:
            subtasks = manager.list_tasks(parent_task_id=task.id)
            tasks_to_enrich.extend(subtasks)

    if not tasks_to_enrich:
        click.echo("No valid tasks to enrich.", err=True)
        return

    # Initialize enricher
    try:
        config = load_config()
        if not config.gobby_tasks.enrichment.enabled:
            click.echo("Error: Task enrichment is disabled in config.", err=True)
            return

        llm_service = LLMService(config)
        enricher = TaskEnricher(config=config.gobby_tasks.enrichment, llm_service=llm_service)

    except Exception as e:
        click.echo(f"Error initializing enricher: {e}", err=True)
        return

    # Enrich tasks
    async def enrich_tasks() -> None:
        enriched_count = 0
        skipped_count = 0
        error_count = 0

        for task in tasks_to_enrich:
            # Skip if already enriched and not forcing
            if task.is_enriched and not force:
                click.echo(f"Skipping #{task.seq_num}: already enriched (use --force)")
                skipped_count += 1
                continue

            task_ref = f"#{task.seq_num}" if task.seq_num else task.id[:8]
            click.echo(f"Enriching {task_ref}: {task.title[:40]}...")

            try:
                result = await enricher.enrich(
                    task_id=task.id,
                    title=task.title,
                    description=task.description,
                    enable_code_research=True,
                    enable_web_research=web_research,
                    enable_mcp_tools=mcp_tools,
                    generate_validation=True,
                )

                # Update task with enrichment results
                import json as json_mod

                expansion_context = json_mod.dumps(result.to_dict())
                update_kwargs: dict[str, Any] = {
                    "is_enriched": True,
                    "expansion_context": expansion_context,
                }
                if result.category:
                    update_kwargs["category"] = result.category
                if result.complexity_score:
                    update_kwargs["complexity_score"] = result.complexity_score
                if result.validation_criteria:
                    update_kwargs["validation_criteria"] = result.validation_criteria

                manager.update_task(task.id, **update_kwargs)
                click.echo(
                    f"  ✓ Enriched (category={result.category}, complexity={result.complexity_score})"
                )
                enriched_count += 1

            except Exception as e:
                click.echo(f"  ✗ Error: {e}", err=True)
                error_count += 1

        click.echo(
            f"\nDone: {enriched_count} enriched, {skipped_count} skipped, {error_count} errors"
        )

    try:
        asyncio.run(enrich_tasks())
    except Exception as e:
        click.echo(f"Error during enrichment: {e}", err=True)


@click.command("apply-tdd")
@click.argument("task_refs", nargs=-1, required=True, metavar="TASKS...")
@click.option("--cascade", "-c", is_flag=True, help="Also apply TDD to subtasks")
@click.option("--force", "-f", is_flag=True, help="Reapply TDD even if already applied")
@click.option("--project", "-p", "_project_name", help="Project name or ID (reserved for future use)")
def apply_tdd_cmd(
    task_refs: tuple[str, ...],
    cascade: bool,
    force: bool,
    _project_name: str | None,
) -> None:
    """Transform tasks into TDD triplets (test, implement, refactor).

    TASKS can be: #N (e.g., #1, #47), comma-separated (#1,#2,#3), or UUIDs.
    Multiple tasks can be specified separated by spaces or commas.

    Creates three subtasks for each task:
    1. [TEST] Write tests for: <title>
    2. [IMPL] Implement: <title>
    3. [REFACTOR] Refactor: <title>

    Examples:
        gobby tasks apply-tdd #42
        gobby tasks apply-tdd #42,#43
        gobby tasks apply-tdd #42 --cascade
    """
    from gobby.cli.tasks._utils import parse_task_refs
    from gobby.storage.task_dependencies import TaskDependencyManager

    # TDD prefixes (same as in MCP tool)
    TDD_PREFIXES = ("[TEST]", "[IMPL]", "[REFACTOR]")

    # Parse task references
    refs = parse_task_refs(task_refs)
    if not refs:
        click.echo("Error: No task references provided", err=True)
        return

    manager = get_task_manager()
    dep_manager = TaskDependencyManager(manager.db)

    # Resolve all tasks
    tasks_to_transform: list[Task] = []
    for ref in refs:
        task = resolve_task_id(manager, ref)
        if not task:
            continue
        tasks_to_transform.append(task)

        # If cascade, get subtasks too
        if cascade:
            subtasks = manager.list_tasks(parent_task_id=task.id)
            tasks_to_transform.extend(subtasks)

    if not tasks_to_transform:
        click.echo("No valid tasks to transform.", err=True)
        return

    # Apply TDD to each task
    applied_count = 0
    skipped_count = 0
    error_count = 0

    for task in tasks_to_transform:
        # Skip if already TDD-applied (unless force)
        if task.is_tdd_applied and not force:
            click.echo(f"Skipping #{task.seq_num}: TDD already applied (use --force)")
            skipped_count += 1
            continue

        # Skip if title has TDD prefix
        if task.title.startswith(TDD_PREFIXES):
            click.echo(f"Skipping #{task.seq_num}: already a TDD subtask")
            skipped_count += 1
            continue

        task_ref = f"#{task.seq_num}" if task.seq_num else task.id[:8]
        click.echo(f"Applying TDD to {task_ref}: {task.title[:40]}...")

        try:
            # Create TDD triplet
            triplet_ids: list[str] = []
            for prefix in TDD_PREFIXES:
                subtask = manager.create_task(
                    title=f"{prefix} {task.title}",
                    project_id=task.project_id,
                    parent_task_id=task.id,
                    task_type="task",
                    priority=task.priority,
                )
                triplet_ids.append(subtask.id)
                sub_ref = f"#{subtask.seq_num}" if subtask.seq_num else subtask.id[:8]
                click.echo(f"  Created {sub_ref}: {subtask.title[:50]}")

            # Wire dependencies
            test_id, impl_id, refactor_id = triplet_ids
            dep_manager.add_dependency(impl_id, test_id, "blocks")
            dep_manager.add_dependency(refactor_id, impl_id, "blocks")

            # Mark task as TDD-applied
            manager.update_task(
                task.id,
                is_tdd_applied=True,
                validation_criteria="All child tasks must be completed (status: closed).",
            )
            applied_count += 1

        except Exception as e:
            click.echo(f"  Error: {e}", err=True)
            error_count += 1

    click.echo(f"\nDone: {applied_count} transformed, {skipped_count} skipped, {error_count} failed")


@click.command("expand")
@click.argument("task_refs", nargs=-1, required=True, metavar="TASKS...")
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
@click.option("--cascade", is_flag=True, help="Also expand subtasks")
@click.option(
    "--enrich/--no-enrich",
    default=True,
    help="Enable/disable auto-enrichment before expansion",
)
@click.option("--force", "-f", is_flag=True, help="Re-expand already expanded tasks")
@click.option("--project", "-p", "project_name", help="Project name or ID")
def expand_task_cmd(
    task_refs: tuple[str, ...],
    context: str | None,
    web_research: bool,
    code_context: bool,
    cascade: bool,
    enrich: bool,
    force: bool,
    project_name: str | None,
) -> None:
    """Expand tasks into subtasks using AI.

    TASKS can be: #N (e.g., #1, #47), comma-separated (#1,#2,#3), or UUIDs.
    Multiple tasks can be specified separated by spaces or commas.

    Examples:
        gobby tasks expand #42
        gobby tasks expand #42,#43,#44
        gobby tasks expand #42 --cascade --no-enrich
    """
    import asyncio
    from dataclasses import dataclass

    from gobby.cli.tasks._utils import parse_task_refs
    from gobby.config.app import load_config
    from gobby.llm import LLMService
    from gobby.storage.task_dependencies import TaskDependencyManager
    from gobby.tasks.expansion import TaskExpander

    # Parse task references
    refs = parse_task_refs(task_refs)
    if not refs:
        click.echo("Error: No task references provided", err=True)
        return

    manager = get_task_manager()

    # Resolve all tasks
    tasks_to_expand: list[Task] = []
    for ref in refs:
        task = resolve_task_id(manager, ref)
        if not task:
            continue
        tasks_to_expand.append(task)

        # If cascade, get subtasks too
        if cascade:
            subtasks = manager.list_tasks(parent_task_id=task.id)
            tasks_to_expand.extend(subtasks)

    if not tasks_to_expand:
        click.echo("No valid tasks to expand.", err=True)
        return

    # Initialize services
    try:
        config = load_config()
        if not config.gobby_tasks.expansion.enabled:
            click.echo("Error: Task expansion is disabled in config.", err=True)
            return

        llm_service = LLMService(config)
        expander = TaskExpander(
            config.gobby_tasks.expansion, llm_service, manager, mcp_manager=None
        )

    except Exception as e:
        click.echo(f"Error initializing services: {e}", err=True)
        return

    dep_manager = TaskDependencyManager(manager.db)

    # Process each task
    total_created = 0
    total_wired = 0

    for resolved in tasks_to_expand:
        # Check if already expanded (unless force)
        if resolved.is_expanded and not force:
            click.echo(f"Skipping #{resolved.seq_num}: already expanded (use --force)")
            continue

        task_ref = f"#{resolved.seq_num}" if resolved.seq_num else resolved.id[:8]
        click.echo(f"\nExpanding {task_ref}: {resolved.title[:50]}...")
        if web_research:
            click.echo("  • Web research enabled")
        if code_context:
            click.echo("  • Code context enabled")

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
            click.echo(f"  Error during expansion: {e}", err=True)
            continue

        if not result:
            click.echo("  Expansion returned no results.")
            continue

        if "error" in result:
            click.echo(f"  Error: {result['error']}", err=True)
            continue

        # Process results (Create subtasks)
        @dataclass
        class PendingDep:
            task_id: str
            depends_on_indices: list[int]
            original_index: int

        pending_wiring: list[PendingDep] = []
        created_subtasks: list[Task] = []
        global_index = 0

        # Process subtasks for this task
        def create_subtask(
            data: dict[str, Any],
            idx: int,
            parent_id: str = resolved.id,
            parent_project_id: str = resolved.project_id,
        ) -> tuple[Task, int]:
            """Create a subtask from expansion data."""
            desc = data.get("description", "")
            if "category" in data:
                desc += f"\n\nCategory: {data['category']}"

            subtask = manager.create_task(
                title=data["title"],
                description=desc,
                parent_task_id=parent_id,
                project_id=parent_project_id,
            )
            return subtask, idx

        # Print analysis if available
        if "complexity_analysis" in result:
            analysis = result["complexity_analysis"]
            click.echo(f"  Complexity Score: {analysis.get('score', '?')}/10")
            click.echo(f"  Reasoning: {analysis.get('reasoning', '')}")

        phases = result.get("phases", [])
        if not phases and isinstance(result, list):
            # Legacy list support
            phases = [{"name": "Plan", "subtasks": result}]

        for phase in phases:
            click.echo(f"  Phase: {phase.get('name', 'Unnamed')}")
            for sub_data in phase.get("subtasks", []):
                subtask, idx = create_subtask(sub_data, global_index)
                created_subtasks.append(subtask)
                indices = sub_data.get("depends_on_indices", [])
                pending_wiring.append(
                    PendingDep(task_id=subtask.id, depends_on_indices=indices, original_index=idx)
                )
                global_index += 1
                sub_ref = f"#{subtask.seq_num}" if subtask.seq_num else subtask.id[:8]
                click.echo(f"    + Created {sub_ref}: {subtask.title[:50]}")

        # Wire dependencies
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

        click.echo(f"  Created {len(created_subtasks)} subtasks with {wired_count} dependencies")
        total_created += len(created_subtasks)
        total_wired += wired_count

    if len(tasks_to_expand) > 1:
        click.echo(f"\nTotal: {total_created} subtasks with {total_wired} dependencies")


@click.command("complexity")
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
            click.echo(
                f"  {r['task_id'][:12]} | Score: {r['complexity_score']:2}/10 | {r['title'][:50]}"
            )

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
        if result["existing_subtasks"] > 0:
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


@click.command("expand-all")
@click.option("--max", "-m", "max_tasks", default=5, help="Maximum tasks to expand")
@click.option("--min-complexity", default=1, help="Only expand tasks with complexity >= this")
@click.option("--type", "task_type", help="Filter by task type")
@click.option("--web-research/--no-web-research", default=False, help="Enable web research")
@click.option("--dry-run", "-d", is_flag=True, help="Show what would be expanded without doing it")
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
        expander = TaskExpander(
            config.gobby_tasks.expansion, llm_service, manager, mcp_manager=None
        )
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
                results.append(
                    {
                        "task_id": task.id,
                        "title": task.title,
                        "subtasks_created": len(subtask_ids),
                        "status": "success" if not result.get("error") else "error",
                        "error": result.get("error"),
                    }
                )
                if result.get("error"):
                    click.echo(f"  Error: {result['error']}")
                else:
                    click.echo(f"  Created {len(subtask_ids)} subtasks")
            except Exception as e:
                results.append(
                    {
                        "task_id": task.id,
                        "title": task.title,
                        "status": "error",
                        "error": str(e),
                    }
                )
                click.echo(f"  Error: {e}")
        return results

    results = asyncio.run(expand_tasks())

    success_count = len([r for r in results if r["status"] == "success"])
    click.echo(f"\nExpanded {success_count}/{len(results)} tasks successfully.")


@click.command("import-spec")
@click.argument("file", type=click.Path(exists=True))
@click.option(
    "--type",
    "spec_type",
    type=click.Choice(["prd", "user_story", "bug_report", "rfc", "generic"]),
    default="generic",
    help="Type of specification document",
)
@click.option(
    "--parent",
    "parent_task_id",
    help="Parent task reference: #N, N (seq_num), path (1.2.3), or UUID",
)
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

    # Resolve parent_task_id if provided
    resolved_parent_task_id: str | None = None
    if parent_task_id:
        resolved_parent = resolve_task_id(manager, parent_task_id)
        if not resolved_parent:
            return  # resolve_task_id already printed the error
        resolved_parent_task_id = resolved_parent.id

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
        expander = TaskExpander(
            config.gobby_tasks.expansion, llm_service, manager, mcp_manager=None
        )
    except Exception as e:
        click.echo(f"Error initializing services: {e}", err=True)
        return

    # Create parent task for spec
    spec_task = manager.create_task(
        project_id=project_id,
        title=title,
        description=spec_content,
        parent_task_id=resolved_parent_task_id,
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
            dep_manager.add_dependency(
                task_id=spec_task.id, depends_on=subtask_id, dep_type="blocks"
            )
        except ValueError:
            pass

    click.echo(f"\nCreated {len(subtask_ids)} tasks from specification.")
    for sid in subtask_ids:
        subtask = manager.get_task(sid)
        if subtask:
            click.echo(f"  + {subtask.id[:12]}: {subtask.title[:50]}")


@click.command("parse-spec")
@click.argument("spec_path", type=click.Path())
@click.option("--parent", "parent_ref", help="Parent task reference: #N, UUID, or path")
@click.option("--project", "-p", "_project_name", help="Project name (reserved for future use)")
def parse_spec_cmd(
    spec_path: str,
    parent_ref: str | None,
    _project_name: str | None,
) -> None:
    """Parse a spec file and create tasks from checkboxes.

    Reads a markdown file and creates tasks from checkbox items:
    - [ ] Task title
    - [x] Completed task (skipped)

    Examples:
        gobby tasks parse-spec spec.md
        gobby tasks parse-spec spec.md --parent #42
        gobby tasks parse-spec spec.md --project myproject
    """
    import re
    from pathlib import Path

    from gobby.utils.project_context import get_project_context

    # Check file exists
    path = Path(spec_path)
    if not path.exists():
        click.echo(f"Error: File not found: {spec_path}", err=True)
        return

    # Read spec file
    try:
        spec_content = path.read_text(encoding="utf-8")
    except Exception as e:
        click.echo(f"Error reading file: {e}", err=True)
        return

    manager = get_task_manager()

    # Resolve parent task if provided
    parent_task_id: str | None = None
    if parent_ref:
        parent_task = resolve_task_id(manager, parent_ref)
        if not parent_task:
            return  # Error already printed
        parent_task_id = parent_task.id

    # Determine project ID
    project_id: str | None = None
    if _project_name:
        # Look up project by name
        ctx = get_project_context()
        if ctx and ctx.get("name") == _project_name:
            project_id = ctx.get("id")
        else:
            click.echo(
                f"Warning: Project '{_project_name}' not found, using current project", err=True
            )

    if not project_id:
        ctx = get_project_context()
        project_id = ctx.get("id") if ctx else None

    if not project_id:
        click.echo("Error: No project context available.", err=True)
        return

    # Parse checkboxes from spec
    checkbox_pattern = re.compile(r"^\s*-\s*\[\s*([xX ])\s*\]\s*(.+)$", re.MULTILINE)
    matches = checkbox_pattern.findall(spec_content)

    if not matches:
        click.echo("No checkbox items found in spec file.")
        return

    created_count = 0
    skipped_count = 0

    for checked, title in matches:
        title = title.strip()
        if not title:
            continue

        # Skip already checked items
        if checked.lower() == "x":
            click.echo(f"  Skipping (completed): {title[:50]}")
            skipped_count += 1
            continue

        try:
            task = manager.create_task(
                title=title,
                project_id=project_id,
                parent_task_id=parent_task_id,
                task_type="task",
            )
            task_ref = f"#{task.seq_num}" if task.seq_num else task.id[:8]
            click.echo(f"  Created {task_ref}: {title[:50]}")
            created_count += 1
        except Exception as e:
            click.echo(f"  Error creating task '{title[:30]}': {e}", err=True)

    click.echo(f"\nCreated {created_count} tasks, skipped {skipped_count} completed items.")


@click.command("suggest")
@click.option("--type", "-t", "task_type", help="Filter by task type")
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

        # Bonus for tasks with category defined
        if task.category:
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
    if best_task.category:
        reasons.append(f"has category ({best_task.category})")

    reason_str = f"Selected because: {', '.join(reasons) if reasons else 'best available option'}"

    if json_format:
        result = {
            "suggestion": best_task.to_dict(),
            "score": best_score,
            "reason": reason_str,
            "alternatives": [
                {"task_id": t.id, "title": t.title, "score": s} for t, s, _ in scored[1:4]
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
