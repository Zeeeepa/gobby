"""Task orchestration tool: orchestrate_ready_tasks."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Literal

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.mcp_proxy.tools.task_readiness import _get_ready_descendants
from gobby.storage.tasks import TaskNotFoundError

from .utils import get_current_project_id

if TYPE_CHECKING:
    from gobby.agents.runner import AgentRunner
    from gobby.storage.tasks import LocalTaskManager
    from gobby.storage.worktrees import LocalWorktreeManager
    from gobby.worktrees.git import WorktreeGitManager

logger = logging.getLogger(__name__)


def register_orchestrator(
    registry: InternalToolRegistry,
    task_manager: LocalTaskManager,
    worktree_storage: LocalWorktreeManager,
    git_manager: WorktreeGitManager | None = None,
    agent_runner: AgentRunner | None = None,
    default_project_id: str | None = None,
) -> None:
    """Register orchestrate_ready_tasks tool."""

    # Lazy import to avoid circular dependency
    from gobby.mcp_proxy.tools.tasks import resolve_task_id_for_mcp

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
        base_branch: str | None = None,
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
            base_branch: Branch to base worktrees on (auto-detected if not provided)

        Returns:
            Dict with:
            - success: bool
            - spawned: List of {task_id, agent_id, worktree_id, branch_name}
            - skipped: List of {task_id, reason} for tasks not spawned
            - error: Optional error message
        """
        # Validate mode parameter
        valid_modes = {"terminal", "headless", "embedded"}
        if mode not in valid_modes:
            return {
                "success": False,
                "error": f"Invalid mode '{mode}'. Must be one of: {', '.join(sorted(valid_modes))}",
                "spawned": [],
                "skipped": [],
            }

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
                "spawned": [],
                "skipped": [],
            }

        # Get ready subtasks under the parent task
        ready_tasks = _get_ready_descendants(
            task_manager=task_manager,
            parent_task_id=resolved_parent_task_id,
            project_id=resolved_project_id,
        )

        if not ready_tasks:
            return {
                "success": True,
                "message": f"No ready subtasks found under {resolved_parent_task_id}",
                "spawned": [],
                "skipped": [],
            }

        # Check how many agents are currently running for this project
        # Get exact count by not limiting the query - ensures max_concurrent is respected
        from gobby.storage.worktrees import WorktreeStatus

        active_worktrees = worktree_storage.list_worktrees(
            project_id=resolved_project_id,
            status=WorktreeStatus.ACTIVE.value,
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
        from pathlib import Path

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
                # nosec B108: /tmp is intentional - worktrees are temporary
                base = Path("/tmp").resolve() / "gobby-worktrees"  # nosec B108
            base.mkdir(parents=True, exist_ok=True)
            return base

        # Detect base_branch if not provided
        effective_base_branch = base_branch
        if not effective_base_branch and git_manager is not None:
            effective_base_branch = git_manager.get_default_branch()
            logger.debug(f"Auto-detected base branch: {effective_base_branch}")
        elif not effective_base_branch:
            effective_base_branch = "main"  # Fallback when no git_manager

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

                # Validate workflow early (before creating worktree to avoid cleanup)
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

                # Determine worktree path
                newly_created_worktree = False
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
                        base_branch=effective_base_branch,
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
                        base_branch=effective_base_branch,
                        task_id=task.id,
                    )

                    # Copy project.json and install hooks (with cleanup on failure)
                    try:
                        _copy_project_json_to_worktree(
                            git_manager.repo_path, worktree.worktree_path
                        )
                        _install_provider_hooks(effective_provider, worktree.worktree_path)
                    except Exception as init_error:
                        # Cleanup: delete DB record and git worktree
                        worktree_storage.delete(worktree.id)
                        git_manager.delete_worktree(
                            worktree_path=worktree_path,
                            force=True,
                            delete_branch=True,
                        )
                        skipped.append(
                            {
                                "task_id": task.id,
                                "title": task.title,
                                "reason": f"Worktree initialization failed: {init_error}",
                            }
                        )
                        continue
                    newly_created_worktree = True

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

                # Note: Task status is updated to in_progress only after successful spawn

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
                        worktree_storage.release(worktree.id)
                        # Clean up newly created worktree on spawn failure
                        if newly_created_worktree and git_manager is not None:
                            worktree_storage.delete(worktree.id)
                            git_manager.delete_worktree(
                                worktree_path=worktree.worktree_path,
                                force=True,
                                delete_branch=True,
                            )
                        skipped.append(
                            {
                                "task_id": task.id,
                                "title": task.title,
                                "reason": spawn_result.error or "Terminal spawn failed",
                            }
                        )
                        continue

                    # Mark task as in_progress only after successful spawn
                    task_manager.update_task(task.id, status="in_progress")

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
                        worktree_storage.release(worktree.id)
                        # Clean up newly created worktree on spawn failure
                        if newly_created_worktree and git_manager is not None:
                            worktree_storage.delete(worktree.id)
                            git_manager.delete_worktree(
                                worktree_path=worktree.worktree_path,
                                force=True,
                                delete_branch=True,
                            )
                        skipped.append(
                            {
                                "task_id": task.id,
                                "title": task.title,
                                "reason": embedded_result.error or "Embedded spawn failed",
                            }
                        )
                        continue

                    # Mark task as in_progress only after successful spawn
                    task_manager.update_task(task.id, status="in_progress")

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
                        worktree_storage.release(worktree.id)
                        # Clean up newly created worktree on spawn failure
                        if newly_created_worktree and git_manager is not None:
                            worktree_storage.delete(worktree.id)
                            git_manager.delete_worktree(
                                worktree_path=worktree.worktree_path,
                                force=True,
                                delete_branch=True,
                            )
                        skipped.append(
                            {
                                "task_id": task.id,
                                "title": task.title,
                                "reason": headless_result.error or "Headless spawn failed",
                            }
                        )
                        continue

                    # Mark task as in_progress only after successful spawn
                    task_manager.update_task(task.id, status="in_progress")

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

    registry.register(
        name="orchestrate_ready_tasks",
        description=(
            "Spawn agents in worktrees for ready subtasks under a parent task. "
            "Used by auto-orchestrator workflow for parallel execution. "
            "Supports role-based provider assignment: explicitly passed params > workflow variables > defaults. "
            "Workflow variables: coding_provider, coding_model, terminal."
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
                "base_branch": {
                    "type": "string",
                    "description": (
                        "Branch to base worktrees on (e.g., main, master, develop). "
                        "Auto-detected from repository if not provided."
                    ),
                    "default": None,
                },
            },
            "required": ["parent_task_id", "parent_session_id"],
        },
        func=orchestrate_ready_tasks,
    )


def _build_task_prompt(task: Any) -> str:
    """Build a prompt for a task agent."""
    prompt_parts = [
        f"# Task: {task.title}",
        f"Task ID: {task.id}",
    ]

    if task.description:
        prompt_parts.append(f"\n## Description\n{task.description}")

    if task.category:
        prompt_parts.append(f"\n## Category\n{task.category}")

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
