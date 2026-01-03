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

from typing import TYPE_CHECKING, Any, Literal

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.storage.projects import LocalProjectManager
from gobby.storage.session_tasks import SessionTaskManager
from gobby.storage.task_dependencies import TaskDependencyManager
from gobby.storage.tasks import (
    LocalTaskManager,
)
from gobby.sync.tasks import TaskSyncManager
from gobby.tasks.expansion import TaskExpander
from gobby.tasks.validation import TaskValidator
from gobby.utils.project_context import get_project_context
from gobby.utils.project_init import initialize_project

if TYPE_CHECKING:
    from gobby.config.app import DaemonConfig


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
    # Get show_result_on_create setting from config
    show_result_on_create = False
    if config is not None:
        show_result_on_create = config.get_gobby_tasks_config().show_result_on_create
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

    @registry.tool(
        name="expand_task",
        description="Expand a high-level task into smaller subtasks using AI.",
    )
    async def expand_task(
        task_id: str,
        context: str | None = None,
        enable_web_research: bool = False,
        enable_code_context: bool = True,
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

        Returns:
            Dictionary with subtask_ids, tool_calls count, and agent text
        """
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

        # Fetch created subtasks for the response
        created_subtasks = []
        for sid in subtask_ids:
            subtask = task_manager.get_task(sid)
            if subtask:
                created_subtasks.append(
                    {
                        "id": subtask.id,
                        "title": subtask.title,
                        "status": subtask.status,
                    }
                )

        # Auto-generate validation criteria for each subtask
        validation_generated = 0
        if task_validator and subtask_ids:
            for sid in subtask_ids:
                subtask = task_manager.get_task(sid)
                if subtask and not subtask.validation_criteria:
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

        return {
            "task_id": task_id,
            "subtask_ids": subtask_ids,
            "subtasks": created_subtasks,
            "tool_calls": result.get("tool_calls", 0),
            "text": result.get("text", ""),
            "validation_criteria_generated": validation_generated,
        }

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
        description="Create tasks from a specification document or PRD.",
    )
    async def expand_from_spec(
        spec_content: str,
        parent_task_id: str | None = None,
        task_type: str = "task",
    ) -> dict[str, Any]:
        """
        Parse a specification document and create tasks from it.

        Creates a parent task from the spec title/summary, then expands it
        into subtasks using tool-based expansion.

        Args:
            spec_content: The specification text (markdown, requirements, etc.)
            parent_task_id: Optional parent task to nest created tasks under
            task_type: Type for created tasks (default: "task")

        Returns:
            Dictionary with parent task and created subtasks
        """
        if not task_expander:
            raise RuntimeError("Task expansion is not enabled")

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

        # Create a parent task for the spec
        spec_task = task_manager.create_task(
            project_id=project_id,
            title=title,
            description=spec_content,
            parent_task_id=parent_task_id,
            task_type="epic",  # Specs typically become epics
        )

        # Expand the spec task into subtasks
        result = await task_expander.expand_task(
            task_id=spec_task.id,
            title=spec_task.title,
            description=spec_content,
            context="Parse this specification and create actionable tasks. "
            "Each task should be specific and implementable.",
            enable_web_research=False,
            enable_code_context=False,
        )

        if "error" in result:
            return {
                "error": result["error"],
                "parent_task": spec_task.to_dict(),
                "subtask_ids": [],
            }

        subtask_ids = result.get("subtask_ids", [])

        # Wire parent → subtask dependencies
        for subtask_id in subtask_ids:
            try:
                dep_manager.add_dependency(
                    task_id=spec_task.id, depends_on=subtask_id, dep_type="blocks"
                )
            except ValueError:
                pass

        # Fetch created subtasks
        subtasks = []
        for sid in subtask_ids:
            subtask = task_manager.get_task(sid)
            if subtask:
                subtasks.append(subtask.to_dict())

        return {
            "parent_task": spec_task.to_dict(),
            "tasks_created": len(subtask_ids),
            "subtask_ids": subtask_ids,
            "subtasks": subtasks,
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

    # --- Task CRUD ---

    def create_task(
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
    ) -> dict[str, Any]:
        """Create a new task in the current project."""
        # Get current project context which is required for task creation
        ctx = get_project_context()
        if ctx and ctx.get("id"):
            project_id = ctx["id"]
        else:
            init_result = initialize_project()
            project_id = init_result.project_id

        task = task_manager.create_task(
            project_id=project_id,
            title=title,
            description=description,
            priority=priority,
            task_type=task_type,
            parent_task_id=parent_task_id,
            labels=labels,
            test_strategy=test_strategy,
            validation_criteria=validation_criteria,
            created_in_session_id=session_id,
        )

        # Handle 'blocks' argument if provided (syntactic sugar)
        if blocks:
            for blocked_id in blocks:
                dep_manager.add_dependency(task.id, blocked_id, "blocks")

        # Return minimal or full result based on config
        if show_result_on_create:
            return task.to_dict()
        return {"id": task.id}

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
                    "description": "Testing strategy for this task (optional)",
                    "default": None,
                },
                "validation_criteria": {
                    "type": "string",
                    "description": "Acceptance criteria for validating task completion (optional). If provided, the task can be validated using validate_task.",
                    "default": None,
                },
                "session_id": {
                    "type": "string",
                    "description": "Your session ID (from system context). Pass this to track which session created the task.",
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
                    "description": "Testing approach for the task",
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
            override_justification: Why agent bypassed validation (stored for audit)

        Returns:
            Closed task or error with validation feedback
        """
        task = task_manager.get_task(task_id)
        if not task:
            return {"error": f"Task {task_id} not found"}

        # Auto-skip validation for certain close reasons
        skip_reasons = {"duplicate", "already_implemented", "wont_fix", "obsolete"}
        should_skip = skip_validation or reason.lower() in skip_reasons

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
                    from gobby.tasks.validation import get_validation_context_smart

                    # Get project repo_path for git commands
                    repo_path = get_project_repo_path(task.project_id)

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

        # Get project repo_path for git commands
        repo_path = get_project_repo_path(task.project_id)
        if repo_path is None:
            import logging

            logging.getLogger(__name__).warning(
                f"No repo_path found for project_id={task.project_id}, "
                f"falling back to daemon working directory for git command"
            )
        cwd = repo_path or "."
        commit_sha = run_git_command(["git", "rev-parse", "HEAD"], cwd=cwd)

        # All checks passed - close the task with session and commit tracking
        closed_task = task_manager.close_task(
            task_id,
            reason=reason,
            closed_in_session_id=session_id,
            closed_commit_sha=commit_sha,
            validation_override_reason=override_justification if should_skip else None,
        )

        # Auto-link session if provided
        if session_id:
            try:
                session_task_manager.link_task(session_id, task_id, "closed")
            except Exception:
                pass  # Best-effort linking, don't fail the close

        response: dict[str, Any] = closed_task.to_dict()
        response["validated"] = not should_skip
        return response

    registry.register(
        name="close_task",
        description="Close a task. Parent tasks require all children closed. Leaf tasks validate with LLM. Validation auto-skipped for: duplicate, already_implemented, wont_fix, obsolete. Automatically captures git commit SHA.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID"},
                "reason": {
                    "type": "string",
                    "description": 'Reason for closing. Use "duplicate", "already_implemented", "wont_fix", or "obsolete" to auto-skip validation.',
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
                    "description": "Why agent bypassed validation. Stored for audit when using skip_validation or auto-skip reasons.",
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
    ) -> dict[str, Any]:
        """List tasks with optional filters."""
        tasks = task_manager.list_tasks(
            status=status,
            priority=priority,
            task_type=task_type,
            assignee=assignee,
            label=label,
            parent_task_id=parent_task_id,
            title_like=title_like,
            limit=limit,
        )
        return {"tasks": [t.to_dict() for t in tasks], "count": len(tasks)}

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
    ) -> dict[str, Any]:
        """List tasks that are open and have no unresolved blocking dependencies."""
        tasks = task_manager.list_ready_tasks(
            priority=priority,
            task_type=task_type,
            assignee=assignee,
            parent_task_id=parent_task_id,
            limit=limit,
        )
        return {"tasks": [t.to_dict() for t in tasks], "count": len(tasks)}

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
            },
        },
        func=list_ready_tasks,
    )

    def list_blocked_tasks(limit: int = 20) -> dict[str, Any]:
        """List tasks that are currently blocked, including what blocks them."""
        blocked_items = task_manager.list_blocked_tasks(limit=limit)
        return {"blocked_tasks": blocked_items}

    registry.register(
        name="list_blocked_tasks",
        description="List tasks that are currently blocked, including what blocks them.",
        input_schema={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max results", "default": 20},
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

    return registry
