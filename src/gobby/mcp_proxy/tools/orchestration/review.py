"""Task orchestration tools: review (spawn_review_agent, process_completed_agents)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Literal

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.storage.tasks import TaskNotFoundError

from .utils import get_current_project_id

if TYPE_CHECKING:
    from gobby.agents.runner import AgentRunner
    from gobby.storage.tasks import LocalTaskManager
    from gobby.storage.worktrees import LocalWorktreeManager

logger = logging.getLogger(__name__)


def register_reviewer(
    registry: InternalToolRegistry,
    task_manager: LocalTaskManager,
    worktree_storage: LocalWorktreeManager,
    agent_runner: AgentRunner | None = None,
    default_project_id: str | None = None,
) -> None:
    """Register review tools."""
    from gobby.mcp_proxy.tools.tasks import resolve_task_id_for_mcp

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
        # Validate mode and review_provider
        allowed_modes = {"terminal", "embedded", "headless"}
        allowed_providers = {"claude", "gemini", "codex", "antigravity"}

        mode_lower = mode.lower() if mode else "terminal"
        if mode_lower not in allowed_modes:
            return {
                "success": False,
                "error": f"Invalid mode '{mode}'. Must be one of: {sorted(allowed_modes)}",
            }
        mode = mode_lower  # Use normalized value

        if review_provider not in allowed_providers:
            return {
                "success": False,
                "error": f"Invalid review_provider '{review_provider}'. Must be one of: {sorted(allowed_providers)}",
            }

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

        # Get the task
        try:
            task = task_manager.get_task(resolved_task_id)
        except ValueError as e:
            return {
                "success": False,
                "error": f"Task {task_id} not found: {e}",
            }
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
                    "type": ["string", "null"],
                    "description": "Path to project directory",
                    "default": None,
                },
            },
            "required": ["task_id", "parent_session_id"],
        },
        func=spawn_review_agent,
    )

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

        # Defensive type coercion - ensure lists of dicts, handle None/wrong types
        def _safe_list_of_dicts(val: Any) -> list[dict[str, Any]]:
            """Coerce value to list of dicts, filtering out non-dict entries."""
            if not val:
                return []
            if not isinstance(val, list):
                return []
            return [x for x in val if isinstance(x, dict)]

        completed_agents = _safe_list_of_dicts(workflow_vars.get("completed_agents"))
        failed_agents = _safe_list_of_dicts(workflow_vars.get("failed_agents"))
        # Create a fresh list for newly reviewed agents to avoid aliasing the stored list
        newly_reviewed: list[dict[str, Any]] = []
        # Shallow copy to avoid aliasing
        review_agents_spawned = list(
            _safe_list_of_dicts(workflow_vars.get("review_agents_spawned"))
        )

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
            try:
                task = task_manager.get_task(task_id)
            except ValueError as e:
                escalated.append(
                    {
                        **agent_info,
                        "escalation_reason": f"Task lookup failed: {e}",
                    }
                )
                continue
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
                newly_reviewed.append(agent_info)
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
                newly_reviewed.append(agent_info)

        # Process failed agents
        still_failed: list[dict[str, Any]] = []

        for agent_info in failed_agents:
            task_id = agent_info.get("task_id")
            failure_reason = agent_info.get("failure_reason") or "Unknown"

            # Check if this is a retriable failure
            if "crashed" in failure_reason.lower() or "exited" in failure_reason.lower():
                # Potentially retriable - reopen task
                if task_id:
                    retry_task: Any = None
                    try:
                        retry_task = task_manager.get_task(task_id)
                    except ValueError:
                        # Task was deleted concurrently - skip
                        pass
                    if retry_task and retry_task.status == "in_progress":
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
                        except Exception as e:
                            # Task update failed - keep in still_failed for next cycle
                            still_failed.append(
                                {
                                    **agent_info,
                                    "pending_retry": True,
                                    "retry_error": str(e),
                                }
                            )
                            continue

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
                # Update reviewed_agents - copy existing to avoid aliasing, then extend
                existing_reviewed = list(state.variables.get("reviewed_agents", []))
                existing_reviewed.extend(newly_reviewed)
                state.variables["reviewed_agents"] = existing_reviewed
                # Update review_agents_spawned
                state.variables["review_agents_spawned"] = review_agents_spawned
                # Update failed_agents
                state.variables["failed_agents"] = still_failed
                # Track escalated agents
                existing_escalated = list(state.variables.get("escalated_agents", []))
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
                    "type": ["string", "null"],
                    "description": "LLM provider for reviews (uses workflow variable if not set)",
                    "default": None,
                },
                "review_model": {
                    "type": ["string", "null"],
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
                    "type": ["string", "null"],
                    "description": "Path to project directory",
                    "default": None,
                },
            },
            "required": ["parent_session_id"],
        },
        func=process_completed_agents,
    )


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
