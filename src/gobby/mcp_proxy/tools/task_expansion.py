"""
Task expansion MCP tools module.

Provides tools for expanding tasks into subtasks with automatic TDD sandwich pattern:
- expand_task: Expand task into subtasks via AI (auto-applies TDD sandwich)
- analyze_complexity: Analyze task complexity
"""

import asyncio
import json
import re
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.storage.task_dependencies import TaskDependencyManager
from gobby.storage.tasks import LocalTaskManager, Task, TaskNotFoundError

if TYPE_CHECKING:
    from gobby.tasks.expansion import TaskExpander
    from gobby.tasks.validation import TaskValidator

__all__ = ["create_expansion_registry", "should_skip_tdd", "TDD_PREFIXES", "TDD_SKIP_PATTERNS"]

# TDD triplet prefixes - used for both skip detection and triplet creation
TDD_PREFIXES = ("[TDD]", "[IMPL]", "[REF]")

# Patterns for tasks that should skip TDD transformation (case-insensitive)
TDD_SKIP_PATTERNS = (
    # New TDD prefixes (already in triplet form)
    r"^\[TDD\]",
    r"^\[IMPL\]",
    r"^\[REF\]",
    # Legacy TDD prefixes (backwards compatibility)
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

# TDD validation criteria templates per phase
TDD_CRITERIA_RED = """## Deliverable
- [ ] Tests written that define expected behavior
- [ ] Tests fail when run (no implementation yet)
- [ ] Test coverage addresses acceptance criteria from parent task
"""

TDD_CRITERIA_BLUE = """## Deliverable
- [ ] All tests continue to pass
- [ ] Code refactored for clarity and maintainability
- [ ] No new functionality added (refactor only)
- [ ] Unrelated bugs discovered during refactor logged as new bug tasks

**Note:** If you discover bugs outside your scope during refactoring, create bug tasks
for them rather than fixing them now.
"""

TDD_PARENT_CRITERIA = """## Deliverable
- [ ] All child tasks completed
"""


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
    auto_generate_on_expand: bool = True,
    resolve_tdd_mode: Callable[[str | None], bool] | None = None,
) -> InternalToolRegistry:
    """
    Create a registry with task expansion tools.

    Args:
        task_manager: LocalTaskManager instance
        task_expander: TaskExpander instance (optional, required for AI expansion)
        task_validator: TaskValidator instance (optional, for auto-generating criteria)
        auto_generate_on_expand: Whether to auto-generate validation criteria on expand
        resolve_tdd_mode: Function to resolve TDD mode from session (optional)

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

    def _build_expansion_context(task: Task, user_context: str | None) -> str | None:
        """
        Build context for expansion by merging stored data with user context.

        If the task has expansion_context (legacy enrichment data), parse it and
        include research findings, validation criteria, and complexity info.

        Args:
            task: The Task object with optional expansion_context
            user_context: User-provided context string (may be None)

        Returns:
            Merged context string, or None if no context available
        """
        enrichment_parts: list[str] = []

        # Parse stored expansion_context (legacy enrichment data)
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
                complexity_level = enrichment_data.get("complexity_level")
                subtask_count = enrichment_data.get("suggested_subtask_count")
                if complexity_level or subtask_count:
                    complexity_info = []
                    if complexity_level:
                        complexity_info.append(f"Complexity level: {complexity_level}")
                    if subtask_count:
                        complexity_info.append(f"Suggested subtask count: {subtask_count}")
                    enrichment_parts.append("## Complexity Analysis\n" + "\n".join(complexity_info))

            except (json.JSONDecodeError, TypeError):
                # Legacy or plain text context - preserve it as raw text
                enrichment_parts.append(f"## Legacy Expansion Context\n{task.expansion_context}")

        # Add user-provided context
        if user_context:
            enrichment_parts.append(f"## Additional Context\n{user_context}")

        # Return merged context or None
        if enrichment_parts:
            return "\n\n".join(enrichment_parts)
        return None

    async def _apply_tdd_sandwich(
        parent_task_id: str,
        impl_task_ids: list[str],
    ) -> dict[str, Any]:
        """Apply TDD sandwich pattern to a parent task's children.

        Creates a "sandwich" structure where implementation tasks are wrapped:
        - ONE [TEST] task at the start (RED phase - write tests for all impls)
        - Original child tasks stay as implementation (GREEN phase)
        - ONE [REFACTOR] task at the end (BLUE phase - refactor everything)

        Dependencies:
        - All impl tasks are blocked by the TEST task
        - REFACTOR task is blocked by all impl tasks

        Args:
            parent_task_id: The parent task (epic) being expanded
            impl_task_ids: List of implementation task IDs (the original children)

        Returns:
            Dict with success=True and tasks_created count, or error info
        """
        parent = task_manager.get_task(parent_task_id)
        if not parent:
            return {"success": False, "error": f"Parent task not found: {parent_task_id}"}

        if not impl_task_ids:
            return {"success": False, "error": "No implementation tasks to wrap"}

        # Skip if already TDD-applied
        if parent.is_tdd_applied:
            return {"success": False, "skipped": True, "reason": "already_applied"}

        try:
            # Build list of impl task titles for TEST task context
            impl_titles = []
            for impl_id in impl_task_ids:
                impl_task = task_manager.get_task(impl_id)
                if impl_task:
                    impl_titles.append(f"- {impl_task.title}")
            impl_list = "\n".join(impl_titles) if impl_titles else "- (implementation tasks)"

            # 1. Create ONE Test Task (Red phase) - tests for all implementations
            test_task = task_manager.create_task(
                title=f"[TDD] Write failing tests for {parent.title}",
                description=(
                    f"Write failing tests for: {parent.title}\n\n"
                    "## Implementation tasks to cover:\n"
                    f"{impl_list}\n\n"
                    "RED phase of TDD - define expected behavior before implementation."
                ),
                project_id=parent.project_id,
                parent_task_id=parent.id,
                task_type="task",
                priority=parent.priority,
                validation_criteria=TDD_CRITERIA_RED,
                category="test",
            )

            # 2. Add [IMPL] prefix to all implementation tasks and wire dependencies
            for impl_id in impl_task_ids:
                impl_task = task_manager.get_task(impl_id)
                if impl_task and not impl_task.title.startswith("[IMPL]"):
                    task_manager.update_task(impl_id, title=f"[IMPL] {impl_task.title}")
                try:
                    dep_manager.add_dependency(impl_id, test_task.id, "blocks")
                except ValueError:
                    pass  # Dependency already exists

            # 3. Create ONE Refactor Task (Blue phase) - refactor after all impls done
            refactor_task = task_manager.create_task(
                title=f"[REF] Refactor and verify {parent.title}",
                description=(
                    f"Refactor implementations in: {parent.title}\n\n"
                    "BLUE phase of TDD - clean up while keeping tests green."
                ),
                project_id=parent.project_id,
                parent_task_id=parent.id,
                task_type="task",
                priority=parent.priority,
                validation_criteria=TDD_CRITERIA_BLUE,
                category="code",
            )

            # 4. Wire refactor to be blocked by TEST task and all implementation tasks
            # REFACTOR depends on TEST (must complete testing before refactoring)
            try:
                dep_manager.add_dependency(refactor_task.id, test_task.id, "blocks")
            except ValueError:
                pass  # Dependency already exists

            # REFACTOR depends on all impl tasks
            for impl_id in impl_task_ids:
                try:
                    dep_manager.add_dependency(refactor_task.id, impl_id, "blocks")
                except ValueError:
                    pass  # Dependency already exists

            # Mark parent as TDD-applied
            task_manager.update_task(
                parent.id,
                is_tdd_applied=True,
                validation_criteria=TDD_PARENT_CRITERIA,
            )

            return {
                "success": True,
                "tasks_created": 2,  # TEST + REFACTOR (impl tasks already existed)
                "test_task_id": test_task.id,
                "refactor_task_id": refactor_task.id,
                "impl_task_count": len(impl_task_ids),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _find_unexpanded_epic(root_task_id: str) -> Task | None:
        """Depth-first search for first unexpanded epic in the task tree.

        Traverses the task tree starting from root_task_id to find the first
        epic that hasn't been expanded yet (is_expanded=False).

        Args:
            root_task_id: Task ID to start search from

        Returns:
            First unexpanded epic Task, or None if all epics are expanded
        """
        task = task_manager.get_task(root_task_id)
        if not task:
            return None

        # Check if this task itself is an unexpanded epic
        if task.task_type == "epic" and not task.is_expanded:
            return task

        # Search children depth-first
        children = task_manager.list_tasks(parent_task_id=root_task_id, limit=1000)
        for child in children:
            if child.task_type == "epic":
                result = _find_unexpanded_epic(child.id)
                if result:
                    return result

        return None

    def _count_unexpanded_epics(root_task_id: str) -> int:
        """Count unexpanded epics in the task tree.

        Args:
            root_task_id: Task ID to start counting from

        Returns:
            Number of unexpanded epics in the tree
        """
        count = 0
        task = task_manager.get_task(root_task_id)
        if not task:
            return 0

        # Count this task if it's an unexpanded epic
        if task.task_type == "epic" and not task.is_expanded:
            count += 1

        # Count children recursively
        children = task_manager.list_tasks(parent_task_id=root_task_id, limit=1000)
        for child in children:
            count += _count_unexpanded_epics(child.id)

        return count

    async def _expand_single_task(
        single_task_id: str,
        context: str | None,
        enable_web_research: bool,
        enable_code_context: bool,
        should_generate_validation: bool,
        skip_tdd: bool = False,
        force: bool = False,
        session_id: str | None = None,
        iterative: bool = False,
    ) -> dict[str, Any]:
        """Internal helper to expand a single task.

        When iterative=True, supports iterative expansion of epic trees:
        - If the root task is already expanded, finds the next unexpanded epic
        - Returns progress info (unexpanded_epics count, complete flag)
        - Call repeatedly until complete=True
        """
        # Resolve task reference
        try:
            resolved_task_id = resolve_task_id_for_mcp(task_manager, single_task_id)
        except (TaskNotFoundError, ValueError) as e:
            return {"error": f"Invalid task_id: {e}", "task_id": single_task_id}

        if not task_expander:
            return {"error": "Task expansion is not enabled", "task_id": single_task_id}

        root_task = task_manager.get_task(resolved_task_id)
        if not root_task:
            return {"error": f"Task not found: {single_task_id}", "task_id": single_task_id}

        # Auto-enable iterative mode for epics (timeout-safe cascade)
        # Each call expands one epic and returns - caller loops until complete=True
        if root_task.task_type == "epic" and not iterative:
            iterative = True

        # Iterative mode: find next unexpanded epic in tree
        if iterative:
            target_task = _find_unexpanded_epic(resolved_task_id)
            if target_task is None:
                # All epics expanded - tree is complete
                return {
                    "complete": True,
                    "task_id": resolved_task_id,
                    "root_ref": f"#{root_task.seq_num}" if root_task.seq_num else root_task.id[:8],
                    "unexpanded_epics": 0,
                }
            task = target_task
        else:
            task = root_task

            # Non-iterative mode: Check if already expanded (unless force=True)
            if task.is_expanded and not force:
                return {
                    "error": "Task already expanded (is_expanded=True). Use force=True to re-expand, or use iterative mode to expand child epics.",
                    "task_id": task.id,
                    "is_expanded": True,
                }

            # Check if task is a leaf (no children) - only in non-iterative mode
            existing_children = task_manager.list_tasks(parent_task_id=task.id, limit=1)
            if existing_children:
                return {
                    "error": "Task already has children. Only leaf tasks can be expanded. Use iterative mode or CLI with --cascade for parent tasks.",
                    "task_id": task.id,
                    "existing_children": len(existing_children),
                }

        # Build context from any stored expansion_context + user context
        merged_context = _build_expansion_context(task, context)

        # Note: TDD transformation is applied separately via apply_tdd command
        result = await task_expander.expand_task(
            task_id=task.id,
            title=task.title,
            description=task.description,
            context=merged_context,
            enable_web_research=enable_web_research,
            enable_code_context=enable_code_context,
            session_id=session_id,
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
                    "ref": f"#{subtask.seq_num}" if subtask.seq_num else subtask.id[:8],
                    "title": subtask.title,
                    "seq_num": subtask.seq_num,
                    "id": subtask.id,
                }
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
                            pass  # nosec B110

        # Update parent task: set is_expanded and validation criteria
        task_manager.update_task(
            task.id,
            is_expanded=True,
            validation_criteria="All child tasks must be completed (status: closed).",
        )

        # Auto-apply TDD sandwich pattern (unless skip_tdd=True or expanding an epic)
        # Creates ONE [TDD] task, renames impl tasks with [IMPL], creates ONE [REF] task
        # IMPORTANT: Skip TDD when expanding epics - TDD is applied at feature task level
        tdd_applied = False
        tdd_categories = ("code", "config")
        if not skip_tdd and subtask_ids and task.task_type != "epic":
            # Collect code/config subtasks that should be wrapped in TDD sandwich
            impl_task_ids = []
            for sid in subtask_ids:
                subtask = task_manager.get_task(sid)
                if not subtask:
                    continue
                # Include code/config categories that aren't already TDD-formatted
                if subtask.category in tdd_categories:
                    if not should_skip_tdd(subtask.title):
                        impl_task_ids.append(sid)

            # Apply TDD sandwich at parent level (wraps all impl tasks)
            if impl_task_ids:
                tdd_result = await _apply_tdd_sandwich(resolved_task_id, impl_task_ids)
                if tdd_result.get("success", False):
                    tdd_applied = True

        # Build response
        response: dict[str, Any] = {
            "task_id": task.id,
            "tasks_created": len(subtask_ids),
            "subtasks": created_subtasks,
            "is_expanded": True,
        }
        # Include seq_num refs for ergonomics
        if task.seq_num is not None:
            response["expanded_ref"] = f"#{task.seq_num}"
            # Keep legacy field for compatibility
            response["parent_seq_num"] = task.seq_num
            response["parent_ref"] = f"#{task.seq_num}"

        # Iterative mode: include progress info
        if iterative:
            remaining = _count_unexpanded_epics(resolved_task_id)
            response["unexpanded_epics"] = remaining
            response["complete"] = remaining == 0
            # Include root task ref for context
            response["root_ref"] = (
                f"#{root_task.seq_num}" if root_task.seq_num else root_task.id[:8]
            )

        if validation_generated > 0:
            response["validation_criteria_generated"] = validation_generated
        if validation_skipped_reason:
            response["validation_skipped_reason"] = validation_skipped_reason
        if tdd_applied:
            response["tdd_applied"] = True
        return response

    @registry.tool(
        name="expand_task",
        description="Expand a task into smaller subtasks using AI. Supports iterative expansion of epic trees.",
    )
    async def expand_task(
        task_id: str | None = None,
        task_ids: list[str] | None = None,
        context: str | None = None,
        enable_web_research: bool = False,
        enable_code_context: bool = True,
        generate_validation: bool | None = None,
        skip_tdd: bool = False,
        force: bool = False,
        session_id: str | None = None,
        iterative: bool = False,
    ) -> dict[str, Any]:
        """
        Expand a task into subtasks using tool-based expansion.

        The expansion agent calls create_task MCP tool directly to create subtasks,
        wiring dependencies via the 'blocks' parameter.

        ## Iterative Mode (iterative=True)

        For epic trees, call repeatedly on the root epic until complete=True:

        ```python
        while True:
            result = expand_task(task_id="#100", iterative=True)
            if result.get("complete"):
                break
            print(f"Expanded {result['expanded_ref']}, {result['unexpanded_epics']} remaining")
        ```

        Returns:
        - expanded_ref: The task that was expanded (may differ from input)
        - unexpanded_epics: Count of remaining unexpanded epics
        - complete: True when all epics in tree are expanded

        Args:
            task_id: ID of single task to expand (mutually exclusive with task_ids)
            task_ids: List of task IDs for batch parallel expansion
            context: Additional context for expansion
            enable_web_research: Whether to enable web research (default: False)
            enable_code_context: Whether to enable code context gathering (default: True)
            generate_validation: Whether to auto-generate validation_criteria for subtasks.
                Defaults to config setting (gobby_tasks.validation.auto_generate_on_expand).
            skip_tdd: Skip automatic TDD transformation for code/config subtasks
            force: Re-expand even if is_expanded=True
            session_id: Session ID for TDD mode resolution (optional)
            iterative: Enable iterative expansion mode for epic trees. When True, finds
                the next unexpanded epic in the tree and expands it. Call repeatedly
                until complete=True. (default: False)

        Returns:
            Dictionary with expansion results. In iterative mode, includes:
            - expanded_ref: Task that was expanded
            - unexpanded_epics: Remaining unexpanded epics
            - complete: True when tree is fully expanded
        """
        # Use config default if not specified
        should_generate_validation = (
            generate_validation if generate_validation is not None else auto_generate_on_expand
        )

        # Validate parameters
        if task_id and task_ids:
            return {
                "error": "task_id and task_ids are mutually exclusive. Provide one or the other."
            }
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
                skip_tdd=skip_tdd,
                force=force,
                session_id=session_id,
                iterative=iterative,
            )

        # Batch mode - process tasks in parallel
        # At this point, task_ids is guaranteed to be a non-empty list (validated above)
        assert task_ids is not None  # nosec B101 - Type narrowing for mypy

        async def expand_one(tid: str) -> dict[str, Any]:
            return await _expand_single_task(
                single_task_id=tid,
                context=context,
                enable_web_research=enable_web_research,
                enable_code_context=enable_code_context,
                should_generate_validation=should_generate_validation,
                skip_tdd=skip_tdd,
                force=force,
                session_id=session_id,
                iterative=iterative,
            )

        raw_results = await asyncio.gather(
            *[expand_one(tid) for tid in task_ids], return_exceptions=True
        )
        # Convert exceptions to error dicts to preserve per-task success/error information
        processed_results: list[dict[str, Any]] = []
        for i, result in enumerate(raw_results):
            if isinstance(result, BaseException):
                processed_results.append(
                    {"error": str(result), "task_id": task_ids[i], "success": False}
                )
            else:
                processed_results.append(result)
        return {"results": processed_results}

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

    return registry
