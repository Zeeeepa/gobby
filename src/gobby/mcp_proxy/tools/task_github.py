"""
GitHub integration tools for gobby-tasks registry.

Provides MCP tools for syncing between gobby tasks and GitHub issues/PRs:
- import_github_issues: Import GitHub issues as gobby tasks
- sync_task_to_github: Sync a task to its linked GitHub issue
- create_pr_for_task: Create a PR for a completed task
- link_github_repo: Link a GitHub repo to the project
- get_github_pr_status: Get PR status for a task

All tools delegate to GitHubSyncService which uses the official GitHub MCP server.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.sync.github import (
    GitHubNotFoundError,
    GitHubRateLimitError,
    GitHubSyncError,
    GitHubSyncService,
)
from gobby.utils.project_context import get_project_context

if TYPE_CHECKING:
    from gobby.mcp_proxy.manager import MCPClientManager
    from gobby.storage.projects import LocalProjectManager
    from gobby.storage.tasks import LocalTaskManager

__all__ = ["create_github_sync_registry"]

logger = logging.getLogger(__name__)


def create_github_sync_registry(
    task_manager: LocalTaskManager,
    mcp_manager: MCPClientManager,
    project_manager: LocalProjectManager,
    project_id: str | None = None,
) -> InternalToolRegistry:
    """
    Create a GitHub sync tool registry.

    Args:
        task_manager: LocalTaskManager instance for task CRUD.
        mcp_manager: MCPClientManager for GitHub MCP server access.
        project_manager: LocalProjectManager for project config.
        project_id: Default project ID (optional, uses context if not provided).

    Returns:
        InternalToolRegistry with GitHub sync tools registered.
    """
    registry = InternalToolRegistry(
        name="gobby-tasks",
        description="GitHub integration tools",
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

    def get_sync_service(repo: str | None = None) -> GitHubSyncService:
        """Create GitHubSyncService with current project context."""
        pid = get_current_project_id()
        if not pid:
            raise ValueError("No project context - run from a gobby project directory")

        return GitHubSyncService(
            mcp_manager=mcp_manager,
            task_manager=task_manager,
            project_id=pid,
            github_repo=repo,
        )

    # --- GitHub Sync Tools ---

    @registry.tool(
        name="import_github_issues",
        description=(
            "Import GitHub issues as gobby tasks. "
            "Each issue becomes a task linked to the original GitHub issue."
        ),
    )
    async def import_github_issues(
        repo: str,
        labels: str | None = None,
        state: str = "open",
    ) -> dict[str, Any]:
        """Import GitHub issues as gobby tasks.

        Args:
            repo: GitHub repo in 'owner/repo' format
            labels: Comma-separated labels to filter issues (optional)
            state: Issue state filter: 'open', 'closed', or 'all' (default: 'open')

        Returns:
            Dict with 'tasks' list of created task dicts and 'count' of imported issues.
        """
        try:
            service = get_sync_service(repo)
            label_list = labels.split(",") if labels else None

            tasks = await service.import_github_issues(
                repo=repo,
                labels=label_list,
                state=state,
            )

            return {
                "success": True,
                "tasks": tasks,
                "count": len(tasks),
                "repo": repo,
            }
        except GitHubRateLimitError as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": "rate_limit",
                "reset_at": e.reset_at,
            }
        except GitHubNotFoundError as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": "not_found",
                "resource": e.resource,
            }
        except GitHubSyncError as e:
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
        name="sync_task_to_github",
        description=(
            "Sync a gobby task to its linked GitHub issue. "
            "Updates the issue title and body to match the task."
        ),
    )
    async def sync_task_to_github(task_id: str) -> dict[str, Any]:
        """Sync a task to its linked GitHub issue.

        Args:
            task_id: ID of the task to sync

        Returns:
            Dict with sync result including updated issue info.
        """
        try:
            service = get_sync_service()
            result = await service.sync_task_to_github(task_id)

            return {
                "success": True,
                "task_id": task_id,
                "github_result": result,
            }
        except ValueError as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": "invalid_task",
            }
        except GitHubRateLimitError as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": "rate_limit",
                "reset_at": e.reset_at,
            }
        except GitHubNotFoundError as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": "not_found",
                "resource": e.resource,
            }
        except GitHubSyncError as e:
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
        name="create_pr_for_task",
        description=(
            "Create a GitHub pull request for a task. Links the PR to the task for tracking."
        ),
    )
    async def create_pr_for_task(
        task_id: str,
        head_branch: str,
        base_branch: str = "main",
        draft: bool = False,
    ) -> dict[str, Any]:
        """Create a GitHub PR for a task.

        Args:
            task_id: ID of the task to create PR for
            head_branch: Branch containing the changes
            base_branch: Branch to merge into (default: 'main')
            draft: Create as draft PR (default: False)

        Returns:
            Dict with PR info including number and URL.
        """
        try:
            service = get_sync_service()
            result = await service.create_pr_for_task(
                task_id=task_id,
                head_branch=head_branch,
                base_branch=base_branch,
                draft=draft,
            )

            return {
                "success": True,
                "task_id": task_id,
                "pr_number": result.get("number"),
                "pr_url": result.get("html_url") or result.get("url"),
                "github_result": result,
            }
        except ValueError as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": "invalid_task",
            }
        except GitHubRateLimitError as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": "rate_limit",
                "reset_at": e.reset_at,
            }
        except GitHubNotFoundError as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": "not_found",
                "resource": e.resource,
            }
        except GitHubSyncError as e:
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
        name="link_github_repo",
        description=(
            "Link a GitHub repo to the current project. "
            "Sets the default repo for GitHub operations."
        ),
    )
    async def link_github_repo(repo: str) -> dict[str, Any]:
        """Link a GitHub repo to the current project.

        Args:
            repo: GitHub repo in 'owner/repo' format

        Returns:
            Dict with link result.
        """
        pid = get_current_project_id()
        if not pid:
            return {
                "success": False,
                "error": "No project context - run from a gobby project directory",
            }

        # Validate repo format
        if "/" not in repo or repo.count("/") != 1:
            return {
                "success": False,
                "error": f"Invalid repo format: '{repo}'. Expected 'owner/repo'",
            }

        # Update project with github_repo
        project_manager.update(pid, github_repo=repo)

        return {
            "success": True,
            "project_id": pid,
            "github_repo": repo,
            "message": f"Linked project to GitHub repo: {repo}",
        }

    @registry.tool(
        name="unlink_github_repo",
        description="Remove GitHub repo link from the current project.",
    )
    async def unlink_github_repo() -> dict[str, Any]:
        """Unlink GitHub repo from the current project.

        Returns:
            Dict with unlink result.
        """
        pid = get_current_project_id()
        if not pid:
            return {
                "success": False,
                "error": "No project context - run from a gobby project directory",
            }

        # Clear github_repo from project
        project_manager.update(pid, github_repo=None)

        return {
            "success": True,
            "project_id": pid,
            "message": "Unlinked GitHub repo from project",
        }

    @registry.tool(
        name="get_github_status",
        description=(
            "Get GitHub integration status for the current project. "
            "Shows linked repo, MCP server availability, and task links."
        ),
    )
    async def get_github_status() -> dict[str, Any]:
        """Get GitHub integration status.

        Returns:
            Dict with GitHub status including linked repo and availability.
        """
        pid = get_current_project_id()
        if not pid:
            return {
                "success": False,
                "error": "No project context - run from a gobby project directory",
            }

        project = project_manager.get(pid)
        github_repo = getattr(project, "github_repo", None) if project else None

        # Check GitHub MCP availability
        from gobby.integrations.github import GitHubIntegration

        github = GitHubIntegration(mcp_manager)
        available = github.is_available()
        unavailable_reason = github.get_unavailable_reason() if not available else None

        # Count linked tasks (direct query since list_tasks doesn't support filters)
        row = task_manager.db.fetchone(
            "SELECT COUNT(*) as count FROM tasks WHERE project_id = ? AND github_issue_number IS NOT NULL",
            (pid,),
        )
        linked_count = row["count"] if row else 0

        return {
            "success": True,
            "project_id": pid,
            "github_repo": github_repo,
            "github_available": available,
            "unavailable_reason": unavailable_reason,
            "linked_tasks_count": linked_count,
        }

    return registry
