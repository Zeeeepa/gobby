"""
Task expansion MCP tools module.

Provides tools for expanding tasks into subtasks using AI or structured parsing:
- expand_task: Expand task into subtasks via AI
- expand_all: Expand multiple unexpanded tasks
- expand_from_spec: Create tasks from spec file
- expand_from_prompt: Create tasks from user prompt
- analyze_complexity: Analyze task complexity
- enrich_task: Enrich tasks with additional context and metadata

Extracted from tasks.py using Strangler Fig pattern for code decomposition.
"""

import asyncio
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.storage.projects import LocalProjectManager
from gobby.storage.task_dependencies import TaskDependencyManager
from gobby.storage.tasks import LocalTaskManager, Task, TaskNotFoundError
from gobby.tasks.criteria import CriteriaGenerator
from gobby.tasks.spec_parser import (
    CheckboxExtractor,
    MarkdownStructureParser,
    TaskHierarchyBuilder,
)
from gobby.utils.project_context import get_project_context, get_verification_config
from gobby.utils.project_init import initialize_project

if TYPE_CHECKING:
    from gobby.tasks.enrich import TaskEnricher
    from gobby.tasks.expansion import TaskExpander
    from gobby.tasks.validation import TaskValidator

__all__ = ["create_expansion_registry", "should_skip_tdd", "TDD_PREFIXES", "TDD_SKIP_PATTERNS"]

# TDD triplet prefixes - used for both skip detection and triplet creation
TDD_PREFIXES = ("Write tests for:", "Implement:", "Refactor:")

# Patterns for tasks that should skip TDD transformation (case-insensitive)
TDD_SKIP_PATTERNS = (
    # TDD prefixes (already in triplet form)
    r"^Write tests for:",
    r"^Implement:",
    r"^Refactor:",
    # Deletion tasks (simple operations, no tests needed)
    r"^Delete\b",
    r"^Remove\b",
    # Documentation updates
    r"^Update.*README",
    r"^Update.*documentation",
    r"^Update.*docs\b",
    # Config file updates
    r"^Update.*\.toml\b",
    r"^Update.*\.yaml\b",
    r"^Update.*\.yml\b",
    r"^Update.*\.json\b",
    r"^Update.*\.env\b",
    r"^Update.*config",
)


def should_skip_tdd(title: str) -> bool:
    """
    Check if a task should skip TDD transformation based on its title.

    Tasks are skipped if they match any TDD_SKIP_PATTERNS:
    - Already TDD triplet tasks (Write tests for:, Implement:, Refactor:)
    - Deletion tasks (Delete X, Remove Y)
    - Documentation updates (Update README, Update docs)
    - Config file updates (Update pyproject.toml, Update .env)

    Args:
        title: The task title to check

    Returns:
        True if the task should skip TDD transformation, False otherwise
    """
    for pattern in TDD_SKIP_PATTERNS:
        if re.search(pattern, title, re.IGNORECASE):
            return True
    return False


def create_expansion_registry(
    task_manager: LocalTaskManager,
    task_expander: "TaskExpander | None" = None,
    task_validator: "TaskValidator | None" = None,
    task_enricher: "TaskEnricher | None" = None,
    auto_generate_on_expand: bool = True,
    resolve_tdd_mode: Callable[[str | None], bool] | None = None,
) -> InternalToolRegistry:
    """
    Create a registry with task expansion tools.

    Args:
        task_manager: LocalTaskManager instance
        task_expander: TaskExpander instance (optional, required for AI expansion)
        task_validator: TaskValidator instance (optional, for auto-generating criteria)
        task_enricher: TaskEnricher instance (optional, for task enrichment)
        auto_generate_on_expand: Whether to auto-generate validation criteria on expand
        resolve_tdd_mode: Callable to resolve TDD mode from session_id (optional)

    Returns:
        InternalToolRegistry with expansion tools registered
    """
    # Lazy import to avoid circular dependency
    from gobby.mcp_proxy.tools.tasks import resolve_task_id_for_mcp

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

    def _build_expansion_context(task: Task, user_context: str | None) -> str | None:
        """
        Build context for expansion by merging stored enrichment data with user context.

        If the task has expansion_context (from prior enrich_task call), parse it and
        include research findings, validation criteria, and complexity info.

        Args:
            task: The Task object with optional expansion_context
            user_context: User-provided context string (may be None)

        Returns:
            Merged context string, or None if no context available
        """
        enrichment_parts: list[str] = []

        # Parse stored expansion_context from prior enrichment
        if task.expansion_context:
            try:
                enrichment_data = json.loads(task.expansion_context)

                # Include research findings
                if research := enrichment_data.get("research_findings"):
                    enrichment_parts.append(f"## Research Findings\n{research}")

                # Include validation criteria
                if validation := enrichment_data.get("validation_criteria"):
                    enrichment_parts.append(f"## Validation Criteria\n{validation}")

                # Include complexity info
                complexity_score = enrichment_data.get("complexity_score")
                subtask_count = enrichment_data.get("suggested_subtask_count")
                if complexity_score or subtask_count:
                    complexity_info = []
                    if complexity_score:
                        complexity_info.append(f"Complexity score: {complexity_score}")
                    if subtask_count:
                        complexity_info.append(f"Suggested subtask count: {subtask_count}")
                    enrichment_parts.append(
                        "## Complexity Analysis\n" + "\n".join(complexity_info)
                    )

            except (json.JSONDecodeError, TypeError):
                # Invalid JSON - skip enrichment context, continue with user context
                pass

        # Add user-provided context
        if user_context:
            enrichment_parts.append(f"## Additional Context\n{user_context}")

        # Return merged context or None
        if enrichment_parts:
            return "\n\n".join(enrichment_parts)
        return None

    async def _expand_single_task(
        single_task_id: str,
        context: str | None,
        enable_web_research: bool,
        enable_code_context: bool,
        should_generate_validation: bool,
        session_id: str | None,
        enrich_if_missing: bool,
    ) -> dict[str, Any]:
        """Internal helper to expand a single task."""
        # Resolve task reference
        try:
            resolved_task_id = resolve_task_id_for_mcp(task_manager, single_task_id)
        except (TaskNotFoundError, ValueError) as e:
            return {"error": f"Invalid task_id: {e}", "task_id": single_task_id}

        if not task_expander:
            return {"error": "Task expansion is not enabled", "task_id": single_task_id}

        task = task_manager.get_task(resolved_task_id)
        if not task:
            return {"error": f"Task not found: {single_task_id}", "task_id": single_task_id}

        # Auto-enrich if task has no expansion_context and enrich_if_missing=True
        auto_enriched = False
        if enrich_if_missing and not task.expansion_context and task_enricher:
            try:
                enrichment_result = await task_enricher.enrich(
                    task_id=task.id,
                    title=task.title,
                    description=task.description,
                    enable_code_research=enable_code_context,
                    enable_web_research=enable_web_research,
                    enable_mcp_tools=False,
                    generate_validation=True,
                )

                # Store enrichment result in expansion_context
                expansion_context_json = json.dumps(enrichment_result.to_dict())

                # Update task with enrichment results
                enrich_update_kwargs: dict[str, Any] = {
                    "is_enriched": True,
                    "expansion_context": expansion_context_json,
                }
                if enrichment_result.category:
                    enrich_update_kwargs["category"] = enrichment_result.category
                if enrichment_result.complexity_score:
                    enrich_update_kwargs["complexity_score"] = enrichment_result.complexity_score
                if enrichment_result.validation_criteria:
                    enrich_update_kwargs["validation_criteria"] = enrichment_result.validation_criteria

                task_manager.update_task(task.id, **enrich_update_kwargs)

                # Refresh task to get updated expansion_context
                task = task_manager.get_task(resolved_task_id)
                auto_enriched = True
            except Exception:
                # If enrichment fails, continue with expansion without enrichment
                pass

        # Resolve TDD mode from workflow state if resolver provided
        tdd_mode = resolve_tdd_mode(session_id) if resolve_tdd_mode else None

        # Build context from expansion_context (enrichment data) + user context
        merged_context = _build_expansion_context(task, context)

        result = await task_expander.expand_task(
            task_id=task.id,
            title=task.title,
            description=task.description,
            context=merged_context,
            enable_web_research=enable_web_research,
            enable_code_context=enable_code_context,
            tdd_mode=tdd_mode,
        )

        # Handle errors
        if "error" in result:
            return {"error": result["error"], "task_id": task.id}

        # Extract subtask IDs (already created by agent via create_task tool calls)
        subtask_ids = result.get("subtask_ids", [])

        # Wire parent → subtask dependencies
        for subtask_id in subtask_ids:
            try:
                dep_manager.add_dependency(
                    task_id=task.id, depends_on=subtask_id, dep_type="blocks"
                )
            except ValueError:
                pass

        # Fetch created subtasks for the response (include seq_num for ergonomics)
        created_subtasks = []
        for sid in subtask_ids:
            subtask = task_manager.get_task(sid)
            if subtask:
                subtask_info: dict[str, Any] = {
                    "id": subtask.id,
                    "title": subtask.title,
                }
                if subtask.seq_num is not None:
                    subtask_info["seq_num"] = subtask.seq_num
                    subtask_info["ref"] = f"#{subtask.seq_num}"
                created_subtasks.append(subtask_info)

        # Auto-generate validation criteria for each subtask (when enabled)
        validation_generated = 0
        validation_skipped_reason = None
        if should_generate_validation and subtask_ids:
            if not task_validator:
                validation_skipped_reason = "task_validator not configured"
            else:
                for sid in subtask_ids:
                    subtask = task_manager.get_task(sid)
                    if subtask and not subtask.validation_criteria and subtask.task_type != "epic":
                        try:
                            criteria = await task_validator.generate_criteria(
                                title=subtask.title,
                                description=subtask.description,
                            )
                            if criteria:
                                task_manager.update_task(sid, validation_criteria=criteria)
                                validation_generated += 1
                        except Exception:
                            pass

        # Update parent task: set is_expanded and validation criteria
        task_manager.update_task(
            task.id,
            is_expanded=True,
            validation_criteria="All child tasks must be completed (status: closed).",
        )

        # Build response
        response: dict[str, Any] = {
            "task_id": task.id,
            "tasks_created": len(subtask_ids),
            "subtasks": created_subtasks,
            "is_expanded": True,
        }
        # Include parent seq_num for ergonomics
        if task.seq_num is not None:
            response["parent_seq_num"] = task.seq_num
            response["parent_ref"] = f"#{task.seq_num}"
        if auto_enriched:
            response["auto_enriched"] = True
        if validation_generated > 0:
            response["validation_criteria_generated"] = validation_generated
        if validation_skipped_reason:
            response["validation_skipped_reason"] = validation_skipped_reason
        return response

    @registry.tool(
        name="expand_task",
        description="Expand a high-level task into smaller subtasks using AI.",
    )
    async def expand_task(
        task_id: str | None = None,
        task_ids: list[str] | None = None,
        context: str | None = None,
        enable_web_research: bool = False,
        enable_code_context: bool = True,
        generate_validation: bool | None = None,
        session_id: str | None = None,
        enrich_if_missing: bool = True,
    ) -> dict[str, Any]:
        """
        Expand a task into subtasks using tool-based expansion.

        The expansion agent calls create_task MCP tool directly to create subtasks,
        wiring dependencies via the 'blocks' parameter.

        Args:
            task_id: ID of single task to expand (mutually exclusive with task_ids)
            task_ids: List of task IDs for batch parallel expansion
            context: Additional context for expansion
            enable_web_research: Whether to enable web research (default: False)
            enable_code_context: Whether to enable code context gathering (default: True)
            generate_validation: Whether to auto-generate validation_criteria for subtasks.
                Defaults to config setting (gobby_tasks.validation.auto_generate_on_expand).
            session_id: Session ID to resolve TDD mode from workflow state.
            enrich_if_missing: Auto-run enrichment if task has no expansion_context.
                Defaults to True, ensuring expansion always has enrichment data.

        Returns:
            Dictionary with subtask_ids for single task, or results list for batch mode
        """
        # Use config default if not specified
        should_generate_validation = (
            generate_validation if generate_validation is not None else auto_generate_on_expand
        )

        # Validate parameters
        if task_id and task_ids:
            return {"error": "task_id and task_ids are mutually exclusive. Provide one or the other."}
        if not task_id and not task_ids:
            return {"error": "Either task_id or task_ids must be provided"}
        if task_ids is not None and len(task_ids) == 0:
            return {"error": "task_ids list cannot be empty"}

        # Single task mode
        if task_id:
            return await _expand_single_task(
                single_task_id=task_id,
                context=context,
                enable_web_research=enable_web_research,
                enable_code_context=enable_code_context,
                should_generate_validation=should_generate_validation,
                session_id=session_id,
                enrich_if_missing=enrich_if_missing,
            )

        # Batch mode - process tasks in parallel
        async def expand_one(tid: str) -> dict[str, Any]:
            return await _expand_single_task(
                single_task_id=tid,
                context=context,
                enable_web_research=enable_web_research,
                enable_code_context=enable_code_context,
                should_generate_validation=should_generate_validation,
                session_id=session_id,
                enrich_if_missing=enrich_if_missing,
            )

        results = await asyncio.gather(*[expand_one(tid) for tid in task_ids])
        return {"results": list(results)}

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
            task_id: Task reference: #N, N (seq_num), path (1.2.3), or UUID

        Returns:
            Complexity analysis with score and reasoning
        """
        # Resolve task reference
        try:
            resolved_task_id = resolve_task_id_for_mcp(task_manager, task_id)
        except (TaskNotFoundError, ValueError) as e:
            return {"error": f"Invalid task_id: {e}"}

        task = task_manager.get_task(resolved_task_id)
        if not task:
            raise ValueError(f"Task not found: {task_id}")

        # Check for existing subtasks
        subtasks = task_manager.list_tasks(parent_task_id=task.id, limit=100)
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
        session_id: str | None = None,
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
            session_id: Session ID to resolve TDD mode from workflow state.

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
            # Create criteria generator for structured expansion
            criteria_generator = None
            if task_expander:
                # Get pattern config from task expander's config
                pattern_config = task_expander.config.pattern_criteria
                verification_config = get_verification_config()
                criteria_generator = CriteriaGenerator(
                    pattern_config=pattern_config,
                    verification_config=verification_config,
                )

            # Resolve TDD mode from workflow state if resolver provided
            tdd_mode = resolve_tdd_mode(session_id) if resolve_tdd_mode else None

            # Use structured parsing with optional LLM fallback
            builder = TaskHierarchyBuilder(
                task_manager=task_manager,
                project_id=project_id,
                parent_task_id=spec_task.id,
                criteria_generator=criteria_generator,
                tdd_mode=tdd_mode or False,
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

            # Resolve TDD mode from workflow state if resolver provided
            llm_tdd_mode = resolve_tdd_mode(session_id) if resolve_tdd_mode else None

            llm_result = await task_expander.expand_task(
                task_id=spec_task.id,
                title=spec_task.title,
                description=spec_content,
                context="Parse this specification and create actionable tasks. "
                "Each task should be specific and implementable.",
                enable_web_research=False,
                enable_code_context=False,
                tdd_mode=llm_tdd_mode,
            )

            if "error" in llm_result:
                return {
                    "error": llm_result["error"],
                    "parent_task_id": spec_task.id,
                    "mode_used": effective_mode,
                }

            subtask_ids = llm_result.get("subtask_ids", [])

        # NOTE: We do NOT add explicit blocking dependencies from parent to children here.
        # The parent-child relationship is already captured via parent_task_id.
        # Adding explicit deps causes readiness detection issues (parent incorrectly
        # marked as blocked by descendants, breaking the ready task query).
        # Inter-sibling dependencies (task A before task B) are still created in
        # expansion.py based on LLM-suggested depends_on_indices.

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
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Parse a user prompt and create tasks from it.

        Creates a parent task from the prompt, then expands it into subtasks
        using tool-based expansion. Designed for use with slash commands.

        Args:
            prompt: The user's task prompt (e.g., "implement user authentication")
            parent_task_id: Optional parent task to nest created tasks under
            task_type: Type for created tasks (default: "task")
            session_id: Optional session ID to resolve workflow variables (e.g., tdd_mode)

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

        # Resolve TDD mode from workflow state if resolver provided
        tdd_mode = resolve_tdd_mode(session_id) if resolve_tdd_mode else None

        # Expand the task into subtasks
        result = await task_expander.expand_task(
            task_id=prompt_task.id,
            title=prompt_task.title,
            description=prompt,
            context="Break this request into actionable tasks. "
            "Each task should be specific, testable, and implementable.",
            enable_web_research=False,
            enable_code_context=True,  # Use code context for prompts
            tdd_mode=tdd_mode,
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

    # Default size limit for task descriptions (prevents wasted LLM calls)
    DEFAULT_MAX_DESCRIPTION_SIZE = 10000

    @registry.tool(
        name="enrich_task",
        description="Enrich task(s) with additional context, research findings, and metadata.",
    )
    async def enrich_task(
        task_id: str | None = None,
        task_ids: list[str] | None = None,
        enable_code_research: bool = True,
        enable_web_research: bool = False,
        enable_mcp_tools: bool = False,
        generate_validation: bool = True,
        force: bool = False,
        session_id: str | None = None,
        max_description_size: int | None = None,
    ) -> dict[str, Any]:
        """
        Enrich task(s) with additional context and metadata.

        Uses AI and optional research tools to gather context about tasks and
        enhance their descriptions with implementation guidance, acceptance
        criteria, and complexity estimates.

        Args:
            task_id: Single task ID to enrich (mutually exclusive with task_ids)
            task_ids: List of task IDs for batch enrichment
            enable_code_research: Enable code context gathering (default: True)
            enable_web_research: Enable web research for external context (default: False)
            enable_mcp_tools: Enable MCP tools for additional research (default: False)
            generate_validation: Generate validation criteria (default: True)
            force: Re-enrich even if task is already enriched (default: False)
            session_id: Optional session ID for context
            max_description_size: Maximum description size in characters (default: 10000).
                Descriptions exceeding this limit will be rejected to prevent wasted LLM calls.

        Returns:
            Enrichment result(s) with category, complexity, and findings
        """
        # Use default limit if not specified
        size_limit = max_description_size if max_description_size is not None else DEFAULT_MAX_DESCRIPTION_SIZE

        def validate_description_size(desc: str | None, tid: str, title: str) -> dict[str, Any] | None:
            """Check if description exceeds size limit. Returns error dict if invalid, None if OK."""
            if desc is None:
                return None
            if len(desc) > size_limit:
                return {
                    "error": f"Description exceeds maximum size ({len(desc)} > {size_limit} characters). "
                    "Consider splitting the task or summarizing the description.",
                    "task_id": tid,
                    "title": title,
                    "description_size": len(desc),
                    "max_size": size_limit,
                    "suggestion": "Use the CLI to edit the task description, or split into smaller tasks.",
                }
            return None
        if not task_enricher:
            raise RuntimeError("Task enrichment is not enabled or not configured")

        # Determine which tasks to enrich
        target_ids: list[str] = []
        if task_ids:
            target_ids = list(task_ids)
        elif task_id:
            target_ids = [task_id]
        else:
            return {"error": "Either task_id or task_ids must be provided"}

        # Process single task
        if len(target_ids) == 1:
            single_task_id = target_ids[0]
            try:
                resolved_id = resolve_task_id_for_mcp(task_manager, single_task_id)
            except (TaskNotFoundError, ValueError) as e:
                return {"error": f"Invalid task_id: {e}"}

            task = task_manager.get_task(resolved_id)
            if not task:
                return {"error": f"Task not found: {single_task_id}"}

            # Skip if already enriched (unless force=True)
            if task.is_enriched and not force:
                return {
                    "task_id": task.id,
                    "skipped": True,
                    "already_enriched": True,
                    "message": "Task is already enriched. Use force=True to re-enrich.",
                }

            # Validate description size BEFORE calling enricher
            size_error = validate_description_size(task.description, task.id, task.title)
            if size_error:
                return size_error

            try:
                result = await task_enricher.enrich(
                    task_id=task.id,
                    title=task.title,
                    description=task.description,
                    enable_code_research=enable_code_research,
                    enable_web_research=enable_web_research,
                    enable_mcp_tools=enable_mcp_tools,
                    generate_validation=generate_validation,
                )

                # Store full enrichment result in expansion_context as JSON
                expansion_context = json.dumps(result.to_dict())

                # Update task with enrichment results
                update_kwargs: dict[str, Any] = {
                    "is_enriched": True,
                    "expansion_context": expansion_context,
                }
                if result.category:
                    update_kwargs["category"] = result.category
                if result.complexity_score:
                    update_kwargs["complexity_score"] = result.complexity_score
                if result.validation_criteria and generate_validation:
                    update_kwargs["validation_criteria"] = result.validation_criteria

                task_manager.update_task(task.id, **update_kwargs)

                # Return enrichment result
                return {
                    "task_id": task.id,
                    "category": result.category,
                    "complexity_score": result.complexity_score,
                    "research_findings": result.research_findings,
                    "suggested_subtask_count": result.suggested_subtask_count,
                    "validation_criteria": result.validation_criteria,
                    "mcp_tools_used": result.mcp_tools_used,
                }
            except Exception as e:
                return {"error": f"Enrichment failed: {e}", "task_id": task.id}

        # Process batch
        results: list[dict[str, Any]] = []
        for tid in target_ids:
            try:
                resolved_id = resolve_task_id_for_mcp(task_manager, tid)
            except (TaskNotFoundError, ValueError) as e:
                results.append({"task_id": tid, "error": f"Invalid task_id: {e}"})
                continue

            task = task_manager.get_task(resolved_id)
            if not task:
                results.append({"task_id": tid, "error": "Task not found"})
                continue

            # Skip if already enriched (unless force=True)
            if task.is_enriched and not force:
                results.append({
                    "task_id": task.id,
                    "skipped": True,
                    "already_enriched": True,
                })
                continue

            # Validate description size BEFORE calling enricher
            size_error = validate_description_size(task.description, task.id, task.title)
            if size_error:
                results.append(size_error)
                continue

            try:
                result = await task_enricher.enrich(
                    task_id=task.id,
                    title=task.title,
                    description=task.description,
                    enable_code_research=enable_code_research,
                    enable_web_research=enable_web_research,
                    enable_mcp_tools=enable_mcp_tools,
                    generate_validation=generate_validation,
                )

                # Store full enrichment result in expansion_context as JSON
                expansion_context = json.dumps(result.to_dict())

                # Update task with enrichment results
                update_kwargs: dict[str, Any] = {
                    "is_enriched": True,
                    "expansion_context": expansion_context,
                }
                if result.category:
                    update_kwargs["category"] = result.category
                if result.complexity_score:
                    update_kwargs["complexity_score"] = result.complexity_score
                if result.validation_criteria and generate_validation:
                    update_kwargs["validation_criteria"] = result.validation_criteria

                task_manager.update_task(task.id, **update_kwargs)

                results.append({
                    "task_id": task.id,
                    "category": result.category,
                    "complexity_score": result.complexity_score,
                    "research_findings": result.research_findings,
                })
            except Exception as e:
                results.append({"task_id": task.id, "error": f"Enrichment failed: {e}"})

        # Summarize batch results
        successful = [r for r in results if "error" not in r and not r.get("skipped")]
        skipped = [r for r in results if r.get("skipped")]
        failed = [r for r in results if "error" in r]

        return {
            "results": results,
            "enriched_count": len(successful),
            "skipped_count": len(skipped),
            "failed_count": len(failed),
            "total": len(target_ids),
        }

    @registry.tool(
        name="apply_tdd",
        description="Transform a task into TDD triplet (test, implement, refactor).",
    )
    async def apply_tdd(
        task_id: str,
    ) -> dict[str, Any]:
        """
        Transform a task into TDD triplet (test, implement, refactor).

        Creates three subtasks for the given task:
        1. Write tests for: <title>
        2. Implement: <title>
        3. Refactor: <title>

        Skips tasks that already have is_tdd_applied=True or tasks with
        titles starting with TDD prefixes.

        Args:
            task_id: Task reference: #N, N (seq_num), path (1.2.3), or UUID

        Returns:
            Dictionary with tasks_created count and subtasks list
        """
        # Resolve task reference (resolve_task_id_for_mcp is imported at module level)
        try:
            resolved_task_id = resolve_task_id_for_mcp(task_manager, task_id)
        except (TaskNotFoundError, ValueError) as e:
            return {"error": f"Invalid task_id: {e}"}

        task = task_manager.get_task(resolved_task_id)
        if not task:
            return {"error": f"Task not found: {task_id}"}

        # Skip if already TDD-applied
        if task.is_tdd_applied:
            return {
                "skipped": True,
                "reason": "TDD already applied to this task",
                "task_id": task.id,
            }

        # Skip if title already has TDD prefix
        if task.title.startswith(TDD_PREFIXES):
            return {
                "skipped": True,
                "reason": "Task title already has TDD prefix",
                "task_id": task.id,
            }

        # Create TDD triplet: Test -> Implement -> Refactor
        # Each step depends on the previous (Impl blocked by Test, Refactor blocked by Impl)
        created_tasks: list[dict[str, Any]] = []
        triplet_ids: list[str] = []  # [test_id, impl_id, refactor_id]

        for prefix in TDD_PREFIXES:
            subtask = task_manager.create_task(
                title=f"{prefix} {task.title}",
                project_id=task.project_id,
                parent_task_id=task.id,
                task_type="task",
                priority=task.priority,
            )
            triplet_ids.append(subtask.id)
            subtask_info: dict[str, Any] = {"id": subtask.id, "title": subtask.title}
            if subtask.seq_num is not None:
                subtask_info["seq_num"] = subtask.seq_num
                subtask_info["ref"] = f"#{subtask.seq_num}"
            created_tasks.append(subtask_info)

        # Wire dependencies: each step blocked by previous
        test_id, impl_id, refactor_id = triplet_ids
        dep_manager.add_dependency(impl_id, test_id, "blocks")
        dep_manager.add_dependency(refactor_id, impl_id, "blocks")

        # Mark task as TDD-applied and update validation criteria
        task_manager.update_task(
            task.id,
            is_tdd_applied=True,
            validation_criteria="All child tasks must be completed (status: closed).",
        )

        return {
            "task_id": task.id,
            "tasks_created": len(created_tasks),
            "subtasks": created_tasks,
        }

    return registry
