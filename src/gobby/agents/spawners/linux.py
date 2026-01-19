"""Linux terminal spawners: GNOME Terminal and Konsole."""

from __future__ import annotations

import os
import shutil
import subprocess  # nosec B404 - subprocess needed for terminal spawning
from pathlib import Path

from gobby.agents.spawners.base import SpawnResult, TerminalSpawnerBase, TerminalType
from gobby.agents.tty_config import get_tty_config

__all__ = ["GnomeTerminalSpawner", "KonsoleSpawner"]


class GnomeTerminalSpawner(TerminalSpawnerBase):
    """Spawner for GNOME Terminal."""

    @property
    def terminal_type(self) -> TerminalType:
        return TerminalType.GNOME_TERMINAL

    def is_available(self) -> bool:
        config = get_tty_config().get_terminal_config("gnome-terminal")
        if not config.enabled:
            return False
        command = config.command or "gnome-terminal"
        return shutil.which(command) is not None

    def spawn(
        self,
        command: list[str],
        cwd: str | Path,
        env: dict[str, str] | None = None,
        title: str | None = None,
    ) -> SpawnResult:
        try:
            tty_config = get_tty_config().get_terminal_config("gnome-terminal")
            cli_command = tty_config.command or "gnome-terminal"
            args = [cli_command, f"--working-directory={cwd}"]
            # Add extra options from config
            args.extend(tty_config.options)
            if title:
                args.extend(["--title", title])
            args.extend(["--", *command])

            spawn_env = os.environ.copy()
            if env:
                spawn_env.update(env)

            process = subprocess.Popen(  # nosec B603 - args built from config
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
        config = get_tty_config().get_terminal_config("konsole")
        if not config.enabled:
            return False
        command = config.command or "konsole"
        return shutil.which(command) is not None

    def spawn(
        self,
        command: list[str],
        cwd: str | Path,
        env: dict[str, str] | None = None,
        title: str | None = None,
    ) -> SpawnResult:
        try:
            tty_config = get_tty_config().get_terminal_config("konsole")
            cli_command = tty_config.command or "konsole"
            args = [cli_command, "--workdir", str(cwd)]
            # Add extra options from config
            args.extend(tty_config.options)
            if title:
                args.extend(["-p", f"tabtitle={title}"])
            args.extend(["-e", *command])

            spawn_env = os.environ.copy()
            if env:
                spawn_env.update(env)

            process = subprocess.Popen(  # nosec B603 - args built from config
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
