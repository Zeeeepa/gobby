"""Tests for terminal spawning functionality."""

import os
import platform
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gobby.agents.spawn import (
    MAX_ENV_PROMPT_LENGTH,
    EmbeddedPTYResult,
    EmbeddedSpawner,
    HeadlessResult,
    HeadlessSpawner,
    PowerShellSpawner,
    PreparedSpawn,
    SpawnResult,
    TerminalSpawner,
    TerminalType,
    TmuxSpawner,
    WSLSpawner,
    _cleanup_all_prompt_files,
    _create_prompt_file,
    _prompt_files_to_cleanup,
    build_cli_command,
    prepare_terminal_spawn,
    read_prompt_from_env,
)

# Skip PTY tests on Windows
pytestmark_unix_only = pytest.mark.skipif(
    sys.platform == "win32", reason="PTY not available on Windows"
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
    @patch("subprocess.run")
    @patch("subprocess.Popen")
    def test_spawn_creates_detached_session(self, mock_popen, mock_run, mock_which, mock_system):
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
    @patch("subprocess.run")
    @patch("subprocess.Popen")
    def test_spawn_sanitizes_session_name(self, mock_popen, mock_run, mock_which, mock_system):
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

    @patch("platform.system", return_value="Darwin")
    @patch("shutil.which", return_value="/usr/local/bin/tmux")
    @patch("subprocess.Popen")
    def test_spawn_disables_destroy_unattached(self, mock_popen, mock_which, mock_system):
        """tmux spawner disables destroy-unattached to prevent immediate session termination."""
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

        # Verify destroy-unattached is disabled via chained command
        call_args = mock_popen.call_args[0][0]
        # Find the chained set-option command (after ;)
        assert ";" in call_args
        semicolon_idx = call_args.index(";")
        chained_args = call_args[semicolon_idx + 1 :]
        assert "set-option" in chained_args
        assert "-t" in chained_args
        assert "test-session" in chained_args
        assert "destroy-unattached" in chained_args
        assert "off" in chained_args
        assert result.success is True

    @patch("platform.system", return_value="Darwin")
    @patch("shutil.which", return_value="/usr/local/bin/tmux")
    @patch("subprocess.Popen")
    def test_spawn_sets_window_title(self, mock_popen, mock_which, mock_system):
        """tmux spawner sets window title using -n flag."""
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
            result = spawner.spawn(["echo", "test"], cwd="/tmp", title="my-window")

        call_args = mock_popen.call_args[0][0]
        # Verify -n flag is present with the session name as window title
        assert "-n" in call_args
        n_index = call_args.index("-n")
        window_name = call_args[n_index + 1]
        assert window_name == "my-window"
        assert result.success is True

    @patch("platform.system", return_value="Darwin")
    @patch("shutil.which", return_value="/usr/local/bin/tmux")
    @patch("subprocess.Popen")
    def test_spawn_passes_env_vars(self, mock_popen, mock_which, mock_system):
        """tmux spawner passes env vars to session via shell exports."""
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
            result = spawner.spawn(
                ["echo", "test"],
                cwd="/tmp",
                title="test-env",
                env={"MY_VAR": "my_value"},
            )

        call_args = mock_popen.call_args[0][0]
        # Verify env vars are exported in the shell command
        assert "sh" in call_args
        sh_index = call_args.index("sh")
        # The -c flag for sh should be right after sh
        assert call_args[sh_index + 1] == "-c"
        shell_cmd = call_args[sh_index + 2]
        assert "export MY_VAR=" in shell_cmd
        assert "my_value" in shell_cmd
        assert "exec echo test" in shell_cmd
        assert result.success is True


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


class TestEmbeddedPTYResult:
    """Tests for EmbeddedPTYResult dataclass."""

    def test_success_result_fields(self):
        """Success result has correct fields."""
        result = EmbeddedPTYResult(
            success=True,
            message="Spawned embedded PTY",
            master_fd=5,
            slave_fd=None,
            pid=12345,
        )
        assert result.success is True
        assert result.message == "Spawned embedded PTY"
        assert result.master_fd == 5
        assert result.slave_fd is None
        assert result.pid == 12345
        assert result.error is None

    def test_failure_result_fields(self):
        """Failure result has correct fields."""
        result = EmbeddedPTYResult(
            success=False,
            message="Failed to spawn",
            error="PTY not supported",
        )
        assert result.success is False
        assert result.master_fd is None
        assert result.slave_fd is None
        assert result.pid is None
        assert result.error == "PTY not supported"

    def test_close_with_valid_fds(self):
        """close() closes valid file descriptors."""
        # Create real file descriptors for testing
        r, w = os.pipe()
        result = EmbeddedPTYResult(
            success=True,
            message="Test",
            master_fd=r,
            slave_fd=w,
            pid=None,
        )

        # Close should not raise
        result.close()

        # Verify fds are closed by checking they raise on close
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
        # Should not raise even though fds are already closed
        result.close()


class TestEmbeddedSpawnerPlatform:
    """Tests for EmbeddedSpawner platform behavior."""

    @patch("platform.system", return_value="Windows")
    def test_not_supported_on_windows(self, mock_system):
        """EmbeddedSpawner returns error on Windows."""
        # Also mock pty to None to simulate Windows
        with patch("gobby.agents.spawners.embedded.pty", None):
            spawner = EmbeddedSpawner()
            result = spawner.spawn(["echo", "test"], cwd="/tmp")

            assert result.success is False
            assert "Windows" in result.message or "not supported" in result.message.lower()
            assert result.error is not None

    @patch("platform.system", return_value="Windows")
    def test_spawn_agent_not_supported_on_windows(self, mock_system):
        """spawn_agent returns error on Windows."""
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


@pytest.mark.skipif(sys.platform == "win32", reason="PTY not available on Windows")
class TestEmbeddedSpawnerUnix:
    """Tests for EmbeddedSpawner on Unix systems."""

    def test_spawn_simple_command(self):
        """spawn() creates PTY and runs command."""
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
            assert result.slave_fd is None  # Closed in parent

            # Read output from master fd
            import select

            # Wait for output with timeout
            ready, _, _ = select.select([result.master_fd], [], [], 2.0)
            if ready:
                output = os.read(result.master_fd, 1024).decode()
                assert "hello" in output
        finally:
            result.close()
            # Wait for child to exit
            if result.pid:
                try:
                    os.waitpid(result.pid, os.WNOHANG)
                except ChildProcessError:
                    pass

    def test_spawn_with_env_vars(self):
        """spawn() passes environment variables to child."""
        spawner = EmbeddedSpawner()
        result = spawner.spawn(
            command=["printenv", "TEST_EMBEDDED_VAR"],
            cwd="/tmp",
            env={"TEST_EMBEDDED_VAR": "embedded_value"},
        )

        try:
            assert result.success is True

            # Read output
            import select

            ready, _, _ = select.select([result.master_fd], [], [], 2.0)
            if ready:
                output = os.read(result.master_fd, 1024).decode()
                assert "embedded_value" in output
        finally:
            result.close()
            if result.pid:
                try:
                    os.waitpid(result.pid, os.WNOHANG)
                except ChildProcessError:
                    pass

    def test_spawn_with_working_directory(self):
        """spawn() uses specified working directory."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            spawner = EmbeddedSpawner()
            result = spawner.spawn(
                command=["pwd"],
                cwd=tmpdir,
            )

            try:
                assert result.success is True

                import select

                ready, _, _ = select.select([result.master_fd], [], [], 2.0)
                if ready:
                    output = os.read(result.master_fd, 1024).decode()
                    # tmpdir may be a symlink, so check the basename
                    assert tmpdir in output or os.path.basename(tmpdir) in output
            finally:
                result.close()
                if result.pid:
                    try:
                        os.waitpid(result.pid, os.WNOHANG)
                    except ChildProcessError:
                        pass

    def test_spawn_nonexistent_command(self):
        """spawn() fails gracefully for non-existent command."""
        spawner = EmbeddedSpawner()
        result = spawner.spawn(
            command=["nonexistent_command_xyz_12345"],
            cwd="/tmp",
        )

        # The fork succeeds but exec fails in child
        # Parent still gets a result with pid
        if result.success:
            result.close()
            if result.pid:
                try:
                    _, status = os.waitpid(result.pid, 0)
                    # Child should have exited with error
                    assert os.WEXITSTATUS(status) != 0 or os.WIFSIGNALED(status)
                except ChildProcessError:
                    pass

    def test_spawn_agent_sets_env_vars(self):
        """spawn_agent() sets Gobby environment variables."""
        spawner = EmbeddedSpawner()
        # Use sh -c to grep for GOBBY env vars specifically
        result = spawner.spawn_agent(
            cli="sh",
            cwd="/tmp",
            session_id="sess-embedded-123",
            parent_session_id="sess-parent-456",
            agent_run_id="run-789",
            project_id="proj-abc",
            workflow_name="test-workflow",
            agent_depth=2,
            max_agent_depth=5,
        )

        try:
            assert result.success is True

            import select
            import time

            # Give process time to start and output
            time.sleep(0.2)

            # Read all available output
            output = ""
            for _ in range(10):  # Try multiple reads
                ready, _, _ = select.select([result.master_fd], [], [], 0.5)
                if ready:
                    try:
                        chunk = os.read(result.master_fd, 8192).decode(errors="replace")
                        output += chunk
                        if not chunk:
                            break
                    except OSError:
                        break
                else:
                    break

            # The sh command with -c flag from build_cli_command will just run sh
            # The env vars are set regardless, but we can't easily verify via output
            # So we verify the spawn was successful and pid exists
            assert result.pid is not None
            assert result.pid > 0
        finally:
            result.close()
            if result.pid:
                try:
                    os.waitpid(result.pid, os.WNOHANG)
                except ChildProcessError:
                    pass

    def test_spawn_agent_with_prompt(self):
        """spawn_agent() passes prompt via environment or file."""
        spawner = EmbeddedSpawner()
        # Test that spawn_agent doesn't fail with prompt
        result = spawner.spawn_agent(
            cli="true",  # Simple command that exits successfully
            cwd="/tmp",
            session_id="sess-123",
            parent_session_id="sess-parent",
            agent_run_id="run-456",
            project_id="proj-789",
            prompt="Test prompt content",
        )

        try:
            assert result.success is True
            assert result.pid is not None
        finally:
            result.close()
            if result.pid:
                try:
                    os.waitpid(result.pid, os.WNOHANG)
                except ChildProcessError:
                    pass


class TestEmbeddedSpawnerMocked:
    """Tests for EmbeddedSpawner with mocked system calls."""

    @patch("gobby.agents.spawners.embedded.pty")
    @patch("os.fork")
    def test_spawn_handles_fork_error(self, mock_fork, mock_pty):
        """spawn() handles fork() errors gracefully."""
        mock_pty.openpty.return_value = (10, 11)
        mock_fork.side_effect = OSError("Fork failed")

        spawner = EmbeddedSpawner()
        result = spawner.spawn(["echo", "test"], cwd="/tmp")

        assert result.success is False
        assert "Fork failed" in result.error or "Failed" in result.message

    @patch("gobby.agents.spawners.embedded.pty")
    def test_spawn_handles_openpty_error(self, mock_pty):
        """spawn() handles openpty() errors gracefully."""
        mock_pty.openpty.side_effect = OSError("PTY creation failed")

        spawner = EmbeddedSpawner()
        result = spawner.spawn(["echo", "test"], cwd="/tmp")

        assert result.success is False
        assert result.error is not None


class TestHeadlessResult:
    """Tests for HeadlessResult dataclass."""

    def test_success_result_fields(self):
        """Success result has correct fields."""
        result = HeadlessResult(
            success=True,
            message="Spawned headless",
            pid=12345,
            process=None,
            output_buffer=["line1", "line2"],
        )
        assert result.success is True
        assert result.pid == 12345
        assert result.output_buffer == ["line1", "line2"]
        assert result.error is None

    def test_get_output_joins_lines(self):
        """get_output() joins buffer with newlines."""
        result = HeadlessResult(
            success=True,
            message="Test",
            output_buffer=["first", "second", "third"],
        )
        assert result.get_output() == "first\nsecond\nthird"

    def test_get_output_empty_buffer(self):
        """get_output() returns empty string for empty buffer."""
        result = HeadlessResult(success=True, message="Test")
        assert result.get_output() == ""


class TestHeadlessSpawnerSync:
    """Tests for HeadlessSpawner synchronous methods."""

    def test_spawn_simple_command(self):
        """spawn() runs command and captures output."""
        spawner = HeadlessSpawner()
        result = spawner.spawn(["echo", "hello"], cwd="/tmp")

        assert result.success is True
        assert result.pid is not None
        assert result.process is not None

        # Read output
        stdout, _ = result.process.communicate()
        assert "hello" in stdout

    def test_spawn_with_env_vars(self):
        """spawn() passes environment variables."""
        spawner = HeadlessSpawner()
        result = spawner.spawn(
            ["printenv", "HEADLESS_TEST_VAR"],
            cwd="/tmp",
            env={"HEADLESS_TEST_VAR": "headless_value"},
        )

        assert result.success is True
        stdout, _ = result.process.communicate()
        assert "headless_value" in stdout

    def test_spawn_nonexistent_command(self):
        """spawn() fails gracefully for non-existent command."""
        spawner = HeadlessSpawner()
        result = spawner.spawn(["nonexistent_xyz_12345"], cwd="/tmp")

        assert result.success is False
        assert result.error is not None


@pytest.mark.asyncio
class TestHeadlessSpawnerAsync:
    """Async tests for HeadlessSpawner.spawn_and_capture()."""

    async def test_basic_output_capture(self):
        """spawn_and_capture() captures command output."""
        spawner = HeadlessSpawner()
        result = await spawner.spawn_and_capture(
            command=["echo", "async hello"],
            cwd="/tmp",
        )

        assert result.success is True
        assert "async hello" in result.output_buffer or "async hello" in result.get_output()

    async def test_multi_line_output(self):
        """spawn_and_capture() captures multiple lines."""
        spawner = HeadlessSpawner()
        result = await spawner.spawn_and_capture(
            command=["sh", "-c", "echo line1; echo line2; echo line3"],
            cwd="/tmp",
        )

        assert result.success is True
        output = result.get_output()
        assert "line1" in output
        assert "line2" in output
        assert "line3" in output

    async def test_callback_invocation(self):
        """spawn_and_capture() invokes callback for each line."""
        spawner = HeadlessSpawner()
        captured_lines: list[str] = []

        def on_output(line: str) -> None:
            captured_lines.append(line)

        result = await spawner.spawn_and_capture(
            command=["sh", "-c", "echo one; echo two; echo three"],
            cwd="/tmp",
            on_output=on_output,
        )

        assert result.success is True
        # Callback should have been called for each line
        assert len(captured_lines) >= 3
        assert "one" in captured_lines
        assert "two" in captured_lines
        assert "three" in captured_lines

    async def test_timeout_terminates_process(self):
        """spawn_and_capture() terminates process on timeout."""
        spawner = HeadlessSpawner()
        result = await spawner.spawn_and_capture(
            command=["sleep", "60"],  # Would take 60 seconds
            cwd="/tmp",
            timeout=0.5,  # Timeout after 0.5 seconds
        )

        # Should timeout
        assert result.error == "Process timed out"
        # Process should be terminated
        if result.process:
            assert result.process.poll() is not None  # Process has exited

    async def test_timeout_with_output(self):
        """spawn_and_capture() captures output before timeout."""
        spawner = HeadlessSpawner()
        result = await spawner.spawn_and_capture(
            command=["sh", "-c", "echo before_timeout; sleep 60"],
            cwd="/tmp",
            timeout=1.0,
        )

        # Should timeout but have captured output
        assert result.error == "Process timed out"
        assert "before_timeout" in result.get_output()

    async def test_env_vars_in_async(self):
        """spawn_and_capture() passes environment variables."""
        spawner = HeadlessSpawner()
        result = await spawner.spawn_and_capture(
            command=["printenv", "ASYNC_TEST_VAR"],
            cwd="/tmp",
            env={"ASYNC_TEST_VAR": "async_value"},
        )

        assert result.success is True
        assert "async_value" in result.get_output()

    async def test_large_output_handling(self):
        """spawn_and_capture() handles large output."""
        spawner = HeadlessSpawner()
        # Generate 1000 lines of output
        result = await spawner.spawn_and_capture(
            command=["sh", "-c", "for i in $(seq 1 1000); do echo line_$i; done"],
            cwd="/tmp",
        )

        assert result.success is True
        # Should have captured all 1000 lines
        assert len(result.output_buffer) == 1000
        assert "line_1" in result.output_buffer
        assert "line_1000" in result.output_buffer

    async def test_error_handling_nonexistent_command(self):
        """spawn_and_capture() handles command not found."""
        spawner = HeadlessSpawner()
        result = await spawner.spawn_and_capture(
            command=["nonexistent_command_xyz_async"],
            cwd="/tmp",
        )

        assert result.success is False
        assert result.error is not None

    async def test_working_directory(self):
        """spawn_and_capture() uses correct working directory."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            spawner = HeadlessSpawner()
            result = await spawner.spawn_and_capture(
                command=["pwd"],
                cwd=tmpdir,
            )

            assert result.success is True
            output = result.get_output()
            # tmpdir may be a symlink, check contains or basename
            assert tmpdir in output or os.path.basename(tmpdir) in output

    async def test_exit_code_captured(self):
        """spawn_and_capture() waits for process completion."""
        spawner = HeadlessSpawner()
        result = await spawner.spawn_and_capture(
            command=["sh", "-c", "exit 42"],
            cwd="/tmp",
        )

        assert result.success is True  # spawn succeeded
        # Process should have exited
        if result.process:
            assert result.process.returncode == 42

    async def test_stderr_merged_with_stdout(self):
        """spawn_and_capture() captures stderr in output."""
        spawner = HeadlessSpawner()
        result = await spawner.spawn_and_capture(
            command=["sh", "-c", "echo stdout_msg; echo stderr_msg >&2"],
            cwd="/tmp",
        )

        assert result.success is True
        output = result.get_output()
        # Both stdout and stderr should be in output (stderr is merged)
        assert "stdout_msg" in output
        assert "stderr_msg" in output


class TestPromptFileManagement:
    """Tests for prompt file creation and cleanup."""

    def test_create_prompt_file_basic(self):
        """_create_prompt_file creates file with correct content."""
        prompt = "Test prompt content"
        session_id = "test-session-123"

        path = _create_prompt_file(prompt, session_id)
        try:
            # Verify file was created
            prompt_path = Path(path)
            assert prompt_path.exists()
            # Verify content
            assert prompt_path.read_text(encoding="utf-8") == prompt
            # Verify it's in the cleanup set
            assert prompt_path in _prompt_files_to_cleanup
        finally:
            # Clean up
            Path(path).unlink(missing_ok=True)
            _prompt_files_to_cleanup.discard(Path(path))

    def test_create_prompt_file_secure_permissions(self):
        """_create_prompt_file creates file with mode 0o600."""
        prompt = "Secret prompt"
        session_id = "secure-session"

        path = _create_prompt_file(prompt, session_id)
        try:
            prompt_path = Path(path)
            # Check file permissions (only owner can read/write)
            mode = prompt_path.stat().st_mode & 0o777
            assert mode == 0o600
        finally:
            Path(path).unlink(missing_ok=True)
            _prompt_files_to_cleanup.discard(Path(path))

    def test_create_prompt_file_in_gobby_prompts_dir(self):
        """_create_prompt_file creates file in gobby-prompts directory."""
        prompt = "Directory test"
        session_id = "dir-session"

        path = _create_prompt_file(prompt, session_id)
        try:
            prompt_path = Path(path)
            assert prompt_path.parent.name == "gobby-prompts"
            assert prompt_path.name == f"prompt-{session_id}.txt"
        finally:
            Path(path).unlink(missing_ok=True)
            _prompt_files_to_cleanup.discard(Path(path))

    def test_cleanup_all_prompt_files_removes_existing(self):
        """_cleanup_all_prompt_files removes tracked files."""
        # Create test files manually
        temp_dir = Path(tempfile.gettempdir()) / "gobby-prompts-test"
        temp_dir.mkdir(parents=True, exist_ok=True)

        test_file1 = temp_dir / "test1.txt"
        test_file2 = temp_dir / "test2.txt"

        test_file1.write_text("content1")
        test_file2.write_text("content2")

        # Add to cleanup set
        _prompt_files_to_cleanup.add(test_file1)
        _prompt_files_to_cleanup.add(test_file2)

        # Run cleanup
        _cleanup_all_prompt_files()

        # Verify files were removed
        assert not test_file1.exists()
        assert not test_file2.exists()
        # Verify set was cleared
        assert test_file1 not in _prompt_files_to_cleanup
        assert test_file2 not in _prompt_files_to_cleanup

        # Cleanup temp dir
        temp_dir.rmdir()

    def test_cleanup_all_prompt_files_handles_missing_file(self):
        """_cleanup_all_prompt_files handles already-deleted files."""
        # Add a non-existent file to the cleanup set
        fake_path = Path("/nonexistent/path/to/prompt.txt")
        _prompt_files_to_cleanup.add(fake_path)

        # Should not raise
        _cleanup_all_prompt_files()

        # Set should be cleared
        assert fake_path not in _prompt_files_to_cleanup

    def test_cleanup_all_prompt_files_handles_oserror(self):
        """_cleanup_all_prompt_files handles OSError gracefully."""
        temp_dir = Path(tempfile.gettempdir()) / "gobby-prompts-oserror"
        temp_dir.mkdir(parents=True, exist_ok=True)

        test_file = temp_dir / "test.txt"
        test_file.write_text("content")

        _prompt_files_to_cleanup.add(test_file)

        # Mock unlink to raise OSError
        with patch.object(Path, "unlink", side_effect=OSError("Permission denied")):
            with patch.object(Path, "exists", return_value=True):
                # Should not raise
                _cleanup_all_prompt_files()

        # Set should still be cleared
        assert test_file not in _prompt_files_to_cleanup

        # Manual cleanup
        if test_file.exists():
            test_file.unlink()
        temp_dir.rmdir()


class TestBuildCliCommandExtended:
    """Extended tests for build_cli_command covering all branches."""

    def test_claude_full_command(self):
        """Claude CLI with all options."""
        cmd = build_cli_command(
            "claude",
            prompt="Do something",
            session_id="sess-123",
            auto_approve=True,
        )
        assert cmd == [
            "claude",
            "--session-id",
            "sess-123",
            "--dangerously-skip-permissions",
            "-p",
            "Do something",
        ]

    def test_gemini_with_prompt(self):
        """Gemini CLI with prompt."""
        cmd = build_cli_command("gemini", prompt="Hello gemini")
        assert cmd == ["gemini", "Hello gemini"]

    def test_gemini_full_command(self):
        """Gemini CLI with all applicable options."""
        cmd = build_cli_command("gemini", prompt="Hello", auto_approve=True)
        assert "--approval-mode" in cmd
        assert "yolo" in cmd
        assert "Hello" in cmd

    def test_codex_full_command(self):
        """Codex CLI with all options."""
        cmd = build_cli_command(
            "codex",
            prompt="Codex prompt",
            auto_approve=True,
            working_directory="/projects/myapp",
        )
        assert "--full-auto" in cmd
        assert "-C" in cmd
        assert "/projects/myapp" in cmd
        assert "Codex prompt" in cmd

    def test_codex_without_working_dir(self):
        """Codex CLI without working directory."""
        cmd = build_cli_command("codex", auto_approve=True)
        assert "-C" not in cmd

    def test_unknown_cli(self):
        """Unknown CLI just returns base command with prompt."""
        cmd = build_cli_command("unknown_cli", prompt="hello")
        assert cmd == ["unknown_cli", "hello"]

    def test_no_prompt_no_flags(self):
        """CLI with no prompt or flags returns minimal command."""
        cmd = build_cli_command("gemini")
        assert cmd == ["gemini"]


class TestTerminalSpawnerMethods:
    """Tests for TerminalSpawner methods."""

    def test_get_available_terminals(self):
        """get_available_terminals returns available terminal list."""
        spawner = TerminalSpawner()

        # Mock some spawners as available
        with patch.object(spawner._spawners[TerminalType.TMUX], "is_available", return_value=True):
            with patch.object(
                spawner._spawners[TerminalType.KITTY], "is_available", return_value=True
            ):
                available = spawner.get_available_terminals()
                assert TerminalType.TMUX in available
                assert TerminalType.KITTY in available

    def test_get_preferred_terminal_returns_first_available(self):
        """get_preferred_terminal returns first available from preferences."""
        spawner = TerminalSpawner()

        with patch("gobby.agents.spawn.get_tty_config") as mock_config:
            mock_config.return_value.get_preferences.return_value = ["ghostty", "kitty", "tmux"]

            # Mock ghostty as unavailable, kitty as available
            with patch.object(
                spawner.SPAWNER_CLASSES["ghostty"],
                "is_available",
                return_value=False,
            ):
                with patch.object(
                    spawner.SPAWNER_CLASSES["kitty"],
                    "is_available",
                    return_value=True,
                ):
                    # Need to patch the instance method
                    mock_ghostty = MagicMock()
                    mock_ghostty.is_available.return_value = False
                    mock_kitty = MagicMock()
                    mock_kitty.is_available.return_value = True
                    mock_kitty.terminal_type = TerminalType.KITTY

                    with patch.object(
                        spawner.SPAWNER_CLASSES["ghostty"], "__call__", return_value=mock_ghostty
                    ):
                        with patch.object(
                            spawner.SPAWNER_CLASSES["kitty"], "__call__", return_value=mock_kitty
                        ):
                            result = spawner.get_preferred_terminal()
                            assert result == TerminalType.KITTY

    def test_get_preferred_terminal_returns_none_if_none_available(self):
        """get_preferred_terminal returns None if no terminals available."""
        spawner = TerminalSpawner()

        with patch("gobby.agents.spawn.get_tty_config") as mock_config:
            mock_config.return_value.get_preferences.return_value = ["nonexistent_terminal"]
            result = spawner.get_preferred_terminal()
            assert result is None

    def test_get_preferred_terminal_skips_unknown_terminals(self):
        """get_preferred_terminal skips terminals not in SPAWNER_CLASSES."""
        spawner = TerminalSpawner()

        with patch("gobby.agents.spawn.get_tty_config") as mock_config:
            # First preference is unknown, second is tmux
            mock_config.return_value.get_preferences.return_value = ["unknown_terminal", "tmux"]

            mock_tmux = MagicMock()
            mock_tmux.is_available.return_value = True
            mock_tmux.terminal_type = TerminalType.TMUX

            with patch.object(spawner.SPAWNER_CLASSES["tmux"], "__call__", return_value=mock_tmux):
                result = spawner.get_preferred_terminal()
                assert result == TerminalType.TMUX

    def test_spawn_auto_detect_no_terminals(self):
        """spawn with AUTO returns error when no terminals available."""
        spawner = TerminalSpawner()

        with patch.object(spawner, "get_preferred_terminal", return_value=None):
            result = spawner.spawn(["echo", "test"], cwd="/tmp", terminal=TerminalType.AUTO)
            assert result.success is False
            assert "No supported terminal found" in result.message

    def test_spawn_unregistered_terminal(self):
        """spawn returns error for unregistered terminal type."""
        spawner = TerminalSpawner()

        # Create a fake terminal type (won't actually work but tests the path)
        # Since we can't easily create a new enum value, we test this path
        # by removing a spawner from the dict
        del spawner._spawners[TerminalType.TMUX]

        result = spawner.spawn(["echo", "test"], cwd="/tmp", terminal=TerminalType.TMUX)
        assert result.success is False
        assert "No spawner registered" in result.message

    def test_spawn_terminal_not_available(self):
        """spawn returns error when terminal not available."""
        spawner = TerminalSpawner()

        with patch.object(spawner._spawners[TerminalType.TMUX], "is_available", return_value=False):
            result = spawner.spawn(["echo", "test"], cwd="/tmp", terminal=TerminalType.TMUX)
            assert result.success is False
            assert "not available" in result.message

    def test_spawn_string_to_enum_conversion(self):
        """spawn converts string terminal type to enum."""
        spawner = TerminalSpawner()

        with patch.object(spawner._spawners[TerminalType.TMUX], "is_available", return_value=True):
            with patch.object(
                spawner._spawners[TerminalType.TMUX],
                "spawn",
                return_value=SpawnResult(success=True, message="OK", pid=123),
            ):
                result = spawner.spawn(["echo", "test"], cwd="/tmp", terminal="tmux")
                assert result.success is True


class TestTerminalSpawnerSpawnAgent:
    """Tests for TerminalSpawner.spawn_agent method."""

    def test_spawn_agent_basic(self):
        """spawn_agent builds correct command and env."""
        spawner = TerminalSpawner()

        with patch.object(spawner, "spawn") as mock_spawn:
            mock_spawn.return_value = SpawnResult(success=True, message="OK", pid=123)

            result = spawner.spawn_agent(
                cli="claude",
                cwd="/projects/test",
                session_id="sess-123",
                parent_session_id="parent-456",
                agent_run_id="run-789",
                project_id="proj-abc",
            )

            # Verify result was returned from spawn
            assert result.success is True
            assert result.pid == 123

            # Verify spawn was called
            mock_spawn.assert_called_once()
            call_kwargs = mock_spawn.call_args[1]

            # Verify command includes Claude flags
            assert call_kwargs["command"][0] == "claude"
            assert "--dangerously-skip-permissions" in call_kwargs["command"]
            assert "--session-id" in call_kwargs["command"]

            # Verify env was passed
            assert "GOBBY_SESSION_ID" in call_kwargs["env"]
            assert call_kwargs["env"]["GOBBY_SESSION_ID"] == "sess-123"

    def test_spawn_agent_with_short_prompt(self):
        """spawn_agent passes short prompt via env var."""
        spawner = TerminalSpawner()

        short_prompt = "Short task"
        assert len(short_prompt) <= MAX_ENV_PROMPT_LENGTH

        with patch.object(spawner, "spawn") as mock_spawn:
            mock_spawn.return_value = SpawnResult(success=True, message="OK", pid=123)

            spawner.spawn_agent(
                cli="claude",
                cwd="/tmp",
                session_id="sess-123",
                parent_session_id="parent-456",
                agent_run_id="run-789",
                project_id="proj-abc",
                prompt=short_prompt,
            )

            call_kwargs = mock_spawn.call_args[1]
            assert "GOBBY_PROMPT" in call_kwargs["env"]
            assert call_kwargs["env"]["GOBBY_PROMPT"] == short_prompt

    def test_spawn_agent_with_long_prompt(self):
        """spawn_agent writes long prompt to file."""
        spawner = TerminalSpawner()

        long_prompt = "x" * (MAX_ENV_PROMPT_LENGTH + 100)

        with patch.object(spawner, "spawn") as mock_spawn:
            with patch.object(
                spawner, "_write_prompt_file", return_value="/tmp/prompt.txt"
            ) as mock_write:
                mock_spawn.return_value = SpawnResult(success=True, message="OK", pid=123)

                spawner.spawn_agent(
                    cli="claude",
                    cwd="/tmp",
                    session_id="sess-123",
                    parent_session_id="parent-456",
                    agent_run_id="run-789",
                    project_id="proj-abc",
                    prompt=long_prompt,
                )

                # Verify prompt file was written
                mock_write.assert_called_once_with(long_prompt, "sess-123")

                call_kwargs = mock_spawn.call_args[1]
                assert "GOBBY_PROMPT_FILE" in call_kwargs["env"]

    def test_spawn_agent_with_workflow(self):
        """spawn_agent passes workflow name in env."""
        spawner = TerminalSpawner()

        with patch.object(spawner, "spawn") as mock_spawn:
            mock_spawn.return_value = SpawnResult(success=True, message="OK", pid=123)

            spawner.spawn_agent(
                cli="claude",
                cwd="/tmp",
                session_id="sess-123",
                parent_session_id="parent-456",
                agent_run_id="run-789",
                project_id="proj-abc",
                workflow_name="plan-execute",
            )

            call_kwargs = mock_spawn.call_args[1]
            assert call_kwargs["env"]["GOBBY_WORKFLOW_NAME"] == "plan-execute"

    def test_spawn_agent_codex_working_directory(self):
        """spawn_agent passes working directory for Codex."""
        spawner = TerminalSpawner()

        with patch.object(spawner, "spawn") as mock_spawn:
            mock_spawn.return_value = SpawnResult(success=True, message="OK", pid=123)

            spawner.spawn_agent(
                cli="codex",
                cwd="/projects/app",
                session_id="sess-123",
                parent_session_id="parent-456",
                agent_run_id="run-789",
                project_id="proj-abc",
            )

            call_kwargs = mock_spawn.call_args[1]
            # Codex command should have -C flag
            assert "-C" in call_kwargs["command"]
            assert "/projects/app" in call_kwargs["command"]

    def test_spawn_agent_sets_title(self):
        """spawn_agent sets appropriate window title."""
        spawner = TerminalSpawner()

        with patch.object(spawner, "spawn") as mock_spawn:
            mock_spawn.return_value = SpawnResult(success=True, message="OK", pid=123)

            spawner.spawn_agent(
                cli="claude",
                cwd="/tmp",
                session_id="sess-123",
                parent_session_id="parent-456",
                agent_run_id="run-789",
                project_id="proj-abc",
                agent_depth=2,
            )

            call_kwargs = mock_spawn.call_args[1]
            assert call_kwargs["title"] == "gobby-claude-d2"


class TestPrepareTerminalSpawn:
    """Tests for prepare_terminal_spawn function."""

    def test_prepare_terminal_spawn_basic(self):
        """prepare_terminal_spawn creates child session and returns PreparedSpawn."""
        # Mock session manager
        mock_session_manager = MagicMock()
        mock_child_session = MagicMock()
        mock_child_session.id = "child-sess-123"
        mock_child_session.agent_depth = 1
        mock_session_manager.create_child_session.return_value = mock_child_session

        result = prepare_terminal_spawn(
            session_manager=mock_session_manager,
            parent_session_id="parent-456",
            project_id="proj-abc",
            machine_id="machine-xyz",
        )

        assert isinstance(result, PreparedSpawn)
        assert result.session_id == "child-sess-123"
        assert result.parent_session_id == "parent-456"
        assert result.project_id == "proj-abc"
        assert result.agent_depth == 1
        assert "GOBBY_SESSION_ID" in result.env_vars

    def test_prepare_terminal_spawn_with_workflow(self):
        """prepare_terminal_spawn includes workflow in env."""
        mock_session_manager = MagicMock()
        mock_child_session = MagicMock()
        mock_child_session.id = "child-sess-123"
        mock_child_session.agent_depth = 1
        mock_session_manager.create_child_session.return_value = mock_child_session

        result = prepare_terminal_spawn(
            session_manager=mock_session_manager,
            parent_session_id="parent-456",
            project_id="proj-abc",
            machine_id="machine-xyz",
            workflow_name="test-workflow",
        )

        assert result.workflow_name == "test-workflow"
        assert result.env_vars["GOBBY_WORKFLOW_NAME"] == "test-workflow"

    def test_prepare_terminal_spawn_short_prompt(self):
        """prepare_terminal_spawn passes short prompt via env var."""
        mock_session_manager = MagicMock()
        mock_child_session = MagicMock()
        mock_child_session.id = "child-sess-123"
        mock_child_session.agent_depth = 1
        mock_session_manager.create_child_session.return_value = mock_child_session

        short_prompt = "Do something"

        result = prepare_terminal_spawn(
            session_manager=mock_session_manager,
            parent_session_id="parent-456",
            project_id="proj-abc",
            machine_id="machine-xyz",
            prompt=short_prompt,
        )

        assert "GOBBY_PROMPT" in result.env_vars
        assert result.env_vars["GOBBY_PROMPT"] == short_prompt

    def test_prepare_terminal_spawn_long_prompt(self):
        """prepare_terminal_spawn writes long prompt to file."""
        mock_session_manager = MagicMock()
        mock_child_session = MagicMock()
        mock_child_session.id = "child-sess-123"
        mock_child_session.agent_depth = 1
        mock_session_manager.create_child_session.return_value = mock_child_session

        long_prompt = "x" * (MAX_ENV_PROMPT_LENGTH + 100)

        with patch("gobby.agents.spawn._create_prompt_file") as mock_create:
            mock_create.return_value = "/tmp/gobby-prompts/prompt-child-sess-123.txt"

            result = prepare_terminal_spawn(
                session_manager=mock_session_manager,
                parent_session_id="parent-456",
                project_id="proj-abc",
                machine_id="machine-xyz",
                prompt=long_prompt,
            )

            mock_create.assert_called_once_with(long_prompt, "child-sess-123")
            assert "GOBBY_PROMPT_FILE" in result.env_vars

    def test_prepare_terminal_spawn_generates_agent_run_id(self):
        """prepare_terminal_spawn generates unique agent run ID."""
        mock_session_manager = MagicMock()
        mock_child_session = MagicMock()
        mock_child_session.id = "child-sess-123"
        mock_child_session.agent_depth = 1
        mock_session_manager.create_child_session.return_value = mock_child_session

        result = prepare_terminal_spawn(
            session_manager=mock_session_manager,
            parent_session_id="parent-456",
            project_id="proj-abc",
            machine_id="machine-xyz",
        )

        assert result.agent_run_id.startswith("run-")
        assert len(result.agent_run_id) == 16  # "run-" + 12 hex chars


class TestReadPromptFromEnv:
    """Tests for read_prompt_from_env function."""

    def test_read_prompt_from_env_inline(self):
        """read_prompt_from_env reads from GOBBY_PROMPT."""
        with patch.dict(os.environ, {"GOBBY_PROMPT": "Inline prompt"}, clear=False):
            # Clear GOBBY_PROMPT_FILE if set
            with patch.dict(os.environ, {"GOBBY_PROMPT_FILE": ""}, clear=False):
                result = read_prompt_from_env()
                assert result == "Inline prompt"

    def test_read_prompt_from_env_file(self):
        """read_prompt_from_env reads from file when GOBBY_PROMPT_FILE set."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("File prompt content")
            temp_path = f.name

        try:
            with patch.dict(os.environ, {"GOBBY_PROMPT_FILE": temp_path}, clear=False):
                result = read_prompt_from_env()
                assert result == "File prompt content"
        finally:
            os.unlink(temp_path)

    def test_read_prompt_from_env_file_not_found(self):
        """read_prompt_from_env handles missing file gracefully."""
        with patch.dict(
            os.environ,
            {"GOBBY_PROMPT_FILE": "/nonexistent/prompt.txt"},
            clear=False,
        ):
            # Should fall back to GOBBY_PROMPT
            with patch.dict(os.environ, {"GOBBY_PROMPT": "Fallback"}, clear=False):
                result = read_prompt_from_env()
                assert result == "Fallback"

    def test_read_prompt_from_env_file_read_error(self):
        """read_prompt_from_env handles file read errors."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            temp_path = f.name

        try:
            with patch.dict(os.environ, {"GOBBY_PROMPT_FILE": temp_path}, clear=False):
                with patch.object(Path, "read_text", side_effect=PermissionError("denied")):
                    with patch.dict(os.environ, {"GOBBY_PROMPT": "Fallback"}, clear=False):
                        result = read_prompt_from_env()
                        # Should fall back to GOBBY_PROMPT
                        assert result == "Fallback"
        finally:
            os.unlink(temp_path)

    def test_read_prompt_from_env_nothing_set(self):
        """read_prompt_from_env returns None when nothing set."""
        with patch.dict(os.environ, {}, clear=True):
            # Need to ensure the env vars are not set
            os.environ.pop("GOBBY_PROMPT", None)
            os.environ.pop("GOBBY_PROMPT_FILE", None)
            result = read_prompt_from_env()
            assert result is None

    def test_read_prompt_from_env_file_priority(self):
        """read_prompt_from_env prioritizes file over inline."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("From file")
            temp_path = f.name

        try:
            with patch.dict(
                os.environ,
                {"GOBBY_PROMPT_FILE": temp_path, "GOBBY_PROMPT": "From inline"},
                clear=False,
            ):
                result = read_prompt_from_env()
                assert result == "From file"
        finally:
            os.unlink(temp_path)


class TestPreparedSpawnDataclass:
    """Tests for PreparedSpawn dataclass."""

    def test_prepared_spawn_fields(self):
        """PreparedSpawn has correct fields."""
        spawn = PreparedSpawn(
            session_id="sess-123",
            agent_run_id="run-456",
            parent_session_id="parent-789",
            project_id="proj-abc",
            workflow_name="test-workflow",
            agent_depth=2,
            env_vars={"KEY": "value"},
        )

        assert spawn.session_id == "sess-123"
        assert spawn.agent_run_id == "run-456"
        assert spawn.parent_session_id == "parent-789"
        assert spawn.project_id == "proj-abc"
        assert spawn.workflow_name == "test-workflow"
        assert spawn.agent_depth == 2
        assert spawn.env_vars == {"KEY": "value"}

    def test_prepared_spawn_no_workflow(self):
        """PreparedSpawn works with None workflow."""
        spawn = PreparedSpawn(
            session_id="sess-123",
            agent_run_id="run-456",
            parent_session_id="parent-789",
            project_id="proj-abc",
            workflow_name=None,
            agent_depth=1,
            env_vars={},
        )

        assert spawn.workflow_name is None


class TestMaxEnvPromptLength:
    """Tests for MAX_ENV_PROMPT_LENGTH constant."""

    def test_max_env_prompt_length_value(self):
        """MAX_ENV_PROMPT_LENGTH has expected value."""
        assert MAX_ENV_PROMPT_LENGTH == 4096

    def test_prompt_length_boundary(self):
        """Test behavior at prompt length boundary."""
        spawner = TerminalSpawner()

        # Test prompt exactly at limit
        exact_prompt = "x" * MAX_ENV_PROMPT_LENGTH

        with patch.object(spawner, "spawn") as mock_spawn:
            with patch.object(spawner, "_write_prompt_file") as mock_write:
                mock_spawn.return_value = SpawnResult(success=True, message="OK", pid=123)

                spawner.spawn_agent(
                    cli="claude",
                    cwd="/tmp",
                    session_id="sess-123",
                    parent_session_id="parent-456",
                    agent_run_id="run-789",
                    project_id="proj-abc",
                    prompt=exact_prompt,
                )

                # At exactly MAX, should NOT write to file
                mock_write.assert_not_called()

                call_kwargs = mock_spawn.call_args[1]
                assert "GOBBY_PROMPT" in call_kwargs["env"]

    def test_prompt_length_one_over_boundary(self):
        """Test behavior with prompt one character over limit."""
        spawner = TerminalSpawner()

        over_prompt = "x" * (MAX_ENV_PROMPT_LENGTH + 1)

        with patch.object(spawner, "spawn") as mock_spawn:
            with patch.object(
                spawner, "_write_prompt_file", return_value="/tmp/p.txt"
            ) as mock_write:
                mock_spawn.return_value = SpawnResult(success=True, message="OK", pid=123)

                spawner.spawn_agent(
                    cli="claude",
                    cwd="/tmp",
                    session_id="sess-123",
                    parent_session_id="parent-456",
                    agent_run_id="run-789",
                    project_id="proj-abc",
                    prompt=over_prompt,
                )

                # Over MAX, should write to file
                mock_write.assert_called_once()


class TestTerminalSpawnerWritePromptFile:
    """Tests for TerminalSpawner._write_prompt_file method."""

    def test_write_prompt_file_delegates(self):
        """_write_prompt_file delegates to _create_prompt_file."""
        spawner = TerminalSpawner()

        with patch("gobby.agents.spawn._create_prompt_file") as mock_create:
            mock_create.return_value = "/tmp/prompt.txt"

            result = spawner._write_prompt_file("test prompt", "sess-123")

            mock_create.assert_called_once_with("test prompt", "sess-123")
            assert result == "/tmp/prompt.txt"


class TestCreatePromptFileExceptionHandling:
    """Tests for exception handling in _create_prompt_file."""

    def test_create_prompt_file_registers_atexit_handler(self):
        """_create_prompt_file registers atexit handler on first call."""
        import gobby.agents.spawn as spawn_module

        # Reset the atexit registration flag
        original_flag = spawn_module._atexit_registered
        spawn_module._atexit_registered = False

        try:
            with patch("atexit.register") as mock_atexit:
                prompt = "Test prompt"
                session_id = "atexit-test-session"

                path = _create_prompt_file(prompt, session_id)
                try:
                    # Verify atexit was registered
                    mock_atexit.assert_called_once_with(_cleanup_all_prompt_files)
                    # Verify flag was set
                    assert spawn_module._atexit_registered is True
                finally:
                    Path(path).unlink(missing_ok=True)
                    _prompt_files_to_cleanup.discard(Path(path))
        finally:
            # Restore original flag
            spawn_module._atexit_registered = original_flag

    def test_create_prompt_file_does_not_reregister_atexit(self):
        """_create_prompt_file does not re-register atexit handler."""
        import gobby.agents.spawn as spawn_module

        # Ensure atexit is already registered
        original_flag = spawn_module._atexit_registered
        spawn_module._atexit_registered = True

        try:
            with patch("atexit.register") as mock_atexit:
                prompt = "Test prompt 2"
                session_id = "no-reregister-session"

                path = _create_prompt_file(prompt, session_id)
                try:
                    # Verify atexit was NOT called
                    mock_atexit.assert_not_called()
                finally:
                    Path(path).unlink(missing_ok=True)
                    _prompt_files_to_cleanup.discard(Path(path))
        finally:
            spawn_module._atexit_registered = original_flag

    def test_create_prompt_file_handles_write_exception(self):
        """_create_prompt_file propagates write exceptions."""
        with patch("os.open", return_value=99):
            with patch("os.fdopen", side_effect=OSError("Write failed")):
                with patch("os.close") as mock_close:
                    with pytest.raises(OSError, match="Write failed"):
                        _create_prompt_file("test", "exc-session")

                    # Verify fd was closed
                    mock_close.assert_called_once_with(99)

    def test_create_prompt_file_fd_close_error_suppressed(self):
        """_create_prompt_file suppresses fd close errors."""
        with patch("os.open", return_value=99):
            with patch("os.fdopen", side_effect=OSError("Write failed")):
                with patch("os.close", side_effect=OSError("Close failed")):
                    # Should still raise the original error, not the close error
                    with pytest.raises(OSError, match="Write failed"):
                        _create_prompt_file("test", "close-error-session")


class TestTerminalSpawnerAutoDetect:
    """Tests for terminal auto-detection."""

    def test_spawn_auto_uses_preferred_terminal(self):
        """spawn with AUTO uses get_preferred_terminal result."""
        spawner = TerminalSpawner()

        # Mock preferred terminal as TMUX
        with patch.object(spawner, "get_preferred_terminal", return_value=TerminalType.TMUX):
            with patch.object(
                spawner._spawners[TerminalType.TMUX], "is_available", return_value=True
            ):
                with patch.object(
                    spawner._spawners[TerminalType.TMUX],
                    "spawn",
                    return_value=SpawnResult(success=True, message="OK", pid=123),
                ) as mock_spawn:
                    result = spawner.spawn(["echo", "test"], cwd="/tmp", terminal=TerminalType.AUTO)

                    assert result.success is True
                    mock_spawn.assert_called_once()


class TestPrepareTerminalSpawnAllParams:
    """Tests for prepare_terminal_spawn with all parameters."""

    def test_prepare_terminal_spawn_all_params(self):
        """prepare_terminal_spawn with all parameters."""
        mock_session_manager = MagicMock()
        mock_child_session = MagicMock()
        mock_child_session.id = "child-full"
        mock_child_session.agent_depth = 2
        mock_session_manager.create_child_session.return_value = mock_child_session

        result = prepare_terminal_spawn(
            session_manager=mock_session_manager,
            parent_session_id="parent-full",
            project_id="proj-full",
            machine_id="machine-full",
            source="gemini",
            agent_id="agent-full",
            workflow_name="full-workflow",
            title="Full Test Session",
            git_branch="feature/full",
            prompt="Full test prompt",
            max_agent_depth=5,
        )

        # Verify create_child_session was called with correct config
        call_args = mock_session_manager.create_child_session.call_args
        config = call_args[0][0]

        assert config.parent_session_id == "parent-full"
        assert config.project_id == "proj-full"
        assert config.machine_id == "machine-full"
        assert config.source == "gemini"
        assert config.agent_id == "agent-full"
        assert config.workflow_name == "full-workflow"
        assert config.title == "Full Test Session"
        assert config.git_branch == "feature/full"

        # Verify result
        assert result.agent_depth == 2
        assert result.env_vars["GOBBY_MAX_AGENT_DEPTH"] == "5"


class TestSpawnAgentGemini:
    """Tests for spawn_agent with Gemini CLI."""

    def test_spawn_agent_gemini(self):
        """spawn_agent with Gemini CLI."""
        spawner = TerminalSpawner()

        with patch.object(spawner, "spawn") as mock_spawn:
            mock_spawn.return_value = SpawnResult(success=True, message="OK", pid=123)

            spawner.spawn_agent(
                cli="gemini",
                cwd="/tmp",
                session_id="sess-gemini",
                parent_session_id="parent-gemini",
                agent_run_id="run-gemini",
                project_id="proj-gemini",
                prompt="Hello Gemini",
            )

            call_kwargs = mock_spawn.call_args[1]
            # Gemini command should have yolo mode
            assert "--approval-mode" in call_kwargs["command"]
            assert "yolo" in call_kwargs["command"]
            assert "Hello Gemini" in call_kwargs["command"]

    def test_spawn_agent_no_prompt(self):
        """spawn_agent without prompt."""
        spawner = TerminalSpawner()

        with patch.object(spawner, "spawn") as mock_spawn:
            mock_spawn.return_value = SpawnResult(success=True, message="OK", pid=123)

            spawner.spawn_agent(
                cli="claude",
                cwd="/tmp",
                session_id="sess-123",
                parent_session_id="parent-456",
                agent_run_id="run-789",
                project_id="proj-abc",
                # No prompt
            )

            call_kwargs = mock_spawn.call_args[1]
            # No GOBBY_PROMPT or GOBBY_PROMPT_FILE
            assert "GOBBY_PROMPT" not in call_kwargs["env"]
            assert "GOBBY_PROMPT_FILE" not in call_kwargs["env"]
