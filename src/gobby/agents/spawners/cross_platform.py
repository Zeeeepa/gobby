"""Cross-platform terminal spawners: Kitty, Alacritty, and tmux."""

from __future__ import annotations

import os
import platform
import shlex
import shutil
import subprocess  # nosec B404 - subprocess needed for terminal spawning
import time
from pathlib import Path

from gobby.agents.spawners.base import SpawnResult, TerminalSpawnerBase, TerminalType
from gobby.agents.tty_config import get_tty_config

__all__ = ["KittySpawner", "AlacrittySpawner", "TmuxSpawner"]


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


class TmuxSpawner(TerminalSpawnerBase):
    """
    Spawner for tmux terminal multiplexer.

    Creates a new detached tmux session that runs the command.
    The session can be attached to later with `tmux attach -t <session>`.
    """

    @property
    def terminal_type(self) -> TerminalType:
        return TerminalType.TMUX

    def is_available(self) -> bool:
        # tmux is available on macOS and Linux (not Windows natively)
        if platform.system() == "Windows":
            return False
        config = get_tty_config().get_terminal_config("tmux")
        if not config.enabled:
            return False
        command = config.command or "tmux"
        return shutil.which(command) is not None

    def spawn(
        self,
        command: list[str],
        cwd: str | Path,
        env: dict[str, str] | None = None,
        title: str | None = None,
    ) -> SpawnResult:
        try:
            tty_config = get_tty_config().get_terminal_config("tmux")
            cli_command = tty_config.command or "tmux"

            # Generate a unique session name based on title or timestamp
            session_name = title or f"gobby-{int(time.time())}"
            # Sanitize session name (tmux doesn't like dots or colons)
            session_name = session_name.replace(".", "-").replace(":", "-")

            # Build tmux command:
            # tmux new-session -d -s <name> -n <name> -c <cwd> <command> \
            #   \; set-option destroy-unattached off \
            #   \; set-environment VAR value ...
            # -d: detached (runs in background)
            # -s: session name
            # -n: window name (title)
            # -c: starting directory
            # The chained set-option prevents session destruction when user has
            # global destroy-unattached on (must be atomic with session creation)
            args = [
                cli_command,
                "new-session",
                "-d",  # Detached
                "-s",
                session_name,
                "-n",
                session_name,  # Window title
                "-c",
                str(cwd),
            ]

            # Add extra options from config
            args.extend(tty_config.options)

            # Build the command to run, injecting env vars if provided
            # We export env vars in the shell command so they're available to the process
            # (tmux set-environment only affects new processes, not the initial command)
            if env:
                # Build export statements for each env var
                exports = " ".join(
                    f"export {shlex.quote(k)}={shlex.quote(v)};" for k, v in env.items()
                )
                # Wrap command with exports
                shell_cmd = f"{exports} exec {shlex.join(command)}"
                args.extend(["sh", "-c", shell_cmd])
            elif len(command) == 1:
                args.append(command[0])
            else:
                # Use shell to handle complex commands with arguments
                args.extend(["sh", "-c", shlex.join(command)])

            # Chain set-option to disable destroy-unattached atomically
            # This prevents the session from being destroyed before we can configure it
            args.extend([";", "set-option", "-t", session_name, "destroy-unattached", "off"])

            spawn_env = os.environ.copy()
            if env:
                spawn_env.update(env)

            process = subprocess.Popen(  # nosec B603 - args built from config
                args,
                cwd=cwd,
                env=spawn_env,
                start_new_session=True,
            )

            # Wait for tmux to start (it exits quickly after creating the session)
            process.wait()

            if process.returncode != 0:
                return SpawnResult(
                    success=False,
                    message=f"tmux exited with code {process.returncode}",
                    error=f"tmux failed to create session '{session_name}'",
                )

            # pid=None since tmux process has exited; session_name is the identifier
            return SpawnResult(
                success=True,
                message=f"Spawned tmux session '{session_name}' (attach with: tmux attach -t {session_name})",
                pid=None,
                terminal_type=self.terminal_type.value,
            )

        except Exception as e:
            return SpawnResult(
                success=False,
                message=f"Failed to spawn tmux: {e}",
                error=str(e),
            )
