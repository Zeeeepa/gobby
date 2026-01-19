"""
Task expansion MCP tools module.

Provides tools for expanding tasks into subtasks with automatic TDD sandwich pattern:
- expand_task: Expand task into subtasks via AI (auto-applies TDD sandwich)
- analyze_complexity: Analyze task complexity
"""

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.storage.task_dependencies import TaskDependencyManager
from gobby.storage.tasks import LocalTaskManager, Task, TaskNotFoundError

# Import shared TDD utilities
from gobby.tasks.tdd import (
    TDD_CATEGORIES,
    TDD_PREFIXES,
    TDD_SKIP_PATTERNS,
    apply_tdd_sandwich,
    build_expansion_context,
    should_skip_expansion,
    should_skip_tdd,
)

if TYPE_CHECKING:
    from gobby.tasks.expansion import TaskExpander
    from gobby.tasks.validation import TaskValidator

logger = logging.getLogger(__name__)

# Re-export for backwards compatibility
__all__ = [
    "create_expansion_registry",
    "should_skip_tdd",
    "TDD_PREFIXES",
    "TDD_SKIP_PATTERNS",
    "TDD_CATEGORIES",
]


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

    async def _apply_tdd_sandwich_wrapper(
        parent_task_id: str,
        impl_task_ids: list[str],
        refactor_task_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Wrapper to call shared apply_tdd_sandwich with local managers."""
        return await apply_tdd_sandwich(
            task_manager, dep_manager, parent_task_id, impl_task_ids, refactor_task_ids
        )

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

            # Re-fetch to get latest state and verify task should be expanded
            target_task = task_manager.get_task(target_task.id)
            if target_task is None:
                return {"error": "Task deleted during expansion", "task_id": resolved_task_id}

            # Check if task should be skipped (TDD prefixes or already expanded)
            skip, reason = should_skip_expansion(target_task.title, target_task.is_expanded, force)
            if skip:
                logger.info(f"Skipping task {target_task.id[:8]}: {reason}")
                return {
                    "skipped": True,
                    "reason": reason,
                    "task_id": target_task.id,
                    "unexpanded_epics": _count_unexpanded_epics(resolved_task_id),
                }

            task = target_task
        else:
            task = root_task

            # Non-iterative mode: Check if task should be skipped
            skip, reason = should_skip_expansion(task.title, task.is_expanded, force)
            if skip:
                if reason == "already expanded":
                    return {
                        "error": "Task already expanded (is_expanded=True). Use force=True to re-expand, or use iterative mode to expand child epics.",
                        "task_id": task.id,
                        "is_expanded": True,
                    }
                else:
                    return {
                        "error": f"Cannot expand task: {reason}",
                        "task_id": task.id,
                        "skipped": True,
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
        merged_context = build_expansion_context(task.expansion_context, context)

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
                            pass  # nosec B110 - best-effort validation generation

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
        should_apply_tdd = not skip_tdd and subtask_ids and task.task_type != "epic"
        logger.info(
            f"TDD check: task={task.id[:8]} type={task.task_type} "
            f"skip_tdd={skip_tdd} subtask_count={len(subtask_ids)} "
            f"should_apply={should_apply_tdd}"
        )
        if should_apply_tdd:
            # Collect code/config subtasks that should be wrapped in TDD sandwich
            impl_task_ids = []
            refactor_task_ids = []
            for sid in subtask_ids:
                subtask = task_manager.get_task(sid)
                if not subtask:
                    continue
                # Include code/config categories that aren't already TDD-formatted
                if subtask.category in tdd_categories:
                    if not should_skip_tdd(subtask.title):
                        impl_task_ids.append(sid)
                        logger.debug(
                            f"  TDD candidate: {subtask.id[:8]} category={subtask.category}"
                        )
                    else:
                        logger.debug(
                            f"  TDD skip (pattern): {subtask.id[:8]} title={subtask.title[:40]}"
                        )
                elif subtask.category == "refactor":
                    # Refactor-category tasks get [REF] prefix and wire into dependency chain
                    if not should_skip_tdd(subtask.title):
                        refactor_task_ids.append(sid)
                        logger.debug(
                            f"  TDD refactor candidate: {subtask.id[:8]} category={subtask.category}"
                        )
                    else:
                        logger.debug(
                            f"  TDD skip (pattern): {subtask.id[:8]} title={subtask.title[:40]}"
                        )
                else:
                    logger.debug(
                        f"  TDD skip (category): {subtask.id[:8]} category={subtask.category}"
                    )

            # Apply TDD sandwich at parent level (wraps all impl tasks)
            if impl_task_ids:
                logger.info(
                    f"Applying TDD sandwich: {len(impl_task_ids)} code/config subtasks, "
                    f"{len(refactor_task_ids)} refactor subtasks"
                )
                tdd_result = await _apply_tdd_sandwich_wrapper(
                    resolved_task_id, impl_task_ids, refactor_task_ids or None
                )
                if tdd_result.get("success", False):
                    tdd_applied = True
                    logger.info(f"TDD sandwich applied successfully to {task.id[:8]}")
                else:
                    logger.warning(f"TDD sandwich failed: {tdd_result}")
            else:
                logger.info(f"No code/config subtasks for TDD sandwich in {task.id[:8]}")

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
