"""Task orchestration tools: monitor (poll_agent_status, get_orchestration_status)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.storage.tasks import TaskNotFoundError

from .utils import get_current_project_id

if TYPE_CHECKING:
    from gobby.agents.runner import AgentRunner
    from gobby.storage.tasks import LocalTaskManager
    from gobby.storage.worktrees import LocalWorktreeManager

logger = logging.getLogger(__name__)


def register_monitor(
    registry: InternalToolRegistry,
    task_manager: LocalTaskManager,
    worktree_storage: LocalWorktreeManager,
    agent_runner: AgentRunner | None = None,
    default_project_id: str | None = None,
) -> None:
    """Register monitor tools."""
    from gobby.mcp_proxy.tools.tasks import resolve_task_id_for_mcp

    async def get_orchestration_status(
        parent_task_id: str,
        project_path: str | None = None,
    ) -> dict[str, Any]:
        """
        Get the current orchestration status for a parent task.

        Returns information about spawned agents, their status, and worktree state.

        Args:
            parent_task_id: Task reference: #N, N (seq_num), path (1.2.3), or UUID
            project_path: Path to project directory

        Returns:
            Dict with orchestration status
        """
        # Resolve parent_task_id reference
        try:
            resolved_parent_task_id = resolve_task_id_for_mcp(task_manager, parent_task_id)
        except (TaskNotFoundError, ValueError) as e:
            return {
                "success": False,
                "error": f"Invalid parent_task_id: {e}",
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

        # Get subtasks
        subtasks = task_manager.list_tasks(parent_task_id=resolved_parent_task_id, limit=100)

        # Categorize by status
        open_tasks = []
        in_progress_tasks = []
        review_tasks: list[dict[str, Any]] = []
        closed_tasks = []

        for task in subtasks:
            task_info: dict[str, Any] = {
                "id": task.id,
                "title": task.title,
                "status": task.status,
                "validation_status": task.validation_status,
            }

            # Check for linked worktree
            worktree = worktree_storage.get_by_task(task.id)
            if worktree:
                task_info["worktree_id"] = worktree.id
                task_info["worktree_status"] = worktree.status
                task_info["has_active_agent"] = worktree.agent_session_id is not None

            if task.status == "closed":
                closed_tasks.append(task_info)
            elif task.status == "in_progress":
                in_progress_tasks.append(task_info)
            elif task.status == "review":
                review_tasks.append(task_info)
            else:
                open_tasks.append(task_info)

        # Check if parent task is complete
        parent_task = task_manager.get_task(resolved_parent_task_id)
        is_complete = parent_task and parent_task.status == "closed"

        return {
            "success": True,
            "parent_task_id": resolved_parent_task_id,
            "is_complete": is_complete,
            "summary": {
                "open": len(open_tasks),
                "in_progress": len(in_progress_tasks),
                "review": len(review_tasks),
                "closed": len(closed_tasks),
                "total": len(subtasks),
            },
            "open_tasks": open_tasks,
            "in_progress_tasks": in_progress_tasks,
            "review_tasks": review_tasks,
            "closed_tasks": closed_tasks,
        }

    registry.register(
        name="get_orchestration_status",
        description="Get current orchestration status for a parent task",
        input_schema={
            "type": "object",
            "properties": {
                "parent_task_id": {
                    "type": "string",
                    "description": "Task reference: #N, N (seq_num), path (1.2.3), or UUID",
                },
                "project_path": {
                    "type": "string",
                    "description": "Path to project directory",
                },
            },
            "required": ["parent_task_id"],
        },
        func=get_orchestration_status,
    )

    async def poll_agent_status(
        parent_session_id: str,
    ) -> dict[str, Any]:
        """
        Poll running agents and update tracking lists in workflow state.

        Checks all spawned agents for completion/failure and moves them to
        appropriate lists (completed_agents, failed_agents). Used by the
        auto-orchestrator workflow's monitor step.

        Args:
            parent_session_id: Parent session ID (orchestrator session)

        Returns:
            Dict with:
            - still_running: List of agents still in progress
            - newly_completed: List of agents that completed since last poll
            - newly_failed: List of agents that failed since last poll
            - summary: Counts of running/completed/failed
        """
        if agent_runner is None:
            return {
                "success": False,
                "error": "Agent runner not configured",
            }

        # Get workflow state
        from gobby.workflows.state_manager import WorkflowStateManager

        state_manager = WorkflowStateManager(task_manager.db)
        state = state_manager.get_state(parent_session_id)
        if not state:
            return {
                "success": True,
                "still_running": [],
                "newly_completed": [],
                "newly_failed": [],
                "summary": {"running": 0, "completed": 0, "failed": 0},
                "message": "No workflow state found",
            }

        workflow_vars = state.variables
        spawned_agents = workflow_vars.get("spawned_agents", [])
        completed_agents = workflow_vars.get("completed_agents", [])
        failed_agents = workflow_vars.get("failed_agents", [])

        if not spawned_agents:
            return {
                "success": True,
                "still_running": [],
                "newly_completed": completed_agents,
                "newly_failed": failed_agents,
                "summary": {
                    "running": 0,
                    "completed": len(completed_agents),
                    "failed": len(failed_agents),
                },
                "message": "No spawned agents to poll",
            }

        # Check status of each spawned agent
        still_running: list[dict[str, Any]] = []
        newly_completed: list[dict[str, Any]] = []
        newly_failed: list[dict[str, Any]] = []

        for agent_info in spawned_agents:
            session_id = agent_info.get("session_id")
            task_id = agent_info.get("task_id")

            if not session_id:
                # Invalid agent info, mark as failed
                newly_failed.append(
                    {
                        **agent_info,
                        "failure_reason": "Missing session_id in agent info",
                    }
                )
                continue

            # Check if the task is closed (agent completed successfully)
            if task_id:
                try:
                    task = task_manager.get_task(task_id)
                except Exception as e:
                    logger.warning(f"Failed to get task {task_id}: {e}")
                    task = None

                if task is not None and task.status == "closed":
                    newly_completed.append(
                        {
                            **agent_info,
                            "completed_at": task.closed_at,
                            "closed_reason": task.closed_reason,
                            "commit_sha": task.closed_commit_sha,
                        }
                    )
                    continue

            # Check worktree status (if agent released worktree, it's done)
            worktree_id = agent_info.get("worktree_id")
            if worktree_id:
                worktree = worktree_storage.get(worktree_id)
                if worktree and not worktree.agent_session_id:
                    # Worktree released but task not closed - check if failed
                    if task_id:
                        task = task_manager.get_task(task_id)
                        if task and task.status != "closed":
                            # Agent released worktree without closing task
                            newly_failed.append(
                                {
                                    **agent_info,
                                    "failure_reason": "Agent released worktree without closing task",
                                }
                            )
                            continue

            # Check if agent is still running via in-memory registry
            running_agent = agent_runner.get_running_agent(session_id)
            if running_agent:
                # Still running
                still_running.append(
                    {
                        **agent_info,
                        "running_since": running_agent.started_at.isoformat()
                        if running_agent.started_at
                        else None,
                    }
                )
            else:
                # Agent not in running registry and task not closed
                # Could be completed or failed - check task status
                if task_id:
                    task = task_manager.get_task(task_id)
                    if task and task.status == "closed":
                        newly_completed.append(
                            {
                                **agent_info,
                                "completed_at": task.closed_at,
                            }
                        )
                    elif task and task.status == "in_progress":
                        # Still in progress but agent not running - likely crashed
                        newly_failed.append(
                            {
                                **agent_info,
                                "failure_reason": "Agent exited without completing task",
                            }
                        )
                    else:
                        # Task open, agent not running - was never started properly
                        newly_failed.append(
                            {
                                **agent_info,
                                "failure_reason": "Agent not running and task not started",
                            }
                        )
                else:
                    # No task ID, can't determine status
                    newly_failed.append(
                        {
                            **agent_info,
                            "failure_reason": "Unknown status - no task_id",
                        }
                    )

        # Update workflow state
        # Compare by session IDs to detect real changes in agent membership
        # (dict comparison would fail due to added fields like running_since)
        still_running_ids = {a.get("session_id") for a in still_running}
        spawned_ids = {a.get("session_id") for a in spawned_agents}
        agents_changed = still_running_ids != spawned_ids

        if newly_completed or newly_failed or agents_changed:
            try:
                # Re-fetch state to ensure we have the latest
                state = state_manager.get_state(parent_session_id)
                if state:
                    # Update completed_agents list
                    if newly_completed:
                        existing_completed = state.variables.get("completed_agents", [])
                        existing_completed.extend(newly_completed)
                        state.variables["completed_agents"] = existing_completed
                        completed_agents = existing_completed

                    # Update failed_agents list
                    if newly_failed:
                        existing_failed = state.variables.get("failed_agents", [])
                        existing_failed.extend(newly_failed)
                        state.variables["failed_agents"] = existing_failed
                        failed_agents = existing_failed

                    # Update spawned_agents to only include still running
                    state.variables["spawned_agents"] = still_running

                    state_manager.save_state(state)

            except Exception as e:
                logger.warning(f"Failed to update workflow state during poll: {e}")

        return {
            "success": True,
            "still_running": still_running,
            "newly_completed": newly_completed,
            "newly_failed": newly_failed,
            "summary": {
                "running": len(still_running),
                "completed": len(completed_agents),
                "failed": len(failed_agents),
            },
            "all_done": len(still_running) == 0,
        }

    registry.register(
        name="poll_agent_status",
        description=(
            "Poll running agents and update tracking lists. "
            "Checks spawned_agents, moves completed to completed_agents and failed to failed_agents. "
            "Used by auto-orchestrator monitor step."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "parent_session_id": {
                    "type": "string",
                    "description": "Parent session ID (orchestrator session)",
                },
            },
            "required": ["parent_session_id"],
        },
        func=poll_agent_status,
    )
