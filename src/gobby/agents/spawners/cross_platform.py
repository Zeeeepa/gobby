"""Cross-platform terminal spawners: Kitty and Alacritty.

Note: TmuxSpawner has been promoted to ``gobby.agents.tmux.spawner``.
"""

from __future__ import annotations

import platform
import shutil
import subprocess  # nosec B404 - subprocess needed for terminal spawning
from pathlib import Path

from gobby.agents.spawners.base import (
    SpawnResult,
    TerminalSpawnerBase,
    TerminalType,
    make_spawn_env,
)
from gobby.agents.tty_config import get_tty_config

__all__ = ["KittySpawner", "AlacrittySpawner"]


class KittySpawner(TerminalSpawnerBase):
    """Spawner for Kitty terminal."""

    @property
    def terminal_type(self) -> TerminalType:
        return TerminalType.KITTY

    def is_available(self) -> bool:
        config = get_tty_config().get_terminal_config("kitty")
        if not config.enabled:
            return False
        # On macOS, check app bundle; on other platforms check CLI
        if platform.system() == "Darwin":
            app_path = config.app_path or "/Applications/kitty.app"
            return Path(app_path).exists()
        command = config.command or "kitty"
        return shutil.which(command) is not None

    def spawn(
        self,
        command: list[str],
        cwd: str | Path,
        env: dict[str, str] | None = None,
        title: str | None = None,
    ) -> SpawnResult:
        try:
            tty_config = get_tty_config().get_terminal_config("kitty")
            if platform.system() == "Darwin":
                # On macOS, --detach doesn't work properly - command doesn't execute
                # Use direct path without --detach, subprocess handles backgrounding
                app_path = tty_config.app_path or "/Applications/kitty.app"
                kitty_path = f"{app_path}/Contents/MacOS/kitty"
                args = [kitty_path, "--directory", str(cwd)]
            else:
                # On Linux, --detach works correctly
                cli_command = tty_config.command or "kitty"
                args = [cli_command, "--detach", "--directory", str(cwd)]

            # Add extra options from config (includes confirm_os_window_close=0 by default)
            args.extend(tty_config.options)

            if title:
                args.extend(["--title", title])
            # Add end-of-options separator before the user command
            # This ensures command arguments starting with '-' are not interpreted as Kitty options
            args.append("--")
            args.extend(command)

            process = subprocess.Popen(  # nosec B603 - args built from config
                args,
                env=make_spawn_env(env),
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
        config = get_tty_config().get_terminal_config("alacritty")
        if not config.enabled:
            return False
        command = config.command or "alacritty"
        return shutil.which(command) is not None

    def spawn(
        self,
        command: list[str],
        cwd: str | Path,
        env: dict[str, str] | None = None,
        title: str | None = None,
    ) -> SpawnResult:
        try:
            tty_config = get_tty_config().get_terminal_config("alacritty")
            cli_command = tty_config.command or "alacritty"
            args = [cli_command, "--working-directory", str(cwd)]
            # Add extra options from config
            args.extend(tty_config.options)
            if title:
                args.extend(["--title", title])
            args.extend(["-e"] + command)

            process = subprocess.Popen(  # nosec B603 - args built from config
                args,
                env=make_spawn_env(env),
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
