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

import logging
import socket
from pathlib import Path
from typing import TYPE_CHECKING, Any

from gobby.agents.context import (
    ContextResolutionError,
    ContextResolver,
    format_injected_prompt,
)
from gobby.agents.registry import (
    RunningAgent,
    RunningAgentRegistry,
    get_running_agent_registry,
)
from gobby.agents.spawn import (
    EmbeddedSpawner,
    HeadlessSpawner,
    SpawnMode,
    TerminalSpawner,
)
from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.utils.project_context import get_project_context

if TYPE_CHECKING:
    from gobby.agents.runner import AgentRunner
    from gobby.config.app import ContextInjectionConfig
    from gobby.llm.executor import ToolResult
    from gobby.storage.session_messages import LocalSessionMessageManager
    from gobby.storage.sessions import LocalSessionManager

logger = logging.getLogger(__name__)


def create_agents_registry(
    runner: AgentRunner,
    session_manager: LocalSessionManager | None = None,
    message_manager: LocalSessionMessageManager | None = None,
    context_config: ContextInjectionConfig | None = None,
    get_session_context: Any | None = None,
    running_registry: RunningAgentRegistry | None = None,
) -> InternalToolRegistry:
    """
    Create an agent tool registry with all agent-related tools.

    Args:
        runner: AgentRunner instance for executing agents.
        session_manager: Session manager for context resolution.
        message_manager: Message manager for transcript resolution.
        context_config: Context injection configuration.
        get_session_context: Optional callable returning current session context.
        running_registry: Optional in-memory registry for running agents.

    Returns:
        InternalToolRegistry with all agent tools registered.
    """
    registry = InternalToolRegistry(
        name="gobby-agents",
        description="Agent spawning - start, monitor, and manage subagents",
    )

    # Use provided registry or global singleton
    agent_registry = running_registry or get_running_agent_registry()

    # Create context resolver if managers are provided
    context_resolver: ContextResolver | None = None
    context_enabled = True  # Default enabled
    context_template: str | None = None  # Custom template for injection
    if session_manager and message_manager:
        # Use config values if provided, otherwise use defaults
        if context_config:
            context_enabled = context_config.enabled
            context_template = context_config.context_template
            context_resolver = ContextResolver(
                session_manager=session_manager,
                message_manager=message_manager,
                project_path=None,  # Will be set per-request
                max_file_size=context_config.max_file_size,
                max_content_size=context_config.max_content_size,
                max_transcript_messages=context_config.max_transcript_messages,
                truncation_suffix=context_config.truncation_suffix,
            )
        else:
            context_resolver = ContextResolver(
                session_manager=session_manager,
                message_manager=message_manager,
                project_path=None,  # Will be set per-request
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
        supported_modes = {"in_process", "terminal", "embedded", "headless"}
        if mode not in supported_modes:
            return {
                "success": False,
                "error": f"Invalid mode '{mode}'. Supported: {supported_modes}",
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

        # Resolve context and inject into prompt
        effective_prompt = prompt
        context_was_injected = False
        if context_resolver and context_enabled and session_context:
            try:
                # Update resolver's project path for file resolution
                context_resolver._project_path = Path(project_path) if project_path else None

                resolved_context = await context_resolver.resolve(
                    session_context, parent_session_id
                )
                if resolved_context:
                    effective_prompt = format_injected_prompt(
                        resolved_context, prompt, template=context_template
                    )
                    context_was_injected = True
                    logger.info(
                        f"Injected context from '{session_context}' into agent prompt "
                        f"({len(resolved_context)} chars)"
                    )
            except ContextResolutionError as e:
                logger.warning(f"Context resolution failed: {e}")
                # Continue with original prompt - context injection is best-effort
                pass

        # Use provided provider or default
        effective_provider = provider or "claude"

        config = AgentConfig(
            prompt=effective_prompt,
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
            context_injected=context_was_injected,
        )

        # Handle different execution modes
        if mode == "in_process":
            # In-process mode: run directly via runner
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

        # Terminal, embedded, or headless mode: prepare run then spawn
        # Use prepare_run to create session and run records
        from gobby.agents.runner import AgentResult

        prepare_result = runner.prepare_run(config)
        if isinstance(prepare_result, AgentResult):
            # prepare_run returns AgentResult on error
            return {
                "success": False,
                "error": prepare_result.error,
            }

        # Successfully prepared - we have context with session and run
        context = prepare_result

        # Determine working directory
        cwd = project_path or "."

        if mode == "terminal":
            # Spawn in external terminal
            spawner = TerminalSpawner()
            spawn_result = spawner.spawn_agent(
                cli=effective_provider,  # claude, gemini, codex
                cwd=cwd,
                session_id=context.session.id,
                parent_session_id=parent_session_id,
                agent_run_id=context.run.id,
                project_id=project_id,
                workflow_name=workflow,
                agent_depth=context.session.agent_depth,
                max_agent_depth=runner._child_session_manager.max_agent_depth,
                terminal=terminal,
                prompt=effective_prompt,
            )

            if not spawn_result.success:
                return {
                    "success": False,
                    "error": spawn_result.error or spawn_result.message,
                    "run_id": context.run.id,
                    "child_session_id": context.session.id,
                }

            # Register in running agents registry
            running_agent = RunningAgent(
                run_id=context.run.id,
                session_id=context.session.id,
                parent_session_id=parent_session_id,
                mode="terminal",
                pid=spawn_result.pid,
                terminal_type=spawn_result.terminal_type,
                provider=effective_provider,
                workflow_name=workflow,
                worktree_id=worktree_id,
            )
            agent_registry.add(running_agent)

            return {
                "success": True,
                "run_id": context.run.id,
                "child_session_id": context.session.id,
                "status": "pending",
                "message": f"Agent spawned in {spawn_result.terminal_type} (PID: {spawn_result.pid})",
                "terminal_type": spawn_result.terminal_type,
                "pid": spawn_result.pid,
            }

        elif mode == "embedded":
            # Spawn with PTY for UI attachment
            spawner = EmbeddedSpawner()
            spawn_result = spawner.spawn_agent(
                cli=effective_provider,
                cwd=cwd,
                session_id=context.session.id,
                parent_session_id=parent_session_id,
                agent_run_id=context.run.id,
                project_id=project_id,
                workflow_name=workflow,
                agent_depth=context.session.agent_depth,
                max_agent_depth=runner._child_session_manager.max_agent_depth,
                prompt=effective_prompt,
            )

            if not spawn_result.success:
                return {
                    "success": False,
                    "error": spawn_result.error or spawn_result.message,
                    "run_id": context.run.id,
                    "child_session_id": context.session.id,
                }

            # Register in running agents registry
            running_agent = RunningAgent(
                run_id=context.run.id,
                session_id=context.session.id,
                parent_session_id=parent_session_id,
                mode="embedded",
                pid=spawn_result.pid,
                master_fd=spawn_result.master_fd,
                provider=effective_provider,
                workflow_name=workflow,
                worktree_id=worktree_id,
            )
            agent_registry.add(running_agent)

            return {
                "success": True,
                "run_id": context.run.id,
                "child_session_id": context.session.id,
                "status": "pending",
                "message": f"Agent spawned with PTY (PID: {spawn_result.pid})",
                "pid": spawn_result.pid,
                "master_fd": spawn_result.master_fd,
            }

        else:  # headless mode
            # Spawn headless with output capture
            spawner = HeadlessSpawner()
            spawn_result = spawner.spawn_agent(
                cli=effective_provider,
                cwd=cwd,
                session_id=context.session.id,
                parent_session_id=parent_session_id,
                agent_run_id=context.run.id,
                project_id=project_id,
                workflow_name=workflow,
                agent_depth=context.session.agent_depth,
                max_agent_depth=runner._child_session_manager.max_agent_depth,
                prompt=effective_prompt,
            )

            if not spawn_result.success:
                return {
                    "success": False,
                    "error": spawn_result.error or spawn_result.message,
                    "run_id": context.run.id,
                    "child_session_id": context.session.id,
                }

            # Register in running agents registry
            running_agent = RunningAgent(
                run_id=context.run.id,
                session_id=context.session.id,
                parent_session_id=parent_session_id,
                mode="headless",
                pid=spawn_result.pid,
                provider=effective_provider,
                workflow_name=workflow,
                worktree_id=worktree_id,
            )
            agent_registry.add(running_agent)

            return {
                "success": True,
                "run_id": context.run.id,
                "child_session_id": context.session.id,
                "status": "pending",
                "message": f"Agent spawned headless (PID: {spawn_result.pid})",
                "pid": spawn_result.pid,
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
            # Also remove from running agents registry
            agent_registry.remove(run_id)
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

    @registry.tool(
        name="list_running_agents",
        description="List all currently running agents (in-memory process state).",
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
            parent_session_id: Optional filter by parent session.
            mode: Optional filter by execution mode (terminal, embedded, headless).

        Returns:
            Dict with list of running agents.
        """
        if parent_session_id:
            agents = agent_registry.list_by_parent(parent_session_id)
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
            return {
                "success": False,
                "error": f"No running agent found with ID {run_id}",
            }

        return {
            "success": True,
            "agent": agent.to_dict(),
        }

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
            return {
                "success": True,
                "message": f"Unregistered agent {run_id}",
            }
        else:
            return {
                "success": False,
                "error": f"No running agent found with ID {run_id}",
            }

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

    return registry
