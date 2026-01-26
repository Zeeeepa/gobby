"""Terminal spawning for agent execution."""

from __future__ import annotations

import atexit
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from gobby.agents.constants import get_terminal_env_vars
from gobby.agents.session import ChildSessionConfig, ChildSessionManager
from gobby.agents.spawners import (
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
    "MAX_ENV_PROMPT_LENGTH",
]

# Maximum prompt length to pass via environment variable
# Longer prompts will be written to a temp file
MAX_ENV_PROMPT_LENGTH = 4096

logger = logging.getLogger(__name__)

# Module-level set for tracking prompt files to clean up on exit
# This avoids registering a new atexit handler for each prompt file
_prompt_files_to_cleanup: set[Path] = set()
_atexit_registered = False


def _cleanup_all_prompt_files() -> None:
    """Clean up all tracked prompt files on process exit."""
    for prompt_path in list(_prompt_files_to_cleanup):
        try:
            if prompt_path.exists():
                prompt_path.unlink()
        except OSError:
            pass
    _prompt_files_to_cleanup.clear()


def _create_prompt_file(prompt: str, session_id: str) -> str:
    """
    Create a prompt file with secure permissions.

    The file is created in the system temp directory with restrictive
    permissions (owner read/write only) and tracked for cleanup on exit.

    Args:
        prompt: The prompt content to write
        session_id: Session ID for naming the file

    Returns:
        Path to the created temp file
    """
    global _atexit_registered

    # Create temp directory with restrictive permissions
    temp_dir = Path(tempfile.gettempdir()) / "gobby-prompts"
    temp_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

    # Create the prompt file path
    prompt_path = temp_dir / f"prompt-{session_id}.txt"

    # Write with secure permissions atomically - create with mode 0o600 from the start
    # This avoids the TOCTOU window between write_text and chmod
    fd = os.open(str(prompt_path), os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(prompt)
            f.flush()
            os.fsync(f.fileno())
    except Exception:
        # fd is closed by fdopen, but if fdopen fails we need to close it
        try:
            os.close(fd)
        except OSError:
            pass
        raise

    # Track for cleanup
    _prompt_files_to_cleanup.add(prompt_path)

    # Register cleanup handler once
    if not _atexit_registered:
        atexit.register(_cleanup_all_prompt_files)
        _atexit_registered = True

    logger.debug(f"Created secure prompt file: {prompt_path}")
    return str(prompt_path)


def build_cli_command(
    cli: str,
    prompt: str | None = None,
    session_id: str | None = None,
    auto_approve: bool = False,
    working_directory: str | None = None,
    mode: str = "terminal",
) -> list[str]:
    """
    Build the CLI command with proper prompt passing and permission flags.

    Each CLI has different syntax for passing prompts and handling permissions:

    Claude Code:
    - claude --session-id <uuid> --dangerously-skip-permissions [prompt]
    - Use --dangerously-skip-permissions for autonomous subagent operation

    Gemini CLI:
    - gemini -i "prompt" (interactive mode with initial prompt)
    - gemini --approval-mode yolo -i "prompt" (YOLO + interactive)
    - gemini "prompt" (one-shot non-interactive for headless)

    Codex CLI:
    - codex --full-auto -C <dir> [PROMPT]
    - Or: codex -c 'sandbox_permissions=["disk-full-read-access"]' -a never [PROMPT]

    Args:
        cli: CLI name (claude, gemini, codex)
        prompt: Optional prompt to pass
        session_id: Optional session ID (used by Claude CLI)
        auto_approve: If True, add flags to auto-approve actions/permissions
        working_directory: Optional working directory (used by Codex -C flag)
        mode: Execution mode - "terminal" (interactive) or "headless" (non-interactive)

    Returns:
        Command list for subprocess execution
    """
    command = [cli]

    if cli == "claude":
        # Claude CLI flags
        if session_id:
            command.extend(["--session-id", session_id])
        if auto_approve:
            # Skip all permission prompts for autonomous subagent operation
            command.append("--dangerously-skip-permissions")
        # For headless mode, use -p (print mode) for single-turn execution
        # For terminal mode, don't use -p to allow multi-turn interaction
        if prompt and mode != "terminal":
            command.append("-p")

    elif cli == "gemini":
        # Gemini CLI flags
        if auto_approve:
            command.extend(["--approval-mode", "yolo"])
        # For terminal mode, use -i (prompt-interactive) to execute prompt and stay interactive
        # For headless mode, use positional prompt for one-shot execution
        if prompt:
            if mode == "terminal":
                command.extend(["-i", prompt])
                return command  # Don't add prompt again as positional
            # else: fall through to add as positional for headless

    elif cli == "codex":
        # Codex CLI flags
        if auto_approve:
            # --full-auto: low-friction sandboxed automatic execution
            command.append("--full-auto")
        if working_directory:
            command.extend(["-C", working_directory])

    # All three CLIs accept prompt as positional argument (must come last)
    # For Gemini terminal mode, this is skipped (handled above with -i flag)
    if prompt:
        command.append(prompt)

    return command


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

        Returns:
            SpawnResult with success status
        """
        # Build command with prompt as CLI argument and auto-approve for autonomous work
        command = build_cli_command(
            cli,
            prompt=prompt,
            session_id=session_id,
            auto_approve=True,  # Subagents need to work autonomously
            working_directory=str(cwd) if cli == "codex" else None,
            mode="terminal",  # Interactive terminal mode
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

        Delegates to the module-level _create_prompt_file helper which
        handles secure permissions and cleanup tracking.

        Args:
            prompt: The prompt content
            session_id: Session ID for naming the file

        Returns:
            Path to the created temp file
        """
        return _create_prompt_file(prompt, session_id)


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
            prompt_file = _create_prompt_file(prompt, child_session.id)

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


def read_prompt_from_env() -> str | None:
    """
    Read initial prompt from environment variables.

    Checks GOBBY_PROMPT_FILE first (for long prompts),
    then falls back to GOBBY_PROMPT (for short prompts).

    Returns:
        Prompt string or None if not set
    """
    from gobby.agents.constants import GOBBY_PROMPT, GOBBY_PROMPT_FILE

    # Check for prompt file first
    prompt_file = os.environ.get(GOBBY_PROMPT_FILE)
    if prompt_file:
        try:
            prompt_path = Path(prompt_file)
            if prompt_path.exists():
                return prompt_path.read_text(encoding="utf-8")
            else:
                logger.warning(f"Prompt file not found: {prompt_file}")
        except Exception as e:
            logger.error(f"Error reading prompt file: {e}")

    # Fall back to inline prompt
    return os.environ.get(GOBBY_PROMPT)


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
            prompt_file = _create_prompt_file(prompt, child_session.id)

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


def build_gemini_command_with_resume(
    gemini_external_id: str,
    prompt: str | None = None,
    auto_approve: bool = False,
    gobby_session_id: str | None = None,
) -> list[str]:
    """
    Build Gemini CLI command with session resume.

    Uses -r flag to resume a preflight-captured session, with session context
    injected into the initial prompt.

    Args:
        gemini_external_id: Gemini's session_id from preflight capture
        prompt: Optional user prompt
        auto_approve: If True, add --approval-mode yolo
        gobby_session_id: Gobby session ID to inject into context

    Returns:
        Command list for subprocess execution
    """
    command = ["gemini"]

    # Resume the preflight session
    command.extend(["-r", gemini_external_id])

    if auto_approve:
        command.extend(["--approval-mode", "yolo"])

    # Build prompt with session context
    if gobby_session_id:
        context_prefix = (
            f"Your Gobby session_id is: {gobby_session_id}\n"
            f"Use this when calling Gobby MCP tools.\n\n"
        )
        full_prompt = context_prefix + (prompt or "")
    else:
        full_prompt = prompt or ""

    # Use -i for interactive mode with initial prompt
    if full_prompt:
        command.extend(["-i", full_prompt])

    return command


# =============================================================================
# Codex Preflight Capture
# =============================================================================


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
            prompt_file = _create_prompt_file(prompt, child_session.id)

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


def build_codex_command_with_resume(
    codex_external_id: str,
    prompt: str | None = None,
    auto_approve: bool = False,
    gobby_session_id: str | None = None,
    working_directory: str | None = None,
) -> list[str]:
    """
    Build Codex CLI command with session resume.

    Uses `codex resume {session_id}` to resume a preflight-captured session,
    with session context injected into the prompt.

    Args:
        codex_external_id: Codex's session_id from preflight capture
        prompt: Optional user prompt
        auto_approve: If True, add --full-auto flag
        gobby_session_id: Gobby session ID to inject into context
        working_directory: Optional working directory override

    Returns:
        Command list for subprocess execution
    """
    command = ["codex", "resume", codex_external_id]

    if auto_approve:
        command.append("--full-auto")

    if working_directory:
        command.extend(["-C", working_directory])

    # Build prompt with session context
    if gobby_session_id:
        context_prefix = (
            f"Your Gobby session_id is: {gobby_session_id}\n"
            f"Use this when calling Gobby MCP tools.\n\n"
        )
        full_prompt = context_prefix + (prompt or "")
    else:
        full_prompt = prompt or ""

    # Prompt is a positional argument after session_id
    if full_prompt:
        command.append(full_prompt)

    return command
