"""Terminal spawning for agent execution.

This module provides PreparedSpawn helpers and preflight functions for
spawning CLI agents.  The actual terminal spawning is handled by
:class:`TmuxSpawner` (re-exported here for backward compatibility).

Implementation is split across submodules:
- spawners/prompt_manager.py: Prompt file creation and cleanup
- spawners/command_builder.py: CLI command construction
- agents/tmux/spawner.py: TmuxSpawner (sole terminal backend)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from gobby.agents.constants import get_terminal_env_vars
from gobby.agents.session import ChildSessionConfig, ChildSessionManager
from gobby.agents.spawners import (
    MAX_ENV_PROMPT_LENGTH,
    SpawnMode,
    SpawnResult,
    TerminalSpawnerBase,
    TerminalType,
    build_cli_command,
    build_codex_command_with_resume,
    build_gemini_command_with_resume,
    create_prompt_file,
    read_prompt_from_env,
)
from gobby.agents.spawners.base import EmbeddedPTYResult, HeadlessResult
from gobby.agents.spawners.embedded import EmbeddedSpawner
from gobby.agents.spawners.headless import HeadlessSpawner
from gobby.agents.tmux.spawner import TmuxSpawner

# Re-export TmuxSpawner under the old name for callers that still
# reference ``TerminalSpawner`` in patch targets or imports.
TerminalSpawner = TmuxSpawner

__all__ = [
    # Enums
    "SpawnMode",
    "TerminalType",
    # Result dataclasses
    "SpawnResult",
    "EmbeddedPTYResult",
    "HeadlessResult",
    # Base class
    "TerminalSpawnerBase",
    # Spawner (tmux-only)
    "TmuxSpawner",
    "TerminalSpawner",  # backward compat alias
    # Embedded/Headless
    "EmbeddedSpawner",
    "HeadlessSpawner",
    # Helpers
    "PreparedSpawn",
    "prepare_terminal_spawn",
    "prepare_gemini_spawn_with_preflight",
    "prepare_codex_spawn_with_preflight",
    "read_prompt_from_env",
    "build_cli_command",
    "build_gemini_command_with_resume",
    "build_codex_command_with_resume",
    "create_prompt_file",
    "MAX_ENV_PROMPT_LENGTH",
]

logger = logging.getLogger(__name__)


@dataclass
class PreparedSpawn:
    """Configuration for a prepared terminal spawn."""

    session_id: str
    """The pre-created child session ID."""

    agent_run_id: str
    """The agent run record ID."""

    parent_session_id: str
    """The parent session ID."""

    project_id: str
    """The project ID."""

    workflow_name: str | None
    """Workflow to activate (if any)."""

    agent_depth: int
    """Current agent depth."""

    env_vars: dict[str, str]
    """Environment variables to set."""


def prepare_terminal_spawn(
    session_manager: ChildSessionManager,
    parent_session_id: str,
    project_id: str,
    machine_id: str,
    source: str = "claude",
    agent_id: str | None = None,
    workflow_name: str | None = None,
    step_variables: dict[str, Any] | None = None,
    title: str | None = None,
    git_branch: str | None = None,
    prompt: str | None = None,
    max_agent_depth: int = 3,
) -> PreparedSpawn:
    """
    Prepare a terminal spawn by creating the child session.

    This should be called before spawning a terminal to:
    1. Create the child session in the database
    2. Generate the agent run ID
    3. Build the environment variables

    Args:
        session_manager: ChildSessionManager for session creation
        parent_session_id: Parent session ID
        project_id: Project ID
        machine_id: Machine ID
        source: CLI source (claude, gemini, codex, cursor, windsurf, copilot)
        agent_id: Optional agent ID
        workflow_name: Optional workflow to activate
        title: Optional session title
        git_branch: Optional git branch
        prompt: Optional initial prompt
        max_agent_depth: Maximum agent depth

    Returns:
        PreparedSpawn with all necessary spawn configuration

    Raises:
        ValueError: If max agent depth exceeded
    """
    import uuid

    # Create child session config
    config = ChildSessionConfig(
        parent_session_id=parent_session_id,
        project_id=project_id,
        machine_id=machine_id,
        source=source,
        agent_id=agent_id,
        workflow_name=workflow_name,
        step_variables=step_variables,
        title=title,
        git_branch=git_branch,
    )

    # Create the child session
    child_session = session_manager.create_child_session(config)

    # Generate agent run ID
    agent_run_id = f"run-{uuid.uuid4().hex[:12]}"

    # Handle prompt - decide env var vs file
    prompt_env: str | None = None
    prompt_file: str | None = None

    if prompt:
        if len(prompt) <= MAX_ENV_PROMPT_LENGTH:
            prompt_env = prompt
        else:
            # Write to temp file with secure permissions
            prompt_file = create_prompt_file(prompt, child_session.id)

    # Build environment variables
    env_vars = get_terminal_env_vars(
        session_id=child_session.id,
        parent_session_id=parent_session_id,
        agent_run_id=agent_run_id,
        project_id=project_id,
        workflow_name=workflow_name,
        agent_depth=child_session.agent_depth,
        max_agent_depth=max_agent_depth,
        prompt=prompt_env,
        prompt_file=prompt_file,
    )

    return PreparedSpawn(
        session_id=child_session.id,
        agent_run_id=agent_run_id,
        parent_session_id=parent_session_id,
        project_id=project_id,
        workflow_name=workflow_name,
        agent_depth=child_session.agent_depth,
        env_vars=env_vars,
    )


async def prepare_gemini_spawn_with_preflight(
    session_manager: ChildSessionManager,
    parent_session_id: str,
    project_id: str,
    machine_id: str,
    agent_id: str | None = None,
    workflow_name: str | None = None,
    step_variables: dict[str, Any] | None = None,
    title: str | None = None,
    git_branch: str | None = None,
    prompt: str | None = None,
    max_agent_depth: int = 3,
    preflight_timeout: float = 10.0,
) -> PreparedSpawn:
    """
    Prepare a Gemini terminal spawn with preflight session ID capture.

    This is necessary because Gemini CLI in interactive mode cannot introspect
    its own session_id. We use preflight capture to:
    1. Launch Gemini with stream-json to capture its session_id
    2. Create the Gobby session with that external_id
    3. Resume the Gemini session with -r flag

    Args:
        session_manager: ChildSessionManager for session creation
        parent_session_id: Parent session ID
        project_id: Project ID
        machine_id: Machine ID
        agent_id: Optional agent ID
        workflow_name: Optional workflow to activate
        title: Optional session title
        git_branch: Optional git branch
        prompt: Optional initial prompt
        max_agent_depth: Maximum agent depth
        preflight_timeout: Timeout for preflight capture (default 10s)

    Returns:
        PreparedSpawn with gemini_external_id set in env_vars

    Raises:
        ValueError: If max agent depth exceeded
        asyncio.TimeoutError: If preflight capture times out
    """
    import uuid

    from gobby.agents.gemini_session import capture_gemini_session_id

    # 1. Preflight: capture Gemini's session_id
    logger.info("Starting Gemini preflight capture...")
    gemini_info = await capture_gemini_session_id(timeout=preflight_timeout)
    logger.info(f"Captured Gemini session_id: {gemini_info.session_id}")

    # 2. Create child session config with Gemini's session_id as external_id
    config = ChildSessionConfig(
        parent_session_id=parent_session_id,
        project_id=project_id,
        machine_id=machine_id,
        source="gemini",
        agent_id=agent_id,
        workflow_name=workflow_name,
        step_variables=step_variables,
        title=title,
        git_branch=git_branch,
        external_id=gemini_info.session_id,  # Link to Gemini's session
    )

    # Create the child session
    child_session = session_manager.create_child_session(config)

    # Generate agent run ID
    agent_run_id = f"run-{uuid.uuid4().hex[:12]}"

    # Handle prompt - decide env var vs file
    prompt_env: str | None = None
    prompt_file: str | None = None

    if prompt:
        if len(prompt) <= MAX_ENV_PROMPT_LENGTH:
            prompt_env = prompt
        else:
            prompt_file = create_prompt_file(prompt, child_session.id)

    # Build environment variables
    env_vars = get_terminal_env_vars(
        session_id=child_session.id,
        parent_session_id=parent_session_id,
        agent_run_id=agent_run_id,
        project_id=project_id,
        workflow_name=workflow_name,
        agent_depth=child_session.agent_depth,
        max_agent_depth=max_agent_depth,
        prompt=prompt_env,
        prompt_file=prompt_file,
    )

    # Add Gemini-specific env vars for session linking
    env_vars["GOBBY_GEMINI_EXTERNAL_ID"] = gemini_info.session_id
    if gemini_info.model:
        env_vars["GOBBY_GEMINI_MODEL"] = gemini_info.model

    return PreparedSpawn(
        session_id=child_session.id,
        agent_run_id=agent_run_id,
        parent_session_id=parent_session_id,
        project_id=project_id,
        workflow_name=workflow_name,
        agent_depth=child_session.agent_depth,
        env_vars=env_vars,
    )


async def prepare_codex_spawn_with_preflight(
    session_manager: ChildSessionManager,
    parent_session_id: str,
    project_id: str,
    machine_id: str,
    agent_id: str | None = None,
    workflow_name: str | None = None,
    step_variables: dict[str, Any] | None = None,
    title: str | None = None,
    git_branch: str | None = None,
    prompt: str | None = None,
    max_agent_depth: int = 3,
    preflight_timeout: float = 30.0,
) -> PreparedSpawn:
    """
    Prepare a Codex terminal spawn with preflight session ID capture.

    This is necessary because we need Codex's session_id before launching
    interactive mode to properly link sessions. We use preflight capture to:
    1. Launch Codex with `exec "exit"` to capture its session_id
    2. Create the Gobby session with that external_id
    3. Resume the Codex session with `codex resume {session_id}`

    Args:
        session_manager: ChildSessionManager for session creation
        parent_session_id: Parent session ID
        project_id: Project ID
        machine_id: Machine ID
        agent_id: Optional agent ID
        workflow_name: Optional workflow to activate
        title: Optional session title
        git_branch: Optional git branch
        prompt: Optional initial prompt
        max_agent_depth: Maximum agent depth
        preflight_timeout: Timeout for preflight capture (default 30s)

    Returns:
        PreparedSpawn with codex_external_id set in env_vars

    Raises:
        ValueError: If max agent depth exceeded
        asyncio.TimeoutError: If preflight capture times out
    """
    import uuid

    from gobby.agents.codex_session import capture_codex_session_id

    # 1. Preflight: capture Codex's session_id
    logger.info("Starting Codex preflight capture...")
    codex_info = await capture_codex_session_id(timeout=preflight_timeout)
    logger.info(f"Captured Codex session_id: {codex_info.session_id}")

    # 2. Create child session config with Codex's session_id as external_id
    config = ChildSessionConfig(
        parent_session_id=parent_session_id,
        project_id=project_id,
        machine_id=machine_id,
        source="codex",
        agent_id=agent_id,
        workflow_name=workflow_name,
        step_variables=step_variables,
        title=title,
        git_branch=git_branch,
        external_id=codex_info.session_id,  # Link to Codex's session
    )

    # Create the child session
    child_session = session_manager.create_child_session(config)

    # Generate agent run ID
    agent_run_id = f"run-{uuid.uuid4().hex[:12]}"

    # Handle prompt - decide env var vs file
    prompt_env: str | None = None
    prompt_file: str | None = None

    if prompt:
        if len(prompt) <= MAX_ENV_PROMPT_LENGTH:
            prompt_env = prompt
        else:
            prompt_file = create_prompt_file(prompt, child_session.id)

    # Build environment variables
    env_vars = get_terminal_env_vars(
        session_id=child_session.id,
        parent_session_id=parent_session_id,
        agent_run_id=agent_run_id,
        project_id=project_id,
        workflow_name=workflow_name,
        agent_depth=child_session.agent_depth,
        max_agent_depth=max_agent_depth,
        prompt=prompt_env,
        prompt_file=prompt_file,
    )

    # Add Codex-specific env vars for session linking
    env_vars["GOBBY_CODEX_EXTERNAL_ID"] = codex_info.session_id
    if codex_info.model:
        env_vars["GOBBY_CODEX_MODEL"] = codex_info.model

    return PreparedSpawn(
        session_id=child_session.id,
        agent_run_id=agent_run_id,
        parent_session_id=parent_session_id,
        project_id=project_id,
        workflow_name=workflow_name,
        agent_depth=child_session.agent_depth,
        env_vars=env_vars,
    )
