"""
Internal MCP tools for Gobby Worktree Management.

Exposes functionality for:
- Creating git worktrees for isolated development
- Managing worktree lifecycle (claim, release, cleanup)
- Syncing worktrees with main branch
- Spawning agents in worktrees

These tools are registered with the InternalToolRegistry and accessed
via the downstream proxy pattern (call_tool, list_tools, get_tool_schema).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.storage.worktrees import WorktreeStatus
from gobby.utils.project_context import get_project_context
from gobby.worktrees.git import WorktreeGitManager

if TYPE_CHECKING:
    from gobby.agents.runner import AgentRunner
    from gobby.storage.worktrees import LocalWorktreeManager
    from gobby.worktrees.git import WorktreeGitManager

logger = logging.getLogger(__name__)

# Cache for WorktreeGitManager instances per repo path
_git_manager_cache: dict[str, WorktreeGitManager] = {}


def _resolve_project_context(
    project_path: str | None,
    default_git_manager: WorktreeGitManager | None,
    default_project_id: str | None,
) -> tuple[WorktreeGitManager | None, str | None, str | None]:
    """
    Resolve project context from project_path or fall back to defaults.

    Args:
        project_path: Path to project directory (cwd from caller).
        default_git_manager: Registry-level git manager (may be None).
        default_project_id: Registry-level project ID (may be None).

    Returns:
        Tuple of (git_manager, project_id, error_message).
        If error_message is not None, the other values should not be used.
    """
    if project_path:
        # Resolve from provided path
        path = Path(project_path)
        if not path.exists():
            return None, None, f"Project path does not exist: {project_path}"

        project_ctx = get_project_context(path)
        if not project_ctx:
            return None, None, f"No .gobby/project.json found in {project_path}"

        resolved_project_id = project_ctx.get("id")
        resolved_path = project_ctx.get("project_path", str(path))

        # Get or create git manager for this path
        if resolved_path not in _git_manager_cache:
            try:
                _git_manager_cache[resolved_path] = WorktreeGitManager(resolved_path)
            except ValueError as e:
                return None, None, f"Invalid git repository: {e}"

        return _git_manager_cache[resolved_path], resolved_project_id, None

    # Fall back to defaults
    if default_git_manager is None:
        return None, None, "No project_path provided and no default git manager configured."
    if default_project_id is None:
        return None, None, "No project_path provided and no default project ID configured."

    return default_git_manager, default_project_id, None


def create_worktrees_registry(
    worktree_storage: LocalWorktreeManager,
    git_manager: WorktreeGitManager | None = None,
    project_id: str | None = None,
    agent_runner: AgentRunner | None = None,
) -> InternalToolRegistry:
    """
    Create a worktree tool registry with all worktree-related tools.

    Args:
        worktree_storage: LocalWorktreeManager for database operations.
        git_manager: WorktreeGitManager for git operations.
        project_id: Default project ID for operations.
        agent_runner: AgentRunner for spawning agents in worktrees.

    Returns:
        InternalToolRegistry with all worktree tools registered.
    """
    registry = InternalToolRegistry(
        name="gobby-worktrees",
        description="Git worktree management - create, manage, and cleanup isolated development directories",
    )

    @registry.tool(
        name="create_worktree",
        description="Create a new git worktree for isolated development.",
    )
    async def create_worktree(
        branch_name: str,
        base_branch: str = "main",
        task_id: str | None = None,
        worktree_path: str | None = None,
        create_branch: bool = True,
        project_path: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a new git worktree.

        Args:
            branch_name: Name for the new branch.
            base_branch: Branch to base the worktree on (default: main).
            task_id: Optional task ID to link to this worktree.
            worktree_path: Optional custom path (defaults to ../{branch_name}).
            create_branch: Whether to create a new branch (default: True).
            project_path: Path to project directory (pass cwd from CLI).

        Returns:
            Dict with worktree ID, path, and branch info.
        """
        # Resolve project context
        resolved_git_mgr, resolved_project_id, error = _resolve_project_context(
            project_path, git_manager, project_id
        )
        if error:
            return {"success": False, "error": error}

        # Check if branch already exists as a worktree
        existing = worktree_storage.get_by_branch(resolved_project_id, branch_name)
        if existing:
            return {
                "success": False,
                "error": f"Worktree already exists for branch '{branch_name}'",
                "existing_worktree_id": existing.id,
                "existing_path": existing.worktree_path,
            }

        # Generate default worktree path if not provided
        if worktree_path is None:
            # Default to sibling directory named after branch
            worktree_path = str(Path(resolved_git_mgr.repo_path).parent / branch_name)

        # Create git worktree
        result = resolved_git_mgr.create_worktree(
            worktree_path=worktree_path,
            branch_name=branch_name,
            base_branch=base_branch,
            create_branch=create_branch,
        )

        if not result.success:
            return {
                "success": False,
                "error": result.error or "Failed to create git worktree",
            }

        # Record in database
        worktree = worktree_storage.create(
            project_id=resolved_project_id,
            branch_name=branch_name,
            worktree_path=worktree_path,
            base_branch=base_branch,
            task_id=task_id,
        )

        return {
            "success": True,
            "worktree_id": worktree.id,
            "branch_name": worktree.branch_name,
            "worktree_path": worktree.worktree_path,
            "base_branch": worktree.base_branch,
            "task_id": worktree.task_id,
            "status": worktree.status,
        }

    @registry.tool(
        name="get_worktree",
        description="Get details of a specific worktree.",
    )
    async def get_worktree(worktree_id: str) -> dict[str, Any]:
        """
        Get worktree details by ID.

        Args:
            worktree_id: The worktree ID.

        Returns:
            Dict with full worktree details.
        """
        worktree = worktree_storage.get(worktree_id)
        if not worktree:
            return {
                "success": False,
                "error": f"Worktree '{worktree_id}' not found",
            }

        # Get git status if manager available
        git_status = None
        if git_manager and Path(worktree.worktree_path).exists():
            status = git_manager.get_worktree_status(worktree.worktree_path)
            if status:
                git_status = {
                    "has_uncommitted_changes": status.has_uncommitted_changes,
                    "commits_ahead": status.ahead,
                    "commits_behind": status.behind,
                    "current_branch": status.branch,
                }

        return {
            "success": True,
            "worktree": worktree.to_dict(),
            "git_status": git_status,
        }

    @registry.tool(
        name="list_worktrees",
        description="List worktrees with optional filters.",
    )
    async def list_worktrees(
        status: str | None = None,
        agent_session_id: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """
        List worktrees with optional filters.

        Args:
            status: Filter by status (active, stale, merged, abandoned).
            agent_session_id: Filter by owning session.
            limit: Maximum results (default: 50).

        Returns:
            Dict with list of worktrees.
        """
        worktrees = worktree_storage.list_worktrees(
            project_id=project_id,
            status=status,
            agent_session_id=agent_session_id,
            limit=limit,
        )

        return {
            "success": True,
            "worktrees": [
                {
                    "id": wt.id,
                    "branch_name": wt.branch_name,
                    "worktree_path": wt.worktree_path,
                    "status": wt.status,
                    "task_id": wt.task_id,
                    "agent_session_id": wt.agent_session_id,
                    "created_at": wt.created_at,
                }
                for wt in worktrees
            ],
            "count": len(worktrees),
        }

    @registry.tool(
        name="claim_worktree",
        description="Claim ownership of a worktree for an agent session.",
    )
    async def claim_worktree(
        worktree_id: str,
        session_id: str,
    ) -> dict[str, Any]:
        """
        Claim a worktree for an agent session.

        Args:
            worktree_id: The worktree ID to claim.
            session_id: The session ID claiming ownership.

        Returns:
            Dict with success status.
        """
        worktree = worktree_storage.get(worktree_id)
        if not worktree:
            return {
                "success": False,
                "error": f"Worktree '{worktree_id}' not found",
            }

        if worktree.agent_session_id and worktree.agent_session_id != session_id:
            return {
                "success": False,
                "error": f"Worktree already claimed by session '{worktree.agent_session_id}'",
            }

        updated = worktree_storage.claim(worktree_id, session_id)
        if not updated:
            return {
                "success": False,
                "error": "Failed to claim worktree",
            }

        return {
            "success": True,
            "worktree_id": worktree_id,
            "session_id": session_id,
            "message": f"Worktree '{worktree_id}' claimed by session '{session_id}'",
        }

    @registry.tool(
        name="release_worktree",
        description="Release ownership of a worktree.",
    )
    async def release_worktree(worktree_id: str) -> dict[str, Any]:
        """
        Release a worktree from its current owner.

        Args:
            worktree_id: The worktree ID to release.

        Returns:
            Dict with success status.
        """
        worktree = worktree_storage.get(worktree_id)
        if not worktree:
            return {
                "success": False,
                "error": f"Worktree '{worktree_id}' not found",
            }

        updated = worktree_storage.release(worktree_id)
        if not updated:
            return {
                "success": False,
                "error": "Failed to release worktree",
            }

        return {
            "success": True,
            "worktree_id": worktree_id,
            "message": f"Worktree '{worktree_id}' released",
        }

    @registry.tool(
        name="delete_worktree",
        description="Delete a worktree (both git and database record).",
    )
    async def delete_worktree(
        worktree_id: str,
        force: bool = False,
    ) -> dict[str, Any]:
        """
        Delete a worktree.

        Args:
            worktree_id: The worktree ID to delete.
            force: Force deletion even if there are uncommitted changes.

        Returns:
            Dict with success status.
        """
        worktree = worktree_storage.get(worktree_id)
        if not worktree:
            return {
                "success": False,
                "error": f"Worktree '{worktree_id}' not found",
            }

        # Check for uncommitted changes if not forcing
        if git_manager and not force:
            status = git_manager.get_worktree_status(worktree.worktree_path)
            if status and status.has_uncommitted_changes:
                return {
                    "success": False,
                    "error": "Worktree has uncommitted changes. Use force=True to delete anyway.",
                    "uncommitted_changes": True,
                }

        # Delete git worktree
        if git_manager:
            result = git_manager.delete_worktree(
                worktree.worktree_path,
                force=force,
            )
            if not result.success:
                return {
                    "success": False,
                    "error": result.error or "Failed to delete git worktree",
                }

        # Delete database record
        deleted = worktree_storage.delete(worktree_id)
        if not deleted:
            return {
                "success": False,
                "error": "Failed to delete worktree record",
            }

        return {
            "success": True,
            "worktree_id": worktree_id,
            "message": f"Worktree '{worktree_id}' deleted",
        }

    @registry.tool(
        name="sync_worktree",
        description="Sync a worktree with the main branch.",
    )
    async def sync_worktree(
        worktree_id: str,
        strategy: str = "merge",
    ) -> dict[str, Any]:
        """
        Sync a worktree with the main branch.

        Args:
            worktree_id: The worktree ID to sync.
            strategy: Sync strategy ('merge' or 'rebase').

        Returns:
            Dict with sync result.
        """
        if git_manager is None:
            return {
                "success": False,
                "error": "Git manager not configured.",
            }

        worktree = worktree_storage.get(worktree_id)
        if not worktree:
            return {
                "success": False,
                "error": f"Worktree '{worktree_id}' not found",
            }

        # Validate strategy
        if strategy not in ("rebase", "merge"):
            return {
                "success": False,
                "error": f"Invalid strategy '{strategy}'. Must be 'rebase' or 'merge'.",
            }

        strategy_literal: Literal["rebase", "merge"] = strategy  # type: ignore[assignment]

        result = git_manager.sync_from_main(
            worktree.worktree_path,
            base_branch=worktree.base_branch,
            strategy=strategy_literal,
        )

        if not result.success:
            return {
                "success": False,
                "error": result.error or "Sync failed",
            }

        # Update last activity
        worktree_storage.update(worktree_id)

        return {
            "success": True,
            "worktree_id": worktree_id,
            "message": f"Worktree synced with {worktree.base_branch} using {strategy}",
        }

    @registry.tool(
        name="mark_worktree_merged",
        description="Mark a worktree as merged (ready for cleanup).",
    )
    async def mark_worktree_merged(worktree_id: str) -> dict[str, Any]:
        """
        Mark a worktree as merged.

        Args:
            worktree_id: The worktree ID to mark.

        Returns:
            Dict with success status.
        """
        worktree = worktree_storage.get(worktree_id)
        if not worktree:
            return {
                "success": False,
                "error": f"Worktree '{worktree_id}' not found",
            }

        updated = worktree_storage.mark_merged(worktree_id)
        if not updated:
            return {
                "success": False,
                "error": "Failed to mark worktree as merged",
            }

        return {
            "success": True,
            "worktree_id": worktree_id,
            "status": WorktreeStatus.MERGED.value,
            "message": f"Worktree '{worktree_id}' marked as merged",
        }

    @registry.tool(
        name="detect_stale_worktrees",
        description="Find worktrees with no activity for a period.",
    )
    async def detect_stale_worktrees(
        hours: int = 24,
        limit: int = 50,
    ) -> dict[str, Any]:
        """
        Find stale worktrees (no activity for N hours).

        Args:
            hours: Hours of inactivity threshold (default: 24).
            limit: Maximum results (default: 50).

        Returns:
            Dict with list of stale worktrees.
        """
        if project_id is None:
            return {
                "success": False,
                "error": "No project context.",
            }

        stale = worktree_storage.find_stale(
            project_id=project_id,
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
        hours: int = 24,
        dry_run: bool = True,
        delete_git: bool = False,
    ) -> dict[str, Any]:
        """
        Cleanup stale worktrees.

        Args:
            hours: Hours of inactivity threshold (default: 24).
            dry_run: If True, only report what would be cleaned (default: True).
            delete_git: If True, also delete git worktrees (default: False).

        Returns:
            Dict with cleanup results.
        """
        if project_id is None:
            return {
                "success": False,
                "error": "No project context.",
            }

        # Find and mark stale worktrees
        stale = worktree_storage.cleanup_stale(
            project_id=project_id,
            hours=hours,
            dry_run=dry_run,
        )

        results = []
        for wt in stale:
            result = {
                "id": wt.id,
                "branch_name": wt.branch_name,
                "worktree_path": wt.worktree_path,
                "marked_abandoned": not dry_run,
                "git_deleted": False,
            }

            # Optionally delete git worktrees
            if delete_git and not dry_run and git_manager:
                git_result = git_manager.delete_worktree(
                    wt.worktree_path,
                    force=True,
                )
                result["git_deleted"] = git_result.success
                if not git_result.success:
                    result["git_error"] = git_result.error

            results.append(result)

        return {
            "success": True,
            "dry_run": dry_run,
            "cleaned": results,
            "count": len(results),
            "threshold_hours": hours,
        }

    @registry.tool(
        name="get_worktree_stats",
        description="Get worktree statistics for the project.",
    )
    async def get_worktree_stats(project_path: str | None = None) -> dict[str, Any]:
        """
        Get worktree statistics.

        Args:
            project_path: Path to project directory (pass cwd from CLI).

        Returns:
            Dict with counts by status.
        """
        # Resolve project context (git_manager not needed for stats)
        _, resolved_project_id, error = _resolve_project_context(
            project_path, git_manager, project_id
        )
        if error:
            return {"success": False, "error": error}

        counts = worktree_storage.count_by_status(resolved_project_id)

        return {
            "success": True,
            "project_id": resolved_project_id,
            "counts": counts,
            "total": sum(counts.values()),
        }

    @registry.tool(
        name="get_worktree_by_task",
        description="Get worktree linked to a specific task.",
    )
    async def get_worktree_by_task(task_id: str) -> dict[str, Any]:
        """
        Get worktree linked to a task.

        Args:
            task_id: The task ID to look up.

        Returns:
            Dict with worktree details or not found.
        """
        worktree = worktree_storage.get_by_task(task_id)
        if not worktree:
            return {
                "success": False,
                "error": f"No worktree linked to task '{task_id}'",
            }

        return {
            "success": True,
            "worktree": worktree.to_dict(),
        }

    @registry.tool(
        name="link_task_to_worktree",
        description="Link a task to an existing worktree.",
    )
    async def link_task_to_worktree(
        worktree_id: str,
        task_id: str,
    ) -> dict[str, Any]:
        """
        Link a task to a worktree.

        Args:
            worktree_id: The worktree ID.
            task_id: The task ID to link.

        Returns:
            Dict with success status.
        """
        worktree = worktree_storage.get(worktree_id)
        if not worktree:
            return {
                "success": False,
                "error": f"Worktree '{worktree_id}' not found",
            }

        updated = worktree_storage.update(worktree_id, task_id=task_id)
        if not updated:
            return {
                "success": False,
                "error": "Failed to link task to worktree",
            }

        return {
            "success": True,
            "worktree_id": worktree_id,
            "task_id": task_id,
            "message": f"Task '{task_id}' linked to worktree '{worktree_id}'",
        }

    @registry.tool(
        name="spawn_agent_in_worktree",
        description="Create a worktree and spawn an agent in it.",
    )
    async def spawn_agent_in_worktree(
        prompt: str,
        branch_name: str,
        base_branch: str = "main",
        task_id: str | None = None,
        parent_session_id: str | None = None,
        mode: str = "terminal",  # Note: in_process mode is not supported
        terminal: str = "auto",
        provider: str = "claude",
        model: str | None = None,
        workflow: str | None = None,
        timeout: float = 120.0,
        max_turns: int = 10,
    ) -> dict[str, Any]:
        """
        Create a worktree and spawn an agent to work in it.

        This combines worktree creation with agent spawning for isolated development.

        Args:
            prompt: The task/prompt for the agent.
            branch_name: Name for the new branch/worktree.
            base_branch: Branch to base the worktree on (default: main).
            task_id: Optional task ID to link to this worktree.
            parent_session_id: Parent session ID for context.
            mode: Execution mode (terminal, embedded, headless). Note: in_process is not supported.
            terminal: Terminal for terminal/embedded modes (auto, ghostty, etc.).
            provider: LLM provider (claude, gemini, etc.).
            model: Optional model override.
            workflow: Workflow name to execute.
            timeout: Execution timeout in seconds (default: 120).
            max_turns: Maximum turns (default: 10).

        Returns:
            Dict with worktree_id, run_id, and status.
        """
        if agent_runner is None:
            return {
                "success": False,
                "error": "Agent runner not configured. Cannot spawn agent.",
            }

        if git_manager is None:
            return {
                "success": False,
                "error": "Git manager not configured. Cannot create worktree.",
            }

        if project_id is None:
            return {
                "success": False,
                "error": "No project context. Run from a Gobby project directory.",
            }

        if parent_session_id is None:
            return {
                "success": False,
                "error": "parent_session_id is required for agent spawning.",
            }

        # in_process mode requires a real tool handler which isn't available
        # in this context. Only terminal/embedded/headless modes are supported.
        if mode == "in_process":
            return {
                "success": False,
                "error": (
                    "in_process mode is not supported for spawn_agent_in_worktree. "
                    "Use mode='terminal', 'embedded', or 'headless' instead. "
                    "in_process mode requires tool handler configuration not available in this context."
                ),
            }

        # Check if worktree already exists for this branch
        existing = worktree_storage.get_by_branch(project_id, branch_name)
        if existing:
            # Use existing worktree
            worktree = existing
            logger.info(f"Using existing worktree for branch '{branch_name}'")
        else:
            # Generate worktree path as sibling directory
            worktree_path = str(Path(git_manager.repo_path).parent / branch_name)

            # Create git worktree
            result = git_manager.create_worktree(
                worktree_path=worktree_path,
                branch_name=branch_name,
                base_branch=base_branch,
                create_branch=True,
            )

            if not result.success:
                return {
                    "success": False,
                    "error": result.error or "Failed to create git worktree",
                }

            # Record in database
            worktree = worktree_storage.create(
                project_id=project_id,
                branch_name=branch_name,
                worktree_path=worktree_path,
                base_branch=base_branch,
                task_id=task_id,
            )

        # Check spawn depth limit
        can_spawn, reason, _depth = agent_runner.can_spawn(parent_session_id)
        if not can_spawn:
            return {
                "success": False,
                "error": reason,
                "worktree_id": worktree.id,
            }

        # Import AgentConfig and get machine_id
        from gobby.agents.runner import AgentConfig
        from gobby.utils.machine_id import get_machine_id

        # Auto-detect machine_id if not provided
        machine_id = get_machine_id()

        # Create agent config with worktree
        config = AgentConfig(
            prompt=prompt,
            parent_session_id=parent_session_id,
            project_id=project_id,
            machine_id=machine_id,
            source=provider,
            workflow=workflow,
            task=task_id,
            session_context="summary_markdown",
            mode=mode,
            terminal=terminal,
            worktree_id=worktree.id,
            provider=provider,
            model=model,
            max_turns=max_turns,
            timeout=timeout,
            project_path=worktree.worktree_path,
        )

        # Stub tool handler for terminal/embedded/headless modes.
        # For these modes, the spawned external process handles its own tools.
        # in_process mode (which would need this handler) is blocked above.
        # This stub exists to satisfy the agent_runner.run() signature.
        async def tool_handler(tool_name: str, arguments: dict[str, Any]) -> Any:
            from gobby.llm.executor import ToolResult

            return ToolResult(
                tool_name=tool_name,
                success=False,
                error=f"Tool {tool_name} not available - external process handles tools",
            )

        # Run the agent
        run_result = await agent_runner.run(config, tool_handler=tool_handler)

        # Claim worktree for the child session
        if run_result.child_session_id:
            worktree_storage.claim(worktree.id, run_result.child_session_id)

        return {
            "success": run_result.status in ("success", "partial"),
            "worktree_id": worktree.id,
            "worktree_path": worktree.worktree_path,
            "branch_name": worktree.branch_name,
            "run_id": run_result.run_id,
            "status": run_result.status,
            "child_session_id": run_result.child_session_id,
            "output": run_result.output,
            "error": run_result.error,
        }

    return registry
