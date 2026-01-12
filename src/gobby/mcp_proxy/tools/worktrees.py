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

import json
import logging
import platform
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.utils.project_context import get_project_context
from gobby.workflows.loader import WorkflowLoader
from gobby.worktrees.git import WorktreeGitManager

if TYPE_CHECKING:
    from gobby.agents.runner import AgentRunner
    from gobby.storage.worktrees import LocalWorktreeManager
    from gobby.worktrees.git import WorktreeGitManager

logger = logging.getLogger(__name__)

# Cache for WorktreeGitManager instances per repo path
_git_manager_cache: dict[str, WorktreeGitManager] = {}


def _get_worktree_base_dir() -> Path:
    """
    Get the base directory for worktrees.

    Uses the system temp directory:
    - macOS/Linux: /tmp/gobby-worktrees/
    - Windows: %TEMP%/gobby-worktrees/

    Returns:
        Path to worktree base directory (creates if needed)
    """
    if platform.system() == "Windows":
        # Windows: use %TEMP% (typically C:\\Users\\<user>\\AppData\\Local\\Temp)
        base = Path(tempfile.gettempdir()) / "gobby-worktrees"
    else:
        # macOS/Linux: use /tmp for better isolation
        # Resolve symlink on macOS (/tmp -> /private/tmp) for consistent paths
        base = Path("/tmp").resolve() / "gobby-worktrees"

    base.mkdir(parents=True, exist_ok=True)
    return base


def _generate_worktree_path(branch_name: str, project_name: str | None = None) -> str:
    """
    Generate a worktree path in the temp directory.

    Args:
        branch_name: Branch name (used as directory name)
        project_name: Optional project name for namespacing

    Returns:
        Full path for the worktree
    """
    base = _get_worktree_base_dir()

    # Sanitize branch name for filesystem (replace / with -)
    safe_branch = branch_name.replace("/", "-")

    if project_name:
        # Namespace by project: /tmp/gobby-worktrees/project-name/branch-name
        return str(base / project_name / safe_branch)
    else:
        # No project namespace: /tmp/gobby-worktrees/branch-name
        return str(base / safe_branch)


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


def _copy_project_json_to_worktree(
    repo_path: str | Path,
    worktree_path: str | Path,
) -> None:
    """
    Copy .gobby/project.json from main repo to worktree, adding parent reference.

    This ensures worktree sessions:
    - Use the same project_id as the parent repo
    - Can discover the parent project path for workflow lookup

    Args:
        repo_path: Path to main repository
        worktree_path: Path to worktree directory
    """
    main_gobby_dir = Path(repo_path) / ".gobby"
    main_project_json = main_gobby_dir / "project.json"
    worktree_gobby_dir = Path(worktree_path) / ".gobby"

    if main_project_json.exists():
        try:
            worktree_gobby_dir.mkdir(parents=True, exist_ok=True)
            worktree_project_json = worktree_gobby_dir / "project.json"
            if not worktree_project_json.exists():
                # Read, add parent reference, write
                with open(main_project_json) as f:
                    data = json.load(f)

                data["parent_project_path"] = str(Path(repo_path).resolve())

                with open(worktree_project_json, "w") as f:
                    json.dump(data, f, indent=2)

                logger.info("Created project.json in worktree with parent reference")
        except Exception as e:
            logger.warning(f"Failed to create project.json in worktree: {e}")


def _install_provider_hooks(
    provider: Literal["claude", "gemini", "codex", "antigravity"] | None,
    worktree_path: str | Path,
) -> bool:
    """
    Install CLI hooks for the specified provider in the worktree.

    Args:
        provider: Provider name ('claude', 'gemini', 'antigravity', or None)
        worktree_path: Path to worktree directory

    Returns:
        True if hooks were successfully installed, False otherwise
    """
    if not provider:
        return False

    worktree_path_obj = Path(worktree_path)
    try:
        if provider == "claude":
            from gobby.cli.installers.claude import install_claude

            result = install_claude(worktree_path_obj)
            if result["success"]:
                logger.info(f"Installed Claude hooks in worktree: {worktree_path}")
                return True
            else:
                logger.warning(f"Failed to install Claude hooks: {result.get('error')}")
        elif provider == "gemini":
            from gobby.cli.installers.gemini import install_gemini

            result = install_gemini(worktree_path_obj)
            if result["success"]:
                logger.info(f"Installed Gemini hooks in worktree: {worktree_path}")
                return True
            else:
                logger.warning(f"Failed to install Gemini hooks: {result.get('error')}")
        elif provider == "antigravity":
            from gobby.cli.installers.antigravity import install_antigravity

            result = install_antigravity(worktree_path_obj)
            if result["success"]:
                logger.info(f"Installed Antigravity hooks in worktree: {worktree_path}")
                return True
            else:
                logger.warning(f"Failed to install Antigravity hooks: {result.get('error')}")
        # Note: codex uses CODEX_NOTIFY_SCRIPT env var, not project-level hooks
    except Exception as e:
        logger.warning(f"Failed to install {provider} hooks in worktree: {e}")
    return False


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
        provider: Literal["claude", "gemini", "codex", "antigravity"] | None = None,
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
            provider: CLI provider to install hooks for (claude, gemini, codex, antigravity).
                     If specified, installs hooks so agents can communicate with daemon.

        Returns:
            Dict with worktree ID, path, and branch info.
        """
        # Resolve project context
        resolved_git_mgr, resolved_project_id, error = _resolve_project_context(
            project_path, git_manager, project_id
        )
        if error:
            return {"success": False, "error": error}

        # Type narrowing: if no error, these are guaranteed non-None
        if resolved_git_mgr is None or resolved_project_id is None:
            raise RuntimeError("Git manager or project ID unexpectedly None")

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
            # Use temp directory (e.g., /tmp/gobby-worktrees/project-name/branch-name)
            project_name = Path(resolved_git_mgr.repo_path).name
            worktree_path = _generate_worktree_path(branch_name, project_name)

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

        # Copy project.json and install provider hooks
        _copy_project_json_to_worktree(resolved_git_mgr.repo_path, worktree.worktree_path)
        hooks_installed = _install_provider_hooks(provider, worktree.worktree_path)

        return {
            "success": True,
            "worktree_id": worktree.id,
            "worktree_path": worktree.worktree_path,
            "hooks_installed": hooks_installed,
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

        return {"success": True}

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

        return {"success": True}

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

        return {"success": True}

    @registry.tool(
        name="sync_worktree",
        description="Sync a worktree with the main branch.",
    )
    async def sync_worktree(
        worktree_id: str,
        strategy: str = "merge",
        project_path: str | None = None,
    ) -> dict[str, Any]:
        """
        Sync a worktree with the main branch.

        Args:
            worktree_id: The worktree ID to sync.
            strategy: Sync strategy ('merge' or 'rebase').
            project_path: Path to project directory (pass cwd from CLI).

        Returns:
            Dict with sync result.
        """
        # Resolve git manager from project_path or fall back to default
        resolved_git_mgr, _, error = _resolve_project_context(
            project_path, git_manager, project_id
        )
        if error:
            return {"success": False, "error": error}

        if resolved_git_mgr is None:
            return {
                "success": False,
                "error": "Git manager not configured and no project_path provided.",
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

        strategy_literal = cast(Literal["rebase", "merge"], strategy)

        result = resolved_git_mgr.sync_from_main(
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
            "message": result.message,
            "output": result.output,
            "strategy": strategy,
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

        return {"success": True}

    @registry.tool(
        name="detect_stale_worktrees",
        description="Find worktrees with no activity for a period.",
    )
    async def detect_stale_worktrees(
        project_path: str | None = None,
        hours: int = 24,
        limit: int = 50,
    ) -> dict[str, Any]:
        """
        Find stale worktrees (no activity for N hours).

        Args:
            project_path: Path to project directory (pass cwd from CLI).
            hours: Hours of inactivity threshold (default: 24).
            limit: Maximum results (default: 50).

        Returns:
            Dict with list of stale worktrees.
        """
        _, resolved_project_id, error = _resolve_project_context(
            project_path, git_manager, project_id
        )
        if error:
            return {"success": False, "error": error}
        if resolved_project_id is None:
            return {"success": False, "error": "Could not resolve project ID"}

        stale = worktree_storage.find_stale(
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
        hours: int = 24,
        dry_run: bool = True,
        delete_git: bool = False,
    ) -> dict[str, Any]:
        """
        Cleanup stale worktrees.

        Args:
            project_path: Path to project directory (pass cwd from CLI).
            hours: Hours of inactivity threshold (default: 24).
            dry_run: If True, only report what would be cleaned (default: True).
            delete_git: If True, also delete git worktrees (default: False).

        Returns:
            Dict with cleanup results.
        """
        resolved_git_manager, resolved_project_id, error = _resolve_project_context(
            project_path, git_manager, project_id
        )
        if error:
            return {"success": False, "error": error}
        if resolved_project_id is None:
            return {"success": False, "error": "Could not resolve project ID"}

        # Find and mark stale worktrees
        stale = worktree_storage.cleanup_stale(
            project_id=resolved_project_id,
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
            if delete_git and not dry_run and resolved_git_manager:
                git_result = resolved_git_manager.delete_worktree(
                    wt.worktree_path,
                    force=True,
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

        # Type narrowing: if no error, resolved_project_id is guaranteed non-None
        if resolved_project_id is None:
            raise RuntimeError("Project ID unexpectedly None")

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

        return {"success": True}

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
        provider: Literal["claude", "gemini", "codex", "antigravity"] = "claude",
        model: str | None = None,
        workflow: str | None = None,
        timeout: float = 120.0,
        max_turns: int = 10,
        project_path: str | None = None,
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
            project_path: Path to project directory (pass cwd from CLI).

        Returns:
            Dict with worktree_id, run_id, and status.
        """
        if agent_runner is None:
            return {
                "success": False,
                "error": "Agent runner not configured. Cannot spawn agent.",
            }

        # Resolve project context
        resolved_git_mgr, resolved_project_id, error = _resolve_project_context(
            project_path, git_manager, project_id
        )
        if error:
            return {"success": False, "error": error}

        # Type narrowing: if no error, these are guaranteed non-None
        if resolved_git_mgr is None or resolved_project_id is None:
            raise RuntimeError("Git manager or project ID unexpectedly None")

        if parent_session_id is None:
            return {
                "success": False,
                "error": "parent_session_id is required for agent spawning.",
            }

        # Handle mode aliases and validation
        # "interactive" is an alias for "terminal" mode
        if mode == "interactive":
            mode = "terminal"

        valid_modes = ["terminal", "embedded", "headless"]
        if mode not in valid_modes:
            return {
                "success": False,
                "error": (
                    f"Invalid mode '{mode}'. Must be one of: {', '.join(valid_modes)} (or 'interactive' as alias for 'terminal'). "
                    f"Note: 'in_process' mode is not supported for spawn_agent_in_worktree."
                ),
            }

        # Normalize terminal parameter to lowercase for enum compatibility
        # (TerminalType enum values are lowercase, e.g., "terminal.app" not "Terminal.app")
        if isinstance(terminal, str):
            terminal = terminal.lower()

        # Validate workflow (reject lifecycle workflows)
        if workflow:
            workflow_loader = WorkflowLoader()
            is_valid, error_msg = workflow_loader.validate_workflow_for_agent(
                workflow, project_path=project_path
            )
            if not is_valid:
                return {
                    "success": False,
                    "error": error_msg,
                }

        # Check if worktree already exists for this branch
        existing = worktree_storage.get_by_branch(resolved_project_id, branch_name)
        if existing:
            # Use existing worktree
            worktree = existing
            logger.info(f"Using existing worktree for branch '{branch_name}'")
        else:
            # Generate worktree path in temp directory
            project_name = Path(resolved_git_mgr.repo_path).name
            worktree_path = _generate_worktree_path(branch_name, project_name)

            # Create git worktree
            result = resolved_git_mgr.create_worktree(
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
                project_id=resolved_project_id,
                branch_name=branch_name,
                worktree_path=worktree_path,
                base_branch=base_branch,
                task_id=task_id,
            )

        # Copy project.json and install provider hooks
        _copy_project_json_to_worktree(resolved_git_mgr.repo_path, worktree.worktree_path)
        _install_provider_hooks(provider, worktree.worktree_path)

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
            project_id=resolved_project_id,
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

        # For terminal/embedded/headless modes, use prepare_run + spawner
        # (runner.run() is only for in_process mode)
        from gobby.llm.executor import AgentResult

        prepare_result = agent_runner.prepare_run(config)
        if isinstance(prepare_result, AgentResult):
            # prepare_run returns AgentResult on error
            return {
                "success": False,
                "worktree_id": worktree.id,
                "worktree_path": worktree.worktree_path,
                "branch_name": worktree.branch_name,
                "error": prepare_result.error,
            }

        # Successfully prepared - we have context with session and run
        context = prepare_result

        if context.session is None or context.run is None:
            return {
                "success": False,
                "worktree_id": worktree.id,
                "error": "Internal error: context missing session or run after prepare_run",
            }

        child_session = context.session
        agent_run = context.run

        # Claim worktree for the child session
        worktree_storage.claim(worktree.id, child_session.id)

        # Spawn in terminal using TerminalSpawner
        if mode == "terminal":
            from gobby.agents.spawn import TerminalSpawner

            terminal_spawner = TerminalSpawner()
            terminal_result = terminal_spawner.spawn_agent(
                cli=provider,  # claude, gemini, codex
                cwd=worktree.worktree_path,
                session_id=child_session.id,
                parent_session_id=parent_session_id,
                agent_run_id=agent_run.id,
                project_id=resolved_project_id,
                workflow_name=workflow,
                agent_depth=child_session.agent_depth,
                max_agent_depth=agent_runner._child_session_manager.max_agent_depth,
                terminal=terminal,
                prompt=prompt,
            )

            if not terminal_result.success:
                return {
                    "success": False,
                    "worktree_id": worktree.id,
                    "worktree_path": worktree.worktree_path,
                    "branch_name": worktree.branch_name,
                    "run_id": agent_run.id,
                    "child_session_id": child_session.id,
                    "error": terminal_result.error or terminal_result.message,
                }

            return {
                "success": True,
                "worktree_id": worktree.id,
                "worktree_path": worktree.worktree_path,
                "branch_name": worktree.branch_name,
                "run_id": agent_run.id,
                "child_session_id": child_session.id,
                "status": "pending",
                "message": f"Agent spawned in {terminal_result.terminal_type} (PID: {terminal_result.pid})",
                "terminal_type": terminal_result.terminal_type,
                "pid": terminal_result.pid,
            }

        elif mode == "embedded":
            from gobby.agents.spawn import EmbeddedSpawner

            embedded_spawner = EmbeddedSpawner()
            embedded_result = embedded_spawner.spawn_agent(
                cli=provider,
                cwd=worktree.worktree_path,
                session_id=child_session.id,
                parent_session_id=parent_session_id,
                agent_run_id=agent_run.id,
                project_id=resolved_project_id,
                workflow_name=workflow,
                agent_depth=child_session.agent_depth,
                max_agent_depth=agent_runner._child_session_manager.max_agent_depth,
                prompt=prompt,
            )

            return {
                "success": embedded_result.success,
                "worktree_id": worktree.id,
                "worktree_path": worktree.worktree_path,
                "branch_name": worktree.branch_name,
                "run_id": agent_run.id,
                "child_session_id": child_session.id,
                "status": "pending" if embedded_result.success else "error",
                "error": embedded_result.error if not embedded_result.success else None,
            }

        else:  # headless
            from gobby.agents.spawn import HeadlessSpawner

            headless_spawner = HeadlessSpawner()
            headless_result = headless_spawner.spawn_agent(
                cli=provider,
                cwd=worktree.worktree_path,
                session_id=child_session.id,
                parent_session_id=parent_session_id,
                agent_run_id=agent_run.id,
                project_id=resolved_project_id,
                workflow_name=workflow,
                agent_depth=child_session.agent_depth,
                max_agent_depth=agent_runner._child_session_manager.max_agent_depth,
                prompt=prompt,
            )

            return {
                "success": headless_result.success,
                "worktree_id": worktree.id,
                "worktree_path": worktree.worktree_path,
                "branch_name": worktree.branch_name,
                "run_id": agent_run.id,
                "child_session_id": child_session.id,
                "status": "pending" if headless_result.success else "error",
                "pid": headless_result.pid if headless_result.success else None,
                "error": headless_result.error if not headless_result.success else None,
            }

    return registry
