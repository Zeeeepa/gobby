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
"""

from gobby.agents.spawners.base import (
    EmbeddedPTYResult,
    HeadlessResult,
    SpawnMode,
    SpawnResult,
    TerminalSpawnerBase,
    TerminalType,
)
from gobby.agents.spawners.cross_platform import (
    AlacrittySpawner,
    KittySpawner,
    TmuxSpawner,
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
from gobby.agents.spawners.windows import (
    CmdSpawner,
    PowerShellSpawner,
    WindowsTerminalSpawner,
    WSLSpawner,
)

__all__ = [
    # Base types
    "SpawnMode",
    "TerminalType",
    "SpawnResult",
    "EmbeddedPTYResult",
    "HeadlessResult",
    "TerminalSpawnerBase",
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
]
