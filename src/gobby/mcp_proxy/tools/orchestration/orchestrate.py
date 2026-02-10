"""Task orchestration tool: orchestrate_ready_tasks."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Literal

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.mcp_proxy.tools.task_readiness import _get_ready_descendants
from gobby.storage.tasks import Task, TaskNotFoundError

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
        provider: Literal[
            "claude", "gemini", "codex", "antigravity", "cursor", "windsurf", "copilot"
        ] = "gemini",
        model: str | None = None,
        terminal: str = "auto",
        mode: str = "terminal",
        workflow: str | None = "auto-task",
        max_concurrent: int = 3,
        parent_session_id: str | None = None,
        project_path: str | None = None,
        coding_provider: Literal[
            "claude", "gemini", "codex", "antigravity", "cursor", "windsurf", "copilot"
        ]
        | None = None,
        coding_model: str | None = None,
        base_branch: str | None = None,
        dry_run: bool = False,
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
            dry_run: If True, resolve tasks, check slots, build prompts, and return
                the plan without actually spawning agents or creating worktrees.

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

        # Atomically check capacity and reserve slots to prevent concurrent
        # orchestrate_ready_tasks calls from exceeding max_concurrent
        from gobby.workflows.state_manager import WorkflowStateManager

        state_manager = WorkflowStateManager(task_manager.db)
        reserved_slots = 0

        if parent_session_id:
            reserved_slots = state_manager.check_and_reserve_slots(
                parent_session_id,
                max_concurrent=max_concurrent,
                requested=len(ready_tasks),
            )
        else:
            # No parent session — fall back to non-atomic check
            from gobby.storage.worktrees import WorktreeStatus

            active_worktrees = worktree_storage.list_worktrees(
                project_id=resolved_project_id,
                status=WorktreeStatus.ACTIVE.value,
            )
            current_running = sum(1 for wt in active_worktrees if wt.agent_session_id)
            reserved_slots = max(0, min(len(ready_tasks), max_concurrent - current_running))

        if reserved_slots == 0:
            return {
                "success": True,
                "message": f"Max concurrent limit reached ({max_concurrent} agents running)",
                "spawned": [],
                "skipped": [
                    {"task_id": t.id, "reason": "max_concurrent limit reached"} for t in ready_tasks
                ],
            }

        # Limit to reserved slots
        tasks_to_spawn = ready_tasks[:reserved_slots]
        tasks_skipped = ready_tasks[reserved_slots:]

        # Resolve effective provider and model for implementation tasks
        # Priority: explicit parameter > workflow variable > default
        workflow_vars: dict[str, Any] = {}
        if parent_session_id:
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

        # Dry run: return the plan without spawning
        if dry_run:
            planned = [
                {
                    "task_id": task.id,
                    "title": task.title,
                    "category": task.category,
                    "prompt": _build_task_prompt(task),
                    "provider": effective_provider,
                    "model": effective_model,
                    "mode": mode,
                    "workflow": workflow,
                }
                for task in tasks_to_spawn
            ]

            # Release reserved slots since we're not actually spawning
            if parent_session_id:
                state_manager.release_reserved_slots(parent_session_id, reserved_slots)

            return {
                "success": True,
                "dry_run": True,
                "parent_task_id": resolved_parent_task_id,
                "planned": planned,
                "skipped": skipped,
                "planned_count": len(planned),
                "skipped_count": len(skipped),
                "max_concurrent": max_concurrent,
                "effective_provider": effective_provider,
                "effective_model": effective_model,
            }

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

        def _spawn_in_mode(
            task: Task,
            worktree: Any,
            child_session: Any,
            agent_run: Any,
            newly_created_worktree: bool,
            prompt: str,
            effective_provider: str,
            effective_terminal: str,
            mode: str,
        ) -> dict[str, Any] | None:
            """Spawn agent in the configured mode.

            Returns spawn info dict on success, or None on failure
            (appends to ``skipped`` as a side effect).
            """
            from gobby.agents.spawn import EmbeddedSpawner, HeadlessSpawner, TerminalSpawner
            from gobby.agents.spawners.base import EmbeddedPTYResult, HeadlessResult, SpawnResult

            # Ensure agent_runner is available (checked in orchestrate_ready_tasks)
            if agent_runner is None:
                raise RuntimeError("agent_runner is None in _spawn_in_mode")

            common_kwargs: dict[str, Any] = {
                "cli": effective_provider,
                "cwd": worktree.worktree_path,
                "session_id": child_session.id,
                "parent_session_id": parent_session_id,
                "agent_run_id": agent_run.id,
                "project_id": resolved_project_id,
                "workflow_name": workflow,
                "agent_depth": child_session.agent_depth,
                "max_agent_depth": agent_runner.child_session_manager.max_agent_depth,
                "prompt": prompt,
            }

            result: SpawnResult | EmbeddedPTYResult | HeadlessResult
            if mode == "terminal":
                common_kwargs["terminal"] = effective_terminal
                result = TerminalSpawner().spawn_agent(**common_kwargs)
            elif mode == "embedded":
                result = EmbeddedSpawner().spawn_agent(**common_kwargs)
            else:
                result = HeadlessSpawner().spawn_agent(**common_kwargs)

            if not result.success:
                worktree_storage.release(worktree.id)
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
                        "reason": result.error or f"{mode.title()} spawn failed",
                    }
                )
                return None

            task_manager.update_task(task.id, status="in_progress")

            info: dict[str, Any] = {
                "task_id": task.id,
                "title": task.title,
                "agent_id": agent_run.id,
                "session_id": child_session.id,
                "worktree_id": worktree.id,
                "branch_name": worktree.branch_name,
                "worktree_path": worktree.worktree_path,
            }
            if hasattr(result, "terminal_type") and result.terminal_type:
                info["terminal_type"] = result.terminal_type
            if result.pid is not None:
                info["pid"] = result.pid
            return info

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
                    is_valid, error_msg = workflow_loader.validate_workflow_for_agent_sync(
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

                # Spawn agent in the configured mode
                spawn_info = _spawn_in_mode(
                    task,
                    worktree,
                    child_session,
                    agent_run,
                    newly_created_worktree,
                    prompt,
                    effective_provider,
                    effective_terminal,
                    mode,
                )
                if spawn_info is None:
                    continue
                spawned.append(spawn_info)

            except Exception as e:
                logger.exception(f"Error orchestrating task {task.id}")
                skipped.append(
                    {
                        "task_id": task.id,
                        "title": task.title,
                        "reason": str(e),
                    }
                )

        # Atomically append spawned agents and release reserved slots
        if parent_session_id:
            try:
                state_manager.update_orchestration_lists(
                    parent_session_id,
                    append_to_spawned=spawned or None,
                )
                if spawned:
                    logger.info(
                        f"Appended {len(spawned)} agents to spawned_agents in workflow state"
                    )
            except Exception as e:
                logger.warning(f"Failed to update workflow state: {e}")
            finally:
                # Release all reserved slots — spawned agents are now tracked
                # in spawned_agents list, failed ones weren't added
                state_manager.release_reserved_slots(parent_session_id, reserved_slots)

        return {
            "success": True,
            "parent_task_id": resolved_parent_task_id,
            "spawned": spawned,
            "skipped": skipped,
            "spawned_count": len(spawned),
            "skipped_count": len(skipped),
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
                    "description": "Fallback LLM provider (claude, gemini, codex, antigravity, cursor, windsurf, copilot)",
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
                "dry_run": {
                    "type": "boolean",
                    "description": (
                        "If true, resolve tasks and check capacity but don't spawn. "
                        "Returns the plan showing what would be spawned."
                    ),
                    "default": False,
                },
            },
            "required": ["parent_task_id", "parent_session_id"],
        },
        func=orchestrate_ready_tasks,
    )


def _build_task_prompt(task: Task) -> str:
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
