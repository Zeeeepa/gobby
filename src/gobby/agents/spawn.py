"""Terminal spawning for agent execution."""

from __future__ import annotations

import asyncio
import atexit
import logging
import os
import platform
import shlex
import shutil
import stat
import subprocess
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

# pty is only available on Unix-like systems
try:
    import pty
except ImportError:
    pty = None  # type: ignore[assignment]

from gobby.agents.constants import get_terminal_env_vars
from gobby.agents.session import ChildSessionConfig, ChildSessionManager

# Maximum prompt length to pass via environment variable
# Longer prompts will be written to a temp file
MAX_ENV_PROMPT_LENGTH = 4096

logger = logging.getLogger(__name__)


def build_cli_command(
    cli: str,
    prompt: str | None = None,
    session_id: str | None = None,
    auto_approve: bool = False,
    working_directory: str | None = None,
) -> list[str]:
    """
    Build the CLI command with proper prompt passing and permission flags.

    Each CLI has different syntax for passing prompts and handling permissions:

    Claude Code:
    - claude --session-id <uuid> --dangerously-skip-permissions [prompt]
    - Use --dangerously-skip-permissions for autonomous subagent operation

    Gemini CLI:
    - gemini --approval-mode yolo [query..]
    - Or: gemini -y [query..] (yolo shorthand)

    Codex CLI:
    - codex --full-auto -C <dir> [PROMPT]
    - Or: codex -c 'sandbox_permissions=["disk-full-read-access"]' -a never [PROMPT]

    Args:
        cli: CLI name (claude, gemini, codex)
        prompt: Optional prompt to pass
        session_id: Optional session ID (used by Claude CLI)
        auto_approve: If True, add flags to auto-approve actions/permissions
        working_directory: Optional working directory (used by Codex -C flag)

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
        if prompt:
            # Use -p (print mode) for non-interactive execution that exits after processing
            command.append("-p")

    elif cli == "gemini":
        # Gemini CLI flags
        if auto_approve:
            command.extend(["--approval-mode", "yolo"])

    elif cli == "codex":
        # Codex CLI flags
        if auto_approve:
            # --full-auto: low-friction sandboxed automatic execution
            command.append("--full-auto")
        if working_directory:
            command.extend(["-C", working_directory])

    # All three CLIs accept prompt as positional argument (must come last)
    if prompt:
        command.append(prompt)

    return command


class SpawnMode(str, Enum):
    """Agent execution mode."""

    TERMINAL = "terminal"  # Spawn in external terminal window
    EMBEDDED = "embedded"  # Return PTY handle for UI attachment
    HEADLESS = "headless"  # Daemon captures output, no terminal visible
    IN_PROCESS = "in_process"  # Run via SDK in daemon process


class TerminalType(str, Enum):
    """Supported terminal types."""

    # macOS
    GHOSTTY = "ghostty"
    ITERM = "iterm"
    TERMINAL_APP = "terminal.app"
    KITTY = "kitty"
    ALACRITTY = "alacritty"

    # Linux
    GNOME_TERMINAL = "gnome-terminal"
    KONSOLE = "konsole"

    # Windows
    WINDOWS_TERMINAL = "windows-terminal"
    CMD = "cmd"

    # Auto-detect
    AUTO = "auto"


@dataclass
class SpawnResult:
    """Result of spawning a terminal process."""

    success: bool
    message: str
    pid: int | None = None
    terminal_type: str | None = None
    error: str | None = None


@dataclass
class EmbeddedPTYResult:
    """Result of spawning an embedded PTY process."""

    success: bool
    message: str
    master_fd: int | None = None
    """Master file descriptor for reading/writing to PTY."""
    slave_fd: int | None = None
    """Slave file descriptor (used by child process)."""
    pid: int | None = None
    """Child process PID."""
    error: str | None = None

    def close(self) -> None:
        """Close the PTY file descriptors."""
        if self.master_fd is not None:
            try:
                os.close(self.master_fd)
            except OSError:
                pass
        if self.slave_fd is not None:
            try:
                os.close(self.slave_fd)
            except OSError:
                pass


@dataclass
class HeadlessResult:
    """Result of spawning a headless process."""

    success: bool
    message: str
    pid: int | None = None
    """Child process PID."""
    process: subprocess.Popen | None = None
    """Subprocess handle for output capture."""
    output_buffer: list[str] = field(default_factory=list)
    """Captured output lines."""
    error: str | None = None

    def get_output(self) -> str:
        """Get all captured output as a string."""
        return "\n".join(self.output_buffer)


class TerminalSpawnerBase(ABC):
    """Base class for terminal spawners."""

    @property
    @abstractmethod
    def terminal_type(self) -> TerminalType:
        """The terminal type this spawner handles."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this terminal is available on the system."""
        pass

    @abstractmethod
    def spawn(
        self,
        command: list[str],
        cwd: str | Path,
        env: dict[str, str] | None = None,
        title: str | None = None,
    ) -> SpawnResult:
        """
        Spawn a new terminal window with the given command.

        Args:
            command: Command to run in the terminal
            cwd: Working directory
            env: Environment variables to set
            title: Optional window title

        Returns:
            SpawnResult with success status and process info
        """
        pass


class GhosttySpawner(TerminalSpawnerBase):
    """Spawner for Ghostty terminal."""

    @property
    def terminal_type(self) -> TerminalType:
        return TerminalType.GHOSTTY

    def is_available(self) -> bool:
        # On macOS, check for the app bundle; on other platforms check CLI
        if platform.system() == "Darwin":
            return Path("/Applications/Ghostty.app").exists()
        return shutil.which("ghostty") is not None

    def spawn(
        self,
        command: list[str],
        cwd: str | Path,
        env: dict[str, str] | None = None,
        title: str | None = None,
    ) -> SpawnResult:
        try:
            # On macOS, ghostty CLI doesn't support launching the emulator directly
            # Must use 'open -na Ghostty.app --args' instead
            # Note: Ghostty requires --key=value syntax, not --key value
            if platform.system() == "Darwin":
                # Build args for open command
                # open -na Ghostty.app --args [ghostty-options] -e [command]
                # Note: 'open' doesn't pass cwd, so we must use --working-directory
                ghostty_args = [f"--working-directory={cwd}"]
                if title:
                    ghostty_args.append(f"--title={title}")
                ghostty_args.extend(["-e"] + command)

                args = ["open", "-na", "Ghostty.app", "--args"] + ghostty_args
            else:
                # On Linux/other platforms, use ghostty CLI directly
                args = ["ghostty"]
                if title:
                    args.append(f"--title={title}")
                args.extend(["-e"] + command)

            # Merge environment
            spawn_env = os.environ.copy()
            if env:
                spawn_env.update(env)

            # Spawn process
            process = subprocess.Popen(
                args,
                cwd=cwd,
                env=spawn_env,
                start_new_session=True,
            )

            return SpawnResult(
                success=True,
                message=f"Spawned Ghostty with PID {process.pid}",
                pid=process.pid,
                terminal_type=self.terminal_type.value,
            )

        except Exception as e:
            return SpawnResult(
                success=False,
                message=f"Failed to spawn Ghostty: {e}",
                error=str(e),
            )


class ITermSpawner(TerminalSpawnerBase):
    """Spawner for iTerm2 on macOS."""

    @property
    def terminal_type(self) -> TerminalType:
        return TerminalType.ITERM

    def is_available(self) -> bool:
        if platform.system() != "Darwin":
            return False
        return Path("/Applications/iTerm.app").exists()

    def spawn(
        self,
        command: list[str],
        cwd: str | Path,
        env: dict[str, str] | None = None,
        title: str | None = None,
    ) -> SpawnResult:
        try:
            # Build AppleScript for iTerm with proper escaping
            # Shell-quote the command to prevent injection
            cmd_str = shlex.join(command)

            # Shell-quote environment variable assignments
            env_exports = ""
            if env:
                # Quote both keys and values to prevent injection
                exports = []
                for k, v in env.items():
                    # Validate key is a valid shell variable name
                    if k.isidentifier():
                        exports.append(f"export {k}={shlex.quote(v)};")
                env_exports = " ".join(exports)

            # Quote cwd for shell
            safe_cwd = shlex.quote(str(cwd))

            # Escape special characters for AppleScript string
            # AppleScript uses backslash escaping for quotes and backslashes
            def escape_applescript(s: str) -> str:
                return s.replace("\\", "\\\\").replace('"', '\\"')

            shell_command = f"cd {safe_cwd} && {env_exports} {cmd_str}"
            safe_shell_command = escape_applescript(shell_command)

            # Use 'create window with default profile command' to execute the command
            # directly when creating the window. This avoids timing issues with 'write text'
            # and ensures exactly one window with one command execution.
            script = f'''
            tell application "iTerm"
                activate
                create window with default profile command "{safe_shell_command}"
            end tell
            '''

            process = subprocess.Popen(
                ["osascript", "-e", script],
                start_new_session=True,
            )

            return SpawnResult(
                success=True,
                message="Spawned iTerm window",
                pid=process.pid,
                terminal_type=self.terminal_type.value,
            )

        except Exception as e:
            return SpawnResult(
                success=False,
                message=f"Failed to spawn iTerm: {e}",
                error=str(e),
            )


class TerminalAppSpawner(TerminalSpawnerBase):
    """Spawner for Terminal.app on macOS."""

    @property
    def terminal_type(self) -> TerminalType:
        return TerminalType.TERMINAL_APP

    def is_available(self) -> bool:
        if platform.system() != "Darwin":
            return False
        return Path("/System/Applications/Utilities/Terminal.app").exists()

    def spawn(
        self,
        command: list[str],
        cwd: str | Path,
        env: dict[str, str] | None = None,
        title: str | None = None,
    ) -> SpawnResult:
        try:
            # Build AppleScript for Terminal.app with proper escaping
            # Shell-quote the command to prevent injection
            cmd_str = shlex.join(command)

            # Shell-quote environment variable assignments
            env_exports = ""
            if env:
                # Quote both keys and values to prevent injection
                exports = []
                for k, v in env.items():
                    # Validate key is a valid shell variable name
                    if k.isidentifier():
                        exports.append(f"export {k}={shlex.quote(v)};")
                env_exports = " ".join(exports)

            # Quote cwd for shell
            safe_cwd = shlex.quote(str(cwd))

            # Escape special characters for AppleScript string
            # AppleScript uses backslash escaping for quotes and backslashes
            def escape_applescript(s: str) -> str:
                return s.replace("\\", "\\\\").replace('"', '\\"')

            shell_command = f"cd {safe_cwd} && {env_exports} {cmd_str}"
            safe_shell_command = escape_applescript(shell_command)

            script = f'''
            tell application "Terminal"
                do script "{safe_shell_command}"
                activate
            end tell
            '''

            process = subprocess.Popen(
                ["osascript", "-e", script],
                start_new_session=True,
            )

            return SpawnResult(
                success=True,
                message="Spawned Terminal.app window",
                pid=process.pid,
                terminal_type=self.terminal_type.value,
            )

        except Exception as e:
            return SpawnResult(
                success=False,
                message=f"Failed to spawn Terminal.app: {e}",
                error=str(e),
            )


class KittySpawner(TerminalSpawnerBase):
    """Spawner for Kitty terminal."""

    @property
    def terminal_type(self) -> TerminalType:
        return TerminalType.KITTY

    def is_available(self) -> bool:
        return shutil.which("kitty") is not None

    def spawn(
        self,
        command: list[str],
        cwd: str | Path,
        env: dict[str, str] | None = None,
        title: str | None = None,
    ) -> SpawnResult:
        try:
            if platform.system() == "Darwin":
                # On macOS, --detach doesn't work properly - command doesn't execute
                # Use direct path without --detach, subprocess handles backgrounding
                kitty_path = "/Applications/kitty.app/Contents/MacOS/kitty"
                args = [kitty_path, "--directory", str(cwd)]
            else:
                # On Linux, --detach works correctly
                args = ["kitty", "--detach", "--directory", str(cwd)]

            # Disable close confirmation prompt for agent windows
            args.extend(["-o", "confirm_os_window_close=0"])

            if title:
                args.extend(["--title", title])
            # Add end-of-options separator before the user command
            # This ensures command arguments starting with '-' are not interpreted as Kitty options
            args.append("--")
            args.extend(command)

            spawn_env = os.environ.copy()
            if env:
                spawn_env.update(env)

            process = subprocess.Popen(
                args,
                env=spawn_env,
                start_new_session=True,
            )

            return SpawnResult(
                success=True,
                message=f"Spawned Kitty with PID {process.pid}",
                pid=process.pid,
                terminal_type=self.terminal_type.value,
            )

        except Exception as e:
            return SpawnResult(
                success=False,
                message=f"Failed to spawn Kitty: {e}",
                error=str(e),
            )


class AlacrittySpawner(TerminalSpawnerBase):
    """Spawner for Alacritty terminal."""

    @property
    def terminal_type(self) -> TerminalType:
        return TerminalType.ALACRITTY

    def is_available(self) -> bool:
        return shutil.which("alacritty") is not None

    def spawn(
        self,
        command: list[str],
        cwd: str | Path,
        env: dict[str, str] | None = None,
        title: str | None = None,
    ) -> SpawnResult:
        try:
            args = ["alacritty", "--working-directory", str(cwd)]
            if title:
                args.extend(["--title", title])
            args.extend(["-e"] + command)

            spawn_env = os.environ.copy()
            if env:
                spawn_env.update(env)

            process = subprocess.Popen(
                args,
                env=spawn_env,
                start_new_session=True,
            )

            return SpawnResult(
                success=True,
                message=f"Spawned Alacritty with PID {process.pid}",
                pid=process.pid,
                terminal_type=self.terminal_type.value,
            )

        except Exception as e:
            return SpawnResult(
                success=False,
                message=f"Failed to spawn Alacritty: {e}",
                error=str(e),
            )


class GnomeTerminalSpawner(TerminalSpawnerBase):
    """Spawner for GNOME Terminal."""

    @property
    def terminal_type(self) -> TerminalType:
        return TerminalType.GNOME_TERMINAL

    def is_available(self) -> bool:
        return shutil.which("gnome-terminal") is not None

    def spawn(
        self,
        command: list[str],
        cwd: str | Path,
        env: dict[str, str] | None = None,
        title: str | None = None,
    ) -> SpawnResult:
        try:
            args = ["gnome-terminal", f"--working-directory={cwd}"]
            if title:
                args.extend(["--title", title])
            args.extend(["--", *command])

            spawn_env = os.environ.copy()
            if env:
                spawn_env.update(env)

            process = subprocess.Popen(
                args,
                env=spawn_env,
                start_new_session=True,
            )

            return SpawnResult(
                success=True,
                message=f"Spawned GNOME Terminal with PID {process.pid}",
                pid=process.pid,
                terminal_type=self.terminal_type.value,
            )

        except Exception as e:
            return SpawnResult(
                success=False,
                message=f"Failed to spawn GNOME Terminal: {e}",
                error=str(e),
            )


class KonsoleSpawner(TerminalSpawnerBase):
    """Spawner for KDE Konsole."""

    @property
    def terminal_type(self) -> TerminalType:
        return TerminalType.KONSOLE

    def is_available(self) -> bool:
        return shutil.which("konsole") is not None

    def spawn(
        self,
        command: list[str],
        cwd: str | Path,
        env: dict[str, str] | None = None,
        title: str | None = None,
    ) -> SpawnResult:
        try:
            args = ["konsole", "--workdir", str(cwd)]
            if title:
                args.extend(["-p", f"tabtitle={title}"])
            args.extend(["-e", *command])

            spawn_env = os.environ.copy()
            if env:
                spawn_env.update(env)

            process = subprocess.Popen(
                args,
                env=spawn_env,
                start_new_session=True,
            )

            return SpawnResult(
                success=True,
                message=f"Spawned Konsole with PID {process.pid}",
                pid=process.pid,
                terminal_type=self.terminal_type.value,
            )

        except Exception as e:
            return SpawnResult(
                success=False,
                message=f"Failed to spawn Konsole: {e}",
                error=str(e),
            )


class WindowsTerminalSpawner(TerminalSpawnerBase):
    """Spawner for Windows Terminal."""

    @property
    def terminal_type(self) -> TerminalType:
        return TerminalType.WINDOWS_TERMINAL

    def is_available(self) -> bool:
        if platform.system() != "Windows":
            return False
        return shutil.which("wt") is not None

    def spawn(
        self,
        command: list[str],
        cwd: str | Path,
        env: dict[str, str] | None = None,
        title: str | None = None,
    ) -> SpawnResult:
        try:
            args = ["wt", "-d", str(cwd)]
            if title:
                args.extend(["--title", title])
            args.extend(["--", *command])

            spawn_env = os.environ.copy()
            if env:
                spawn_env.update(env)

            process = subprocess.Popen(
                args,
                env=spawn_env,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,  # type: ignore[attr-defined]
            )

            return SpawnResult(
                success=True,
                message=f"Spawned Windows Terminal with PID {process.pid}",
                pid=process.pid,
                terminal_type=self.terminal_type.value,
            )

        except Exception as e:
            return SpawnResult(
                success=False,
                message=f"Failed to spawn Windows Terminal: {e}",
                error=str(e),
            )


class CmdSpawner(TerminalSpawnerBase):
    """Spawner for Windows cmd.exe."""

    @property
    def terminal_type(self) -> TerminalType:
        return TerminalType.CMD

    def is_available(self) -> bool:
        return platform.system() == "Windows"

    def spawn(
        self,
        command: list[str],
        cwd: str | Path,
        env: dict[str, str] | None = None,
        title: str | None = None,
    ) -> SpawnResult:
        try:
            # Build the inner command as a list and convert safely with list2cmdline
            # This properly escapes all arguments to prevent command injection
            cd_cmd = ["cd", "/d", str(cwd)]
            # Build full command list: cd /d path && original_command
            # list2cmdline handles proper escaping for Windows
            inner_cmd = subprocess.list2cmdline(cd_cmd) + " && " + subprocess.list2cmdline(command)

            args = ["cmd", "/c", "start"]
            if title:
                # Title must be quoted if it contains spaces
                args.append(subprocess.list2cmdline([title]))
            # Use empty title if none provided (required for start command when path is quoted)
            else:
                args.append('""')
            # Pass the inner command as a single argument to cmd /k
            args.extend(["cmd", "/k", inner_cmd])

            spawn_env = os.environ.copy()
            if env:
                spawn_env.update(env)

            process = subprocess.Popen(
                args,
                env=spawn_env,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,  # type: ignore[attr-defined]
            )

            return SpawnResult(
                success=True,
                message=f"Spawned cmd.exe with PID {process.pid}",
                pid=process.pid,
                terminal_type=self.terminal_type.value,
            )

        except Exception as e:
            return SpawnResult(
                success=False,
                message=f"Failed to spawn cmd.exe: {e}",
                error=str(e),
            )


class TerminalSpawner:
    """
    Main terminal spawner that auto-detects and uses available terminals.

    Provides a unified interface for spawning terminal processes across
    different platforms and terminal emulators.
    """

    # Terminal preference order by platform
    MACOS_PREFERENCE = [
        GhosttySpawner,
        ITermSpawner,
        KittySpawner,
        AlacrittySpawner,
        TerminalAppSpawner,
    ]

    LINUX_PREFERENCE = [
        GhosttySpawner,
        KittySpawner,
        GnomeTerminalSpawner,
        KonsoleSpawner,
        AlacrittySpawner,
    ]

    WINDOWS_PREFERENCE = [
        WindowsTerminalSpawner,
        AlacrittySpawner,
        CmdSpawner,
    ]

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
        ]

        for spawner in all_spawners:
            self._spawners[spawner.terminal_type] = spawner

    def get_available_terminals(self) -> list[TerminalType]:
        """Get list of available terminals on this system."""
        return [
            term_type for term_type, spawner in self._spawners.items() if spawner.is_available()
        ]

    def get_preferred_terminal(self) -> TerminalType | None:
        """Get the preferred available terminal for this platform."""
        system = platform.system()

        if system == "Darwin":
            preferences = self.MACOS_PREFERENCE
        elif system == "Windows":
            preferences = self.WINDOWS_PREFERENCE
        else:
            preferences = self.LINUX_PREFERENCE

        for spawner_cls in preferences:
            spawner = spawner_cls()  # type: ignore[abstract]
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

        The file is created in the system temp directory and named
        with the session ID for easy identification. The file has
        restrictive permissions (owner read/write only) and is
        registered for cleanup on process exit.

        Args:
            prompt: The prompt content
            session_id: Session ID for naming the file

        Returns:
            Path to the created temp file
        """
        # Create temp file with session ID in name
        temp_dir = Path(tempfile.gettempdir()) / "gobby-prompts"
        temp_dir.mkdir(parents=True, exist_ok=True)

        prompt_path = temp_dir / f"prompt-{session_id}.txt"
        prompt_path.write_text(prompt, encoding="utf-8")

        # Set restrictive permissions (owner read/write only)
        prompt_path.chmod(stat.S_IRUSR | stat.S_IWUSR)

        # Register for cleanup on process exit
        def cleanup_prompt_file() -> None:
            try:
                if prompt_path.exists():
                    prompt_path.unlink()
            except OSError:
                pass

        atexit.register(cleanup_prompt_file)

        logger.debug(f"Wrote prompt to temp file: {prompt_path}")
        return str(prompt_path)


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
            # Write to temp file
            temp_dir = Path(tempfile.gettempdir()) / "gobby-prompts"
            temp_dir.mkdir(parents=True, exist_ok=True)
            prompt_path = temp_dir / f"prompt-{child_session.id}.txt"
            prompt_path.write_text(prompt, encoding="utf-8")
            prompt_file = str(prompt_path)

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


class EmbeddedSpawner:
    """
    Spawner for embedded mode with PTY.

    Creates a pseudo-terminal that can be attached to a UI component.
    The master file descriptor can be used to read/write to the process.
    """

    def spawn(
        self,
        command: list[str],
        cwd: str | Path,
        env: dict[str, str] | None = None,
    ) -> EmbeddedPTYResult:
        """
        Spawn a process with a PTY for embedded mode.

        Args:
            command: Command to run
            cwd: Working directory
            env: Environment variables to set

        Returns:
            EmbeddedPTYResult with PTY file descriptors and process info
        """
        if platform.system() == "Windows" or pty is None:
            return EmbeddedPTYResult(
                success=False,
                message="Embedded PTY mode not supported on Windows",
                error="Windows does not support Unix PTY",
            )

        master_fd: int | None = None
        slave_fd: int | None = None

        try:
            # Create pseudo-terminal
            master_fd, slave_fd = pty.openpty()

            # Merge environment
            spawn_env = os.environ.copy()
            if env:
                spawn_env.update(env)

            # Fork and exec
            pid = os.fork()

            if pid == 0:
                # Child process
                try:
                    # Close master fd in child - not needed
                    os.close(master_fd)

                    # Create new session
                    os.setsid()

                    # Set slave as controlling terminal
                    os.dup2(slave_fd, 0)  # stdin
                    os.dup2(slave_fd, 1)  # stdout
                    os.dup2(slave_fd, 2)  # stderr

                    # Close original slave fd after duplication
                    os.close(slave_fd)

                    # Change to working directory
                    os.chdir(cwd)

                    # Execute command
                    os.execvpe(command[0], command, spawn_env)
                except Exception:
                    # Ensure we exit on any failure
                    os._exit(1)

                # Should never reach here, but just in case
                os._exit(1)
            else:
                # Parent process - close slave fd (child has its own copy)
                os.close(slave_fd)
                slave_fd = None  # Mark as closed

                return EmbeddedPTYResult(
                    success=True,
                    message=f"Spawned embedded PTY with PID {pid}",
                    master_fd=master_fd,
                    slave_fd=None,  # Closed in parent
                    pid=pid,
                )

        except Exception as e:
            # Clean up file descriptors on any error
            if master_fd is not None:
                try:
                    os.close(master_fd)
                except OSError:
                    pass
            if slave_fd is not None:
                try:
                    os.close(slave_fd)
                except OSError:
                    pass
            return EmbeddedPTYResult(
                success=False,
                message=f"Failed to spawn embedded PTY: {e}",
                error=str(e),
            )

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
        prompt: str | None = None,
    ) -> EmbeddedPTYResult:
        """
        Spawn a CLI agent with embedded PTY.

        Args:
            cli: CLI to run
            cwd: Working directory
            session_id: Pre-created child session ID
            parent_session_id: Parent session ID
            agent_run_id: Agent run record ID
            project_id: Project ID
            workflow_name: Optional workflow to activate
            agent_depth: Current nesting depth
            max_agent_depth: Maximum allowed depth
            prompt: Optional initial prompt

        Returns:
            EmbeddedPTYResult with PTY info
        """
        # Build command with prompt as CLI argument and auto-approve for autonomous work
        command = build_cli_command(
            cli,
            prompt=prompt,
            session_id=session_id,
            auto_approve=True,  # Subagents need to work autonomously
            working_directory=str(cwd) if cli == "codex" else None,
        )

        # Handle prompt for environment variables (backup for hooks/context)
        prompt_env: str | None = None
        prompt_file: str | None = None

        if prompt:
            if len(prompt) <= MAX_ENV_PROMPT_LENGTH:
                prompt_env = prompt
            else:
                temp_dir = Path(tempfile.gettempdir()) / "gobby-prompts"
                temp_dir.mkdir(parents=True, exist_ok=True)
                prompt_path = temp_dir / f"prompt-{session_id}.txt"
                prompt_path.write_text(prompt, encoding="utf-8")
                prompt_file = str(prompt_path)

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

        return self.spawn(command, cwd, env)


class HeadlessSpawner:
    """
    Spawner for headless mode with output capture.

    Runs the process without a visible terminal, capturing all output
    to a buffer that can be stored in the session transcript.
    """

    def spawn(
        self,
        command: list[str],
        cwd: str | Path,
        env: dict[str, str] | None = None,
    ) -> HeadlessResult:
        """
        Spawn a headless process with output capture.

        Args:
            command: Command to run
            cwd: Working directory
            env: Environment variables to set

        Returns:
            HeadlessResult with process handle for output capture
        """
        try:
            # Merge environment
            spawn_env = os.environ.copy()
            if env:
                spawn_env.update(env)

            # Spawn process with captured output
            process = subprocess.Popen(
                command,
                cwd=cwd,
                env=spawn_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE,
                text=True,
                bufsize=1,  # Line buffered
            )

            return HeadlessResult(
                success=True,
                message=f"Spawned headless process with PID {process.pid}",
                pid=process.pid,
                process=process,
            )

        except Exception as e:
            return HeadlessResult(
                success=False,
                message=f"Failed to spawn headless process: {e}",
                error=str(e),
            )

    async def spawn_and_capture(
        self,
        command: list[str],
        cwd: str | Path,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
        on_output: Any | None = None,
    ) -> HeadlessResult:
        """
        Spawn a headless process and capture output asynchronously.

        Args:
            command: Command to run
            cwd: Working directory
            env: Environment variables to set
            timeout: Optional timeout in seconds
            on_output: Optional callback for each line of output

        Returns:
            HeadlessResult with captured output
        """
        result = self.spawn(command, cwd, env)
        if not result.success or result.process is None:
            return result

        try:
            # Read output asynchronously
            async def read_output() -> None:
                if result.process and result.process.stdout:
                    loop = asyncio.get_running_loop()
                    while True:
                        line = await loop.run_in_executor(
                            None, result.process.stdout.readline
                        )
                        if not line:
                            break
                        line = line.rstrip("\n")
                        result.output_buffer.append(line)
                        if on_output:
                            on_output(line)

            if timeout:
                await asyncio.wait_for(read_output(), timeout=timeout)
            else:
                await read_output()

            # Wait for process to complete without blocking the event loop
            if result.process:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, result.process.wait)

        except TimeoutError:
            if result.process:
                result.process.terminate()
                # Also wait for termination to complete (non-blocking)
                try:
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(None, result.process.wait)
                except Exception:
                    pass
            result.error = "Process timed out"

        except Exception as e:
            result.error = str(e)

        return result

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
        prompt: str | None = None,
    ) -> HeadlessResult:
        """
        Spawn a CLI agent in headless mode.

        Args:
            cli: CLI to run
            cwd: Working directory
            session_id: Pre-created child session ID
            parent_session_id: Parent session ID
            agent_run_id: Agent run record ID
            project_id: Project ID
            workflow_name: Optional workflow to activate
            agent_depth: Current nesting depth
            max_agent_depth: Maximum allowed depth
            prompt: Optional initial prompt

        Returns:
            HeadlessResult with process handle
        """
        # Build command with prompt as CLI argument and auto-approve for autonomous work
        command = build_cli_command(
            cli,
            prompt=prompt,
            session_id=session_id,
            auto_approve=True,  # Subagents need to work autonomously
            working_directory=str(cwd) if cli == "codex" else None,
        )

        # Handle prompt for environment variables (backup for hooks/context)
        prompt_env: str | None = None
        prompt_file: str | None = None

        if prompt:
            if len(prompt) <= MAX_ENV_PROMPT_LENGTH:
                prompt_env = prompt
            else:
                temp_dir = Path(tempfile.gettempdir()) / "gobby-prompts"
                temp_dir.mkdir(parents=True, exist_ok=True)
                prompt_path = temp_dir / f"prompt-{session_id}.txt"
                prompt_path.write_text(prompt, encoding="utf-8")
                prompt_file = str(prompt_path)

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

        return self.spawn(command, cwd, env)
