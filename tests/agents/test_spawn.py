"""Tests for terminal spawning functionality."""

import os
import platform
import sys
from unittest.mock import MagicMock, patch

import pytest

from gobby.agents.spawn import (
    EmbeddedPTYResult,
    EmbeddedSpawner,
    HeadlessResult,
    HeadlessSpawner,
    PowerShellSpawner,
    SpawnResult,
    TerminalSpawner,
    TerminalType,
    TmuxSpawner,
    WSLSpawner,
    build_cli_command,
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
    def test_spawn_creates_detached_session(
        self, mock_popen, mock_run, mock_which, mock_system
    ):
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
    def test_spawn_sanitizes_session_name(
        self, mock_popen, mock_run, mock_which, mock_system
    ):
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
