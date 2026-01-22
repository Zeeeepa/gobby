"""Orchestration tool modules.

Contains decomposed orchestration functionality:
- orchestrate: Core orchestration tools (orchestrate_ready_tasks)
- monitor: Status monitoring tools (get_orchestration_status, poll_agent_status)
- review: Review workflow tools (spawn_review_agent, process_completed_agents)
- cleanup: Cleanup tools (cleanup_reviewed_worktrees, cleanup_stale_worktrees)
- wait: Blocking wait tools (wait_for_task, wait_for_any_task, wait_for_all_tasks)
- utils: Shared utilities
"""

from gobby.mcp_proxy.tools.orchestration.cleanup import register_cleanup
from gobby.mcp_proxy.tools.orchestration.monitor import register_monitor
from gobby.mcp_proxy.tools.orchestration.orchestrate import register_orchestrator
from gobby.mcp_proxy.tools.orchestration.review import register_reviewer
from gobby.mcp_proxy.tools.orchestration.utils import get_current_project_id
from gobby.mcp_proxy.tools.orchestration.wait import register_wait

__all__ = [
    "register_cleanup",
    "register_monitor",
    "register_orchestrator",
    "register_reviewer",
    "register_wait",
    "get_current_project_id",
]
