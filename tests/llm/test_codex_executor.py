"""Tests for CodexExecutor class.

Note: CodexExecutor only supports subscription/cli mode. API key mode is handled
by LiteLLMExecutor with provider='codex'. See test_litellm_executor.py for
API key mode tests.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.llm.executor import ToolSchema


class TestCodexExecutorInit:
    """Tests for CodexExecutor initialization."""

    def test_init_subscription_mode_without_cli_raises(self):
        """CodexExecutor raises ValueError when CLI not found."""
        with patch("shutil.which", return_value=None):
            from gobby.llm.codex_executor import CodexExecutor

            with pytest.raises(ValueError, match="Codex CLI not found"):
                CodexExecutor(auth_mode="subscription")

    def test_init_subscription_mode_with_cli(self):
        """CodexExecutor initializes in subscription mode when CLI found."""
        with patch("shutil.which", return_value="/usr/local/bin/codex"):
            from gobby.llm.codex_executor import CodexExecutor

            executor = CodexExecutor(auth_mode="subscription")

            assert executor.auth_mode == "subscription"
            assert executor._cli_path == "/usr/local/bin/codex"

    def test_init_cli_mode_with_cli(self):
        """CodexExecutor initializes in cli mode when CLI found."""
        with patch("shutil.which", return_value="/usr/local/bin/codex"):
            from gobby.llm.codex_executor import CodexExecutor

            executor = CodexExecutor(auth_mode="cli")

            assert executor.auth_mode == "cli"
            assert executor._cli_path == "/usr/local/bin/codex"

    def test_init_with_custom_model(self):
        """CodexExecutor accepts custom default model."""
        with patch("shutil.which", return_value="/usr/local/bin/codex"):
            from gobby.llm.codex_executor import CodexExecutor

            executor = CodexExecutor(auth_mode="subscription", default_model="gpt-4-turbo")

            assert executor.default_model == "gpt-4-turbo"

    def test_init_api_key_mode_raises(self):
        """CodexExecutor raises ValueError for api_key mode (now unsupported)."""
        from gobby.llm.codex_executor import CodexExecutor

        with pytest.raises(ValueError, match="only supports subscription/cli mode"):
            CodexExecutor(auth_mode="api_key")

    def test_init_invalid_auth_mode_raises(self):
        """CodexExecutor raises ValueError for invalid auth mode."""
        from gobby.llm.codex_executor import CodexExecutor

        with pytest.raises(ValueError, match="only supports subscription/cli mode"):
            CodexExecutor(auth_mode="invalid")  # type: ignore


class TestCodexExecutorSubscriptionMode:
    """Tests for CodexExecutor in subscription mode."""

    @pytest.fixture
    def executor_subscription(self):
        """Create executor in subscription mode with mocked CLI."""
        with patch("shutil.which", return_value="/usr/local/bin/codex"):
            from gobby.llm.codex_executor import CodexExecutor

            return CodexExecutor(auth_mode="subscription")

    @pytest.mark.asyncio
    async def test_run_parses_jsonl_output(self, executor_subscription):
        """Run parses JSONL output from codex exec correctly."""
        # Sample JSONL output from codex exec --json
        jsonl_output = "\n".join(
            [
                json.dumps({"type": "thread.started", "thread_id": "thread-123"}),
                json.dumps({"type": "turn.started"}),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {"id": "item_0", "type": "reasoning", "text": "Thinking..."},
                    }
                ),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "item_1",
                            "type": "command_execution",
                            "command": "ls -la",
                            "aggregated_output": "total 0\n",
                            "exit_code": 0,
                            "status": "completed",
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "item_2",
                            "type": "agent_message",
                            "text": "Done listing files.",
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "turn.completed",
                        "usage": {"input_tokens": 100, "output_tokens": 50},
                    }
                ),
            ]
        )

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(jsonl_output.encode(), b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await executor_subscription.run(
                prompt="List files",
                tools=[],  # Ignored in subscription mode
                tool_handler=AsyncMock(),
            )

        assert result.status == "success"
        assert result.output == "Done listing files."
        assert result.turns_used == 1
        # Should have one tool call for the command execution
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].tool_name == "bash"
        assert result.tool_calls[0].arguments["command"] == "ls -la"

    @pytest.mark.asyncio
    async def test_run_handles_cli_error(self, executor_subscription):
        """Run handles CLI errors correctly."""
        mock_process = AsyncMock()
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(return_value=(b"", b"Authentication failed"))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await executor_subscription.run(
                prompt="Do something",
                tools=[],
                tool_handler=AsyncMock(),
            )

        assert result.status == "error"
        assert "exited with code 1" in result.error
        assert "Authentication failed" in result.error

    @pytest.mark.asyncio
    async def test_run_handles_timeout(self, executor_subscription):
        """Run handles CLI timeout correctly."""
        mock_process = AsyncMock()

        async def slow_communicate():
            await asyncio.sleep(10)
            return (b"", b"")

        mock_process.communicate = slow_communicate
        mock_process.kill = MagicMock()
        mock_process.wait = AsyncMock()

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await executor_subscription.run(
                prompt="Do something",
                tools=[],
                tool_handler=AsyncMock(),
                timeout=0.1,
            )

        assert result.status == "timeout"
        assert "timed out" in result.error
        mock_process.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_handles_file_changes(self, executor_subscription):
        """Run records file changes from JSONL output."""
        jsonl_output = "\n".join(
            [
                json.dumps({"type": "thread.started", "thread_id": "thread-123"}),
                json.dumps({"type": "turn.started"}),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "item_1",
                            "type": "file_change",
                            "path": "/src/main.py",
                            "change_type": "modified",
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "item_2",
                            "type": "agent_message",
                            "text": "File updated.",
                        },
                    }
                ),
                json.dumps({"type": "turn.completed"}),
            ]
        )

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(jsonl_output.encode(), b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await executor_subscription.run(
                prompt="Update file",
                tools=[],
                tool_handler=AsyncMock(),
            )

        assert result.status == "success"
        # Should have file_change recorded
        file_change_calls = [tc for tc in result.tool_calls if tc.tool_name == "file_change"]
        assert len(file_change_calls) == 1
        assert file_change_calls[0].arguments["path"] == "/src/main.py"

    @pytest.mark.asyncio
    async def test_tools_ignored_in_subscription_mode(self, executor_subscription):
        """Custom tools are ignored in subscription mode."""
        jsonl_output = json.dumps(
            {
                "type": "item.completed",
                "item": {"id": "item_1", "type": "agent_message", "text": "Done"},
            }
        )

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(jsonl_output.encode(), b""))

        # Even with tools provided, they should be ignored
        custom_tools = [
            ToolSchema(
                name="my_custom_tool",
                description="Custom tool",
                input_schema={"type": "object"},
            )
        ]
        tool_handler = AsyncMock()

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await executor_subscription.run(
                prompt="Do something",
                tools=custom_tools,
                tool_handler=tool_handler,
            )

        # Tool handler should never be called in subscription mode
        tool_handler.assert_not_called()
        assert result.status == "success"


class TestCodexExecutorProviderName:
    """Tests for provider_name property."""

    def test_provider_name_subscription_mode(self):
        """Provider name is 'codex' in subscription mode."""
        with patch("shutil.which", return_value="/usr/local/bin/codex"):
            from gobby.llm.codex_executor import CodexExecutor

            executor = CodexExecutor(auth_mode="subscription")
            assert executor.provider_name == "codex"

    def test_provider_name_cli_mode(self):
        """Provider name is 'codex' in cli mode."""
        with patch("shutil.which", return_value="/usr/local/bin/codex"):
            from gobby.llm.codex_executor import CodexExecutor

            executor = CodexExecutor(auth_mode="cli")
            assert executor.provider_name == "codex"


class TestCodexExecutorSubscriptionModeEdgeCases:
    """Tests for edge cases in subscription mode."""

    @pytest.fixture
    def executor_subscription(self):
        """Create executor in subscription mode with mocked CLI."""
        with patch("shutil.which", return_value="/usr/local/bin/codex"):
            from gobby.llm.codex_executor import CodexExecutor

            return CodexExecutor(auth_mode="subscription")

    @pytest.mark.asyncio
    async def test_run_handles_invalid_json_lines(self, executor_subscription):
        """Run skips invalid JSON lines in CLI output."""
        # Mix of valid JSON and invalid lines
        jsonl_output = "\n".join(
            [
                "This is not JSON",
                json.dumps({"type": "turn.started"}),
                "{ invalid json",
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {"id": "item_1", "type": "agent_message", "text": "Done"},
                    }
                ),
                "",  # Empty line
                json.dumps({"type": "turn.completed"}),
            ]
        )

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(jsonl_output.encode(), b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await executor_subscription.run(
                prompt="Do something",
                tools=[],
                tool_handler=AsyncMock(),
            )

        assert result.status == "success"
        assert result.output == "Done"
        assert result.turns_used == 1

    @pytest.mark.asyncio
    async def test_run_handles_command_with_non_zero_exit_code(self, executor_subscription):
        """Run records command execution with non-zero exit code as error."""
        jsonl_output = "\n".join(
            [
                json.dumps({"type": "turn.started"}),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "item_1",
                            "type": "command_execution",
                            "command": "cat /nonexistent",
                            "aggregated_output": "cat: /nonexistent: No such file or directory",
                            "exit_code": 1,
                            "status": "completed",
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "item_2",
                            "type": "agent_message",
                            "text": "File not found.",
                        },
                    }
                ),
                json.dumps({"type": "turn.completed"}),
            ]
        )

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(jsonl_output.encode(), b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await executor_subscription.run(
                prompt="Cat a file",
                tools=[],
                tool_handler=AsyncMock(),
            )

        assert result.status == "success"
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].tool_name == "bash"
        assert result.tool_calls[0].result.success is False
        assert "No such file or directory" in result.tool_calls[0].result.error

    @pytest.mark.asyncio
    async def test_run_handles_file_not_found_error(self, executor_subscription):
        """Run handles FileNotFoundError when CLI executable is missing."""
        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("codex not found"),
        ):
            result = await executor_subscription.run(
                prompt="Do something",
                tools=[],
                tool_handler=AsyncMock(),
            )

        assert result.status == "error"
        assert "Codex CLI not found" in result.error
        assert result.turns_used == 0

    @pytest.mark.asyncio
    async def test_run_handles_generic_exception(self, executor_subscription):
        """Run handles generic exceptions during CLI execution."""
        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=OSError("Permission denied"),
        ):
            result = await executor_subscription.run(
                prompt="Do something",
                tools=[],
                tool_handler=AsyncMock(),
            )

        assert result.status == "error"
        assert "Permission denied" in result.error

    @pytest.mark.asyncio
    async def test_run_handles_empty_stdout(self, executor_subscription):
        """Run handles empty stdout from CLI."""
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await executor_subscription.run(
                prompt="Do something",
                tools=[],
                tool_handler=AsyncMock(),
            )

        assert result.status == "success"
        assert result.output == ""
        assert result.turns_used == 0

    @pytest.mark.asyncio
    async def test_run_handles_multiple_turns(self, executor_subscription):
        """Run correctly counts multiple turns."""
        jsonl_output = "\n".join(
            [
                json.dumps({"type": "turn.started"}),
                json.dumps({"type": "turn.completed"}),
                json.dumps({"type": "turn.started"}),
                json.dumps({"type": "turn.completed"}),
                json.dumps({"type": "turn.started"}),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {"id": "item_1", "type": "agent_message", "text": "Done"},
                    }
                ),
                json.dumps({"type": "turn.completed"}),
            ]
        )

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(jsonl_output.encode(), b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await executor_subscription.run(
                prompt="Multi-turn task",
                tools=[],
                tool_handler=AsyncMock(),
            )

        assert result.status == "success"
        assert result.turns_used == 3

    @pytest.mark.asyncio
    async def test_run_handles_unknown_item_types(self, executor_subscription):
        """Run ignores unknown item types in JSONL output."""
        jsonl_output = "\n".join(
            [
                json.dumps({"type": "turn.started"}),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {"id": "item_1", "type": "unknown_type", "data": "whatever"},
                    }
                ),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {"id": "item_2", "type": "agent_message", "text": "Done"},
                    }
                ),
                json.dumps({"type": "turn.completed"}),
            ]
        )

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(jsonl_output.encode(), b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await executor_subscription.run(
                prompt="Do something",
                tools=[],
                tool_handler=AsyncMock(),
            )

        assert result.status == "success"
        assert result.output == "Done"
        # Unknown item types should not create tool calls
        assert len(result.tool_calls) == 0

    @pytest.mark.asyncio
    async def test_run_preserves_tool_calls_on_error(self, executor_subscription):
        """Run preserves tool calls even when CLI exits with error."""
        jsonl_output = "\n".join(
            [
                json.dumps({"type": "turn.started"}),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "item_1",
                            "type": "command_execution",
                            "command": "echo hello",
                            "aggregated_output": "hello\n",
                            "exit_code": 0,
                        },
                    }
                ),
            ]
        )

        mock_process = AsyncMock()
        mock_process.returncode = 1  # CLI exits with error
        mock_process.communicate = AsyncMock(
            return_value=(jsonl_output.encode(), b"Session expired")
        )

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await executor_subscription.run(
                prompt="Do something",
                tools=[],
                tool_handler=AsyncMock(),
            )

        assert result.status == "error"
        assert "exited with code 1" in result.error
        # Tool calls should be preserved
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].tool_name == "bash"
