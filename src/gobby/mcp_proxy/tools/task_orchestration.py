"""Task orchestration tool registry."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.mcp_proxy.tools.orchestration.cleanup import register_cleanup
from gobby.mcp_proxy.tools.orchestration.monitor import register_monitor
from gobby.mcp_proxy.tools.orchestration.orchestrate import register_orchestrator
from gobby.mcp_proxy.tools.orchestration.review import register_reviewer
from gobby.mcp_proxy.tools.orchestration.utils import get_current_project_id
from gobby.mcp_proxy.tools.orchestration.wait import register_wait

if TYPE_CHECKING:
    from gobby.agents.runner import AgentRunner
    from gobby.storage.tasks import LocalTaskManager
    from gobby.storage.worktrees import LocalWorktreeManager
    from gobby.worktrees.git import WorktreeGitManager

logger = logging.getLogger(__name__)


def create_orchestration_registry(
    task_manager: LocalTaskManager,
    worktree_storage: LocalWorktreeManager,
    git_manager: WorktreeGitManager | None = None,
    agent_runner: AgentRunner | None = None,
    project_id: str | None = None,
) -> InternalToolRegistry:
    """Create registry with orchestration tools."""
    registry = InternalToolRegistry(
        name="gobby-orchestration",
        description="Task orchestration, monitoring, and review tools",
    )

    # Determine default project ID if not provided
    default_project_id = project_id or get_current_project_id()

    # Register orchestration tools
    register_orchestrator(
        registry=registry,
        task_manager=task_manager,
        worktree_storage=worktree_storage,
        git_manager=git_manager,
        agent_runner=agent_runner,
        default_project_id=default_project_id,
    )

    # Register monitor tools
    register_monitor(
        registry=registry,
        task_manager=task_manager,
        worktree_storage=worktree_storage,
        agent_runner=agent_runner,
        default_project_id=default_project_id,
    )

    # Register review tools
    register_reviewer(
        registry=registry,
        task_manager=task_manager,
        worktree_storage=worktree_storage,
        agent_runner=agent_runner,
        default_project_id=default_project_id,
    )

    # Register cleanup tools
    register_cleanup(
        registry=registry,
        task_manager=task_manager,
        worktree_storage=worktree_storage,
        git_manager=git_manager,
        default_project_id=default_project_id,
    )

    # Register wait tools
    register_wait(
        registry=registry,
        task_manager=task_manager,
    )

    return registry
