"""
Unified Spawn Executor for Agent Spawning.

This module consolidates the spawn dispatch logic from agents.py, worktrees.py,
and clones.py into a single unified executor that handles terminal, embedded,
and headless modes.
"""

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, cast

from gobby.agents.sandbox import (
    GeminiSandboxResolver,
    SandboxConfig,
    compute_sandbox_paths,
)

if TYPE_CHECKING:
    from gobby.agents.session import ChildSessionManager
from gobby.agents.spawn import (
    TerminalSpawner,
    build_cli_command,
    build_codex_command_with_resume,
    prepare_codex_spawn_with_preflight,
    prepare_terminal_spawn,
)
from gobby.agents.spawners.embedded import EmbeddedSpawner
from gobby.agents.spawners.headless import HeadlessSpawner

logger = logging.getLogger(__name__)


@dataclass
class SpawnRequest:
    """Request for spawning an agent."""

    # Required fields
    prompt: str
    cwd: str
    mode: Literal["terminal", "embedded", "headless", "self"]
    provider: str
    terminal: str
    session_id: str
    run_id: str
    parent_session_id: str
    project_id: str

    # Optional fields
    workflow: str | None = None
    step_variables: dict[str, Any] | None = None  # Variables for step workflow activation
    worktree_id: str | None = None
    clone_id: str | None = None
    branch_name: str | None = None  # Git branch for worktree/clone isolation
    agent_depth: int = 0
    max_agent_depth: int = 3
    session_manager: Any | None = None  # Required for Gemini/Codex preflight
    machine_id: str | None = None

    # Sandbox configuration
    sandbox_config: SandboxConfig | None = None
    sandbox_args: list[str] | None = None
    sandbox_env: dict[str, str] | None = field(default=None)


@dataclass
class SpawnResult:
    """Result of a spawn operation."""

    success: bool
    run_id: str
    child_session_id: str | None
    status: str

    # Optional result fields
    pid: int | None = None
    terminal_type: str | None = None
    master_fd: int | None = None
    error: str | None = None
    message: str | None = None
    process: Any | None = None  # subprocess.Popen for headless
    gemini_session_id: str | None = None  # Gemini external session ID
    codex_session_id: str | None = None  # Codex external session ID


async def execute_spawn(request: SpawnRequest) -> SpawnResult:
    """
    Unified spawn dispatch for terminal/embedded/headless modes.

    Consolidates duplicated logic from agents.py, worktrees.py, clones.py
    into a single dispatch function.

    Args:
        request: SpawnRequest with all spawn parameters

    Returns:
        SpawnResult with spawn outcome and metadata
    """
    if request.mode == "terminal":
        # Special handling for Gemini/Codex: requires preflight session capture
        if request.provider == "gemini":
            return await _spawn_gemini_terminal(request)
        elif request.provider == "codex":
            return await _spawn_codex_terminal(request)
        return await _spawn_terminal(request)
    elif request.mode == "embedded":
        return await _spawn_embedded(request)
    else:  # headless
        return await _spawn_headless(request)


async def _spawn_terminal(request: SpawnRequest) -> SpawnResult:
    """Spawn agent in external terminal."""
    spawner = TerminalSpawner()
    result = spawner.spawn_agent(
        cli=request.provider,
        cwd=request.cwd,
        session_id=request.session_id,
        parent_session_id=request.parent_session_id,
        agent_run_id=request.run_id,
        project_id=request.project_id,
        workflow_name=request.workflow,
        agent_depth=request.agent_depth,
        max_agent_depth=request.max_agent_depth,
        terminal=request.terminal,
        prompt=request.prompt,
        sandbox_config=request.sandbox_config,
    )

    if not result.success:
        return SpawnResult(
            success=False,
            run_id=request.run_id,
            child_session_id=request.session_id,
            status="failed",
            error=result.error or result.message,
        )

    return SpawnResult(
        success=True,
        run_id=request.run_id,
        child_session_id=request.session_id,
        status="pending",
        pid=result.pid,
        terminal_type=result.terminal_type,
        message=f"Agent spawned in {result.terminal_type} (PID: {result.pid})",
    )


async def _spawn_embedded(request: SpawnRequest) -> SpawnResult:
    """Spawn agent with PTY for UI attachment."""
    spawner = EmbeddedSpawner()
    result = spawner.spawn_agent(
        cli=request.provider,
        cwd=request.cwd,
        session_id=request.session_id,
        parent_session_id=request.parent_session_id,
        agent_run_id=request.run_id,
        project_id=request.project_id,
        workflow_name=request.workflow,
        agent_depth=request.agent_depth,
        max_agent_depth=request.max_agent_depth,
        prompt=request.prompt,
        sandbox_config=request.sandbox_config,
    )

    if not result.success:
        return SpawnResult(
            success=False,
            run_id=request.run_id,
            child_session_id=request.session_id,
            status="failed",
            error=result.error or result.message,
        )

    return SpawnResult(
        success=True,
        run_id=request.run_id,
        child_session_id=request.session_id,
        status="pending",
        pid=result.pid,
        master_fd=result.master_fd,
        message=f"Agent spawned with PTY (PID: {result.pid})",
    )


async def _spawn_headless(request: SpawnRequest) -> SpawnResult:
    """Spawn headless agent with output capture."""
    spawner = HeadlessSpawner()
    result = spawner.spawn_agent(
        cli=request.provider,
        cwd=request.cwd,
        session_id=request.session_id,
        parent_session_id=request.parent_session_id,
        agent_run_id=request.run_id,
        project_id=request.project_id,
        workflow_name=request.workflow,
        agent_depth=request.agent_depth,
        max_agent_depth=request.max_agent_depth,
        prompt=request.prompt,
        sandbox_config=request.sandbox_config,
    )

    if not result.success:
        return SpawnResult(
            success=False,
            run_id=request.run_id,
            child_session_id=request.session_id,
            status="failed",
            error=result.error or result.message,
        )

    return SpawnResult(
        success=True,
        run_id=request.run_id,
        child_session_id=request.session_id,
        status="running",  # Headless is immediately running
        pid=result.pid,
        process=result.process,
        message=f"Agent spawned headless (PID: {result.pid})",
    )


async def _spawn_gemini_terminal(request: SpawnRequest) -> SpawnResult:
    """
    Spawn Gemini agent in terminal with direct spawn (no preflight).

    Session linkage approach:
    1. Pre-create Gobby session with parent linkage (no external_id yet)
    2. Pass GOBBY_SESSION_ID and other env vars to the terminal
    3. Gemini's hook dispatcher reads env vars and includes in SessionStart
    4. Daemon updates external_id when SessionStart fires with Gemini's native session_id

    This avoids the preflight+resume approach which failed because Gemini
    doesn't persist sessions when terminated.
    """
    if request.session_manager is None:
        return SpawnResult(
            success=False,
            run_id=request.run_id,
            child_session_id=None,
            status="failed",
            error="session_manager is required for Gemini spawn",
        )

    # Prepare spawn context (creates child session, builds env vars)
    spawn_context = prepare_terminal_spawn(
        session_manager=cast("ChildSessionManager", request.session_manager),
        parent_session_id=request.parent_session_id,
        project_id=request.project_id,
        machine_id=request.machine_id or "unknown",
        source="gemini",
        workflow_name=request.workflow,
        step_variables=request.step_variables,
        prompt=request.prompt,
        max_agent_depth=request.max_agent_depth,
        git_branch=request.branch_name,
    )

    gobby_session_id = spawn_context.session_id

    # Build command for fresh Gemini session (not resume)
    # Session context is injected via additionalContext at SessionStart by the daemon
    cmd = build_cli_command(
        cli="gemini",
        prompt=request.prompt,
        auto_approve=True,
        mode="terminal",
    )

    # Resolve sandbox config if provided
    sandbox_args: list[str] = []
    sandbox_env: dict[str, str] = {}
    if request.sandbox_config and request.sandbox_config.enabled:
        resolver = GeminiSandboxResolver()
        paths = compute_sandbox_paths(
            config=request.sandbox_config,
            workspace_path=request.cwd,
        )
        sandbox_args, sandbox_env = resolver.resolve(request.sandbox_config, paths)
        # Append sandbox args to command
        cmd.extend(sandbox_args)

    # Merge env vars: spawn context + sandbox
    env = spawn_context.env_vars.copy()
    if sandbox_env:
        env.update(sandbox_env)

    # Pass machine_id as env var for sandboxed agents that can't read ~/.gobby/machine_id
    if request.machine_id:
        env["GOBBY_MACHINE_ID"] = request.machine_id

    # Spawn in terminal with env vars
    terminal_spawner = TerminalSpawner()
    terminal_result = terminal_spawner.spawn(
        command=cmd,
        cwd=request.cwd,
        terminal=request.terminal,
        env=env,
    )

    if not terminal_result.success:
        return SpawnResult(
            success=False,
            run_id=request.run_id,
            child_session_id=gobby_session_id,
            status="failed",
            error=terminal_result.error or terminal_result.message,
        )

    return SpawnResult(
        success=True,
        run_id=spawn_context.agent_run_id,
        child_session_id=gobby_session_id,
        status="pending",
        pid=terminal_result.pid,
        message=f"Gemini agent spawned in terminal with session {gobby_session_id}",
    )


async def _spawn_codex_terminal(request: SpawnRequest) -> SpawnResult:
    """
    Spawn Codex agent in terminal with preflight session capture.

    Codex outputs session_id in startup banner, which we parse from `codex exec "exit"`.
    """
    if request.session_manager is None:
        return SpawnResult(
            success=False,
            run_id=request.run_id,
            child_session_id=request.session_id,
            status="failed",
            error="session_manager is required for Codex preflight",
        )

    try:
        # Preflight capture: gets Codex's session_id and creates linked Gobby session
        spawn_context = await prepare_codex_spawn_with_preflight(
            session_manager=cast("ChildSessionManager", request.session_manager),
            parent_session_id=request.parent_session_id,
            project_id=request.project_id,
            machine_id=request.machine_id or "unknown",
            workflow_name=request.workflow,
            step_variables=request.step_variables,
            git_branch=request.branch_name,
        )
    except FileNotFoundError as e:
        return SpawnResult(
            success=False,
            run_id=request.run_id,
            child_session_id=request.session_id,
            status="failed",
            error=str(e),
        )
    except Exception as e:
        logger.error(f"Codex preflight capture failed: {e}", exc_info=True)
        return SpawnResult(
            success=False,
            run_id=request.run_id,
            child_session_id=request.session_id,
            status="failed",
            error=f"Codex preflight capture failed: {e}",
        )

    # Extract IDs from prepared spawn context
    gobby_session_id = spawn_context.session_id
    codex_session_id = spawn_context.env_vars["GOBBY_CODEX_EXTERNAL_ID"]

    # Build command with session context injected into prompt
    cmd = build_codex_command_with_resume(
        codex_external_id=codex_session_id,
        prompt=request.prompt,
        auto_approve=True,  # --full-auto for sandboxed autonomy
        gobby_session_id=gobby_session_id,
        working_directory=request.cwd,
    )

    # Spawn in terminal
    terminal_spawner = TerminalSpawner()
    terminal_result = terminal_spawner.spawn(
        command=cmd,
        cwd=request.cwd,
        terminal=request.terminal,
    )

    if not terminal_result.success:
        return SpawnResult(
            success=False,
            run_id=request.run_id,
            child_session_id=gobby_session_id,
            status="failed",
            error=terminal_result.error or terminal_result.message,
        )

    return SpawnResult(
        success=True,
        run_id=f"codex-{codex_session_id[:8]}",
        child_session_id=gobby_session_id,
        status="pending",
        pid=terminal_result.pid,
        codex_session_id=codex_session_id,
        message=f"Codex agent spawned in terminal with session {gobby_session_id}",
    )
