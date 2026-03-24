"""Worktree cleanup and stale detection tools."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.mcp_proxy.tools.worktrees._context import RegistryContext
from gobby.mcp_proxy.tools.worktrees._helpers import resolve_project_context

logger = logging.getLogger(__name__)


def create_cleanup_registry(ctx: RegistryContext) -> InternalToolRegistry:
    """Create a registry with worktree cleanup tools.

    Args:
        ctx: Shared registry context

    Returns:
        InternalToolRegistry with stale detection and cleanup tools
    """
    registry = InternalToolRegistry(
        name="gobby-worktrees-cleanup",
        description="Worktree stale detection and cleanup",
    )

    @registry.tool(
        name="detect_stale_worktrees",
        description="Find worktrees with no activity for a period.",
    )
    async def detect_stale_worktrees(
        project_path: str | None = None,
        hours: int | str = 24,
        limit: int | str = 50,
    ) -> dict[str, Any]:
        """Find stale worktrees (no activity for N hours).

        Args:
            project_path: Path to project directory (pass cwd from CLI).
            hours: Hours of inactivity threshold (default: 24).
            limit: Maximum results (default: 50).

        Returns:
            Dict with list of stale worktrees.
        """
        hours = int(hours) if isinstance(hours, str) else hours
        limit = int(limit) if isinstance(limit, str) else limit

        _, resolved_project_id, error = resolve_project_context(
            project_path, ctx.git_manager, ctx.project_id
        )
        if error:
            return {"success": False, "error": error}
        if resolved_project_id is None:
            return {"success": False, "error": "Could not resolve project ID"}

        stale = ctx.worktree_storage.find_stale(
            project_id=resolved_project_id,
            hours=hours,
            limit=limit,
        )

        return {
            "success": True,
            "stale_worktrees": [
                {
                    "id": wt.id,
                    "branch_name": wt.branch_name,
                    "worktree_path": wt.worktree_path,
                    "updated_at": wt.updated_at,
                    "task_id": wt.task_id,
                }
                for wt in stale
            ],
            "count": len(stale),
            "threshold_hours": hours,
        }

    @registry.tool(
        name="cleanup_stale_worktrees",
        description="Mark and optionally delete stale worktrees.",
    )
    async def cleanup_stale_worktrees(
        project_path: str | None = None,
        hours: int | str = 24,
        dry_run: bool | str = True,
        delete_git: bool | str = False,
    ) -> dict[str, Any]:
        """Cleanup stale worktrees.

        Args:
            project_path: Path to project directory (pass cwd from CLI).
            hours: Hours of inactivity threshold (default: 24).
            dry_run: If True, only report what would be cleaned (default: True).
            delete_git: If True, also delete git worktrees (default: False).

        Returns:
            Dict with cleanup results.
        """
        hours = int(hours) if isinstance(hours, str) else hours
        dry_run = dry_run in (True, "true", "True", "1") if isinstance(dry_run, str) else dry_run
        delete_git = (
            delete_git in (True, "true", "True", "1") if isinstance(delete_git, str) else delete_git
        )

        resolved_git_manager, resolved_project_id, error = resolve_project_context(
            project_path, ctx.git_manager, ctx.project_id
        )
        if error:
            return {"success": False, "error": error}
        if resolved_project_id is None:
            return {"success": False, "error": "Could not resolve project ID"}

        stale = ctx.worktree_storage.cleanup_stale(
            project_id=resolved_project_id,
            hours=hours,
            dry_run=dry_run,
        )

        results = []
        for wt in stale:
            result: dict[str, Any] = {
                "id": wt.id,
                "branch_name": wt.branch_name,
                "worktree_path": wt.worktree_path,
                "marked_abandoned": not dry_run,
                "git_deleted": False,
            }

            if delete_git and not dry_run and resolved_git_manager:
                git_result = await asyncio.to_thread(
                    resolved_git_manager.delete_worktree,
                    wt.worktree_path,
                    force=True,
                    delete_branch=True,
                    branch_name=wt.branch_name,
                )
                result["git_deleted"] = git_result.success
                if not git_result.success:
                    result["git_error"] = git_result.error or "Unknown error"

            results.append(result)

        return {
            "success": True,
            "dry_run": dry_run,
            "cleaned": results,
            "count": len(results),
            "threshold_hours": hours,
        }

    return registry
