"""Terminal spawning for agent execution.

This module provides the TerminalSpawner orchestrator and PreparedSpawn helpers
for spawning CLI agents in terminal windows.

Implementation is split across submodules:
- spawners/prompt_manager.py: Prompt file creation and cleanup
- spawners/command_builder.py: CLI command construction
- spawners/: Platform-specific terminal spawners
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from gobby.agents.constants import get_terminal_env_vars
from gobby.agents.sandbox import SandboxConfig, compute_sandbox_paths, get_sandbox_resolver
from gobby.agents.session import ChildSessionConfig, ChildSessionManager
from gobby.agents.spawners import (
    MAX_ENV_PROMPT_LENGTH,
    AlacrittySpawner,
    CmdSpawner,
    EmbeddedSpawner,
    GhosttySpawner,
    GnomeTerminalSpawner,
    HeadlessSpawner,
    ITermSpawner,
    KittySpawner,
    KonsoleSpawner,
    PowerShellSpawner,
    SpawnMode,
    SpawnResult,
    TerminalAppSpawner,
    TerminalSpawnerBase,
    TerminalType,
    TmuxSpawner,
    WindowsTerminalSpawner,
    WSLSpawner,
    build_cli_command,
    build_codex_command_with_resume,
    build_gemini_command_with_resume,
    create_prompt_file,
    read_prompt_from_env,
)
from gobby.agents.spawners.base import EmbeddedPTYResult, HeadlessResult
from gobby.agents.tty_config import get_tty_config

# Re-export for backward compatibility - these types moved to spawners/ package
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
    # Orchestrator
    "TerminalSpawner",
    # Spawner implementations
    "GhosttySpawner",
    "ITermSpawner",
    "TerminalAppSpawner",
    "KittySpawner",
    "AlacrittySpawner",
    "GnomeTerminalSpawner",
    "KonsoleSpawner",
    "WindowsTerminalSpawner",
    "CmdSpawner",
    "PowerShellSpawner",
    "WSLSpawner",
    "TmuxSpawner",
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


class TerminalSpawner:
    """
    Main terminal spawner that auto-detects and uses available terminals.

    Provides a unified interface for spawning terminal processes across
    different platforms and terminal emulators. Terminal preferences and
    configurations are loaded from ~/.gobby/tty_config.yaml.
    """

    # Map terminal names to spawner classes
    SPAWNER_CLASSES: dict[str, type[TerminalSpawnerBase]] = {
        "ghostty": GhosttySpawner,
        "iterm": ITermSpawner,
        "terminal.app": TerminalAppSpawner,
        "kitty": KittySpawner,
        "alacritty": AlacrittySpawner,
        "gnome-terminal": GnomeTerminalSpawner,
        "konsole": KonsoleSpawner,
        "windows-terminal": WindowsTerminalSpawner,
        "cmd": CmdSpawner,
        "powershell": PowerShellSpawner,
        "wsl": WSLSpawner,
        "tmux": TmuxSpawner,
    }

    def __init__(self) -> None:
        """Initialize with platform-specific terminal preferences."""
        self._spawners: dict[TerminalType, TerminalSpawnerBase] = {}
        self._register_spawners()

    def _register_spawners(self) -> None:
        """Register all available spawners."""
        all_spawners = [
            GhosttySpawner(),
            ITermSpawner(),
            TerminalAppSpawner(),
            KittySpawner(),
            AlacrittySpawner(),
            GnomeTerminalSpawner(),
            KonsoleSpawner(),
            WindowsTerminalSpawner(),
            CmdSpawner(),
            PowerShellSpawner(),
            WSLSpawner(),
            TmuxSpawner(),
        ]

        for spawner in all_spawners:
            self._spawners[spawner.terminal_type] = spawner

    def get_available_terminals(self) -> list[TerminalType]:
        """Get list of available terminals on this system."""
        return [
            term_type for term_type, spawner in self._spawners.items() if spawner.is_available()
        ]

    def get_preferred_terminal(self) -> TerminalType | None:
        """Get the preferred available terminal for this platform based on config."""
        config = get_tty_config()
        preferences = config.get_preferences()

        for terminal_name in preferences:
            spawner_cls = self.SPAWNER_CLASSES.get(terminal_name)
            if spawner_cls is None:
                continue
            spawner = spawner_cls()
            if spawner.is_available():
                return spawner.terminal_type

        return None

    def spawn(
        self,
        command: list[str],
        cwd: str | Path,
        terminal: TerminalType | str = TerminalType.AUTO,
        env: dict[str, str] | None = None,
        title: str | None = None,
    ) -> SpawnResult:
        """
        Spawn a command in a new terminal window.

        Args:
            command: Command to run
            cwd: Working directory
            terminal: Terminal type or "auto" for auto-detection
            env: Environment variables to set
            title: Optional window title

        Returns:
            SpawnResult with success status
        """
        # Convert string to enum if needed
        if isinstance(terminal, str):
            try:
                terminal = TerminalType(terminal)
            except ValueError:
                return SpawnResult(
                    success=False,
                    message=f"Unknown terminal type: {terminal}",
                )

        # Auto-detect if requested
        if terminal == TerminalType.AUTO:
            preferred = self.get_preferred_terminal()
            if preferred is None:
                return SpawnResult(
                    success=False,
                    message="No supported terminal found on this system",
                )
            terminal = preferred

        # Get spawner
        spawner = self._spawners.get(terminal)
        if spawner is None:
            return SpawnResult(
                success=False,
                message=f"No spawner registered for terminal: {terminal}",
            )

        if not spawner.is_available():
            return SpawnResult(
                success=False,
                message=f"Terminal {terminal.value} is not available on this system",
            )

        # Spawn the terminal
        return spawner.spawn(command, cwd, env, title)

    def spawn_agent(
        self,
        cli: str,
        cwd: str | Path,
        session_id: str,
        parent_session_id: str,
        agent_run_id: str,
        project_id: str,
        workflow_name: str | None = None,
        agent_depth: int = 1,
        max_agent_depth: int = 3,
        terminal: TerminalType | str = TerminalType.AUTO,
        prompt: str | None = None,
        sandbox_config: SandboxConfig | None = None,
    ) -> SpawnResult:
        """
        Spawn a CLI agent in a new terminal with Gobby environment variables.

        Args:
            cli: CLI to run (e.g., "claude", "gemini", "codex")
            cwd: Working directory (usually project root or worktree)
            session_id: Pre-created child session ID
            parent_session_id: Parent session for context resolution
            agent_run_id: Agent run record ID
            project_id: Project ID
            workflow_name: Optional workflow to activate
            agent_depth: Current nesting depth
            max_agent_depth: Maximum allowed depth
            terminal: Terminal type or "auto"
            prompt: Optional initial prompt
            sandbox_config: Optional sandbox configuration

        Returns:
            SpawnResult with success status
        """
        # Resolve sandbox configuration if enabled
        sandbox_args: list[str] | None = None
        sandbox_env: dict[str, str] = {}

        if sandbox_config and sandbox_config.enabled:
            # Compute sandbox paths based on cwd (workspace)
            resolved_paths = compute_sandbox_paths(sandbox_config, str(cwd))
            # Get CLI-specific resolver and generate args/env
            resolver = get_sandbox_resolver(cli)
            sandbox_args, sandbox_env = resolver.resolve(sandbox_config, resolved_paths)

        # Build command with prompt as CLI argument and auto-approve for autonomous work
        command = build_cli_command(
            cli,
            prompt=prompt,
            session_id=session_id,
            auto_approve=True,  # Subagents need to work autonomously
            working_directory=str(cwd) if cli == "codex" else None,
            mode="terminal",  # Interactive terminal mode
            sandbox_args=sandbox_args,
        )

        # Handle prompt for environment variables (backup for hooks/context)
        prompt_env: str | None = None
        prompt_file: str | None = None

        if prompt:
            if len(prompt) <= MAX_ENV_PROMPT_LENGTH:
                prompt_env = prompt
            else:
                prompt_file = self._write_prompt_file(prompt, session_id)

        # Build environment
        env = get_terminal_env_vars(
            session_id=session_id,
            parent_session_id=parent_session_id,
            agent_run_id=agent_run_id,
            project_id=project_id,
            workflow_name=workflow_name,
            agent_depth=agent_depth,
            max_agent_depth=max_agent_depth,
            prompt=prompt_env,
            prompt_file=prompt_file,
        )

        # Merge sandbox environment variables if present
        if sandbox_env:
            env.update(sandbox_env)

        # Set title (avoid colons/parentheses which Ghostty interprets as config syntax)
        title = f"gobby-{cli}-d{agent_depth}"

        return self.spawn(
            command=command,
            cwd=cwd,
            terminal=terminal,
            env=env,
            title=title,
        )

    def _write_prompt_file(self, prompt: str, session_id: str) -> str:
        """
        Write prompt to a temp file for passing to spawned agent.

        Delegates to the create_prompt_file helper which handles
        secure permissions and cleanup tracking.

        Args:
            prompt: The prompt content
            session_id: Session ID for naming the file

        Returns:
            Path to the created temp file
        """
        return create_prompt_file(prompt, session_id)


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
        source: CLI source (claude, gemini, codex)
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
