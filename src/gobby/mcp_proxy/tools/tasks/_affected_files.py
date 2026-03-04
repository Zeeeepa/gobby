"""MCP tools for task affected files.

Provides tools for managing file annotations on tasks:
- set_affected_files: Bulk set files for a task
- get_affected_files: Query files for a task
- find_file_overlaps: Detect file contention between tasks
"""

from typing import TYPE_CHECKING, Any

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.mcp_proxy.tools.tasks._resolution import resolve_task_id_for_mcp
from gobby.storage.task_affected_files import AnnotationSource, TaskAffectedFileManager
from gobby.storage.tasks import TaskNotFoundError

if TYPE_CHECKING:
    from gobby.mcp_proxy.tools.tasks._context import RegistryContext

__all__ = ["create_affected_files_registry"]


def create_affected_files_registry(ctx: "RegistryContext") -> InternalToolRegistry:
    """Create a registry with task affected file tools."""

    registry = InternalToolRegistry(
        name="gobby-tasks-affected-files",
        description="Task affected file management tools",
    )

    af_manager = TaskAffectedFileManager(ctx.task_manager.db)

    # --- set_affected_files ---

    def set_affected_files(
        task_id: str,
        files: list[str],
        source: str = "manual",
    ) -> dict[str, Any]:
        """Set affected files for a task."""
        try:
            resolved_id = resolve_task_id_for_mcp(ctx.task_manager, task_id)
        except (TaskNotFoundError, ValueError) as e:
            return {"error": f"Invalid task_id: {e}"}

        if source not in ("expansion", "manual", "observed"):
            return {"error": f"Invalid source: {source}. Must be 'expansion', 'manual', or 'observed'."}

        annotation_source: AnnotationSource = source  # type: ignore[assignment]
        results = af_manager.set_files(resolved_id, files, annotation_source)
        return {
            "task_id": resolved_id,
            "files_set": len(results),
            "files": [r.file_path for r in results],
        }

    registry.register(
        name="set_affected_files",
        description="Set affected files for a task. Replaces existing files for the given source.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task reference: #N, path, or UUID",
                },
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of file paths (relative to repo root)",
                },
                "source": {
                    "type": "string",
                    "description": "Annotation source: 'expansion', 'manual' (default), or 'observed'",
                    "default": "manual",
                    "enum": ["expansion", "manual", "observed"],
                },
            },
            "required": ["task_id", "files"],
        },
        func=set_affected_files,
    )

    # --- get_affected_files ---

    def get_affected_files(task_id: str) -> dict[str, Any]:
        """Get affected files for a task."""
        try:
            resolved_id = resolve_task_id_for_mcp(ctx.task_manager, task_id)
        except (TaskNotFoundError, ValueError) as e:
            return {"error": f"Invalid task_id: {e}"}

        files = af_manager.get_files(resolved_id)
        return {
            "task_id": resolved_id,
            "count": len(files),
            "files": [f.to_dict() for f in files],
        }

    registry.register(
        name="get_affected_files",
        description="Get affected files for a task.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task reference: #N, path, or UUID",
                },
            },
            "required": ["task_id"],
        },
        func=get_affected_files,
    )

    # --- find_file_overlaps ---

    def find_file_overlaps(task_ids: list[str]) -> dict[str, Any]:
        """Find file overlaps between tasks."""
        resolved_ids = []
        for tid in task_ids:
            try:
                resolved_ids.append(resolve_task_id_for_mcp(ctx.task_manager, tid))
            except (TaskNotFoundError, ValueError) as e:
                return {"error": f"Invalid task_id '{tid}': {e}"}

        overlaps = af_manager.find_overlapping_tasks(resolved_ids)
        # Convert tuple keys to string for JSON serialization
        result = []
        for (task_a, task_b), shared_files in overlaps.items():
            result.append({
                "task_a": task_a,
                "task_b": task_b,
                "shared_files": shared_files,
                "overlap_count": len(shared_files),
            })

        return {
            "task_count": len(resolved_ids),
            "overlapping_pairs": len(result),
            "overlaps": result,
        }

    registry.register(
        name="find_file_overlaps",
        description="Detect file contention between tasks. Returns pairs of tasks that share affected files.",
        input_schema={
            "type": "object",
            "properties": {
                "task_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of task references to check for overlaps",
                },
            },
            "required": ["task_ids"],
        },
        func=find_file_overlaps,
    )

    return registry
