"""
Task dependency MCP tools module.

Provides tools for managing task dependencies:
- add_dependency: Add a dependency between tasks
- remove_dependency: Remove a dependency
- get_dependency_tree: Get upstream/downstream dependencies
- check_dependency_cycles: Detect circular dependencies

Extracted from tasks.py using Strangler Fig pattern for code decomposition.
"""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.utils.project_context import get_project_context

if TYPE_CHECKING:
    from gobby.storage.task_dependencies import TaskDependencyManager
    from gobby.storage.tasks import LocalTaskManager

__all__ = ["create_dependency_registry"]


def get_current_project_id() -> str | None:
    """Get the current project ID from context."""
    context = get_project_context()
    return context.get("id") if context else None


class DependencyToolRegistry(InternalToolRegistry):
    """Registry for dependency tools with test-friendly get_tool method."""

    def get_tool(self, name: str) -> Callable[..., Any] | None:
        """Get a tool function by name (for testing)."""
        tool = self._tools.get(name)
        return tool.func if tool else None


def create_dependency_registry(
    task_manager: "LocalTaskManager | None" = None,
    dep_manager: "TaskDependencyManager | None" = None,
) -> DependencyToolRegistry:
    """
    Create a registry with task dependency tools.

    Args:
        task_manager: LocalTaskManager instance (optional)
        dep_manager: TaskDependencyManager instance

    Returns:
        DependencyToolRegistry with dependency tools registered
    """
    registry = DependencyToolRegistry(
        name="gobby-tasks-dependencies",
        description="Task dependency management tools",
    )

    if dep_manager is None:
        raise ValueError("dep_manager is required")

    # --- add_dependency ---

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
        description="Add a dependency between tasks. Creates a blocking relationship where depends_on must complete before task_id.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "The dependent task (blocked by depends_on)",
                },
                "depends_on": {
                    "type": "string",
                    "description": "The blocker task (must complete first)",
                },
                "dep_type": {
                    "type": "string",
                    "description": 'Dependency type: "blocks" (default), "discovered-from", or "related"',
                    "default": "blocks",
                    "enum": ["blocks", "discovered-from", "related"],
                },
            },
            "required": ["task_id", "depends_on"],
        },
        func=add_dependency,
    )

    # --- remove_dependency ---

    def remove_dependency(task_id: str, depends_on: str) -> dict[str, Any]:
        """Remove a dependency between tasks."""
        dep_manager.remove_dependency(task_id, depends_on)
        return {"removed": True, "task_id": task_id, "depends_on": depends_on}

    registry.register(
        name="remove_dependency",
        description="Remove a dependency between tasks.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "The dependent task",
                },
                "depends_on": {
                    "type": "string",
                    "description": "The blocker task to unlink",
                },
            },
            "required": ["task_id", "depends_on"],
        },
        func=remove_dependency,
    )

    # --- get_dependency_tree ---

    def get_dependency_tree(task_id: str, direction: str = "both") -> dict[str, Any]:
        """Get dependency tree for a task."""
        tree: dict[str, Any] = dep_manager.get_dependency_tree(task_id)
        if direction == "blockers":
            return {"blockers": tree.get("blockers", [])}
        elif direction == "blocking":
            return {"blocking": tree.get("blocking", [])}
        return tree

    registry.register(
        name="get_dependency_tree",
        description="Get dependency tree showing upstream blockers and downstream dependents.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Root task ID to get tree for",
                },
                "direction": {
                    "type": "string",
                    "description": '"blockers" (upstream), "blocking" (downstream), or "both"',
                    "default": "both",
                    "enum": ["blockers", "blocking", "both"],
                },
            },
            "required": ["task_id"],
        },
        func=get_dependency_tree,
    )

    # --- check_dependency_cycles ---

    def check_dependency_cycles() -> dict[str, Any]:
        """Detect circular dependencies in the project."""
        cycles = dep_manager.check_cycles()
        if cycles:
            return {"has_cycles": True, "cycles": cycles}
        return {"has_cycles": False}

    registry.register(
        name="check_dependency_cycles",
        description="Detect circular dependencies in the project. Returns any cycles found.",
        input_schema={"type": "object", "properties": {}},
        func=check_dependency_cycles,
    )

    return registry
