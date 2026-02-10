"""Terminal spawner implementations for agent execution.

This package provides Strategy pattern implementations for spawning
agents in various terminal types across different platforms.

Usage:
    from gobby.agents.spawners import (
        TerminalSpawnerBase,
        SpawnResult,
        TerminalType,
        SpawnMode,
        # Platform-specific spawners
        GhosttySpawner,
        ITermSpawner,
        # etc.
    )

    # Command building
    from gobby.agents.spawners import build_cli_command

    # Prompt file management
    from gobby.agents.spawners import create_prompt_file, read_prompt_from_env
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gobby.agents.tmux.spawner import TmuxSpawner as TmuxSpawner

from gobby.agents.spawners.base import (
    EmbeddedPTYResult,
    HeadlessResult,
    SpawnMode,
    SpawnResult,
    TerminalSpawnerBase,
    TerminalType,
    make_spawn_env,
)
from gobby.agents.spawners.command_builder import (
    build_cli_command,
    build_codex_command_with_resume,
    build_gemini_command_with_resume,
)
from gobby.agents.spawners.cross_platform import (
    AlacrittySpawner,
    KittySpawner,
)
from gobby.agents.spawners.embedded import EmbeddedSpawner
from gobby.agents.spawners.headless import HeadlessSpawner
from gobby.agents.spawners.linux import (
    GnomeTerminalSpawner,
    KonsoleSpawner,
)
from gobby.agents.spawners.macos import (
    GhosttySpawner,
    ITermSpawner,
    TerminalAppSpawner,
)
from gobby.agents.spawners.prompt_manager import (
    MAX_ENV_PROMPT_LENGTH,
    create_prompt_file,
    read_prompt_from_env,
)
from gobby.agents.spawners.windows import (
    CmdSpawner,
    PowerShellSpawner,
    WindowsTerminalSpawner,
    WSLSpawner,
)

# TmuxSpawner is lazily imported via __getattr__ to avoid circular imports
# (tmux.spawner imports from spawners.base, which triggers this __init__)

__all__ = [
    # Base types
    "SpawnMode",
    "TerminalType",
    "SpawnResult",
    "EmbeddedPTYResult",
    "HeadlessResult",
    "TerminalSpawnerBase",
    "make_spawn_env",
    # macOS spawners
    "GhosttySpawner",
    "ITermSpawner",
    "TerminalAppSpawner",
    # Linux spawners
    "GnomeTerminalSpawner",
    "KonsoleSpawner",
    # Windows spawners
    "WindowsTerminalSpawner",
    "CmdSpawner",
    "PowerShellSpawner",
    "WSLSpawner",
    # Cross-platform spawners
    "KittySpawner",
    "AlacrittySpawner",
    "TmuxSpawner",
    # Embedded/Headless spawners
    "EmbeddedSpawner",
    "HeadlessSpawner",
    # Command building
    "build_cli_command",
    "build_gemini_command_with_resume",
    "build_codex_command_with_resume",
    # Prompt management
    "MAX_ENV_PROMPT_LENGTH",
    "create_prompt_file",
    "read_prompt_from_env",
]


def __getattr__(name: str) -> Any:
    """Lazy import for TmuxSpawner to avoid circular imports."""
    if name == "TmuxSpawner":
        from gobby.agents.tmux.spawner import TmuxSpawner

        return TmuxSpawner
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
