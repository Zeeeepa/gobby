"""
Task expansion MCP tools module.

Provides tools for expanding tasks into subtasks using AI or structured parsing:
- expand_task: Expand task into subtasks via AI
- expand_all: Expand multiple unexpanded tasks
- expand_from_spec: Create tasks from spec file
- expand_from_prompt: Create tasks from user prompt
- analyze_complexity: Analyze task complexity

Extracted from tasks.py using Strangler Fig pattern for code decomposition.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.storage.projects import LocalProjectManager
from gobby.storage.task_dependencies import TaskDependencyManager
from gobby.storage.tasks import LocalTaskManager
from gobby.tasks.spec_parser import (
    CheckboxExtractor,
    MarkdownStructureParser,
    TaskHierarchyBuilder,
)
from gobby.utils.project_context import get_project_context
from gobby.utils.project_init import initialize_project

if TYPE_CHECKING:
    from gobby.tasks.expansion import TaskExpander
    from gobby.tasks.validation import TaskValidator

__all__ = ["create_expansion_registry"]


def create_expansion_registry(
    task_manager: LocalTaskManager,
    task_expander: "TaskExpander | None" = None,
    task_validator: "TaskValidator | None" = None,
    auto_generate_on_expand: bool = True,
) -> InternalToolRegistry:
    """
    Create a registry with task expansion tools.

    Args:
        task_manager: LocalTaskManager instance
        task_expander: TaskExpander instance (optional, required for AI expansion)
        task_validator: TaskValidator instance (optional, for auto-generating criteria)
        auto_generate_on_expand: Whether to auto-generate validation criteria on expand

    Returns:
        InternalToolRegistry with expansion tools registered
    """
    registry = InternalToolRegistry(
        name="gobby-tasks-expansion",
        description="Task expansion tools - AI and structured parsing",
    )

    # Create helper managers
    dep_manager = TaskDependencyManager(task_manager.db)
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

    return registry
