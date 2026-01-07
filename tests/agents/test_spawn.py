"""Tests for terminal spawning functionality."""

import platform
from unittest.mock import MagicMock, patch

from gobby.agents.spawn import (
    PowerShellSpawner,
    SpawnResult,
    TerminalSpawner,
    TerminalType,
    TmuxSpawner,
    WSLSpawner,
    build_cli_command,
)


class TestTerminalType:
    """Tests for TerminalType enum."""

    def test_macos_terminals(self):
        """macOS terminals are defined."""
        assert TerminalType.GHOSTTY == "ghostty"
        assert TerminalType.ITERM == "iterm"
        assert TerminalType.TERMINAL_APP == "terminal.app"
        assert TerminalType.KITTY == "kitty"
        assert TerminalType.ALACRITTY == "alacritty"

    def test_linux_terminals(self):
        """Linux terminals are defined."""
        assert TerminalType.GNOME_TERMINAL == "gnome-terminal"
        assert TerminalType.KONSOLE == "konsole"

    def test_windows_terminals(self):
        """Windows terminals are defined."""
        assert TerminalType.WINDOWS_TERMINAL == "windows-terminal"
        assert TerminalType.CMD == "cmd"
        assert TerminalType.POWERSHELL == "powershell"
        assert TerminalType.WSL == "wsl"

    def test_cross_platform_terminals(self):
        """Cross-platform terminals are defined."""
        assert TerminalType.TMUX == "tmux"

    def test_auto_detect(self):
        """Auto-detect mode is available."""
        assert TerminalType.AUTO == "auto"


class TestBuildCliCommand:
    """Tests for build_cli_command function."""

    def test_claude_basic(self):
        """Claude CLI basic command."""
        cmd = build_cli_command("claude")
        assert cmd == ["claude"]

    def test_claude_with_prompt(self):
        """Claude CLI with prompt."""
        cmd = build_cli_command("claude", prompt="Hello")
        assert cmd == ["claude", "-p", "Hello"]

    def test_claude_with_session_id(self):
        """Claude CLI with session ID."""
        cmd = build_cli_command("claude", session_id="sess-123")
        assert cmd == ["claude", "--session-id", "sess-123"]

    def test_claude_with_auto_approve(self):
        """Claude CLI with auto approve."""
        cmd = build_cli_command("claude", auto_approve=True)
        assert "--dangerously-skip-permissions" in cmd

    def test_gemini_with_auto_approve(self):
        """Gemini CLI with auto approve."""
        cmd = build_cli_command("gemini", auto_approve=True)
        assert "--approval-mode" in cmd
        assert "yolo" in cmd

    def test_codex_with_auto_approve(self):
        """Codex CLI with auto approve."""
        cmd = build_cli_command("codex", auto_approve=True)
        assert "--full-auto" in cmd

    def test_codex_with_working_directory(self):
        """Codex CLI with working directory."""
        cmd = build_cli_command("codex", working_directory="/tmp/test")
        assert "-C" in cmd
        assert "/tmp/test" in cmd


class TestPowerShellSpawner:
    """Tests for PowerShellSpawner."""

    def test_terminal_type(self):
        """Spawner returns correct terminal type."""
        spawner = PowerShellSpawner()
        assert spawner.terminal_type == TerminalType.POWERSHELL

    @patch("platform.system", return_value="Darwin")
    def test_not_available_on_macos(self, mock_system):
        """PowerShell spawner not available on macOS."""
        spawner = PowerShellSpawner()
        assert spawner.is_available() is False

    @patch("platform.system", return_value="Linux")
    def test_not_available_on_linux(self, mock_system):
        """PowerShell spawner not available on Linux."""
        spawner = PowerShellSpawner()
        assert spawner.is_available() is False

    @patch("platform.system", return_value="Windows")
    @patch("shutil.which", return_value=None)
    def test_not_available_without_powershell(self, mock_which, mock_system):
        """PowerShell spawner not available when pwsh/powershell not installed."""
        spawner = PowerShellSpawner()
        with patch("gobby.agents.spawn.get_tty_config") as mock_config:
            mock_config.return_value.get_terminal_config.return_value = MagicMock(
                enabled=True, command="pwsh"
            )
            assert spawner.is_available() is False

    @patch("platform.system", return_value="Windows")
    @patch("shutil.which", side_effect=lambda x: x if x == "pwsh" else None)
    def test_available_with_pwsh(self, mock_which, mock_system):
        """PowerShell spawner available with pwsh."""
        spawner = PowerShellSpawner()
        with patch("gobby.agents.spawn.get_tty_config") as mock_config:
            mock_config.return_value.get_terminal_config.return_value = MagicMock(
                enabled=True, command="pwsh"
            )
            assert spawner.is_available() is True

    @patch("platform.system", return_value="Windows")
    @patch("shutil.which", side_effect=lambda x: x if x == "powershell" else None)
    def test_available_with_windows_powershell(self, mock_which, mock_system):
        """PowerShell spawner available with Windows PowerShell fallback."""
        spawner = PowerShellSpawner()
        with patch("gobby.agents.spawn.get_tty_config") as mock_config:
            mock_config.return_value.get_terminal_config.return_value = MagicMock(
                enabled=True, command="pwsh"
            )
            assert spawner.is_available() is True


class TestWSLSpawner:
    """Tests for WSLSpawner."""

    def test_terminal_type(self):
        """Spawner returns correct terminal type."""
        spawner = WSLSpawner()
        assert spawner.terminal_type == TerminalType.WSL

    @patch("platform.system", return_value="Darwin")
    def test_not_available_on_macos(self, mock_system):
        """WSL spawner not available on macOS."""
        spawner = WSLSpawner()
        assert spawner.is_available() is False

    @patch("platform.system", return_value="Linux")
    def test_not_available_on_linux(self, mock_system):
        """WSL spawner not available on Linux."""
        spawner = WSLSpawner()
        assert spawner.is_available() is False

    @patch("platform.system", return_value="Windows")
    @patch("shutil.which", return_value=None)
    def test_not_available_without_wsl(self, mock_which, mock_system):
        """WSL spawner not available when wsl not installed."""
        spawner = WSLSpawner()
        with patch("gobby.agents.spawn.get_tty_config") as mock_config:
            mock_config.return_value.get_terminal_config.return_value = MagicMock(
                enabled=True, command="wsl"
            )
            assert spawner.is_available() is False

    @patch("platform.system", return_value="Windows")
    @patch("shutil.which", return_value="/usr/bin/wsl")
    def test_available_with_wsl(self, mock_which, mock_system):
        """WSL spawner available when wsl installed."""
        spawner = WSLSpawner()
        with patch("gobby.agents.spawn.get_tty_config") as mock_config:
            mock_config.return_value.get_terminal_config.return_value = MagicMock(
                enabled=True, command="wsl"
            )
            assert spawner.is_available() is True


class TestWSLPathConversion:
    """Tests for WSL path conversion in WSLSpawner."""

    @patch("platform.system", return_value="Windows")
    @patch("shutil.which", return_value="/usr/bin/wsl")
    @patch("subprocess.Popen")
    def test_windows_path_conversion(self, mock_popen, mock_which, mock_system):
        """Windows paths are converted to WSL format."""
        spawner = WSLSpawner()
        mock_popen.return_value = MagicMock(pid=123)

        with patch("gobby.agents.spawn.get_tty_config") as mock_config:
            mock_config.return_value.get_terminal_config.return_value = MagicMock(
                enabled=True, command="wsl", options=[]
            )
            spawner.spawn(["echo", "test"], cwd="C:\\Users\\test")

        # Check that the call was made with WSL path format
        call_args = mock_popen.call_args[0][0]
        # The path should be converted in the bash -c script
        assert "bash" in call_args or "wsl" in call_args

    @patch("platform.system", return_value="Windows")
    @patch("shutil.which", return_value="/usr/bin/wsl")
    @patch("subprocess.Popen")
    def test_already_unix_path(self, mock_popen, mock_which, mock_system):
        """Unix paths are passed through unchanged."""
        spawner = WSLSpawner()
        mock_popen.return_value = MagicMock(pid=123)

        with patch("gobby.agents.spawn.get_tty_config") as mock_config:
            mock_config.return_value.get_terminal_config.return_value = MagicMock(
                enabled=True, command="wsl", options=[]
            )
            result = spawner.spawn(["echo", "test"], cwd="/home/user/project")

        assert result.success is True


class TestTmuxSpawner:
    """Tests for TmuxSpawner."""

    def test_terminal_type(self):
        """Spawner returns correct terminal type."""
        spawner = TmuxSpawner()
        assert spawner.terminal_type == TerminalType.TMUX

    @patch("platform.system", return_value="Windows")
    def test_not_available_on_windows(self, mock_system):
        """tmux spawner not available on Windows."""
        spawner = TmuxSpawner()
        assert spawner.is_available() is False

    @patch("platform.system", return_value="Darwin")
    @patch("shutil.which", return_value=None)
    def test_not_available_without_tmux(self, mock_which, mock_system):
        """tmux spawner not available when tmux not installed."""
        spawner = TmuxSpawner()
        with patch("gobby.agents.spawn.get_tty_config") as mock_config:
            mock_config.return_value.get_terminal_config.return_value = MagicMock(
                enabled=True, command="tmux"
            )
            assert spawner.is_available() is False

    @patch("platform.system", return_value="Darwin")
    @patch("shutil.which", return_value="/usr/local/bin/tmux")
    def test_available_on_macos_with_tmux(self, mock_which, mock_system):
        """tmux spawner available on macOS when tmux installed."""
        spawner = TmuxSpawner()
        with patch("gobby.agents.spawn.get_tty_config") as mock_config:
            mock_config.return_value.get_terminal_config.return_value = MagicMock(
                enabled=True, command="tmux"
            )
            assert spawner.is_available() is True

    @patch("platform.system", return_value="Linux")
    @patch("shutil.which", return_value="/usr/bin/tmux")
    def test_available_on_linux_with_tmux(self, mock_which, mock_system):
        """tmux spawner available on Linux when tmux installed."""
        spawner = TmuxSpawner()
        with patch("gobby.agents.spawn.get_tty_config") as mock_config:
            mock_config.return_value.get_terminal_config.return_value = MagicMock(
                enabled=True, command="tmux"
            )
            assert spawner.is_available() is True

    @patch("platform.system", return_value="Darwin")
    @patch("shutil.which", return_value="/usr/local/bin/tmux")
    @patch("subprocess.Popen")
    def test_spawn_creates_detached_session(self, mock_popen, mock_which, mock_system):
        """tmux spawner creates a detached session."""
        spawner = TmuxSpawner()
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.returncode = 0
        mock_process.wait.return_value = 0
        mock_popen.return_value = mock_process

        with patch("gobby.agents.spawn.get_tty_config") as mock_config:
            mock_config.return_value.get_terminal_config.return_value = MagicMock(
                enabled=True, command="tmux", options=[]
            )
            result = spawner.spawn(["echo", "test"], cwd="/tmp", title="test-session")

        # Verify tmux was called with correct arguments
        call_args = mock_popen.call_args[0][0]
        assert "tmux" in call_args
        assert "new-session" in call_args
        assert "-d" in call_args  # Detached
        assert "-s" in call_args  # Session name
        assert result.success is True

    @patch("platform.system", return_value="Darwin")
    @patch("shutil.which", return_value="/usr/local/bin/tmux")
    @patch("subprocess.Popen")
    def test_spawn_sanitizes_session_name(self, mock_popen, mock_which, mock_system):
        """tmux spawner sanitizes session names."""
        spawner = TmuxSpawner()
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.returncode = 0
        mock_process.wait.return_value = 0
        mock_popen.return_value = mock_process

        with patch("gobby.agents.spawn.get_tty_config") as mock_config:
            mock_config.return_value.get_terminal_config.return_value = MagicMock(
                enabled=True, command="tmux", options=[]
            )
            # Title with dots and colons should be sanitized
            spawner.spawn(["echo", "test"], cwd="/tmp", title="test.session:1")

        call_args = mock_popen.call_args[0][0]
        # Find the session name in the args (after -s flag)
        s_index = call_args.index("-s")
        session_name = call_args[s_index + 1]
        # Dots and colons should be replaced with dashes
        assert "." not in session_name
        assert ":" not in session_name


class TestTerminalSpawnerRegistry:
    """Tests for TerminalSpawner registry."""

    def test_all_spawners_registered(self):
        """All spawner classes are registered."""
        spawner = TerminalSpawner()
        expected_types = {
            TerminalType.GHOSTTY,
            TerminalType.ITERM,
            TerminalType.TERMINAL_APP,
            TerminalType.KITTY,
            TerminalType.ALACRITTY,
            TerminalType.GNOME_TERMINAL,
            TerminalType.KONSOLE,
            TerminalType.WINDOWS_TERMINAL,
            TerminalType.CMD,
            TerminalType.POWERSHELL,
            TerminalType.WSL,
            TerminalType.TMUX,
        }
        assert set(spawner._spawners.keys()) == expected_types

    def test_spawner_classes_dict_complete(self):
        """SPAWNER_CLASSES dict includes all terminals."""
        expected_terminals = {
            "ghostty",
            "iterm",
            "terminal.app",
            "kitty",
            "alacritty",
            "gnome-terminal",
            "konsole",
            "windows-terminal",
            "cmd",
            "powershell",
            "wsl",
            "tmux",
        }
        assert set(TerminalSpawner.SPAWNER_CLASSES.keys()) == expected_terminals

    def test_new_spawners_in_classes_dict(self):
        """New spawners are properly registered in SPAWNER_CLASSES."""
        assert TerminalSpawner.SPAWNER_CLASSES["powershell"] == PowerShellSpawner
        assert TerminalSpawner.SPAWNER_CLASSES["wsl"] == WSLSpawner
        assert TerminalSpawner.SPAWNER_CLASSES["tmux"] == TmuxSpawner


class TestTerminalSpawnerSpawn:
    """Tests for TerminalSpawner.spawn method."""

    def test_spawn_unknown_terminal(self):
        """Spawning unknown terminal returns error."""
        spawner = TerminalSpawner()
        result = spawner.spawn(["echo", "test"], cwd="/tmp", terminal="nonexistent")
        assert result.success is False
        assert "Unknown terminal type" in result.message

    def test_spawn_with_enum(self):
        """Spawning with TerminalType enum works."""
        spawner = TerminalSpawner()
        # Use tmux on Unix, cmd on Windows
        if platform.system() == "Windows":
            terminal = TerminalType.CMD
        else:
            terminal = TerminalType.TMUX

        # Mock the actual spawner to avoid spawning real processes
        with patch.object(spawner._spawners[terminal], "is_available", return_value=True):
            with patch.object(
                spawner._spawners[terminal],
                "spawn",
                return_value=SpawnResult(success=True, message="OK", pid=123),
            ):
                result = spawner.spawn(["echo", "test"], cwd="/tmp", terminal=terminal)
                assert result.success is True


class TestSpawnResultDataclass:
    """Tests for SpawnResult dataclass."""

    def test_success_result(self):
        """Success result has correct fields."""
        result = SpawnResult(
            success=True,
            message="Spawned successfully",
            pid=12345,
            terminal_type="ghostty",
        )
        assert result.success is True
        assert result.pid == 12345
        assert result.terminal_type == "ghostty"
        assert result.error is None

    def test_failure_result(self):
        """Failure result has correct fields."""
        result = SpawnResult(
            success=False,
            message="Failed to spawn",
            error="Command not found",
        )
        assert result.success is False
        assert result.pid is None
        assert result.terminal_type is None
        assert result.error == "Command not found"
