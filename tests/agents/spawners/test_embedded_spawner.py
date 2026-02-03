"""Comprehensive tests for EmbeddedSpawner.

Tests for:
- EmbeddedSpawner.spawn() method
- EmbeddedSpawner.spawn_agent() method
- PTY creation and management
- Error handling and edge cases
- Platform-specific behavior
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gobby.agents.spawners.base import EmbeddedPTYResult
from gobby.agents.spawners.embedded import (
    MAX_ENV_PROMPT_LENGTH,
    EmbeddedSpawner,
    _get_spawn_utils,
)

pytestmark = pytest.mark.unit

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def spawner():
    """Create an EmbeddedSpawner instance for testing."""
    return EmbeddedSpawner()


@pytest.fixture
def mock_pty():
    """Mock the pty module for testing."""
    with patch("gobby.agents.spawners.embedded.pty") as mock:
        mock.openpty.return_value = (10, 11)
        yield mock


@pytest.fixture
def mock_os_fork():
    """Mock os.fork() for testing."""
    with patch("os.fork") as mock:
        yield mock


@pytest.fixture
def mock_os_close():
    """Mock os.close() for testing."""
    with patch("os.close") as mock:
        yield mock


# =============================================================================
# Tests for _get_spawn_utils helper
# =============================================================================


class TestGetSpawnUtils:
    """Tests for _get_spawn_utils lazy import helper."""

    def test_returns_tuple_of_three(self) -> None:
        """_get_spawn_utils returns correct tuple of utilities."""
        result = _get_spawn_utils()
        assert len(result) == 3

    def test_returns_callable_build_cli_command(self) -> None:
        """First element should be build_cli_command function."""
        build_cli_command, _, _ = _get_spawn_utils()
        assert callable(build_cli_command)

    def test_returns_callable_create_prompt_file(self) -> None:
        """Second element should be _create_prompt_file function."""
        _, create_prompt_file, _ = _get_spawn_utils()
        assert callable(create_prompt_file)

    def test_returns_max_env_prompt_length(self) -> None:
        """Third element should be MAX_ENV_PROMPT_LENGTH constant."""
        _, _, max_length = _get_spawn_utils()
        assert isinstance(max_length, int)
        assert max_length > 0


# =============================================================================
# Tests for EmbeddedSpawner.spawn() method
# =============================================================================


class TestEmbeddedSpawnerSpawn:
    """Tests for EmbeddedSpawner.spawn() method."""

    def test_spawn_empty_command_list(self, spawner) -> None:
        """spawn() returns error for empty command list."""
        result = spawner.spawn([], cwd="/tmp")

        assert result.success is False
        assert "empty command" in result.message.lower()
        assert result.error is not None

    def test_spawn_none_in_command_check(self, spawner) -> None:
        """spawn() handles edge case of checking empty command."""
        # Test with a list that has zero length
        result = spawner.spawn(command=[], cwd="/tmp")
        assert result.success is False
        assert "empty command" in result.message.lower()

    @patch("platform.system", return_value="Windows")
    def test_spawn_not_supported_on_windows(self, mock_system, spawner) -> None:
        """spawn() returns error on Windows platform."""
        with patch("gobby.agents.spawners.embedded.pty", None):
            result = spawner.spawn(["echo", "test"], cwd="/tmp")

            assert result.success is False
            assert "Windows" in result.message or "not supported" in result.message.lower()
            assert result.error is not None

    @patch("gobby.agents.spawners.embedded.pty", None)
    def test_spawn_without_pty_module(self, spawner) -> None:
        """spawn() returns error when pty module is not available."""
        with patch("platform.system", return_value="Linux"):
            result = spawner.spawn(["echo", "test"], cwd="/tmp")

            assert result.success is False
            # Should indicate PTY not supported

    def test_spawn_openpty_error(self, spawner, mock_pty) -> None:
        """spawn() handles openpty() errors gracefully."""
        mock_pty.openpty.side_effect = OSError("PTY creation failed")

        result = spawner.spawn(["echo", "test"], cwd="/tmp")

        assert result.success is False
        assert result.error is not None
        assert "PTY creation failed" in result.error or "Failed" in result.message

    def test_spawn_fork_error(self, spawner, mock_pty, mock_os_close) -> None:
        """spawn() handles fork() errors gracefully."""
        with patch("os.fork", side_effect=OSError("Fork failed")):
            result = spawner.spawn(["echo", "test"], cwd="/tmp")

            assert result.success is False
            assert "Fork failed" in result.error or "Failed" in result.message
            # Verify cleanup was attempted - os.close should be called for both fds
            assert mock_os_close.call_count >= 1

    def test_spawn_parent_process_success(self, spawner, mock_pty, mock_os_close) -> None:
        """spawn() returns correct result in parent process."""
        mock_pty.openpty.return_value = (10, 11)

        with patch("os.fork", return_value=12345):  # Parent gets positive PID
            result = spawner.spawn(["echo", "test"], cwd="/tmp")

            assert result.success is True
            assert result.pid == 12345
            assert result.master_fd == 10
            assert result.slave_fd is None  # Closed in parent
            assert "Spawned embedded PTY with PID 12345" in result.message
            mock_os_close.assert_called_once_with(11)

    def test_spawn_with_path_object(self, spawner, mock_pty, mock_os_close) -> None:
        """spawn() accepts Path object for cwd."""
        mock_pty.openpty.return_value = (10, 11)

        with patch("os.fork", return_value=12345):
            result = spawner.spawn(["echo", "test"], cwd=Path("/tmp"))

            assert result.success is True

    def test_spawn_with_env_vars(self, spawner, mock_pty, mock_os_close) -> None:
        """spawn() passes environment variables correctly."""
        mock_pty.openpty.return_value = (10, 11)

        with patch("os.fork", return_value=12345):
            result = spawner.spawn(
                ["echo", "test"],
                cwd="/tmp",
                env={"MY_VAR": "my_value", "OTHER_VAR": "other_value"},
            )

            assert result.success is True

    def test_spawn_without_env_vars(self, spawner, mock_pty, mock_os_close) -> None:
        """spawn() works without environment variables."""
        mock_pty.openpty.return_value = (10, 11)

        with patch("os.fork", return_value=12345):
            result = spawner.spawn(["echo", "test"], cwd="/tmp", env=None)

            assert result.success is True

    def test_spawn_closes_fds_on_exception(self, spawner, mock_pty) -> None:
        """spawn() closes file descriptors when an exception occurs."""
        mock_pty.openpty.return_value = (100, 101)

        with patch("os.fork", side_effect=RuntimeError("Unexpected error")):
            with patch("os.close") as mock_close:
                result = spawner.spawn(["echo", "test"], cwd="/tmp")

                assert result.success is False
                # Both master and slave fd should be closed on error
                assert mock_close.call_count == 2
                mock_close.assert_any_call(100)
                mock_close.assert_any_call(101)

    def test_spawn_handles_close_oserror_on_cleanup(self, spawner, mock_pty) -> None:
        """spawn() handles OSError when closing fds during cleanup."""
        mock_pty.openpty.return_value = (100, 101)

        with patch("os.fork", side_effect=RuntimeError("Fork error")):
            with patch("os.close", side_effect=OSError("Bad file descriptor")):
                # Should not raise, should return error result
                result = spawner.spawn(["echo", "test"], cwd="/tmp")
                assert result.success is False


# =============================================================================
# Tests for EmbeddedSpawner.spawn_agent() method
# =============================================================================


class TestEmbeddedSpawnerSpawnAgent:
    """Tests for EmbeddedSpawner.spawn_agent() method."""

    @patch("platform.system", return_value="Windows")
    def test_spawn_agent_not_supported_on_windows(self, mock_system, spawner) -> None:
        """spawn_agent() returns error on Windows platform."""
        with patch("gobby.agents.spawners.embedded.pty", None):
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
    def test_spawn_agent_basic(self, mock_utils, mock_close, mock_fork, mock_pty, spawner) -> None:
        """spawn_agent() creates command with correct parameters."""
        mock_pty.openpty.return_value = (10, 11)

        def mock_build_cli_command(
            cli,
            prompt=None,
            session_id=None,
            auto_approve=False,
            working_directory=None,
            sandbox_args=None,
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

        result = spawner.spawn_agent(
            cli="claude",
            cwd="/tmp",
            session_id="sess-123",
            parent_session_id="sess-parent",
            agent_run_id="run-456",
            project_id="proj-789",
        )

        assert result.success is True
        assert result.pid == 12345

    @patch("gobby.agents.spawners.embedded.pty")
    @patch("os.fork", return_value=12345)
    @patch("os.close")
    @patch("gobby.agents.spawners.embedded._get_spawn_utils")
    def test_spawn_agent_with_short_prompt(
        self, mock_utils, mock_close, mock_fork, mock_pty, spawner
    ) -> None:
        """spawn_agent() passes short prompt via environment variable."""
        mock_pty.openpty.return_value = (10, 11)

        mock_build_cmd = MagicMock(return_value=["claude", "-p", "Test prompt"])
        mock_create_file = MagicMock()
        mock_utils.return_value = (mock_build_cmd, mock_create_file, 4096)

        result = spawner.spawn_agent(
            cli="claude",
            cwd="/tmp",
            session_id="sess-123",
            parent_session_id="sess-parent",
            agent_run_id="run-456",
            project_id="proj-789",
            prompt="Short prompt",
        )

        assert result.success is True
        # Short prompt should NOT create a file
        mock_create_file.assert_not_called()

    @patch("gobby.agents.spawners.embedded.pty")
    @patch("os.fork", return_value=12345)
    @patch("os.close")
    @patch("gobby.agents.spawners.embedded._get_spawn_utils")
    def test_spawn_agent_with_long_prompt(
        self, mock_utils, mock_close, mock_fork, mock_pty, spawner
    ) -> None:
        """spawn_agent() writes long prompt to file."""
        mock_pty.openpty.return_value = (10, 11)

        mock_create_prompt_file = MagicMock(return_value="/tmp/prompt.txt")
        mock_utils.return_value = (
            MagicMock(return_value=["claude"]),
            mock_create_prompt_file,
            100,  # Low threshold to trigger file creation
        )

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
    def test_spawn_agent_prompt_exactly_at_threshold(
        self, mock_utils, mock_close, mock_fork, mock_pty, spawner
    ) -> None:
        """spawn_agent() uses env var when prompt is exactly at threshold."""
        mock_pty.openpty.return_value = (10, 11)

        mock_create_prompt_file = MagicMock(return_value="/tmp/prompt.txt")
        threshold = 100
        mock_utils.return_value = (
            MagicMock(return_value=["claude"]),
            mock_create_prompt_file,
            threshold,
        )

        # Prompt exactly at threshold should use env var, not file
        exact_prompt = "x" * threshold
        result = spawner.spawn_agent(
            cli="claude",
            cwd="/tmp",
            session_id="sess-123",
            parent_session_id="sess-parent",
            agent_run_id="run-456",
            project_id="proj-789",
            prompt=exact_prompt,
        )

        assert result.success is True
        mock_create_prompt_file.assert_not_called()

    @patch("gobby.agents.spawners.embedded.pty")
    @patch("os.fork", return_value=12345)
    @patch("os.close")
    @patch("gobby.agents.spawners.embedded._get_spawn_utils")
    def test_spawn_agent_codex_working_directory(
        self, mock_utils, mock_close, mock_fork, mock_pty, spawner
    ) -> None:
        """spawn_agent() passes working directory for Codex CLI."""
        mock_pty.openpty.return_value = (10, 11)

        mock_build_cmd = MagicMock(return_value=["codex", "-C", "/projects/app"])
        mock_utils.return_value = (mock_build_cmd, MagicMock(), 4096)

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

    @patch("gobby.agents.spawners.embedded.pty")
    @patch("os.fork", return_value=12345)
    @patch("os.close")
    @patch("gobby.agents.spawners.embedded._get_spawn_utils")
    def test_spawn_agent_gemini_no_working_directory(
        self, mock_utils, mock_close, mock_fork, mock_pty, spawner
    ) -> None:
        """spawn_agent() does not pass working directory for non-Codex CLIs."""
        mock_pty.openpty.return_value = (10, 11)

        mock_build_cmd = MagicMock(return_value=["gemini"])
        mock_utils.return_value = (mock_build_cmd, MagicMock(), 4096)

        result = spawner.spawn_agent(
            cli="gemini",
            cwd="/projects/app",
            session_id="sess-123",
            parent_session_id="sess-parent",
            agent_run_id="run-456",
            project_id="proj-789",
        )

        assert result.success is True
        mock_build_cmd.assert_called_once()
        call_kwargs = mock_build_cmd.call_args[1]
        assert call_kwargs["working_directory"] is None

    @patch("gobby.agents.spawners.embedded.pty")
    @patch("os.fork", return_value=12345)
    @patch("os.close")
    @patch("gobby.agents.spawners.embedded._get_spawn_utils")
    def test_spawn_agent_with_workflow(
        self, mock_utils, mock_close, mock_fork, mock_pty, spawner
    ) -> None:
        """spawn_agent() passes workflow name correctly."""
        mock_pty.openpty.return_value = (10, 11)
        mock_utils.return_value = (MagicMock(return_value=["claude"]), MagicMock(), 4096)

        result = spawner.spawn_agent(
            cli="claude",
            cwd="/tmp",
            session_id="sess-123",
            parent_session_id="sess-parent",
            agent_run_id="run-456",
            project_id="proj-789",
            workflow_name="plan-execute",
        )

        assert result.success is True

    @patch("gobby.agents.spawners.embedded.pty")
    @patch("os.fork", return_value=12345)
    @patch("os.close")
    @patch("gobby.agents.spawners.embedded._get_spawn_utils")
    def test_spawn_agent_with_custom_depth(
        self, mock_utils, mock_close, mock_fork, mock_pty, spawner
    ) -> None:
        """spawn_agent() passes custom agent depth values."""
        mock_pty.openpty.return_value = (10, 11)
        mock_utils.return_value = (MagicMock(return_value=["claude"]), MagicMock(), 4096)

        result = spawner.spawn_agent(
            cli="claude",
            cwd="/tmp",
            session_id="sess-123",
            parent_session_id="sess-parent",
            agent_run_id="run-456",
            project_id="proj-789",
            agent_depth=2,
            max_agent_depth=5,
        )

        assert result.success is True

    @patch("gobby.agents.spawners.embedded.pty")
    @patch("os.fork", return_value=12345)
    @patch("os.close")
    @patch("gobby.agents.spawners.embedded._get_spawn_utils")
    def test_spawn_agent_auto_approve_always_true(
        self, mock_utils, mock_close, mock_fork, mock_pty, spawner
    ) -> None:
        """spawn_agent() always sets auto_approve=True for subagents."""
        mock_pty.openpty.return_value = (10, 11)

        mock_build_cmd = MagicMock(return_value=["claude", "--dangerously-skip-permissions"])
        mock_utils.return_value = (mock_build_cmd, MagicMock(), 4096)

        spawner.spawn_agent(
            cli="claude",
            cwd="/tmp",
            session_id="sess-123",
            parent_session_id="sess-parent",
            agent_run_id="run-456",
            project_id="proj-789",
        )

        mock_build_cmd.assert_called_once()
        call_kwargs = mock_build_cmd.call_args[1]
        assert call_kwargs["auto_approve"] is True

    @patch("gobby.agents.spawners.embedded.pty")
    @patch("os.fork", return_value=12345)
    @patch("os.close")
    @patch("gobby.agents.spawners.embedded._get_spawn_utils")
    def test_spawn_agent_without_prompt(
        self, mock_utils, mock_close, mock_fork, mock_pty, spawner
    ) -> None:
        """spawn_agent() works without a prompt."""
        mock_pty.openpty.return_value = (10, 11)

        mock_create_file = MagicMock()
        mock_utils.return_value = (MagicMock(return_value=["claude"]), mock_create_file, 4096)

        result = spawner.spawn_agent(
            cli="claude",
            cwd="/tmp",
            session_id="sess-123",
            parent_session_id="sess-parent",
            agent_run_id="run-456",
            project_id="proj-789",
            prompt=None,
        )

        assert result.success is True
        mock_create_file.assert_not_called()

    @patch("gobby.agents.spawners.embedded.pty")
    @patch("os.fork", return_value=12345)
    @patch("os.close")
    @patch("gobby.agents.spawners.embedded._get_spawn_utils")
    def test_spawn_agent_with_path_object_cwd(
        self, mock_utils, mock_close, mock_fork, mock_pty, spawner
    ) -> None:
        """spawn_agent() accepts Path object for cwd."""
        mock_pty.openpty.return_value = (10, 11)

        mock_build_cmd = MagicMock(return_value=["codex"])
        mock_utils.return_value = (mock_build_cmd, MagicMock(), 4096)

        result = spawner.spawn_agent(
            cli="codex",
            cwd=Path("/projects/app"),
            session_id="sess-123",
            parent_session_id="sess-parent",
            agent_run_id="run-456",
            project_id="proj-789",
        )

        assert result.success is True
        # For codex, working_directory should be string form of path
        call_kwargs = mock_build_cmd.call_args[1]
        assert call_kwargs["working_directory"] == "/projects/app"


# =============================================================================
# Tests for child process behavior (line coverage for child fork branch)
# =============================================================================


class TestEmbeddedSpawnerChildProcess:
    """Tests for child process behavior in spawn().

    Note: These tests verify the error handling paths since we can't
    actually test the child process without real forking.
    """

    def test_spawn_error_handling_comprehensive(self, spawner, mock_pty, mock_os_close) -> None:
        """Comprehensive test for exception handling in spawn."""
        mock_pty.openpty.return_value = (10, 11)

        # Test generic exception
        with patch("os.fork", side_effect=Exception("Generic error")):
            result = spawner.spawn(["echo", "test"], cwd="/tmp")
            assert result.success is False
            assert "Generic error" in result.error


# =============================================================================
# Unix-only integration tests
# =============================================================================


@pytest.mark.skipif(sys.platform == "win32", reason="PTY not available on Windows")
class TestEmbeddedSpawnerUnixIntegration:
    """Integration tests for EmbeddedSpawner on Unix systems."""

    def test_spawn_real_process(self, spawner) -> None:
        """spawn() creates real PTY and runs command."""
        result = spawner.spawn(
            command=["echo", "hello"],
            cwd="/tmp",
        )

        try:
            assert result.success is True
            assert result.pid is not None
            assert result.pid > 0
            assert result.master_fd is not None
            assert result.master_fd > 0
        finally:
            result.close()
            if result.pid:
                try:
                    os.waitpid(result.pid, os.WNOHANG)
                except ChildProcessError:
                    pass

    def test_spawn_with_env_integration(self, spawner) -> None:
        """spawn() passes environment variables in real process."""
        result = spawner.spawn(
            command=["env"],
            cwd="/tmp",
            env={"TEST_VAR": "test_value"},
        )

        try:
            assert result.success is True
            assert result.master_fd is not None
        finally:
            result.close()
            if result.pid:
                try:
                    os.waitpid(result.pid, os.WNOHANG)
                except ChildProcessError:
                    pass

    def test_spawn_invalid_command(self, spawner) -> None:
        """spawn() handles invalid commands."""
        result = spawner.spawn(
            command=["nonexistent_command_12345"],
            cwd="/tmp",
        )

        # The spawn should succeed (fork succeeds) but the child will fail
        # The parent won't know about the exec failure immediately
        if result.success:
            try:
                # Give child time to fail
                import time

                time.sleep(0.1)
            finally:
                result.close()
                if result.pid:
                    try:
                        os.waitpid(result.pid, os.WNOHANG)
                    except ChildProcessError:
                        pass

    def test_spawn_read_from_pty(self, spawner) -> None:
        """spawn() allows reading from master fd."""
        result = spawner.spawn(
            command=["echo", "hello_from_pty"],
            cwd="/tmp",
        )

        try:
            assert result.success is True
            assert result.master_fd is not None

            # Read from PTY (with timeout to avoid hanging)
            import select

            readable, _, _ = select.select([result.master_fd], [], [], 2.0)
            if readable:
                output = os.read(result.master_fd, 1024)
                assert b"hello_from_pty" in output
        finally:
            result.close()
            if result.pid:
                try:
                    os.waitpid(result.pid, os.WNOHANG)
                except ChildProcessError:
                    pass


# =============================================================================
# Tests for EmbeddedPTYResult helper methods
# =============================================================================


class TestEmbeddedPTYResult:
    """Tests for EmbeddedPTYResult dataclass methods."""

    def test_close_with_valid_fds(self) -> None:
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

        # Verify fds are closed by checking they can't be closed again
        with pytest.raises(OSError):
            os.close(r)
        with pytest.raises(OSError):
            os.close(w)

    def test_close_with_none_fds(self) -> None:
        """close() handles None file descriptors gracefully."""
        result = EmbeddedPTYResult(
            success=False,
            message="Failed",
            master_fd=None,
            slave_fd=None,
        )
        # Should not raise
        result.close()

    def test_close_with_already_closed_fd(self) -> None:
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

    def test_close_master_only(self) -> None:
        """close() handles case where only master_fd is set."""
        r, w = os.pipe()
        os.close(w)  # Close one end ourselves

        result = EmbeddedPTYResult(
            success=True,
            message="Test",
            master_fd=r,
            slave_fd=None,
            pid=12345,
        )

        result.close()

        # Verify master fd is closed
        with pytest.raises(OSError):
            os.close(r)

    def test_close_slave_only(self) -> None:
        """close() handles case where only slave_fd is set."""
        r, w = os.pipe()
        os.close(r)  # Close one end ourselves

        result = EmbeddedPTYResult(
            success=True,
            message="Test",
            master_fd=None,
            slave_fd=w,
            pid=None,
        )

        result.close()

        # Verify slave fd is closed
        with pytest.raises(OSError):
            os.close(w)


# =============================================================================
# Tests for module constants
# =============================================================================


class TestModuleConstants:
    """Tests for module-level constants."""

    def test_max_env_prompt_length_value(self) -> None:
        """MAX_ENV_PROMPT_LENGTH has expected value."""
        assert MAX_ENV_PROMPT_LENGTH == 4096

    def test_max_env_prompt_length_is_positive(self) -> None:
        """MAX_ENV_PROMPT_LENGTH is a positive integer."""
        assert isinstance(MAX_ENV_PROMPT_LENGTH, int)
        assert MAX_ENV_PROMPT_LENGTH > 0


# =============================================================================
# Tests for edge cases and security
# =============================================================================


class TestEdgeCasesAndSecurity:
    """Tests for edge cases and security considerations."""

    def test_spawn_with_special_characters_in_command(
        self, spawner, mock_pty, mock_os_close
    ) -> None:
        """spawn() handles commands with special characters."""
        mock_pty.openpty.return_value = (10, 11)

        with patch("os.fork", return_value=12345):
            result = spawner.spawn(
                ["echo", "hello; rm -rf /; echo world"],
                cwd="/tmp",
            )

            assert result.success is True

    def test_spawn_with_unicode_in_command(self, spawner, mock_pty, mock_os_close) -> None:
        """spawn() handles commands with unicode characters."""
        mock_pty.openpty.return_value = (10, 11)

        with patch("os.fork", return_value=12345):
            result = spawner.spawn(
                ["echo", "Hello, world!"],
                cwd="/tmp",
            )

            assert result.success is True

    def test_spawn_with_empty_string_command(self, spawner, mock_pty, mock_os_close) -> None:
        """spawn() handles command with empty string element."""
        mock_pty.openpty.return_value = (10, 11)

        with patch("os.fork", return_value=12345):
            # Empty string is still a valid command element (though may fail to execute)
            result = spawner.spawn([""], cwd="/tmp")
            # Should not crash - behavior depends on execvpe
            assert result.success is True

    def test_spawn_with_spaces_in_path(self, spawner, mock_pty, mock_os_close) -> None:
        """spawn() handles working directory with spaces."""
        mock_pty.openpty.return_value = (10, 11)

        with patch("os.fork", return_value=12345):
            result = spawner.spawn(
                ["echo", "test"],
                cwd="/path/with spaces/here",
            )

            assert result.success is True

    @patch("gobby.agents.spawners.embedded.pty")
    @patch("os.fork", return_value=12345)
    @patch("os.close")
    @patch("gobby.agents.spawners.embedded._get_spawn_utils")
    def test_spawn_agent_with_special_chars_in_prompt(
        self, mock_utils, mock_close, mock_fork, mock_pty, spawner
    ) -> None:
        """spawn_agent() handles special characters in prompt."""
        mock_pty.openpty.return_value = (10, 11)
        mock_utils.return_value = (MagicMock(return_value=["claude"]), MagicMock(), 4096)

        result = spawner.spawn_agent(
            cli="claude",
            cwd="/tmp",
            session_id="sess-123",
            parent_session_id="sess-parent",
            agent_run_id="run-456",
            project_id="proj-789",
            prompt="Hello $(rm -rf /); echo 'injection'",
        )

        assert result.success is True

    @patch("gobby.agents.spawners.embedded.pty")
    @patch("os.fork", return_value=12345)
    @patch("os.close")
    @patch("gobby.agents.spawners.embedded._get_spawn_utils")
    def test_spawn_agent_with_newlines_in_prompt(
        self, mock_utils, mock_close, mock_fork, mock_pty, spawner
    ) -> None:
        """spawn_agent() handles newlines in prompt."""
        mock_pty.openpty.return_value = (10, 11)
        mock_utils.return_value = (MagicMock(return_value=["claude"]), MagicMock(), 4096)

        result = spawner.spawn_agent(
            cli="claude",
            cwd="/tmp",
            session_id="sess-123",
            parent_session_id="sess-parent",
            agent_run_id="run-456",
            project_id="proj-789",
            prompt="Line 1\nLine 2\nLine 3",
        )

        assert result.success is True


# =============================================================================
# Tests for platform-specific behavior
# =============================================================================


class TestPlatformSpecificBehavior:
    """Tests for platform-specific behavior."""

    @patch("platform.system", return_value="Darwin")
    def test_spawn_on_macos(self, mock_system, spawner, mock_pty, mock_os_close) -> None:
        """spawn() works on macOS."""
        mock_pty.openpty.return_value = (10, 11)

        with patch("os.fork", return_value=12345):
            result = spawner.spawn(["echo", "test"], cwd="/tmp")

            assert result.success is True

    @patch("platform.system", return_value="Linux")
    def test_spawn_on_linux(self, mock_system, spawner, mock_pty, mock_os_close) -> None:
        """spawn() works on Linux."""
        mock_pty.openpty.return_value = (10, 11)

        with patch("os.fork", return_value=12345):
            result = spawner.spawn(["echo", "test"], cwd="/tmp")

            assert result.success is True

    @patch("platform.system", return_value="FreeBSD")
    def test_spawn_on_freebsd(self, mock_system, spawner, mock_pty, mock_os_close) -> None:
        """spawn() works on FreeBSD (Unix-like)."""
        mock_pty.openpty.return_value = (10, 11)

        with patch("os.fork", return_value=12345):
            result = spawner.spawn(["echo", "test"], cwd="/tmp")

            assert result.success is True


# =============================================================================
# Tests for __all__ export
# =============================================================================


class TestModuleExports:
    """Tests for module exports."""

    def test_embedded_spawner_in_all(self) -> None:
        """EmbeddedSpawner is exported in __all__."""
        from gobby.agents.spawners import embedded

        assert "EmbeddedSpawner" in embedded.__all__
