"""Windows terminal spawners: Windows Terminal, cmd, PowerShell, and WSL."""

from __future__ import annotations

import os
import platform
import shlex
import shutil
import subprocess  # nosec B404 - subprocess needed for terminal spawning
from pathlib import Path

from gobby.agents.spawners.base import SpawnResult, TerminalSpawnerBase, TerminalType
from gobby.agents.tty_config import get_tty_config

__all__ = ["WindowsTerminalSpawner", "CmdSpawner", "PowerShellSpawner", "WSLSpawner"]


class WindowsTerminalSpawner(TerminalSpawnerBase):
    """Spawner for Windows Terminal."""

    @property
    def terminal_type(self) -> TerminalType:
        return TerminalType.WINDOWS_TERMINAL

    def is_available(self) -> bool:
        if platform.system() != "Windows":
            return False
        config = get_tty_config().get_terminal_config("windows-terminal")
        if not config.enabled:
            return False
        command = config.command or "wt"
        return shutil.which(command) is not None

    def spawn(
        self,
        command: list[str],
        cwd: str | Path,
        env: dict[str, str] | None = None,
        title: str | None = None,
    ) -> SpawnResult:
        try:
            tty_config = get_tty_config().get_terminal_config("windows-terminal")
            cli_command = tty_config.command or "wt"
            args = [cli_command, "-d", str(cwd)]
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
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
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
        if platform.system() != "Windows":
            return False
        config = get_tty_config().get_terminal_config("cmd")
        return config.enabled

    def spawn(
        self,
        command: list[str],
        cwd: str | Path,
        env: dict[str, str] | None = None,
        title: str | None = None,
    ) -> SpawnResult:
        try:
            # Build the inner command as a list and convert safely with list2cmdline
            # This properly escapes all arguments to prevent command injection
            cd_cmd = ["cd", "/d", str(cwd)]
            # Build full command list: cd /d path && original_command
            # list2cmdline handles proper escaping for Windows
            inner_cmd = subprocess.list2cmdline(cd_cmd) + " && " + subprocess.list2cmdline(command)

            args = ["cmd", "/c", "start"]
            if title:
                # Title must be quoted if it contains spaces
                args.append(subprocess.list2cmdline([title]))
            # Use empty title if none provided (required for start command when path is quoted)
            else:
                args.append('""')
            # Pass the inner command as a single argument to cmd /k
            args.extend(["cmd", "/k", inner_cmd])

            spawn_env = os.environ.copy()
            if env:
                spawn_env.update(env)

            process = subprocess.Popen(  # nosec B603 - args built from config
                args,
                env=spawn_env,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
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


class PowerShellSpawner(TerminalSpawnerBase):
    """Spawner for Windows PowerShell."""

    @property
    def terminal_type(self) -> TerminalType:
        return TerminalType.POWERSHELL

    def is_available(self) -> bool:
        if platform.system() != "Windows":
            return False
        config = get_tty_config().get_terminal_config("powershell")
        if not config.enabled:
            return False
        # Check for pwsh (PowerShell Core) first, then powershell (Windows PowerShell)
        command = config.command or "pwsh"
        if shutil.which(command) is not None:
            return True
        # Fall back to Windows PowerShell
        return shutil.which("powershell") is not None

    def spawn(
        self,
        command: list[str],
        cwd: str | Path,
        env: dict[str, str] | None = None,
        title: str | None = None,
    ) -> SpawnResult:
        try:
            tty_config = get_tty_config().get_terminal_config("powershell")
            # Prefer pwsh (PowerShell Core) over powershell (Windows PowerShell)
            cli_command = tty_config.command or "pwsh"
            if shutil.which(cli_command) is None:
                cli_command = "powershell"

            # Build the inner command to run
            # PowerShell requires special escaping for the -Command parameter
            inner_cmd = subprocess.list2cmdline(command)

            # Escape values for PowerShell single-quoted strings (double any single quotes)
            safe_cwd = "'" + str(cwd).replace("'", "''") + "'"
            safe_inner_cmd = inner_cmd.replace("'", "''")

            # Build PowerShell command:
            # Start-Process spawns a new window, -WorkingDirectory sets cwd
            # -NoExit keeps the window open after command completes
            ps_script = f"Set-Location -Path {safe_cwd}; {safe_inner_cmd}"

            args = ["cmd", "/c", "start", "", cli_command]
            # Add extra options from config
            args.extend(tty_config.options)
            if title:
                # Escape title for PowerShell
                safe_title = "'" + title.replace("'", "''") + "'"
                args.extend(["-Title", safe_title])
            args.extend(["-NoExit", "-Command", ps_script])

            spawn_env = os.environ.copy()
            if env:
                spawn_env.update(env)

            process = subprocess.Popen(  # nosec B603 - args built from config
                args,
                env=spawn_env,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )

            return SpawnResult(
                success=True,
                message=f"Spawned PowerShell with PID {process.pid}",
                pid=process.pid,
                terminal_type=self.terminal_type.value,
            )

        except Exception as e:
            return SpawnResult(
                success=False,
                message=f"Failed to spawn PowerShell: {e}",
                error=str(e),
            )


class WSLSpawner(TerminalSpawnerBase):
    """Spawner for Windows Subsystem for Linux (WSL2)."""

    @property
    def terminal_type(self) -> TerminalType:
        return TerminalType.WSL

    def is_available(self) -> bool:
        if platform.system() != "Windows":
            return False
        config = get_tty_config().get_terminal_config("wsl")
        if not config.enabled:
            return False
        command = config.command or "wsl"
        return shutil.which(command) is not None

    def spawn(
        self,
        command: list[str],
        cwd: str | Path,
        env: dict[str, str] | None = None,
        title: str | None = None,
    ) -> SpawnResult:
        try:
            tty_config = get_tty_config().get_terminal_config("wsl")
            cli_command = tty_config.command or "wsl"

            # Convert Windows path to WSL path if needed
            # e.g., C:\Users\foo -> /mnt/c/Users/foo
            cwd_str = str(cwd)
            if len(cwd_str) >= 2 and cwd_str[1] == ":":
                # Windows absolute path - convert to WSL format
                drive = cwd_str[0].lower()
                wsl_path = f"/mnt/{drive}{cwd_str[2:].replace(chr(92), '/')}"
            else:
                wsl_path = cwd_str

            # Build the command to run inside WSL
            # Escape for bash shell inside WSL
            inner_parts = [shlex.quote(part) for part in command]
            inner_cmd = " ".join(inner_parts)
            wsl_script = f"cd {shlex.quote(wsl_path)} && {inner_cmd}"

            # Build environment exports for WSL
            env_exports = ""
            if env:
                exports = []
                for k, v in env.items():
                    if k.isidentifier():
                        exports.append(f"export {k}={shlex.quote(v)}")
                if exports:
                    env_exports = " && ".join(exports) + " && "

            full_script = env_exports + wsl_script

            # Use cmd /c start to spawn in a new console window
            args = ["cmd", "/c", "start"]
            if title:
                args.append(subprocess.list2cmdline([title]))
            else:
                args.append('""')
            args.extend([cli_command])
            # Add extra options from config (e.g., -d for distribution)
            args.extend(tty_config.options)
            args.extend(["--", "bash", "-c", full_script])

            spawn_env = os.environ.copy()
            # Note: env vars passed via spawn_env won't reach WSL directly
            # They're handled via the bash -c script above

            process = subprocess.Popen(  # nosec B603 - args built from config
                args,
                env=spawn_env,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )

            return SpawnResult(
                success=True,
                message=f"Spawned WSL with PID {process.pid}",
                pid=process.pid,
                terminal_type=self.terminal_type.value,
            )

        except Exception as e:
            return SpawnResult(
                success=False,
                message=f"Failed to spawn WSL: {e}",
                error=str(e),
            )
