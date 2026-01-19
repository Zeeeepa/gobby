"""Base classes and types for terminal spawners."""

from __future__ import annotations

import os
import subprocess  # nosec B404 - subprocess needed for terminal spawning
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


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
    POWERSHELL = "powershell"
    WSL = "wsl"

    # Cross-platform multiplexer
    TMUX = "tmux"

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
    process: subprocess.Popen[Any] | None = None
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
