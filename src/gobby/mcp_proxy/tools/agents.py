"""
Internal MCP tools for Gobby Agent System.

Exposes functionality for:
- Starting agents (spawn subagents with prompts)
- Getting agent results (retrieve completed run output)
- Listing agents (view runs for a session)
- Cancelling agents (stop running agents)

These tools are registered with the InternalToolRegistry and accessed
via the downstream proxy pattern (call_tool, list_tools, get_tool_schema).
"""

from __future__ import annotations

import socket
from typing import TYPE_CHECKING, Any

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.utils.project_context import get_project_context

if TYPE_CHECKING:
    from gobby.agents.runner import AgentRunner
    from gobby.llm.executor import ToolResult


def create_agents_registry(
    runner: AgentRunner,
    get_session_context: Any | None = None,
) -> InternalToolRegistry:
    """
    Create an agent tool registry with all agent-related tools.

    Args:
        runner: AgentRunner instance for executing agents.
        get_session_context: Optional callable returning current session context.

    Returns:
        InternalToolRegistry with all agent tools registered.
    """
    registry = InternalToolRegistry(
        name="gobby-agents",
        description="Agent spawning - start, monitor, and manage subagents",
    )

    @registry.tool(
        name="start_agent",
        description=(
            "Spawn a subagent to execute a task. Infers context from current project/session. "
            "Use get_agent_result to poll for completion."
        ),
    )
    async def start_agent(
        prompt: str,
        workflow: str | None = None,
        task: str | None = None,
        session_context: str = "summary_markdown",
        mode: str = "in_process",
        terminal: str = "auto",
        provider: str | None = None,
        model: str | None = None,
        worktree_id: str | None = None,
        timeout: float = 120.0,
        max_turns: int = 10,
        # Optional explicit context (usually inferred)
        parent_session_id: str | None = None,
        project_id: str | None = None,
        machine_id: str | None = None,
        source: str = "claude",
    ) -> dict[str, Any]:
        """
        Start a new agent to execute a task.

        Args:
            prompt: The task/prompt for the agent.
            workflow: Workflow name or path to execute.
            task: Task ID or 'next' for auto-select.
            session_context: Context source (summary_markdown, compact_markdown,
                           session_id:<id>, transcript:<n>, file:<path>).
            mode: Execution mode (in_process, terminal, embedded, headless).
            terminal: Terminal for terminal/embedded modes (auto, ghostty, iterm, etc.).
            provider: LLM provider (claude, gemini, etc.). Defaults to claude.
            model: Optional model override.
            worktree_id: Existing worktree to use for terminal mode.
            timeout: Execution timeout in seconds (default: 120).
            max_turns: Maximum turns (default: 10).
            parent_session_id: Explicit parent session ID (usually inferred).
            project_id: Explicit project ID (usually inferred from context).
            machine_id: Explicit machine ID (usually inferred from hostname).
            source: CLI source (claude, gemini, codex).

        Returns:
            Dict with run_id, child_session_id, status.
        """
        from gobby.agents.runner import AgentConfig

        # Validate mode
        supported_modes = {"in_process"}
        if mode not in supported_modes:
            return {
                "success": False,
                "error": f"Mode '{mode}' not yet implemented. Supported: {supported_modes}",
            }

        # Infer context from project if not provided
        if project_id is None:
            ctx = get_project_context()
            if ctx:
                project_id = ctx.get("id")
                project_path = ctx.get("project_path")
            else:
                return {
                    "success": False,
                    "error": "No project context found. Run from a Gobby project directory.",
                }
        else:
            project_path = None

        # Infer machine_id from hostname if not provided
        if machine_id is None:
            machine_id = socket.gethostname()

        # Parent session is required for depth checking
        if parent_session_id is None:
            # TODO: In future, could look up current active session for project
            return {
                "success": False,
                "error": "parent_session_id is required (session context inference not yet implemented)",
            }

        # Check if spawning is allowed
        can_spawn, reason, _parent_depth = runner.can_spawn(parent_session_id)
        if not can_spawn:
            return {
                "success": False,
                "error": reason,
            }

        # Use provided provider or default
        effective_provider = provider or "claude"

        config = AgentConfig(
            prompt=prompt,
            parent_session_id=parent_session_id,
            project_id=project_id,
            machine_id=machine_id,
            source=source,
            workflow=workflow,
            task=task,
            session_context=session_context,
            mode=mode,
            terminal=terminal,
            worktree_id=worktree_id,
            provider=effective_provider,
            model=model,
            max_turns=max_turns,
            timeout=timeout,
            project_path=project_path,
        )

        # Create a simple tool handler that returns not implemented
        async def tool_handler(tool_name: str, arguments: dict[str, Any]) -> ToolResult:
            from gobby.llm.executor import ToolResult

            return ToolResult(
                tool_name=tool_name,
                success=False,
                error=f"Tool {tool_name} not available for this agent",
            )

        result = await runner.run(config, tool_handler=tool_handler)

        return {
            "success": result.status in ("success", "partial"),
            "run_id": result.run_id,
            "status": result.status,
            "output": result.output,
            "error": result.error,
            "turns_used": result.turns_used,
            "tool_calls_count": len(result.tool_calls),
        }

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
            return {
                "success": False,
                "error": f"Agent run {run_id} not found",
            }

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
        description="List agent runs for a session.",
    )
    async def list_agents(
        parent_session_id: str,
        status: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """
        List agent runs for a session.

        Args:
            parent_session_id: The parent session ID.
            status: Optional status filter (pending, running, success, error, timeout, cancelled).
            limit: Maximum results (default: 20).

        Returns:
            Dict with list of agent runs.
        """
        runs = runner.list_runs(parent_session_id, status=status, limit=limit)

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
        name="cancel_agent",
        description="Cancel a running agent.",
    )
    async def cancel_agent(run_id: str) -> dict[str, Any]:
        """
        Cancel a running agent.

        Args:
            run_id: The agent run ID to cancel.

        Returns:
            Dict with success status.
        """
        success = runner.cancel_run(run_id)
        if success:
            return {
                "success": True,
                "message": f"Agent run {run_id} cancelled",
            }
        else:
            run = runner.get_run(run_id)
            if not run:
                return {
                    "success": False,
                    "error": f"Agent run {run_id} not found",
                }
            else:
                return {
                    "success": False,
                    "error": f"Cannot cancel agent in status: {run.status}",
                }

    @registry.tool(
        name="can_spawn_agent",
        description="Check if an agent can be spawned from the current session.",
    )
    async def can_spawn_agent(parent_session_id: str) -> dict[str, Any]:
        """
        Check if an agent can be spawned from the given session.

        This checks the agent depth limit to prevent infinite nesting.

        Args:
            parent_session_id: The session that would spawn the agent.

        Returns:
            Dict with can_spawn boolean and reason.
        """
        can_spawn, reason, _parent_depth = runner.can_spawn(parent_session_id)
        return {
            "can_spawn": can_spawn,
            "reason": reason,
        }

    return registry
