"""
MCP proxy tools module.

Provides factory functions for creating tool registries.
"""

# Main task registry (facade that merges all task-related registries)
# Extracted task module registries (for direct use or testing)
from gobby.mcp_proxy.tools.task_dependencies import create_dependency_registry
from gobby.mcp_proxy.tools.task_github import create_github_sync_registry
from gobby.mcp_proxy.tools.task_readiness import create_readiness_registry
from gobby.mcp_proxy.tools.task_sync import create_sync_registry
from gobby.mcp_proxy.tools.task_validation import create_validation_registry
from gobby.mcp_proxy.tools.tasks import create_task_registry

__all__ = [
    # Main facade
    "create_task_registry",
    # Extracted registries
    "create_dependency_registry",
    "create_github_sync_registry",
    "create_readiness_registry",
    "create_sync_registry",
    "create_validation_registry",
]
