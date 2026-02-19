"""
Utilities for resolving project context.
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from gobby.config.features import HooksConfig, ProjectVerificationConfig

logger = logging.getLogger(__name__)

# Per-async-task project context, set by MCP tool calls from session data.
# Checked first by get_project_context() so daemon-level tools resolve the
# calling session's project, not the daemon's cwd.
_current_project_context: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "current_project_context", default=None
)


def set_project_context(ctx: dict[str, Any] | None) -> contextvars.Token[dict[str, Any] | None]:
    """Set project context for the current async task (used by MCP tool calls)."""
    return _current_project_context.set(ctx)


def reset_project_context(token: contextvars.Token[dict[str, Any] | None]) -> None:
    """Reset project context after tool call completes."""
    _current_project_context.reset(token)


def find_project_root(cwd: Path | None = None) -> Path | None:
    """
    Find the project root directory by looking for .gobby/project.json.

    Args:
        cwd: Current working directory to start search from. Defaults to Path.cwd().

    Returns:
        Path to project root if found, None otherwise.
    """
    if cwd is None:
        cwd = Path.cwd()

    current = cwd.resolve()
    # Traverse up
    for parent in [current] + list(current.parents):
        project_file = parent / ".gobby" / "project.json"
        if project_file.exists():
            return parent
    return None


def get_project_context(cwd: Path | None = None) -> dict[str, Any] | None:
    """
    Get project context from .gobby/project.json.

    Args:
        cwd: Current working directory to start search from.

    Returns:
        Dictionary containing project data (id, name, verification, etc.) and 'project_path',
        or None if not found.

        The returned dict may include:
        - id: Project ID
        - name: Project name
        - created_at: Creation timestamp
        - project_path: Path to project root
        - verification: Optional dict with unit_tests, type_check, lint, integration, custom
    """
    # 1. Check context var (set per-MCP-call from session)
    ctx = _current_project_context.get()
    if ctx is not None:
        return ctx

    # 2. Environment override (set by web chat subprocess for correct project routing)
    override_id = os.environ.get("GOBBY_PROJECT_ID")
    if override_id:
        root = find_project_root(cwd)
        if root:
            try:
                with open(root / ".gobby" / "project.json") as f:
                    data = json.load(f)
                data["project_path"] = str(root)
                if data.get("id") == override_id:
                    return cast(dict[str, Any], data)
            except (FileNotFoundError, PermissionError, json.JSONDecodeError, OSError) as e:
                logger.debug(f"Failed to read project.json for override ID {override_id}: {e}")
        # CWD doesn't match — return minimal context with just the ID
        return {"id": override_id}

    root = find_project_root(cwd)
    if not root:
        return None

    project_file = root / ".gobby" / "project.json"
    try:
        with open(project_file) as f:
            data = json.load(f)
        data["project_path"] = str(root)
        return cast(dict[str, Any], data)
    except (FileNotFoundError, PermissionError, json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to read project context: {e}")
        return None


def get_workflow_project_path(cwd: Path | None = None) -> Path | None:
    """
    Get the project path for workflow lookup.

    In a worktree, returns parent_project_path (where workflows live).
    In a main project, returns the project_path.

    This allows worktree agents to discover workflows from the parent project
    without needing to explicitly pass the project_path parameter.

    Args:
        cwd: Current working directory to start search from.

    Returns:
        Path to use for workflow discovery, or None if no project found.
    """
    ctx = get_project_context(cwd)
    if not ctx:
        return None

    # If in a worktree, use parent project for workflows
    parent = ctx.get("parent_project_path")
    if parent:
        return Path(parent)

    # Otherwise use current project path
    project_path = ctx.get("project_path")
    return Path(project_path) if project_path else None


def get_project_mcp_dir(project_name: str) -> Path:
    """
    Get the directory for project-specific MCP configuration.

    Args:
        project_name: Name of the project.

    Returns:
        Path to the project's MCP directory in ~/.gobby/projects/.
    """
    project_name_safe = project_name.replace(" ", "_").lower()
    return Path.home() / ".gobby" / "projects" / project_name_safe


def get_project_mcp_config_path(project_name: str) -> Path:
    """
    Get the path to the project-specific .mcp.json file.

    Args:
        project_name: Name of the project.

    Returns:
        Path to .mcp.json.
    """
    return get_project_mcp_dir(project_name) / ".mcp.json"


def get_verification_config(cwd: Path | None = None) -> ProjectVerificationConfig | None:
    """
    Get project verification configuration from .gobby/project.json.

    Args:
        cwd: Current working directory to start search from.

    Returns:
        ProjectVerificationConfig if verification section exists, None otherwise.
    """
    from gobby.config.features import ProjectVerificationConfig

    context = get_project_context(cwd)
    if not context:
        return None

    verification_data = context.get("verification")
    if not verification_data:
        return None

    try:
        return ProjectVerificationConfig(**verification_data)
    except Exception as e:
        logger.warning(f"Failed to parse verification config: {e}")
        return None


def get_hooks_config(cwd: Path | None = None) -> HooksConfig | None:
    """
    Get git hooks configuration from .gobby/project.json.

    Args:
        cwd: Current working directory to start search from.

    Returns:
        HooksConfig if hooks section exists, None otherwise.
    """
    from gobby.config.features import HooksConfig

    context = get_project_context(cwd)
    if not context:
        return None

    hooks_data = context.get("hooks")
    if not hooks_data:
        return None

    try:
        return HooksConfig(**hooks_data)
    except Exception as e:
        logger.warning(f"Failed to parse hooks config: {e}")
        return None
