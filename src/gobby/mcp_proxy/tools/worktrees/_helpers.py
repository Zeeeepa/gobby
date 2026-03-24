"""Shared helpers for worktree tools.

Module-level utility functions used across worktree tool handlers.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Literal

from gobby.utils.project_context import ensure_project_json_for_isolation, get_project_context
from gobby.worktrees.git import WorktreeGitManager

logger = logging.getLogger(__name__)

# Cache for WorktreeGitManager instances per repo path
_git_manager_cache: dict[str, WorktreeGitManager] = {}


def get_worktree_base_dir() -> Path:
    """Get the base directory for worktrees.

    Uses ~/.gobby/worktrees/ so worktrees survive reboots.

    Returns:
        Path to worktree base directory (creates if needed)
    """
    base = Path.home() / ".gobby" / "worktrees"
    base.mkdir(parents=True, exist_ok=True)
    return base


def generate_worktree_path(branch_name: str, project_name: str | None = None) -> str:
    """Generate a worktree path in the base directory.

    Args:
        branch_name: Branch name (used as directory name)
        project_name: Optional project name for namespacing

    Returns:
        Full path for the worktree
    """
    base = get_worktree_base_dir()
    safe_branch = re.sub(r'[\\:*?"<>|\s/]', "-", branch_name)
    safe_branch = re.sub(r"-{2,}", "-", safe_branch).strip("-")
    if not safe_branch:
        safe_branch = "unnamed-branch"

    if project_name:
        return str(base / project_name / safe_branch)
    else:
        return str(base / safe_branch)


def resolve_project_context(
    project_path: str | None,
    default_git_manager: WorktreeGitManager | None,
    default_project_id: str | None,
) -> tuple[WorktreeGitManager | None, str | None, str | None]:
    """Resolve project context from project_path or fall back to defaults.

    Args:
        project_path: Path to project directory (cwd from caller).
        default_git_manager: Registry-level git manager (may be None).
        default_project_id: Registry-level project ID (may be None).

    Returns:
        Tuple of (git_manager, project_id, error_message).
        If error_message is not None, the other values should not be used.
    """
    if project_path:
        path = Path(project_path)
        if not path.exists():
            return None, None, f"Project path does not exist: {project_path}"

        project_ctx = get_project_context(path)
        if not project_ctx:
            return None, None, f"No .gobby/project.json found in {project_path}"

        resolved_project_id = project_ctx.get("id")
        resolved_path = project_ctx.get("project_path", str(path))

        if resolved_path not in _git_manager_cache:
            try:
                _git_manager_cache[resolved_path] = WorktreeGitManager(resolved_path)
            except ValueError as e:
                return None, None, f"Invalid git repository: {e}"

        return _git_manager_cache[resolved_path], resolved_project_id, None

    # Fall back to defaults
    if default_git_manager is not None and default_project_id is not None:
        return default_git_manager, default_project_id, None

    # Try resolving from context var (set per-MCP-call from session)
    ctx = get_project_context()
    if ctx and ctx.get("id"):
        resolved_path = ctx.get("project_path")
        if resolved_path:
            if resolved_path not in _git_manager_cache:
                try:
                    _git_manager_cache[resolved_path] = WorktreeGitManager(resolved_path)
                except ValueError as e:
                    return None, None, f"Failed to initialize git manager for {resolved_path}: {e}"
            return _git_manager_cache[resolved_path], ctx["id"], None

    return (
        None,
        None,
        "No project_path provided and no project context available. Pass project_path parameter.",
    )


def copy_project_json_to_worktree(
    repo_path: str | Path,
    worktree_path: str | Path,
) -> None:
    """Copy .gobby/project.json from main repo to worktree, adding parent reference.

    Delegates to ``ensure_project_json_for_isolation`` which always writes
    ``parent_project_path`` even when the file already exists (e.g. git-tracked).
    """
    ensure_project_json_for_isolation(repo_path, worktree_path)


def install_provider_hooks(
    provider: Literal["claude", "gemini", "codex", "antigravity", "cursor", "windsurf", "copilot"]
    | None,
    worktree_path: str | Path,
) -> bool:
    """Install CLI hooks for the specified provider in the worktree.

    Args:
        provider: Provider name or None
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

            result = install_claude(worktree_path_obj, mode="project")
            if result["success"]:
                logger.info(f"Installed Claude hooks in worktree: {worktree_path}")
                return True
            else:
                logger.warning(f"Failed to install Claude hooks: {result.get('error')}")
        elif provider == "cursor":
            from gobby.cli.installers.cursor import install_cursor

            result = install_cursor(worktree_path_obj, mode="project")
            if result["success"]:
                logger.info(f"Installed Cursor hooks in worktree: {worktree_path}")
                return True
            else:
                logger.warning(f"Failed to install Cursor hooks: {result.get('error')}")
        elif provider == "windsurf":
            from gobby.cli.installers.windsurf import install_windsurf

            result = install_windsurf(worktree_path_obj, mode="project")
            if result["success"]:
                logger.info(f"Installed Windsurf hooks in worktree: {worktree_path}")
                return True
            else:
                logger.warning(f"Failed to install Windsurf hooks: {result.get('error')}")
        elif provider == "copilot":
            from gobby.cli.installers.copilot import install_copilot

            result = install_copilot(worktree_path_obj, mode="project")
            if result["success"]:
                logger.info(f"Installed Copilot hooks in worktree: {worktree_path}")
                return True
            else:
                logger.warning(f"Failed to install Copilot hooks: {result.get('error')}")
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
