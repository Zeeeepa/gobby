"""Custom exceptions for tmux module."""

from __future__ import annotations

import platform


def _install_hint() -> str:
    """Return platform-specific tmux install instructions."""
    system = platform.system()
    if system == "Darwin":
        return "Install with: brew install tmux"
    elif system == "Windows":
        return "Install WSL (wsl --install), then: sudo apt install tmux"
    else:
        return "Install with: sudo apt install tmux  (or sudo dnf install tmux)"


class TmuxNotFoundError(RuntimeError):
    """Raised when the tmux binary is not installed or not on PATH."""

    def __init__(self, command: str = "tmux") -> None:
        hint = _install_hint()
        super().__init__(
            f"tmux binary '{command}' not found. {hint}"
        )
        self.command = command


class TmuxSessionError(RuntimeError):
    """Raised when a tmux session operation fails (create, kill, query)."""

    def __init__(self, message: str, session_name: str | None = None) -> None:
        prefix = f"tmux session '{session_name}': " if session_name else "tmux: "
        super().__init__(f"{prefix}{message}")
        self.session_name = session_name
