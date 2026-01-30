"""Session integration tools for task management.

Provides tools for linking tasks to sessions and querying task-session
relationships.
"""

from typing import Any

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.mcp_proxy.tools.tasks._context import RegistryContext
from gobby.mcp_proxy.tools.tasks._resolution import resolve_task_id_for_mcp
from gobby.storage.tasks import TaskNotFoundError


def create_session_registry(ctx: RegistryContext) -> InternalToolRegistry:
    """Create a registry with session-task integration tools.

    Args:
        ctx: Shared registry context

    Returns:
        InternalToolRegistry with session tools registered
    """
    registry = InternalToolRegistry(
        name="gobby-tasks-session",
        description="Task-session integration tools",
    )

    def link_task_to_session(
        task_id: str,
        session_id: str | None = None,
        action: str = "worked_on",
    ) -> dict[str, Any]:
        """Link a task to a session."""
        if not session_id:
            return {"error": "session_id is required"}

        try:
            resolved_id = resolve_task_id_for_mcp(ctx.task_manager, task_id)
        except (TaskNotFoundError, ValueError) as e:
            return {"error": str(e)}

        # Resolve session_id to UUID (accepts #N, N, UUID, or prefix)
        try:
            resolved_session_id = ctx.resolve_session_id(session_id)
        except ValueError as e:
            return {"error": f"Invalid session_id '{session_id}': {e}"}

        try:
            ctx.session_task_manager.link_task(resolved_session_id, resolved_id, action)
            return {}
        except ValueError as e:
            return {"error": str(e)}

    registry.register(
        name="link_task_to_session",
        description="Link a task to a session. Accepts #N, N, UUID, or prefix for session_id.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task reference: #N (e.g., #1, #47), path (e.g., 1.2.3), or UUID",
                },
                "session_id": {
                    "type": "string",
                    "description": "Session reference (accepts #N, N, UUID, or prefix)",
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
        # Resolve session_id to UUID (accepts #N, N, UUID, or prefix)
        try:
            resolved_session_id = ctx.resolve_session_id(session_id)
        except ValueError as e:
            return {"error": f"Invalid session_id '{session_id}': {e}"}

        tasks = ctx.session_task_manager.get_session_tasks(resolved_session_id)
        return {"session_id": resolved_session_id, "tasks": tasks}

    registry.register(
        name="get_session_tasks",
        description="Get all tasks associated with a session. Accepts #N, N, UUID, or prefix for session_id.",
        input_schema={
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Session reference (accepts #N, N, UUID, or prefix)",
                },
            },
            "required": ["session_id"],
        },
        func=get_session_tasks,
    )

    def get_task_sessions(task_id: str) -> dict[str, Any]:
        """Get all sessions that touched a task."""
        try:
            resolved_id = resolve_task_id_for_mcp(ctx.task_manager, task_id)
        except (TaskNotFoundError, ValueError) as e:
            return {"error": str(e)}
        task = ctx.task_manager.get_task(resolved_id)
        sessions = ctx.session_task_manager.get_task_sessions(resolved_id)
        # Handle case where task is not found (shouldn't happen after resolve, but be defensive)
        ref = f"#{task.seq_num}" if task and task.seq_num else resolved_id[:8]
        return {
            "ref": ref,
            "task_id": resolved_id,
            "sessions": sessions,
        }

    registry.register(
        name="get_task_sessions",
        description="Get all sessions that touched a task.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task reference: #N (e.g., #1, #47), path (e.g., 1.2.3), or UUID",
                },
            },
            "required": ["task_id"],
        },
        func=get_task_sessions,
    )

    return registry
