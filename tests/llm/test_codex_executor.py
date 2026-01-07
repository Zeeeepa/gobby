"""Tests for CodexExecutor class."""

import asyncio
import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.llm.executor import ToolResult, ToolSchema


@pytest.fixture
def mock_openai_module():
    """Mock the openai module."""
    mock_openai = MagicMock()
    mock_async_client = MagicMock()
    mock_openai.AsyncOpenAI = MagicMock(return_value=mock_async_client)

    with patch.dict(sys.modules, {"openai": mock_openai}):
        yield mock_openai, mock_async_client


@pytest.fixture
def sample_tools():
    """Create sample tools for testing."""
    return [
        ToolSchema(
            name="create_task",
            description="Create a new task",
            input_schema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                },
                "required": ["title"],
            },
        ),
        ToolSchema(
            name="get_status",
            description="Get task status",
            input_schema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                },
            },
        ),
    ]


class TestCodexExecutorInit:
    """Tests for CodexExecutor initialization."""

    def test_init_with_api_key(self, mock_openai_module):
        """CodexExecutor initializes with API key."""
        mock_openai, mock_client = mock_openai_module

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            from gobby.llm.codex_executor import CodexExecutor

            executor = CodexExecutor(auth_mode="api_key")

            assert executor.provider_name == "codex"
            assert executor.auth_mode == "api_key"
            assert executor.default_model == "gpt-4o"
            mock_openai.AsyncOpenAI.assert_called_with(api_key="test-key")

    def test_init_with_explicit_api_key(self, mock_openai_module):
        """CodexExecutor uses explicit API key over environment."""
        mock_openai, mock_client = mock_openai_module

        from gobby.llm.codex_executor import CodexExecutor

        executor = CodexExecutor(auth_mode="api_key", api_key="explicit-key")

        mock_openai.AsyncOpenAI.assert_called_with(api_key="explicit-key")
        assert executor.auth_mode == "api_key"

    def test_init_with_custom_model(self, mock_openai_module):
        """CodexExecutor accepts custom default model."""
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            from gobby.llm.codex_executor import CodexExecutor

            executor = CodexExecutor(auth_mode="api_key", default_model="gpt-4-turbo")

            assert executor.default_model == "gpt-4-turbo"

    def test_init_without_api_key_raises(self, mock_openai_module):
        """CodexExecutor raises ValueError without API key."""
        with patch.dict("os.environ", {}, clear=True):
            from gobby.llm.codex_executor import CodexExecutor

            with pytest.raises(ValueError, match="API key required"):
                CodexExecutor(auth_mode="api_key")

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

    def test_init_invalid_auth_mode_raises(self, mock_openai_module):
        """CodexExecutor raises ValueError for invalid auth mode."""
        from gobby.llm.codex_executor import CodexExecutor

        with pytest.raises(ValueError, match="Unknown auth_mode"):
            CodexExecutor(auth_mode="invalid")  # type: ignore


class TestCodexExecutorApiKeyMode:
    """Tests for CodexExecutor in api_key mode."""

    @pytest.fixture
    def executor_with_mock_client(self, mock_openai_module):
        """Create executor with mocked OpenAI client."""
        mock_openai, mock_client = mock_openai_module

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            from gobby.llm.codex_executor import CodexExecutor

            executor = CodexExecutor(auth_mode="api_key")
            return executor, mock_client

    def test_convert_tools_to_openai_format(self, executor_with_mock_client, sample_tools):
        """Tools are converted to OpenAI format correctly."""
        executor, _ = executor_with_mock_client

        openai_tools = executor._convert_tools_to_openai_format(sample_tools)

        assert len(openai_tools) == 2
        assert openai_tools[0]["type"] == "function"
        assert openai_tools[0]["function"]["name"] == "create_task"
        assert openai_tools[0]["function"]["description"] == "Create a new task"
        assert openai_tools[0]["function"]["parameters"]["type"] == "object"

    @pytest.mark.asyncio
    async def test_run_simple_response(self, executor_with_mock_client, sample_tools):
        """Run completes successfully with simple text response."""
        executor, mock_client = executor_with_mock_client

        # Mock response with no tool calls
        mock_message = MagicMock()
        mock_message.content = "Task completed successfully"
        mock_message.tool_calls = None
        mock_message.model_dump.return_value = {
            "role": "assistant",
            "content": "Task completed successfully",
        }

        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_choice.finish_reason = "stop"

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_client.chat = MagicMock()
        mock_client.chat.completions = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        tool_handler = AsyncMock()

        result = await executor.run(
            prompt="Do something",
            tools=sample_tools,
            tool_handler=tool_handler,
        )

        assert result.status == "success"
        assert result.output == "Task completed successfully"
        assert result.turns_used == 1
        assert len(result.tool_calls) == 0
        tool_handler.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_with_tool_calls(self, executor_with_mock_client, sample_tools):
        """Run handles tool calls correctly."""
        executor, mock_client = executor_with_mock_client

        # First response with tool call
        mock_tool_call = MagicMock()
        mock_tool_call.id = "call_123"
        mock_tool_call.function.name = "create_task"
        mock_tool_call.function.arguments = '{"title": "New Task"}'

        mock_message1 = MagicMock()
        mock_message1.content = None
        mock_message1.tool_calls = [mock_tool_call]
        mock_message1.model_dump.return_value = {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": "call_123", "function": {"name": "create_task"}}],
        }

        mock_choice1 = MagicMock()
        mock_choice1.message = mock_message1
        mock_choice1.finish_reason = "tool_calls"

        mock_response1 = MagicMock()
        mock_response1.choices = [mock_choice1]

        # Second response after tool result
        mock_message2 = MagicMock()
        mock_message2.content = "Created task successfully"
        mock_message2.tool_calls = None
        mock_message2.model_dump.return_value = {
            "role": "assistant",
            "content": "Created task successfully",
        }

        mock_choice2 = MagicMock()
        mock_choice2.message = mock_message2
        mock_choice2.finish_reason = "stop"

        mock_response2 = MagicMock()
        mock_response2.choices = [mock_choice2]

        mock_client.chat = MagicMock()
        mock_client.chat.completions = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=[mock_response1, mock_response2]
        )

        tool_handler = AsyncMock(
            return_value=ToolResult(
                tool_name="create_task",
                success=True,
                result={"id": "task-123"},
            )
        )

        result = await executor.run(
            prompt="Create a task",
            tools=sample_tools,
            tool_handler=tool_handler,
        )

        assert result.status == "success"
        assert result.output == "Created task successfully"
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].tool_name == "create_task"
        assert result.tool_calls[0].arguments == {"title": "New Task"}
        tool_handler.assert_called_once_with("create_task", {"title": "New Task"})

    @pytest.mark.asyncio
    async def test_run_timeout(self, executor_with_mock_client, sample_tools):
        """Run returns timeout status when execution times out."""
        executor, mock_client = executor_with_mock_client

        # Mock slow response
        async def slow_response(*args, **kwargs):
            await asyncio.sleep(10)
            return MagicMock()

        mock_client.chat = MagicMock()
        mock_client.chat.completions = MagicMock()
        mock_client.chat.completions.create = slow_response

        result = await executor.run(
            prompt="Do something",
            tools=sample_tools,
            tool_handler=AsyncMock(),
            timeout=0.1,
        )

        assert result.status == "timeout"
        assert "timed out" in result.error

    @pytest.mark.asyncio
    async def test_run_api_error(self, executor_with_mock_client, sample_tools):
        """Run handles API errors gracefully."""
        executor, mock_client = executor_with_mock_client

        mock_client.chat = MagicMock()
        mock_client.chat.completions = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=Exception("API rate limit exceeded")
        )

        result = await executor.run(
            prompt="Do something",
            tools=sample_tools,
            tool_handler=AsyncMock(),
        )

        assert result.status == "error"
        assert "API rate limit exceeded" in result.error


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

    def test_provider_name_api_key_mode(self, mock_openai_module):
        """Provider name is 'codex' in api_key mode."""
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            from gobby.llm.codex_executor import CodexExecutor

            executor = CodexExecutor(auth_mode="api_key")
            assert executor.provider_name == "codex"

    def test_provider_name_subscription_mode(self):
        """Provider name is 'codex' in subscription mode."""
        with patch("shutil.which", return_value="/usr/local/bin/codex"):
            from gobby.llm.codex_executor import CodexExecutor

            executor = CodexExecutor(auth_mode="subscription")
            assert executor.provider_name == "codex"
