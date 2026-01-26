"""
Unified Spawn Executor for Agent Spawning.

This module consolidates the spawn dispatch logic from agents.py, worktrees.py,
and clones.py into a single unified executor that handles terminal, embedded,
and headless modes.
"""

import logging
from dataclasses import dataclass
from typing import Any, Literal

from gobby.agents.spawn import TerminalSpawner
from gobby.agents.spawners.embedded import EmbeddedSpawner
from gobby.agents.spawners.headless import HeadlessSpawner

logger = logging.getLogger(__name__)


@dataclass
class SpawnRequest:
    """Request for spawning an agent."""

    # Required fields
    prompt: str
    cwd: str
    mode: Literal["terminal", "embedded", "headless"]
    provider: str
    terminal: str
    session_id: str
    run_id: str
    parent_session_id: str
    project_id: str

    # Optional fields
    workflow: str | None = None
    worktree_id: str | None = None
    clone_id: str | None = None
    agent_depth: int = 0
    max_agent_depth: int = 3


@dataclass
class SpawnResult:
    """Result of a spawn operation."""

    success: bool
    run_id: str
    child_session_id: str
    status: str

    # Optional result fields
    pid: int | None = None
    terminal_type: str | None = None
    master_fd: int | None = None
    error: str | None = None
    message: str | None = None
    process: Any | None = None  # subprocess.Popen for headless


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
