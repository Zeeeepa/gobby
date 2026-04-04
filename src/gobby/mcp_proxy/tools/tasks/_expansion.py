"""Expansion tools for skill-based task decomposition.

Provides tools for the /gobby-expand skill workflow:
1. save_expansion_spec - Save expansion spec to task for later execution
2. execute_expansion - Create subtasks atomically from saved spec
3. get_expansion_spec - Check for pending expansion (for resume)
"""

import json
import logging
import re
from typing import Any

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.mcp_proxy.tools.tasks._context import RegistryContext
from gobby.mcp_proxy.tools.tasks._resolution import resolve_task_id_for_mcp
from gobby.storage.tasks import TaskNotFoundError

logger = logging.getLogger(__name__)

# Categories that get TDD sandwich wrapping
_TDD_CATEGORIES = frozenset({"code", "config"})


def _extract_phase_number(subtask: dict[str, Any]) -> int | None:
    """Extract phase number from '### Plan Section: N.N' in description."""
    desc = subtask.get("description", "")
    match = re.search(r"###\s+Plan Section:\s*(\d+)\.", desc)
    return int(match.group(1)) if match else None


def _extract_phase_from_title(subtask: dict[str, Any]) -> int | None:
    """Extract phase number from TDD-generated titles like '[TEST] Phase 2: ...'."""
    title = subtask.get("title", "")
    match = re.search(r"Phase\s+(\d+)", title)
    return int(match.group(1)) if match else None


def _get_subtask_phase(subtask: dict[str, Any]) -> int:
    """Get phase number for a subtask, checking description then title. Returns 0 if unphased."""
    return _extract_phase_number(subtask) or _extract_phase_from_title(subtask) or 0


def _extract_phase_titles(description: str) -> dict[int, str]:
    """Extract phase titles from plan document content in task description.

    Matches: ## Phase N: Title
    """
    titles: dict[int, str] = {}
    for match in re.finditer(r"##\s+Phase\s+(\d+):\s*(.+)", description):
        titles[int(match.group(1))] = match.group(2).strip()
    return titles


def _translate_deps(deps: list[int], old_to_new: dict[int, int]) -> list[int]:
    """Translate original dependency indices to new indices."""
    return [old_to_new[d] for d in deps if d in old_to_new]


def _apply_tdd_sandwich(subtasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Wrap phases of code/config tasks with [TEST] and [REF] bookends.

    Per phase with TDD-eligible tasks:
        [TEST] -> [IMPL] -> [IMPL] -> ... -> [REF]

    Between phases:
        Phase N [REF] -> Phase N+1 [TEST]

    Non-TDD categories (docs, research, planning, manual, test, refactor)
    pass through without wrapping.
    """
    # Group subtasks by phase number
    phase_groups: dict[int, list[int]] = {}
    for i, st in enumerate(subtasks):
        phase = _extract_phase_number(st)
        if phase is None:
            phase = 0  # Unphased tasks go to phase 0
        phase_groups.setdefault(phase, []).append(i)

    # If everything is phase 0 (no plan sections), treat as single phase
    if list(phase_groups.keys()) == [0]:
        phase_groups = {1: phase_groups[0]}
    elif 0 in phase_groups:
        # Move unphased tasks to end
        max_phase = max(p for p in phase_groups if p > 0)
        phase_groups[max_phase + 1] = phase_groups.pop(0)

    sorted_phases = sorted(phase_groups.keys())

    new_subtasks: list[dict[str, Any]] = []
    old_to_new: dict[int, int] = {}  # original index -> new index
    phase_ref_idx: dict[int, int] = {}  # phase -> new index of its [REF] task

    for phase_num in sorted_phases:
        orig_indices = phase_groups[phase_num]
        orig_set = set(orig_indices)

        has_tdd_tasks = any(subtasks[i].get("category") in _TDD_CATEGORIES for i in orig_indices)

        if not has_tdd_tasks:
            # Non-TDD phase: copy with translated deps
            for orig_idx in orig_indices:
                new_idx = len(new_subtasks)
                old_to_new[orig_idx] = new_idx
                st = dict(subtasks[orig_idx])
                st["depends_on"] = _translate_deps(st.get("depends_on", []), old_to_new)
                new_subtasks.append(st)
            continue

        # --- TDD phase: TEST -> IMPLs -> REF ---

        # Collect cross-phase deps for the TEST task
        cross_deps: set[int] = set()
        for orig_idx in orig_indices:
            for dep in subtasks[orig_idx].get("depends_on", []):
                if dep not in orig_set and dep in old_to_new:
                    dep_phase = _extract_phase_number(subtasks[dep])
                    if dep_phase is not None and dep_phase in phase_ref_idx:
                        cross_deps.add(phase_ref_idx[dep_phase])
                    else:
                        cross_deps.add(old_to_new[dep])

        # Titles of TDD-eligible tasks for TEST description
        impl_titles = [
            subtasks[i]["title"]
            for i in orig_indices
            if subtasks[i].get("category") in _TDD_CATEGORIES
        ]

        # 1. [TEST] task
        test_new_idx = len(new_subtasks)
        new_subtasks.append(
            {
                "title": f"[TEST] Phase {phase_num}: Write failing tests",
                "category": "test",
                "description": (
                    f"Write failing tests for Phase {phase_num} implementation tasks:\n\n"
                    + "\n".join(f"- {t}" for t in impl_titles)
                    + "\n\nTests should cover the expected behavior described in each "
                    "task. All tests must fail (red) before implementation begins."
                ),
                "validation": (
                    "Tests exist and fail with expected assertion errors (not import/syntax errors)"
                ),
                "priority": subtasks[orig_indices[0]].get("priority", 2),
                "depends_on": sorted(cross_deps),
            }
        )

        # 2. [IMPL] tasks (originals) — depend on TEST + intra-phase deps
        # Two-pass: first reserve indices, then wire deps (preserves forward refs)
        impl_start = len(new_subtasks)
        for i, orig_idx in enumerate(orig_indices):
            old_to_new[orig_idx] = impl_start + i
            new_subtasks.append(dict(subtasks[orig_idx]))

        for orig_idx in orig_indices:
            st = new_subtasks[old_to_new[orig_idx]]
            new_deps = [test_new_idx]
            for dep in st.get("depends_on", []):
                if dep in orig_set and dep in old_to_new:
                    new_deps.append(old_to_new[dep])
            st["depends_on"] = new_deps

        # 3. [REF] task — depends on all IMPLs in phase
        ref_new_idx = len(new_subtasks)
        phase_ref_idx[phase_num] = ref_new_idx
        new_subtasks.append(
            {
                "title": f"[REF] Phase {phase_num}: Refactor with green tests",
                "category": "refactor",
                "description": (
                    f"Refactor Phase {phase_num} while keeping all tests green.\n\n"
                    "Review for: duplication, naming, complexity, method length.\n"
                    "Run tests after each change."
                ),
                "validation": "All tests pass. Code reviewed for clarity and simplicity.",
                "priority": subtasks[orig_indices[0]].get("priority", 2),
                "depends_on": [old_to_new[i] for i in orig_indices],
            }
        )

    return new_subtasks


def create_expansion_registry(ctx: RegistryContext) -> InternalToolRegistry:
    """Create a registry with task expansion tools.

    Args:
        ctx: Shared registry context

    Returns:
        InternalToolRegistry with expansion tools registered
    """
    registry = InternalToolRegistry(
        name="gobby-tasks-expansion",
        description="Task expansion for skill-based decomposition",
    )

    async def save_expansion_spec(
        task_id: str,
        spec: dict[str, Any],
        project: str | None = None,
    ) -> dict[str, Any]:
        """Save expansion spec to task.expansion_context for later execution.

        Used by the /gobby-expand skill to persist the expansion plan before
        creating subtasks. This ensures the spec survives session compaction.

        Args:
            task_id: Task ID to expand (can be #N, path, or UUID)
            spec: Expansion specification containing:
                - subtasks: List of subtask definitions, each with:
                    - title: Subtask title (required)
                    - category: code, config, docs, research, planning, manual
                    - depends_on: List of indices of subtasks this depends on
                    - validation: Validation criteria string
                    - description: Optional description
                    - priority: Optional priority (default: 2)
            project: Project name or UUID for task resolution (optional)

        Returns:
            {"saved": True, "task_id": str, "subtask_count": int}
        """
        # Get project context
        try:
            project_id = ctx.resolve_project_filter(project)
        except ValueError as e:
            return {"error": str(e)}

        # Resolve task ID
        try:
            resolved_id = resolve_task_id_for_mcp(ctx.task_manager, task_id, project_id)
        except (TaskNotFoundError, ValueError) as e:
            return {"error": f"Task not found: {e}"}

        # Validate spec structure
        if "subtasks" not in spec or not isinstance(spec["subtasks"], list):
            return {"error": "Spec must contain 'subtasks' array"}

        if len(spec["subtasks"]) == 0:
            return {"error": "Spec must contain at least one subtask"}

        # Validate subtask structure
        for i, subtask in enumerate(spec["subtasks"]):
            if "title" not in subtask:
                return {"error": f"Subtask {i} missing required 'title' field"}

        # Save spec to task
        ctx.task_manager.update_task(
            resolved_id,
            expansion_context=json.dumps(spec),
            expansion_status="pending",
        )

        logger.info(
            f"Saved expansion spec for task {task_id} with {len(spec['subtasks'])} subtasks"
        )

        return {
            "saved": True,
            "task_id": resolved_id,
            "subtask_count": len(spec["subtasks"]),
        }

    async def execute_expansion(
        parent_task_id: str,
        project: str | None = None,
        tdd: bool = False,
    ) -> dict[str, Any]:
        """Execute a saved expansion spec atomically.

        Creates all subtasks from the saved spec and wires dependencies.
        Call save_expansion_spec first to persist the spec.

        Args:
            parent_task_id: Task ID with saved expansion spec
            project: Project name or UUID for task resolution (optional)

        Returns:
            {"created": ["#N", ...], "count": int} or {"error": str}
        """
        from gobby.utils.session_context import get_current_session_id

        session_id = get_current_session_id()
        if not session_id:
            return {"error": "No session context available. Ensure session_id is set."}

        # Get project context
        try:
            project_id = ctx.resolve_project_filter(project)
        except ValueError as e:
            return {"error": str(e)}

        # Resolve task ID
        try:
            resolved_id = resolve_task_id_for_mcp(ctx.task_manager, parent_task_id, project_id)
        except (TaskNotFoundError, ValueError) as e:
            return {"error": f"Task not found: {e}"}

        # Resolve session ref (#N -> UUID)
        try:
            resolved_session_id = ctx.resolve_session_id(session_id)
        except (ValueError, LookupError) as e:
            return {"error": f"Session not found: {e}"}

        # Get task and check for pending spec
        task = ctx.task_manager.get_task(resolved_id)
        if not task:
            return {"error": f"Task {parent_task_id} not found"}

        if task.expansion_status != "pending":
            return {
                "error": f"Task has no pending expansion spec (status: {task.expansion_status})"
            }

        if not task.expansion_context:
            return {"error": "Task has no expansion_context"}

        # Parse spec
        try:
            spec = json.loads(task.expansion_context)
        except json.JSONDecodeError as e:
            return {"error": f"Invalid expansion_context JSON: {e}"}

        subtasks = spec.get("subtasks", [])
        if not subtasks:
            return {"error": "No subtasks in spec"}

        # Apply TDD sandwich if requested (via param or spec flag)
        apply_tdd = tdd or spec.get("tdd", False)
        if apply_tdd:
            subtasks = _apply_tdd_sandwich(subtasks)
            logger.info(
                f"Applied TDD sandwich to expansion: {len(spec['subtasks'])} -> {len(subtasks)} subtasks"
            )

        # Build plan reference block if plan_file is in the spec
        plan_file = spec.get("plan_file")
        plan_ref_block = ""
        if plan_file:
            plan_ref_block = (
                f"> **Plan reference:** `{plan_file}`\n"
                "> Your task description below is your scope — follow it, not the plan.\n"
                "> The plan file provides background context only "
                '(the "why" behind this task).\n'
                "> Your description may differ from the plan because "
                "expansion was adapted to the actual codebase.\n\n"
            )

        epic_validation = "All subtasks must be completed (status: closed)."

        # --- Phase subepic creation ---
        # Group subtasks by phase to determine if subepics are needed
        phase_map: dict[int, list[int]] = {}
        for i, st in enumerate(subtasks):
            phase = _get_subtask_phase(st)
            phase_map.setdefault(phase, []).append(i)

        # Extract phase titles from parent task description
        phase_titles = _extract_phase_titles(task.description or "")

        # Create subepic tasks for each phase (only if >1 phase)
        phase_subepic_ids: dict[int, str] = {}
        created_subepic_ids: list[str] = []  # for cleanup on failure
        has_phases = len([p for p in phase_map if p > 0]) > 1

        if has_phases:
            try:
                for phase_num in sorted(phase_map.keys()):
                    if phase_num == 0:
                        continue  # Unphased tasks stay under root
                    title = phase_titles.get(phase_num, f"Phase {phase_num}")
                    result = ctx.task_manager.create_task_with_decomposition(
                        project_id=task.project_id,
                        title=title,
                        task_type="epic",
                        parent_task_id=resolved_id,
                        category="planning",
                        validation_criteria=epic_validation,
                        created_in_session_id=resolved_session_id,
                    )
                    subepic_id = result["task"]["id"]
                    created_subepic_ids.append(subepic_id)
                    phase_subepic_ids[phase_num] = subepic_id
                logger.info(
                    f"Created {len(phase_subepic_ids)} phase subepics for task {parent_task_id}"
                )
            except Exception as e:
                logger.error(f"Failed to create phase subepics: {e}")
                for se_id in created_subepic_ids:
                    try:
                        ctx.task_manager.delete_task(se_id)
                    except Exception:
                        pass
                return {"error": f"Phase subepic creation failed: {e}"}

        # Create subtasks atomically - clean up on failure
        created_tasks = []
        created_refs = []

        try:
            for subtask in subtasks:
                raw_description = subtask.get("description") or ""
                description = (
                    f"{plan_ref_block}{raw_description}" if plan_ref_block else raw_description
                )

                # Parent under phase subepic if available, otherwise root epic
                subtask_phase = _get_subtask_phase(subtask)
                parent_id = phase_subepic_ids.get(subtask_phase, resolved_id)

                result = ctx.task_manager.create_task_with_decomposition(
                    project_id=task.project_id,
                    title=subtask["title"],
                    description=description or None,
                    priority=subtask.get("priority", 2),
                    task_type=subtask.get("task_type", "task"),
                    parent_task_id=parent_id,
                    category=subtask.get("category"),
                    validation_criteria=subtask.get("validation"),
                    created_in_session_id=resolved_session_id,
                )

                # Get the task (create_task_with_decomposition returns dict with task dict)
                subtask_id = result["task"]["id"]
                created_task = ctx.task_manager.get_task(subtask_id)
                created_tasks.append(created_task)

                # Build ref
                ref = f"#{created_task.seq_num}" if created_task.seq_num else created_task.id
                created_refs.append(ref)
        except Exception as e:
            # Clean up any tasks created before failure (subtasks + subepics)
            logger.error(f"Expansion failed after creating {len(created_tasks)} tasks: {e}")
            for task_to_delete in created_tasks:
                try:
                    ctx.task_manager.delete_task(task_to_delete.id)
                except Exception as delete_err:
                    logger.warning(f"Failed to clean up task {task_to_delete.id}: {delete_err}")
            for se_id in created_subepic_ids:
                try:
                    ctx.task_manager.delete_task(se_id)
                except Exception:
                    pass
            return {"error": f"Expansion failed: {e}", "cleaned_up": len(created_tasks)}

        # Wire dependencies between subtasks
        for i, subtask in enumerate(subtasks):
            depends_on = subtask.get("depends_on", [])
            for dep_idx in depends_on:
                if 0 <= dep_idx < len(created_tasks):
                    try:
                        ctx.dep_manager.add_dependency(
                            task_id=created_tasks[i].id,
                            depends_on=created_tasks[dep_idx].id,
                            dep_type="blocks",
                        )
                    except ValueError:
                        pass  # Dependency already exists or invalid

        # Wire blocking relationships for the task hierarchy
        if phase_subepic_ids:
            # Phase subepics blocked by their children
            for phase_num, subepic_id in phase_subepic_ids.items():
                for idx in phase_map.get(phase_num, []):
                    if idx < len(created_tasks):
                        try:
                            ctx.dep_manager.add_dependency(
                                task_id=subepic_id,
                                depends_on=created_tasks[idx].id,
                                dep_type="blocks",
                            )
                        except ValueError:
                            pass

            # Root epic blocked by subepics
            for subepic_id in phase_subepic_ids.values():
                try:
                    ctx.dep_manager.add_dependency(
                        task_id=resolved_id,
                        depends_on=subepic_id,
                        dep_type="blocks",
                    )
                except ValueError:
                    pass

            # Unphased tasks (phase 0) still block root epic directly
            for idx in phase_map.get(0, []):
                if idx < len(created_tasks):
                    try:
                        ctx.dep_manager.add_dependency(
                            task_id=resolved_id,
                            depends_on=created_tasks[idx].id,
                            dep_type="blocks",
                        )
                    except ValueError:
                        pass
        else:
            # No phases — all children block root epic directly (original behavior)
            for created_task in created_tasks:
                try:
                    ctx.dep_manager.add_dependency(
                        task_id=resolved_id,
                        depends_on=created_task.id,
                        dep_type="blocks",
                    )
                except ValueError:
                    pass  # Already exists

        # Update parent task status
        ctx.task_manager.update_task(
            resolved_id,
            expansion_status="completed",
            validation_criteria=epic_validation,
        )

        logger.info(
            f"Executed expansion for task {parent_task_id}: created {len(created_tasks)} subtasks"
        )

        return {
            "created": created_refs,
            "count": len(created_refs),
        }

    async def get_expansion_spec(
        task_id: str,
        project: str | None = None,
    ) -> dict[str, Any]:
        """Check for pending expansion spec (for resume after compaction).

        Used by /gobby-expand skill to check if there's a pending expansion
        that was interrupted and can be resumed.

        Args:
            task_id: Task ID to check
            project: Project name or UUID for task resolution (optional)

        Returns:
            {"pending": True, "spec": {...}} if pending expansion exists
            {"pending": False} otherwise
        """
        # Get project context
        try:
            project_id = ctx.resolve_project_filter(project)
        except ValueError as e:
            return {"error": str(e)}

        # Resolve task ID
        try:
            resolved_id = resolve_task_id_for_mcp(ctx.task_manager, task_id, project_id)
        except (TaskNotFoundError, ValueError) as e:
            return {"error": f"Task not found: {e}"}

        # Get task
        task = ctx.task_manager.get_task(resolved_id)
        if not task:
            return {"error": f"Task {task_id} not found"}

        # Check for pending expansion
        if task.expansion_status == "pending" and task.expansion_context:
            try:
                spec = json.loads(task.expansion_context)
                return {
                    "pending": True,
                    "spec": spec,
                    "subtask_count": len(spec.get("subtasks", [])),
                }
            except json.JSONDecodeError:
                return {"pending": False, "error": "Invalid expansion_context JSON"}

        return {"pending": False}

    async def validate_expansion_spec(
        task_id: str,
        project: str | None = None,
    ) -> dict[str, Any]:
        """Validate a saved expansion spec for structural correctness and plan coverage.

        Checks:
        1. Non-empty subtasks list
        2. Required fields present (title, description, category)
        3. Valid dependency indices (no out-of-bounds, no self-references)
        4. No circular dependencies
        5. If parent task description has ### N.N plan sections, verifies coverage

        Args:
            task_id: Task ID with saved expansion spec
            project: Project name or UUID for task resolution (optional)

        Returns:
            {"valid": bool, "errors": list[str], "subtask_count": int}
        """
        try:
            project_id = ctx.resolve_project_filter(project)
        except ValueError as e:
            return {"error": str(e)}

        try:
            resolved_id = resolve_task_id_for_mcp(ctx.task_manager, task_id, project_id)
        except (TaskNotFoundError, ValueError) as e:
            return {"error": f"Task not found: {e}"}

        task = ctx.task_manager.get_task(resolved_id)
        if not task:
            return {"error": f"Task {task_id} not found"}

        if not task.expansion_context:
            return {"error": "No expansion spec saved on task"}

        try:
            spec = json.loads(task.expansion_context)
        except json.JSONDecodeError as e:
            return {"valid": False, "errors": [f"Invalid JSON in expansion_context: {e}"]}

        errors: list[str] = []
        subtasks = spec.get("subtasks", [])

        # 1. Non-empty subtasks
        if not subtasks:
            return {"valid": False, "errors": ["Spec contains no subtasks"], "subtask_count": 0}

        n = len(subtasks)

        for i, st in enumerate(subtasks):
            # 2. Required fields
            if not st.get("title", "").strip():
                errors.append(f"Subtask {i}: missing or empty 'title'")
            if not st.get("description", "").strip():
                errors.append(f"Subtask {i}: missing or empty 'description'")
            if not st.get("category", "").strip():
                errors.append(f"Subtask {i}: missing or empty 'category'")

            # 3. Valid dependency indices
            for dep_idx in st.get("depends_on", []):
                if not isinstance(dep_idx, int):
                    errors.append(f"Subtask {i}: dependency '{dep_idx}' is not an integer")
                elif dep_idx == i:
                    errors.append(f"Subtask {i}: self-reference in depends_on")
                elif dep_idx < 0 or dep_idx >= n:
                    errors.append(
                        f"Subtask {i}: depends_on index {dep_idx} out of bounds (0-{n - 1})"
                    )

        # 4. Cycle detection (only if no structural dependency errors)
        dep_errors = [e for e in errors if "depends_on" in e or "self-reference" in e]
        if not dep_errors:
            WHITE, GRAY, BLACK = 0, 1, 2
            color = [WHITE] * n
            adj: dict[int, list[int]] = {i: [] for i in range(n)}
            for i, st in enumerate(subtasks):
                for dep_idx in st.get("depends_on", []):
                    if isinstance(dep_idx, int) and 0 <= dep_idx < n:
                        adj[i].append(dep_idx)

            def _has_cycle_from(node: int) -> bool:
                color[node] = GRAY
                for neighbor in adj[node]:
                    if color[neighbor] == GRAY:
                        return True
                    if color[neighbor] == WHITE and _has_cycle_from(neighbor):
                        return True
                color[node] = BLACK
                return False

            for i in range(n):
                if color[i] == WHITE and _has_cycle_from(i):
                    errors.append("Circular dependency detected in subtask depends_on")
                    break

        # 5. Plan section coverage
        if task.description:
            plan_sections = set(re.findall(r"^###\s+(\d+\.\d+)\s", task.description, re.MULTILINE))
            if plan_sections:
                covered: set[str] = set()
                for st in subtasks:
                    title = st.get("title", "")
                    desc = st.get("description", "")
                    text = f"{title}\n{desc}"
                    for section in plan_sections:
                        if section in text:
                            covered.add(section)

                missing = plan_sections - covered
                if missing:
                    errors.append(f"Plan sections not covered by any subtask: {sorted(missing)}")

        result: dict[str, Any] = {
            "valid": len(errors) == 0,
            "errors": errors,
            "subtask_count": n,
        }
        plan_file = spec.get("plan_file")
        if plan_file:
            result["plan_file"] = plan_file
        return result

    # Register tools
    registry.register(
        name="save_expansion_spec",
        description="Save expansion spec to task for later execution. Used by /gobby-expand skill.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task ID to expand (can be #N, path, or UUID)",
                },
                "spec": {
                    "type": "object",
                    "description": "Expansion specification containing subtasks array and optional plan_file",
                    "properties": {
                        "plan_file": {
                            "type": "string",
                            "description": "Relative path to the plan file for context injection into subtask descriptions",
                        },
                        "subtasks": {
                            "type": "array",
                            "description": "List of subtask definitions",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "title": {"type": "string"},
                                    "category": {"type": "string"},
                                    "depends_on": {
                                        "type": "array",
                                        "items": {"type": "integer"},
                                    },
                                    "validation": {"type": "string"},
                                    "description": {"type": "string"},
                                    "priority": {"type": "integer"},
                                    "affected_files": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "Files this subtask will touch (relative to repo root)",
                                    },
                                },
                                "required": ["title"],
                            },
                        },
                    },
                    "required": ["subtasks"],
                },
                "project": {
                    "type": "string",
                    "description": "Project name or UUID for task resolution",
                },
            },
            "required": ["task_id", "spec"],
        },
        func=save_expansion_spec,
    )

    registry.register(
        name="execute_expansion",
        description="Execute a saved expansion spec atomically. Creates subtasks with dependencies.",
        input_schema={
            "type": "object",
            "properties": {
                "parent_task_id": {
                    "type": "string",
                    "description": "Task ID with saved expansion spec",
                },
                "project": {
                    "type": "string",
                    "description": "Project name or UUID for task resolution",
                },
                "tdd": {
                    "type": "boolean",
                    "description": "Apply TDD sandwich pattern: wrap each phase with [TEST] and [REF] tasks",
                    "default": False,
                },
            },
            "required": ["parent_task_id"],
        },
        func=execute_expansion,
    )

    registry.register(
        name="get_expansion_spec",
        description="Check for pending expansion spec (for resume after session compaction).",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task ID to check",
                },
                "project": {
                    "type": "string",
                    "description": "Project name or UUID for task resolution",
                },
            },
            "required": ["task_id"],
        },
        func=get_expansion_spec,
    )

    registry.register(
        name="validate_expansion_spec",
        description="Validate a saved expansion spec. Checks structure, dependencies, and plan coverage.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task ID with saved expansion spec",
                },
                "project": {
                    "type": "string",
                    "description": "Project name or UUID for task resolution",
                },
            },
            "required": ["task_id"],
        },
        func=validate_expansion_spec,
    )

    async def save_expansion_qa_result(
        task_id: str,
        result: dict[str, Any],
        project: str | None = None,
    ) -> dict[str, Any]:
        """Save expansion QA result to task.expansion_context.qa_result.

        Called by the expansion-qa agent after validating the task tree.
        Stores the QA findings alongside the existing expansion spec.

        Args:
            task_id: Parent task ID (can be #N, path, or UUID)
            result: QA result containing:
                - passed: bool - whether the expansion passed QA
                - fixes: list[dict] - fixes applied [{type, task_ref, detail}]
                - escalations: list[dict] - unfixable issues [{type, detail}]
            project: Project name or UUID for task resolution (optional)

        Returns:
            {"saved": True, "task_id": str, "passed": bool}
        """
        try:
            project_id = ctx.resolve_project_filter(project)
        except ValueError as e:
            return {"error": str(e)}

        try:
            resolved_id = resolve_task_id_for_mcp(ctx.task_manager, task_id, project_id)
        except (TaskNotFoundError, ValueError) as e:
            return {"error": f"Task not found: {e}"}

        # Validate result structure
        if not isinstance(result.get("passed"), bool):
            return {"error": "result.passed must be a boolean"}
        if not isinstance(result.get("fixes"), list):
            return {"error": "result.fixes must be a list"}
        if not isinstance(result.get("escalations"), list):
            return {"error": "result.escalations must be a list"}

        # Load existing expansion_context or start fresh
        task = ctx.task_manager.get_task(resolved_id)
        if not task:
            return {"error": f"Task {task_id} not found"}

        existing_context: dict[str, Any] = {}
        if task.expansion_context:
            try:
                existing_context = json.loads(task.expansion_context)
            except json.JSONDecodeError:
                existing_context = {}

        # Store QA result alongside existing spec data
        existing_context["qa_result"] = result

        ctx.task_manager.update_task(
            resolved_id,
            expansion_context=json.dumps(existing_context),
        )

        logger.info(
            f"Saved expansion QA result for task {task_id}: "
            f"passed={result['passed']}, "
            f"fixes={len(result['fixes'])}, "
            f"escalations={len(result['escalations'])}"
        )

        return {
            "saved": True,
            "task_id": resolved_id,
            "passed": result["passed"],
        }

    async def check_expansion_qa_result(
        task_id: str,
        project: str | None = None,
    ) -> dict[str, Any]:
        """Check expansion QA result from task.expansion_context.qa_result.

        Used by the expand-task pipeline to read QA findings after the
        QA agent completes.

        Args:
            task_id: Parent task ID (can be #N, path, or UUID)
            project: Project name or UUID for task resolution (optional)

        Returns:
            {"passed": bool, "fixes": [...], "escalations": [...]}
            or {"error": str} if no QA result exists
        """
        try:
            project_id = ctx.resolve_project_filter(project)
        except ValueError as e:
            return {"error": str(e)}

        try:
            resolved_id = resolve_task_id_for_mcp(ctx.task_manager, task_id, project_id)
        except (TaskNotFoundError, ValueError) as e:
            return {"error": f"Task not found: {e}"}

        task = ctx.task_manager.get_task(resolved_id)
        if not task:
            return {"error": f"Task {task_id} not found"}

        skipped_response: dict[str, Any] = {
            "passed": True,
            "qa_skipped": True,
            "fixes": [],
            "escalations": [],
        }

        if not task.expansion_context:
            logger.warning(f"check_expansion_qa_result: no expansion_context on task {task_id}")
            return {**skipped_response, "reason": "No expansion context on task"}

        try:
            context = json.loads(task.expansion_context)
        except json.JSONDecodeError:
            logger.warning(
                f"check_expansion_qa_result: invalid JSON in expansion_context for task {task_id}"
            )
            return {**skipped_response, "reason": "Invalid expansion_context JSON"}

        qa_result = context.get("qa_result")
        if qa_result is None:
            logger.warning(
                f"check_expansion_qa_result: no qa_result in expansion_context for task {task_id}"
            )
            return {**skipped_response, "reason": "QA agent did not save result"}

        return dict(qa_result) if isinstance(qa_result, dict) else {"result": qa_result}

    registry.register(
        name="save_expansion_qa_result",
        description="Save expansion QA result after validating task tree against plan.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Parent task ID (can be #N, path, or UUID)",
                },
                "result": {
                    "type": "object",
                    "description": "QA result with passed, fixes, and escalations",
                    "properties": {
                        "passed": {
                            "type": "boolean",
                            "description": "Whether the expansion passed QA",
                        },
                        "fixes": {
                            "type": "array",
                            "items": {"type": "object"},
                            "description": "Fixes applied: [{type, task_ref, detail}]",
                        },
                        "escalations": {
                            "type": "array",
                            "items": {"type": "object"},
                            "description": "Unfixable issues: [{type, detail}]",
                        },
                    },
                    "required": ["passed", "fixes", "escalations"],
                },
                "project": {
                    "type": "string",
                    "description": "Project name or UUID for task resolution",
                },
            },
            "required": ["task_id", "result"],
        },
        func=save_expansion_qa_result,
    )

    registry.register(
        name="check_expansion_qa_result",
        description="Check expansion QA result. Used by pipeline to gate on QA pass/fail.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Parent task ID (can be #N, path, or UUID)",
                },
                "project": {
                    "type": "string",
                    "description": "Project name or UUID for task resolution",
                },
            },
            "required": ["task_id"],
        },
        func=check_expansion_qa_result,
    )

    return registry
