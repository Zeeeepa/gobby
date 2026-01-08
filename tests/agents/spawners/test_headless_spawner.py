"""Comprehensive tests for HeadlessSpawner.

Tests cover:
- HeadlessSpawner.spawn() - synchronous spawning with output capture
- HeadlessSpawner.spawn_and_capture() - async spawning with callbacks and timeout
- HeadlessSpawner.spawn_agent() - agent spawning with environment setup
- Error handling and edge cases
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gobby.agents.spawners.base import HeadlessResult
from gobby.agents.spawners.headless import HeadlessSpawner, _get_spawn_utils

# =============================================================================
# Tests for _get_spawn_utils helper function
# =============================================================================


class TestGetSpawnUtils:
    """Tests for the _get_spawn_utils lazy import function."""

    def test_returns_correct_functions(self):
        """_get_spawn_utils returns the expected functions and constant."""
        build_cli_command, _create_prompt_file, max_env_prompt_length = _get_spawn_utils()

        # Verify types
        assert callable(build_cli_command)
        assert callable(_create_prompt_file)
        assert isinstance(max_env_prompt_length, int)

    def test_max_env_prompt_length_value(self):
        """_get_spawn_utils returns correct MAX_ENV_PROMPT_LENGTH."""
        _, _, max_env_prompt_length = _get_spawn_utils()
        assert max_env_prompt_length == 4096

    def test_build_cli_command_callable(self):
        """build_cli_command from _get_spawn_utils is functional."""
        build_cli_command, _, _ = _get_spawn_utils()

        cmd = build_cli_command("claude", prompt="hello")
        assert isinstance(cmd, list)
        assert "claude" in cmd


# =============================================================================
# Tests for HeadlessSpawner.spawn() - synchronous spawning
# =============================================================================


class TestHeadlessSpawnerSpawn:
    """Tests for HeadlessSpawner.spawn() method."""

    def test_spawn_simple_command(self):
        """spawn() runs a simple command successfully."""
        spawner = HeadlessSpawner()
        result = spawner.spawn(["echo", "hello"], cwd="/tmp")

        assert result.success is True
        assert result.pid is not None
        assert result.pid > 0
        assert result.process is not None
        assert result.error is None
        assert "Spawned headless process with PID" in result.message

        # Clean up
        stdout, _ = result.process.communicate()
        assert "hello" in stdout

    def test_spawn_captures_stdout(self):
        """spawn() captures stdout through the process handle."""
        spawner = HeadlessSpawner()
        result = spawner.spawn(["echo", "test output"], cwd="/tmp")

        assert result.success is True
        stdout, _ = result.process.communicate()
        assert "test output" in stdout

    def test_spawn_with_env_vars(self):
        """spawn() passes environment variables to the subprocess."""
        spawner = HeadlessSpawner()
        result = spawner.spawn(
            ["printenv", "HEADLESS_TEST_VAR"],
            cwd="/tmp",
            env={"HEADLESS_TEST_VAR": "headless_value_123"},
        )

        assert result.success is True
        stdout, _ = result.process.communicate()
        assert "headless_value_123" in stdout

    def test_spawn_merges_env_with_parent(self):
        """spawn() merges custom env with parent environment."""
        spawner = HeadlessSpawner()

        # Use PATH from parent environment
        result = spawner.spawn(
            ["sh", "-c", "echo PATH exists: $PATH"],
            cwd="/tmp",
            env={"CUSTOM_VAR": "custom_value"},
        )

        assert result.success is True
        stdout, _ = result.process.communicate()
        assert "PATH exists:" in stdout

    def test_spawn_without_env_uses_parent_env(self):
        """spawn() uses parent environment when env is None."""
        spawner = HeadlessSpawner()
        result = spawner.spawn(
            ["sh", "-c", "echo PATH: $PATH"],
            cwd="/tmp",
            env=None,
        )

        assert result.success is True
        stdout, _ = result.process.communicate()
        assert "PATH:" in stdout

    def test_spawn_with_working_directory(self):
        """spawn() uses the specified working directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            spawner = HeadlessSpawner()
            result = spawner.spawn(["pwd"], cwd=tmpdir)

            assert result.success is True
            stdout, _ = result.process.communicate()
            # tmpdir may be a symlink on macOS
            assert tmpdir in stdout or os.path.basename(tmpdir) in stdout

    def test_spawn_with_path_object(self):
        """spawn() accepts Path object for cwd."""
        with tempfile.TemporaryDirectory() as tmpdir:
            spawner = HeadlessSpawner()
            result = spawner.spawn(["pwd"], cwd=Path(tmpdir))

            assert result.success is True
            stdout, _ = result.process.communicate()
            assert tmpdir in stdout or os.path.basename(tmpdir) in stdout

    def test_spawn_returns_pid(self):
        """spawn() returns the process PID in the result."""
        spawner = HeadlessSpawner()
        result = spawner.spawn(["sleep", "0.1"], cwd="/tmp")

        assert result.success is True
        assert result.pid is not None
        assert result.pid > 0
        assert result.pid == result.process.pid

        # Clean up
        result.process.terminate()
        result.process.wait()

    def test_spawn_nonexistent_command_fails(self):
        """spawn() returns failure for non-existent commands."""
        spawner = HeadlessSpawner()
        result = spawner.spawn(["nonexistent_command_xyz_12345"], cwd="/tmp")

        assert result.success is False
        assert result.error is not None
        assert "Failed to spawn headless process" in result.message
        assert result.pid is None
        assert result.process is None

    def test_spawn_handles_popen_exception(self):
        """spawn() handles Popen exceptions gracefully."""
        spawner = HeadlessSpawner()

        with patch("subprocess.Popen", side_effect=OSError("Spawn failed")):
            result = spawner.spawn(["echo", "test"], cwd="/tmp")

            assert result.success is False
            assert "Spawn failed" in result.error
            assert "Failed to spawn headless process" in result.message

    def test_spawn_handles_permission_error(self):
        """spawn() handles PermissionError gracefully."""
        spawner = HeadlessSpawner()

        with patch("subprocess.Popen", side_effect=PermissionError("Access denied")):
            result = spawner.spawn(["echo", "test"], cwd="/tmp")

            assert result.success is False
            assert "Access denied" in result.error

    def test_spawn_handles_filenotfound_error(self):
        """spawn() handles FileNotFoundError gracefully."""
        spawner = HeadlessSpawner()

        with patch("subprocess.Popen", side_effect=FileNotFoundError("Command not found")):
            result = spawner.spawn(["nonexistent"], cwd="/tmp")

            assert result.success is False
            assert "Command not found" in result.error

    def test_spawn_process_configuration(self):
        """spawn() configures Popen with correct parameters."""
        spawner = HeadlessSpawner()

        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_popen.return_value = mock_process

            result = spawner.spawn(
                ["echo", "test"],
                cwd="/tmp",
                env={"TEST": "value"},
            )

            # Verify spawn result
            assert result.success is True
            assert result.pid == 12345

            # Verify Popen was called with correct arguments
            mock_popen.assert_called_once()
            call_args = mock_popen.call_args

            assert call_args[0][0] == ["echo", "test"]
            assert call_args[1]["cwd"] == "/tmp"
            assert call_args[1]["stdout"] == subprocess.PIPE
            assert call_args[1]["stderr"] == subprocess.STDOUT
            assert call_args[1]["stdin"] == subprocess.PIPE
            assert call_args[1]["text"] is True
            assert call_args[1]["bufsize"] == 1
            assert "TEST" in call_args[1]["env"]

    def test_spawn_stderr_merged_with_stdout(self):
        """spawn() merges stderr into stdout."""
        spawner = HeadlessSpawner()
        result = spawner.spawn(
            ["sh", "-c", "echo stdout; echo stderr >&2"],
            cwd="/tmp",
        )

        assert result.success is True
        stdout, _ = result.process.communicate()
        # Both stdout and stderr should be in the output
        assert "stdout" in stdout
        assert "stderr" in stdout


# =============================================================================
# Tests for HeadlessSpawner.spawn_and_capture() - async spawning
# =============================================================================


@pytest.mark.asyncio
class TestHeadlessSpawnerSpawnAndCapture:
    """Tests for HeadlessSpawner.spawn_and_capture() async method."""

    async def test_spawn_and_capture_basic(self):
        """spawn_and_capture() captures command output."""
        spawner = HeadlessSpawner()
        result = await spawner.spawn_and_capture(
            command=["echo", "async test"],
            cwd="/tmp",
        )

        assert result.success is True
        assert "async test" in result.output_buffer or "async test" in result.get_output()

    async def test_spawn_and_capture_multi_line_output(self):
        """spawn_and_capture() captures multiple lines of output."""
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

    async def test_spawn_and_capture_output_buffer(self):
        """spawn_and_capture() populates output_buffer list."""
        spawner = HeadlessSpawner()
        result = await spawner.spawn_and_capture(
            command=["sh", "-c", "echo a; echo b; echo c"],
            cwd="/tmp",
        )

        assert result.success is True
        assert len(result.output_buffer) == 3
        assert "a" in result.output_buffer
        assert "b" in result.output_buffer
        assert "c" in result.output_buffer

    async def test_spawn_and_capture_callback_invocation(self):
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
        assert len(captured_lines) == 3
        assert "one" in captured_lines
        assert "two" in captured_lines
        assert "three" in captured_lines

    async def test_spawn_and_capture_callback_none(self):
        """spawn_and_capture() works without callback."""
        spawner = HeadlessSpawner()
        result = await spawner.spawn_and_capture(
            command=["echo", "no callback"],
            cwd="/tmp",
            on_output=None,
        )

        assert result.success is True
        assert "no callback" in result.get_output()

    async def test_spawn_and_capture_with_timeout(self):
        """spawn_and_capture() terminates process on timeout."""
        spawner = HeadlessSpawner()
        result = await spawner.spawn_and_capture(
            command=["sleep", "60"],
            cwd="/tmp",
            timeout=0.5,
        )

        # Should timeout
        assert result.error == "Process timed out"
        # Process should be terminated
        if result.process:
            assert result.process.poll() is not None

    async def test_spawn_and_capture_timeout_captures_partial_output(self):
        """spawn_and_capture() captures output before timeout."""
        spawner = HeadlessSpawner()
        result = await spawner.spawn_and_capture(
            command=["sh", "-c", "echo before_timeout; sleep 60"],
            cwd="/tmp",
            timeout=1.0,
        )

        assert result.error == "Process timed out"
        assert "before_timeout" in result.get_output()

    async def test_spawn_and_capture_no_timeout(self):
        """spawn_and_capture() runs to completion without timeout."""
        spawner = HeadlessSpawner()
        result = await spawner.spawn_and_capture(
            command=["echo", "complete"],
            cwd="/tmp",
            timeout=None,
        )

        assert result.success is True
        assert result.error is None
        assert "complete" in result.get_output()

    async def test_spawn_and_capture_with_env_vars(self):
        """spawn_and_capture() passes environment variables."""
        spawner = HeadlessSpawner()
        result = await spawner.spawn_and_capture(
            command=["printenv", "ASYNC_TEST_VAR"],
            cwd="/tmp",
            env={"ASYNC_TEST_VAR": "async_value_456"},
        )

        assert result.success is True
        assert "async_value_456" in result.get_output()

    async def test_spawn_and_capture_large_output(self):
        """spawn_and_capture() handles large output."""
        spawner = HeadlessSpawner()
        result = await spawner.spawn_and_capture(
            command=["sh", "-c", "for i in $(seq 1 500); do echo line_$i; done"],
            cwd="/tmp",
        )

        assert result.success is True
        assert len(result.output_buffer) == 500
        assert "line_1" in result.output_buffer
        assert "line_500" in result.output_buffer

    async def test_spawn_and_capture_waits_for_completion(self):
        """spawn_and_capture() waits for process to complete."""
        spawner = HeadlessSpawner()
        result = await spawner.spawn_and_capture(
            command=["sh", "-c", "echo done; exit 42"],
            cwd="/tmp",
        )

        assert result.success is True
        if result.process:
            assert result.process.returncode == 42

    async def test_spawn_and_capture_stderr_merged(self):
        """spawn_and_capture() captures stderr in output."""
        spawner = HeadlessSpawner()
        result = await spawner.spawn_and_capture(
            command=["sh", "-c", "echo stdout_msg; echo stderr_msg >&2"],
            cwd="/tmp",
        )

        assert result.success is True
        output = result.get_output()
        assert "stdout_msg" in output
        assert "stderr_msg" in output

    async def test_spawn_and_capture_spawn_failure_propagates(self):
        """spawn_and_capture() propagates spawn failure."""
        spawner = HeadlessSpawner()
        result = await spawner.spawn_and_capture(
            command=["nonexistent_command_xyz_async"],
            cwd="/tmp",
        )

        assert result.success is False
        assert result.error is not None

    async def test_spawn_and_capture_returns_early_on_spawn_failure(self):
        """spawn_and_capture() returns immediately if spawn fails."""
        spawner = HeadlessSpawner()

        with patch.object(
            spawner,
            "spawn",
            return_value=HeadlessResult(success=False, message="Spawn failed", error="Test error"),
        ):
            result = await spawner.spawn_and_capture(
                command=["echo", "test"],
                cwd="/tmp",
            )

            assert result.success is False
            assert result.error == "Test error"
            assert len(result.output_buffer) == 0

    async def test_spawn_and_capture_handles_read_exception(self):
        """spawn_and_capture() handles exceptions during output reading."""
        spawner = HeadlessSpawner()

        # Create a mock process that raises an exception when reading
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.stdout = MagicMock()
        mock_process.stdout.readline.side_effect = OSError("Read error")
        mock_process.wait = MagicMock()

        mock_result = HeadlessResult(
            success=True,
            message="Spawned",
            pid=12345,
            process=mock_process,
        )

        with patch.object(spawner, "spawn", return_value=mock_result):
            result = await spawner.spawn_and_capture(
                command=["echo", "test"],
                cwd="/tmp",
            )

            # Should capture the error
            assert result.error is not None
            assert "Read error" in result.error

    async def test_spawn_and_capture_timeout_waits_for_termination(self):
        """spawn_and_capture() waits for process termination after timeout."""
        spawner = HeadlessSpawner()

        # Use a quick timeout
        result = await spawner.spawn_and_capture(
            command=["sleep", "60"],
            cwd="/tmp",
            timeout=0.2,
        )

        assert result.error == "Process timed out"
        # Process should be fully terminated
        if result.process:
            # Give a moment for termination to complete
            await asyncio.sleep(0.1)
            assert result.process.poll() is not None


# =============================================================================
# Tests for HeadlessSpawner.spawn_agent() - agent spawning
# =============================================================================


class TestHeadlessSpawnerSpawnAgent:
    """Tests for HeadlessSpawner.spawn_agent() method."""

    def test_spawn_agent_basic(self):
        """spawn_agent() builds correct command for Claude CLI."""
        spawner = HeadlessSpawner()

        with patch.object(spawner, "spawn") as mock_spawn:
            mock_spawn.return_value = HeadlessResult(success=True, message="OK", pid=123)

            result = spawner.spawn_agent(
                cli="claude",
                cwd="/tmp",
                session_id="sess-123",
                parent_session_id="parent-456",
                agent_run_id="run-789",
                project_id="proj-abc",
            )

            assert result.success is True
            mock_spawn.assert_called_once()

            call_args = mock_spawn.call_args
            command = call_args[0][0]
            env = call_args[0][2] if len(call_args[0]) > 2 else call_args[1].get("env")

            # Verify command includes Claude flags
            assert command[0] == "claude"
            assert "--dangerously-skip-permissions" in command
            assert "--session-id" in command

            # Verify env vars
            assert env["GOBBY_SESSION_ID"] == "sess-123"
            assert env["GOBBY_PARENT_SESSION_ID"] == "parent-456"
            assert env["GOBBY_AGENT_RUN_ID"] == "run-789"
            assert env["GOBBY_PROJECT_ID"] == "proj-abc"

    def test_spawn_agent_with_prompt(self):
        """spawn_agent() passes prompt in CLI and env."""
        spawner = HeadlessSpawner()

        with patch.object(spawner, "spawn") as mock_spawn:
            mock_spawn.return_value = HeadlessResult(success=True, message="OK", pid=123)

            spawner.spawn_agent(
                cli="claude",
                cwd="/tmp",
                session_id="sess-123",
                parent_session_id="parent-456",
                agent_run_id="run-789",
                project_id="proj-abc",
                prompt="Test prompt",
            )

            call_args = mock_spawn.call_args
            command = call_args[0][0]
            env = call_args[0][2] if len(call_args[0]) > 2 else call_args[1].get("env")

            # Prompt should be in command (for Claude, uses -p flag)
            assert "-p" in command
            assert "Test prompt" in command

            # Short prompt should be in env
            assert env["GOBBY_PROMPT"] == "Test prompt"

    def test_spawn_agent_long_prompt_uses_file(self):
        """spawn_agent() writes long prompts to file."""
        spawner = HeadlessSpawner()

        long_prompt = "x" * 5000  # Over MAX_ENV_PROMPT_LENGTH

        with patch.object(spawner, "spawn") as mock_spawn:
            mock_spawn.return_value = HeadlessResult(success=True, message="OK", pid=123)

            with patch("gobby.agents.spawners.headless._get_spawn_utils") as mock_utils:
                mock_build = MagicMock(return_value=["claude"])
                mock_create_file = MagicMock(return_value="/tmp/prompt.txt")
                mock_utils.return_value = (mock_build, mock_create_file, 4096)

                spawner.spawn_agent(
                    cli="claude",
                    cwd="/tmp",
                    session_id="sess-123",
                    parent_session_id="parent-456",
                    agent_run_id="run-789",
                    project_id="proj-abc",
                    prompt=long_prompt,
                )

                # Verify prompt file was created
                mock_create_file.assert_called_once_with(long_prompt, "sess-123")

                call_args = mock_spawn.call_args
                env = call_args[0][2] if len(call_args[0]) > 2 else call_args[1].get("env")

                # Prompt file path should be in env
                assert env["GOBBY_PROMPT_FILE"] == "/tmp/prompt.txt"

    def test_spawn_agent_with_workflow(self):
        """spawn_agent() passes workflow name in env."""
        spawner = HeadlessSpawner()

        with patch.object(spawner, "spawn") as mock_spawn:
            mock_spawn.return_value = HeadlessResult(success=True, message="OK", pid=123)

            spawner.spawn_agent(
                cli="claude",
                cwd="/tmp",
                session_id="sess-123",
                parent_session_id="parent-456",
                agent_run_id="run-789",
                project_id="proj-abc",
                workflow_name="plan-execute",
            )

            call_args = mock_spawn.call_args
            env = call_args[0][2] if len(call_args[0]) > 2 else call_args[1].get("env")

            assert env["GOBBY_WORKFLOW_NAME"] == "plan-execute"

    def test_spawn_agent_agent_depth(self):
        """spawn_agent() passes agent depth in env."""
        spawner = HeadlessSpawner()

        with patch.object(spawner, "spawn") as mock_spawn:
            mock_spawn.return_value = HeadlessResult(success=True, message="OK", pid=123)

            spawner.spawn_agent(
                cli="claude",
                cwd="/tmp",
                session_id="sess-123",
                parent_session_id="parent-456",
                agent_run_id="run-789",
                project_id="proj-abc",
                agent_depth=2,
                max_agent_depth=5,
            )

            call_args = mock_spawn.call_args
            env = call_args[0][2] if len(call_args[0]) > 2 else call_args[1].get("env")

            assert env["GOBBY_AGENT_DEPTH"] == "2"
            assert env["GOBBY_MAX_AGENT_DEPTH"] == "5"

    def test_spawn_agent_codex_working_directory(self):
        """spawn_agent() passes working directory for Codex CLI."""
        spawner = HeadlessSpawner()

        with patch.object(spawner, "spawn") as mock_spawn:
            mock_spawn.return_value = HeadlessResult(success=True, message="OK", pid=123)

            spawner.spawn_agent(
                cli="codex",
                cwd="/projects/app",
                session_id="sess-123",
                parent_session_id="parent-456",
                agent_run_id="run-789",
                project_id="proj-abc",
            )

            call_args = mock_spawn.call_args
            command = call_args[0][0]

            # Codex command should have -C flag
            assert "-C" in command
            assert "/projects/app" in command

    def test_spawn_agent_gemini_cli(self):
        """spawn_agent() builds correct command for Gemini CLI."""
        spawner = HeadlessSpawner()

        with patch.object(spawner, "spawn") as mock_spawn:
            mock_spawn.return_value = HeadlessResult(success=True, message="OK", pid=123)

            spawner.spawn_agent(
                cli="gemini",
                cwd="/tmp",
                session_id="sess-123",
                parent_session_id="parent-456",
                agent_run_id="run-789",
                project_id="proj-abc",
            )

            call_args = mock_spawn.call_args
            command = call_args[0][0]

            # Gemini command should have yolo mode
            assert "--approval-mode" in command
            assert "yolo" in command

    def test_spawn_agent_default_depth(self):
        """spawn_agent() uses default agent depth values."""
        spawner = HeadlessSpawner()

        with patch.object(spawner, "spawn") as mock_spawn:
            mock_spawn.return_value = HeadlessResult(success=True, message="OK", pid=123)

            spawner.spawn_agent(
                cli="claude",
                cwd="/tmp",
                session_id="sess-123",
                parent_session_id="parent-456",
                agent_run_id="run-789",
                project_id="proj-abc",
            )

            call_args = mock_spawn.call_args
            env = call_args[0][2] if len(call_args[0]) > 2 else call_args[1].get("env")

            # Default values
            assert env["GOBBY_AGENT_DEPTH"] == "1"
            assert env["GOBBY_MAX_AGENT_DEPTH"] == "3"

    def test_spawn_agent_no_workflow(self):
        """spawn_agent() works without workflow name."""
        spawner = HeadlessSpawner()

        with patch.object(spawner, "spawn") as mock_spawn:
            mock_spawn.return_value = HeadlessResult(success=True, message="OK", pid=123)

            spawner.spawn_agent(
                cli="claude",
                cwd="/tmp",
                session_id="sess-123",
                parent_session_id="parent-456",
                agent_run_id="run-789",
                project_id="proj-abc",
                workflow_name=None,
            )

            call_args = mock_spawn.call_args
            env = call_args[0][2] if len(call_args[0]) > 2 else call_args[1].get("env")

            # No workflow env var should be set
            assert "GOBBY_WORKFLOW_NAME" not in env

    def test_spawn_agent_no_prompt(self):
        """spawn_agent() works without prompt."""
        spawner = HeadlessSpawner()

        with patch.object(spawner, "spawn") as mock_spawn:
            mock_spawn.return_value = HeadlessResult(success=True, message="OK", pid=123)

            spawner.spawn_agent(
                cli="claude",
                cwd="/tmp",
                session_id="sess-123",
                parent_session_id="parent-456",
                agent_run_id="run-789",
                project_id="proj-abc",
                prompt=None,
            )

            call_args = mock_spawn.call_args
            env = call_args[0][2] if len(call_args[0]) > 2 else call_args[1].get("env")

            # No prompt env vars should be set
            assert "GOBBY_PROMPT" not in env
            assert "GOBBY_PROMPT_FILE" not in env

    def test_spawn_agent_prompt_at_boundary(self):
        """spawn_agent() handles prompt exactly at MAX_ENV_PROMPT_LENGTH."""
        spawner = HeadlessSpawner()

        # Exactly at threshold
        exact_prompt = "x" * 4096

        with patch.object(spawner, "spawn") as mock_spawn:
            mock_spawn.return_value = HeadlessResult(success=True, message="OK", pid=123)

            with patch("gobby.agents.spawners.headless._get_spawn_utils") as mock_utils:
                mock_build = MagicMock(return_value=["claude"])
                mock_create_file = MagicMock(return_value="/tmp/prompt.txt")
                mock_utils.return_value = (mock_build, mock_create_file, 4096)

                spawner.spawn_agent(
                    cli="claude",
                    cwd="/tmp",
                    session_id="sess-123",
                    parent_session_id="parent-456",
                    agent_run_id="run-789",
                    project_id="proj-abc",
                    prompt=exact_prompt,
                )

                # At exactly MAX, should NOT use file
                mock_create_file.assert_not_called()

    def test_spawn_agent_prompt_one_over_boundary(self):
        """spawn_agent() uses file for prompt one char over MAX_ENV_PROMPT_LENGTH."""
        spawner = HeadlessSpawner()

        # One over threshold
        over_prompt = "x" * 4097

        with patch.object(spawner, "spawn") as mock_spawn:
            mock_spawn.return_value = HeadlessResult(success=True, message="OK", pid=123)

            with patch("gobby.agents.spawners.headless._get_spawn_utils") as mock_utils:
                mock_build = MagicMock(return_value=["claude"])
                mock_create_file = MagicMock(return_value="/tmp/prompt.txt")
                mock_utils.return_value = (mock_build, mock_create_file, 4096)

                spawner.spawn_agent(
                    cli="claude",
                    cwd="/tmp",
                    session_id="sess-123",
                    parent_session_id="parent-456",
                    agent_run_id="run-789",
                    project_id="proj-abc",
                    prompt=over_prompt,
                )

                # Over MAX, should use file
                mock_create_file.assert_called_once()


# =============================================================================
# Tests for HeadlessResult dataclass
# =============================================================================


class TestHeadlessResult:
    """Tests for HeadlessResult dataclass."""

    def test_success_result_fields(self):
        """HeadlessResult has correct fields for success."""
        result = HeadlessResult(
            success=True,
            message="Spawned headless",
            pid=12345,
            process=None,
            output_buffer=["line1", "line2"],
        )

        assert result.success is True
        assert result.message == "Spawned headless"
        assert result.pid == 12345
        assert result.output_buffer == ["line1", "line2"]
        assert result.error is None

    def test_failure_result_fields(self):
        """HeadlessResult has correct fields for failure."""
        result = HeadlessResult(
            success=False,
            message="Failed to spawn",
            error="Command not found",
        )

        assert result.success is False
        assert result.message == "Failed to spawn"
        assert result.error == "Command not found"
        assert result.pid is None
        assert result.process is None

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

    def test_get_output_single_line(self):
        """get_output() returns single line without trailing newline."""
        result = HeadlessResult(
            success=True,
            message="Test",
            output_buffer=["only line"],
        )

        assert result.get_output() == "only line"

    def test_output_buffer_default_empty(self):
        """HeadlessResult has empty output_buffer by default."""
        result = HeadlessResult(success=True, message="Test")
        assert result.output_buffer == []

    def test_output_buffer_mutable(self):
        """output_buffer can be modified."""
        result = HeadlessResult(success=True, message="Test")
        result.output_buffer.append("new line")
        assert "new line" in result.output_buffer

    def test_error_mutable(self):
        """error field can be modified."""
        result = HeadlessResult(success=True, message="Test")
        assert result.error is None

        result.error = "Something went wrong"
        assert result.error == "Something went wrong"


# =============================================================================
# Integration tests
# =============================================================================


@pytest.mark.skipif(sys.platform == "win32", reason="Unix-specific tests")
class TestHeadlessSpawnerIntegration:
    """Integration tests for HeadlessSpawner on Unix systems."""

    def test_spawn_real_process_sync(self):
        """Integration: spawn() runs real process."""
        spawner = HeadlessSpawner()
        result = spawner.spawn(
            command=["sh", "-c", "echo hello; echo world"],
            cwd="/tmp",
        )

        assert result.success is True
        assert result.pid > 0

        stdout, _ = result.process.communicate()
        assert "hello" in stdout
        assert "world" in stdout

    @pytest.mark.asyncio
    async def test_spawn_and_capture_real_process(self):
        """Integration: spawn_and_capture() runs real process."""
        spawner = HeadlessSpawner()
        result = await spawner.spawn_and_capture(
            command=["sh", "-c", "echo async_hello; echo async_world"],
            cwd="/tmp",
        )

        assert result.success is True
        output = result.get_output()
        assert "async_hello" in output
        assert "async_world" in output

    @pytest.mark.asyncio
    async def test_spawn_and_capture_with_callback_integration(self):
        """Integration: callback receives real output."""
        spawner = HeadlessSpawner()
        lines: list[str] = []

        result = await spawner.spawn_and_capture(
            command=["seq", "1", "5"],
            cwd="/tmp",
            on_output=lambda line: lines.append(line),
        )

        assert result.success is True
        assert len(lines) == 5
        assert "1" in lines
        assert "5" in lines

    def test_spawn_agent_integration(self):
        """Integration: spawn_agent() creates process with env vars."""
        spawner = HeadlessSpawner()

        # Use 'env' command instead of actual CLI to verify env vars
        with patch("gobby.agents.spawners.headless._get_spawn_utils") as mock_utils:
            mock_utils.return_value = (
                lambda cli, **_: ["env"],
                MagicMock(),
                4096,
            )

            result = spawner.spawn_agent(
                cli="claude",
                cwd="/tmp",
                session_id="integration-sess",
                parent_session_id="integration-parent",
                agent_run_id="integration-run",
                project_id="integration-proj",
            )

            assert result.success is True

            # Read env output
            stdout, _ = result.process.communicate()
            assert "GOBBY_SESSION_ID=integration-sess" in stdout
            assert "GOBBY_PARENT_SESSION_ID=integration-parent" in stdout


# =============================================================================
# Edge cases and error handling
# =============================================================================


class TestHeadlessSpawnerEdgeCases:
    """Tests for edge cases and error handling."""

    def test_spawn_empty_command(self):
        """spawn() handles empty command list."""
        spawner = HeadlessSpawner()

        with patch("subprocess.Popen", side_effect=IndexError("Empty command")):
            result = spawner.spawn([], cwd="/tmp")
            assert result.success is False

    def test_spawn_with_special_characters_in_args(self):
        """spawn() handles special characters in arguments."""
        spawner = HeadlessSpawner()
        result = spawner.spawn(
            ["echo", "hello $world", "with\nnewline", "and;semicolon"],
            cwd="/tmp",
        )

        assert result.success is True
        stdout, _ = result.process.communicate()
        assert "$world" in stdout

    def test_spawn_with_unicode_in_args(self):
        """spawn() handles unicode in arguments."""
        spawner = HeadlessSpawner()
        result = spawner.spawn(
            ["echo", "hello \u4e16\u754c"],  # "hello world" in Chinese
            cwd="/tmp",
        )

        assert result.success is True
        stdout, _ = result.process.communicate()
        assert "\u4e16\u754c" in stdout or "world" in stdout.lower()

    @pytest.mark.asyncio
    async def test_spawn_and_capture_empty_output(self):
        """spawn_and_capture() handles empty output."""
        spawner = HeadlessSpawner()
        result = await spawner.spawn_and_capture(
            command=["true"],  # Produces no output
            cwd="/tmp",
        )

        assert result.success is True
        assert result.output_buffer == []
        assert result.get_output() == ""

    @pytest.mark.asyncio
    async def test_spawn_and_capture_rapid_output(self):
        """spawn_and_capture() handles rapid successive output."""
        spawner = HeadlessSpawner()
        result = await spawner.spawn_and_capture(
            command=["sh", "-c", "for i in $(seq 1 100); do echo $i; done"],
            cwd="/tmp",
        )

        assert result.success is True
        assert len(result.output_buffer) == 100

    def test_spawn_nonexistent_cwd(self):
        """spawn() handles non-existent working directory."""
        spawner = HeadlessSpawner()
        result = spawner.spawn(
            ["echo", "test"],
            cwd="/nonexistent/directory/path",
        )

        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_spawn_and_capture_process_exits_before_timeout(self):
        """spawn_and_capture() completes before timeout expires."""
        spawner = HeadlessSpawner()
        result = await spawner.spawn_and_capture(
            command=["echo", "quick"],
            cwd="/tmp",
            timeout=10.0,  # Long timeout
        )

        # Should complete without hitting timeout
        assert result.success is True
        assert result.error is None
        assert "quick" in result.get_output()

    @pytest.mark.asyncio
    async def test_spawn_and_capture_process_none_after_failed_spawn(self):
        """spawn_and_capture() handles None process after spawn failure."""
        spawner = HeadlessSpawner()

        with patch.object(
            spawner,
            "spawn",
            return_value=HeadlessResult(
                success=False,
                message="Spawn failed",
                error="Test error",
                process=None,
            ),
        ):
            result = await spawner.spawn_and_capture(
                command=["echo", "test"],
                cwd="/tmp",
            )

            assert result.success is False
            assert result.process is None


# =============================================================================
# Tests for async timeout handling
# =============================================================================


@pytest.mark.asyncio
class TestAsyncTimeoutHandling:
    """Tests for async timeout handling in spawn_and_capture."""

    async def test_timeout_termination_completes(self):
        """Process termination completes after timeout."""
        spawner = HeadlessSpawner()

        result = await spawner.spawn_and_capture(
            command=["sleep", "30"],
            cwd="/tmp",
            timeout=0.3,
        )

        assert result.error == "Process timed out"
        # Allow time for termination
        await asyncio.sleep(0.2)

        if result.process:
            assert result.process.poll() is not None

    async def test_timeout_error_in_termination_suppressed(self):
        """Errors during timeout termination are suppressed."""
        spawner = HeadlessSpawner()

        # Create mock that raises during wait after terminate
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.stdout = MagicMock()
        mock_process.stdout.readline = MagicMock(return_value="")
        mock_process.terminate = MagicMock()
        mock_process.wait = MagicMock(side_effect=[None, OSError("Wait failed")])

        mock_result = HeadlessResult(
            success=True,
            message="Spawned",
            pid=12345,
            process=mock_process,
        )

        with patch.object(spawner, "spawn", return_value=mock_result):
            # Simulate timeout by using a very short timeout
            # The mock will complete immediately so we need to force timeout
            with patch("asyncio.wait_for", side_effect=TimeoutError()):
                result = await spawner.spawn_and_capture(
                    command=["echo", "test"],
                    cwd="/tmp",
                    timeout=0.1,
                )

                # Should still report timeout
                assert result.error == "Process timed out"
