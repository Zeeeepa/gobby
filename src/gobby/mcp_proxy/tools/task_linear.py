"""
Linear integration tools for gobby-tasks registry.

Provides MCP tools for syncing between gobby tasks and Linear issues:
- import_linear_issues: Import Linear issues as gobby tasks
- sync_task_to_linear: Sync a task to its linked Linear issue
- create_issue_for_task: Create a Linear issue for a task
- link_linear_team: Set default Linear team for the project
- get_linear_status: Get Linear integration status

All tools delegate to LinearSyncService which uses the official Linear MCP server.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.sync.linear import (
    LinearNotFoundError,
    LinearRateLimitError,
    LinearSyncError,
    LinearSyncService,
)
from gobby.utils.project_context import get_project_context

if TYPE_CHECKING:
    from gobby.mcp_proxy.manager import MCPClientManager
    from gobby.storage.projects import LocalProjectManager
    from gobby.storage.tasks import LocalTaskManager

__all__ = ["create_linear_sync_registry"]

logger = logging.getLogger(__name__)


def create_linear_sync_registry(
    task_manager: LocalTaskManager,
    mcp_manager: MCPClientManager,
    project_manager: LocalProjectManager,
    project_id: str | None = None,
) -> InternalToolRegistry:
    """
    Create a Linear sync tool registry.

    Args:
        task_manager: LocalTaskManager instance for task CRUD.
        mcp_manager: MCPClientManager for Linear MCP server access.
        project_manager: LocalProjectManager for project config.
        project_id: Default project ID (optional, uses context if not provided).

    Returns:
        InternalToolRegistry with Linear sync tools registered.
    """
    registry = InternalToolRegistry(
        name="gobby-tasks",
        description="Linear integration tools",
    )

    def get_current_project_id() -> str | None:
        """Get the current project ID from context."""
        if project_id:
            return project_id
        ctx = get_project_context()
        if ctx and ctx.get("id"):
            pid_str: str = ctx["id"]
            return pid_str
        return None

    def get_sync_service(team_id: str | None = None) -> LinearSyncService:
        """Create LinearSyncService with current project context."""
        pid = get_current_project_id()
        if not pid:
            raise ValueError("No project context - run from a gobby project directory")

        return LinearSyncService(
            mcp_manager=mcp_manager,
            task_manager=task_manager,
            project_id=pid,
            linear_team_id=team_id,
        )

    # --- Linear Sync Tools ---

    @registry.tool(
        name="import_linear_issues",
        description=(
            "Import Linear issues as gobby tasks. "
            "Each issue becomes a task linked to the original Linear issue."
        ),
    )
    async def import_linear_issues(
        team_id: str | None = None,
        state: str | None = None,
        labels: str | None = None,
    ) -> dict[str, Any]:
        """Import Linear issues as gobby tasks.

        Args:
            team_id: Linear team ID to filter issues (uses project default if not set)
            state: Issue state filter (e.g., 'Todo', 'In Progress', 'Done')
            labels: Comma-separated labels to filter issues (optional)

        Returns:
            Dict with 'tasks' list of created task dicts and 'count' of imported issues.
        """
        try:
            service = get_sync_service(team_id)
            label_list = labels.split(",") if labels else None

            tasks = await service.import_linear_issues(
                team_id=team_id,
                state=state,
                labels=label_list,
            )

            return {
                "success": True,
                "tasks": tasks,
                "count": len(tasks),
                "team_id": team_id,
            }
        except LinearRateLimitError as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": "rate_limit",
                "reset_at": e.reset_at,
            }
        except LinearNotFoundError as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": "not_found",
                "resource": e.resource,
            }
        except LinearSyncError as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": "sync_error",
            }
        except RuntimeError as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": "unavailable",
            }

    @registry.tool(
        name="sync_task_to_linear",
        description=(
            "Sync a gobby task to its linked Linear issue. "
            "Updates the issue title and description to match the task."
        ),
    )
    async def sync_task_to_linear(task_id: str) -> dict[str, Any]:
        """Sync a task to its linked Linear issue.

        Args:
            task_id: ID of the task to sync

        Returns:
            Dict with sync result including updated issue info.
        """
        try:
            service = get_sync_service()
            result = await service.sync_task_to_linear(task_id)

            return {
                "success": True,
                "task_id": task_id,
                "linear_result": result,
            }
        except ValueError as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": "invalid_task",
            }
        except LinearRateLimitError as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": "rate_limit",
                "reset_at": e.reset_at,
            }
        except LinearNotFoundError as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": "not_found",
                "resource": e.resource,
            }
        except LinearSyncError as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": "sync_error",
            }
        except RuntimeError as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": "unavailable",
            }

    @registry.tool(
        name="create_linear_issue_for_task",
        description=(
            "Create a Linear issue from a gobby task. Links the issue to the task for tracking."
        ),
    )
    async def create_linear_issue_for_task(
        task_id: str,
        team_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a Linear issue for a task.

        Args:
            task_id: ID of the task to create issue for
            team_id: Linear team ID (uses task's team_id or project default if not set)

        Returns:
            Dict with issue info including ID.
        """
        try:
            service = get_sync_service(team_id)
            result = await service.create_issue_for_task(
                task_id=task_id,
                team_id=team_id,
            )

            return {
                "success": True,
                "task_id": task_id,
                "issue_id": result.get("id"),
                "linear_result": result,
            }
        except ValueError as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": "invalid_task",
            }
        except LinearRateLimitError as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": "rate_limit",
                "reset_at": e.reset_at,
            }
        except LinearNotFoundError as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": "not_found",
                "resource": e.resource,
            }
        except LinearSyncError as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": "sync_error",
            }
        except RuntimeError as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": "unavailable",
            }

    @registry.tool(
        name="link_linear_team",
        description=(
            "Link a Linear team to the current project. "
            "Sets the default team for Linear operations."
        ),
    )
    async def link_linear_team(team_id: str) -> dict[str, Any]:
        """Link a Linear team to the current project.

        Args:
            team_id: Linear team ID to link

        Returns:
            Dict with link result.
        """
        pid = get_current_project_id()
        if not pid:
            return {
                "success": False,
                "error": "No project context - run from a gobby project directory",
            }

        # Update project with linear_team_id
        project_manager.update(pid, linear_team_id=team_id)

        return {
            "success": True,
            "project_id": pid,
            "linear_team_id": team_id,
            "message": f"Linked project to Linear team: {team_id}",
        }

    @registry.tool(
        name="unlink_linear_team",
        description="Remove Linear team link from the current project.",
    )
    async def unlink_linear_team() -> dict[str, Any]:
        """Unlink Linear team from the current project.

        Returns:
            Dict with unlink result.
        """
        pid = get_current_project_id()
        if not pid:
            return {
                "success": False,
                "error": "No project context - run from a gobby project directory",
            }

        # Clear linear_team_id from project
        project_manager.update(pid, linear_team_id=None)

        return {
            "success": True,
            "project_id": pid,
            "message": "Unlinked Linear team from project",
        }

    @registry.tool(
        name="get_linear_status",
        description=(
            "Get Linear integration status for the current project. "
            "Shows linked team, MCP server availability, and task links."
        ),
    )
    async def get_linear_status() -> dict[str, Any]:
        """Get Linear integration status.

        Returns:
            Dict with Linear status including linked team and availability.
        """
        pid = get_current_project_id()
        if not pid:
            return {
                "success": False,
                "error": "No project context - run from a gobby project directory",
            }

        project = project_manager.get(pid)
        linear_team_id = getattr(project, "linear_team_id", None) if project else None

        # Check Linear MCP availability
        from gobby.integrations.linear import LinearIntegration

        linear = LinearIntegration(mcp_manager)
        available = linear.is_available()
        unavailable_reason = linear.get_unavailable_reason() if not available else None

        # Count linked tasks (direct query since list_tasks doesn't support filters)
        row = task_manager.db.fetchone(
            "SELECT COUNT(*) as count FROM tasks WHERE project_id = ? AND linear_issue_id IS NOT NULL",
            (pid,),
        )
        linked_count = row["count"] if row else 0

        return {
            "success": True,
            "project_id": pid,
            "linear_team_id": linear_team_id,
            "linear_available": available,
            "unavailable_reason": unavailable_reason,
            "linked_tasks_count": linked_count,
        }

    return registry
