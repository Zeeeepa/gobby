"""
Task readiness MCP tools module.

Provides tools for task readiness management:
- list_ready_tasks: List tasks with no unresolved blocking dependencies
- list_blocked_tasks: List tasks that are blocked by dependencies
- suggest_next_task: Suggest the best next task based on scoring

Extracted from tasks.py using Strangler Fig pattern for code decomposition.
"""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.utils.project_context import get_project_context

if TYPE_CHECKING:
    from gobby.storage.tasks import LocalTaskManager

__all__ = ["create_readiness_registry", "is_descendant_of"]


def get_current_project_id() -> str | None:
    """Get the current project ID from context."""
    context = get_project_context()
    return context.get("id") if context else None


def _get_ready_descendants(
    task_manager: "LocalTaskManager",
    parent_id: str,
    task_type: str | None = None,
    project_id: str | None = None,
) -> list:
    """
    Get all ready tasks that are descendants of the given parent task.

    Traverses the task hierarchy to find all tasks under parent_id,
    then filters to only those that are ready (open with no blockers).

    Args:
        task_manager: LocalTaskManager instance
        parent_id: ID of the ancestor task to filter by
        task_type: Optional task type filter
        project_id: Optional project ID filter

    Returns:
        List of ready Task objects that are descendants of parent_id
    """
    # Get all ready tasks first
    all_ready = task_manager.list_ready_tasks(
        task_type=task_type,
        limit=200,  # Get more since we'll filter
        project_id=project_id,
    )

    if not all_ready:
        return []

    # Build a set of all descendant IDs by traversing the hierarchy
    descendant_ids = set()
    to_check = [parent_id]

    while to_check:
        current_id = to_check.pop()
        # Get direct children of this task
        children = task_manager.list_tasks(parent_task_id=current_id, limit=100)
        for child in children:
            if child.id not in descendant_ids:
                descendant_ids.add(child.id)
                to_check.append(child.id)

    # Filter ready tasks to only descendants
    return [t for t in all_ready if t.id in descendant_ids]


def is_descendant_of(
    task_manager: "LocalTaskManager",
    task_id: str,
    ancestor_id: str,
) -> bool:
    """
    Check if a task is a descendant of another task.

    Traverses up the parent chain from task_id to check if
    ancestor_id appears in the ancestry.

    Args:
        task_manager: LocalTaskManager instance
        task_id: ID of the potential descendant task
        ancestor_id: ID of the potential ancestor task

    Returns:
        True if task_id is a descendant of ancestor_id
    """
    if task_id == ancestor_id:
        return True  # A task is considered a descendant of itself

    current_id: str | None = task_id
    visited: set[str] = set()

    while current_id and current_id not in visited:
        visited.add(current_id)
        task = task_manager.get_task(current_id)
        if not task:
            return False
        if task.parent_task_id == ancestor_id:
            return True
        current_id = task.parent_task_id

    return False


class ReadinessToolRegistry(InternalToolRegistry):
    """Registry for readiness tools with test-friendly get_tool method."""

    def get_tool(self, name: str) -> Callable[..., Any] | None:
        """Get a tool function by name (for testing)."""
        tool = self._tools.get(name)
        return tool.func if tool else None


def create_readiness_registry(
    task_manager: "LocalTaskManager | None" = None,
) -> ReadinessToolRegistry:
    """
    Create a registry with task readiness tools.

    Args:
        task_manager: LocalTaskManager instance (required)

    Returns:
        ReadinessToolRegistry with readiness tools registered
    """
    registry = ReadinessToolRegistry(
        name="gobby-tasks-readiness",
        description="Task readiness management tools",
    )

    if task_manager is None:
        raise ValueError("task_manager is required")

    # --- list_ready_tasks ---

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

    # --- list_blocked_tasks ---

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

    # --- suggest_next_task ---

    def suggest_next_task(
        task_type: str | None = None,
        prefer_subtasks: bool = True,
        parent_id: str | None = None,
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
            parent_id: Filter to descendants of this task (optional).
                      When set, only tasks under this parent hierarchy are considered.
                      Use this to scope suggestions to a specific epic/feature.

        Returns:
            Suggested task with reasoning
        """
        # Filter by current project
        project_id = get_current_project_id()

        # If parent_id is set, get all descendants of that task
        if parent_id:
            ready_tasks = _get_ready_descendants(task_manager, parent_id, task_type, project_id)
        else:
            ready_tasks = task_manager.list_ready_tasks(
                task_type=task_type, limit=50, project_id=project_id
            )

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

    registry.register(
        name="suggest_next_task",
        description="Suggest the best next task to work on based on priority, readiness, and complexity. "
        "Use parent_id to scope suggestions to a specific epic/feature hierarchy.",
        input_schema={
            "type": "object",
            "properties": {
                "task_type": {
                    "type": "string",
                    "description": "Filter by task type (optional)",
                    "default": None,
                },
                "prefer_subtasks": {
                    "type": "boolean",
                    "description": "Prefer leaf tasks over parent tasks (default: True)",
                    "default": True,
                },
                "parent_id": {
                    "type": "string",
                    "description": "Filter to descendants of this task (optional). "
                    "When set, only tasks under this parent hierarchy are considered. "
                    "Use this to scope suggestions to a specific epic/feature.",
                    "default": None,
                },
            },
        },
        func=suggest_next_task,
    )

    return registry
