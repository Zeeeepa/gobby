"""
Internal MCP tools for Gobby Task System.

Exposes functionality for:
- Task CRUD (create, get, update, close, delete, list)
- Dependencies (add, remove, tree, cycles)
- Ready Work (ready lists, blocked lists)
- Session Integration (link, get)
- Git Sync (trigger sync, status)

These tools are registered with the InternalToolRegistry and accessed
via the downstream proxy pattern (call_tool, list_tools, get_tool_schema).
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.storage.projects import LocalProjectManager
from gobby.storage.session_tasks import SessionTaskManager
from gobby.storage.task_dependencies import TaskDependencyManager
from gobby.storage.tasks import (
    LocalTaskManager,
)
from gobby.storage.worktrees import LocalWorktreeManager
from gobby.sync.tasks import TaskSyncManager
from gobby.tasks.commits import auto_link_commits as auto_link_commits_fn
from gobby.tasks.commits import get_task_diff
from gobby.tasks.expansion import TaskExpander
from gobby.tasks.spec_parser import (
    CheckboxExtractor,
    MarkdownStructureParser,
    TaskHierarchyBuilder,
)
from gobby.tasks.validation import TaskValidator
from gobby.tasks.validation_history import ValidationHistoryManager
from gobby.utils.project_context import get_project_context
from gobby.utils.project_init import initialize_project

if TYPE_CHECKING:
    from gobby.config.app import DaemonConfig

# Reasons for which commit linking and validation are skipped when closing tasks
SKIP_REASONS: frozenset[str] = frozenset(
    {"duplicate", "already_implemented", "wont_fix", "obsolete"}
)

# Patterns that suggest a task is about manual testing/verification
_MANUAL_TEST_PATTERNS: tuple[str, ...] = (
    "verify that",
    "verify the",
    "check that",
    "check the",
    "functional test",
    "functional testing",
    "smoke test",
    "sanity test",
    "sanity check",
    "manual test",
    "manually verify",
    "manually test",
    "manually check",
    "run and check",
    "run and verify",
    "test that the",
    "confirm that",
    "ensure that",
    "validate that",
    "run each command",
    "run the command",
    "verify output",
    "check output",
    "verify functionality",
    "test functionality",
)


def _infer_test_strategy(title: str, description: str | None) -> str | None:
    """
    Infer test_strategy from task title/description patterns.

    Returns 'manual' if the task appears to be about manual verification/testing,
    None otherwise (let the user/LLM decide).
    """
    text = f"{title} {description or ''}".lower()
    for pattern in _MANUAL_TEST_PATTERNS:
        if pattern in text:
            return "manual"
    return None


def create_task_registry(
    task_manager: LocalTaskManager,
    sync_manager: TaskSyncManager,
    task_expander: TaskExpander | None = None,
    task_validator: TaskValidator | None = None,
    config: "DaemonConfig | None" = None,
) -> InternalToolRegistry:
    """
    Create a task tool registry with all task-related tools.

    Args:
        task_manager: LocalTaskManager instance
        sync_manager: TaskSyncManager instance
        task_expander: TaskExpander instance (optional)
        task_validator: TaskValidator instance (optional)
        config: DaemonConfig instance (optional)

    Returns:
        InternalToolRegistry with all task tools registered
    """
    # Get config settings
    show_result_on_create = False
    auto_generate_on_create = True
    auto_generate_on_expand = True
    if config is not None:
        show_result_on_create = config.get_gobby_tasks_config().show_result_on_create
        validation_config = config.get_gobby_tasks_config().validation
        auto_generate_on_create = validation_config.auto_generate_on_create
        auto_generate_on_expand = validation_config.auto_generate_on_expand
    registry = InternalToolRegistry(
        name="gobby-tasks",
        description="Task management - CRUD, dependencies, sync",
    )

    # Create project manager for looking up project repo_path
    project_manager = LocalProjectManager(task_manager.db)

    def get_project_repo_path(project_id: str | None) -> str | None:
        """Get the repo_path for a project by ID."""
        if not project_id:
            return None
        project = project_manager.get(project_id)
        return project.repo_path if project else None

    def get_current_project_id() -> str | None:
        """Get the current project ID from context, or None if not in a project."""
        ctx = get_project_context()
        if ctx and ctx.get("id"):
            project_id: str = ctx["id"]
            return project_id
        return None

    @registry.tool(
        name="expand_task",
        description="Expand a high-level task into smaller subtasks using AI.",
    )
    async def expand_task(
        task_id: str,
        context: str | None = None,
        enable_web_research: bool = False,
        enable_code_context: bool = True,
        generate_validation: bool | None = None,
    ) -> dict[str, Any]:
        """
        Expand a task into subtasks using tool-based expansion.

        The expansion agent calls create_task MCP tool directly to create subtasks,
        wiring dependencies via the 'blocks' parameter.

        Args:
            task_id: ID of the task to expand
            context: Additional context for expansion
            enable_web_research: Whether to enable web research (default: False)
            enable_code_context: Whether to enable code context gathering (default: True)
            generate_validation: Whether to auto-generate validation_criteria for subtasks.
                Defaults to config setting (gobby_tasks.validation.auto_generate_on_expand).

        Returns:
            Dictionary with subtask_ids, tool_calls count, and agent text
        """
        # Use config default if not specified
        should_generate_validation = (
            generate_validation if generate_validation is not None else auto_generate_on_expand
        )
        if not task_expander:
            raise RuntimeError("Task expansion is not enabled")

        task = task_manager.get_task(task_id)
        if not task:
            raise ValueError(f"Task not found: {task_id}")

        result = await task_expander.expand_task(
            task_id=task.id,
            title=task.title,
            description=task.description,
            context=context,
            enable_web_research=enable_web_research,
            enable_code_context=enable_code_context,
        )

        # Handle errors
        if "error" in result:
            return {"error": result["error"], "subtask_ids": [], "tool_calls": 0}

        # Extract subtask IDs (already created by agent via create_task tool calls)
        subtask_ids = result.get("subtask_ids", [])

        # Wire parent → subtask dependencies
        # The parent task is blocked by all subtasks (can't close until children done)
        for subtask_id in subtask_ids:
            try:
                dep_manager.add_dependency(
                    task_id=task.id, depends_on=subtask_id, dep_type="blocks"
                )
            except ValueError:
                # Ignore cycle errors or duplicate deps
                pass

        # Fetch created subtasks for the response (brief format for token efficiency)
        created_subtasks = []
        for sid in subtask_ids:
            subtask = task_manager.get_task(sid)
            if subtask:
                created_subtasks.append({"id": subtask.id, "title": subtask.title})

        # Auto-generate validation criteria for each subtask (when enabled)
        validation_generated = 0
        validation_skipped_reason = None
        if should_generate_validation and subtask_ids:
            if not task_validator:
                import logging

                logging.getLogger(__name__).warning(
                    "generate_validation=True but task_validator not available. "
                    "Enable task validation in config to auto-generate criteria."
                )
                validation_skipped_reason = "task_validator not configured"
            else:
                for sid in subtask_ids:
                    subtask = task_manager.get_task(sid)
                    # Skip epics - they close when all children are closed
                    if subtask and not subtask.validation_criteria and subtask.task_type != "epic":
                        try:
                            criteria = await task_validator.generate_criteria(
                                title=subtask.title,
                                description=subtask.description,
                            )
                            if criteria:
                                task_manager.update_task(sid, validation_criteria=criteria)
                                validation_generated += 1
                        except Exception as e:
                            # Log but don't fail expansion if validation criteria generation fails
                            import logging

                            logging.getLogger(__name__).warning(
                                f"Failed to generate validation criteria for {sid}: {e}"
                            )

        # Update parent task validation criteria
        task_manager.update_task(
            task_id,
            validation_criteria="All child tasks must be completed (status: closed).",
        )

        # Return concise response (use get_task for full details)
        response: dict[str, Any] = {
            "task_id": task_id,
            "tasks_created": len(subtask_ids),
            "subtasks": created_subtasks,  # Brief: [{id, title}, ...]
        }
        if validation_generated > 0:
            response["validation_criteria_generated"] = validation_generated
        if validation_skipped_reason:
            response["validation_skipped_reason"] = validation_skipped_reason
        return response

    @registry.tool(
        name="validate_task",
        description="Validate if a task is completed. Auto-gathers context from recent commits and relevant files if changes_summary not provided.",
    )
    async def validate_task(
        task_id: str,
        changes_summary: str | None = None,
        context_files: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Validate task completion.

        For parent tasks (tasks with children), validation checks if all children are closed.
        For leaf tasks, uses LLM-based validation against criteria.

        If changes_summary is not provided for leaf tasks, uses smart context gathering:
        1. Current uncommitted changes (staged + unstaged)
        2. Multi-commit window (last 10 commits)
        3. File-based analysis (reads files mentioned in criteria)

        Args:
            task_id: ID of the task to validate
            changes_summary: Summary of changes made (optional - auto-gathered if not provided)
            context_files: List of file paths to read for context (optional)

        Returns:
            Validation result
        """
        task = task_manager.get_task(task_id)
        if not task:
            raise ValueError(f"Task not found: {task_id}")

        # Check if task has children (is a parent task)
        children = task_manager.list_tasks(parent_task_id=task_id, limit=1000)

        if children:
            # Parent task: validate based on child completion
            open_children = [c for c in children if c.status != "closed"]
            all_closed = len(open_children) == 0

            from gobby.tasks.validation import ValidationResult

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
        else:
            # Leaf task: use LLM-based validation
            if not task_validator:
                raise RuntimeError("Task validation is not enabled")

            # Use provided changes_summary or auto-gather via smart context
            validation_context = changes_summary
            if not validation_context:
                from gobby.tasks.validation import get_validation_context_smart

                # Get project repo_path for git commands
                repo_path = get_project_repo_path(task.project_id)

                smart_context = get_validation_context_smart(
                    task_title=task.title,
                    validation_criteria=task.validation_criteria,
                    task_description=task.description,
                    cwd=repo_path,
                )
                if smart_context:
                    validation_context = f"Validation context:\n\n{smart_context}"

            if not validation_context:
                raise ValueError(
                    "No changes found for validation. Either provide changes_summary "
                    "or ensure there are uncommitted changes or recent commits."
                )

            result = await task_validator.validate_task(
                task_id=task.id,
                title=task.title,
                description=task.description,
                changes_summary=validation_context,
                validation_criteria=task.validation_criteria,
                context_files=context_files,
                test_strategy=task.test_strategy,
            )

        # Update validation status
        updates: dict[str, Any] = {
            "validation_status": result.status,
            "validation_feedback": result.feedback,
        }

        MAX_RETRIES = 3

        if result.status == "valid":
            # Success: Close task
            task_manager.close_task(task.id, reason="Completed via validation")
        elif result.status == "invalid":
            # Failure: Increment fail count
            current_fail_count = task.validation_fail_count or 0
            new_fail_count = current_fail_count + 1
            updates["validation_fail_count"] = new_fail_count

            feedback_str = result.feedback or "Validation failed (no feedback provided)."

            if new_fail_count < MAX_RETRIES:
                # Create subtask to fix issues
                fix_task = task_manager.create_task(
                    project_id=task.project_id,
                    title=f"Fix validation failures for {task.title}",
                    description=f"Validation failed with feedback:\n{feedback_str}\n\nPlease fix the issues and re-validate.",
                    parent_task_id=task.id,
                    priority=1,  # High priority fix
                    task_type="bug",
                )
                updates["validation_feedback"] = (
                    feedback_str + f"\n\nCreated fix task: {fix_task.id}"
                )
            else:
                # Exceeded retries: Mark as failed
                updates["status"] = "failed"
                updates["validation_feedback"] = (
                    feedback_str + f"\n\nExceeded max retries ({MAX_RETRIES}). Marked as failed."
                )

        task_manager.update_task(task.id, **updates)

        return {
            "is_valid": result.status == "valid",
            "feedback": result.feedback,
            "status": result.status,
            "fail_count": updates.get("validation_fail_count", task.validation_fail_count),
        }

    @registry.tool(
        name="get_validation_status",
        description="Get validation details for a task.",
    )
    def get_validation_status(task_id: str) -> dict[str, Any]:
        """
        Get validation details.

        Args:
            task_id: Task ID

        Returns:
            Validation details
        """
        task = task_manager.get_task(task_id)
        if not task:
            raise ValueError(f"Task not found: {task_id}")

        return {
            "task_id": task.id,
            "validation_status": task.validation_status,
            "validation_feedback": task.validation_feedback,
            "validation_criteria": task.validation_criteria,
            "validation_fail_count": task.validation_fail_count,
            "use_external_validator": task.use_external_validator,
        }

    @registry.tool(
        name="reset_validation_count",
        description="Reset validation failure count for a task.",
    )
    def reset_validation_count(task_id: str) -> dict[str, Any]:
        """
        Reset validation failure count.

        Args:
            task_id: Task ID

        Returns:
            Updated task details
        """
        task = task_manager.get_task(task_id)
        if not task:
            raise ValueError(f"Task not found: {task_id}")

        updated_task = task_manager.update_task(task_id, validation_fail_count=0)
        return {
            "task_id": updated_task.id,
            "validation_fail_count": updated_task.validation_fail_count,
            "message": "Validation failure count reset to 0",
        }

    @registry.tool(
        name="get_validation_history",
        description="Get full validation history for a task, including all iterations, feedback, and issues.",
    )
    def get_validation_history(task_id: str) -> dict[str, Any]:
        """
        Get validation history for a task.

        Returns all validation iterations with their status, feedback, and issues.

        Args:
            task_id: Task ID

        Returns:
            Validation history with all iterations
        """
        task = task_manager.get_task(task_id)
        if not task:
            return {"error": f"Task {task_id} not found"}

        history = validation_history_manager.get_iteration_history(task_id)

        # Convert iterations to serializable format
        history_dicts = []
        for iteration in history:
            iter_dict: dict[str, Any] = {
                "iteration": iteration.iteration,
                "status": iteration.status,
                "feedback": iteration.feedback,
                "issues": [i.to_dict() for i in (iteration.issues or [])],
                "context_type": iteration.context_type,
                "context_summary": iteration.context_summary,
                "validator_type": iteration.validator_type,
                "created_at": iteration.created_at,
            }
            history_dicts.append(iter_dict)

        return {
            "task_id": task_id,
            "history": history_dicts,
            "total_iterations": len(history_dicts),
        }

    @registry.tool(
        name="get_recurring_issues",
        description="Analyze validation history for recurring issues that keep appearing across iterations.",
    )
    def get_recurring_issues(
        task_id: str,
        threshold: int = 2,
    ) -> dict[str, Any]:
        """
        Get recurring issues analysis for a task.

        Finds issues that appear multiple times across validation iterations.

        Args:
            task_id: Task ID
            threshold: Minimum occurrences to consider an issue recurring (default: 2)

        Returns:
            Recurring issues analysis with grouped issues and counts
        """
        task = task_manager.get_task(task_id)
        if not task:
            return {"error": f"Task {task_id} not found"}

        summary = validation_history_manager.get_recurring_issue_summary(
            task_id, threshold=threshold
        )

        has_recurring = validation_history_manager.has_recurring_issues(
            task_id, threshold=threshold
        )

        return {
            "task_id": task_id,
            "recurring_issues": summary["recurring_issues"],
            "total_iterations": summary["total_iterations"],
            "has_recurring": has_recurring,
        }

    @registry.tool(
        name="clear_validation_history",
        description="Clear all validation history for a task. Use after major changes that invalidate previous feedback.",
    )
    def clear_validation_history(
        task_id: str,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """
        Clear validation history for a fresh start.

        Removes all validation iterations and resets the fail count.

        Args:
            task_id: Task ID
            reason: Optional reason for clearing history

        Returns:
            Confirmation of cleared history
        """
        task = task_manager.get_task(task_id)
        if not task:
            return {"error": f"Task {task_id} not found"}

        # Get count before clearing for response
        history = validation_history_manager.get_iteration_history(task_id)
        iterations_count = len(history)

        # Clear history
        validation_history_manager.clear_history(task_id)

        # Also reset validation fail count
        task_manager.update_task(task_id, validation_fail_count=0)

        return {
            "task_id": task_id,
            "cleared": True,
            "iterations_cleared": iterations_count,
            "reason": reason,
        }

    @registry.tool(
        name="de_escalate_task",
        description="Return an escalated task to open status after human intervention resolves the issue.",
    )
    def de_escalate_task(
        task_id: str,
        reason: str,
        reset_validation: bool = False,
    ) -> dict[str, Any]:
        """
        De-escalate a task back to open status.

        Args:
            task_id: Task ID
            reason: Reason for de-escalation (required)
            reset_validation: Also reset validation fail count (default: False)

        Returns:
            Updated task details
        """
        task = task_manager.get_task(task_id)
        if not task:
            return {"error": f"Task {task_id} not found"}

        if task.status != "escalated":
            return {"error": f"Task {task_id} is not escalated (current status: {task.status})"}

        # Build update kwargs
        update_kwargs: dict[str, Any] = {
            "status": "open",
            "escalated_at": None,
            "escalation_reason": None,
        }

        if reset_validation:
            update_kwargs["validation_fail_count"] = 0

        updated_task = task_manager.update_task(task_id, **update_kwargs)

        return {
            "task_id": updated_task.id,
            "status": updated_task.status,
            "escalated_at": updated_task.escalated_at,
            "escalation_reason": updated_task.escalation_reason,
            "de_escalation_reason": reason,
            "validation_reset": reset_validation,
        }

    @registry.tool(
        name="generate_validation_criteria",
        description="Generate validation criteria for a task using AI. Updates the task with the generated criteria.",
    )
    async def generate_validation_criteria(task_id: str) -> dict[str, Any]:
        """
        Generate validation criteria for a task using AI.

        For parent tasks (tasks with children), sets criteria to "All child tasks completed".
        For leaf tasks, uses LLM to generate criteria from title/description.

        Args:
            task_id: ID of the task to generate criteria for

        Returns:
            Generated criteria and updated task info
        """
        task = task_manager.get_task(task_id)
        if not task:
            raise ValueError(f"Task not found: {task_id}")

        if task.validation_criteria:
            return {
                "task_id": task.id,
                "validation_criteria": task.validation_criteria,
                "generated": False,
                "message": "Task already has validation criteria",
            }

        # Check if task has children (is a parent task)
        children = task_manager.list_tasks(parent_task_id=task_id, limit=1)
        criteria: str | None

        if children:
            # Parent task: criteria is child completion
            criteria = "All child tasks must be completed (status: closed)."
        else:
            # Leaf task: use LLM to generate criteria
            if not task_validator:
                raise RuntimeError("Task validation is not enabled")

            criteria = await task_validator.generate_criteria(
                title=task.title,
                description=task.description,
            )

            if not criteria:
                return {
                    "task_id": task.id,
                    "validation_criteria": None,
                    "generated": False,
                    "error": "Failed to generate criteria",
                }

        # Update task with generated criteria
        task_manager.update_task(task_id, validation_criteria=criteria)

        return {
            "task_id": task.id,
            "validation_criteria": criteria,
            "generated": True,
            "is_parent_task": len(children) > 0,
        }

    @registry.tool(
        name="analyze_complexity",
        description="Analyze task complexity based on existing subtasks or description.",
    )
    async def analyze_complexity(task_id: str) -> dict[str, Any]:
        """
        Analyze task complexity.

        With tool-based expansion, this now analyzes existing subtasks if present,
        or estimates complexity from description length. For detailed breakdown,
        use expand_task which creates subtasks directly.

        Args:
            task_id: ID of the task to analyze

        Returns:
            Complexity analysis with score and reasoning
        """
        task = task_manager.get_task(task_id)
        if not task:
            raise ValueError(f"Task not found: {task_id}")

        # Check for existing subtasks
        subtasks = task_manager.list_tasks(parent_task_id=task_id, limit=100)
        subtask_count = len(subtasks)

        # Simple heuristic-based complexity
        if subtask_count > 0:
            # Complexity based on subtask count
            score = min(10, 1 + subtask_count // 2)
            reasoning = f"Task has {subtask_count} subtasks"
            recommended = subtask_count
        else:
            # Estimate from description length
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
        task_manager.update_task(
            task_id,
            complexity_score=score,
            estimated_subtasks=recommended,
        )

        return {
            "task_id": task_id,
            "title": task.title,
            "complexity_score": score,
            "reasoning": reasoning,
            "recommended_subtasks": recommended,
            "existing_subtasks": subtask_count,
            "note": "For detailed breakdown, use expand_task to create subtasks",
        }

    @registry.tool(
        name="expand_all",
        description="Expand all unexpanded tasks (tasks without subtasks) up to a limit.",
    )
    async def expand_all(
        max_tasks: int = 5,
        min_complexity: int = 1,
        task_type: str | None = None,
        enable_web_research: bool = False,
    ) -> dict[str, Any]:
        """
        Expand multiple tasks that haven't been expanded yet.

        Args:
            max_tasks: Maximum number of tasks to expand (default: 5)
            min_complexity: Only expand tasks with complexity >= this value (default: 1)
            task_type: Filter by task type (optional)
            enable_web_research: Enable web research for expansion (default: False)

        Returns:
            Summary of expanded tasks
        """
        if not task_expander:
            raise RuntimeError("Task expansion is not enabled")

        # Find tasks without children (not expanded)
        all_tasks = task_manager.list_tasks(status="open", task_type=task_type, limit=100)

        # Filter to tasks without subtasks
        unexpanded = []
        for t in all_tasks:
            children = task_manager.list_tasks(parent_task_id=t.id, limit=1)
            if not children:
                # Check complexity if we have it
                if t.complexity_score is None or t.complexity_score >= min_complexity:
                    unexpanded.append(t)

        # Limit
        to_expand = unexpanded[:max_tasks]

        results = []
        for task in to_expand:
            try:
                result = await expand_task(
                    task_id=task.id,
                    enable_web_research=enable_web_research,
                    enable_code_context=True,
                )
                tasks_created = result.get("tasks_created", 0)
                results.append(
                    {
                        "task_id": task.id,
                        "title": task.title,
                        "subtasks_created": tasks_created,
                        "status": "success" if not result.get("error") else "error",
                        "error": result.get("error"),
                    }
                )
            except Exception as e:
                results.append(
                    {
                        "task_id": task.id,
                        "title": task.title,
                        "status": "error",
                        "error": str(e),
                    }
                )

        return {
            "expanded_count": len([r for r in results if r["status"] == "success"]),
            "total_attempted": len(results),
            "results": results,
        }

    @registry.tool(
        name="expand_from_spec",
        description="Create tasks from a specification file (markdown, PRD, etc.).",
    )
    async def expand_from_spec(
        spec_path: str,
        parent_task_id: str | None = None,
        task_type: str = "task",
        mode: Literal["auto", "structured", "llm"] = "auto",
    ) -> dict[str, Any]:
        """
        Parse a specification file and create tasks from it.

        Supports three modes for parsing:
        - auto: Detect structure (headings/checkboxes) and use structured if found
        - structured: Parse headings/checkboxes directly, error if no structure
        - llm: Use LLM to interpret entire spec (original behavior)

        For structured/auto modes with hybrid specs (some sections with checkboxes,
        some without), sections without checkboxes fall back to LLM expansion.

        Args:
            spec_path: Path to the specification file (markdown, requirements, etc.)
            parent_task_id: Optional parent task to nest created tasks under
            task_type: Type for created tasks (default: "task")
            mode: Parsing mode - "auto", "structured", or "llm" (default: "auto")

        Returns:
            Dictionary with parent task, created subtasks, and mode used
        """
        # Read the spec file
        path = Path(spec_path).expanduser().resolve()
        if not path.exists():
            return {"error": f"Spec file not found: {spec_path}"}
        if not path.is_file():
            return {"error": f"Path is not a file: {spec_path}"}

        try:
            spec_content = path.read_text(encoding="utf-8")
        except Exception as e:
            return {"error": f"Failed to read spec file: {e}"}

        # Get project context
        ctx = get_project_context()
        if ctx and ctx.get("id"):
            project_id = ctx["id"]
        else:
            init_result = initialize_project()
            project_id = init_result.project_id

        # Extract title from spec (first heading or first line)
        lines = spec_content.strip().split("\n")
        title = "Specification Tasks"
        for line in lines:
            line = line.strip()
            if line.startswith("#"):
                title = line.lstrip("#").strip()
                break
            elif line:
                title = line[:80] + ("..." if len(line) > 80 else "")
                break

        # Detect structure for auto mode
        heading_parser = MarkdownStructureParser()
        checkbox_extractor = CheckboxExtractor(track_headings=True, build_hierarchy=True)

        headings = heading_parser.parse(spec_content)
        checkboxes = checkbox_extractor.extract(spec_content)

        has_structure = bool(headings) or checkboxes.total_count > 0
        effective_mode = mode

        if mode == "auto":
            effective_mode = "structured" if has_structure else "llm"

        if effective_mode == "structured" and not has_structure:
            return {
                "error": "No structure found in spec (no headings or checkboxes). "
                "Use mode='llm' to interpret with AI, or add markdown structure.",
            }

        # Create a parent task for the spec
        spec_task = task_manager.create_task(
            project_id=project_id,
            title=title,
            description=spec_content,
            parent_task_id=parent_task_id,
            task_type="epic",  # Specs typically become epics
        )

        subtask_ids: list[str] = []

        if effective_mode == "structured":
            # Use structured parsing with optional LLM fallback
            builder = TaskHierarchyBuilder(
                task_manager=task_manager,
                project_id=project_id,
                parent_task_id=spec_task.id,
            )

            # Use fallback method if task_expander available (for hybrid specs)
            if headings:
                hierarchy_result = await builder.build_from_headings_with_fallback(
                    headings=headings,
                    checkboxes=checkboxes if checkboxes.total_count > 0 else None,
                    task_expander=task_expander,
                )
                subtask_ids = hierarchy_result.task_ids
            elif checkboxes.total_count > 0:
                # Only checkboxes, no headings
                hierarchy_result = builder.build_from_checkboxes(checkboxes)
                subtask_ids = hierarchy_result.task_ids

        else:
            # LLM mode - original behavior
            if not task_expander:
                return {
                    "error": "Task expansion is not enabled. "
                    "Use mode='structured' for structured specs.",
                    "parent_task_id": spec_task.id,
                }

            llm_result = await task_expander.expand_task(
                task_id=spec_task.id,
                title=spec_task.title,
                description=spec_content,
                context="Parse this specification and create actionable tasks. "
                "Each task should be specific and implementable.",
                enable_web_research=False,
                enable_code_context=False,
            )

            if "error" in llm_result:
                return {
                    "error": llm_result["error"],
                    "parent_task_id": spec_task.id,
                    "mode_used": effective_mode,
                }

            subtask_ids = llm_result.get("subtask_ids", [])

        # Wire parent → subtask dependencies
        for subtask_id in subtask_ids:
            try:
                dep_manager.add_dependency(
                    task_id=spec_task.id, depends_on=subtask_id, dep_type="blocks"
                )
            except ValueError:
                pass

        # Fetch created subtasks (brief format for token efficiency)
        subtasks = []
        for sid in subtask_ids:
            subtask = task_manager.get_task(sid)
            if subtask:
                subtasks.append({"id": subtask.id, "title": subtask.title})

        # Return concise response (use get_task for full details)
        return {
            "parent_task_id": spec_task.id,
            "parent_task_title": spec_task.title,
            "tasks_created": len(subtask_ids),
            "subtasks": subtasks,  # Brief: [{id, title}, ...]
            "mode_used": effective_mode,
        }

    @registry.tool(
        name="expand_from_prompt",
        description="Create tasks from a user prompt (e.g., '/task implement user auth').",
    )
    async def expand_from_prompt(
        prompt: str,
        parent_task_id: str | None = None,
        task_type: str = "task",
    ) -> dict[str, Any]:
        """
        Parse a user prompt and create tasks from it.

        Creates a parent task from the prompt, then expands it into subtasks
        using tool-based expansion. Designed for use with slash commands.

        Args:
            prompt: The user's task prompt (e.g., "implement user authentication")
            parent_task_id: Optional parent task to nest created tasks under
            task_type: Type for created tasks (default: "task")

        Returns:
            Dictionary with parent task and created subtasks
        """
        if not task_expander:
            raise RuntimeError("Task expansion is not enabled")

        if not prompt or not prompt.strip():
            return {"error": "Prompt cannot be empty"}

        prompt = prompt.strip()

        # Get project context
        ctx = get_project_context()
        if ctx and ctx.get("id"):
            project_id = ctx["id"]
        else:
            init_result = initialize_project()
            project_id = init_result.project_id

        # Extract title from prompt (first line or first sentence, max 80 chars)
        first_line = prompt.split("\n")[0].strip()
        # If first line is short enough, use it as title
        if len(first_line) <= 80:
            title = first_line
        else:
            # Try to find a sentence boundary
            for sep in [". ", "! ", "? ", ": "]:
                if sep in first_line[:80]:
                    title = first_line[: first_line.index(sep) + 1]
                    break
            else:
                title = first_line[:77] + "..."

        # Create a parent task for the prompt
        prompt_task = task_manager.create_task(
            project_id=project_id,
            title=title,
            description=prompt,
            parent_task_id=parent_task_id,
            task_type="epic" if len(prompt) > 200 else task_type,
        )

        # Expand the task into subtasks
        result = await task_expander.expand_task(
            task_id=prompt_task.id,
            title=prompt_task.title,
            description=prompt,
            context="Break this request into actionable tasks. "
            "Each task should be specific, testable, and implementable.",
            enable_web_research=False,
            enable_code_context=True,  # Use code context for prompts
        )

        if "error" in result:
            return {
                "error": result["error"],
                "parent_task_id": prompt_task.id,
            }

        subtask_ids = result.get("subtask_ids", [])

        # Wire parent → subtask dependencies
        for subtask_id in subtask_ids:
            try:
                dep_manager.add_dependency(
                    task_id=prompt_task.id, depends_on=subtask_id, dep_type="blocks"
                )
            except ValueError:
                pass

        # Fetch created subtasks (brief format for token efficiency)
        subtasks = []
        for sid in subtask_ids:
            subtask = task_manager.get_task(sid)
            if subtask:
                subtasks.append({"id": subtask.id, "title": subtask.title})

        # Return concise response (use get_task for full details)
        return {
            "parent_task_id": prompt_task.id,
            "parent_task_title": prompt_task.title,
            "tasks_created": len(subtask_ids),
            "subtasks": subtasks,  # Brief: [{id, title}, ...]
        }

    @registry.tool(
        name="suggest_next_task",
        description="Suggest the next task to work on based on dependencies, priority, and readiness.",
    )
    def suggest_next_task(
        task_type: str | None = None,
        prefer_subtasks: bool = True,
    ) -> dict[str, Any]:
        """
        Suggest the best next task to work on.

        Uses a scoring algorithm considering:
        - Task is ready (no blockers)
        - Priority (higher priority = higher score)
        - Is a leaf task (subtask with no children)
        - Has clear scope (complexity_score if available)

        Args:
            task_type: Filter by task type (optional)
            prefer_subtasks: Prefer leaf tasks over parent tasks (default: True)

        Returns:
            Suggested task with reasoning
        """
        ready_tasks = task_manager.list_ready_tasks(task_type=task_type, limit=50)

        if not ready_tasks:
            return {
                "suggestion": None,
                "reason": "No ready tasks found",
            }

        # Score each task
        scored = []
        for task in ready_tasks:
            score = 0

            # Priority boost (1=high gets +30, 2=medium gets +20, 3=low gets +10)
            score += (4 - task.priority) * 10

            # Check if it's a leaf task (no children)
            children = task_manager.list_tasks(parent_task_id=task.id, status="open", limit=1)
            is_leaf = len(children) == 0

            if prefer_subtasks and is_leaf:
                score += 25  # Prefer actionable leaf tasks

            # Bonus for tasks with clear complexity
            if task.complexity_score and task.complexity_score <= 5:
                score += 15  # Prefer lower complexity tasks

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

        return {
            "suggestion": best_task.to_dict(),
            "score": best_score,
            "reason": f"Selected because: {', '.join(reasons) if reasons else 'best available option'}",
            "alternatives": [
                {"task_id": t.id, "title": t.title, "score": s}
                for t, s, _ in scored[1:4]  # Show top 3 alternatives
            ],
        }

    # Helper managers
    dep_manager = TaskDependencyManager(task_manager.db)
    session_task_manager = SessionTaskManager(task_manager.db)
    validation_history_manager = ValidationHistoryManager(task_manager.db)

    # --- Task CRUD ---

    async def create_task(
        title: str,
        description: str | None = None,
        priority: int = 2,
        task_type: str = "task",
        parent_task_id: str | None = None,
        blocks: list[str] | None = None,
        labels: list[str] | None = None,
        test_strategy: str | None = None,
        validation_criteria: str | None = None,
        session_id: str | None = None,
        generate_validation: bool | None = None,
    ) -> dict[str, Any]:
        """Create a new task in the current project.

        Args:
            title: Task title
            description: Detailed description
            priority: Priority level (1=High, 2=Medium, 3=Low)
            task_type: Task type (task, bug, feature, epic)
            parent_task_id: Optional parent task ID
            blocks: List of task IDs that this new task blocks
            labels: List of labels
            test_strategy: Testing strategy for this task
            validation_criteria: Acceptance criteria for validating completion.
                If not provided and generate_validation is True, criteria will be auto-generated.
            session_id: Your session ID for tracking
            generate_validation: Auto-generate validation criteria if not provided.
                Defaults to config setting. Skipped for epic tasks.

        Returns:
            Created task dict with id (minimal) or full task details based on config.
        """
        # Get current project context which is required for task creation
        ctx = get_project_context()
        if ctx and ctx.get("id"):
            project_id = ctx["id"]
        else:
            init_result = initialize_project()
            project_id = init_result.project_id

        # Auto-infer test_strategy if not provided
        effective_test_strategy = test_strategy
        if effective_test_strategy is None:
            effective_test_strategy = _infer_test_strategy(title, description)

        task = task_manager.create_task(
            project_id=project_id,
            title=title,
            description=description,
            priority=priority,
            task_type=task_type,
            parent_task_id=parent_task_id,
            labels=labels,
            test_strategy=effective_test_strategy,
            validation_criteria=validation_criteria,
            created_in_session_id=session_id,
        )

        # Handle 'blocks' argument if provided (syntactic sugar)
        if blocks:
            for blocked_id in blocks:
                dep_manager.add_dependency(task.id, blocked_id, "blocks")

        # Auto-generate validation criteria if enabled and not already provided
        should_generate = (
            generate_validation if generate_validation is not None else auto_generate_on_create
        )
        validation_generated = False
        if should_generate and not validation_criteria and task_type != "epic" and task_validator:
            try:
                criteria = await task_validator.generate_criteria(
                    title=title,
                    description=description,
                )
                if criteria:
                    task_manager.update_task(task.id, validation_criteria=criteria)
                    task = task_manager.get_task(task.id)  # Refresh task
                    validation_generated = True
            except Exception as e:
                import logging

                logging.getLogger(__name__).warning(
                    f"Failed to auto-generate validation criteria for {task.id}: {e}"
                )

        # Return minimal or full result based on config
        result = task.to_dict() if show_result_on_create else {"id": task.id}
        if validation_generated:
            result["validation_generated"] = True
        return result

    registry.register(
        name="create_task",
        description="Create a new task in the current project.",
        input_schema={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Task title"},
                "description": {
                    "type": "string",
                    "description": "Detailed description",
                    "default": None,
                },
                "priority": {
                    "type": "integer",
                    "description": "Priority level (1=High, 2=Medium, 3=Low)",
                    "default": 2,
                },
                "task_type": {
                    "type": "string",
                    "description": "Task type (task, bug, feature, epic)",
                    "default": "task",
                },
                "parent_task_id": {
                    "type": "string",
                    "description": "Optional parent task ID",
                    "default": None,
                },
                "blocks": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of task IDs that this new task blocks (optional)",
                    "default": None,
                },
                "labels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of labels (optional)",
                    "default": None,
                },
                "test_strategy": {
                    "type": "string",
                    "description": "Testing strategy: 'manual' (verify by running/inspecting, no automated tests required), 'automated' (requires unit/integration tests), or 'none' (no testing needed). Auto-inferred as 'manual' for verification/functional testing tasks if not specified.",
                    "enum": ["manual", "automated", "none"],
                    "default": None,
                },
                "validation_criteria": {
                    "type": "string",
                    "description": "Acceptance criteria for validating task completion (optional). If not provided and generate_validation is True, criteria will be auto-generated.",
                    "default": None,
                },
                "session_id": {
                    "type": "string",
                    "description": "Your session ID (from system context). Pass this to track which session created the task.",
                    "default": None,
                },
                "generate_validation": {
                    "type": "boolean",
                    "description": "Auto-generate validation criteria if not provided. Defaults to config setting. Skipped for epic tasks.",
                    "default": None,
                },
            },
            "required": ["title"],
        },
        func=create_task,
    )

    def get_task(task_id: str) -> dict[str, Any]:
        """Get task details including dependencies."""
        task = task_manager.get_task(task_id)
        if not task:
            return {"error": f"Task {task_id} not found", "found": False}

        result: dict[str, Any] = task.to_dict()

        # Enrich with dependency info
        blockers = dep_manager.get_blockers(task_id)
        blocking = dep_manager.get_blocking(task_id)

        result["dependencies"] = {
            "blocked_by": [b.to_dict() for b in blockers],
            "blocking": [b.to_dict() for b in blocking],
        }

        return result

    registry.register(
        name="get_task",
        description="Get task details including dependencies.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "The ID of the task to retrieve"},
            },
            "required": ["task_id"],
        },
        func=get_task,
    )

    def update_task(
        task_id: str,
        title: str | None = None,
        description: str | None = None,
        status: str | None = None,
        priority: int | None = None,
        assignee: str | None = None,
        labels: list[str] | None = None,
        validation_criteria: str | None = None,
        parent_task_id: str | None = None,
        test_strategy: str | None = None,
        workflow_name: str | None = None,
        verification: str | None = None,
        sequence_order: int | None = None,
    ) -> dict[str, Any]:
        """Update task fields."""
        # Build kwargs only for non-None values to avoid overwriting with NULL
        kwargs: dict[str, Any] = {}
        if title is not None:
            kwargs["title"] = title
        if description is not None:
            kwargs["description"] = description
        if status is not None:
            kwargs["status"] = status
        if priority is not None:
            kwargs["priority"] = priority
        if assignee is not None:
            kwargs["assignee"] = assignee
        if labels is not None:
            kwargs["labels"] = labels
        if validation_criteria is not None:
            kwargs["validation_criteria"] = validation_criteria
        if parent_task_id is not None:
            kwargs["parent_task_id"] = parent_task_id
        if test_strategy is not None:
            kwargs["test_strategy"] = test_strategy
        if workflow_name is not None:
            kwargs["workflow_name"] = workflow_name
        if verification is not None:
            kwargs["verification"] = verification
        if sequence_order is not None:
            kwargs["sequence_order"] = sequence_order

        task = task_manager.update_task(task_id, **kwargs)
        if not task:
            return {"error": f"Task {task_id} not found"}
        result: dict[str, Any] = task.to_dict()
        return result

    registry.register(
        name="update_task",
        description="Update task fields.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID"},
                "title": {"type": "string", "description": "New title", "default": None},
                "description": {
                    "type": "string",
                    "description": "New description",
                    "default": None,
                },
                "status": {
                    "type": "string",
                    "description": "New status (open, in_progress, closed)",
                    "default": None,
                },
                "priority": {"type": "integer", "description": "New priority", "default": None},
                "assignee": {"type": "string", "description": "New assignee", "default": None},
                "labels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "New labels list",
                    "default": None,
                },
                "validation_criteria": {
                    "type": "string",
                    "description": "Acceptance criteria for validating task completion",
                    "default": None,
                },
                "parent_task_id": {
                    "type": "string",
                    "description": "Parent task ID (for re-parenting)",
                    "default": None,
                },
                "test_strategy": {
                    "type": "string",
                    "description": "Testing strategy: 'manual' (verify by running/inspecting, no automated tests required), 'automated' (requires unit/integration tests), or 'none' (no testing needed).",
                    "enum": ["manual", "automated", "none"],
                    "default": None,
                },
                "workflow_name": {
                    "type": "string",
                    "description": "Workflow name for execution context",
                    "default": None,
                },
                "verification": {
                    "type": "string",
                    "description": "Verification steps or notes",
                    "default": None,
                },
                "sequence_order": {
                    "type": "integer",
                    "description": "Order in a sequence of tasks",
                    "default": None,
                },
            },
            "required": ["task_id"],
        },
        func=update_task,
    )

    def add_label(task_id: str, label: str) -> dict[str, Any]:
        """Add a label to a task."""
        task = task_manager.add_label(task_id, label)
        if not task:
            return {"error": f"Task {task_id} not found"}
        result: dict[str, Any] = task.to_dict()
        return result

    registry.register(
        name="add_label",
        description="Add a label to a task.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID"},
                "label": {"type": "string", "description": "Label to add"},
            },
            "required": ["task_id", "label"],
        },
        func=add_label,
    )

    def remove_label(task_id: str, label: str) -> dict[str, Any]:
        """Remove a label from a task."""
        task = task_manager.remove_label(task_id, label)
        if not task:
            return {"error": f"Task {task_id} not found"}
        result: dict[str, Any] = task.to_dict()
        return result

    registry.register(
        name="remove_label",
        description="Remove a label from a task.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID"},
                "label": {"type": "string", "description": "Label to remove"},
            },
            "required": ["task_id", "label"],
        },
        func=remove_label,
    )

    async def close_task(
        task_id: str,
        reason: str = "completed",
        changes_summary: str | None = None,
        skip_validation: bool = False,
        session_id: str | None = None,
        override_justification: str | None = None,
        no_commit_needed: bool = False,
        commit_sha: str | None = None,
    ) -> dict[str, Any]:
        """Close a task with validation.

        For parent tasks: automatically checks all children are closed.
        For leaf tasks: optionally validates with LLM if changes_summary provided.

        Args:
            task_id: Task ID to close
            reason: Reason for closing
            changes_summary: Summary of changes (enables LLM validation for leaf tasks)
            skip_validation: Skip all validation checks
            session_id: Session ID where task is being closed (auto-links to session)
            override_justification: Why agent bypassed validation (stored for audit).
                Also used to explain why no commit was needed when no_commit_needed=True.
            no_commit_needed: Set to True for tasks that don't produce code changes
                (research, planning, documentation review). Requires override_justification.
            commit_sha: Git commit SHA to link before closing. Convenience for link + close in one call.

        Returns:
            Closed task or error with validation feedback
        """
        task = task_manager.get_task(task_id)
        if not task:
            return {"error": f"Task {task_id} not found"}

        # Link commit if provided (convenience for link + close in one call)
        if commit_sha:
            task = task_manager.link_commit(task_id, commit_sha)

        # Get project repo_path for git commands
        repo_path = get_project_repo_path(task.project_id)
        cwd = repo_path or "."

        # Check for linked commits (unless task type doesn't require commits)
        # Skip commit check for certain close reasons that imply no work was done
        requires_commit_check = reason.lower() not in SKIP_REASONS

        if requires_commit_check and not task.commits:
            # No commits linked - require explicit acknowledgment
            if no_commit_needed:
                if not override_justification:
                    return {
                        "error": "justification_required",
                        "message": "When no_commit_needed=True, you must provide override_justification explaining why no commit was needed.",
                    }
                # Allowed to proceed - agent confirmed no commit needed
            else:
                return {
                    "error": "no_commits_linked",
                    "message": (
                        "Cannot close task: no commits are linked. Either:\n"
                        "1. Commit your changes and use link_commit() or include [task_id] in commit message\n"
                        "2. Set no_commit_needed=True with override_justification if this task didn't require code changes"
                    ),
                }

        # Auto-skip validation for certain close reasons
        should_skip = skip_validation or reason.lower() in SKIP_REASONS

        if not should_skip:
            # Check if task has children (is a parent task)
            children = task_manager.list_tasks(parent_task_id=task_id, limit=1000)

            if children:
                # Parent task: must have all children closed
                open_children = [c for c in children if c.status != "closed"]
                if open_children:
                    open_titles = [f"- {c.id}: {c.title}" for c in open_children[:5]]
                    remaining = len(open_children) - 5 if len(open_children) > 5 else 0
                    feedback = f"Cannot close: {len(open_children)} child tasks still open:\n"
                    feedback += "\n".join(open_titles)
                    if remaining > 0:
                        feedback += f"\n... and {remaining} more"
                    return {
                        "error": "validation_failed",
                        "message": feedback,
                        "open_children": [c.id for c in open_children],
                    }
            elif task_validator and task.validation_criteria:
                # Leaf task with validation criteria: run LLM validation
                # Use provided changes_summary or auto-fetch via smart context gathering
                validation_context = changes_summary
                if not validation_context:
                    # First try commit-based diff if task has linked commits
                    if task.commits:
                        try:
                            diff_result = get_task_diff(
                                task_id=task.id,
                                task_manager=task_manager,
                                include_uncommitted=True,  # Include uncommitted for complete picture
                                cwd=repo_path,
                            )
                            if diff_result.diff:
                                validation_context = (
                                    f"Commit-based diff ({len(diff_result.commits)} commits, "
                                    f"{diff_result.file_count} files):\n\n{diff_result.diff}"
                                )
                        except Exception:
                            pass  # Fall back to smart context on error

                    # Fall back to smart context if no commit diff available
                    if not validation_context:
                        from gobby.tasks.validation import get_validation_context_smart

                        # Smart context gathering: uncommitted changes + multi-commit window + file analysis
                        smart_context = get_validation_context_smart(
                            task_title=task.title,
                            validation_criteria=task.validation_criteria,
                            task_description=task.description,
                            cwd=repo_path,
                        )
                        if smart_context:
                            validation_context = f"Validation context:\n\n{smart_context}"

                if validation_context:
                    result = await task_validator.validate_task(
                        task_id=task.id,
                        title=task.title,
                        description=task.description,
                        changes_summary=validation_context,
                        validation_criteria=task.validation_criteria,
                        test_strategy=task.test_strategy,
                    )
                    # Store validation result regardless of pass/fail
                    task_manager.update_task(
                        task_id,
                        validation_status=result.status,
                        validation_feedback=result.feedback,
                    )
                    if result.status != "valid":
                        # Block closing on invalid or pending (error during validation)
                        return {
                            "error": "validation_failed",
                            "message": result.feedback or "Validation did not pass",
                            "validation_status": result.status,
                        }

        # Get git commit SHA (best-effort)
        from gobby.utils.git import run_git_command

        commit_sha = run_git_command(["git", "rev-parse", "HEAD"], cwd=cwd)

        # All checks passed - close the task with session and commit tracking
        # Store override reason if validation was skipped or no commit was needed
        store_override = should_skip or no_commit_needed
        closed_task = task_manager.close_task(
            task_id,
            reason=reason,
            closed_in_session_id=session_id,
            closed_commit_sha=commit_sha,
            validation_override_reason=override_justification if store_override else None,
        )

        # Auto-link session if provided
        if session_id:
            try:
                session_task_manager.link_task(session_id, task_id, "closed")
            except Exception:
                pass  # Best-effort linking, don't fail the close

        # Update worktree status based on closure reason (case-insensitive)
        try:
            reason_normalized = reason.lower()
            worktree_manager = LocalWorktreeManager(task_manager.db)
            wt = worktree_manager.get_by_task(task_id)
            if wt:
                if reason_normalized in ("wont_fix", "obsolete", "duplicate", "already_implemented"):
                    worktree_manager.mark_abandoned(wt.id)
                elif reason_normalized == "completed":
                    worktree_manager.mark_merged(wt.id)
        except Exception:
            pass  # Best-effort worktree update, don't fail the close

        response: dict[str, Any] = closed_task.to_dict()
        response["validated"] = not should_skip
        if no_commit_needed:
            response["no_commit_needed"] = True
        return response

    registry.register(
        name="close_task",
        description="Close a task. Requires commits to be linked (use link_commit or include [task_id] in commit message). Parent tasks require all children closed. Leaf tasks validate with LLM. Validation auto-skipped for: duplicate, already_implemented, wont_fix, obsolete.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID"},
                "reason": {
                    "type": "string",
                    "description": 'Reason for closing. Use "duplicate", "already_implemented", "wont_fix", or "obsolete" to auto-skip validation and commit check.',
                    "default": "completed",
                },
                "changes_summary": {
                    "type": "string",
                    "description": "Summary of changes made. If provided for leaf tasks, triggers LLM validation before close.",
                    "default": None,
                },
                "skip_validation": {
                    "type": "boolean",
                    "description": "Explicitly skip validation checks.",
                    "default": False,
                },
                "session_id": {
                    "type": "string",
                    "description": "Your session ID (from system context). Pass this to track which session closed the task.",
                    "default": None,
                },
                "override_justification": {
                    "type": "string",
                    "description": "Why agent bypassed validation or commit requirement. Required when no_commit_needed=True.",
                    "default": None,
                },
                "no_commit_needed": {
                    "type": "boolean",
                    "description": "Set to True for tasks that don't produce code changes (research, planning, review). Requires override_justification.",
                    "default": False,
                },
                "commit_sha": {
                    "type": "string",
                    "description": "Git commit SHA to link before closing. Convenience for commit + close in one call.",
                    "default": None,
                },
            },
            "required": ["task_id"],
        },
        func=close_task,
    )

    def reopen_task(task_id: str, reason: str | None = None) -> dict[str, Any]:
        """Reopen a closed task.

        Args:
            task_id: Task ID to reopen
            reason: Optional reason for reopening

        Returns:
            Reopened task or error
        """
        try:
            task = task_manager.reopen_task(task_id, reason=reason)

            # Reactivate any associated worktrees that were marked merged/abandoned
            try:
                from gobby.storage.worktrees import WorktreeStatus

                worktree_manager = LocalWorktreeManager(task_manager.db)
                wt = worktree_manager.get_by_task(task_id)
                if wt and wt.status in (
                    WorktreeStatus.MERGED.value,
                    WorktreeStatus.ABANDONED.value,
                ):
                    worktree_manager.update(wt.id, status=WorktreeStatus.ACTIVE.value)
            except Exception:
                pass  # Best-effort worktree update

            return task.to_dict()
        except ValueError as e:
            return {"error": str(e)}

    registry.register(
        name="reopen_task",
        description="Reopen a closed task. Clears closed_at, closed_reason, and closed_in_session_id. Optionally appends a reopen reason to the description.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID to reopen"},
                "reason": {
                    "type": "string",
                    "description": "Optional reason for reopening the task",
                    "default": None,
                },
            },
            "required": ["task_id"],
        },
        func=reopen_task,
    )

    def delete_task(task_id: str, cascade: bool = True) -> dict[str, Any]:
        """Delete a task and its children by default."""
        success = task_manager.delete_task(task_id, cascade=cascade)
        if not success:
            return {"error": f"Task {task_id} not found"}
        return {"deleted": True, "task_id": task_id}

    registry.register(
        name="delete_task",
        description="Delete a task.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID"},
                "cascade": {
                    "type": "boolean",
                    "description": "If True, delete all child tasks as well. Defaults to True.",
                    "default": True,
                },
            },
            "required": ["task_id"],
        },
        func=delete_task,
    )

    def list_tasks(
        status: str | None = None,
        priority: int | None = None,
        task_type: str | None = None,
        assignee: str | None = None,
        label: str | None = None,
        parent_task_id: str | None = None,
        title_like: str | None = None,
        limit: int = 50,
        all_projects: bool = False,
    ) -> dict[str, Any]:
        """List tasks with optional filters."""
        # Filter by current project unless all_projects is True
        project_id = None if all_projects else get_current_project_id()
        tasks = task_manager.list_tasks(
            status=status,
            priority=priority,
            task_type=task_type,
            assignee=assignee,
            label=label,
            parent_task_id=parent_task_id,
            title_like=title_like,
            limit=limit,
            project_id=project_id,
        )
        return {"tasks": [t.to_brief() for t in tasks], "count": len(tasks)}

    registry.register(
        name="list_tasks",
        description="List tasks with optional filters.",
        input_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string", "description": "Filter by status", "default": None},
                "priority": {
                    "type": "integer",
                    "description": "Filter by priority",
                    "default": None,
                },
                "task_type": {
                    "type": "string",
                    "description": "Filter by task type",
                    "default": None,
                },
                "assignee": {
                    "type": "string",
                    "description": "Filter by assignee",
                    "default": None,
                },
                "label": {
                    "type": "string",
                    "description": "Filter by label presence",
                    "default": None,
                },
                "parent_task_id": {
                    "type": "string",
                    "description": "Filter by parent task",
                    "default": None,
                },
                "title_like": {
                    "type": "string",
                    "description": "Filter by title (fuzzy match)",
                    "default": None,
                },
                "limit": {
                    "type": "integer",
                    "description": "Max number of tasks to return",
                    "default": 50,
                },
                "all_projects": {
                    "type": "boolean",
                    "description": "If true, list tasks from all projects instead of just the current project",
                    "default": False,
                },
            },
        },
        func=list_tasks,
    )

    # --- Dependencies ---

    def add_dependency(
        task_id: str,
        depends_on: str,
        dep_type: Literal["blocks", "discovered-from", "related"] = "blocks",
    ) -> dict[str, Any]:
        """Add a dependency between tasks."""
        try:
            dep_manager.add_dependency(task_id, depends_on, dep_type)
            return {
                "added": True,
                "task_id": task_id,
                "depends_on": depends_on,
                "dep_type": dep_type,
            }
        except ValueError as e:
            return {"error": str(e)}

    registry.register(
        name="add_dependency",
        description="Add a dependency between tasks.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "The dependent task (e.g., Task B)"},
                "depends_on": {"type": "string", "description": "The blocker task (e.g., Task A)"},
                "dep_type": {
                    "type": "string",
                    "description": 'Dependency type (default: "blocks")',
                    "default": "blocks",
                },
            },
            "required": ["task_id", "depends_on"],
        },
        func=add_dependency,
    )

    def remove_dependency(task_id: str, depends_on: str) -> dict[str, Any]:
        """Remove a dependency."""
        dep_manager.remove_dependency(task_id, depends_on)
        return {"removed": True, "task_id": task_id, "depends_on": depends_on}

    registry.register(
        name="remove_dependency",
        description="Remove a dependency.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "The dependent task"},
                "depends_on": {"type": "string", "description": "The blocker task"},
            },
            "required": ["task_id", "depends_on"],
        },
        func=remove_dependency,
    )

    def get_dependency_tree(task_id: str, direction: str = "both") -> dict[str, Any]:
        """Get dependency tree."""
        tree: dict[str, Any] = dep_manager.get_dependency_tree(task_id)
        if direction == "blockers":
            return {"blockers": tree.get("blockers", [])}
        elif direction == "blocking":
            return {"blocking": tree.get("blocking", [])}
        return tree

    registry.register(
        name="get_dependency_tree",
        description="Get dependency tree.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Root task ID"},
                "direction": {
                    "type": "string",
                    "description": '"blockers" (upstream), "blocking" (downstream), or "both"',
                    "default": "both",
                },
            },
            "required": ["task_id"],
        },
        func=get_dependency_tree,
    )

    def check_dependency_cycles() -> dict[str, Any]:
        """Detect circular dependencies in the project."""
        cycles = dep_manager.check_cycles()
        if cycles:
            return {"has_cycles": True, "cycles": cycles}
        return {"has_cycles": False}

    registry.register(
        name="check_dependency_cycles",
        description="Detect circular dependencies in the project.",
        input_schema={"type": "object", "properties": {}},
        func=check_dependency_cycles,
    )

    # --- Ready Work ---

    def list_ready_tasks(
        priority: int | None = None,
        task_type: str | None = None,
        assignee: str | None = None,
        parent_task_id: str | None = None,
        limit: int = 10,
        all_projects: bool = False,
    ) -> dict[str, Any]:
        """List tasks that are open and have no unresolved blocking dependencies."""
        # Filter by current project unless all_projects is True
        project_id = None if all_projects else get_current_project_id()
        tasks = task_manager.list_ready_tasks(
            priority=priority,
            task_type=task_type,
            assignee=assignee,
            parent_task_id=parent_task_id,
            limit=limit,
            project_id=project_id,
        )
        return {"tasks": [t.to_brief() for t in tasks], "count": len(tasks)}

    registry.register(
        name="list_ready_tasks",
        description="List tasks that are open and have no unresolved blocking dependencies.",
        input_schema={
            "type": "object",
            "properties": {
                "priority": {
                    "type": "integer",
                    "description": "Filter by priority",
                    "default": None,
                },
                "task_type": {"type": "string", "description": "Filter by type", "default": None},
                "assignee": {
                    "type": "string",
                    "description": "Filter by assignee",
                    "default": None,
                },
                "parent_task_id": {
                    "type": "string",
                    "description": "Filter by parent task (find ready subtasks)",
                    "default": None,
                },
                "limit": {"type": "integer", "description": "Max results", "default": 10},
                "all_projects": {
                    "type": "boolean",
                    "description": "If true, list tasks from all projects instead of just the current project",
                    "default": False,
                },
            },
        },
        func=list_ready_tasks,
    )

    def list_blocked_tasks(
        parent_task_id: str | None = None,
        limit: int = 20,
        all_projects: bool = False,
    ) -> dict[str, Any]:
        """List tasks that are currently blocked, including what blocks them."""
        # Filter by current project unless all_projects is True
        project_id = None if all_projects else get_current_project_id()
        blocked_tasks = task_manager.list_blocked_tasks(
            parent_task_id=parent_task_id,
            limit=limit,
            project_id=project_id,
        )
        return {"tasks": [t.to_brief() for t in blocked_tasks], "count": len(blocked_tasks)}

    registry.register(
        name="list_blocked_tasks",
        description="List tasks that are currently blocked by external dependencies (excludes parent tasks blocked by their own children).",
        input_schema={
            "type": "object",
            "properties": {
                "parent_task_id": {
                    "type": "string",
                    "description": "Filter by parent task (find blocked subtasks)",
                    "default": None,
                },
                "limit": {"type": "integer", "description": "Max results", "default": 20},
                "all_projects": {
                    "type": "boolean",
                    "description": "If true, list tasks from all projects instead of just the current project",
                    "default": False,
                },
            },
        },
        func=list_blocked_tasks,
    )

    # --- Session Integration ---

    def link_task_to_session(
        task_id: str,
        session_id: str | None = None,
        action: str = "worked_on",
    ) -> dict[str, Any]:
        """Link a task to a session."""
        if not session_id:
            return {"error": "session_id is required"}

        try:
            session_task_manager.link_task(session_id, task_id, action)
            return {"linked": True, "task_id": task_id, "session_id": session_id, "action": action}
        except ValueError as e:
            return {"error": str(e)}

    registry.register(
        name="link_task_to_session",
        description="Link a task to a session.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID"},
                "session_id": {
                    "type": "string",
                    "description": "Session ID (optional, defaults to linking context if available)",
                    "default": None,
                },
                "action": {
                    "type": "string",
                    "description": "Relationship type (worked_on, discovered, mentioned, closed)",
                    "default": "worked_on",
                },
            },
            "required": ["task_id"],
        },
        func=link_task_to_session,
    )

    def get_session_tasks(session_id: str) -> dict[str, Any]:
        """Get all tasks associated with a session."""
        tasks = session_task_manager.get_session_tasks(session_id)
        return {"session_id": session_id, "tasks": tasks}

    registry.register(
        name="get_session_tasks",
        description="Get all tasks associated with a session.",
        input_schema={
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Session ID"},
            },
            "required": ["session_id"],
        },
        func=get_session_tasks,
    )

    def get_task_sessions(task_id: str) -> dict[str, Any]:
        """Get all sessions that touched a task."""
        sessions = session_task_manager.get_task_sessions(task_id)
        return {"task_id": task_id, "sessions": sessions}

    registry.register(
        name="get_task_sessions",
        description="Get all sessions that touched a task.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID"},
            },
            "required": ["task_id"],
        },
        func=get_task_sessions,
    )

    # --- Git Sync ---

    def sync_tasks(direction: str = "both") -> dict[str, Any]:
        """Manually trigger task synchronization."""
        result = {}
        if direction in ["import", "both"]:
            sync_manager.import_from_jsonl()
            result["import"] = "completed"

        if direction in ["export", "both"]:
            sync_manager.export_to_jsonl()
            result["export"] = "completed"

        return result

    registry.register(
        name="sync_tasks",
        description="Manually trigger task synchronization.",
        input_schema={
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "description": '"import", "export", or "both"',
                    "default": "both",
                },
            },
        },
        func=sync_tasks,
    )

    def get_sync_status() -> dict[str, Any]:
        """Get current synchronization status."""
        result: dict[str, Any] = sync_manager.get_sync_status()
        return result

    registry.register(
        name="get_sync_status",
        description="Get current synchronization status.",
        input_schema={"type": "object", "properties": {}},
        func=get_sync_status,
    )

    # --- Commit Linking ---

    def link_commit(task_id: str, commit_sha: str) -> dict[str, Any]:
        """Link a git commit to a task."""
        try:
            task = task_manager.link_commit(task_id, commit_sha)
            return {
                "task_id": task.id,
                "commits": task.commits or [],
            }
        except ValueError as e:
            return {"error": str(e)}

    registry.register(
        name="link_commit",
        description="Link a git commit to a task. Useful for tracking which commits implement a task.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID"},
                "commit_sha": {
                    "type": "string",
                    "description": "Git commit SHA (short or full)",
                },
            },
            "required": ["task_id", "commit_sha"],
        },
        func=link_commit,
    )

    def unlink_commit(task_id: str, commit_sha: str) -> dict[str, Any]:
        """Unlink a git commit from a task."""
        try:
            task = task_manager.unlink_commit(task_id, commit_sha)
            return {
                "task_id": task.id,
                "commits": task.commits or [],
            }
        except ValueError as e:
            return {"error": str(e)}

    registry.register(
        name="unlink_commit",
        description="Unlink a git commit from a task.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID"},
                "commit_sha": {
                    "type": "string",
                    "description": "Git commit SHA to unlink",
                },
            },
            "required": ["task_id", "commit_sha"],
        },
        func=unlink_commit,
    )

    def auto_link_commits(
        task_id: str | None = None,
        since: str | None = None,
    ) -> dict[str, Any]:
        """Auto-detect and link commits that mention task IDs."""
        # Get project repo_path
        ctx = get_project_context()
        repo_path = None
        if ctx and ctx.get("id"):
            project = project_manager.get(ctx["id"])
            if project:
                repo_path = project.repo_path

        result = auto_link_commits_fn(
            task_manager=task_manager,
            task_id=task_id,
            since=since,
            cwd=repo_path,
        )

        return {
            "linked_tasks": result.linked_tasks,
            "total_linked": result.total_linked,
            "skipped": result.skipped,
        }

    registry.register(
        name="auto_link_commits",
        description="Auto-detect and link commits that mention task IDs in their messages. "
        "Supports patterns: [gt-xxxxx], gt-xxxxx:, Implements/Fixes/Closes gt-xxxxx.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Filter to specific task ID (optional)",
                    "default": None,
                },
                "since": {
                    "type": "string",
                    "description": "Git --since parameter (e.g., '1 week ago', '2024-01-01')",
                    "default": None,
                },
            },
        },
        func=auto_link_commits,
    )

    def get_task_diff_tool(
        task_id: str,
        include_uncommitted: bool = False,
    ) -> dict[str, Any]:
        """Get the combined diff for all commits linked to a task."""
        task = task_manager.get_task(task_id)
        if not task:
            return {"error": f"Task {task_id} not found"}

        # Get project repo_path
        repo_path = get_project_repo_path(task.project_id)

        result = get_task_diff(
            task_id=task_id,
            task_manager=task_manager,
            include_uncommitted=include_uncommitted,
            cwd=repo_path,
        )

        return {
            "diff": result.diff,
            "commits": result.commits,
            "has_uncommitted_changes": result.has_uncommitted_changes,
            "file_count": result.file_count,
        }

    registry.register(
        name="get_task_diff",
        description="Get the combined diff for all commits linked to a task. "
        "Optionally include uncommitted changes.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID"},
                "include_uncommitted": {
                    "type": "boolean",
                    "description": "Include uncommitted changes in the diff",
                    "default": False,
                },
            },
            "required": ["task_id"],
        },
        func=get_task_diff_tool,
    )

    return registry
