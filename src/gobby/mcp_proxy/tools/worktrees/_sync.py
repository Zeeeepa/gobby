"""Worktree sync and merge tools."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Literal, cast

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.mcp_proxy.tools.worktrees._context import RegistryContext
from gobby.mcp_proxy.tools.worktrees._helpers import resolve_project_context

logger = logging.getLogger(__name__)


def create_sync_registry(ctx: RegistryContext) -> InternalToolRegistry:
    """Create a registry with worktree sync/merge tools.

    Args:
        ctx: Shared registry context

    Returns:
        InternalToolRegistry with sync and merge tools
    """
    registry = InternalToolRegistry(
        name="gobby-worktrees-sync",
        description="Worktree sync and merge operations",
    )

    @registry.tool(
        name="sync_worktree",
        description="Sync a worktree with the main branch.",
    )
    async def sync_worktree(
        worktree_id: str,
        strategy: str = "merge",
        project_path: str | None = None,
    ) -> dict[str, Any]:
        """Sync a worktree with the main branch.

        Args:
            worktree_id: The worktree ID to sync.
            strategy: Sync strategy ('merge' or 'rebase').
            project_path: Path to project directory (pass cwd from CLI).

        Returns:
            Dict with sync result.
        """
        resolved_git_mgr, _, error = resolve_project_context(
            project_path, ctx.git_manager, ctx.project_id
        )
        if error:
            return {"success": False, "error": error}

        if resolved_git_mgr is None:
            return {
                "success": False,
                "error": "Git manager not configured and no project_path provided.",
            }

        worktree = ctx.worktree_storage.get(worktree_id)
        if not worktree:
            return {"success": False, "error": f"Worktree '{worktree_id}' not found"}

        if strategy not in ("rebase", "merge"):
            return {
                "success": False,
                "error": f"Invalid strategy '{strategy}'. Must be 'rebase' or 'merge'.",
            }

        strategy_literal = cast(Literal["rebase", "merge"], strategy)

        result = await asyncio.to_thread(
            resolved_git_mgr.sync_from_main,
            worktree.worktree_path,
            base_branch=worktree.base_branch,
            strategy=strategy_literal,
        )

        if not result.success:
            return {"success": False, "error": result.error or "Sync failed"}

        ctx.worktree_storage.update(worktree_id)

        return {
            "success": True,
            "message": result.message,
            "output": result.output,
            "strategy": strategy,
        }

    @registry.tool(
        name="merge_worktree",
        description="Merge a worktree's branch into its base branch (or a specified target).",
    )
    async def merge_worktree(
        worktree_id: str,
        source_branch: str | None = None,
        target_branch: str | None = None,
        push: bool = False,
        project_path: str | None = None,
    ) -> dict[str, Any]:
        """Merge and optionally push from worktree -- fully isolated, never touches main repo.

        1. Fetch latest in the worktree
        2. Merge target INTO source branch (in worktree -- conflicts resolved here)
        3. (Optional) Push source to origin as target (git push origin source:target)

        The main repo is never touched. All operations use cwd=worktree_path.

        Args:
            worktree_id: The worktree ID to merge.
            source_branch: Agent's working branch (defaults to worktree's branch_name).
            target_branch: Branch to merge into (defaults to worktree's base_branch).
            push: If True, push source branch to origin as target after merge.
            project_path: Path to project directory (pass cwd from CLI).

        Returns:
            Dict with source_branch, target_branch on success.
        """
        resolved_git_mgr, _, error = resolve_project_context(
            project_path, ctx.git_manager, ctx.project_id
        )
        if error:
            return {"success": False, "error": error}
        if resolved_git_mgr is None:
            return {"success": False, "error": "Git manager not available"}

        worktree = ctx.worktree_storage.get(worktree_id)
        if not worktree:
            return {"success": False, "error": f"Worktree '{worktree_id}' not found"}

        effective_source = source_branch or worktree.branch_name
        merge_target = target_branch or worktree.base_branch
        wt_path = worktree.worktree_path

        # Step 1: Fetch latest in the worktree
        fetch_result = await asyncio.to_thread(
            resolved_git_mgr._run_git, ["fetch", "origin"], cwd=wt_path, timeout=60
        )
        if fetch_result.returncode != 0:
            logger.warning(f"Fetch failed in worktree (non-fatal): {fetch_result.stderr.strip()}")

        # Step 2: Merge target INTO source branch (in worktree)
        merge_ref = (
            f"origin/{merge_target}" if not merge_target.startswith("origin/") else merge_target
        )
        merge_result = await asyncio.to_thread(
            resolved_git_mgr._run_git,
            ["merge", merge_ref, "--no-edit"],
            cwd=wt_path,
            timeout=60,
        )

        if merge_result.returncode != 0:
            # Detect unmerged (conflicted) files via git index — more reliable
            # than parsing human-readable merge output for "CONFLICT" strings
            unmerged_result = await asyncio.to_thread(
                resolved_git_mgr._run_git,
                ["diff", "--name-only", "--diff-filter=U"],
                cwd=wt_path,
                timeout=10,
            )
            conflicted_files = [
                f.strip() for f in unmerged_result.stdout.strip().split("\n") if f.strip()
            ]
            if conflicted_files:
                await asyncio.to_thread(
                    resolved_git_mgr._run_git, ["merge", "--abort"], cwd=wt_path, timeout=10
                )
                return {
                    "success": False,
                    "has_conflicts": True,
                    "conflicted_files": conflicted_files,
                    "error": "merge_conflict",
                    "message": (
                        f"Merge conflicts detected in {len(conflicted_files)} file(s). "
                        "Use gobby-merge tools to resolve."
                    ),
                }
            merge_output = merge_result.stdout + merge_result.stderr
            return {
                "success": False,
                "has_conflicts": False,
                "error": merge_output.strip(),
            }

        # Mark as merged in storage
        ctx.worktree_storage.mark_merged(worktree_id)

        # Step 3 (optional): Push source branch to origin as target
        if push:
            push_result = await asyncio.to_thread(
                resolved_git_mgr._run_git,
                ["push", "--no-verify", "origin", f"{effective_source}:{merge_target}"],
                cwd=wt_path,
                timeout=60,
            )
            if push_result.returncode != 0:
                return {
                    "success": False,
                    "error": f"Push failed: {push_result.stderr.strip()}",
                    "merge_succeeded": True,
                    "source_branch": effective_source,
                    "target_branch": merge_target,
                }

        return {
            "success": True,
            "message": f"Merged and {'pushed' if push else 'ready to push'}",
            "source_branch": effective_source,
            "target_branch": merge_target,
            "pushed": push,
            **(
                {"push_command": f"git push --no-verify origin {effective_source}:{merge_target}"}
                if not push
                else {}
            ),
        }

    return registry
