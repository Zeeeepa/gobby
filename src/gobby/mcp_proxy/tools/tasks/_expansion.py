"""Expansion tools for skill-based task decomposition.

Provides tools for the /gobby-expand skill workflow:
1. save_expansion_spec - Save expansion spec to task for later execution
2. execute_expansion - Create subtasks atomically from saved spec
3. get_expansion_spec - Check for pending expansion (for resume)
"""

import json
import logging
from typing import Any

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.mcp_proxy.tools.tasks._context import RegistryContext
from gobby.mcp_proxy.tools.tasks._resolution import resolve_task_id_for_mcp
from gobby.storage.tasks import TaskNotFoundError
from gobby.utils.project_context import get_project_context

logger = logging.getLogger(__name__)


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

        Returns:
            {"saved": True, "task_id": str, "subtask_count": int}
        """
        # Get project context
        project_ctx = get_project_context()
        project_id = project_ctx.get("id") if project_ctx else None

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
        session_id: str,
    ) -> dict[str, Any]:
        """Execute a saved expansion spec atomically.

        Creates all subtasks from the saved spec and wires dependencies.
        Call save_expansion_spec first to persist the spec.

        Args:
            parent_task_id: Task ID with saved expansion spec
            session_id: Session ID for tracking created tasks

        Returns:
            {"created": ["#N", ...], "count": int} or {"error": str}
        """
        # Get project context
        project_ctx = get_project_context()
        project_id = project_ctx.get("id") if project_ctx else None

        # Resolve task ID
        try:
            resolved_id = resolve_task_id_for_mcp(ctx.task_manager, parent_task_id, project_id)
        except (TaskNotFoundError, ValueError) as e:
            return {"error": f"Task not found: {e}"}

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

        # Create subtasks atomically - clean up on failure
        created_tasks = []
        created_refs = []

        try:
            for subtask in subtasks:
                result = ctx.task_manager.create_task_with_decomposition(
                    project_id=task.project_id,
                    title=subtask["title"],
                    description=subtask.get("description"),
                    priority=subtask.get("priority", 2),
                    task_type=subtask.get("task_type", "task"),
                    parent_task_id=resolved_id,
                    category=subtask.get("category"),
                    validation_criteria=subtask.get("validation"),
                    created_in_session_id=session_id,
                )

                # Get the task (create_task_with_decomposition returns dict with task dict)
                subtask_id = result["task"]["id"]
                created_task = ctx.task_manager.get_task(subtask_id)
                created_tasks.append(created_task)

                # Build ref
                ref = f"#{created_task.seq_num}" if created_task.seq_num else created_task.id[:8]
                created_refs.append(ref)
        except Exception as e:
            # Clean up any tasks created before failure
            logger.error(f"Expansion failed after creating {len(created_tasks)} tasks: {e}")
            for task_to_delete in created_tasks:
                try:
                    ctx.task_manager.delete_task(task_to_delete.id)
                except Exception as delete_err:
                    logger.warning(f"Failed to clean up task {task_to_delete.id}: {delete_err}")
            return {"error": f"Expansion failed: {e}", "cleaned_up": len(created_tasks)}

        # Wire dependencies
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

        # Wire parent blocked by all children
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
            is_expanded=True,
            expansion_status="completed",
            validation_criteria="All subtasks must be completed (status: closed).",
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
    ) -> dict[str, Any]:
        """Check for pending expansion spec (for resume after compaction).

        Used by /gobby-expand skill to check if there's a pending expansion
        that was interrupted and can be resumed.

        Args:
            task_id: Task ID to check

        Returns:
            {"pending": True, "spec": {...}} if pending expansion exists
            {"pending": False} otherwise
        """
        # Get project context
        project_ctx = get_project_context()
        project_id = project_ctx.get("id") if project_ctx else None

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
                    "description": "Expansion specification containing subtasks array",
                    "properties": {
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
                                },
                                "required": ["title"],
                            },
                        },
                    },
                    "required": ["subtasks"],
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
                "session_id": {
                    "type": "string",
                    "description": "Session ID for tracking created tasks",
                },
            },
            "required": ["parent_task_id", "session_id"],
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
            },
            "required": ["task_id"],
        },
        func=get_expansion_spec,
    )

    return registry
