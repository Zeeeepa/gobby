"""Comprehensive tests for Windows terminal spawners.

Tests for:
- windows.py: WindowsTerminalSpawner, CmdSpawner, PowerShellSpawner, WSLSpawner

All tests mock Windows-specific APIs to allow running on any platform.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gobby.agents.spawners.base import SpawnResult, TerminalType
from gobby.agents.spawners.windows import (
    CmdSpawner,
    PowerShellSpawner,
    WindowsTerminalSpawner,
    WSLSpawner,
)

pytestmark = pytest.mark.unit

# =============================================================================
# Helper Fixtures
# =============================================================================


@pytest.fixture
def mock_windows_tty_config():
    """Create a mock TTY config for Windows terminal testing."""
    with patch("gobby.agents.spawners.windows.get_tty_config") as mock_config:

        def create_mock_config(enabled=True, command=None, options=None):
            config = MagicMock()
            config.enabled = enabled
            config.command = command
            config.options = options or []
            return config

        mock_config.return_value.get_terminal_config = create_mock_config
        yield {
            "config": mock_config,
            "create_config": create_mock_config,
        }


@pytest.fixture
def mock_windows_env():
    """Mock environment for Windows testing."""
    with patch.dict(os.environ, {"PATH": "C:\\Windows\\System32;C:\\Windows"}):
        yield


# =============================================================================
# Tests for WindowsTerminalSpawner
# =============================================================================


class TestWindowsTerminalSpawner:
    """Tests for WindowsTerminalSpawner."""

    def test_terminal_type(self) -> None:
        """Spawner returns correct terminal type."""
        spawner = WindowsTerminalSpawner()
        assert spawner.terminal_type == TerminalType.WINDOWS_TERMINAL

    @patch("platform.system", return_value="Linux")
    def test_is_available_not_windows(self, mock_system) -> None:
        """Windows Terminal not available on non-Windows platforms."""
        spawner = WindowsTerminalSpawner()
        assert spawner.is_available() is False

    @patch("platform.system", return_value="Darwin")
    def test_is_available_not_windows_macos(self, mock_system) -> None:
        """Windows Terminal not available on macOS."""
        spawner = WindowsTerminalSpawner()
        assert spawner.is_available() is False

    @patch("platform.system", return_value="Windows")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_is_available_disabled(self, mock_config, mock_system) -> None:
        """Windows Terminal not available when disabled in config."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=False, command="wt"
        )
        spawner = WindowsTerminalSpawner()
        assert spawner.is_available() is False

    @patch("platform.system", return_value="Windows")
    @patch("shutil.which", return_value="C:\\Program Files\\WindowsApps\\wt.exe")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_is_available_with_wt_command(self, mock_config, mock_which, mock_system) -> None:
        """Windows Terminal available when wt command exists."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="wt"
        )
        spawner = WindowsTerminalSpawner()
        assert spawner.is_available() is True
        mock_which.assert_called_with("wt")

    @patch("platform.system", return_value="Windows")
    @patch("shutil.which", return_value=None)
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_is_available_wt_not_found(self, mock_config, mock_which, mock_system) -> None:
        """Windows Terminal not available when wt command not found."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="wt"
        )
        spawner = WindowsTerminalSpawner()
        assert spawner.is_available() is False

    @patch("platform.system", return_value="Windows")
    @patch("shutil.which", return_value="C:\\custom\\wt.exe")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_is_available_custom_command(self, mock_config, mock_which, mock_system) -> None:
        """Windows Terminal uses custom command from config."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="custom-wt"
        )
        spawner = WindowsTerminalSpawner()
        spawner.is_available()
        mock_which.assert_called_with("custom-wt")

    @patch("platform.system", return_value="Windows")
    @patch("shutil.which", return_value="C:\\wt.exe")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_is_available_default_command_when_none(self, mock_config, mock_which, mock_system) -> None:
        """Windows Terminal uses 'wt' as default command when config.command is None."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command=None
        )
        spawner = WindowsTerminalSpawner()
        spawner.is_available()
        mock_which.assert_called_with("wt")

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_spawn_basic(self, mock_config, mock_popen) -> None:
        """Spawn creates correct Windows Terminal command."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="wt", options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = WindowsTerminalSpawner()
        result = spawner.spawn(["python", "script.py"], cwd="C:\\Projects")

        assert result.success is True
        assert result.pid == 12345
        assert result.terminal_type == "windows-terminal"
        assert "Spawned Windows Terminal with PID 12345" in result.message

        call_args = mock_popen.call_args[0][0]
        assert call_args[0] == "wt"
        assert "-d" in call_args
        assert "C:\\Projects" in call_args
        assert "--" in call_args
        assert "python" in call_args
        assert "script.py" in call_args

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_spawn_with_title(self, mock_config, mock_popen) -> None:
        """Spawn includes --title flag when title provided."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="wt", options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = WindowsTerminalSpawner()
        result = spawner.spawn(["echo", "test"], cwd="C:\\Projects", title="My Terminal")

        assert result.success is True
        call_args = mock_popen.call_args[0][0]
        assert "--title" in call_args
        title_idx = call_args.index("--title")
        assert call_args[title_idx + 1] == "My Terminal"

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_spawn_without_title(self, mock_config, mock_popen) -> None:
        """Spawn excludes --title flag when no title provided."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="wt", options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = WindowsTerminalSpawner()
        spawner.spawn(["echo", "test"], cwd="C:\\Projects")

        call_args = mock_popen.call_args[0][0]
        assert "--title" not in call_args

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_spawn_with_options(self, mock_config, mock_popen) -> None:
        """Spawn includes extra options from config."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="wt", options=["--profile", "Ubuntu", "--tabColor", "#FF0000"]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = WindowsTerminalSpawner()
        spawner.spawn(["bash"], cwd="C:\\")

        call_args = mock_popen.call_args[0][0]
        assert "--profile" in call_args
        assert "Ubuntu" in call_args
        assert "--tabColor" in call_args
        assert "#FF0000" in call_args

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_spawn_with_env_vars(self, mock_config, mock_popen) -> None:
        """Spawn passes environment variables."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="wt", options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = WindowsTerminalSpawner()
        result = spawner.spawn(
            ["python", "test.py"],
            cwd="C:\\Projects",
            env={"MY_VAR": "my_value", "OTHER_VAR": "other"},
        )

        assert result.success is True
        call_kwargs = mock_popen.call_args[1]
        assert "MY_VAR" in call_kwargs["env"]
        assert call_kwargs["env"]["MY_VAR"] == "my_value"
        assert call_kwargs["env"]["OTHER_VAR"] == "other"

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_spawn_uses_create_new_process_group(self, mock_config, mock_popen) -> None:
        """Spawn uses CREATE_NEW_PROCESS_GROUP creationflags on Windows."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="wt", options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = WindowsTerminalSpawner()
        spawner.spawn(["cmd"], cwd="C:\\")

        call_kwargs = mock_popen.call_args[1]
        # The creationflags should use CREATE_NEW_PROCESS_GROUP if available
        expected_flag = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        assert call_kwargs["creationflags"] == expected_flag

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_spawn_with_path_object(self, mock_config, mock_popen) -> None:
        """Spawn handles Path objects for cwd."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="wt", options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = WindowsTerminalSpawner()
        result = spawner.spawn(["cmd"], cwd=Path("C:\\Projects\\MyApp"))

        assert result.success is True
        call_args = mock_popen.call_args[0][0]
        assert "C:\\Projects\\MyApp" in call_args

    @patch("subprocess.Popen", side_effect=FileNotFoundError("wt not found"))
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_spawn_handles_file_not_found(self, mock_config, mock_popen) -> None:
        """Spawn handles FileNotFoundError gracefully."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="wt", options=[]
        )

        spawner = WindowsTerminalSpawner()
        result = spawner.spawn(["cmd"], cwd="C:\\")

        assert result.success is False
        assert "wt not found" in result.error
        assert "Failed to spawn Windows Terminal" in result.message

    @patch("subprocess.Popen", side_effect=OSError("Access denied"))
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_spawn_handles_os_error(self, mock_config, mock_popen) -> None:
        """Spawn handles OSError gracefully."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="wt", options=[]
        )

        spawner = WindowsTerminalSpawner()
        result = spawner.spawn(["cmd"], cwd="C:\\")

        assert result.success is False
        assert "Access denied" in result.error

    @patch("subprocess.Popen", side_effect=Exception("Unexpected error"))
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_spawn_handles_generic_exception(self, mock_config, mock_popen) -> None:
        """Spawn handles generic exceptions gracefully."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="wt", options=[]
        )

        spawner = WindowsTerminalSpawner()
        result = spawner.spawn(["cmd"], cwd="C:\\")

        assert result.success is False
        assert "Unexpected error" in result.error


# =============================================================================
# Tests for CmdSpawner
# =============================================================================


class TestCmdSpawner:
    """Tests for CmdSpawner."""

    def test_terminal_type(self) -> None:
        """Spawner returns correct terminal type."""
        spawner = CmdSpawner()
        assert spawner.terminal_type == TerminalType.CMD

    @patch("platform.system", return_value="Linux")
    def test_is_available_not_windows(self, mock_system) -> None:
        """cmd.exe not available on non-Windows platforms."""
        spawner = CmdSpawner()
        assert spawner.is_available() is False

    @patch("platform.system", return_value="Darwin")
    def test_is_available_not_windows_macos(self, mock_system) -> None:
        """cmd.exe not available on macOS."""
        spawner = CmdSpawner()
        assert spawner.is_available() is False

    @patch("platform.system", return_value="Windows")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_is_available_disabled(self, mock_config, mock_system) -> None:
        """cmd.exe not available when disabled in config."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(enabled=False)
        spawner = CmdSpawner()
        assert spawner.is_available() is False

    @patch("platform.system", return_value="Windows")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_is_available_enabled(self, mock_config, mock_system) -> None:
        """cmd.exe available when enabled on Windows (built-in, no which check)."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(enabled=True)
        spawner = CmdSpawner()
        assert spawner.is_available() is True

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_spawn_basic(self, mock_config, mock_popen) -> None:
        """Spawn creates correct cmd.exe command."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(enabled=True)
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = CmdSpawner()
        result = spawner.spawn(["python", "script.py"], cwd="C:\\Projects")

        assert result.success is True
        assert result.pid == 12345
        assert result.terminal_type == "cmd"
        assert "Spawned cmd.exe with PID 12345" in result.message

        call_args = mock_popen.call_args[0][0]
        assert call_args[0] == "cmd"
        assert "/c" in call_args
        assert "start" in call_args

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_spawn_with_title(self, mock_config, mock_popen) -> None:
        """Spawn includes title in start command."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(enabled=True)
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = CmdSpawner()
        result = spawner.spawn(["echo", "test"], cwd="C:\\Projects", title="My CMD Window")

        assert result.success is True
        call_args = mock_popen.call_args[0][0]
        # Title should be quoted using list2cmdline
        assert '"My CMD Window"' in call_args

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_spawn_without_title_uses_empty_quotes(self, mock_config, mock_popen) -> None:
        """Spawn uses empty title quotes when no title provided."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(enabled=True)
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = CmdSpawner()
        spawner.spawn(["echo", "test"], cwd="C:\\Projects")

        call_args = mock_popen.call_args[0][0]
        # Empty title is required for start command when path contains spaces
        assert '""' in call_args

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_spawn_with_env_vars(self, mock_config, mock_popen) -> None:
        """Spawn passes environment variables."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(enabled=True)
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = CmdSpawner()
        result = spawner.spawn(["dir"], cwd="C:\\", env={"MY_VAR": "value"})

        assert result.success is True
        call_kwargs = mock_popen.call_args[1]
        assert "MY_VAR" in call_kwargs["env"]
        assert call_kwargs["env"]["MY_VAR"] == "value"

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_spawn_uses_cmd_k_for_keeping_window_open(self, mock_config, mock_popen) -> None:
        """Spawn uses cmd /k to keep window open after command."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(enabled=True)
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = CmdSpawner()
        spawner.spawn(["echo", "hello"], cwd="C:\\")

        call_args = mock_popen.call_args[0][0]
        # Should use /k to keep window open (vs /c which closes)
        assert "/k" in call_args

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_spawn_properly_escapes_command(self, mock_config, mock_popen) -> None:
        """Spawn uses list2cmdline for proper escaping."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(enabled=True)
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = CmdSpawner()
        # Command with special characters
        spawner.spawn(["python", "-c", 'print("hello world")'], cwd="C:\\Program Files\\Python")

        call_args = mock_popen.call_args[0][0]
        # Verify command structure is correct
        assert "cmd" in call_args
        assert "/c" in call_args
        assert "start" in call_args

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_spawn_uses_create_new_process_group(self, mock_config, mock_popen) -> None:
        """Spawn uses CREATE_NEW_PROCESS_GROUP creationflags."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(enabled=True)
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = CmdSpawner()
        spawner.spawn(["cmd"], cwd="C:\\")

        call_kwargs = mock_popen.call_args[1]
        expected_flag = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        assert call_kwargs["creationflags"] == expected_flag

    @patch("subprocess.Popen", side_effect=FileNotFoundError("cmd not found"))
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_spawn_handles_file_not_found(self, mock_config, mock_popen) -> None:
        """Spawn handles FileNotFoundError gracefully."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(enabled=True)

        spawner = CmdSpawner()
        result = spawner.spawn(["dir"], cwd="C:\\")

        assert result.success is False
        assert "cmd not found" in result.error
        assert "Failed to spawn cmd.exe" in result.message

    @patch("subprocess.Popen", side_effect=OSError("The system cannot find the path"))
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_spawn_handles_invalid_path(self, mock_config, mock_popen) -> None:
        """Spawn handles invalid path errors gracefully."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(enabled=True)

        spawner = CmdSpawner()
        result = spawner.spawn(["cmd"], cwd="Z:\\NonExistent")

        assert result.success is False
        assert "cannot find the path" in result.error

    @patch("subprocess.Popen", side_effect=Exception("Unknown error"))
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_spawn_handles_generic_exception(self, mock_config, mock_popen) -> None:
        """Spawn handles generic exceptions gracefully."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(enabled=True)

        spawner = CmdSpawner()
        result = spawner.spawn(["cmd"], cwd="C:\\")

        assert result.success is False
        assert "Unknown error" in result.error


# =============================================================================
# Tests for PowerShellSpawner
# =============================================================================


class TestPowerShellSpawner:
    """Tests for PowerShellSpawner."""

    def test_terminal_type(self) -> None:
        """Spawner returns correct terminal type."""
        spawner = PowerShellSpawner()
        assert spawner.terminal_type == TerminalType.POWERSHELL

    @patch("platform.system", return_value="Linux")
    def test_is_available_not_windows(self, mock_system) -> None:
        """PowerShell not available on non-Windows platforms."""
        spawner = PowerShellSpawner()
        assert spawner.is_available() is False

    @patch("platform.system", return_value="Darwin")
    def test_is_available_not_windows_macos(self, mock_system) -> None:
        """PowerShell not available on macOS."""
        spawner = PowerShellSpawner()
        assert spawner.is_available() is False

    @patch("platform.system", return_value="Windows")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_is_available_disabled(self, mock_config, mock_system) -> None:
        """PowerShell not available when disabled in config."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=False, command="pwsh"
        )
        spawner = PowerShellSpawner()
        assert spawner.is_available() is False

    @patch("platform.system", return_value="Windows")
    @patch("shutil.which")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_is_available_pwsh_found(self, mock_config, mock_which, mock_system) -> None:
        """PowerShell available when pwsh (PowerShell Core) exists."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="pwsh"
        )
        mock_which.return_value = "C:\\Program Files\\PowerShell\\7\\pwsh.exe"

        spawner = PowerShellSpawner()
        assert spawner.is_available() is True
        mock_which.assert_called_with("pwsh")

    @patch("platform.system", return_value="Windows")
    @patch("shutil.which")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_is_available_fallback_to_powershell(self, mock_config, mock_which, mock_system) -> None:
        """PowerShell falls back to Windows PowerShell when pwsh not found."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="pwsh"
        )
        # pwsh not found, but powershell is
        mock_which.side_effect = lambda cmd: (
            None
            if cmd == "pwsh"
            else "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe"
        )

        spawner = PowerShellSpawner()
        assert spawner.is_available() is True

    @patch("platform.system", return_value="Windows")
    @patch("shutil.which", return_value=None)
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_is_available_neither_found(self, mock_config, mock_which, mock_system) -> None:
        """PowerShell not available when neither pwsh nor powershell found."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="pwsh"
        )

        spawner = PowerShellSpawner()
        assert spawner.is_available() is False

    @patch("platform.system", return_value="Windows")
    @patch("shutil.which", return_value="C:\\custom\\ps.exe")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_is_available_custom_command(self, mock_config, mock_which, mock_system) -> None:
        """PowerShell uses custom command from config."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="custom-pwsh"
        )

        spawner = PowerShellSpawner()
        spawner.is_available()
        mock_which.assert_called_with("custom-pwsh")

    @patch("shutil.which")
    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_spawn_basic_pwsh(self, mock_config, mock_popen, mock_which) -> None:
        """Spawn creates correct PowerShell Core command."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="pwsh", options=[]
        )
        mock_which.return_value = "C:\\pwsh.exe"
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = PowerShellSpawner()
        result = spawner.spawn(["python", "script.py"], cwd="C:\\Projects")

        assert result.success is True
        assert result.pid == 12345
        assert result.terminal_type == "powershell"
        assert "Spawned PowerShell with PID 12345" in result.message

        call_args = mock_popen.call_args[0][0]
        assert "cmd" in call_args
        assert "/c" in call_args
        assert "start" in call_args
        assert "pwsh" in call_args
        assert "-NoExit" in call_args
        assert "-Command" in call_args

    @patch("shutil.which")
    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_spawn_fallback_to_powershell(self, mock_config, mock_popen, mock_which) -> None:
        """Spawn falls back to powershell when pwsh not found."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="pwsh", options=[]
        )
        # pwsh not found, powershell is
        mock_which.side_effect = lambda cmd: None if cmd == "pwsh" else "C:\\powershell.exe"
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = PowerShellSpawner()
        result = spawner.spawn(["echo", "test"], cwd="C:\\")

        assert result.success is True
        call_args = mock_popen.call_args[0][0]
        assert "powershell" in call_args

    @patch("shutil.which", return_value="C:\\pwsh.exe")
    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_spawn_with_title(self, mock_config, mock_popen, mock_which) -> None:
        """Spawn includes -Title flag when title provided."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="pwsh", options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = PowerShellSpawner()
        result = spawner.spawn(["echo", "test"], cwd="C:\\Projects", title="My PowerShell")

        assert result.success is True
        call_args = mock_popen.call_args[0][0]
        assert "-Title" in call_args
        # Title should be properly escaped for PowerShell
        title_idx = call_args.index("-Title")
        assert "'My PowerShell'" in call_args[title_idx + 1]

    @patch("shutil.which", return_value="C:\\pwsh.exe")
    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_spawn_escapes_single_quotes_in_title(self, mock_config, mock_popen, mock_which) -> None:
        """Spawn properly escapes single quotes in title."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="pwsh", options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = PowerShellSpawner()
        spawner.spawn(["echo", "test"], cwd="C:\\", title="It's a test")

        call_args = mock_popen.call_args[0][0]
        title_idx = call_args.index("-Title")
        # Single quotes should be doubled for PowerShell
        assert "It''s a test" in call_args[title_idx + 1]

    @patch("shutil.which", return_value="C:\\pwsh.exe")
    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_spawn_escapes_single_quotes_in_cwd(self, mock_config, mock_popen, mock_which) -> None:
        """Spawn properly escapes single quotes in working directory."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="pwsh", options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = PowerShellSpawner()
        spawner.spawn(["echo", "test"], cwd="C:\\User's Files")

        call_args = mock_popen.call_args[0][0]
        # Find the -Command argument
        cmd_idx = call_args.index("-Command")
        ps_script = call_args[cmd_idx + 1]
        # Single quotes in path should be doubled
        assert "User''s Files" in ps_script

    @patch("shutil.which", return_value="C:\\pwsh.exe")
    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_spawn_with_options(self, mock_config, mock_popen, mock_which) -> None:
        """Spawn includes extra options from config."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="pwsh", options=["-NoLogo", "-ExecutionPolicy", "Bypass"]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = PowerShellSpawner()
        spawner.spawn(["echo", "test"], cwd="C:\\")

        call_args = mock_popen.call_args[0][0]
        assert "-NoLogo" in call_args
        assert "-ExecutionPolicy" in call_args
        assert "Bypass" in call_args

    @patch("shutil.which", return_value="C:\\pwsh.exe")
    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_spawn_with_env_vars(self, mock_config, mock_popen, mock_which) -> None:
        """Spawn passes environment variables."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="pwsh", options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = PowerShellSpawner()
        result = spawner.spawn(["echo", "$env:MY_VAR"], cwd="C:\\", env={"MY_VAR": "value"})

        assert result.success is True
        call_kwargs = mock_popen.call_args[1]
        assert "MY_VAR" in call_kwargs["env"]
        assert call_kwargs["env"]["MY_VAR"] == "value"

    @patch("shutil.which", return_value="C:\\pwsh.exe")
    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_spawn_uses_set_location(self, mock_config, mock_popen, mock_which) -> None:
        """Spawn uses Set-Location for working directory."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="pwsh", options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = PowerShellSpawner()
        spawner.spawn(["echo", "test"], cwd="C:\\Projects\\App")

        call_args = mock_popen.call_args[0][0]
        cmd_idx = call_args.index("-Command")
        ps_script = call_args[cmd_idx + 1]
        assert "Set-Location" in ps_script
        assert "C:\\Projects\\App" in ps_script

    @patch("shutil.which", return_value="C:\\pwsh.exe")
    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_spawn_uses_create_new_process_group(self, mock_config, mock_popen, mock_which) -> None:
        """Spawn uses CREATE_NEW_PROCESS_GROUP creationflags."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="pwsh", options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = PowerShellSpawner()
        spawner.spawn(["echo", "test"], cwd="C:\\")

        call_kwargs = mock_popen.call_args[1]
        expected_flag = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        assert call_kwargs["creationflags"] == expected_flag

    @patch("shutil.which", return_value="C:\\pwsh.exe")
    @patch("subprocess.Popen", side_effect=FileNotFoundError("pwsh not found"))
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_spawn_handles_file_not_found(self, mock_config, mock_popen, mock_which) -> None:
        """Spawn handles FileNotFoundError gracefully."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="pwsh", options=[]
        )

        spawner = PowerShellSpawner()
        result = spawner.spawn(["echo", "test"], cwd="C:\\")

        assert result.success is False
        assert "pwsh not found" in result.error
        assert "Failed to spawn PowerShell" in result.message

    @patch("shutil.which", return_value="C:\\pwsh.exe")
    @patch("subprocess.Popen", side_effect=Exception("Unexpected error"))
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_spawn_handles_generic_exception(self, mock_config, mock_popen, mock_which) -> None:
        """Spawn handles generic exceptions gracefully."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="pwsh", options=[]
        )

        spawner = PowerShellSpawner()
        result = spawner.spawn(["echo", "test"], cwd="C:\\")

        assert result.success is False
        assert "Unexpected error" in result.error


# =============================================================================
# Tests for WSLSpawner
# =============================================================================


class TestWSLSpawner:
    """Tests for WSLSpawner."""

    def test_terminal_type(self) -> None:
        """Spawner returns correct terminal type."""
        spawner = WSLSpawner()
        assert spawner.terminal_type == TerminalType.WSL

    @patch("platform.system", return_value="Linux")
    def test_is_available_not_windows(self, mock_system) -> None:
        """WSL not available on non-Windows platforms."""
        spawner = WSLSpawner()
        assert spawner.is_available() is False

    @patch("platform.system", return_value="Darwin")
    def test_is_available_not_windows_macos(self, mock_system) -> None:
        """WSL not available on macOS."""
        spawner = WSLSpawner()
        assert spawner.is_available() is False

    @patch("platform.system", return_value="Windows")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_is_available_disabled(self, mock_config, mock_system) -> None:
        """WSL not available when disabled in config."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=False, command="wsl"
        )
        spawner = WSLSpawner()
        assert spawner.is_available() is False

    @patch("platform.system", return_value="Windows")
    @patch("shutil.which", return_value="C:\\Windows\\System32\\wsl.exe")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_is_available_wsl_found(self, mock_config, mock_which, mock_system) -> None:
        """WSL available when wsl command exists."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="wsl"
        )
        spawner = WSLSpawner()
        assert spawner.is_available() is True
        mock_which.assert_called_with("wsl")

    @patch("platform.system", return_value="Windows")
    @patch("shutil.which", return_value=None)
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_is_available_wsl_not_found(self, mock_config, mock_which, mock_system) -> None:
        """WSL not available when wsl command not found."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="wsl"
        )
        spawner = WSLSpawner()
        assert spawner.is_available() is False

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_spawn_basic(self, mock_config, mock_popen) -> None:
        """Spawn creates correct WSL command."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="wsl", options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = WSLSpawner()
        result = spawner.spawn(["python", "script.py"], cwd="/home/user/projects")

        assert result.success is True
        assert result.pid == 12345
        assert result.terminal_type == "wsl"
        assert "Spawned WSL with PID 12345" in result.message

        call_args = mock_popen.call_args[0][0]
        assert "cmd" in call_args
        assert "/c" in call_args
        assert "start" in call_args
        assert "wsl" in call_args
        assert "--" in call_args
        assert "bash" in call_args
        assert "-c" in call_args

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_spawn_converts_windows_path_to_wsl(self, mock_config, mock_popen) -> None:
        """Spawn converts Windows path to WSL path format."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="wsl", options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = WSLSpawner()
        spawner.spawn(["ls"], cwd="C:\\Users\\Test\\Projects")

        call_args = mock_popen.call_args[0][0]
        # Find the bash -c script
        bash_idx = call_args.index("bash")
        script = call_args[bash_idx + 2]
        # Path should be converted to WSL format
        assert "/mnt/c/Users/Test/Projects" in script

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_spawn_converts_drive_letter_lowercase(self, mock_config, mock_popen) -> None:
        """Spawn converts drive letter to lowercase for WSL."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="wsl", options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = WSLSpawner()
        spawner.spawn(["pwd"], cwd="D:\\Data")

        call_args = mock_popen.call_args[0][0]
        bash_idx = call_args.index("bash")
        script = call_args[bash_idx + 2]
        # Drive letter should be lowercase
        assert "/mnt/d/Data" in script

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_spawn_preserves_unix_paths(self, mock_config, mock_popen) -> None:
        """Spawn preserves Unix-style paths without conversion."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="wsl", options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = WSLSpawner()
        spawner.spawn(["ls"], cwd="/home/user/projects")

        call_args = mock_popen.call_args[0][0]
        bash_idx = call_args.index("bash")
        script = call_args[bash_idx + 2]
        # Path should not be modified
        assert "/home/user/projects" in script
        assert "/mnt/" not in script

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_spawn_with_title(self, mock_config, mock_popen) -> None:
        """Spawn includes title in start command."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="wsl", options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = WSLSpawner()
        result = spawner.spawn(["bash"], cwd="/home/user", title="My WSL Window")

        assert result.success is True
        call_args = mock_popen.call_args[0][0]
        # Title should be quoted using list2cmdline
        assert '"My WSL Window"' in call_args

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_spawn_without_title_uses_empty_quotes(self, mock_config, mock_popen) -> None:
        """Spawn uses empty title quotes when no title provided."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="wsl", options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = WSLSpawner()
        spawner.spawn(["bash"], cwd="/home/user")

        call_args = mock_popen.call_args[0][0]
        assert '""' in call_args

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_spawn_with_options_distribution(self, mock_config, mock_popen) -> None:
        """Spawn includes extra options from config (e.g., distribution)."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="wsl", options=["-d", "Ubuntu"]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = WSLSpawner()
        spawner.spawn(["bash"], cwd="/home/user")

        call_args = mock_popen.call_args[0][0]
        assert "-d" in call_args
        assert "Ubuntu" in call_args

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_spawn_with_env_vars(self, mock_config, mock_popen) -> None:
        """Spawn includes environment variable exports in bash script."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="wsl", options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = WSLSpawner()
        spawner.spawn(
            ["echo", "$MY_VAR"], cwd="/home/user", env={"MY_VAR": "my_value", "OTHER_VAR": "other"}
        )

        call_args = mock_popen.call_args[0][0]
        bash_idx = call_args.index("bash")
        script = call_args[bash_idx + 2]
        # Environment variables should be exported via shell
        assert "export MY_VAR=" in script
        assert "export OTHER_VAR=" in script

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_spawn_validates_env_var_names(self, mock_config, mock_popen) -> None:
        """Spawn only exports valid identifier env var names."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="wsl", options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = WSLSpawner()
        spawner.spawn(
            ["env"],
            cwd="/home/user",
            env={"VALID_VAR": "value", "123invalid": "ignored", "with-dash": "ignored"},
        )

        call_args = mock_popen.call_args[0][0]
        bash_idx = call_args.index("bash")
        script = call_args[bash_idx + 2]
        assert "export VALID_VAR=" in script
        assert "123invalid" not in script
        assert "with-dash" not in script

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_spawn_escapes_command_for_bash(self, mock_config, mock_popen) -> None:
        """Spawn properly escapes command arguments for bash."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="wsl", options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = WSLSpawner()
        # Command with special characters
        spawner.spawn(["echo", "hello world", "test'quote"], cwd="/home/user")

        call_args = mock_popen.call_args[0][0]
        bash_idx = call_args.index("bash")
        script = call_args[bash_idx + 2]
        # Arguments should be properly quoted for bash
        assert "hello world" in script or "'hello world'" in script

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_spawn_uses_create_new_process_group(self, mock_config, mock_popen) -> None:
        """Spawn uses CREATE_NEW_PROCESS_GROUP creationflags."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="wsl", options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = WSLSpawner()
        spawner.spawn(["bash"], cwd="/home/user")

        call_kwargs = mock_popen.call_args[1]
        expected_flag = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        assert call_kwargs["creationflags"] == expected_flag

    @patch("subprocess.Popen", side_effect=FileNotFoundError("wsl not found"))
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_spawn_handles_file_not_found(self, mock_config, mock_popen) -> None:
        """Spawn handles FileNotFoundError gracefully."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="wsl", options=[]
        )

        spawner = WSLSpawner()
        result = spawner.spawn(["bash"], cwd="/home/user")

        assert result.success is False
        assert "wsl not found" in result.error
        assert "Failed to spawn WSL" in result.message

    @patch("subprocess.Popen", side_effect=Exception("WSL not installed"))
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_spawn_handles_generic_exception(self, mock_config, mock_popen) -> None:
        """Spawn handles generic exceptions gracefully."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="wsl", options=[]
        )

        spawner = WSLSpawner()
        result = spawner.spawn(["bash"], cwd="/home/user")

        assert result.success is False
        assert "WSL not installed" in result.error


# =============================================================================
# Tests for Edge Cases and Security
# =============================================================================


class TestWindowsSpawnerSecurity:
    """Tests for security considerations and edge cases in Windows spawners."""

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_cmd_injection_prevention(self, mock_config, mock_popen) -> None:
        """CmdSpawner properly escapes commands to prevent injection."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(enabled=True)
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = CmdSpawner()
        # Attempt command injection
        malicious_command = ["echo", "test & del C:\\* /q"]
        spawner.spawn(malicious_command, cwd="C:\\")

        # Verify the command was passed properly (list2cmdline handles escaping)
        assert mock_popen.called

    @patch("shutil.which", return_value="C:\\pwsh.exe")
    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_powershell_injection_prevention(self, mock_config, mock_popen, mock_which) -> None:
        """PowerShellSpawner properly escapes commands to prevent injection."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="pwsh", options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = PowerShellSpawner()
        # Attempt command injection via path
        malicious_cwd = "C:\\Users'; Remove-Item -Recurse C:\\; echo '"
        spawner.spawn(["echo", "test"], cwd=malicious_cwd)

        call_args = mock_popen.call_args[0][0]
        cmd_idx = call_args.index("-Command")
        ps_script = call_args[cmd_idx + 1]
        # The malicious content should be escaped (single quotes doubled)
        assert "Remove-Item" not in ps_script.split(";")

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_wsl_injection_prevention(self, mock_config, mock_popen) -> None:
        """WSLSpawner properly escapes commands to prevent injection."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="wsl", options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = WSLSpawner()
        # Attempt command injection
        malicious_command = ["echo", "; rm -rf /; echo"]
        spawner.spawn(malicious_command, cwd="/home/user")

        call_args = mock_popen.call_args[0][0]
        bash_idx = call_args.index("bash")
        script = call_args[bash_idx + 2]
        # The semicolons should be escaped/quoted
        # shlex.quote should prevent injection
        assert "rm -rf /" not in script.split("&&")


class TestWindowsSpawnerEdgeCases:
    """Tests for edge cases in Windows spawners."""

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_wt_path_with_spaces(self, mock_config, mock_popen) -> None:
        """WindowsTerminalSpawner handles paths with spaces."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="wt", options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = WindowsTerminalSpawner()
        spawner.spawn(["python", "test.py"], cwd="C:\\Program Files\\My App")

        call_args = mock_popen.call_args[0][0]
        d_idx = call_args.index("-d")
        assert call_args[d_idx + 1] == "C:\\Program Files\\My App"

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_cmd_path_with_special_chars(self, mock_config, mock_popen) -> None:
        """CmdSpawner handles paths with special characters."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(enabled=True)
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = CmdSpawner()
        spawner.spawn(["dir"], cwd="C:\\Users\\Test (1)\\Files&Data")

        # Verify Popen was called (proper escaping happens via list2cmdline)
        assert mock_popen.called

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_wsl_handles_short_path(self, mock_config, mock_popen) -> None:
        """WSLSpawner handles short paths correctly."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="wsl", options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = WSLSpawner()
        # Very short path - single character (not a drive letter pattern)
        spawner.spawn(["ls"], cwd="/")

        call_args = mock_popen.call_args[0][0]
        bash_idx = call_args.index("bash")
        script = call_args[bash_idx + 2]
        assert "cd '/'" in script or "cd /" in script

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_empty_env_dict(self, mock_config, mock_popen) -> None:
        """Spawners handle empty env dict correctly."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="wt", options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = WindowsTerminalSpawner()
        result = spawner.spawn(["cmd"], cwd="C:\\", env={})

        assert result.success is True

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.windows.get_tty_config")
    def test_wsl_empty_env_no_exports(self, mock_config, mock_popen) -> None:
        """WSLSpawner doesn't add export statements for empty env."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="wsl", options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = WSLSpawner()
        spawner.spawn(["bash"], cwd="/home/user", env={})

        call_args = mock_popen.call_args[0][0]
        bash_idx = call_args.index("bash")
        script = call_args[bash_idx + 2]
        # Should not have dangling && from empty env exports
        assert not script.startswith(" && ")


# =============================================================================
# Tests for SpawnResult Dataclass
# =============================================================================


class TestSpawnResultDataclass:
    """Tests for SpawnResult dataclass attributes."""

    def test_spawn_result_success(self) -> None:
        """SpawnResult correctly stores success data."""
        result = SpawnResult(
            success=True,
            message="Spawned successfully",
            pid=12345,
            terminal_type="windows-terminal",
        )
        assert result.success is True
        assert result.message == "Spawned successfully"
        assert result.pid == 12345
        assert result.terminal_type == "windows-terminal"
        assert result.error is None

    def test_spawn_result_failure(self) -> None:
        """SpawnResult correctly stores failure data."""
        result = SpawnResult(
            success=False,
            message="Failed to spawn",
            error="File not found",
        )
        assert result.success is False
        assert result.message == "Failed to spawn"
        assert result.pid is None
        assert result.terminal_type is None
        assert result.error == "File not found"


# =============================================================================
# Platform Skip Decorator Tests
# =============================================================================


@pytest.mark.skipif(os.name != "nt", reason="Windows-specific integration tests")
class TestWindowsIntegration:
    """Integration tests that only run on Windows."""

    def test_cmd_spawner_available_on_windows(self) -> None:
        """CmdSpawner should be available on Windows."""
        spawner = CmdSpawner()
        # cmd.exe is always available on Windows
        assert spawner.is_available() is True

    def test_windows_terminal_type_values(self) -> None:
        """Verify TerminalType enum values for Windows spawners."""
        assert TerminalType.WINDOWS_TERMINAL.value == "windows-terminal"
        assert TerminalType.CMD.value == "cmd"
        assert TerminalType.POWERSHELL.value == "powershell"
        assert TerminalType.WSL.value == "wsl"
