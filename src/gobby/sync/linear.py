"""Linear sync service that orchestrates between gobby tasks and Linear.

This service delegates all Linear operations to the official Linear MCP server,
avoiding custom API client code.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

from gobby.integrations.linear import LinearIntegration

if TYPE_CHECKING:
    from gobby.mcp_proxy.manager import MCPClientManager
    from gobby.storage.tasks import LocalTaskManager

__all__ = [
    "LinearSyncService",
    "LinearSyncError",
    "LinearRateLimitError",
    "LinearNotFoundError",
]

logger = logging.getLogger(__name__)


class LinearSyncError(Exception):
    """Base exception for Linear sync errors."""

    pass


class LinearRateLimitError(LinearSyncError):
    """Raised when Linear API rate limit is exceeded.

    Attributes:
        reset_at: Unix timestamp when rate limit resets.
    """

    def __init__(self, message: str, reset_at: int | None = None) -> None:
        super().__init__(message)
        self.reset_at = reset_at


class LinearNotFoundError(LinearSyncError):
    """Raised when a Linear resource is not found.

    Attributes:
        resource: Type of resource (e.g., "issue", "team", "project").
        resource_id: Identifier of the missing resource.
    """

    def __init__(
        self,
        message: str,
        resource: str | None = None,
        resource_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.resource = resource
        self.resource_id = resource_id


class LinearSyncService:
    """Service for syncing gobby tasks with Linear issues.

    This service orchestrates bidirectional sync between gobby tasks and Linear:
    - Import Linear issues as gobby tasks
    - Sync task updates back to Linear issues
    - Create new issues from gobby tasks

    All Linear operations are delegated to the official Linear MCP server.

    Attributes:
        mcp_manager: MCPClientManager for accessing Linear MCP server.
        task_manager: LocalTaskManager for gobby task CRUD.
        project_id: Gobby project ID for creating tasks.
        linear_team_id: Default Linear team ID for creating issues.
        linear: LinearIntegration instance for availability checks.
    """

    def __init__(
        self,
        mcp_manager: MCPClientManager,
        task_manager: LocalTaskManager,
        project_id: str,
        linear_team_id: str | None = None,
    ) -> None:
        """Initialize LinearSyncService.

        Args:
            mcp_manager: MCPClientManager for Linear MCP server access.
            task_manager: LocalTaskManager for gobby task operations.
            project_id: Gobby project ID for creating tasks.
            linear_team_id: Default Linear team ID for creating issues.
        """
        self.mcp_manager = mcp_manager
        self.task_manager = task_manager
        self.project_id = project_id
        self.linear_team_id = linear_team_id
        self.linear = LinearIntegration(mcp_manager)

    def is_available(self) -> bool:
        """Check if Linear MCP server is available.

        Returns:
            True if Linear MCP server is available, False otherwise.
        """
        return self.linear.is_available()

    async def import_linear_issues(
        self,
        team_id: str | None = None,
        state: str | None = None,
        labels: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Import Linear issues as gobby tasks.

        Fetches issues from Linear via the MCP server and creates corresponding
        gobby tasks with linked linear_issue_id and linear_team_id fields.

        Args:
            team_id: Linear team ID to filter issues. Uses default if not provided.
            state: Issue state to filter (e.g., "In Progress", "Todo").
            labels: Optional list of labels to filter issues.

        Returns:
            List of created task dictionaries.

        Raises:
            RuntimeError: If Linear MCP server is unavailable.
            ValueError: If no team_id is provided and no default configured.
        """
        self.linear.require_available()

        effective_team_id = team_id or self.linear_team_id
        if not effective_team_id:
            raise ValueError("No team_id provided and no default linear_team_id configured.")

        # Build filter arguments for Linear MCP
        args: dict[str, Any] = {"teamId": effective_team_id}
        if state:
            args["state"] = state
        if labels:
            args["labels"] = labels

        result = await self.mcp_manager.call_tool(
            server_name="linear",
            tool_name="list_issues",
            arguments=args,
        )

        issues = result.get("issues", [])
        created_tasks = []

        for issue in issues:
            # Create gobby task linked to Linear issue
            task = self.task_manager.create_task(
                project_id=self.project_id,
                title=issue.get("title", "Untitled Issue"),
                description=issue.get("description", ""),
                linear_issue_id=issue.get("id"),
                linear_team_id=effective_team_id,
            )
            created_tasks.append(task.to_dict())

        logger.info(f"Imported {len(created_tasks)} issues from Linear team {effective_team_id}")
        return created_tasks

    async def sync_task_to_linear(self, task_id: str) -> dict[str, Any]:
        """Sync a gobby task to its linked Linear issue.

        Updates the Linear issue title and description to match the task.

        Args:
            task_id: ID of the task to sync.

        Returns:
            Result from Linear MCP update_issue call.

        Raises:
            RuntimeError: If Linear MCP server is unavailable.
            ValueError: If task has no linked Linear issue.
        """
        self.linear.require_available()

        task = self.task_manager.get_task(task_id)

        if not task.linear_issue_id:
            raise ValueError(
                f"Task {task_id} has no linked Linear issue. Set linear_issue_id to sync."
            )

        result = await self.mcp_manager.call_tool(
            server_name="linear",
            tool_name="update_issue",
            arguments={
                "issueId": task.linear_issue_id,
                "title": task.title,
                "description": task.description or "",
            },
        )

        # Validate response
        if result is None or not isinstance(result, dict):
            raise LinearSyncError(
                f"Invalid response from Linear MCP when updating issue "
                f"{task.linear_issue_id}: expected dict, got {type(result).__name__}"
            )

        logger.info(f"Synced task {task_id} to Linear issue {task.linear_issue_id}")
        return cast(dict[str, Any], result)

    async def create_issue_for_task(
        self,
        task_id: str,
        team_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a Linear issue from a gobby task.

        Creates an issue on Linear and links it to the task.

        Args:
            task_id: ID of the task to create issue for.
            team_id: Linear team ID for the issue. Uses default if not provided.

        Returns:
            Result from Linear MCP create_issue call.

        Raises:
            RuntimeError: If Linear MCP server is unavailable.
            ValueError: If no team_id is provided and no default configured.
        """
        self.linear.require_available()

        task = self.task_manager.get_task(task_id)

        effective_team_id = team_id or task.linear_team_id or self.linear_team_id
        if not effective_team_id:
            raise ValueError(f"Task {task_id} has no linear_team_id set and no default configured.")

        # Create issue via Linear MCP
        result = await self.mcp_manager.call_tool(
            server_name="linear",
            tool_name="create_issue",
            arguments={
                "teamId": effective_team_id,
                "title": task.title,
                "description": task.description or "",
            },
        )

        # Update task with Linear issue ID if available
        result_dict = cast(dict[str, Any], result)
        issue_id = result_dict.get("id")
        if issue_id:
            self.task_manager.update_task(
                task_id,
                linear_issue_id=issue_id,
                linear_team_id=effective_team_id,
            )
            logger.info(f"Created Linear issue {issue_id} for task {task_id}")

        return result_dict

    def map_gobby_status_to_linear(self, gobby_status: str) -> str:
        """Map gobby task status to Linear issue state.

        Args:
            gobby_status: Gobby task status.

        Returns:
            Linear issue state name.
        """
        status_map = {
            "open": "Todo",
            "in_progress": "In Progress",
            "closed": "Done",
            "failed": "Canceled",
            "escalated": "In Review",
            "needs_decomposition": "Backlog",
        }
        return status_map.get(gobby_status, "Todo")

    def map_linear_status_to_gobby(self, linear_state: str) -> str:
        """Map Linear issue state to gobby task status.

        Args:
            linear_state: Linear issue state name.

        Returns:
            Gobby task status.
        """
        state_map = {
            "Todo": "open",
            "In Progress": "in_progress",
            "Done": "closed",
            "Canceled": "closed",
            "In Review": "in_progress",
            "Backlog": "open",
            "Triage": "open",
        }
        return state_map.get(linear_state, "open")
