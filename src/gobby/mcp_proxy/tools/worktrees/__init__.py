"""Worktree tools package.

This package provides MCP tools for git worktree management. Re-exports
maintain backwards compatibility with the original worktrees.py module.

Public API:
    - create_worktrees_registry: Factory function to create the worktree tool registry

Internal (exported for test compatibility):
    - Helper functions previously at module level in worktrees.py
"""

from gobby.mcp_proxy.tools.worktrees._factory import create_worktrees_registry
from gobby.mcp_proxy.tools.worktrees._helpers import (
    copy_project_json_to_worktree as _copy_project_json_to_worktree,
)
from gobby.mcp_proxy.tools.worktrees._helpers import (
    generate_worktree_path as _generate_worktree_path,
)
from gobby.mcp_proxy.tools.worktrees._helpers import (
    get_worktree_base_dir as _get_worktree_base_dir,
)
from gobby.mcp_proxy.tools.worktrees._helpers import (
    install_provider_hooks as _install_provider_hooks,
)
from gobby.mcp_proxy.tools.worktrees._helpers import (
    resolve_project_context as _resolve_project_context,
)

__all__ = [
    "create_worktrees_registry",
    # Internal exports for backward compatibility
    "_copy_project_json_to_worktree",
    "_generate_worktree_path",
    "_get_worktree_base_dir",
    "_install_provider_hooks",
    "_resolve_project_context",
]
