"""
Internal MCP tools for Gobby Agent System.

Exposes functionality for:
- Spawning agents (via spawn_agent unified tool)
- Getting agent results (retrieve completed run output)
- Listing agents (view runs for a session)
- Cancelling agents (stop running agents)

These tools are registered with the InternalToolRegistry and accessed
via the downstream proxy pattern (call_tool, list_tools, get_tool_schema).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from gobby.agents.registry import (
    RunningAgentRegistry,
    get_running_agent_registry,
)
from gobby.mcp_proxy.tools.internal import InternalToolRegistry

if TYPE_CHECKING:
    from gobby.agents.runner import AgentRunner

logger = logging.getLogger(__name__)


def create_agents_registry(
    runner: AgentRunner,
    running_registry: RunningAgentRegistry | None = None,
    workflow_state_manager: Any | None = None,
    session_manager: Any | None = None,
    # spawn_agent dependencies
    agent_loader: Any | None = None,
    task_manager: Any | None = None,
    worktree_storage: Any | None = None,
    git_manager: Any | None = None,
    clone_storage: Any | None = None,
    clone_manager: Any | None = None,
    # For mode=self (workflow activation on caller session)
    workflow_loader: Any | None = None,
    db: Any | None = None,
) -> InternalToolRegistry:
    """
    Create an agent tool registry with all agent-related tools.

    Args:
        runner: AgentRunner instance for executing agents.
        running_registry: Optional in-memory registry for running agents.
        workflow_state_manager: Optional WorkflowStateManager for stopping workflows
            when agents are killed. If not provided, workflow stop will be skipped.
        session_manager: Optional LocalSessionManager for resolving session references.
        agent_loader: Agent definition loader for spawn_agent.
        task_manager: Task manager for spawn_agent task resolution.
        worktree_storage: Worktree storage for spawn_agent isolation.
        git_manager: Git manager for spawn_agent isolation.
        clone_storage: Clone storage for spawn_agent isolation.
        clone_manager: Clone git manager for spawn_agent isolation.

    Returns:
        InternalToolRegistry with all agent tools registered.
    """
    from gobby.utils.project_context import get_project_context

    def _resolve_session_id(ref: str) -> str:
        """Resolve session reference (#N, N, UUID, or prefix) to UUID."""
        if session_manager is None:
            return ref  # No resolution available, return as-is
        project_ctx = get_project_context()
        project_id = project_ctx.get("id") if project_ctx else None
        return str(session_manager.resolve_session_reference(ref, project_id))

    registry = InternalToolRegistry(
        name="gobby-agents",
        description="Agent spawning - start, monitor, and manage subagents",
    )

    # Use provided registry or global singleton
    agent_registry = running_registry or get_running_agent_registry()

    @registry.tool(
        name="get_agent_result",
        description="Get the result of a completed agent run.",
    )
    async def get_agent_result(run_id: str) -> dict[str, Any]:
        """
        Get the result of an agent run.

        Args:
            run_id: The agent run ID.

        Returns:
            Dict with run details including status, result, error.
        """
        run = runner.get_run(run_id)
        if not run:
            return {"success": False, "error": f"Agent run {run_id} not found"}

        return {
            "success": True,
            "run_id": run.id,
            "status": run.status,
            "result": run.result,
            "error": run.error,
            "provider": run.provider,
            "model": run.model,
            "prompt": run.prompt,
            "tool_calls_count": run.tool_calls_count,
            "turns_used": run.turns_used,
            "started_at": run.started_at,
            "completed_at": run.completed_at,
            "child_session_id": run.child_session_id,
        }

    @registry.tool(
        name="list_agents",
        description="List agent runs for a session. Accepts #N, N, UUID, or prefix for session_id.",
    )
    async def list_agents(
        parent_session_id: str,
        status: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """
        List agent runs for a session.

        Args:
            parent_session_id: Session reference (accepts #N, N, UUID, or prefix) for the parent.
            status: Optional status filter (pending, running, success, error, timeout, cancelled).
            limit: Maximum results (default: 20).

        Returns:
            Dict with list of agent runs.
        """
        # Resolve session_id to UUID (accepts #N, N, UUID, or prefix)
        try:
            resolved_parent_id = _resolve_session_id(parent_session_id)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        runs = runner.list_runs(resolved_parent_id, status=status, limit=limit)

        return {
            "success": True,
            "runs": [
                {
                    "id": run.id,
                    "status": run.status,
                    "provider": run.provider,
                    "model": run.model,
                    "workflow_name": run.workflow_name,
                    "prompt": run.prompt[:100] + "..." if len(run.prompt) > 100 else run.prompt,
                    "started_at": run.started_at,
                    "completed_at": run.completed_at,
                }
                for run in runs
            ],
            "count": len(runs),
        }

    @registry.tool(
        name="stop_agent",
        description="Stop a running agent (marks as cancelled in DB, does not kill process).",
    )
    async def stop_agent(run_id: str) -> dict[str, Any]:
        """
        Stop a running agent by marking it as cancelled.

        This only updates the database status - it does NOT kill the actual process.
        Use kill_agent to terminate the process.

        Args:
            run_id: The agent run ID to stop.

        Returns:
            Dict with success status.
        """
        success = runner.cancel_run(run_id)
        if success:
            # Also remove from running agents registry
            agent_registry.remove(run_id)
            return {"success": True, "message": f"Agent run {run_id} stopped"}
        else:
            run = runner.get_run(run_id)
            if not run:
                return {"success": False, "error": f"Agent run {run_id} not found"}
            else:
                return {"success": False, "error": f"Cannot stop agent in status: {run.status}"}

    @registry.tool(
        name="kill_agent",
        description=(
            "Kill a running agent process and close its terminal. "
            "Use run_id (parent kills child) or session_id (self-termination)."
        ),
    )
    async def kill_agent(
        run_id: str | None = None,
        session_id: str | None = None,
        signal: str = "TERM",
        force: bool = False,
        debug: bool = False,
    ) -> dict[str, Any]:
        """
        Kill a running agent process.

        This terminates the process, closes the terminal, and cleans up workflow state.
        Can be called by parent (using run_id) or by the agent itself (using session_id).

        Args:
            run_id: Agent run ID (for parent killing child)
            session_id: Session ID of the agent (for self-termination). Accepts #N, N, UUID, or prefix.
            signal: Signal to send (TERM, KILL, INT, HUP, QUIT). Default: TERM
            force: Use SIGKILL immediately (equivalent to signal="KILL")
            debug: If True, kill agent process but preserve workflow state and leave
                terminal open for inspection. Default: False (full cleanup).

        Returns:
            Dict with success status and kill details.
        """
        if force:
            signal = "KILL"

        # Validate signal against allowlist to prevent injection
        signal = signal.upper()
        allowed_signals = {"TERM", "KILL", "INT", "HUP", "QUIT"}
        if signal not in allowed_signals:
            return {
                "success": False,
                "error": f"Invalid signal '{signal}'. Allowed: {', '.join(sorted(allowed_signals))}",
            }

        # Resolve run_id from session_id if needed (self-termination case)
        resolved_session_id: str | None = None
        if run_id is None and session_id:
            # Resolve session_id (accepts #N, N, UUID, prefix)
            try:
                resolved_session_id = _resolve_session_id(session_id)
            except ValueError as e:
                return {"error": str(e)}

            # Try registry first (fast path)
            agent = agent_registry.get_by_session(resolved_session_id)
            if agent:
                run_id = agent.run_id
            else:
                # Fallback: query DB for agent run with this child_session_id
                run_id = runner.get_run_id_by_session(resolved_session_id)

            if not run_id:
                return {"success": False, "error": f"No agent found for session {session_id}"}

        if run_id is None:
            return {"success": False, "error": "Either run_id or session_id required"}

        # Get agent info before killing
        agent = agent_registry.get(run_id)
        agent_session_id = agent.session_id if agent else resolved_session_id

        # Database fallback: if not in registry, look up from DB
        if agent_session_id is None:
            db_run = runner.get_run(run_id)
            if db_run and db_run.child_session_id:
                agent_session_id = db_run.child_session_id

        # Default: full cleanup. debug=True preserves state/terminal for inspection.
        close_terminal = not debug

        result = await agent_registry.kill(
            run_id,
            signal_name=signal,
            close_terminal=close_terminal,
        )

        if result.get("success"):
            # Update database status
            runner.cancel_run(run_id)

            # Delete workflow state unless debugging
            if not debug and agent_session_id:
                if workflow_state_manager is not None:
                    try:
                        workflow_state_manager.delete_state(agent_session_id)
                        result["workflow_deleted"] = True
                    except Exception as e:
                        result["workflow_delete_error"] = str(e)

                # Mark session as 'expired' so transcript gets processed
                # (Gemini sessions don't transition to expired via normal flow)
                if session_manager is not None:
                    try:
                        session_manager.update_status(agent_session_id, "expired")
                        result["session_expired"] = True
                    except Exception as e:
                        result["session_expire_error"] = str(e)

        return result

    @registry.tool(
        name="can_spawn_agent",
        description="Check if an agent can be spawned from the current session. Accepts #N, N, UUID, or prefix for session_id.",
    )
    async def can_spawn_agent(parent_session_id: str) -> dict[str, Any]:
        """
        Check if an agent can be spawned from the given session.

        This checks the agent depth limit to prevent infinite nesting.

        Args:
            parent_session_id: Session reference (accepts #N, N, UUID, or prefix) for the session that would spawn the agent.

        Returns:
            Dict with can_spawn boolean and reason.
        """
        # Resolve session_id to UUID (accepts #N, N, UUID, or prefix)
        try:
            resolved_parent_id = _resolve_session_id(parent_session_id)
        except ValueError as e:
            return {"success": False, "can_spawn": False, "reason": str(e)}

        can_spawn, reason, _parent_depth = runner.can_spawn(resolved_parent_id)
        return {
            "success": True,
            "can_spawn": can_spawn,
            "reason": reason,
        }

    @registry.tool(
        name="list_running_agents",
        description="List all currently running agents (in-memory process state). Accepts #N, N, UUID, or prefix for session_id.",
    )
    async def list_running_agents(
        parent_session_id: str | None = None,
        mode: str | None = None,
    ) -> dict[str, Any]:
        """
        List all currently running agents.

        This returns in-memory process state for agents that are actively running,
        including PIDs and process handles not stored in the database.

        Args:
            parent_session_id: Optional session reference (accepts #N, N, UUID, or prefix) to filter by parent.
            mode: Optional filter by execution mode (terminal, embedded, headless).

        Returns:
            Dict with list of running agents.
        """
        if parent_session_id:
            # Resolve session_id to UUID (accepts #N, N, UUID, or prefix)
            try:
                resolved_parent_id = _resolve_session_id(parent_session_id)
            except ValueError as e:
                return {"success": False, "error": str(e)}
            agents = agent_registry.list_by_parent(resolved_parent_id)
        elif mode:
            agents = agent_registry.list_by_mode(mode)
        else:
            agents = agent_registry.list_all()

        return {
            "success": True,
            "agents": [agent.to_dict() for agent in agents],
            "count": len(agents),
        }

    @registry.tool(
        name="get_running_agent",
        description="Get in-memory process state for a running agent.",
    )
    async def get_running_agent(run_id: str) -> dict[str, Any]:
        """
        Get the in-memory state for a running agent.

        This returns process information like PID and PTY fd that aren't
        stored in the database.

        Args:
            run_id: The agent run ID.

        Returns:
            Dict with running agent details.
        """
        agent = agent_registry.get(run_id)
        if not agent:
            return {"success": False, "error": f"No running agent found with ID {run_id}"}

        return {"success": True, "agent": agent.to_dict()}

    @registry.tool(
        name="unregister_agent",
        description="Remove an agent from the in-memory running registry (internal use).",
    )
    async def unregister_agent(run_id: str) -> dict[str, Any]:
        """
        Remove an agent from the running registry.

        This is typically called automatically when a session ends,
        but can be called manually for cleanup.

        Args:
            run_id: The agent run ID to unregister.

        Returns:
            Dict with success status.
        """
        removed = agent_registry.remove(run_id)
        if removed:
            return {"success": True, "message": f"Unregistered agent {run_id}"}
        else:
            return {"success": False, "error": f"No running agent found with ID {run_id}"}

    @registry.tool(
        name="running_agent_stats",
        description="Get statistics about running agents.",
    )
    async def running_agent_stats() -> dict[str, Any]:
        """
        Get statistics about running agents.

        Returns:
            Dict with counts by mode and parent.
        """
        all_agents = agent_registry.list_all()
        by_mode: dict[str, int] = {}
        by_parent: dict[str, int] = {}

        for agent in all_agents:
            by_mode[agent.mode] = by_mode.get(agent.mode, 0) + 1
            by_parent[agent.parent_session_id] = by_parent.get(agent.parent_session_id, 0) + 1

        return {
            "success": True,
            "total": len(all_agents),
            "by_mode": by_mode,
            "by_parent_count": len(by_parent),
        }

    @registry.tool(
        name="evaluate_spawn",
        description="Dry-run evaluation of spawn_agent — checks agent, workflow, isolation, and runtime without executing.",
    )
    async def evaluate_spawn_tool(
        agent: str = "generic",
        workflow: str | None = None,
        task_id: str | None = None,
        isolation: str | None = None,
        mode: str | None = None,
        terminal: str = "auto",
        provider: str | None = None,
        branch_name: str | None = None,
        base_branch: str | None = None,
        parent_session_id: str | None = None,
        project_path: str | None = None,
    ) -> dict[str, Any]:
        """
        Dry-run evaluation of spawn_agent.

        Simulates the spawn process and reports what would happen,
        including any misconfigurations, without actually spawning.

        Args:
            agent: Agent name (default: "generic").
            workflow: Optional workflow name override.
            task_id: Optional task ID for branch naming.
            isolation: Optional isolation mode (current, worktree, clone).
            mode: Optional execution mode (terminal, embedded, headless, self).
            terminal: Terminal type (default: auto).
            provider: Optional provider override.
            branch_name: Optional explicit branch name.
            base_branch: Optional base branch for isolation.
            parent_session_id: Optional parent session for depth checks.
            project_path: Optional project path.

        Returns:
            Dict with evaluation results including can_spawn, items, and workflow_evaluation.
        """
        from gobby.agents.dry_run import evaluate_spawn

        # Resolve parent session if provided
        resolved_parent = None
        if parent_session_id:
            try:
                resolved_parent = _resolve_session_id(parent_session_id)
            except ValueError:
                resolved_parent = parent_session_id

        # Get project path from context if not provided
        if not project_path:
            project_ctx = get_project_context()
            if project_ctx:
                project_path = project_ctx.get("project_path")

        # Get MCP manager from runner if available
        mcp_mgr = getattr(runner, "_mcp_manager", None)

        eval_result = await evaluate_spawn(
            agent=agent,
            workflow=workflow,
            task_id=task_id,
            isolation=isolation,
            mode=mode,
            terminal=terminal,
            provider=provider,
            branch_name=branch_name,
            base_branch=base_branch,
            parent_session_id=resolved_parent,
            project_path=project_path,
            agent_loader=agent_loader,
            workflow_loader=workflow_loader,
            runner=runner,
            state_manager=workflow_state_manager,
            session_manager=session_manager,
            git_manager=git_manager,
            worktree_storage=worktree_storage,
            clone_storage=clone_storage,
            clone_manager=clone_manager,
            task_manager=task_manager,
            mcp_manager=mcp_mgr,
        )
        return eval_result.to_dict()

    @registry.tool(
        name="wait_for_agent",
        description=(
            "Wait for an agent run to complete. "
            "Blocks until the agent reaches a terminal status (success, error, timeout, cancelled), "
            "or the wait timeout expires."
        ),
    )
    async def wait_for_agent(
        run_id: str,
        timeout: int = 600,
        poll_interval: int = 10,
    ) -> dict[str, Any]:
        """
        Wait for an agent run to complete.

        Polls the agent run status until it is no longer pending/running, or timeout expires.

        Args:
            run_id: The agent run ID to wait for.
            timeout: Maximum wait time in seconds (default: 600).
            poll_interval: Time between status checks in seconds (default: 10).

        Returns:
            Dict with:
            - completed: Whether the agent reached a terminal status
            - status: Final agent status
            - run_id: The agent run ID
            - timed_out: Whether the wait timed out
            - wait_time: How long we waited
        """
        import asyncio
        import time

        if poll_interval <= 0:
            poll_interval = 10

        start_time = time.monotonic()

        # Check initial state
        run = runner.get_run(run_id)
        if not run:
            return {"success": False, "error": f"Agent run {run_id} not found"}

        terminal_statuses = {"success", "error", "timeout", "cancelled"}

        if run.status in terminal_statuses:
            return {
                "completed": True,
                "status": run.status,
                "run_id": run_id,
                "timed_out": False,
                "wait_time": 0.0,
            }

        # Poll until complete or timeout
        while True:
            elapsed = time.monotonic() - start_time

            if elapsed >= timeout:
                # Re-fetch to get latest status
                run = runner.get_run(run_id)
                return {
                    "completed": False,
                    "status": run.status if run else "unknown",
                    "run_id": run_id,
                    "timed_out": True,
                    "wait_time": elapsed,
                }

            await asyncio.sleep(poll_interval)

            run = runner.get_run(run_id)
            if not run:
                return {
                    "completed": False,
                    "status": "unknown",
                    "run_id": run_id,
                    "timed_out": False,
                    "wait_time": time.monotonic() - start_time,
                    "error": "Agent run disappeared during wait",
                }

            if run.status in terminal_statuses:
                return {
                    "completed": True,
                    "status": run.status,
                    "run_id": run_id,
                    "timed_out": False,
                    "wait_time": time.monotonic() - start_time,
                }

    # Register spawn_agent tool from spawn_agent module
    from gobby.mcp_proxy.tools.spawn_agent import create_spawn_agent_registry

    spawn_registry = create_spawn_agent_registry(
        runner=runner,
        agent_loader=agent_loader,
        task_manager=task_manager,
        worktree_storage=worktree_storage,
        git_manager=git_manager,
        clone_storage=clone_storage,
        clone_manager=clone_manager,
        session_manager=session_manager,
        workflow_loader=workflow_loader,
        # For mode=self (workflow activation on caller session)
        state_manager=workflow_state_manager,
        db=db,
    )

    # Merge spawn_agent tools into agents registry
    for tool_name, tool in spawn_registry._tools.items():
        registry._tools[tool_name] = tool

    return registry
