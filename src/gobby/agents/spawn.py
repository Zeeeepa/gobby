"""Terminal spawning for agent execution."""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from gobby.agents.constants import get_terminal_env_vars

logger = logging.getLogger(__name__)


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
        return shutil.which("ghostty") is not None

    def spawn(
        self,
        command: list[str],
        cwd: str | Path,
        env: dict[str, str] | None = None,
        title: str | None = None,
    ) -> SpawnResult:
        try:
            # Build ghostty command
            args = ["ghostty", "-e", " ".join(command)]
            if title:
                args.extend(["--title", title])

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
            # Build AppleScript for iTerm
            cmd_str = " ".join(command)
            env_exports = ""
            if env:
                env_exports = " ".join(f'export {k}="{v}";' for k, v in env.items())

            script = f'''
            tell application "iTerm"
                create window with default profile
                tell current session of current window
                    write text "cd {cwd} && {env_exports} {cmd_str}"
                end tell
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
            cmd_str = " ".join(command)
            env_exports = ""
            if env:
                env_exports = " ".join(f'export {k}="{v}";' for k, v in env.items())

            script = f'''
            tell application "Terminal"
                do script "cd {cwd} && {env_exports} {cmd_str}"
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
            args = ["kitty", "--detach", "--directory", str(cwd)]
            if title:
                args.extend(["--title", title])
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
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
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
            cmd_str = " ".join(command)
            args = ["cmd", "/c", "start"]
            if title:
                args.append(title)
            args.extend(["cmd", "/k", f"cd /d {cwd} && {cmd_str}"])

            spawn_env = os.environ.copy()
            if env:
                spawn_env.update(env)

            process = subprocess.Popen(
                args,
                env=spawn_env,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
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

    def __init__(self):
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
            term_type
            for term_type, spawner in self._spawners.items()
            if spawner.is_available()
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
            prompt: Optional initial prompt (passed via temp file)

        Returns:
            SpawnResult with success status
        """
        # Build command
        command = [cli]
        if prompt:
            command.extend(["-p", prompt])

        # Build environment
        env = get_terminal_env_vars(
            session_id=session_id,
            parent_session_id=parent_session_id,
            agent_run_id=agent_run_id,
            project_id=project_id,
            workflow_name=workflow_name,
            agent_depth=agent_depth,
            max_agent_depth=max_agent_depth,
        )

        # Set title
        title = f"Gobby Agent: {cli} (depth={agent_depth})"

        return self.spawn(
            command=command,
            cwd=cwd,
            terminal=terminal,
            env=env,
            title=title,
        )
