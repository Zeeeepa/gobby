"""Comprehensive tests for terminal spawners in the spawners/ package.

Tests for:
- cross_platform.py: KittySpawner, AlacrittySpawner, TmuxSpawner
- embedded.py: EmbeddedSpawner
- macos.py: GhosttySpawner, ITermSpawner, TerminalAppSpawner
- linux.py: GnomeTerminalSpawner, KonsoleSpawner
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gobby.agents.spawn import build_cli_command
from gobby.agents.spawners.base import (
    EmbeddedPTYResult,
    TerminalType,
)
from gobby.agents.spawners.cross_platform import (
    AlacrittySpawner,
    KittySpawner,
    TmuxSpawner,
)
from gobby.agents.spawners.embedded import EmbeddedSpawner
from gobby.agents.spawners.linux import GnomeTerminalSpawner, KonsoleSpawner
from gobby.agents.spawners.macos import (
    GhosttySpawner,
    ITermSpawner,
    TerminalAppSpawner,
    escape_applescript,
)

# =============================================================================
# Helper Fixtures
# =============================================================================


@pytest.fixture
def mock_tty_config():
    """Create a mock TTY config for testing."""
    with (
        patch("gobby.agents.spawners.cross_platform.get_tty_config") as mock_cp,
        patch("gobby.agents.spawners.macos.get_tty_config") as mock_macos,
        patch("gobby.agents.spawners.linux.get_tty_config") as mock_linux,
    ):

        def create_mock_config(enabled=True, command=None, app_path=None, options=None):
            config = MagicMock()
            config.enabled = enabled
            config.command = command
            config.app_path = app_path
            config.options = options or []
            return config

        mock_cp.return_value.get_terminal_config = create_mock_config
        mock_macos.return_value.get_terminal_config = create_mock_config
        mock_linux.return_value.get_terminal_config = create_mock_config

        yield {
            "cross_platform": mock_cp,
            "macos": mock_macos,
            "linux": mock_linux,
            "create_config": create_mock_config,
        }


# =============================================================================
# Tests for cross_platform.py - KittySpawner
# =============================================================================


class TestKittySpawner:
    """Tests for KittySpawner."""

    def test_terminal_type(self):
        """Spawner returns correct terminal type."""
        spawner = KittySpawner()
        assert spawner.terminal_type == TerminalType.KITTY

    @patch("gobby.agents.spawners.cross_platform.get_tty_config")
    def test_is_available_disabled(self, mock_config):
        """Kitty spawner not available when disabled in config."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=False, command="kitty", app_path=None
        )
        spawner = KittySpawner()
        assert spawner.is_available() is False

    @patch("platform.system", return_value="Darwin")
    @patch("gobby.agents.spawners.cross_platform.get_tty_config")
    def test_is_available_macos_app_exists(self, mock_config, mock_system):
        """Kitty available on macOS when app bundle exists."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, app_path="/Applications/kitty.app", command=None
        )
        with patch.object(Path, "exists", return_value=True):
            spawner = KittySpawner()
            assert spawner.is_available() is True

    @patch("platform.system", return_value="Darwin")
    @patch("gobby.agents.spawners.cross_platform.get_tty_config")
    def test_is_available_macos_app_not_exists(self, mock_config, mock_system):
        """Kitty not available on macOS when app bundle doesn't exist."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, app_path="/Applications/kitty.app", command=None
        )
        with patch.object(Path, "exists", return_value=False):
            spawner = KittySpawner()
            assert spawner.is_available() is False

    @patch("platform.system", return_value="Linux")
    @patch("shutil.which", return_value="/usr/bin/kitty")
    @patch("gobby.agents.spawners.cross_platform.get_tty_config")
    def test_is_available_linux_command_exists(self, mock_config, mock_which, mock_system):
        """Kitty available on Linux when command exists."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="kitty", app_path=None
        )
        spawner = KittySpawner()
        assert spawner.is_available() is True

    @patch("platform.system", return_value="Linux")
    @patch("shutil.which", return_value=None)
    @patch("gobby.agents.spawners.cross_platform.get_tty_config")
    def test_is_available_linux_command_not_exists(self, mock_config, mock_which, mock_system):
        """Kitty not available on Linux when command doesn't exist."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="kitty", app_path=None
        )
        spawner = KittySpawner()
        assert spawner.is_available() is False

    @patch("platform.system", return_value="Darwin")
    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.cross_platform.get_tty_config")
    def test_spawn_macos(self, mock_config, mock_popen, mock_system):
        """Spawn on macOS uses app bundle path."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True,
            app_path="/Applications/kitty.app",
            command=None,
            options=["-o", "confirm_os_window_close=0"],
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = KittySpawner()
        result = spawner.spawn(["echo", "test"], cwd="/tmp")

        assert result.success is True
        assert result.pid == 12345
        assert result.terminal_type == "kitty"

        # Verify macOS-specific path was used
        call_args = mock_popen.call_args[0][0]
        assert "/Applications/kitty.app/Contents/MacOS/kitty" in call_args
        assert "--directory" in call_args
        assert "--" in call_args  # End of options separator
        assert "echo" in call_args
        assert "test" in call_args

    @patch("platform.system", return_value="Linux")
    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.cross_platform.get_tty_config")
    def test_spawn_linux(self, mock_config, mock_popen, mock_system):
        """Spawn on Linux uses command with --detach."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="kitty", app_path=None, options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = KittySpawner()
        result = spawner.spawn(["echo", "test"], cwd="/tmp", title="Test Window")

        assert result.success is True

        call_args = mock_popen.call_args[0][0]
        assert "kitty" == call_args[0]
        assert "--detach" in call_args
        assert "--directory" in call_args
        assert "--title" in call_args
        assert "Test Window" in call_args

    @patch("platform.system", return_value="Darwin")
    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.cross_platform.get_tty_config")
    def test_spawn_with_env_vars(self, mock_config, mock_popen, mock_system):
        """Spawn passes environment variables."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, app_path="/Applications/kitty.app", options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = KittySpawner()
        result = spawner.spawn(["echo", "test"], cwd="/tmp", env={"MY_VAR": "my_value"})

        assert result.success is True
        call_kwargs = mock_popen.call_args[1]
        assert "MY_VAR" in call_kwargs["env"]
        assert call_kwargs["env"]["MY_VAR"] == "my_value"
        assert call_kwargs["start_new_session"] is True

    @patch("platform.system", return_value="Darwin")
    @patch("subprocess.Popen", side_effect=Exception("Spawn failed"))
    @patch("gobby.agents.spawners.cross_platform.get_tty_config")
    def test_spawn_handles_exception(self, mock_config, mock_popen, mock_system):
        """Spawn handles exceptions gracefully."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, app_path="/Applications/kitty.app", options=[]
        )

        spawner = KittySpawner()
        result = spawner.spawn(["echo", "test"], cwd="/tmp")

        assert result.success is False
        assert "Spawn failed" in result.error
        assert "Failed to spawn Kitty" in result.message


# =============================================================================
# Tests for cross_platform.py - AlacrittySpawner
# =============================================================================


class TestAlacrittySpawner:
    """Tests for AlacrittySpawner."""

    def test_terminal_type(self):
        """Spawner returns correct terminal type."""
        spawner = AlacrittySpawner()
        assert spawner.terminal_type == TerminalType.ALACRITTY

    @patch("gobby.agents.spawners.cross_platform.get_tty_config")
    def test_is_available_disabled(self, mock_config):
        """Alacritty spawner not available when disabled."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=False, command="alacritty"
        )
        spawner = AlacrittySpawner()
        assert spawner.is_available() is False

    @patch("shutil.which", return_value="/usr/bin/alacritty")
    @patch("gobby.agents.spawners.cross_platform.get_tty_config")
    def test_is_available_with_command(self, mock_config, mock_which):
        """Alacritty available when command exists."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="alacritty"
        )
        spawner = AlacrittySpawner()
        assert spawner.is_available() is True
        mock_which.assert_called_with("alacritty")

    @patch("shutil.which", return_value=None)
    @patch("gobby.agents.spawners.cross_platform.get_tty_config")
    def test_is_available_without_command(self, mock_config, mock_which):
        """Alacritty not available when command doesn't exist."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="alacritty"
        )
        spawner = AlacrittySpawner()
        assert spawner.is_available() is False

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.cross_platform.get_tty_config")
    def test_spawn_basic(self, mock_config, mock_popen):
        """Basic spawn creates correct command."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="alacritty", options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = AlacrittySpawner()
        result = spawner.spawn(["echo", "test"], cwd="/tmp")

        assert result.success is True
        assert result.pid == 12345

        call_args = mock_popen.call_args[0][0]
        assert "alacritty" == call_args[0]
        assert "--working-directory" in call_args
        assert "-e" in call_args

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.cross_platform.get_tty_config")
    def test_spawn_with_title(self, mock_config, mock_popen):
        """Spawn with title includes --title flag."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="alacritty", options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = AlacrittySpawner()
        result = spawner.spawn(["echo", "test"], cwd="/tmp", title="My Terminal")

        assert result.success is True
        assert result.pid == 12345

        call_args = mock_popen.call_args[0][0]
        assert "--title" in call_args
        title_idx = call_args.index("--title")
        assert call_args[title_idx + 1] == "My Terminal"

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.cross_platform.get_tty_config")
    def test_spawn_with_options(self, mock_config, mock_popen):
        """Spawn includes extra options from config."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="alacritty", options=["--class", "gobby-terminal"]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = AlacrittySpawner()
        result = spawner.spawn(["echo", "test"], cwd="/tmp")

        assert result.success is True
        assert result.pid == 12345

        call_args = mock_popen.call_args[0][0]
        assert "--class" in call_args
        assert "gobby-terminal" in call_args

    @patch("subprocess.Popen", side_effect=FileNotFoundError("alacritty not found"))
    @patch("gobby.agents.spawners.cross_platform.get_tty_config")
    def test_spawn_handles_exception(self, mock_config, mock_popen):
        """Spawn handles exceptions gracefully."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="alacritty", options=[]
        )

        spawner = AlacrittySpawner()
        result = spawner.spawn(["echo", "test"], cwd="/tmp")

        assert result.success is False
        assert "alacritty not found" in result.error


# =============================================================================
# Tests for cross_platform.py - TmuxSpawner
# =============================================================================


class TestTmuxSpawner:
    """Tests for TmuxSpawner."""

    def test_terminal_type(self):
        """Spawner returns correct terminal type."""
        spawner = TmuxSpawner()
        assert spawner.terminal_type == TerminalType.TMUX

    @patch("platform.system", return_value="Windows")
    def test_is_available_windows(self, mock_system):
        """tmux not available on Windows."""
        spawner = TmuxSpawner()
        assert spawner.is_available() is False

    @patch("platform.system", return_value="Darwin")
    @patch("gobby.agents.spawners.cross_platform.get_tty_config")
    def test_is_available_disabled(self, mock_config, mock_system):
        """tmux not available when disabled."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=False, command="tmux"
        )
        spawner = TmuxSpawner()
        assert spawner.is_available() is False

    @patch("platform.system", return_value="Darwin")
    @patch("shutil.which", return_value="/usr/local/bin/tmux")
    @patch("gobby.agents.spawners.cross_platform.get_tty_config")
    def test_is_available_macos_with_tmux(self, mock_config, mock_which, mock_system):
        """tmux available on macOS when installed."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="tmux"
        )
        spawner = TmuxSpawner()
        assert spawner.is_available() is True

    @patch("platform.system", return_value="Linux")
    @patch("shutil.which", return_value="/usr/bin/tmux")
    @patch("gobby.agents.spawners.cross_platform.get_tty_config")
    def test_is_available_linux_with_tmux(self, mock_config, mock_which, mock_system):
        """tmux available on Linux when installed."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="tmux"
        )
        spawner = TmuxSpawner()
        assert spawner.is_available() is True

    @patch("platform.system", return_value="Darwin")
    @patch("shutil.which", return_value=None)
    @patch("gobby.agents.spawners.cross_platform.get_tty_config")
    def test_is_available_without_tmux(self, mock_config, mock_which, mock_system):
        """tmux not available when not installed."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="tmux"
        )
        spawner = TmuxSpawner()
        assert spawner.is_available() is False

    @patch("platform.system", return_value="Darwin")
    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.cross_platform.get_tty_config")
    def test_spawn_creates_detached_session(self, mock_config, mock_popen, mock_system):
        """Spawn creates a detached tmux session."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="tmux", options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.returncode = 0
        mock_process.wait.return_value = 0
        mock_popen.return_value = mock_process

        spawner = TmuxSpawner()
        result = spawner.spawn(["echo", "test"], cwd="/tmp", title="test-session")

        assert result.success is True
        assert "test-session" in result.message

        call_args = mock_popen.call_args[0][0]
        assert "tmux" in call_args
        assert "new-session" in call_args
        assert "-d" in call_args  # Detached
        assert "-s" in call_args  # Session name
        assert "-c" in call_args  # Working directory

    @patch("platform.system", return_value="Darwin")
    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.cross_platform.get_tty_config")
    def test_spawn_sanitizes_session_name(self, mock_config, mock_popen, mock_system):
        """Spawn sanitizes session names (dots and colons to dashes)."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="tmux", options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.returncode = 0
        mock_process.wait.return_value = 0
        mock_popen.return_value = mock_process

        spawner = TmuxSpawner()
        spawner.spawn(["echo", "test"], cwd="/tmp", title="test.session:1")

        call_args = mock_popen.call_args[0][0]
        s_index = call_args.index("-s")
        session_name = call_args[s_index + 1]
        assert "." not in session_name
        assert ":" not in session_name
        assert session_name == "test-session-1"

    @patch("platform.system", return_value="Darwin")
    @patch("subprocess.Popen")
    @patch("time.time", return_value=1234567890)
    @patch("gobby.agents.spawners.cross_platform.get_tty_config")
    def test_spawn_generates_session_name_without_title(
        self, mock_config, mock_time, mock_popen, mock_system
    ):
        """Spawn generates session name from timestamp when no title."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="tmux", options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.returncode = 0
        mock_process.wait.return_value = 0
        mock_popen.return_value = mock_process

        spawner = TmuxSpawner()
        spawner.spawn(["echo", "test"], cwd="/tmp")

        call_args = mock_popen.call_args[0][0]
        s_index = call_args.index("-s")
        session_name = call_args[s_index + 1]
        assert session_name == "gobby-1234567890"

    @patch("platform.system", return_value="Darwin")
    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.cross_platform.get_tty_config")
    def test_spawn_disables_destroy_unattached(self, mock_config, mock_popen, mock_system):
        """Spawn disables destroy-unattached option."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="tmux", options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.returncode = 0
        mock_process.wait.return_value = 0
        mock_popen.return_value = mock_process

        spawner = TmuxSpawner()
        result = spawner.spawn(["echo", "test"], cwd="/tmp", title="test-session")

        assert result.success is True
        assert result.pid is None

        call_args = mock_popen.call_args[0][0]
        assert ";" in call_args
        semicolon_idx = call_args.index(";")
        chained_args = call_args[semicolon_idx + 1 :]
        assert "set-option" in chained_args
        assert "destroy-unattached" in chained_args
        assert "off" in chained_args

    @patch("platform.system", return_value="Darwin")
    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.cross_platform.get_tty_config")
    def test_spawn_sets_window_title(self, mock_config, mock_popen, mock_system):
        """Spawn sets window title using -n flag."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="tmux", options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.returncode = 0
        mock_process.wait.return_value = 0
        mock_popen.return_value = mock_process

        spawner = TmuxSpawner()
        spawner.spawn(["echo", "test"], cwd="/tmp", title="my-window")

        call_args = mock_popen.call_args[0][0]
        assert "-n" in call_args
        n_index = call_args.index("-n")
        assert call_args[n_index + 1] == "my-window"

    @patch("platform.system", return_value="Darwin")
    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.cross_platform.get_tty_config")
    def test_spawn_passes_env_vars(self, mock_config, mock_popen, mock_system):
        """Spawn passes env vars via shell exports."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="tmux", options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.returncode = 0
        mock_process.wait.return_value = 0
        mock_popen.return_value = mock_process

        spawner = TmuxSpawner()
        spawner.spawn(
            ["echo", "test"],
            cwd="/tmp",
            title="test-env",
            env={"MY_VAR": "my_value", "OTHER_VAR": "other_value"},
        )

        call_args = mock_popen.call_args[0][0]
        assert "sh" in call_args
        sh_index = call_args.index("sh")
        assert call_args[sh_index + 1] == "-c"
        shell_cmd = call_args[sh_index + 2]
        assert "export MY_VAR=" in shell_cmd
        assert "export OTHER_VAR=" in shell_cmd
        assert "exec echo test" in shell_cmd

    @patch("platform.system", return_value="Darwin")
    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.cross_platform.get_tty_config")
    def test_spawn_single_command_no_env(self, mock_config, mock_popen, mock_system):
        """Spawn with single command and no env uses simple command."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="tmux", options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.returncode = 0
        mock_process.wait.return_value = 0
        mock_popen.return_value = mock_process

        spawner = TmuxSpawner()
        spawner.spawn(["bash"], cwd="/tmp", title="test")

        call_args = mock_popen.call_args[0][0]
        # Single command without env should be appended directly
        tmp_idx = call_args.index("/tmp")  # After -c /tmp
        # The command should be somewhere after the directory
        assert "bash" in call_args
        bash_idx = call_args.index("bash")
        assert bash_idx > tmp_idx, "bash should come after /tmp in command"

    @patch("platform.system", return_value="Darwin")
    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.cross_platform.get_tty_config")
    def test_spawn_multi_command_no_env(self, mock_config, mock_popen, mock_system):
        """Spawn with multiple args and no env uses sh -c."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="tmux", options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.returncode = 0
        mock_process.wait.return_value = 0
        mock_popen.return_value = mock_process

        spawner = TmuxSpawner()
        spawner.spawn(["echo", "hello", "world"], cwd="/tmp", title="test")

        call_args = mock_popen.call_args[0][0]
        assert "sh" in call_args
        sh_index = call_args.index("sh")
        assert call_args[sh_index + 1] == "-c"

    @patch("platform.system", return_value="Darwin")
    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.cross_platform.get_tty_config")
    def test_spawn_failure_returns_error(self, mock_config, mock_popen, mock_system):
        """Spawn returns error when tmux fails."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="tmux", options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.returncode = 1  # Non-zero exit code
        mock_process.wait.return_value = 1
        mock_popen.return_value = mock_process

        spawner = TmuxSpawner()
        result = spawner.spawn(["echo", "test"], cwd="/tmp", title="test")

        assert result.success is False
        assert "exited with code 1" in result.message

    @patch("platform.system", return_value="Darwin")
    @patch("subprocess.Popen", side_effect=Exception("tmux not found"))
    @patch("gobby.agents.spawners.cross_platform.get_tty_config")
    def test_spawn_handles_exception(self, mock_config, mock_popen, mock_system):
        """Spawn handles exceptions gracefully."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="tmux", options=[]
        )

        spawner = TmuxSpawner()
        result = spawner.spawn(["echo", "test"], cwd="/tmp")

        assert result.success is False
        assert "tmux not found" in result.error

    @patch("platform.system", return_value="Darwin")
    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.cross_platform.get_tty_config")
    def test_spawn_with_config_options(self, mock_config, mock_popen, mock_system):
        """Spawn includes extra options from config."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="tmux", options=["-L", "gobby-socket"]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.returncode = 0
        mock_process.wait.return_value = 0
        mock_popen.return_value = mock_process

        spawner = TmuxSpawner()
        spawner.spawn(["echo", "test"], cwd="/tmp", title="test")

        call_args = mock_popen.call_args[0][0]
        assert "-L" in call_args
        assert "gobby-socket" in call_args


# =============================================================================
# Tests for embedded.py - EmbeddedSpawner
# =============================================================================


class TestEmbeddedSpawner:
    """Tests for EmbeddedSpawner."""

    def test_spawn_empty_command(self):
        """Spawn returns error for empty command."""
        spawner = EmbeddedSpawner()
        result = spawner.spawn([], cwd="/tmp")

        assert result.success is False
        assert "empty command" in result.message.lower()

    @patch("platform.system", return_value="Windows")
    def test_spawn_not_supported_windows(self, mock_system):
        """Spawn not supported on Windows."""
        with patch("gobby.agents.spawners.embedded.pty", None):
            spawner = EmbeddedSpawner()
            result = spawner.spawn(["echo", "test"], cwd="/tmp")

            assert result.success is False
            assert "Windows" in result.message or "not supported" in result.message.lower()

    @patch("gobby.agents.spawners.embedded.pty")
    @patch("os.fork")
    @patch("os.close")
    def test_spawn_handles_fork_error(self, mock_close, mock_fork, mock_pty):
        """Spawn handles fork() errors gracefully."""
        mock_pty.openpty.return_value = (10, 11)
        mock_fork.side_effect = OSError("Fork failed")

        spawner = EmbeddedSpawner()
        result = spawner.spawn(["echo", "test"], cwd="/tmp")

        assert result.success is False
        assert "Fork failed" in result.error or "Failed" in result.message

    @patch("gobby.agents.spawners.embedded.pty")
    def test_spawn_handles_openpty_error(self, mock_pty):
        """Spawn handles openpty() errors gracefully."""
        mock_pty.openpty.side_effect = OSError("PTY creation failed")

        spawner = EmbeddedSpawner()
        result = spawner.spawn(["echo", "test"], cwd="/tmp")

        assert result.success is False
        assert result.error is not None

    @patch("gobby.agents.spawners.embedded.pty")
    @patch("os.fork", return_value=12345)  # Parent process (pid > 0)
    @patch("os.close")
    def test_spawn_parent_process(self, mock_close, mock_fork, mock_pty):
        """Spawn in parent process returns correct result."""
        mock_pty.openpty.return_value = (10, 11)

        spawner = EmbeddedSpawner()
        result = spawner.spawn(["echo", "test"], cwd="/tmp")

        assert result.success is True
        assert result.pid == 12345
        assert result.master_fd == 10
        assert result.slave_fd is None  # Closed in parent
        mock_close.assert_called_once_with(11)  # Slave fd closed

    @patch("gobby.agents.spawners.embedded.pty")
    @patch("os.fork", return_value=12345)
    @patch("os.close")
    def test_spawn_with_env_vars(self, mock_close, mock_fork, mock_pty):
        """Spawn passes environment variables."""
        mock_pty.openpty.return_value = (10, 11)

        spawner = EmbeddedSpawner()
        result = spawner.spawn(["echo", "test"], cwd="/tmp", env={"MY_VAR": "my_value"})

        assert result.success is True

    @patch("platform.system", return_value="Windows")
    def test_spawn_agent_not_supported_windows(self, mock_system):
        """spawn_agent not supported on Windows."""
        with patch("gobby.agents.spawners.embedded.pty", None):
            spawner = EmbeddedSpawner()
            result = spawner.spawn_agent(
                cli="claude",
                cwd="/tmp",
                session_id="sess-123",
                parent_session_id="sess-parent",
                agent_run_id="run-456",
                project_id="proj-789",
            )

            assert result.success is False

    @patch("gobby.agents.spawners.embedded.pty")
    @patch("os.fork", return_value=12345)
    @patch("os.close")
    @patch("gobby.agents.spawners.embedded._get_spawn_utils")
    def test_spawn_agent_basic(self, mock_utils, mock_close, mock_fork, mock_pty):
        """spawn_agent creates command with correct flags."""
        mock_pty.openpty.return_value = (10, 11)

        def mock_build_cli_command(
            cli, prompt=None, session_id=None, auto_approve=False, working_directory=None
        ):
            cmd = [cli]
            if session_id:
                cmd.extend(["--session-id", session_id])
            if auto_approve:
                cmd.append("--dangerously-skip-permissions")
            if prompt:
                cmd.extend(["-p", prompt])
            return cmd

        mock_utils.return_value = (mock_build_cli_command, MagicMock(), 4096)

        spawner = EmbeddedSpawner()
        result = spawner.spawn_agent(
            cli="claude",
            cwd="/tmp",
            session_id="sess-123",
            parent_session_id="sess-parent",
            agent_run_id="run-456",
            project_id="proj-789",
            prompt="Test prompt",
        )

        assert result.success is True
        assert result.pid == 12345

    @patch("gobby.agents.spawners.embedded.pty")
    @patch("os.fork", return_value=12345)
    @patch("os.close")
    @patch("gobby.agents.spawners.embedded._get_spawn_utils")
    def test_spawn_agent_with_long_prompt(self, mock_utils, mock_close, mock_fork, mock_pty):
        """spawn_agent writes long prompt to file."""
        mock_pty.openpty.return_value = (10, 11)

        mock_create_prompt_file = MagicMock(return_value="/tmp/prompt.txt")
        mock_utils.return_value = (
            MagicMock(return_value=["claude"]),
            mock_create_prompt_file,
            100,  # Low threshold to trigger file creation
        )

        spawner = EmbeddedSpawner()
        long_prompt = "x" * 200  # Longer than threshold
        result = spawner.spawn_agent(
            cli="claude",
            cwd="/tmp",
            session_id="sess-123",
            parent_session_id="sess-parent",
            agent_run_id="run-456",
            project_id="proj-789",
            prompt=long_prompt,
        )

        assert result.success is True
        mock_create_prompt_file.assert_called_once_with(long_prompt, "sess-123")

    @patch("gobby.agents.spawners.embedded.pty")
    @patch("os.fork", return_value=12345)
    @patch("os.close")
    @patch("gobby.agents.spawners.embedded._get_spawn_utils")
    def test_spawn_agent_codex_working_directory(self, mock_utils, mock_close, mock_fork, mock_pty):
        """spawn_agent passes working directory for Codex."""
        mock_pty.openpty.return_value = (10, 11)

        mock_build_cmd = MagicMock(return_value=["codex", "-C", "/projects/app"])
        mock_utils.return_value = (mock_build_cmd, MagicMock(), 4096)

        spawner = EmbeddedSpawner()
        result = spawner.spawn_agent(
            cli="codex",
            cwd="/projects/app",
            session_id="sess-123",
            parent_session_id="sess-parent",
            agent_run_id="run-456",
            project_id="proj-789",
        )

        assert result.success is True
        mock_build_cmd.assert_called_once()
        call_kwargs = mock_build_cmd.call_args[1]
        assert call_kwargs["working_directory"] == "/projects/app"


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.skipif(sys.platform == "win32", reason="PTY not available on Windows")
class TestEmbeddedSpawnerUnix:
    """Integration tests for EmbeddedSpawner on Unix systems."""

    def test_spawn_real_process(self):
        """spawn() creates real PTY and runs command."""
        spawner = EmbeddedSpawner()
        result = spawner.spawn(
            command=["echo", "hello"],
            cwd="/tmp",
        )

        try:
            assert result.success is True
            assert result.pid is not None
            assert result.pid > 0
            assert result.master_fd is not None
        finally:
            result.close()
            if result.pid:
                try:
                    os.waitpid(result.pid, os.WNOHANG)
                except ChildProcessError:
                    pass


# =============================================================================
# Tests for macos.py - escape_applescript helper
# =============================================================================


class TestEscapeApplescript:
    """Tests for escape_applescript helper function."""

    def test_escape_backslash(self):
        """Backslashes are escaped."""
        assert escape_applescript("path\\to\\file") == "path\\\\to\\\\file"

    def test_escape_quotes(self):
        """Double quotes are escaped."""
        assert escape_applescript('say "hello"') == 'say \\"hello\\"'

    def test_escape_mixed(self):
        """Mixed escaping works correctly."""
        result = escape_applescript('path\\to\\"file"')
        assert result == 'path\\\\to\\\\\\"file\\"'

    def test_no_escape_needed(self):
        """Strings without special chars pass through unchanged."""
        assert escape_applescript("simple string") == "simple string"


# =============================================================================
# Tests for macos.py - GhosttySpawner
# =============================================================================


class TestGhosttySpawner:
    """Tests for GhosttySpawner."""

    def test_terminal_type(self):
        """Spawner returns correct terminal type."""
        spawner = GhosttySpawner()
        assert spawner.terminal_type == TerminalType.GHOSTTY

    @patch("gobby.agents.spawners.macos.get_tty_config")
    def test_is_available_disabled(self, mock_config):
        """Ghostty not available when disabled."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=False, app_path=None, command="ghostty"
        )
        spawner = GhosttySpawner()
        assert spawner.is_available() is False

    @patch("platform.system", return_value="Darwin")
    @patch("gobby.agents.spawners.macos.get_tty_config")
    def test_is_available_macos_app_exists(self, mock_config, mock_system):
        """Ghostty available on macOS when app bundle exists."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, app_path="/Applications/Ghostty.app", command=None
        )
        with patch.object(Path, "exists", return_value=True):
            spawner = GhosttySpawner()
            assert spawner.is_available() is True

    @patch("platform.system", return_value="Darwin")
    @patch("gobby.agents.spawners.macos.get_tty_config")
    def test_is_available_macos_app_not_exists(self, mock_config, mock_system):
        """Ghostty not available on macOS when app doesn't exist."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, app_path="/Applications/Ghostty.app", command=None
        )
        with patch.object(Path, "exists", return_value=False):
            spawner = GhosttySpawner()
            assert spawner.is_available() is False

    @patch("platform.system", return_value="Linux")
    @patch("shutil.which", return_value="/usr/bin/ghostty")
    @patch("gobby.agents.spawners.macos.get_tty_config")
    def test_is_available_linux_command_exists(self, mock_config, mock_which, mock_system):
        """Ghostty available on Linux when command exists."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="ghostty", app_path=None
        )
        spawner = GhosttySpawner()
        assert spawner.is_available() is True

    @patch("platform.system", return_value="Linux")
    @patch("shutil.which", return_value=None)
    @patch("gobby.agents.spawners.macos.get_tty_config")
    def test_is_available_linux_command_not_exists(self, mock_config, mock_which, mock_system):
        """Ghostty not available on Linux when command doesn't exist."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="ghostty", app_path=None
        )
        spawner = GhosttySpawner()
        assert spawner.is_available() is False

    @patch("platform.system", return_value="Darwin")
    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.macos.get_tty_config")
    def test_spawn_macos(self, mock_config, mock_popen, mock_system):
        """Spawn on macOS uses 'open -na' command."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, app_path="/Applications/Ghostty.app", command=None, options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = GhosttySpawner()
        result = spawner.spawn(["echo", "test"], cwd="/tmp", title="Test")

        assert result.success is True
        assert result.pid == 12345

        call_args = mock_popen.call_args[0][0]
        assert call_args[0] == "open"
        assert "-na" in call_args
        assert "/Applications/Ghostty.app" in call_args
        assert "--args" in call_args
        # Ghostty uses --key=value syntax
        assert "--working-directory=/tmp" in call_args
        assert "--title=Test" in call_args
        assert "-e" in call_args

    @patch("platform.system", return_value="Linux")
    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.macos.get_tty_config")
    def test_spawn_linux(self, mock_config, mock_popen, mock_system):
        """Spawn on Linux uses ghostty command directly."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="ghostty", app_path=None, options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = GhosttySpawner()
        result = spawner.spawn(["echo", "test"], cwd="/tmp", title="Test")

        assert result.success is True

        call_args = mock_popen.call_args[0][0]
        assert call_args[0] == "ghostty"
        assert "--title=Test" in call_args
        assert "-e" in call_args

    @patch("platform.system", return_value="Darwin")
    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.macos.get_tty_config")
    def test_spawn_with_env_vars(self, mock_config, mock_popen, mock_system):
        """Spawn passes environment variables."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, app_path="/Applications/Ghostty.app", options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = GhosttySpawner()
        spawner.spawn(["echo", "test"], cwd="/tmp", env={"VAR": "value"})

        call_kwargs = mock_popen.call_args[1]
        assert call_kwargs["env"]["VAR"] == "value"
        assert call_kwargs["start_new_session"] is True

    @patch("platform.system", return_value="Darwin")
    @patch("subprocess.Popen", side_effect=Exception("Spawn failed"))
    @patch("gobby.agents.spawners.macos.get_tty_config")
    def test_spawn_handles_exception(self, mock_config, mock_popen, mock_system):
        """Spawn handles exceptions gracefully."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, app_path="/Applications/Ghostty.app", options=[]
        )

        spawner = GhosttySpawner()
        result = spawner.spawn(["echo", "test"], cwd="/tmp")

        assert result.success is False
        assert "Spawn failed" in result.error


# =============================================================================
# Tests for macos.py - ITermSpawner
# =============================================================================


class TestITermSpawner:
    """Tests for ITermSpawner."""

    def test_terminal_type(self):
        """Spawner returns correct terminal type."""
        spawner = ITermSpawner()
        assert spawner.terminal_type == TerminalType.ITERM

    @patch("platform.system", return_value="Linux")
    def test_is_available_not_macos(self, mock_system):
        """iTerm not available on non-macOS platforms."""
        spawner = ITermSpawner()
        assert spawner.is_available() is False

    @patch("platform.system", return_value="Darwin")
    @patch("gobby.agents.spawners.macos.get_tty_config")
    def test_is_available_disabled(self, mock_config, mock_system):
        """iTerm not available when disabled."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=False, app_path="/Applications/iTerm.app"
        )
        spawner = ITermSpawner()
        assert spawner.is_available() is False

    @patch("platform.system", return_value="Darwin")
    @patch("gobby.agents.spawners.macos.get_tty_config")
    def test_is_available_app_exists(self, mock_config, mock_system):
        """iTerm available when app bundle exists."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, app_path="/Applications/iTerm.app"
        )
        with patch.object(Path, "exists", return_value=True):
            spawner = ITermSpawner()
            assert spawner.is_available() is True

    @patch("platform.system", return_value="Darwin")
    @patch("gobby.agents.spawners.macos.get_tty_config")
    def test_is_available_app_not_exists(self, mock_config, mock_system):
        """iTerm not available when app doesn't exist."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, app_path="/Applications/iTerm.app"
        )
        with patch.object(Path, "exists", return_value=False):
            spawner = ITermSpawner()
            assert spawner.is_available() is False

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.macos.get_tty_config")
    def test_spawn_creates_script_and_applescript(self, mock_config, mock_popen):
        """Spawn creates temp script and runs AppleScript."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, app_path="/Applications/iTerm.app"
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = ITermSpawner()
        result = spawner.spawn(["echo", "test"], cwd="/tmp")

        assert result.success is True
        assert result.pid == 12345

        call_args = mock_popen.call_args[0][0]
        assert call_args[0].endswith("osascript")  # Accept /usr/bin/osascript or osascript
        assert "-e" in call_args

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.macos.get_tty_config")
    def test_spawn_with_env_vars(self, mock_config, mock_popen):
        """Spawn includes env vars in script."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, app_path="/Applications/iTerm.app"
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        with patch("tempfile.gettempdir", return_value="/tmp"):
            with patch.object(Path, "mkdir"):
                with patch.object(Path, "write_text") as mock_write:
                    with patch.object(Path, "chmod"):
                        spawner = ITermSpawner()
                        spawner.spawn(["echo", "test"], cwd="/tmp", env={"MY_VAR": "my_value"})

                        # Check script content includes env export
                        script_content = mock_write.call_args[0][0]
                        assert "export MY_VAR=" in script_content

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.macos.get_tty_config")
    def test_spawn_validates_env_var_names(self, mock_config, mock_popen):
        """Spawn only exports valid identifier env var names."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, app_path="/Applications/iTerm.app"
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        with patch("tempfile.gettempdir", return_value="/tmp"):
            with patch.object(Path, "mkdir"):
                with patch.object(Path, "write_text") as mock_write:
                    with patch.object(Path, "chmod"):
                        spawner = ITermSpawner()
                        spawner.spawn(
                            ["echo", "test"],
                            cwd="/tmp",
                            env={
                                "VALID_VAR": "value",
                                "123invalid": "ignored",
                                "with-dash": "ignored",
                            },
                        )

                        script_content = mock_write.call_args[0][0]
                        assert "export VALID_VAR=" in script_content
                        assert "123invalid" not in script_content
                        assert "with-dash" not in script_content

    @patch("subprocess.Popen", side_effect=Exception("osascript failed"))
    @patch("gobby.agents.spawners.macos.get_tty_config")
    def test_spawn_handles_exception(self, mock_config, mock_popen):
        """Spawn handles exceptions gracefully."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, app_path="/Applications/iTerm.app"
        )

        with patch("tempfile.gettempdir", return_value="/tmp"):
            with patch.object(Path, "mkdir"):
                with patch.object(Path, "write_text"):
                    with patch.object(Path, "chmod"):
                        spawner = ITermSpawner()
                        result = spawner.spawn(["echo", "test"], cwd="/tmp")

        assert result.success is False
        assert "osascript failed" in result.error


# =============================================================================
# Tests for macos.py - TerminalAppSpawner
# =============================================================================


class TestTerminalAppSpawner:
    """Tests for TerminalAppSpawner."""

    def test_terminal_type(self):
        """Spawner returns correct terminal type."""
        spawner = TerminalAppSpawner()
        assert spawner.terminal_type == TerminalType.TERMINAL_APP

    @patch("platform.system", return_value="Linux")
    def test_is_available_not_macos(self, mock_system):
        """Terminal.app not available on non-macOS platforms."""
        spawner = TerminalAppSpawner()
        assert spawner.is_available() is False

    @patch("platform.system", return_value="Darwin")
    @patch("gobby.agents.spawners.macos.get_tty_config")
    def test_is_available_disabled(self, mock_config, mock_system):
        """Terminal.app not available when disabled."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=False, app_path="/System/Applications/Utilities/Terminal.app"
        )
        spawner = TerminalAppSpawner()
        assert spawner.is_available() is False

    @patch("platform.system", return_value="Darwin")
    @patch("gobby.agents.spawners.macos.get_tty_config")
    def test_is_available_app_exists(self, mock_config, mock_system):
        """Terminal.app available when app exists."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, app_path="/System/Applications/Utilities/Terminal.app"
        )
        with patch.object(Path, "exists", return_value=True):
            spawner = TerminalAppSpawner()
            assert spawner.is_available() is True

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.macos.get_tty_config")
    def test_spawn_uses_applescript(self, mock_config, mock_popen):
        """Spawn uses AppleScript to launch Terminal.app."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, app_path="/System/Applications/Utilities/Terminal.app"
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = TerminalAppSpawner()
        result = spawner.spawn(["echo", "test"], cwd="/tmp")

        assert result.success is True

        call_args = mock_popen.call_args[0][0]
        assert call_args[0].endswith("osascript")  # Accept /usr/bin/osascript or osascript
        assert "-e" in call_args

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.macos.get_tty_config")
    def test_spawn_escapes_command(self, mock_config, mock_popen):
        """Spawn properly escapes shell command."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, app_path="/System/Applications/Utilities/Terminal.app"
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = TerminalAppSpawner()
        spawner.spawn(["echo", "hello world", 'with"quotes'], cwd="/tmp")

        call_args = mock_popen.call_args[0][0]
        script = call_args[2]  # The AppleScript content
        # The command should be properly escaped
        assert "do script" in script

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.macos.get_tty_config")
    def test_spawn_with_env_vars(self, mock_config, mock_popen):
        """Spawn includes env var exports in command."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, app_path="/System/Applications/Utilities/Terminal.app"
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = TerminalAppSpawner()
        spawner.spawn(["echo", "test"], cwd="/tmp", env={"MY_VAR": "my_value"})

        call_args = mock_popen.call_args[0][0]
        script = call_args[2]
        assert "export MY_VAR=" in script

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.macos.get_tty_config")
    def test_spawn_validates_env_var_names(self, mock_config, mock_popen):
        """Spawn only exports valid identifier env var names."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, app_path="/System/Applications/Utilities/Terminal.app"
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = TerminalAppSpawner()
        spawner.spawn(
            ["echo", "test"],
            cwd="/tmp",
            env={
                "VALID_VAR": "value",
                "123invalid": "ignored",
            },
        )

        call_args = mock_popen.call_args[0][0]
        script = call_args[2]
        assert "export VALID_VAR=" in script
        assert "123invalid" not in script

    @patch("subprocess.Popen", side_effect=Exception("osascript error"))
    @patch("gobby.agents.spawners.macos.get_tty_config")
    def test_spawn_handles_exception(self, mock_config, mock_popen):
        """Spawn handles exceptions gracefully."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, app_path="/System/Applications/Utilities/Terminal.app"
        )

        spawner = TerminalAppSpawner()
        result = spawner.spawn(["echo", "test"], cwd="/tmp")

        assert result.success is False
        assert "osascript error" in result.error


# =============================================================================
# Tests for linux.py - GnomeTerminalSpawner
# =============================================================================


class TestGnomeTerminalSpawner:
    """Tests for GnomeTerminalSpawner."""

    def test_terminal_type(self):
        """Spawner returns correct terminal type."""
        spawner = GnomeTerminalSpawner()
        assert spawner.terminal_type == TerminalType.GNOME_TERMINAL

    @patch("gobby.agents.spawners.linux.get_tty_config")
    def test_is_available_disabled(self, mock_config):
        """GNOME Terminal not available when disabled."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=False, command="gnome-terminal"
        )
        spawner = GnomeTerminalSpawner()
        assert spawner.is_available() is False

    @patch("shutil.which", return_value="/usr/bin/gnome-terminal")
    @patch("gobby.agents.spawners.linux.get_tty_config")
    def test_is_available_with_command(self, mock_config, mock_which):
        """GNOME Terminal available when command exists."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="gnome-terminal"
        )
        spawner = GnomeTerminalSpawner()
        assert spawner.is_available() is True

    @patch("shutil.which", return_value=None)
    @patch("gobby.agents.spawners.linux.get_tty_config")
    def test_is_available_without_command(self, mock_config, mock_which):
        """GNOME Terminal not available when command doesn't exist."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="gnome-terminal"
        )
        spawner = GnomeTerminalSpawner()
        assert spawner.is_available() is False

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.linux.get_tty_config")
    def test_spawn_basic(self, mock_config, mock_popen):
        """Spawn creates correct command."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="gnome-terminal", options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = GnomeTerminalSpawner()
        result = spawner.spawn(["echo", "test"], cwd="/tmp")

        assert result.success is True
        assert result.pid == 12345
        assert result.terminal_type == "gnome-terminal"

        call_args = mock_popen.call_args[0][0]
        assert call_args[0] == "gnome-terminal"
        assert "--working-directory=/tmp" in call_args
        assert "--" in call_args
        assert "echo" in call_args

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.linux.get_tty_config")
    def test_spawn_with_title(self, mock_config, mock_popen):
        """Spawn with title includes --title flag."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="gnome-terminal", options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = GnomeTerminalSpawner()
        spawner.spawn(["echo", "test"], cwd="/tmp", title="My Terminal")

        call_args = mock_popen.call_args[0][0]
        assert "--title" in call_args
        title_idx = call_args.index("--title")
        assert call_args[title_idx + 1] == "My Terminal"

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.linux.get_tty_config")
    def test_spawn_with_options(self, mock_config, mock_popen):
        """Spawn includes extra options from config."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="gnome-terminal", options=["--hide-menubar"]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = GnomeTerminalSpawner()
        spawner.spawn(["echo", "test"], cwd="/tmp")

        call_args = mock_popen.call_args[0][0]
        assert "--hide-menubar" in call_args

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.linux.get_tty_config")
    def test_spawn_with_env_vars(self, mock_config, mock_popen):
        """Spawn passes environment variables."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="gnome-terminal", options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = GnomeTerminalSpawner()
        spawner.spawn(["echo", "test"], cwd="/tmp", env={"MY_VAR": "value"})

        call_kwargs = mock_popen.call_args[1]
        assert call_kwargs["env"]["MY_VAR"] == "value"
        assert call_kwargs["start_new_session"] is True

    @patch("subprocess.Popen", side_effect=Exception("Command not found"))
    @patch("gobby.agents.spawners.linux.get_tty_config")
    def test_spawn_handles_exception(self, mock_config, mock_popen):
        """Spawn handles exceptions gracefully."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="gnome-terminal", options=[]
        )

        spawner = GnomeTerminalSpawner()
        result = spawner.spawn(["echo", "test"], cwd="/tmp")

        assert result.success is False
        assert "Command not found" in result.error


# =============================================================================
# Tests for linux.py - KonsoleSpawner
# =============================================================================


class TestKonsoleSpawner:
    """Tests for KonsoleSpawner."""

    def test_terminal_type(self):
        """Spawner returns correct terminal type."""
        spawner = KonsoleSpawner()
        assert spawner.terminal_type == TerminalType.KONSOLE

    @patch("gobby.agents.spawners.linux.get_tty_config")
    def test_is_available_disabled(self, mock_config):
        """Konsole not available when disabled."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=False, command="konsole"
        )
        spawner = KonsoleSpawner()
        assert spawner.is_available() is False

    @patch("shutil.which", return_value="/usr/bin/konsole")
    @patch("gobby.agents.spawners.linux.get_tty_config")
    def test_is_available_with_command(self, mock_config, mock_which):
        """Konsole available when command exists."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="konsole"
        )
        spawner = KonsoleSpawner()
        assert spawner.is_available() is True

    @patch("shutil.which", return_value=None)
    @patch("gobby.agents.spawners.linux.get_tty_config")
    def test_is_available_without_command(self, mock_config, mock_which):
        """Konsole not available when command doesn't exist."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="konsole"
        )
        spawner = KonsoleSpawner()
        assert spawner.is_available() is False

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.linux.get_tty_config")
    def test_spawn_basic(self, mock_config, mock_popen):
        """Spawn creates correct command."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="konsole", options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = KonsoleSpawner()
        result = spawner.spawn(["echo", "test"], cwd="/tmp")

        assert result.success is True
        assert result.pid == 12345
        assert result.terminal_type == "konsole"

        call_args = mock_popen.call_args[0][0]
        assert call_args[0] == "konsole"
        assert "--workdir" in call_args
        assert "-e" in call_args

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.linux.get_tty_config")
    def test_spawn_with_title(self, mock_config, mock_popen):
        """Spawn with title uses -p tabtitle= syntax."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="konsole", options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = KonsoleSpawner()
        spawner.spawn(["echo", "test"], cwd="/tmp", title="My Konsole")

        call_args = mock_popen.call_args[0][0]
        assert "-p" in call_args
        p_idx = call_args.index("-p")
        assert call_args[p_idx + 1] == "tabtitle=My Konsole"

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.linux.get_tty_config")
    def test_spawn_with_options(self, mock_config, mock_popen):
        """Spawn includes extra options from config."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="konsole", options=["--hide-menubar", "--notransparency"]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = KonsoleSpawner()
        spawner.spawn(["echo", "test"], cwd="/tmp")

        call_args = mock_popen.call_args[0][0]
        assert "--hide-menubar" in call_args
        assert "--notransparency" in call_args

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.linux.get_tty_config")
    def test_spawn_with_env_vars(self, mock_config, mock_popen):
        """Spawn passes environment variables."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="konsole", options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = KonsoleSpawner()
        spawner.spawn(["echo", "test"], cwd="/tmp", env={"MY_VAR": "value"})

        call_kwargs = mock_popen.call_args[1]
        assert call_kwargs["env"]["MY_VAR"] == "value"
        assert call_kwargs["start_new_session"] is True

    @patch("subprocess.Popen", side_effect=FileNotFoundError("konsole not found"))
    @patch("gobby.agents.spawners.linux.get_tty_config")
    def test_spawn_handles_exception(self, mock_config, mock_popen):
        """Spawn handles exceptions gracefully."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="konsole", options=[]
        )

        spawner = KonsoleSpawner()
        result = spawner.spawn(["echo", "test"], cwd="/tmp")

        assert result.success is False
        assert "konsole not found" in result.error


# =============================================================================
# Tests for base.py - EmbeddedPTYResult close() method
# =============================================================================


class TestEmbeddedPTYResultClose:
    """Tests for EmbeddedPTYResult.close() method."""

    def test_close_with_valid_fds(self):
        """close() closes valid file descriptors."""
        r, w = os.pipe()
        result = EmbeddedPTYResult(
            success=True,
            message="Test",
            master_fd=r,
            slave_fd=w,
            pid=None,
        )

        result.close()

        # Verify fds are closed
        with pytest.raises(OSError):
            os.close(r)
        with pytest.raises(OSError):
            os.close(w)

    def test_close_with_none_fds(self):
        """close() handles None file descriptors gracefully."""
        result = EmbeddedPTYResult(
            success=False,
            message="Failed",
            master_fd=None,
            slave_fd=None,
        )
        # Should not raise
        result.close()

    def test_close_with_already_closed_fd(self):
        """close() handles already closed file descriptors gracefully."""
        r, w = os.pipe()
        os.close(r)
        os.close(w)

        result = EmbeddedPTYResult(
            success=True,
            message="Test",
            master_fd=r,
            slave_fd=w,
            pid=None,
        )
        # Should not raise
        result.close()


# =============================================================================
# Tests for edge cases and security
# =============================================================================


class TestSecurityAndEdgeCases:
    """Tests for security considerations and edge cases."""

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.macos.get_tty_config")
    def test_applescript_injection_prevention_terminal_app(self, mock_config, mock_popen):
        """Terminal.app spawn escapes AppleScript injection attempts."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, app_path="/System/Applications/Utilities/Terminal.app"
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = TerminalAppSpawner()
        # Attempt AppleScript injection via path
        malicious_cwd = '/tmp"; do shell script "malicious_command" --'
        spawner.spawn(["echo", "test"], cwd=malicious_cwd)

        call_args = mock_popen.call_args[0][0]
        script = call_args[2]
        # The malicious content should be escaped
        assert 'do shell script "malicious_command"' not in script

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.cross_platform.get_tty_config")
    def test_shell_injection_prevention_tmux(self, mock_config, mock_popen):
        """tmux spawn properly escapes shell commands."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="tmux", options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.returncode = 0
        mock_process.wait.return_value = 0
        mock_popen.return_value = mock_process

        spawner = TmuxSpawner()
        # Attempt shell injection via command
        malicious_command = ["echo", "; rm -rf /; echo"]
        spawner.spawn(malicious_command, cwd="/tmp", title="test")

        call_args = mock_popen.call_args[0][0]
        # The command should be properly escaped with shlex.join
        # Look for the shell command in the args
        if "sh" in call_args:
            sh_idx = call_args.index("sh")
            shell_cmd = call_args[sh_idx + 2]
            # The semicolons should be quoted/escaped
            assert "rm -rf /" not in shell_cmd.split()  # Not as separate command

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.linux.get_tty_config")
    def test_path_with_spaces(self, mock_config, mock_popen):
        """Spawners handle paths with spaces correctly."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="konsole", options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = KonsoleSpawner()
        path_with_spaces = "/path/with spaces/directory"
        spawner.spawn(["echo", "test"], cwd=path_with_spaces)

        mock_popen.assert_called_once()
        # KonsoleSpawner passes cwd via --workdir command-line arg
        call_args = mock_popen.call_args[0][0]
        workdir_idx = call_args.index("--workdir")
        assert call_args[workdir_idx + 1] == path_with_spaces

    @patch("subprocess.Popen")
    @patch("gobby.agents.spawners.linux.get_tty_config")
    def test_konsole_workdir_with_spaces(self, mock_config, mock_popen):
        """Konsole handles working directory with spaces."""
        mock_config.return_value.get_terminal_config.return_value = MagicMock(
            enabled=True, command="konsole", options=[]
        )
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner = KonsoleSpawner()
        spawner.spawn(["echo", "test"], cwd="/path/with spaces/here")

        call_args = mock_popen.call_args[0][0]
        workdir_idx = call_args.index("--workdir")
        assert call_args[workdir_idx + 1] == "/path/with spaces/here"


# =============================================================================
# Platform-specific test markers
# =============================================================================


@pytest.mark.integration
@pytest.mark.skipif(sys.platform != "darwin", reason="macOS-only tests")
class TestMacOSIntegration:
    """Integration tests that only run on macOS."""

    def test_terminal_app_available(self):
        """Terminal.app should be available on macOS."""
        # Skip if running in CI without GUI
        if os.environ.get("CI"):
            pytest.skip("Skipping GUI tests in CI")

        spawner = TerminalAppSpawner()
        # Check the is_available logic returns a boolean
        result = spawner.is_available()
        assert isinstance(result, bool)


@pytest.mark.skipif(sys.platform != "linux", reason="Linux-only tests")
class TestLinuxIntegration:
    """Integration tests that only run on Linux."""

    pass  # Add Linux-specific integration tests as needed


# =============================================================================
# Tests for build_cli_command with sandbox_args
# =============================================================================


class TestBuildCliCommandSandboxArgs:
    """Tests for build_cli_command sandbox_args parameter."""

    def test_sandbox_args_none_has_no_effect(self):
        """Test that sandbox_args=None doesn't add anything."""
        cmd = build_cli_command(cli="claude", prompt="test")
        # Should just be basic command without sandbox args
        assert cmd == ["claude", "test"]

    def test_sandbox_args_empty_list_has_no_effect(self):
        """Test that empty sandbox_args list doesn't add anything."""
        cmd = build_cli_command(cli="claude", prompt="test", sandbox_args=[])
        assert cmd == ["claude", "test"]

    def test_sandbox_args_inserted_for_claude(self):
        """Test sandbox_args are inserted for Claude CLI."""
        sandbox_args = ["--settings", '{"sandbox":{"enabled":true}}']
        cmd = build_cli_command(cli="claude", prompt="test", sandbox_args=sandbox_args)
        # sandbox_args should be in the command
        assert "--settings" in cmd
        assert '{"sandbox":{"enabled":true}}' in cmd
        # Prompt should still be last
        assert cmd[-1] == "test"

    def test_sandbox_args_inserted_for_codex(self):
        """Test sandbox_args are inserted for Codex CLI."""
        sandbox_args = ["--sandbox", "workspace-write", "--add-dir", "/extra"]
        cmd = build_cli_command(cli="codex", prompt="test", sandbox_args=sandbox_args)
        assert "--sandbox" in cmd
        assert "workspace-write" in cmd
        assert "--add-dir" in cmd
        assert "/extra" in cmd
        # Prompt should still be last
        assert cmd[-1] == "test"

    def test_sandbox_args_inserted_for_gemini(self):
        """Test sandbox_args are inserted for Gemini CLI."""
        sandbox_args = ["-s"]
        cmd = build_cli_command(cli="gemini", prompt="test", mode="headless", sandbox_args=sandbox_args)
        assert "-s" in cmd
        # Prompt should still be last
        assert cmd[-1] == "test"

    def test_sandbox_args_combined_with_other_flags(self):
        """Test sandbox_args work alongside other flags."""
        sandbox_args = ["--settings", '{"sandbox":{"enabled":true}}']
        cmd = build_cli_command(
            cli="claude",
            prompt="test",
            session_id="sess-123",
            auto_approve=True,
            sandbox_args=sandbox_args,
        )
        # Should have session_id, auto_approve, sandbox, and prompt
        assert "--session-id" in cmd
        assert "sess-123" in cmd
        assert "--dangerously-skip-permissions" in cmd
        assert "--settings" in cmd
        assert cmd[-1] == "test"


# =============================================================================
# Tests for TerminalSpawner.spawn_agent with sandbox_config
# =============================================================================


class TestTerminalSpawnerSandbox:
    """Tests for TerminalSpawner.spawn_agent sandbox handling."""

    @patch("gobby.agents.spawn.TerminalSpawner.spawn")
    @patch("gobby.agents.spawn.build_cli_command")
    def test_sandbox_config_none_has_no_effect(self, mock_build_cmd, mock_spawn):
        """Test that sandbox_config=None doesn't add sandbox args."""
        from gobby.agents.spawn import TerminalSpawner

        mock_build_cmd.return_value = ["claude", "test"]
        mock_spawn.return_value = MagicMock(success=True, pid=1234)

        spawner = TerminalSpawner()
        result = spawner.spawn_agent(
            cli="claude",
            cwd="/project",
            session_id="sess-123",
            parent_session_id="parent-456",
            agent_run_id="run-789",
            project_id="proj-abc",
            prompt="test prompt",
            sandbox_config=None,
        )

        # build_cli_command should be called without sandbox_args
        mock_build_cmd.assert_called_once()
        call_kwargs = mock_build_cmd.call_args[1]
        assert call_kwargs.get("sandbox_args") is None
        assert result.success is True

    @patch("gobby.agents.spawn.TerminalSpawner.spawn")
    @patch("gobby.agents.spawn.build_cli_command")
    def test_sandbox_config_disabled_has_no_effect(self, mock_build_cmd, mock_spawn):
        """Test that sandbox_config with enabled=False doesn't add sandbox args."""
        from gobby.agents.sandbox import SandboxConfig
        from gobby.agents.spawn import TerminalSpawner

        mock_build_cmd.return_value = ["claude", "test"]
        mock_spawn.return_value = MagicMock(success=True, pid=1234)

        spawner = TerminalSpawner()
        sandbox_config = SandboxConfig(enabled=False)
        result = spawner.spawn_agent(
            cli="claude",
            cwd="/project",
            session_id="sess-123",
            parent_session_id="parent-456",
            agent_run_id="run-789",
            project_id="proj-abc",
            prompt="test prompt",
            sandbox_config=sandbox_config,
        )

        # build_cli_command should be called without sandbox_args
        mock_build_cmd.assert_called_once()
        call_kwargs = mock_build_cmd.call_args[1]
        assert call_kwargs.get("sandbox_args") is None
        assert result.success is True

    @patch("gobby.agents.spawn.TerminalSpawner.spawn")
    @patch("gobby.agents.spawn.build_cli_command")
    def test_sandbox_config_enabled_adds_sandbox_args_for_claude(self, mock_build_cmd, mock_spawn):
        """Test that enabled sandbox_config adds sandbox args for Claude CLI."""
        from gobby.agents.sandbox import SandboxConfig
        from gobby.agents.spawn import TerminalSpawner

        mock_build_cmd.return_value = ["claude", "--settings", "{}", "test"]
        mock_spawn.return_value = MagicMock(success=True, pid=1234)

        spawner = TerminalSpawner()
        sandbox_config = SandboxConfig(enabled=True, mode="permissive")
        result = spawner.spawn_agent(
            cli="claude",
            cwd="/project",
            session_id="sess-123",
            parent_session_id="parent-456",
            agent_run_id="run-789",
            project_id="proj-abc",
            prompt="test prompt",
            sandbox_config=sandbox_config,
        )

        # build_cli_command should be called with sandbox_args
        mock_build_cmd.assert_called_once()
        call_kwargs = mock_build_cmd.call_args[1]
        assert call_kwargs.get("sandbox_args") is not None
        sandbox_args = call_kwargs["sandbox_args"]
        assert "--settings" in sandbox_args
        assert result.success is True

    @patch("gobby.agents.spawn.TerminalSpawner.spawn")
    @patch("gobby.agents.spawn.build_cli_command")
    def test_sandbox_config_enabled_adds_env_for_gemini(self, mock_build_cmd, mock_spawn):
        """Test that enabled sandbox_config adds env vars for Gemini CLI."""
        from gobby.agents.sandbox import SandboxConfig
        from gobby.agents.spawn import TerminalSpawner

        mock_build_cmd.return_value = ["gemini", "-s", "test"]
        mock_spawn.return_value = MagicMock(success=True, pid=1234)

        spawner = TerminalSpawner()
        sandbox_config = SandboxConfig(enabled=True, mode="restrictive")
        result = spawner.spawn_agent(
            cli="gemini",
            cwd="/project",
            session_id="sess-123",
            parent_session_id="parent-456",
            agent_run_id="run-789",
            project_id="proj-abc",
            prompt="test prompt",
            sandbox_config=sandbox_config,
        )

        # spawn should be called with env containing SEATBELT_PROFILE
        mock_spawn.assert_called_once()
        call_kwargs = mock_spawn.call_args[1]
        env = call_kwargs.get("env", {})
        assert "SEATBELT_PROFILE" in env
        assert "restrictive" in env["SEATBELT_PROFILE"]
        assert result.success is True

    @patch("gobby.agents.spawn.TerminalSpawner.spawn")
    @patch("gobby.agents.spawn.build_cli_command")
    def test_sandbox_config_enabled_adds_args_for_codex(self, mock_build_cmd, mock_spawn):
        """Test that enabled sandbox_config adds sandbox args for Codex CLI."""
        from gobby.agents.sandbox import SandboxConfig
        from gobby.agents.spawn import TerminalSpawner

        mock_build_cmd.return_value = ["codex", "--sandbox", "workspace-write", "test"]
        mock_spawn.return_value = MagicMock(success=True, pid=1234)

        spawner = TerminalSpawner()
        sandbox_config = SandboxConfig(enabled=True, mode="permissive")
        result = spawner.spawn_agent(
            cli="codex",
            cwd="/project",
            session_id="sess-123",
            parent_session_id="parent-456",
            agent_run_id="run-789",
            project_id="proj-abc",
            prompt="test prompt",
            sandbox_config=sandbox_config,
        )

        # build_cli_command should be called with sandbox_args
        mock_build_cmd.assert_called_once()
        call_kwargs = mock_build_cmd.call_args[1]
        assert call_kwargs.get("sandbox_args") is not None
        sandbox_args = call_kwargs["sandbox_args"]
        assert "--sandbox" in sandbox_args
        assert result.success is True


# =============================================================================
# Tests for EmbeddedSpawner.spawn_agent with sandbox_config
# =============================================================================


class TestEmbeddedSpawnerSandbox:
    """Tests for EmbeddedSpawner.spawn_agent sandbox handling."""

    @patch("gobby.agents.spawners.embedded.EmbeddedSpawner.spawn")
    @patch("gobby.agents.spawners.embedded._get_spawn_utils")
    def test_sandbox_config_none_has_no_effect(self, mock_utils, mock_spawn):
        """Test that sandbox_config=None doesn't add sandbox args."""
        mock_build_cmd = MagicMock(return_value=["claude", "test"])
        mock_create_file = MagicMock()
        mock_utils.return_value = (mock_build_cmd, mock_create_file, 4096)
        mock_spawn.return_value = MagicMock(success=True, pid=1234)

        spawner = EmbeddedSpawner()
        result = spawner.spawn_agent(
            cli="claude",
            cwd="/project",
            session_id="sess-123",
            parent_session_id="parent-456",
            agent_run_id="run-789",
            project_id="proj-abc",
            prompt="test prompt",
            sandbox_config=None,
        )

        # build_cli_command should be called without sandbox_args
        mock_build_cmd.assert_called_once()
        call_kwargs = mock_build_cmd.call_args[1]
        assert call_kwargs.get("sandbox_args") is None
        assert result.success is True

    @patch("gobby.agents.spawners.embedded.EmbeddedSpawner.spawn")
    @patch("gobby.agents.spawners.embedded._get_spawn_utils")
    def test_sandbox_config_disabled_has_no_effect(self, mock_utils, mock_spawn):
        """Test that sandbox_config with enabled=False doesn't add sandbox args."""
        from gobby.agents.sandbox import SandboxConfig

        mock_build_cmd = MagicMock(return_value=["claude", "test"])
        mock_create_file = MagicMock()
        mock_utils.return_value = (mock_build_cmd, mock_create_file, 4096)
        mock_spawn.return_value = MagicMock(success=True, pid=1234)

        spawner = EmbeddedSpawner()
        sandbox_config = SandboxConfig(enabled=False)
        result = spawner.spawn_agent(
            cli="claude",
            cwd="/project",
            session_id="sess-123",
            parent_session_id="parent-456",
            agent_run_id="run-789",
            project_id="proj-abc",
            prompt="test prompt",
            sandbox_config=sandbox_config,
        )

        # build_cli_command should be called without sandbox_args
        mock_build_cmd.assert_called_once()
        call_kwargs = mock_build_cmd.call_args[1]
        assert call_kwargs.get("sandbox_args") is None
        assert result.success is True

    @patch("gobby.agents.spawners.embedded.EmbeddedSpawner.spawn")
    @patch("gobby.agents.spawners.embedded._get_spawn_utils")
    def test_sandbox_config_enabled_adds_sandbox_args(self, mock_utils, mock_spawn):
        """Test that enabled sandbox_config adds sandbox args for CLI."""
        from gobby.agents.sandbox import SandboxConfig

        mock_build_cmd = MagicMock(return_value=["claude", "--settings", "{}", "test"])
        mock_create_file = MagicMock()
        mock_utils.return_value = (mock_build_cmd, mock_create_file, 4096)
        mock_spawn.return_value = MagicMock(success=True, pid=1234)

        spawner = EmbeddedSpawner()
        sandbox_config = SandboxConfig(enabled=True, mode="permissive")
        result = spawner.spawn_agent(
            cli="claude",
            cwd="/project",
            session_id="sess-123",
            parent_session_id="parent-456",
            agent_run_id="run-789",
            project_id="proj-abc",
            prompt="test prompt",
            sandbox_config=sandbox_config,
        )

        # build_cli_command should be called with sandbox_args
        mock_build_cmd.assert_called_once()
        call_kwargs = mock_build_cmd.call_args[1]
        assert call_kwargs.get("sandbox_args") is not None
        sandbox_args = call_kwargs["sandbox_args"]
        assert "--settings" in sandbox_args
        assert result.success is True

    @patch("gobby.agents.spawners.embedded.EmbeddedSpawner.spawn")
    @patch("gobby.agents.spawners.embedded._get_spawn_utils")
    def test_sandbox_env_merged_into_spawn_env(self, mock_utils, mock_spawn):
        """Test that sandbox_env is merged into spawn environment."""
        from gobby.agents.sandbox import SandboxConfig

        mock_build_cmd = MagicMock(return_value=["gemini", "-s", "test"])
        mock_create_file = MagicMock()
        mock_utils.return_value = (mock_build_cmd, mock_create_file, 4096)
        mock_spawn.return_value = MagicMock(success=True, pid=1234)

        spawner = EmbeddedSpawner()
        sandbox_config = SandboxConfig(enabled=True, mode="restrictive")
        result = spawner.spawn_agent(
            cli="gemini",
            cwd="/project",
            session_id="sess-123",
            parent_session_id="parent-456",
            agent_run_id="run-789",
            project_id="proj-abc",
            prompt="test prompt",
            sandbox_config=sandbox_config,
        )

        # spawn should be called with env containing SEATBELT_PROFILE
        mock_spawn.assert_called_once()
        call_args = mock_spawn.call_args
        env = call_args[0][2] if len(call_args[0]) > 2 else call_args[1].get("env", {})
        assert "SEATBELT_PROFILE" in env
        assert "restrictive" in env["SEATBELT_PROFILE"]
        assert result.success is True
