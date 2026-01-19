"""Task ID resolution for MCP tools.

Provides resolve_task_id_for_mcp() which resolves various task reference
formats (#N, N, path, UUID) to task UUIDs.
"""

from gobby.mcp_proxy.tools.tasks._helpers import _is_path_format
from gobby.storage.tasks import LocalTaskManager, TaskNotFoundError
from gobby.utils.project_context import get_project_context


def resolve_task_id_for_mcp(
    task_manager: LocalTaskManager,
    task_id: str,
    project_id: str | None = None,
) -> str:
    """Resolve a task reference to its UUID for MCP tools.

    Supports multiple reference formats:
      - #N: Project-scoped seq_num (e.g., #1, #47) - requires project_id
      - N: Bare numeric seq_num (e.g., 1, 47) - requires project_id
      - 1.2.3: Path cache format - requires project_id
      - UUID: Direct UUID lookup (validated to exist)

    Args:
        task_manager: The task manager
        task_id: Task reference in any supported format
        project_id: Project ID for scoped lookups (#N and path formats).
                   If not provided, will try to get from project context.

    Returns:
        The resolved task UUID

    Raises:
        TaskNotFoundError: If the reference cannot be resolved
        ValueError: If the format is invalid
    """
    # Get project_id from context if not provided
    if project_id is None:
        ctx = get_project_context()
        project_id = ctx.get("id") if ctx else None

    # Check for #N format or path format (requires project_id)
    if project_id and (task_id.startswith("#") or _is_path_format(task_id)):
        return task_manager.resolve_task_reference(task_id, project_id)

    # Check for bare numeric string (seq_num without #)
    if project_id and task_id.isdigit():
        return task_manager.resolve_task_reference(f"#{task_id}", project_id)

    # UUID format: validate it exists by trying to get it
    task = task_manager.get_task(task_id)
    if task is None:
        raise TaskNotFoundError(f"Task with UUID '{task_id}' not found")
    return task_id
