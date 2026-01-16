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
from collections.abc import Callable
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
    TerminalSpawner,
)
from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.utils.project_context import get_project_context

if TYPE_CHECKING:
    from gobby.agents.runner import AgentRunner
    from gobby.config.app import ContextInjectionConfig
    from gobby.llm.executor import ToolResult
    from gobby.mcp_proxy.services.tool_proxy import ToolProxyService
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
    tool_proxy_getter: Callable[[], ToolProxyService | None] | None = None,
    workflow_state_manager: Any | None = None,
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
        tool_proxy_getter: Optional callable that returns ToolProxyService for
            routing tool calls in in-process agents. If not provided, tool calls
            will fail with "tool not available".
        workflow_state_manager: Optional WorkflowStateManager for stopping workflows
            when agents are killed. If not provided, workflow stop will be skipped.

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
            "Spawn a subagent to execute a task. Can use a named agent definition "
            "(e.g. 'validation-runner') or raw parameters. "
            "Infers context from current project/session. "
            "Use get_agent_result to poll for completion."
        ),
    )
    async def start_agent(
        prompt: str,
        workflow: str | None = None,
        task: str | None = None,
        agent: str | None = None,
        session_context: str = "summary_markdown",
        mode: str = "terminal",
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
            agent: Named agent definition to use.
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

        # Validate workflow (reject lifecycle workflows)
        if workflow:
            from gobby.workflows.loader import WorkflowLoader

            workflow_loader = WorkflowLoader()
            is_valid, error_msg = workflow_loader.validate_workflow_for_agent(workflow)
            if not is_valid:
                return {
                    "success": False,
                    "error": error_msg,
                }

        # Infer context from project if not provided
        ctx = get_project_context()
        if project_id is None:
            if ctx:
                project_id = ctx.get("id")
                project_path = ctx.get("project_path")
            else:
                return {
                    "success": False,
                    "error": "No project context found. Run from a Gobby project directory.",
                }
        else:
            # project_id was provided - try to get project_path from context if it matches
            if ctx and ctx.get("id") == project_id:
                project_path = ctx.get("project_path")
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
            agent=agent,
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

                # Get tool proxy for routing calls
                tool_proxy = tool_proxy_getter() if tool_proxy_getter else None
                if tool_proxy is None:
                    return ToolResult(
                        tool_name=tool_name,
                        success=False,
                        error=f"Tool proxy not configured - cannot route tool {tool_name}",
                    )

                # Route the tool call through the MCP proxy
                try:
                    result = await tool_proxy.call_tool_by_name(tool_name, arguments)

                    # Handle error response format from call_tool_by_name
                    if isinstance(result, dict) and result.get("success") is False:
                        return ToolResult(
                            tool_name=tool_name,
                            success=False,
                            error=result.get("error", f"Tool {tool_name} failed"),
                        )

                    # Successful tool call
                    return ToolResult(
                        tool_name=tool_name,
                        success=True,
                        result=result,
                    )
                except Exception as e:
                    logger.warning(f"Tool call failed for {tool_name}: {e}")
                    return ToolResult(
                        tool_name=tool_name,
                        success=False,
                        error=str(e),
                    )

            # Load available tools for the agent
            from gobby.llm.executor import ToolSchema

            tool_schemas: list[ToolSchema] = []
            tool_proxy = tool_proxy_getter() if tool_proxy_getter else None
            if tool_proxy:
                # Get internal servers that have tools
                internal_servers = ["gobby-tasks", "gobby-memory", "gobby-sessions"]
                for srv in internal_servers:
                    try:
                        tools_result = await tool_proxy.list_tools(srv)
                        if tools_result.get("success"):
                            for tool_brief in tools_result.get("tools", []):
                                # Get full schema for each tool
                                schema_result = await tool_proxy.get_tool_schema(
                                    srv, tool_brief["name"]
                                )
                                if schema_result.get("success"):
                                    tool_data = schema_result.get("tool", {})
                                    tool_schemas.append(
                                        ToolSchema(
                                            name=tool_brief["name"],
                                            description=tool_brief.get("brief", ""),
                                            input_schema=tool_data.get("inputSchema", {}),
                                            server_name=srv,
                                        )
                                    )
                    except Exception as e:
                        logger.debug(f"Could not load tools from {srv}: {e}")

            # Set tools on config
            config.tools = tool_schemas
            logger.info(f"Loaded {len(tool_schemas)} tools for in-process agent")

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

        # Special handling for Gemini terminal mode: requires preflight session capture
        # Gemini CLI in interactive mode can't introspect its session_id, so we:
        # 1. Launch preflight to capture session_id from stream-json output
        # 2. Create Gobby session with external_id = gemini's session_id
        # 3. Launch interactive with -r {session_id} to resume
        if mode == "terminal" and effective_provider == "gemini":
            from gobby.agents.spawn import (
                build_gemini_command_with_resume,
                prepare_gemini_spawn_with_preflight,
            )

            # Ensure project_id is non-None for spawning
            if project_id is None:
                return {
                    "success": False,
                    "error": "project_id is required for spawning Gemini agent",
                }

            # Determine working directory
            cwd = project_path or "."

            try:
                # Preflight capture: gets Gemini's session_id and creates linked Gobby session
                spawn_context = await prepare_gemini_spawn_with_preflight(
                    session_manager=runner._child_session_manager,
                    parent_session_id=parent_session_id,
                    project_id=project_id,
                    machine_id=socket.gethostname(),
                    workflow_name=workflow,
                    git_branch=None,  # Will be detected by hook
                )
            except FileNotFoundError as e:
                return {
                    "success": False,
                    "error": str(e),
                }
            except Exception as e:
                logger.error(f"Gemini preflight capture failed: {e}", exc_info=True)
                return {
                    "success": False,
                    "error": f"Gemini preflight capture failed: {e}",
                }

            # Extract IDs from prepared spawn context
            gobby_session_id = spawn_context.session_id
            gemini_session_id = spawn_context.env_vars["GOBBY_GEMINI_EXTERNAL_ID"]

            # Build command with session context injected into prompt
            # build_gemini_command_with_resume handles the context prefix
            cmd = build_gemini_command_with_resume(
                gemini_external_id=gemini_session_id,
                prompt=effective_prompt,
                auto_approve=True,  # Subagents need to work autonomously
                gobby_session_id=gobby_session_id,
            )

            # Spawn in terminal
            terminal_spawner = TerminalSpawner()
            terminal_result = terminal_spawner.spawn(
                command=cmd,
                cwd=cwd,
                terminal=terminal,
            )

            if not terminal_result.success:
                return {
                    "success": False,
                    "error": terminal_result.error or terminal_result.message,
                    "child_session_id": gobby_session_id,
                }

            # Register in running agents registry
            registry = get_running_agent_registry()
            running_agent = RunningAgent(
                run_id=f"gemini-{gemini_session_id[:8]}",
                session_id=gobby_session_id,
                parent_session_id=parent_session_id,
                pid=terminal_result.pid,
                mode="terminal",
                provider="gemini",
                workflow_name=workflow,
            )
            registry.add(running_agent)

            return {
                "success": True,
                "run_id": running_agent.run_id,
                "child_session_id": gobby_session_id,
                "gemini_session_id": gemini_session_id,
                "mode": "terminal",
                "message": (f"Gemini agent spawned in terminal with session {gobby_session_id}"),
                "pid": terminal_result.pid,
            }

        # Special handling for Codex terminal mode: requires preflight session capture
        # Codex outputs session_id in startup banner, which we parse from `codex exec "exit"`
        if mode == "terminal" and effective_provider == "codex":
            from gobby.agents.spawn import (
                build_codex_command_with_resume,
                prepare_codex_spawn_with_preflight,
            )

            # Ensure project_id is non-None for spawning
            if project_id is None:
                return {
                    "success": False,
                    "error": "project_id is required for spawning Codex agent",
                }

            # Determine working directory
            cwd = project_path or "."

            try:
                # Preflight capture: gets Codex's session_id and creates linked Gobby session
                spawn_context = await prepare_codex_spawn_with_preflight(
                    session_manager=runner._child_session_manager,
                    parent_session_id=parent_session_id,
                    project_id=project_id,
                    machine_id=socket.gethostname(),
                    workflow_name=workflow,
                    git_branch=None,  # Will be detected by hook
                )
            except FileNotFoundError as e:
                return {
                    "success": False,
                    "error": str(e),
                }
            except Exception as e:
                logger.error(f"Codex preflight capture failed: {e}", exc_info=True)
                return {
                    "success": False,
                    "error": f"Codex preflight capture failed: {e}",
                }

            # Extract IDs from prepared spawn context
            gobby_session_id = spawn_context.session_id
            codex_session_id = spawn_context.env_vars["GOBBY_CODEX_EXTERNAL_ID"]

            # Build command with session context injected into prompt
            # build_codex_command_with_resume handles the context prefix
            cmd = build_codex_command_with_resume(
                codex_external_id=codex_session_id,
                prompt=effective_prompt,
                auto_approve=True,  # --full-auto for sandboxed autonomy
                gobby_session_id=gobby_session_id,
                working_directory=cwd,
            )

            # Spawn in terminal
            terminal_spawner = TerminalSpawner()
            terminal_result = terminal_spawner.spawn(
                command=cmd,
                cwd=cwd,
                terminal=terminal,
            )

            if not terminal_result.success:
                return {
                    "success": False,
                    "error": terminal_result.error or terminal_result.message,
                    "child_session_id": gobby_session_id,
                }

            # Register in running agents registry
            registry = get_running_agent_registry()
            running_agent = RunningAgent(
                run_id=f"codex-{codex_session_id[:8]}",
                session_id=gobby_session_id,
                parent_session_id=parent_session_id,
                pid=terminal_result.pid,
                mode="terminal",
                provider="codex",
                workflow_name=workflow,
            )
            registry.add(running_agent)

            return {
                "success": True,
                "run_id": running_agent.run_id,
                "child_session_id": gobby_session_id,
                "codex_session_id": codex_session_id,
                "mode": "terminal",
                "message": (f"Codex agent spawned in terminal with session {gobby_session_id}"),
                "pid": terminal_result.pid,
            }

        # Terminal, embedded, or headless mode: prepare run then spawn
        # Use prepare_run to create session and run records
        from gobby.llm.executor import AgentResult

        prepare_result = runner.prepare_run(config)
        if isinstance(prepare_result, AgentResult):
            # prepare_run returns AgentResult on error
            return {
                "success": False,
                "error": prepare_result.error,
            }

        # Successfully prepared - we have context with session and run
        context = prepare_result

        # Validate context has required session and run (should always be set after prepare_run)
        if context.session is None or context.run is None:
            return {
                "success": False,
                "error": "Internal error: context missing session or run after prepare_run",
            }

        # Type narrowing: assign to non-optional variables
        child_session = context.session
        agent_run = context.run

        # Determine working directory
        cwd = project_path or "."

        # Ensure project_id is non-None for spawn calls
        if project_id is None:
            return {
                "success": False,
                "error": "project_id is required for spawning",
            }

        if mode == "terminal":
            # Spawn in external terminal
            terminal_spawner = TerminalSpawner()
            terminal_result = terminal_spawner.spawn_agent(
                cli=effective_provider,  # claude, gemini, codex
                cwd=cwd,
                session_id=child_session.id,
                parent_session_id=parent_session_id,
                agent_run_id=agent_run.id,
                project_id=project_id,
                workflow_name=workflow,
                agent_depth=child_session.agent_depth,
                max_agent_depth=runner._child_session_manager.max_agent_depth,
                terminal=terminal,
                prompt=effective_prompt,
            )

            if not terminal_result.success:
                return {
                    "success": False,
                    "error": terminal_result.error or terminal_result.message,
                    "run_id": agent_run.id,
                    "child_session_id": child_session.id,
                }

            # Register in running agents registry
            running_agent = RunningAgent(
                run_id=agent_run.id,
                session_id=child_session.id,
                parent_session_id=parent_session_id,
                mode="terminal",
                pid=terminal_result.pid,
                terminal_type=terminal_result.terminal_type,
                provider=effective_provider,
                workflow_name=workflow,
                worktree_id=worktree_id,
            )
            agent_registry.add(running_agent)

            return {
                "success": True,
                "run_id": agent_run.id,
                "child_session_id": child_session.id,
                "status": "pending",
                "message": f"Agent spawned in {terminal_result.terminal_type} (PID: {terminal_result.pid})",
                "terminal_type": terminal_result.terminal_type,
                "pid": terminal_result.pid,
            }

        elif mode == "embedded":
            # Spawn with PTY for UI attachment
            embedded_spawner = EmbeddedSpawner()
            embedded_result = embedded_spawner.spawn_agent(
                cli=effective_provider,
                cwd=cwd,
                session_id=child_session.id,
                parent_session_id=parent_session_id,
                agent_run_id=agent_run.id,
                project_id=project_id,
                workflow_name=workflow,
                agent_depth=child_session.agent_depth,
                max_agent_depth=runner._child_session_manager.max_agent_depth,
                prompt=effective_prompt,
            )

            if not embedded_result.success:
                return {
                    "success": False,
                    "error": embedded_result.error or embedded_result.message,
                    "run_id": agent_run.id,
                    "child_session_id": child_session.id,
                }

            # Register in running agents registry
            running_agent = RunningAgent(
                run_id=agent_run.id,
                session_id=child_session.id,
                parent_session_id=parent_session_id,
                mode="embedded",
                pid=embedded_result.pid,
                master_fd=embedded_result.master_fd,
                provider=effective_provider,
                workflow_name=workflow,
                worktree_id=worktree_id,
            )
            agent_registry.add(running_agent)

            return {
                "success": True,
                "run_id": agent_run.id,
                "child_session_id": child_session.id,
                "status": "pending",
                "message": f"Agent spawned with PTY (PID: {embedded_result.pid})",
                "pid": embedded_result.pid,
                "master_fd": embedded_result.master_fd,
            }

        else:  # headless mode
            # Spawn headless with output capture
            headless_spawner = HeadlessSpawner()
            headless_result = headless_spawner.spawn_agent(
                cli=effective_provider,
                cwd=cwd,
                session_id=child_session.id,
                parent_session_id=parent_session_id,
                agent_run_id=agent_run.id,
                project_id=project_id,
                workflow_name=workflow,
                agent_depth=child_session.agent_depth,
                max_agent_depth=runner._child_session_manager.max_agent_depth,
                prompt=effective_prompt,
            )

            if not headless_result.success:
                return {
                    "success": False,
                    "error": headless_result.error or headless_result.message,
                    "run_id": agent_run.id,
                    "child_session_id": child_session.id,
                }

            # IMPORTANT: For headless mode with -p flag, hooks are NOT called.
            # Claude's print mode bypasses the hook system entirely.
            # We must manually mark the agent run as started.
            try:
                runner._run_storage.start(agent_run.id)
                logger.info(f"Manually started headless agent run {agent_run.id}")
            except Exception as e:
                logger.warning(f"Failed to manually start agent run: {e}")

            # Register in running agents registry
            running_agent = RunningAgent(
                run_id=agent_run.id,
                session_id=child_session.id,
                parent_session_id=parent_session_id,
                mode="headless",
                pid=headless_result.pid,
                provider=effective_provider,
                workflow_name=workflow,
                worktree_id=worktree_id,
            )
            agent_registry.add(running_agent)

            # Start background task to monitor process completion
            import asyncio

            async def monitor_headless_process() -> None:
                """Monitor headless process and update status on completion."""
                try:
                    process = headless_result.process
                    if process is None:
                        return

                    # Wait for process to complete
                    loop = asyncio.get_running_loop()
                    return_code = await loop.run_in_executor(None, process.wait)

                    # Capture output
                    output = ""
                    if process.stdout:
                        output = process.stdout.read() or ""

                    # Update agent run status
                    if return_code == 0:
                        runner._run_storage.complete(
                            agent_run.id,
                            result=output,
                            tool_calls_count=0,
                            turns_used=1,
                        )
                        logger.info(f"Headless agent {agent_run.id} completed successfully")
                    else:
                        runner._run_storage.fail(
                            agent_run.id, error=f"Process exited with code {return_code}"
                        )
                        logger.warning(
                            f"Headless agent {agent_run.id} failed with code {return_code}"
                        )

                    # Remove from running agents registry
                    agent_registry.remove(agent_run.id)

                except Exception as e:
                    logger.error(f"Error monitoring headless process: {e}")
                    try:
                        runner._run_storage.fail(agent_run.id, error=str(e))
                        agent_registry.remove(agent_run.id)
                    except Exception:
                        pass  # nosec B110 - Best-effort cleanup during error handling

            # Schedule monitoring task and store reference to prevent GC
            running_agent.monitor_task = asyncio.create_task(monitor_headless_process())

            return {
                "success": True,
                "run_id": agent_run.id,
                "child_session_id": child_session.id,
                "status": "running",  # Now "running" since we manually started it
                "message": f"Agent spawned headless (PID: {headless_result.pid})",
                "pid": headless_result.pid,
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
            return {
                "success": True,
                "message": f"Agent run {run_id} stopped",
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
                    "error": f"Cannot stop agent in status: {run.status}",
                }

    @registry.tool(
        name="kill_agent",
        description="Kill a running agent process. Use stop=True to also end its workflow.",
    )
    async def kill_agent(
        run_id: str,
        signal: str = "TERM",
        force: bool = False,
        stop: bool = False,
    ) -> dict[str, Any]:
        """
        Kill a running agent process.

        This actually terminates the process (unlike stop_agent which only updates DB).

        Args:
            run_id: Agent run ID
            signal: Signal to send (TERM, KILL, INT, HUP, QUIT). Default: TERM
            force: Use SIGKILL immediately (equivalent to signal="KILL")
            stop: Also end the agent's workflow (prevents restart)

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

        # Get agent info before killing (for session_id)
        agent = agent_registry.get(run_id)
        session_id = agent.session_id if agent else None

        # Kill via registry (run in thread to avoid blocking event loop)
        import asyncio

        result = await asyncio.to_thread(agent_registry.kill, run_id, signal_name=signal)

        if result.get("success"):
            # Update database status
            runner.cancel_run(run_id)

            # Optionally end the workflow to prevent restart
            if stop and session_id:
                if workflow_state_manager is not None:
                    try:
                        workflow_state_manager.delete_state(session_id)
                        result["workflow_stopped"] = True
                    except Exception as e:
                        result["workflow_stop_error"] = str(e)
                else:
                    result["workflow_stop_error"] = "WorkflowStateManager not configured"

        return result

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
