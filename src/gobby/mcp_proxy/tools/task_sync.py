"""
Task sync and commit linking MCP tools module.

Provides tools for task synchronization and commit linking:
- sync_tasks: Manually trigger task import/export
- get_sync_status: Get current sync status
- link_commit: Link a git commit to a task
- unlink_commit: Unlink a git commit from a task
- auto_link_commits: Auto-detect and link commits mentioning task IDs
- get_task_diff: Get combined diff for all commits linked to a task

Extracted from tasks.py using Strangler Fig pattern for code decomposition.
"""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.utils.project_context import get_project_context

if TYPE_CHECKING:
    from gobby.storage.projects import LocalProjectManager
    from gobby.storage.tasks import LocalTaskManager
    from gobby.sync.tasks import TaskSyncManager

__all__ = ["create_sync_registry"]


def get_current_project_id() -> str | None:
    """Get the current project ID from context."""
    context = get_project_context()
    return context.get("id") if context else None


class SyncToolRegistry(InternalToolRegistry):
    """Registry for sync tools with test-friendly get_tool method."""

    def get_tool(self, name: str) -> Callable[..., Any] | None:
        """Get a tool function by name (for testing)."""
        tool = self._tools.get(name)
        return tool.func if tool else None


def create_sync_registry(
    sync_manager: "TaskSyncManager | None" = None,
    task_manager: "LocalTaskManager | None" = None,
    project_manager: "LocalProjectManager | None" = None,
    auto_link_commits_fn: Callable[..., Any] | None = None,
    get_task_diff_fn: Callable[..., Any] | None = None,
) -> SyncToolRegistry:
    """
    Create a registry with task sync and commit linking tools.

    Args:
        sync_manager: TaskSyncManager instance
        task_manager: LocalTaskManager instance
        project_manager: LocalProjectManager instance (for repo_path lookup)
        auto_link_commits_fn: Function for auto-linking commits (injectable for testing)
        get_task_diff_fn: Function for getting task diff (injectable for testing)

    Returns:
        SyncToolRegistry with sync tools registered
    """
    registry = SyncToolRegistry(
        name="gobby-tasks-sync",
        description="Task synchronization and commit linking tools",
    )

    if sync_manager is None:
        raise ValueError("sync_manager is required")

    # --- sync_tasks ---

    def sync_tasks(direction: str = "both") -> dict[str, Any]:
        """Manually trigger task synchronization."""
        result = {}
        if direction in ["import", "both"]:
            sync_manager.import_from_jsonl()
            result["import"] = "completed"

        if direction in ["export", "both"]:
            sync_manager.export_to_jsonl()
            result["export"] = "completed"

        return result

    registry.register(
        name="sync_tasks",
        description="Manually trigger task synchronization.",
        input_schema={
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "description": '"import", "export", or "both"',
                    "default": "both",
                },
            },
        },
        func=sync_tasks,
    )

    # --- get_sync_status ---

    def get_sync_status() -> dict[str, Any]:
        """Get current synchronization status."""
        result: dict[str, Any] = sync_manager.get_sync_status()
        return result

    registry.register(
        name="get_sync_status",
        description="Get current synchronization status.",
        input_schema={"type": "object", "properties": {}},
        func=get_sync_status,
    )

    # --- link_commit ---

    def link_commit(task_id: str, commit_sha: str) -> dict[str, Any]:
        """Link a git commit to a task."""
        if task_manager is None:
            return {"error": "task_manager not configured"}
        try:
            task = task_manager.link_commit(task_id, commit_sha)
            return {
                "task_id": task.id,
                "commits": task.commits or [],
            }
        except ValueError as e:
            return {"error": str(e)}

    registry.register(
        name="link_commit",
        description="Link a git commit to a task. Useful for tracking which commits implement a task.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID"},
                "commit_sha": {
                    "type": "string",
                    "description": "Git commit SHA (short or full)",
                },
            },
            "required": ["task_id", "commit_sha"],
        },
        func=link_commit,
    )

    # --- unlink_commit ---

    def unlink_commit(task_id: str, commit_sha: str) -> dict[str, Any]:
        """Unlink a git commit from a task."""
        if task_manager is None:
            return {"error": "task_manager not configured"}
        try:
            task = task_manager.unlink_commit(task_id, commit_sha)
            return {
                "task_id": task.id,
                "commits": task.commits or [],
            }
        except ValueError as e:
            return {"error": str(e)}

    registry.register(
        name="unlink_commit",
        description="Unlink a git commit from a task.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID"},
                "commit_sha": {
                    "type": "string",
                    "description": "Git commit SHA to unlink",
                },
            },
            "required": ["task_id", "commit_sha"],
        },
        func=unlink_commit,
    )

    # --- auto_link_commits ---

    def auto_link_commits(
        task_id: str | None = None,
        since: str | None = None,
    ) -> dict[str, Any]:
        """Auto-detect and link commits that mention task IDs."""
        if auto_link_commits_fn is None:
            return {"error": "auto_link_commits_fn not configured"}
        if task_manager is None:
            return {"error": "task_manager not configured"}

        # Get project repo_path
        ctx = get_project_context()
        repo_path = None
        if ctx and ctx.get("id") and project_manager:
            project = project_manager.get(ctx["id"])
            if project:
                repo_path = project.repo_path

        result = auto_link_commits_fn(
            task_manager=task_manager,
            task_id=task_id,
            since=since,
            cwd=repo_path,
        )

        return {
            "linked_tasks": result.linked_tasks,
            "total_linked": result.total_linked,
            "skipped": result.skipped,
        }

    registry.register(
        name="auto_link_commits",
        description="Auto-detect and link commits that mention task IDs in their messages. "
        "Supports patterns: [gt-xxxxx], gt-xxxxx:, Implements/Fixes/Closes gt-xxxxx.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Filter to specific task ID (optional)",
                    "default": None,
                },
                "since": {
                    "type": "string",
                    "description": "Git --since parameter (e.g., '1 week ago', '2024-01-01')",
                    "default": None,
                },
            },
        },
        func=auto_link_commits,
    )

    # --- get_task_diff ---

    def get_task_diff_tool(
        task_id: str,
        include_uncommitted: bool = False,
    ) -> dict[str, Any]:
        """Get the combined diff for all commits linked to a task."""
        if task_manager is None:
            return {"error": "task_manager not configured"}

        task = task_manager.get_task(task_id)
        if not task:
            return {"error": f"Task {task_id} not found"}

        if get_task_diff_fn is None:
            return {"error": "get_task_diff_fn not configured"}

        # Get project repo_path
        repo_path = None
        if project_manager and task.project_id:
            project = project_manager.get(task.project_id)
            if project:
                repo_path = project.repo_path

        result = get_task_diff_fn(
            task_id=task_id,
            task_manager=task_manager,
            include_uncommitted=include_uncommitted,
            cwd=repo_path,
        )

        return {
            "diff": result.diff,
            "commits": result.commits,
            "has_uncommitted_changes": result.has_uncommitted_changes,
            "file_count": result.file_count,
        }

    registry.register(
        name="get_task_diff",
        description="Get the combined diff for all commits linked to a task. "
        "Optionally include uncommitted changes.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID"},
                "include_uncommitted": {
                    "type": "boolean",
                    "description": "Include uncommitted changes in the diff",
                    "default": False,
                },
            },
            "required": ["task_id"],
        },
        func=get_task_diff_tool,
    )

    return registry
