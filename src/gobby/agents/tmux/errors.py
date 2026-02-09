"""Custom exceptions for tmux module."""

from __future__ import annotations


class TmuxNotFoundError(RuntimeError):
    """Raised when the tmux binary is not installed or not on PATH."""

    def __init__(self, command: str = "tmux") -> None:
        super().__init__(
            f"tmux binary '{command}' not found. Install tmux to use tmux-based agent spawning."
        )
        self.command = command


class TmuxSessionError(RuntimeError):
    """Raised when a tmux session operation fails (create, kill, query)."""

    def __init__(self, message: str, session_name: str | None = None) -> None:
        prefix = f"tmux session '{session_name}': " if session_name else "tmux: "
        super().__init__(f"{prefix}{message}")
        self.session_name = session_name
