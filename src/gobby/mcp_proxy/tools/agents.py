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

from typing import TYPE_CHECKING, Any

from gobby.mcp_proxy.tools.internal import InternalToolRegistry

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
            "Spawn a subagent to execute a task. Returns immediately with run ID. "
            "Use get_agent_result to poll for completion."
        ),
    )
    async def start_agent(
        prompt: str,
        parent_session_id: str,
        project_id: str,
        machine_id: str,
        source: str = "claude",
        provider: str = "claude",
        model: str | None = None,
        workflow_name: str | None = None,
        system_prompt: str | None = None,
        max_turns: int = 10,
        timeout: float = 120.0,
        title: str | None = None,
        git_branch: str | None = None,
    ) -> dict[str, Any]:
        """
        Start a new agent to execute a task.

        Args:
            prompt: The task/prompt for the agent.
            parent_session_id: ID of the session spawning this agent.
            project_id: Project ID for the agent's session.
            machine_id: Machine identifier.
            source: CLI source (claude, gemini, codex).
            provider: LLM provider (claude, gemini, etc.).
            model: Optional model override.
            workflow_name: Optional workflow to execute.
            system_prompt: Optional system prompt override.
            max_turns: Maximum turns (default: 10).
            timeout: Execution timeout in seconds (default: 120).
            title: Optional title for the agent session.
            git_branch: Git branch for the session.

        Returns:
            Dict with run_id, child_session_id, status.
        """
        from gobby.agents.runner import AgentConfig

        # Check if spawning is allowed
        can_spawn, reason, _parent_depth = runner.can_spawn(parent_session_id)
        if not can_spawn:
            return {
                "success": False,
                "error": reason,
            }

        config = AgentConfig(
            prompt=prompt,
            parent_session_id=parent_session_id,
            project_id=project_id,
            machine_id=machine_id,
            source=source,
            provider=provider,
            model=model,
            workflow_name=workflow_name,
            system_prompt=system_prompt,
            max_turns=max_turns,
            timeout=timeout,
            title=title,
            git_branch=git_branch,
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
