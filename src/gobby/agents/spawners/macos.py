"""macOS terminal spawners: Ghostty, iTerm2, and Terminal.app."""

from __future__ import annotations

import os
import platform
import shlex
import shutil
import subprocess  # nosec B404 - subprocess needed for terminal spawning
import tempfile
from pathlib import Path

from gobby.agents.spawners.base import SpawnResult, TerminalSpawnerBase, TerminalType
from gobby.agents.tty_config import get_tty_config

__all__ = ["GhosttySpawner", "ITermSpawner", "TerminalAppSpawner"]


def escape_applescript(s: str) -> str:
    """Escape special characters for embedding in AppleScript strings.

    AppleScript uses backslash escaping for quotes and backslashes.
    """
    return s.replace("\\", "\\\\").replace('"', '\\"')


class GhosttySpawner(TerminalSpawnerBase):
    """Spawner for Ghostty terminal."""

    @property
    def terminal_type(self) -> TerminalType:
        return TerminalType.GHOSTTY

    def _is_ghostty_running(self) -> bool:
        """Check if Ghostty is currently running on macOS."""
        try:
            result = subprocess.run(  # nosec B603, B607 - osascript is safe
                [
                    "/usr/bin/osascript",
                    "-e",
                    'tell application "System Events" to (name of processes) contains "Ghostty"',
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.stdout.strip().lower() == "true"
        except Exception:
            # If we can't determine, assume running to use safer -n behavior
            return True

    def is_available(self) -> bool:
        config = get_tty_config().get_terminal_config("ghostty")
        if not config.enabled:
            return False
        # On macOS, check for the app bundle; on other platforms check CLI
        if platform.system() == "Darwin":
            app_path = config.app_path or "/Applications/Ghostty.app"
            return Path(app_path).exists()
        command = config.command or "ghostty"
        return shutil.which(command) is not None

    def spawn(
        self,
        command: list[str],
        cwd: str | Path,
        env: dict[str, str] | None = None,
        title: str | None = None,
    ) -> SpawnResult:
        try:
            tty_config = get_tty_config().get_terminal_config("ghostty")
            # On macOS, ghostty CLI doesn't support launching the emulator directly
            # Must use 'open -na Ghostty.app --args' instead
            # Note: Ghostty requires --key=value syntax, not --key value
            if platform.system() == "Darwin":
                app_path = tty_config.app_path or "/Applications/Ghostty.app"
                # Build args for open command
                # open -na /path/to/Ghostty.app --args [ghostty-options] -e [command]
                # Note: 'open' doesn't pass cwd, so we must use --working-directory
                ghostty_args = [f"--working-directory={cwd}"]
                if title:
                    ghostty_args.append(f"--title={title}")
                # Add any extra options from config
                ghostty_args.extend(tty_config.options)
                ghostty_args.extend(["-e"] + command)

                # Check if Ghostty is already running
                # If running: use -n to open a new window
                # If not running: omit -n to avoid double window on first launch
                ghostty_running = self._is_ghostty_running()
                if ghostty_running:
                    args = ["open", "-na", app_path, "--args"] + ghostty_args
                else:
                    args = ["open", "-a", app_path, "--args"] + ghostty_args
            else:
                # On Linux/other platforms, use ghostty CLI directly
                cli_command = tty_config.command or "ghostty"
                args = [cli_command]
                if title:
                    args.append(f"--title={title}")
                # Add any extra options from config
                args.extend(tty_config.options)
                args.extend(["-e"] + command)

            # Merge environment
            spawn_env = os.environ.copy()
            if env:
                spawn_env.update(env)

            # Spawn process
            process = subprocess.Popen(  # nosec B603 - args built from config
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
        config = get_tty_config().get_terminal_config("iterm")
        if not config.enabled:
            return False
        app_path = config.app_path or "/Applications/iTerm.app"
        return Path(app_path).exists()

    def spawn(
        self,
        command: list[str],
        cwd: str | Path,
        env: dict[str, str] | None = None,
        title: str | None = None,
    ) -> SpawnResult:
        try:
            # Write command to a temp script to avoid escaping issues
            # This is the most reliable way to pass complex commands to iTerm
            script_content = "#!/bin/bash\n"
            script_content += f"cd {shlex.quote(str(cwd))}\n"
            if env:
                for k, v in env.items():
                    if k.isidentifier():
                        script_content += f"export {k}={shlex.quote(v)}\n"
            script_content += shlex.join(command) + "\n"
            script_content += "exit\n"  # Exit shell so terminal window closes

            # Create temp script file
            script_dir = Path(tempfile.gettempdir()) / "gobby-scripts"
            script_dir.mkdir(parents=True, exist_ok=True)
            script_path = script_dir / f"iterm-{os.getpid()}-{id(command)}.sh"
            script_path.write_text(script_content)
            script_path.chmod(0o755)

            # Check if iTerm was running before we launch it
            # If running: create new window with command
            # If not running: use the default window that gets auto-created
            # Escape script_path to prevent AppleScript injection
            safe_script_path = escape_applescript(str(script_path))
            applescript = f"""
            set iTermWasRunning to application "iTerm" is running
            tell application "iTerm"
                activate
                if iTermWasRunning then
                    -- iTerm already running, create a new window
                    create window with default profile command "{safe_script_path}"
                else
                    -- iTerm just launched, use the default window
                    -- Wait for shell to be ready, then exec script (replaces shell so it closes when done)
                    delay 0.5
                    tell current session of current window
                        write text "exec {safe_script_path}"
                    end tell
                end if
            end tell
            """

            process = subprocess.Popen(  # nosec B603 - osascript with internal AppleScript
                ["/usr/bin/osascript", "-e", applescript],
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
        config = get_tty_config().get_terminal_config("terminal.app")
        if not config.enabled:
            return False
        app_path = config.app_path or "/System/Applications/Utilities/Terminal.app"
        return Path(app_path).exists()

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

            shell_command = f"cd {safe_cwd} && {env_exports} {cmd_str}"
            safe_shell_command = escape_applescript(shell_command)

            # Check if Terminal was running before we launch it
            # If running: do script creates a new window (correct behavior)
            # If not running: Terminal opens a default window on launch, so we use that
            # instead of calling do script (which would open a second window)
            script = f"""
            set termWasRunning to application "Terminal" is running
            tell application "Terminal"
                activate
                if termWasRunning then
                    -- Terminal already running, create a new window
                    do script "{safe_shell_command}"
                else
                    -- Terminal just launched, use the default window
                    -- Wait for shell to be ready, then exec our command
                    delay 0.3
                    tell front window
                        do script "{safe_shell_command}" in selected tab
                    end tell
                end if
            end tell
            """

            process = subprocess.Popen(  # nosec B603 - osascript with internal AppleScript
                ["/usr/bin/osascript", "-e", script],
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
