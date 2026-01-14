"""
Task orchestration MCP tools module.

Provides tools for autonomous multi-agent task orchestration:
- orchestrate_ready_tasks: Spawn agents in worktrees for ready subtasks

Combines task readiness with worktree/agent spawning for the
auto-orchestrator workflow.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.mcp_proxy.tools.task_readiness import _get_ready_descendants
from gobby.storage.tasks import TaskNotFoundError
from gobby.utils.project_context import get_project_context

if TYPE_CHECKING:
    from gobby.agents.runner import AgentRunner
    from gobby.storage.tasks import LocalTaskManager
    from gobby.storage.worktrees import LocalWorktreeManager
    from gobby.worktrees.git import WorktreeGitManager

logger = logging.getLogger(__name__)

__all__ = [
    "create_orchestration_registry",
]


def get_current_project_id() -> str | None:
    """Get the current project ID from context."""
    context = get_project_context()
    return context.get("id") if context else None


def create_orchestration_registry(
    task_manager: LocalTaskManager,
    worktree_storage: LocalWorktreeManager,
    git_manager: WorktreeGitManager | None = None,
    agent_runner: AgentRunner | None = None,
    project_id: str | None = None,
) -> InternalToolRegistry:
    """
    Create a registry with task orchestration tools.

    Args:
        task_manager: LocalTaskManager for task operations
        worktree_storage: LocalWorktreeManager for worktree operations
        git_manager: WorktreeGitManager for git operations
        agent_runner: AgentRunner for spawning agents
        project_id: Default project ID

    Returns:
        InternalToolRegistry with orchestration tools registered
    """
    # Lazy import to avoid circular dependency
    from gobby.mcp_proxy.tools.tasks import resolve_task_id_for_mcp

    registry = InternalToolRegistry(
        name="gobby-tasks-orchestration",
        description="Task orchestration tools for multi-agent workflows",
    )

    # --- orchestrate_ready_tasks ---

    async def orchestrate_ready_tasks(
        parent_task_id: str,
        provider: Literal["claude", "gemini", "codex", "antigravity"] = "gemini",
        model: str | None = None,
        terminal: str = "auto",
        mode: str = "terminal",
        workflow: str | None = "auto-task",
        max_concurrent: int = 3,
        parent_session_id: str | None = None,
        project_path: str | None = None,
        coding_provider: Literal["claude", "gemini", "codex", "antigravity"] | None = None,
        coding_model: str | None = None,
    ) -> dict[str, Any]:
        """
        Orchestrate spawning agents in worktrees for ready subtasks.

        Gets ready subtasks under a parent task, creates worktrees for each,
        and spawns agents to work on them. Returns list of spawned agent/worktree pairs.

        Used by the auto-orchestrator workflow to parallelize work.

        Provider assignment:
        - coding_provider/coding_model: Use these for implementation tasks (preferred)
        - provider/model: Fallback if coding_* not specified

        Args:
            parent_task_id: Task reference: #N, N (seq_num), path (1.2.3), or UUID
            provider: Fallback LLM provider (default: gemini)
            model: Fallback model override
            terminal: Terminal for terminal mode (default: auto)
            mode: Execution mode (terminal, embedded, headless)
            workflow: Workflow for spawned agents (default: auto-task)
            max_concurrent: Maximum concurrent agents to spawn (default: 3)
            parent_session_id: Parent session ID for context (required)
            project_path: Path to project directory
            coding_provider: LLM provider for implementation tasks (overrides provider)
            coding_model: Model for implementation tasks (overrides model)

        Returns:
            Dict with:
            - success: bool
            - spawned: List of {task_id, agent_id, worktree_id, branch_name}
            - skipped: List of {task_id, reason} for tasks not spawned
            - error: Optional error message
        """
        # Resolve parent_task_id reference
        try:
            resolved_parent_task_id = resolve_task_id_for_mcp(task_manager, parent_task_id)
        except (TaskNotFoundError, ValueError) as e:
            return {
                "success": False,
                "error": f"Invalid parent_task_id: {e}",
                "spawned": [],
                "skipped": [],
            }

        if agent_runner is None:
            return {
                "success": False,
                "error": "Agent runner not configured. Cannot orchestrate.",
                "spawned": [],
                "skipped": [],
            }

        if parent_session_id is None:
            return {
                "success": False,
                "error": "parent_session_id is required for orchestration",
                "spawned": [],
                "skipped": [],
            }

        # Resolve project ID
        resolved_project_id = project_id
        if project_path:
            ctx = get_project_context(Path(project_path))
            if ctx:
                resolved_project_id = ctx.get("id")

        if not resolved_project_id:
            resolved_project_id = get_current_project_id()

        if not resolved_project_id:
            return {
                "success": False,
                "error": "Could not resolve project ID",
                "spawned": [],
                "skipped": [],
            }

        # Get ready subtasks under the parent task
        ready_tasks = _get_ready_descendants(
            task_manager=task_manager,
            parent_id=resolved_parent_task_id,
            project_id=resolved_project_id,
        )

        if not ready_tasks:
            return {
                "success": True,
                "message": f"No ready subtasks found under {resolved_parent_task_id}",
                "spawned": [],
                "skipped": [],
            }

        # Check how many agents are currently running for this parent
        from gobby.storage.worktrees import WorktreeStatus

        active_worktrees = worktree_storage.list_worktrees(
            project_id=resolved_project_id,
            status=WorktreeStatus.ACTIVE.value,
            limit=100,
        )

        # Count worktrees claimed by active sessions (have agent_session_id)
        current_running = sum(1 for wt in active_worktrees if wt.agent_session_id)
        available_slots = max(0, max_concurrent - current_running)

        if available_slots == 0:
            return {
                "success": True,
                "message": f"Max concurrent limit reached ({max_concurrent} agents running)",
                "spawned": [],
                "skipped": [
                    {"task_id": t.id, "reason": "max_concurrent limit reached"} for t in ready_tasks
                ],
                "current_running": current_running,
            }

        # Limit to available slots
        tasks_to_spawn = ready_tasks[:available_slots]
        tasks_skipped = ready_tasks[available_slots:]

        # Resolve effective provider and model for implementation tasks
        # Priority: explicit parameter > workflow variable > default
        from gobby.workflows.state_manager import WorkflowStateManager

        workflow_vars: dict[str, Any] = {}
        if parent_session_id:
            state_manager = WorkflowStateManager(task_manager.db)
            state = state_manager.get_state(parent_session_id)
            if state:
                workflow_vars = state.variables

        # Provider assignment chain: parameter > workflow var > default
        effective_provider = coding_provider or workflow_vars.get("coding_provider") or provider
        effective_model = coding_model or workflow_vars.get("coding_model") or model
        # Also capture terminal from workflow if not explicitly set
        effective_terminal = (
            terminal if terminal != "auto" else workflow_vars.get("terminal", "auto")
        )

        spawned: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []

        # Add skipped due to limit
        for task in tasks_skipped:
            skipped.append(
                {
                    "task_id": task.id,
                    "title": task.title,
                    "reason": "max_concurrent limit reached",
                }
            )

        # Import worktree tool helpers
        import platform
        import tempfile

        from gobby.mcp_proxy.tools.worktrees import (
            _copy_project_json_to_worktree,
            _install_provider_hooks,
        )
        from gobby.workflows.loader import WorkflowLoader

        def get_worktree_base_dir() -> Path:
            """Get base directory for worktrees."""
            if platform.system() == "Windows":
                base = Path(tempfile.gettempdir()) / "gobby-worktrees"
            else:
                base = Path("/tmp").resolve() / "gobby-worktrees"  # nosec B108
            base.mkdir(parents=True, exist_ok=True)
            return base

        for task in tasks_to_spawn:
            try:
                # Generate branch name from task ID
                branch_name = f"task/{task.id}"
                safe_branch = branch_name.replace("/", "-")

                # Check if worktree already exists for this task
                existing_wt = worktree_storage.get_by_task(task.id)
                if existing_wt and existing_wt.agent_session_id:
                    # Worktree exists and has active agent
                    skipped.append(
                        {
                            "task_id": task.id,
                            "title": task.title,
                            "reason": f"Already has active worktree: {existing_wt.id}",
                        }
                    )
                    continue

                # Check if branch worktree exists
                existing_branch_wt = worktree_storage.get_by_branch(
                    resolved_project_id, branch_name
                )
                if existing_branch_wt and existing_branch_wt.agent_session_id:
                    skipped.append(
                        {
                            "task_id": task.id,
                            "title": task.title,
                            "reason": f"Branch {branch_name} has active agent",
                        }
                    )
                    continue

                # Determine worktree path
                if existing_wt:
                    worktree = existing_wt
                elif existing_branch_wt:
                    worktree = existing_branch_wt
                    # Link task to existing worktree
                    worktree_storage.update(worktree.id, task_id=task.id)
                else:
                    # Create new worktree
                    if git_manager is None:
                        skipped.append(
                            {
                                "task_id": task.id,
                                "title": task.title,
                                "reason": "No git manager configured",
                            }
                        )
                        continue

                    # Generate path
                    project_name = Path(git_manager.repo_path).name
                    base_dir = get_worktree_base_dir()
                    worktree_path = str(base_dir / project_name / safe_branch)

                    # Create git worktree
                    result = git_manager.create_worktree(
                        worktree_path=worktree_path,
                        branch_name=branch_name,
                        base_branch="main",
                        create_branch=True,
                    )

                    if not result.success:
                        skipped.append(
                            {
                                "task_id": task.id,
                                "title": task.title,
                                "reason": f"Failed to create worktree: {result.error}",
                            }
                        )
                        continue

                    # Record in database
                    worktree = worktree_storage.create(
                        project_id=resolved_project_id,
                        branch_name=branch_name,
                        worktree_path=worktree_path,
                        base_branch="main",
                        task_id=task.id,
                    )

                    # Copy project.json and install hooks
                    _copy_project_json_to_worktree(git_manager.repo_path, worktree.worktree_path)
                    _install_provider_hooks(effective_provider, worktree.worktree_path)

                # Validate workflow
                if workflow:
                    workflow_loader = WorkflowLoader()
                    is_valid, error_msg = workflow_loader.validate_workflow_for_agent(
                        workflow, project_path=project_path
                    )
                    if not is_valid:
                        skipped.append(
                            {
                                "task_id": task.id,
                                "title": task.title,
                                "reason": f"Invalid workflow: {error_msg}",
                            }
                        )
                        continue

                # Build prompt with task context
                prompt = _build_task_prompt(task)

                # Check spawn depth
                can_spawn, reason, _depth = agent_runner.can_spawn(parent_session_id)
                if not can_spawn:
                    skipped.append(
                        {
                            "task_id": task.id,
                            "title": task.title,
                            "reason": reason,
                        }
                    )
                    continue

                # Prepare agent run
                from gobby.agents.runner import AgentConfig
                from gobby.llm.executor import AgentResult
                from gobby.utils.machine_id import get_machine_id

                machine_id = get_machine_id()

                config = AgentConfig(
                    prompt=prompt,
                    parent_session_id=parent_session_id,
                    project_id=resolved_project_id,
                    machine_id=machine_id,
                    source=effective_provider,
                    workflow=workflow,
                    task=task.id,
                    session_context="summary_markdown",
                    mode=mode,
                    terminal=effective_terminal,
                    worktree_id=worktree.id,
                    provider=effective_provider,
                    model=effective_model,
                    max_turns=50,  # Allow substantial work
                    timeout=600.0,  # 10 minutes
                    project_path=worktree.worktree_path,
                )

                prepare_result = agent_runner.prepare_run(config)
                if isinstance(prepare_result, AgentResult):
                    skipped.append(
                        {
                            "task_id": task.id,
                            "title": task.title,
                            "reason": prepare_result.error or "Failed to prepare agent run",
                        }
                    )
                    continue

                context = prepare_result
                if context.session is None or context.run is None:
                    skipped.append(
                        {
                            "task_id": task.id,
                            "title": task.title,
                            "reason": "Internal error: context missing session or run",
                        }
                    )
                    continue

                child_session = context.session
                agent_run = context.run

                # Claim worktree for child session
                worktree_storage.claim(worktree.id, child_session.id)

                # Mark task as in_progress
                task_manager.update_task(task.id, status="in_progress")

                # Spawn in terminal
                if mode == "terminal":
                    from gobby.agents.spawn import TerminalSpawner

                    spawner = TerminalSpawner()
                    spawn_result = spawner.spawn_agent(
                        cli=effective_provider,
                        cwd=worktree.worktree_path,
                        session_id=child_session.id,
                        parent_session_id=parent_session_id,
                        agent_run_id=agent_run.id,
                        project_id=resolved_project_id,
                        workflow_name=workflow,
                        agent_depth=child_session.agent_depth,
                        max_agent_depth=agent_runner._child_session_manager.max_agent_depth,
                        terminal=effective_terminal,
                        prompt=prompt,
                    )

                    if not spawn_result.success:
                        skipped.append(
                            {
                                "task_id": task.id,
                                "title": task.title,
                                "reason": spawn_result.error or "Terminal spawn failed",
                            }
                        )
                        continue

                    spawned.append(
                        {
                            "task_id": task.id,
                            "title": task.title,
                            "agent_id": agent_run.id,
                            "session_id": child_session.id,
                            "worktree_id": worktree.id,
                            "branch_name": worktree.branch_name,
                            "worktree_path": worktree.worktree_path,
                            "terminal_type": spawn_result.terminal_type,
                            "pid": spawn_result.pid,
                        }
                    )

                elif mode == "embedded":
                    from gobby.agents.spawn import EmbeddedSpawner

                    embedded_spawner = EmbeddedSpawner()
                    embedded_result = embedded_spawner.spawn_agent(
                        cli=effective_provider,
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

                    if not embedded_result.success:
                        skipped.append(
                            {
                                "task_id": task.id,
                                "title": task.title,
                                "reason": embedded_result.error or "Embedded spawn failed",
                            }
                        )
                        continue

                    spawned.append(
                        {
                            "task_id": task.id,
                            "title": task.title,
                            "agent_id": agent_run.id,
                            "session_id": child_session.id,
                            "worktree_id": worktree.id,
                            "branch_name": worktree.branch_name,
                            "worktree_path": worktree.worktree_path,
                        }
                    )

                else:  # headless
                    from gobby.agents.spawn import HeadlessSpawner

                    headless_spawner = HeadlessSpawner()
                    headless_result = headless_spawner.spawn_agent(
                        cli=effective_provider,
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

                    if not headless_result.success:
                        skipped.append(
                            {
                                "task_id": task.id,
                                "title": task.title,
                                "reason": headless_result.error or "Headless spawn failed",
                            }
                        )
                        continue

                    spawned.append(
                        {
                            "task_id": task.id,
                            "title": task.title,
                            "agent_id": agent_run.id,
                            "session_id": child_session.id,
                            "worktree_id": worktree.id,
                            "branch_name": worktree.branch_name,
                            "worktree_path": worktree.worktree_path,
                            "pid": headless_result.pid,
                        }
                    )

            except Exception as e:
                logger.exception(f"Error orchestrating task {task.id}")
                skipped.append(
                    {
                        "task_id": task.id,
                        "title": task.title,
                        "reason": str(e),
                    }
                )

        # Store spawned agents in workflow state for tracking
        if spawned and parent_session_id:
            try:
                state_manager = WorkflowStateManager(task_manager.db)
                state = state_manager.get_state(parent_session_id)
                if state:
                    current_spawned = state.variables.get("spawned_agents", [])
                    # Append new agents to existing list
                    current_spawned.extend(spawned)
                    state.variables["spawned_agents"] = current_spawned
                    state_manager.save_state(state)
                    logger.info(
                        f"Updated spawned_agents in workflow state: {len(current_spawned)} total"
                    )
            except Exception as e:
                logger.warning(f"Failed to update workflow state: {e}")

        return {
            "success": True,
            "parent_task_id": resolved_parent_task_id,
            "spawned": spawned,
            "skipped": skipped,
            "spawned_count": len(spawned),
            "skipped_count": len(skipped),
            "current_running": current_running + len(spawned),
            "max_concurrent": max_concurrent,
        }

    def _build_task_prompt(task: Any) -> str:
        """Build a prompt for a task agent."""
        prompt_parts = [
            f"# Task: {task.title}",
            f"Task ID: {task.id}",
        ]

        if task.description:
            prompt_parts.append(f"\n## Description\n{task.description}")

        if task.test_strategy:
            prompt_parts.append(f"\n## Test Strategy\n{task.test_strategy}")

        if task.validation_criteria:
            prompt_parts.append(f"\n## Validation Criteria\n{task.validation_criteria}")

        prompt_parts.append(
            "\n## Instructions\n"
            "1. Implement the task as described\n"
            "2. Write tests if applicable\n"
            f"3. Commit your changes with the task ID in the message: [{task.id}]\n"
            "4. Close the task when complete using close_task(commit_sha=...)"
        )

        return "\n".join(prompt_parts)

    registry.register(
        name="orchestrate_ready_tasks",
        description=(
            "Spawn agents in worktrees for ready subtasks under a parent task. "
            "Used by auto-orchestrator workflow for parallel execution. "
            "Supports role-based provider assignment: explicitly passed params > workflow variables > defaults. "
            "Workflow variables: coding_provider, coding_model, terminal, max_concurrent."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "parent_task_id": {
                    "type": "string",
                    "description": "Task reference: #N, N (seq_num), path (1.2.3), or UUID",
                },
                "provider": {
                    "type": "string",
                    "description": "Fallback LLM provider (claude, gemini, codex, antigravity)",
                    "default": "gemini",
                },
                "model": {
                    "type": "string",
                    "description": "Fallback model override",
                    "default": None,
                },
                "coding_provider": {
                    "type": "string",
                    "description": (
                        "LLM provider for implementation tasks. "
                        "Overrides 'provider' for coding work."
                    ),
                    "default": None,
                },
                "coding_model": {
                    "type": "string",
                    "description": (
                        "Model for implementation tasks. Overrides 'model' for coding work."
                    ),
                    "default": None,
                },
                "terminal": {
                    "type": "string",
                    "description": "Terminal for terminal mode (auto, ghostty, iterm2, etc.)",
                    "default": "auto",
                },
                "mode": {
                    "type": "string",
                    "description": "Execution mode (terminal, embedded, headless)",
                    "default": "terminal",
                },
                "workflow": {
                    "type": "string",
                    "description": "Workflow for spawned agents",
                    "default": "auto-task",
                },
                "max_concurrent": {
                    "type": "integer",
                    "description": "Maximum concurrent agents to spawn",
                    "default": 3,
                },
                "parent_session_id": {
                    "type": "string",
                    "description": "Parent session ID for context (required)",
                },
                "project_path": {
                    "type": "string",
                    "description": "Path to project directory",
                    "default": None,
                },
            },
            "required": ["parent_task_id", "parent_session_id"],
        },
        func=orchestrate_ready_tasks,
    )

    # --- get_orchestration_status ---

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
        resolved_project_id = project_id
        if project_path:
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
                "closed": len(closed_tasks),
                "total": len(subtasks),
            },
            "open_tasks": open_tasks,
            "in_progress_tasks": in_progress_tasks,
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
                    "default": None,
                },
            },
            "required": ["parent_task_id"],
        },
        func=get_orchestration_status,
    )

    # --- poll_agent_status ---

    async def poll_agent_status(
        parent_session_id: str,
        project_path: str | None = None,
    ) -> dict[str, Any]:
        """
        Poll running agents and update tracking lists in workflow state.

        Checks all spawned agents for completion/failure and moves them to
        appropriate lists (completed_agents, failed_agents). Used by the
        auto-orchestrator workflow's monitor step.

        Args:
            parent_session_id: Parent session ID (orchestrator session)
            project_path: Path to project directory

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
                task = task_manager.get_task(task_id)
                if task and task.status == "closed":
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
        if newly_completed or newly_failed or still_running != spawned_agents:
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
                "project_path": {
                    "type": "string",
                    "description": "Path to project directory",
                    "default": None,
                },
            },
            "required": ["parent_session_id"],
        },
        func=poll_agent_status,
    )

    # --- spawn_review_agent ---

    async def spawn_review_agent(
        task_id: str,
        review_provider: Literal["claude", "gemini", "codex", "antigravity"] = "claude",
        review_model: str | None = "claude-opus-4-5",
        terminal: str = "auto",
        mode: str = "terminal",
        parent_session_id: str | None = None,
        project_path: str | None = None,
    ) -> dict[str, Any]:
        """
        Spawn a review agent for a completed task.

        Used by the auto-orchestrator workflow's review step to validate
        completed work before merging/cleanup.

        Args:
            task_id: Task reference: #N, N (seq_num), path (1.2.3), or UUID
            review_provider: LLM provider for review (default: claude)
            review_model: Model for review (default: claude-opus-4-5 for thorough analysis)
            terminal: Terminal for terminal mode (default: auto)
            mode: Execution mode (terminal, embedded, headless)
            parent_session_id: Parent session ID for context (required)
            project_path: Path to project directory

        Returns:
            Dict with:
            - success: bool
            - agent_id: ID of spawned review agent
            - session_id: Child session ID
            - error: Optional error message
        """
        # Resolve task_id reference
        try:
            resolved_task_id = resolve_task_id_for_mcp(task_manager, task_id)
        except (TaskNotFoundError, ValueError) as e:
            return {
                "success": False,
                "error": f"Invalid task_id: {e}",
            }

        if agent_runner is None:
            return {
                "success": False,
                "error": "Agent runner not configured. Cannot spawn review agent.",
            }

        if parent_session_id is None:
            return {
                "success": False,
                "error": "parent_session_id is required for spawning review agent",
            }

        # Resolve project ID
        resolved_project_id = project_id
        if project_path:
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

        # Get the task
        task = task_manager.get_task(resolved_task_id)
        if not task:
            return {
                "success": False,
                "error": f"Task {task_id} not found",
            }

        # Get worktree for the task
        worktree = worktree_storage.get_by_task(resolved_task_id)
        if not worktree:
            return {
                "success": False,
                "error": f"No worktree found for task {resolved_task_id}",
            }

        # Build review prompt
        review_prompt = _build_review_prompt(task, worktree)

        # Check spawn depth
        can_spawn, reason, _depth = agent_runner.can_spawn(parent_session_id)
        if not can_spawn:
            return {
                "success": False,
                "error": reason,
            }

        # Prepare agent run
        from gobby.agents.runner import AgentConfig
        from gobby.llm.executor import AgentResult
        from gobby.utils.machine_id import get_machine_id

        machine_id = get_machine_id()

        config = AgentConfig(
            prompt=review_prompt,
            parent_session_id=parent_session_id,
            project_id=resolved_project_id,
            machine_id=machine_id,
            source=review_provider,
            workflow=None,  # Review doesn't need a workflow
            task=resolved_task_id,
            session_context="summary_markdown",
            mode=mode,
            terminal=terminal,
            worktree_id=worktree.id,
            provider=review_provider,
            model=review_model,
            max_turns=20,  # Reviews should be shorter
            timeout=300.0,  # 5 minutes
            project_path=worktree.worktree_path,
        )

        prepare_result = agent_runner.prepare_run(config)
        if isinstance(prepare_result, AgentResult):
            return {
                "success": False,
                "error": prepare_result.error or "Failed to prepare review agent run",
            }

        context = prepare_result
        if context.session is None or context.run is None:
            return {
                "success": False,
                "error": "Internal error: context missing session or run",
            }

        child_session = context.session
        agent_run = context.run

        # Spawn the review agent
        if mode == "terminal":
            from gobby.agents.spawn import TerminalSpawner

            spawner = TerminalSpawner()
            spawn_result = spawner.spawn_agent(
                cli=review_provider,
                cwd=worktree.worktree_path,
                session_id=child_session.id,
                parent_session_id=parent_session_id,
                agent_run_id=agent_run.id,
                project_id=resolved_project_id,
                workflow_name=None,
                agent_depth=child_session.agent_depth,
                max_agent_depth=agent_runner._child_session_manager.max_agent_depth,
                terminal=terminal,
                prompt=review_prompt,
            )

            if not spawn_result.success:
                return {
                    "success": False,
                    "error": spawn_result.error or "Terminal spawn failed",
                }

            return {
                "success": True,
                "task_id": resolved_task_id,
                "agent_id": agent_run.id,
                "session_id": child_session.id,
                "worktree_id": worktree.id,
                "terminal_type": spawn_result.terminal_type,
                "pid": spawn_result.pid,
                "provider": review_provider,
                "model": review_model,
            }

        elif mode == "embedded":
            from gobby.agents.spawn import EmbeddedSpawner

            embedded_spawner = EmbeddedSpawner()
            embedded_result = embedded_spawner.spawn_agent(
                cli=review_provider,
                cwd=worktree.worktree_path,
                session_id=child_session.id,
                parent_session_id=parent_session_id,
                agent_run_id=agent_run.id,
                project_id=resolved_project_id,
                workflow_name=None,
                agent_depth=child_session.agent_depth,
                max_agent_depth=agent_runner._child_session_manager.max_agent_depth,
                prompt=review_prompt,
            )

            if not embedded_result.success:
                return {
                    "success": False,
                    "error": embedded_result.error or "Embedded spawn failed",
                }

            return {
                "success": True,
                "task_id": resolved_task_id,
                "agent_id": agent_run.id,
                "session_id": child_session.id,
                "worktree_id": worktree.id,
                "provider": review_provider,
                "model": review_model,
            }

        else:  # headless
            from gobby.agents.spawn import HeadlessSpawner

            headless_spawner = HeadlessSpawner()
            headless_result = headless_spawner.spawn_agent(
                cli=review_provider,
                cwd=worktree.worktree_path,
                session_id=child_session.id,
                parent_session_id=parent_session_id,
                agent_run_id=agent_run.id,
                project_id=resolved_project_id,
                workflow_name=None,
                agent_depth=child_session.agent_depth,
                max_agent_depth=agent_runner._child_session_manager.max_agent_depth,
                prompt=review_prompt,
            )

            if not headless_result.success:
                return {
                    "success": False,
                    "error": headless_result.error or "Headless spawn failed",
                }

            return {
                "success": True,
                "task_id": resolved_task_id,
                "agent_id": agent_run.id,
                "session_id": child_session.id,
                "worktree_id": worktree.id,
                "pid": headless_result.pid,
                "provider": review_provider,
                "model": review_model,
            }

    def _build_review_prompt(task: Any, worktree: Any) -> str:
        """Build a review prompt for a completed task."""
        prompt_parts = [
            "# Code Review Request",
            f"\n## Task: {task.title}",
            f"Task ID: {task.id}",
            f"Branch: {worktree.branch_name}",
        ]

        if task.description:
            prompt_parts.append(f"\n## Task Description\n{task.description}")

        if task.validation_criteria:
            prompt_parts.append(f"\n## Validation Criteria\n{task.validation_criteria}")

        prompt_parts.append(
            "\n## Review Instructions\n"
            "1. Review the code changes on this branch\n"
            "2. Check that the implementation matches the task description\n"
            "3. Verify tests exist and pass (if applicable)\n"
            "4. Check for code quality, security issues, and best practices\n"
            "5. Use validate_task() to mark as valid/invalid with feedback\n"
            "6. If valid, the task can proceed to merge\n"
            "7. If invalid, provide clear feedback for the implementer"
        )

        return "\n".join(prompt_parts)

    registry.register(
        name="spawn_review_agent",
        description=(
            "Spawn a review agent for a completed task. "
            "Used by auto-orchestrator workflow for code review. "
            "Uses review_provider/review_model for thorough analysis."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task reference: #N, N (seq_num), path (1.2.3), or UUID",
                },
                "review_provider": {
                    "type": "string",
                    "description": "LLM provider for review (claude, gemini, codex, antigravity)",
                    "default": "claude",
                },
                "review_model": {
                    "type": "string",
                    "description": "Model for review (default: claude-opus-4-5 for thorough analysis)",
                    "default": "claude-opus-4-5",
                },
                "terminal": {
                    "type": "string",
                    "description": "Terminal for terminal mode (auto, ghostty, iterm2, etc.)",
                    "default": "auto",
                },
                "mode": {
                    "type": "string",
                    "description": "Execution mode (terminal, embedded, headless)",
                    "default": "terminal",
                },
                "parent_session_id": {
                    "type": "string",
                    "description": "Parent session ID for context (required)",
                },
                "project_path": {
                    "type": "string",
                    "description": "Path to project directory",
                    "default": None,
                },
            },
            "required": ["task_id", "parent_session_id"],
        },
        func=spawn_review_agent,
    )

    # --- process_completed_agents ---

    async def process_completed_agents(
        parent_session_id: str,
        spawn_reviews: bool = True,
        review_provider: Literal["claude", "gemini", "codex", "antigravity"] | None = None,
        review_model: str | None = None,
        terminal: str = "auto",
        mode: str = "terminal",
        project_path: str | None = None,
    ) -> dict[str, Any]:
        """
        Process completed agents and route them to review or cleanup.

        Takes agents from completed_agents list and either:
        - Spawns review agents for validation (if spawn_reviews=True)
        - Moves directly to reviewed_agents list (if already validated)

        For failed agents, optionally retries or escalates.

        Args:
            parent_session_id: Parent session ID (orchestrator session)
            spawn_reviews: Whether to spawn review agents for completed tasks
            review_provider: LLM provider for reviews (uses workflow variable if not set)
            review_model: Model for reviews (uses workflow variable if not set)
            terminal: Terminal for terminal mode
            mode: Execution mode for review agents
            project_path: Path to project directory

        Returns:
            Dict with:
            - reviews_spawned: List of review agents spawned
            - ready_for_cleanup: List of agents ready for worktree cleanup
            - retries_scheduled: List of failed agents scheduled for retry
            - escalated: List of agents escalated for manual intervention
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
                "reviews_spawned": [],
                "ready_for_cleanup": [],
                "retries_scheduled": [],
                "escalated": [],
                "message": "No workflow state found",
            }

        workflow_vars = state.variables
        completed_agents = workflow_vars.get("completed_agents", [])
        failed_agents = workflow_vars.get("failed_agents", [])
        reviewed_agents = workflow_vars.get("reviewed_agents", [])
        review_agents_spawned = workflow_vars.get("review_agents_spawned", [])

        # Resolve review provider from workflow vars or parameters
        effective_review_provider = (
            review_provider or workflow_vars.get("review_provider") or "claude"
        )
        effective_review_model = (
            review_model or workflow_vars.get("review_model") or "claude-opus-4-5"
        )

        reviews_spawned: list[dict[str, Any]] = []
        ready_for_cleanup: list[dict[str, Any]] = []
        retries_scheduled: list[dict[str, Any]] = []
        escalated: list[dict[str, Any]] = []

        # Process completed agents
        still_pending_review: list[dict[str, Any]] = []

        for agent_info in completed_agents:
            task_id = agent_info.get("task_id")
            if not task_id:
                # Invalid agent info
                escalated.append(
                    {
                        **agent_info,
                        "escalation_reason": "Missing task_id",
                    }
                )
                continue

            # Check task validation status
            task = task_manager.get_task(task_id)
            if not task:
                escalated.append(
                    {
                        **agent_info,
                        "escalation_reason": "Task not found",
                    }
                )
                continue

            # Check if task is already validated (passed validation)
            if task.validation_status == "valid":
                # Ready for cleanup
                ready_for_cleanup.append(
                    {
                        **agent_info,
                        "validation_status": "valid",
                    }
                )
                reviewed_agents.append(agent_info)
                continue

            # Check if task validation failed - may need retry
            if task.validation_status == "invalid":
                # Check failure count
                fail_count = task.validation_fail_count or 0
                max_retries = 3

                if fail_count >= max_retries:
                    # Escalate - too many failures
                    escalated.append(
                        {
                            **agent_info,
                            "escalation_reason": f"Validation failed {fail_count} times",
                            "validation_feedback": task.validation_feedback,
                        }
                    )
                else:
                    # Retry - reopen task and add back to queue
                    try:
                        task_manager.reopen_task(task_id, reason="Validation failed, retrying")
                        retries_scheduled.append(
                            {
                                **agent_info,
                                "retry_count": fail_count + 1,
                            }
                        )
                    except Exception as e:
                        escalated.append(
                            {
                                **agent_info,
                                "escalation_reason": f"Failed to reopen task: {e}",
                            }
                        )
                continue

            # Task needs review - spawn review agent if enabled
            if spawn_reviews:
                # Check if review agent already spawned for this task
                already_spawned = any(ra.get("task_id") == task_id for ra in review_agents_spawned)
                if already_spawned:
                    # Keep in pending review list
                    still_pending_review.append(agent_info)
                    continue

                # Spawn review agent
                review_result = await spawn_review_agent(
                    task_id=task_id,
                    review_provider=effective_review_provider,
                    review_model=effective_review_model,
                    terminal=terminal,
                    mode=mode,
                    parent_session_id=parent_session_id,
                    project_path=project_path,
                )

                if review_result.get("success"):
                    reviews_spawned.append(
                        {
                            "task_id": task_id,
                            "agent_id": review_result.get("agent_id"),
                            "session_id": review_result.get("session_id"),
                            "worktree_id": review_result.get("worktree_id"),
                        }
                    )
                    review_agents_spawned.append(
                        {
                            "task_id": task_id,
                            "agent_id": review_result.get("agent_id"),
                        }
                    )
                    # Keep agent in completed list until review completes
                    still_pending_review.append(agent_info)
                else:
                    # Review spawn failed - escalate
                    escalated.append(
                        {
                            **agent_info,
                            "escalation_reason": f"Review spawn failed: {review_result.get('error')}",
                        }
                    )
            else:
                # Not spawning reviews - move to ready_for_cleanup
                ready_for_cleanup.append(
                    {
                        **agent_info,
                        "skipped_review": True,
                    }
                )
                reviewed_agents.append(agent_info)

        # Process failed agents
        still_failed: list[dict[str, Any]] = []

        for agent_info in failed_agents:
            task_id = agent_info.get("task_id")
            failure_reason = agent_info.get("failure_reason", "Unknown")

            # Check if this is a retriable failure
            if "crashed" in failure_reason.lower() or "exited" in failure_reason.lower():
                # Potentially retriable - reopen task
                if task_id:
                    task = task_manager.get_task(task_id)
                    if task and task.status == "in_progress":
                        # Reopen for retry
                        try:
                            task_manager.update_task(task_id, status="open")
                            retries_scheduled.append(
                                {
                                    **agent_info,
                                    "retry_reason": "Agent crashed, reopened task",
                                }
                            )
                            continue
                        except Exception:
                            pass  # nosec B110 - Best-effort task reopen on crash

            # Non-retriable - escalate
            escalated.append(
                {
                    **agent_info,
                    "escalation_reason": failure_reason,
                }
            )

        # Update workflow state
        try:
            state = state_manager.get_state(parent_session_id)
            if state:
                # Update completed_agents to only include pending review
                state.variables["completed_agents"] = still_pending_review
                # Update reviewed_agents
                existing_reviewed = state.variables.get("reviewed_agents", [])
                existing_reviewed.extend(reviewed_agents)
                state.variables["reviewed_agents"] = existing_reviewed
                # Update review_agents_spawned
                state.variables["review_agents_spawned"] = review_agents_spawned
                # Update failed_agents
                state.variables["failed_agents"] = still_failed
                # Track escalated agents
                existing_escalated = state.variables.get("escalated_agents", [])
                existing_escalated.extend(escalated)
                state.variables["escalated_agents"] = existing_escalated

                state_manager.save_state(state)
        except Exception as e:
            logger.warning(f"Failed to update workflow state during processing: {e}")

        return {
            "success": True,
            "reviews_spawned": reviews_spawned,
            "ready_for_cleanup": ready_for_cleanup,
            "retries_scheduled": retries_scheduled,
            "escalated": escalated,
            "summary": {
                "reviews_spawned": len(reviews_spawned),
                "ready_for_cleanup": len(ready_for_cleanup),
                "retries_scheduled": len(retries_scheduled),
                "escalated": len(escalated),
                "pending_review": len(still_pending_review),
            },
        }

    registry.register(
        name="process_completed_agents",
        description=(
            "Process completed agents and route to review or cleanup. "
            "Spawns review agents for validation, handles retries for failures, "
            "escalates unrecoverable errors. Used by auto-orchestrator review step."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "parent_session_id": {
                    "type": "string",
                    "description": "Parent session ID (orchestrator session)",
                },
                "spawn_reviews": {
                    "type": "boolean",
                    "description": "Whether to spawn review agents for completed tasks",
                    "default": True,
                },
                "review_provider": {
                    "type": "string",
                    "description": "LLM provider for reviews (uses workflow variable if not set)",
                    "default": None,
                },
                "review_model": {
                    "type": "string",
                    "description": "Model for reviews (uses workflow variable if not set)",
                    "default": None,
                },
                "terminal": {
                    "type": "string",
                    "description": "Terminal for terminal mode",
                    "default": "auto",
                },
                "mode": {
                    "type": "string",
                    "description": "Execution mode for review agents",
                    "default": "terminal",
                },
                "project_path": {
                    "type": "string",
                    "description": "Path to project directory",
                    "default": None,
                },
            },
            "required": ["parent_session_id"],
        },
        func=process_completed_agents,
    )

    # --- cleanup_reviewed_worktrees ---

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
                # Step 1: Merge branch to base (if enabled)
                if merge_to_base:
                    merge_result = _merge_branch_to_base(
                        git_manager=git_manager,
                        branch_name=branch,
                        base_branch=worktree.base_branch,
                    )

                    if merge_result["success"]:
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

                # Step 2: Mark worktree as merged
                worktree_storage.mark_merged(worktree_id)

                # Step 3: Delete git worktree (if enabled)
                if delete_worktrees:
                    delete_result = git_manager.delete_worktree(
                        worktree_path=worktree_path,
                        force=force,
                        delete_branch=delete_branches,
                    )

                    if delete_result.success:
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
                        # Worktree deletion failed, but it's already marked as merged
                        failed.append(
                            {
                                **agent_info,
                                "failure_reason": f"Worktree deletion failed: {delete_result.message}",
                                "worktree_status": "merged",  # Still merged
                            }
                        )
                        continue

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
                remaining_reviewed = [a for a in reviewed_agents if a not in cleaned_agents]
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
                if "CONFLICT" in merge_result.stdout or "CONFLICT" in merge_result.stderr:
                    # Abort the merge
                    git_manager._run_git(["merge", "--abort"], timeout=10)
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
                    "description": "Path to project directory",
                    "default": None,
                },
            },
            "required": ["parent_session_id"],
        },
        func=cleanup_reviewed_worktrees,
    )

    # --- cleanup_stale_worktrees ---

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
            older_than_hours: Only cleanup worktrees older than this (default: 24)
            force: Force deletion even if dirty

        Returns:
            Dict with cleanup results
        """
        if git_manager is None:
            return {
                "success": False,
                "error": "Git manager not configured",
            }

        # Resolve project ID
        resolved_project_id = project_id
        if project_path:
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

            # Add active worktrees with no agent that are old enough
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
                    "description": "Path to project directory",
                    "default": None,
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

    return registry
