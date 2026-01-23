"""Task orchestration tools: cleanup (cleanup_reviewed_worktrees, cleanup_stale_worktrees)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from gobby.mcp_proxy.tools.internal import InternalToolRegistry

from .utils import get_current_project_id

if TYPE_CHECKING:
    from gobby.storage.tasks import LocalTaskManager
    from gobby.storage.worktrees import LocalWorktreeManager
    from gobby.worktrees.git import WorktreeGitManager

logger = logging.getLogger(__name__)


def register_cleanup(
    registry: InternalToolRegistry,
    task_manager: LocalTaskManager,
    worktree_storage: LocalWorktreeManager,
    git_manager: WorktreeGitManager | None = None,
    default_project_id: str | None = None,
) -> None:
    """Register cleanup tools."""
    from gobby.mcp_proxy.tools.tasks import resolve_task_id_for_mcp
    from gobby.storage.tasks import TaskNotFoundError

    async def approve_and_cleanup(
        task_id: str,
        push_branch: bool = False,
        delete_worktree: bool = True,
        force: bool = False,
    ) -> dict[str, Any]:
        """
        Approve a reviewed task and clean up its worktree.

        This tool transitions a task from "review" to "closed" status
        and optionally deletes the associated worktree.

        Args:
            task_id: Task reference (#N, N, path, or UUID)
            push_branch: Whether to push the branch to remote before cleanup
            delete_worktree: Whether to delete the git worktree (default: True)
            force: Force deletion even if worktree is dirty

        Returns:
            Dict with:
            - success: Whether the operation succeeded
            - task_status: New task status
            - worktree_deleted: Whether worktree was deleted
            - branch_pushed: Whether branch was pushed
        """
        # Resolve task ID
        try:
            resolved_task_id = resolve_task_id_for_mcp(task_manager, task_id)
        except (TaskNotFoundError, ValueError) as e:
            return {
                "success": False,
                "error": f"Task not found: {task_id} ({e})",
            }

        # Get the task
        task = task_manager.get_task(resolved_task_id)
        if task is None:
            return {
                "success": False,
                "error": f"Task not found: {task_id}",
            }

        # Verify task is in review status
        if task.status != "review":
            return {
                "success": False,
                "error": f"Task must be in 'review' status to approve. Current status: {task.status}",
            }

        # Get associated worktree (if any)
        worktree = worktree_storage.get_by_task(resolved_task_id)
        branch_pushed = False
        worktree_deleted = False

        # Push branch to remote if requested
        if push_branch and worktree and git_manager:
            try:
                push_result = git_manager._run_git(
                    ["push", "origin", worktree.branch_name],
                    timeout=60,
                )
                branch_pushed = push_result.returncode == 0
                if not branch_pushed:
                    logger.warning(f"Failed to push branch: {push_result.stderr}")
            except Exception as e:
                logger.warning(f"Error pushing branch: {e}")

        # Update task status FIRST - before worktree deletion
        try:
            task_manager.update_task(
                resolved_task_id,
                status="closed",
            )
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to update task status: {e}",
                "task_id": resolved_task_id,
                "worktree_deleted": False,
            }

        # Delete worktree if requested and available (after task is closed)
        if delete_worktree and worktree:
            if git_manager is None:
                # No git manager - can't delete worktree, but continue
                logger.warning("Git manager not available, skipping worktree deletion")
            else:
                try:
                    delete_result = git_manager.delete_worktree(
                        worktree_path=worktree.worktree_path,
                        force=force,
                        delete_branch=False,  # Keep branch for history
                    )

                    if delete_result.success:
                        worktree_deleted = True
                        # Mark worktree as merged and delete record
                        worktree_storage.mark_merged(worktree.id)
                        worktree_storage.delete(worktree.id)
                    else:
                        # Task is closed but worktree deletion failed
                        logger.warning(f"Failed to delete worktree: {delete_result.message}")
                except Exception as e:
                    # Task is closed but worktree deletion failed
                    logger.warning(f"Error deleting worktree: {e}")

        return {
            "success": True,
            "task_id": resolved_task_id,
            "task_status": "closed",
            "worktree_deleted": worktree_deleted,
            "branch_pushed": branch_pushed,
            "message": f"Task {task_id} approved and marked as closed",
        }

    registry.register(
        name="approve_and_cleanup",
        description=(
            "Approve a reviewed task and clean up its worktree. "
            "Transitions task from 'review' to 'closed' status and deletes worktree."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task reference: #N, N (seq_num), path (1.2.3), or UUID",
                },
                "push_branch": {
                    "type": "boolean",
                    "description": "Whether to push branch to remote before cleanup",
                    "default": False,
                },
                "delete_worktree": {
                    "type": "boolean",
                    "description": "Whether to delete the git worktree",
                    "default": True,
                },
                "force": {
                    "type": "boolean",
                    "description": "Force deletion even if worktree is dirty",
                    "default": False,
                },
            },
            "required": ["task_id"],
        },
        func=approve_and_cleanup,
    )

    async def cleanup_reviewed_worktrees(
        parent_session_id: str,
        merge_to_base: bool = True,
        delete_worktrees: bool = True,
        delete_branches: bool = False,
        force: bool = False,
        project_path: str | None = None,
    ) -> dict[str, Any]:
        """
        Clean up worktrees for reviewed agents.

        After successful review, this tool:
        1. Merges worktree branch to its base branch (if merge_to_base=True)
        2. Marks worktree as merged in database
        3. Deletes the git worktree (if delete_worktrees=True)
        4. Optionally deletes the branch (if delete_branches=True)
        5. Updates workflow state by clearing reviewed_agents

        The base branch is whatever branch the worktree was created from
        (stored in worktree.base_branch), allowing the orchestrator to work
        on any branch (dev, main, feature branches, etc.).

        Used by the auto-orchestrator workflow's cleanup step.

        Args:
            parent_session_id: Parent session ID (orchestrator session)
            merge_to_base: Whether to merge branch to base before cleanup
            delete_worktrees: Whether to delete git worktrees
            delete_branches: Whether to delete branches after cleanup
            force: Force deletion even if worktree is dirty
            project_path: Path to project directory

        Returns:
            Dict with:
            - merged: List of successfully merged branches
            - deleted: List of deleted worktrees
            - failed: List of failed operations with reasons
            - summary: Counts
        """
        if git_manager is None:
            return {
                "success": False,
                "error": "Git manager not configured. Cannot cleanup worktrees.",
            }

        # Get workflow state
        from gobby.workflows.state_manager import WorkflowStateManager

        state_manager = WorkflowStateManager(task_manager.db)
        state = state_manager.get_state(parent_session_id)
        if not state:
            return {
                "success": True,
                "merged": [],
                "deleted": [],
                "failed": [],
                "summary": {"merged": 0, "deleted": 0, "failed": 0},
                "message": "No workflow state found",
            }

        workflow_vars = state.variables
        reviewed_agents = workflow_vars.get("reviewed_agents", [])

        if not reviewed_agents:
            return {
                "success": True,
                "merged": [],
                "deleted": [],
                "failed": [],
                "summary": {"merged": 0, "deleted": 0, "failed": 0},
                "message": "No reviewed agents to cleanup",
            }

        merged: list[dict[str, Any]] = []
        deleted: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        cleaned_agents: list[dict[str, Any]] = []

        for agent_info in reviewed_agents:
            worktree_id = agent_info.get("worktree_id")
            task_id = agent_info.get("task_id")
            branch_name = agent_info.get("branch_name")

            if not worktree_id:
                failed.append(
                    {
                        **agent_info,
                        "failure_reason": "Missing worktree_id",
                    }
                )
                continue

            # Get worktree from storage
            worktree = worktree_storage.get(worktree_id)
            if not worktree:
                # Worktree already deleted, consider it cleaned
                cleaned_agents.append(agent_info)
                continue

            branch = branch_name or worktree.branch_name
            worktree_path = worktree.worktree_path

            try:
                # Track if at least one successful operation occurred
                operation_succeeded = False

                # Step 1: Merge branch to base (if enabled)
                merge_succeeded = False
                if merge_to_base:
                    # Validate required fields for merge
                    if not branch:
                        failed.append(
                            {
                                **agent_info,
                                "failure_reason": "Missing branch name for merge operation",
                            }
                        )
                        continue
                    if not worktree.base_branch:
                        failed.append(
                            {
                                **agent_info,
                                "failure_reason": "Missing base_branch for merge operation",
                            }
                        )
                        continue

                    merge_result = _merge_branch_to_base(
                        git_manager=git_manager,
                        branch_name=branch,
                        base_branch=worktree.base_branch,
                    )

                    if merge_result["success"]:
                        merge_succeeded = True
                        operation_succeeded = True
                        merged.append(
                            {
                                "worktree_id": worktree_id,
                                "task_id": task_id,
                                "branch_name": branch,
                                "merge_commit": merge_result.get("merge_commit"),
                            }
                        )
                    else:
                        # Merge failed - cannot proceed with cleanup
                        failed.append(
                            {
                                **agent_info,
                                "failure_reason": f"Merge failed: {merge_result.get('error')}",
                                "merge_error": merge_result.get("error"),
                            }
                        )
                        continue

                # Step 2: Mark worktree as merged (only if merge actually occurred)
                if merge_succeeded:
                    worktree_storage.mark_merged(worktree_id)

                # Step 3: Delete git worktree (if enabled)
                if delete_worktrees:
                    # Validate required fields for deletion
                    if not worktree_path:
                        failed.append(
                            {
                                **agent_info,
                                "failure_reason": "Missing worktree_path for delete operation",
                            }
                        )
                        continue

                    delete_result = git_manager.delete_worktree(
                        worktree_path=worktree_path,
                        force=force,
                        delete_branch=delete_branches,
                    )

                    if delete_result.success:
                        operation_succeeded = True
                        deleted.append(
                            {
                                "worktree_id": worktree_id,
                                "task_id": task_id,
                                "worktree_path": worktree_path,
                                "branch_deleted": delete_branches,
                            }
                        )

                        # Also delete the database record
                        worktree_storage.delete(worktree_id)
                    else:
                        # Worktree deletion failed - report actual merge status
                        failed.append(
                            {
                                **agent_info,
                                "failure_reason": f"Worktree deletion failed: {delete_result.message}",
                                "worktree_status": "merged"
                                if merge_succeeded
                                else agent_info.get("worktree_status", "unmerged"),
                            }
                        )
                        continue

                # Only mark as cleaned if at least one operation succeeded
                if operation_succeeded:
                    cleaned_agents.append(agent_info)

            except Exception as e:
                logger.exception(f"Error cleaning up worktree {worktree_id}")
                failed.append(
                    {
                        **agent_info,
                        "failure_reason": str(e),
                    }
                )

        # Update workflow state
        try:
            state = state_manager.get_state(parent_session_id)
            if state:
                # Remove successfully cleaned agents from reviewed_agents
                # Compare by worktree_id to avoid dict identity issues
                cleaned_worktree_ids = {a.get("worktree_id") for a in cleaned_agents}
                remaining_reviewed = [
                    a for a in reviewed_agents if a.get("worktree_id") not in cleaned_worktree_ids
                ]
                state.variables["reviewed_agents"] = remaining_reviewed

                # Track cleanup history
                cleanup_history = state.variables.get("cleanup_history", [])
                cleanup_history.append(
                    {
                        "merged_count": len(merged),
                        "deleted_count": len(deleted),
                        "failed_count": len(failed),
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                )
                state.variables["cleanup_history"] = cleanup_history

                state_manager.save_state(state)
        except Exception as e:
            logger.warning(f"Failed to update workflow state after cleanup: {e}")

        return {
            "success": True,
            "merged": merged,
            "deleted": deleted,
            "failed": failed,
            "summary": {
                "merged": len(merged),
                "deleted": len(deleted),
                "failed": len(failed),
            },
            "remaining_reviewed": len(reviewed_agents) - len(cleaned_agents),
        }

    async def cleanup_stale_worktrees(
        project_path: str | None = None,
        older_than_hours: int = 24,
        force: bool = False,
    ) -> dict[str, Any]:
        """
        Clean up stale worktrees that have been inactive.

        Finds worktrees marked as stale or with no active agent session
        that are older than the specified threshold, and cleans them up.

        Args:
            project_path: Path to project directory
            older_than_hours: Only cleanup worktrees older than this (hours)
            force: Force deletion even if dirty

        Returns:
            Dict with cleanup results
        """
        if git_manager is None:
            return {
                "success": False,
                "error": "Git manager not configured",
            }

        # Validate older_than_hours
        try:
            older_than_hours = int(older_than_hours)
        except (TypeError, ValueError):
            return {
                "success": False,
                "error": "older_than_hours must be an integer",
            }
        if older_than_hours < 0:
            return {
                "success": False,
                "error": "older_than_hours must be non-negative",
            }

        # Resolve project ID
        resolved_project_id = default_project_id
        if project_path:
            from pathlib import Path

            from gobby.utils.project_context import get_project_context

            ctx = get_project_context(Path(project_path))
            if ctx:
                resolved_project_id = ctx.get("id")

        if not resolved_project_id:
            resolved_project_id = get_current_project_id()

        if not resolved_project_id:
            return {
                "success": False,
                "error": "Could not resolve project ID",
            }

        from gobby.storage.worktrees import WorktreeStatus as WTStatus

        # Get all worktrees to check for stale or abandoned candidates
        all_worktrees = worktree_storage.list_worktrees(
            project_id=resolved_project_id,
            limit=100,
        )

        cutoff = datetime.now(UTC) - timedelta(hours=older_than_hours)
        candidates = []

        for wt in all_worktrees:
            # Skip merged or abandoned
            if wt.status in [WTStatus.MERGED.value, WTStatus.ABANDONED.value]:
                continue

            # Add stale worktrees
            if wt.status == WTStatus.STALE.value:
                candidates.append(wt)
                continue

            # Add active worktrees with no active session that are old enough
            if wt.agent_session_id is None:
                try:
                    created = datetime.fromisoformat(wt.created_at.replace("Z", "+00:00"))
                    if created < cutoff:
                        candidates.append(wt)
                except (ValueError, AttributeError):
                    pass

        deleted: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []

        for wt in candidates:
            try:
                # Mark as stale first if not already
                if wt.status != WTStatus.STALE.value:
                    worktree_storage.mark_stale(wt.id)

                # Delete the git worktree
                delete_result = git_manager.delete_worktree(
                    worktree_path=wt.worktree_path,
                    force=force,
                    delete_branch=False,  # Keep branches for stale cleanup
                )

                if delete_result.success:
                    # Mark as abandoned and delete record
                    worktree_storage.mark_abandoned(wt.id)
                    worktree_storage.delete(wt.id)
                    deleted.append(
                        {
                            "worktree_id": wt.id,
                            "branch_name": wt.branch_name,
                            "worktree_path": wt.worktree_path,
                        }
                    )
                else:
                    failed.append(
                        {
                            "worktree_id": wt.id,
                            "branch_name": wt.branch_name,
                            "failure_reason": delete_result.message,
                        }
                    )

            except Exception as e:
                logger.exception(f"Error cleaning up stale worktree {wt.id}")
                failed.append(
                    {
                        "worktree_id": wt.id,
                        "branch_name": wt.branch_name,
                        "failure_reason": str(e),
                    }
                )

        return {
            "success": True,
            "deleted": deleted,
            "failed": failed,
            "summary": {
                "candidates": len(candidates),
                "deleted": len(deleted),
                "failed": len(failed),
            },
        }

    registry.register(
        name="cleanup_reviewed_worktrees",
        description=(
            "Clean up worktrees for reviewed agents. "
            "Merges branches to base branch (from worktree.base_branch), marks as merged, deletes worktrees. "
            "Used by auto-orchestrator cleanup step."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "parent_session_id": {
                    "type": "string",
                    "description": "Parent session ID (orchestrator session)",
                },
                "merge_to_base": {
                    "type": "boolean",
                    "description": "Whether to merge branch to base before cleanup",
                    "default": True,
                },
                "delete_worktrees": {
                    "type": "boolean",
                    "description": "Whether to delete git worktrees",
                    "default": True,
                },
                "delete_branches": {
                    "type": "boolean",
                    "description": "Whether to delete branches after cleanup",
                    "default": False,
                },
                "force": {
                    "type": "boolean",
                    "description": "Force deletion even if worktree is dirty",
                    "default": False,
                },
                "project_path": {
                    "type": "string",
                    "description": "Path to project directory (optional)",
                },
            },
            "required": ["parent_session_id"],
        },
        func=cleanup_reviewed_worktrees,
    )

    registry.register(
        name="cleanup_stale_worktrees",
        description=(
            "Clean up stale worktrees that have been inactive. "
            "Deletes worktrees with no active agent older than threshold."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "project_path": {
                    "type": "string",
                    "description": "Path to project directory (optional)",
                },
                "older_than_hours": {
                    "type": "integer",
                    "description": "Only cleanup worktrees older than this (hours)",
                    "default": 24,
                },
                "force": {
                    "type": "boolean",
                    "description": "Force deletion even if dirty",
                    "default": False,
                },
            },
            "required": [],
        },
        func=cleanup_stale_worktrees,
    )


def _merge_branch_to_base(
    git_manager: WorktreeGitManager,
    branch_name: str,
    base_branch: str = "main",
) -> dict[str, Any]:
    """
    Merge a branch back to its base branch.

    The base_branch is typically the branch the worktree was created from
    (e.g., dev, main, or a feature branch). This allows the orchestrator
    to run on any branch and merge completed work back.

    Args:
        git_manager: Git manager instance
        branch_name: Branch to merge (the worktree branch)
        base_branch: Target branch to merge into (from worktree.base_branch)

    Returns:
        Dict with success status, merge_commit, and error details
    """
    try:
        # Fetch latest from remote
        fetch_result = git_manager._run_git(
            ["fetch", "origin", base_branch],
            timeout=60,
        )
        if fetch_result.returncode != 0:
            return {
                "success": False,
                "error": f"Failed to fetch: {fetch_result.stderr}",
            }

        # Checkout the base branch
        checkout_result = git_manager._run_git(
            ["checkout", base_branch],
            timeout=30,
        )
        if checkout_result.returncode != 0:
            return {
                "success": False,
                "error": f"Failed to checkout {base_branch}: {checkout_result.stderr}",
            }

        # Pull latest
        pull_result = git_manager._run_git(
            ["pull", "origin", base_branch],
            timeout=60,
        )
        if pull_result.returncode != 0:
            return {
                "success": False,
                "error": f"Failed to pull: {pull_result.stderr}",
            }

        # Merge the branch
        merge_result = git_manager._run_git(
            ["merge", branch_name, "--no-ff", "-m", f"Merge branch '{branch_name}'"],
            timeout=120,
        )

        if merge_result.returncode != 0:
            # Check for conflicts
            has_conflicts = "CONFLICT" in merge_result.stdout or "CONFLICT" in merge_result.stderr

            # Always try to abort/reset the repo to ensure clean state
            abort_result = git_manager._run_git(["merge", "--abort"], timeout=10)
            if abort_result.returncode != 0:
                # Abort failed, force reset to clean state
                git_manager._run_git(["reset", "--hard", "HEAD"], timeout=10)
                git_manager._run_git(["clean", "-fd"], timeout=10)

            if has_conflicts:
                return {
                    "success": False,
                    "error": "Merge conflict detected",
                    "conflicts": True,
                }
            return {
                "success": False,
                "error": merge_result.stderr or merge_result.stdout,
            }

        # Get the merge commit SHA
        log_result = git_manager._run_git(
            ["rev-parse", "HEAD"],
            timeout=10,
        )
        merge_commit = log_result.stdout.strip() if log_result.returncode == 0 else None

        # Push the merge to remote
        push_result = git_manager._run_git(
            ["push", "origin", base_branch],
            timeout=60,
        )
        if push_result.returncode != 0:
            return {
                "success": False,
                "error": f"Merge succeeded but push failed: {push_result.stderr}",
                "merge_commit": merge_commit,
                "push_failed": True,
            }

        return {
            "success": True,
            "merge_commit": merge_commit,
            "message": f"Successfully merged {branch_name} to {base_branch}",
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }
