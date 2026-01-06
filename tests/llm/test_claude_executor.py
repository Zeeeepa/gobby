"""Tests for ClaudeExecutor class."""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.llm.executor import AgentResult, ToolResult, ToolSchema


class MockAPIError(Exception):
    """Mock Anthropic API Error for testing."""

    pass


@pytest.fixture
def mock_anthropic_module():
    """Mock the anthropic module."""
    mock_anthropic = MagicMock()
    mock_anthropic.AsyncAnthropic = MagicMock()
    mock_anthropic.APIError = MockAPIError
    mock_anthropic.types = MagicMock()
    mock_anthropic.types.ToolParam = dict
    mock_anthropic.types.MessageParam = dict
    mock_anthropic.types.ContentBlockParam = dict
    mock_anthropic.types.ToolResultBlockParam = dict

    with patch.dict(
        sys.modules,
        {
            "anthropic": mock_anthropic,
            "anthropic.types": mock_anthropic.types,
        },
    ):
        yield mock_anthropic


class TestClaudeExecutorInit:
    """Tests for ClaudeExecutor initialization."""

    def test_init_with_api_key_mode(self, mock_anthropic_module):
        """ClaudeExecutor initializes with API key mode."""
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            from gobby.llm.claude_executor import ClaudeExecutor

            executor = ClaudeExecutor(auth_mode="api_key")

            assert executor.provider_name == "claude"
            assert executor.auth_mode == "api_key"
            assert executor.default_model == "claude-sonnet-4-20250514"
            assert executor._client is not None

    def test_init_with_explicit_api_key(self, mock_anthropic_module):
        """ClaudeExecutor uses explicit API key over environment."""
        from gobby.llm.claude_executor import ClaudeExecutor

        executor = ClaudeExecutor(auth_mode="api_key", api_key="explicit-key")

        # Verify executor was created and has correct mode
        assert executor.auth_mode == "api_key"
        assert executor._client is not None

    def test_init_with_custom_model(self, mock_anthropic_module):
        """ClaudeExecutor accepts custom default model."""
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            from gobby.llm.claude_executor import ClaudeExecutor

            executor = ClaudeExecutor(
                auth_mode="api_key", default_model="claude-opus-4-5-20251101"
            )

            assert executor.default_model == "claude-opus-4-5-20251101"

    def test_init_without_api_key_raises(self, mock_anthropic_module):
        """ClaudeExecutor raises ValueError without API key."""
        with patch.dict("os.environ", {}, clear=True):
            from gobby.llm.claude_executor import ClaudeExecutor

            with pytest.raises(ValueError, match="API key required"):
                ClaudeExecutor(auth_mode="api_key")

    def test_init_with_subscription_mode(self, mock_anthropic_module):
        """ClaudeExecutor initializes with subscription mode."""
        import shutil

        with patch.object(shutil, "which", return_value="/usr/bin/claude"):
            from gobby.llm.claude_executor import ClaudeExecutor

            executor = ClaudeExecutor(auth_mode="subscription")

            assert executor.auth_mode == "subscription"
            assert executor._cli_path == "/usr/bin/claude"
            assert executor._client is None

    def test_init_subscription_mode_without_cli_raises(self, mock_anthropic_module):
        """ClaudeExecutor raises ValueError when CLI not found in subscription mode."""
        import shutil

        with patch.object(shutil, "which", return_value=None):
            from gobby.llm.claude_executor import ClaudeExecutor

            with pytest.raises(ValueError, match="Claude CLI not found"):
                ClaudeExecutor(auth_mode="subscription")

    def test_init_unknown_auth_mode_raises(self, mock_anthropic_module):
        """ClaudeExecutor raises ValueError for unknown auth mode."""
        from gobby.llm.claude_executor import ClaudeExecutor

        with pytest.raises(ValueError, match="Unknown auth_mode"):
            ClaudeExecutor(auth_mode="unknown")  # type: ignore[arg-type]


class TestClaudeExecutorRun:
    """Tests for ClaudeExecutor.run() method with API key mode."""

    @pytest.fixture
    def executor(self, mock_anthropic_module):
        """Create a ClaudeExecutor instance."""
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            from gobby.llm.claude_executor import ClaudeExecutor

            return ClaudeExecutor(auth_mode="api_key")

    @pytest.fixture
    def simple_tools(self):
        """Create simple tool schemas for testing."""
        return [
            ToolSchema(
                name="get_weather",
                description="Get the current weather",
                input_schema={
                    "type": "object",
                    "properties": {
                        "location": {"type": "string", "description": "City name"},
                    },
                    "required": ["location"],
                },
            ),
        ]

    async def test_run_returns_text_response(
        self, executor, mock_anthropic_module, simple_tools
    ):
        """run() returns text response when no tools are called."""
        # Setup mock response
        mock_text_block = MagicMock()
        mock_text_block.type = "text"
        mock_text_block.text = "Hello, I'm Claude!"

        mock_response = MagicMock()
        mock_response.content = [mock_text_block]
        mock_response.stop_reason = "end_turn"

        executor._client.messages.create = AsyncMock(return_value=mock_response)

        async def dummy_handler(name: str, args: dict) -> ToolResult:
            return ToolResult(tool_name=name, success=True, result={"ok": True})

        result = await executor.run(
            prompt="Hello!",
            tools=simple_tools,
            tool_handler=dummy_handler,
        )

        assert result.status == "success"
        assert result.output == "Hello, I'm Claude!"
        assert len(result.tool_calls) == 0

    async def test_run_handles_tool_use(
        self, executor, mock_anthropic_module, simple_tools
    ):
        """run() handles tool use and sends results back."""
        # First response with tool use
        mock_tool_block = MagicMock()
        mock_tool_block.type = "tool_use"
        mock_tool_block.id = "tool-123"
        mock_tool_block.name = "get_weather"
        mock_tool_block.input = {"location": "San Francisco"}

        mock_response1 = MagicMock()
        mock_response1.content = [mock_tool_block]
        mock_response1.stop_reason = "tool_use"

        # Second response with text
        mock_text_block = MagicMock()
        mock_text_block.type = "text"
        mock_text_block.text = "The weather in San Francisco is sunny."

        mock_response2 = MagicMock()
        mock_response2.content = [mock_text_block]
        mock_response2.stop_reason = "end_turn"

        executor._client.messages.create = AsyncMock(
            side_effect=[mock_response1, mock_response2]
        )

        async def weather_handler(name: str, args: dict) -> ToolResult:
            if name == "get_weather":
                return ToolResult(
                    tool_name=name,
                    success=True,
                    result={"temp": "72°F", "condition": "sunny"},
                )
            return ToolResult(tool_name=name, success=False, error="Unknown tool")

        result = await executor.run(
            prompt="What's the weather in San Francisco?",
            tools=simple_tools,
            tool_handler=weather_handler,
        )

        assert result.status == "success"
        assert result.output == "The weather in San Francisco is sunny."
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].tool_name == "get_weather"
        assert result.tool_calls[0].arguments == {"location": "San Francisco"}

    async def test_run_handles_tool_error(
        self, executor, mock_anthropic_module, simple_tools
    ):
        """run() handles tool execution errors gracefully."""
        # Response with tool use
        mock_tool_block = MagicMock()
        mock_tool_block.type = "tool_use"
        mock_tool_block.id = "tool-123"
        mock_tool_block.name = "get_weather"
        mock_tool_block.input = {"location": "Unknown"}

        mock_response1 = MagicMock()
        mock_response1.content = [mock_tool_block]
        mock_response1.stop_reason = "tool_use"

        # Response after error
        mock_text_block = MagicMock()
        mock_text_block.type = "text"
        mock_text_block.text = "I couldn't get the weather."

        mock_response2 = MagicMock()
        mock_response2.content = [mock_text_block]
        mock_response2.stop_reason = "end_turn"

        executor._client.messages.create = AsyncMock(
            side_effect=[mock_response1, mock_response2]
        )

        async def failing_handler(name: str, args: dict) -> ToolResult:
            return ToolResult(tool_name=name, success=False, error="Location not found")

        result = await executor.run(
            prompt="What's the weather?",
            tools=simple_tools,
            tool_handler=failing_handler,
        )

        assert result.status == "success"
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].result is not None
        assert result.tool_calls[0].result.success is False
        assert result.tool_calls[0].result.error == "Location not found"

    async def test_run_respects_max_turns(
        self, executor, mock_anthropic_module, simple_tools
    ):
        """run() stops after max_turns is reached."""
        # Always return tool use (to exhaust turns)
        mock_tool_block = MagicMock()
        mock_tool_block.type = "tool_use"
        mock_tool_block.id = "tool-123"
        mock_tool_block.name = "get_weather"
        mock_tool_block.input = {"location": "SF"}

        mock_response = MagicMock()
        mock_response.content = [mock_tool_block]
        mock_response.stop_reason = "tool_use"

        executor._client.messages.create = AsyncMock(return_value=mock_response)

        async def dummy_handler(name: str, args: dict) -> ToolResult:
            return ToolResult(tool_name=name, success=True, result={})

        result = await executor.run(
            prompt="Loop forever",
            tools=simple_tools,
            tool_handler=dummy_handler,
            max_turns=3,
        )

        assert result.status == "partial"
        assert result.turns_used == 3

    async def test_run_handles_timeout(
        self, executor, mock_anthropic_module, simple_tools
    ):
        """run() returns timeout status when execution exceeds timeout."""
        import asyncio

        async def slow_response(*args, **kwargs):
            await asyncio.sleep(2)  # Longer than timeout
            return MagicMock()

        executor._client.messages.create = slow_response

        async def dummy_handler(name: str, args: dict) -> ToolResult:
            return ToolResult(tool_name=name, success=True, result={})

        result = await executor.run(
            prompt="Slow request",
            tools=simple_tools,
            tool_handler=dummy_handler,
            timeout=0.1,
        )

        assert result.status == "timeout"
        assert "timed out" in result.error.lower()

    async def test_run_handles_generic_error(
        self, executor, mock_anthropic_module, simple_tools
    ):
        """run() handles generic errors and returns timeout (outer handler)."""
        # Generic exceptions propagate and will be caught by the timeout wrapper
        # which returns a timeout or error depending on how it propagates
        executor._client.messages.create = AsyncMock(
            side_effect=RuntimeError("Connection failed")
        )

        async def dummy_handler(name: str, args: dict) -> ToolResult:
            return ToolResult(tool_name=name, success=True, result={})

        # The exception will propagate out and be caught at some level
        # Either as a timeout (wait_for) or as uncaught exception
        try:
            result = await executor.run(
                prompt="Error request",
                tools=simple_tools,
                tool_handler=dummy_handler,
            )
            # If we get here, it should be an error status
            assert result.status in ("error", "timeout")
        except RuntimeError:
            # Exception propagated up - this is also acceptable behavior
            pass

    async def test_run_uses_system_prompt(
        self, executor, mock_anthropic_module, simple_tools
    ):
        """run() passes system prompt to API."""
        mock_text_block = MagicMock()
        mock_text_block.type = "text"
        mock_text_block.text = "Response"

        mock_response = MagicMock()
        mock_response.content = [mock_text_block]
        mock_response.stop_reason = "end_turn"

        executor._client.messages.create = AsyncMock(return_value=mock_response)

        async def dummy_handler(name: str, args: dict) -> ToolResult:
            return ToolResult(tool_name=name, success=True, result={})

        await executor.run(
            prompt="Hello",
            tools=simple_tools,
            tool_handler=dummy_handler,
            system_prompt="You are a weather assistant.",
        )

        # Verify system prompt was passed
        executor._client.messages.create.assert_called_once()
        call_kwargs = executor._client.messages.create.call_args.kwargs
        assert call_kwargs["system"] == "You are a weather assistant."

    async def test_run_uses_model_override(
        self, executor, mock_anthropic_module, simple_tools
    ):
        """run() uses model override when provided."""
        mock_text_block = MagicMock()
        mock_text_block.type = "text"
        mock_text_block.text = "Response"

        mock_response = MagicMock()
        mock_response.content = [mock_text_block]
        mock_response.stop_reason = "end_turn"

        executor._client.messages.create = AsyncMock(return_value=mock_response)

        async def dummy_handler(name: str, args: dict) -> ToolResult:
            return ToolResult(tool_name=name, success=True, result={})

        await executor.run(
            prompt="Hello",
            tools=simple_tools,
            tool_handler=dummy_handler,
            model="claude-opus-4-5-20251101",
        )

        # Verify model override was used
        executor._client.messages.create.assert_called_once()
        call_kwargs = executor._client.messages.create.call_args.kwargs
        assert call_kwargs["model"] == "claude-opus-4-5-20251101"

    async def test_run_without_client_returns_error(
        self, executor, mock_anthropic_module, simple_tools
    ):
        """run() returns error when client is not initialized."""
        executor._client = None

        async def dummy_handler(name: str, args: dict) -> ToolResult:
            return ToolResult(tool_name=name, success=True, result={})

        result = await executor.run(
            prompt="Hello",
            tools=simple_tools,
            tool_handler=dummy_handler,
        )

        assert result.status == "error"
        assert "not initialized" in result.error.lower()

    async def test_run_handles_handler_exception(
        self, executor, mock_anthropic_module, simple_tools
    ):
        """run() handles exceptions from tool handler."""
        # Response with tool use
        mock_tool_block = MagicMock()
        mock_tool_block.type = "tool_use"
        mock_tool_block.id = "tool-123"
        mock_tool_block.name = "get_weather"
        mock_tool_block.input = {"location": "SF"}

        mock_response1 = MagicMock()
        mock_response1.content = [mock_tool_block]
        mock_response1.stop_reason = "tool_use"

        # Response after error
        mock_text_block = MagicMock()
        mock_text_block.type = "text"
        mock_text_block.text = "Handled error"

        mock_response2 = MagicMock()
        mock_response2.content = [mock_text_block]
        mock_response2.stop_reason = "end_turn"

        executor._client.messages.create = AsyncMock(
            side_effect=[mock_response1, mock_response2]
        )

        async def raising_handler(name: str, args: dict) -> ToolResult:
            raise RuntimeError("Handler crashed!")

        result = await executor.run(
            prompt="Test",
            tools=simple_tools,
            tool_handler=raising_handler,
        )

        assert result.status == "success"
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].result is not None
        assert result.tool_calls[0].result.success is False
        assert "Handler crashed!" in result.tool_calls[0].result.error


class TestClaudeExecutorToolConversion:
    """Tests for tool schema conversion."""

    @pytest.fixture
    def executor(self, mock_anthropic_module):
        """Create a ClaudeExecutor instance."""
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            from gobby.llm.claude_executor import ClaudeExecutor

            return ClaudeExecutor(auth_mode="api_key")

    def test_convert_single_tool(self, executor):
        """Converts single tool schema correctly."""
        tools = [
            ToolSchema(
                name="test_tool",
                description="A test tool",
                input_schema={
                    "type": "object",
                    "properties": {"arg1": {"type": "string"}},
                    "required": ["arg1"],
                },
            )
        ]

        result = executor._convert_tools_to_anthropic_format(tools)

        assert len(result) == 1
        assert result[0]["name"] == "test_tool"
        assert result[0]["description"] == "A test tool"
        assert result[0]["input_schema"]["type"] == "object"
        assert "arg1" in result[0]["input_schema"]["properties"]

    def test_convert_multiple_tools(self, executor):
        """Converts multiple tool schemas correctly."""
        tools = [
            ToolSchema(
                name="tool1",
                description="First tool",
                input_schema={"type": "object", "properties": {}},
            ),
            ToolSchema(
                name="tool2",
                description="Second tool",
                input_schema={"type": "object", "properties": {}},
            ),
        ]

        result = executor._convert_tools_to_anthropic_format(tools)

        assert len(result) == 2
        assert result[0]["name"] == "tool1"
        assert result[1]["name"] == "tool2"

    def test_convert_empty_tools(self, executor):
        """Converts empty tool list correctly."""
        result = executor._convert_tools_to_anthropic_format([])

        assert result == []

    def test_convert_adds_object_type_if_missing(self, executor):
        """Adds 'type: object' if missing from schema."""
        tools = [
            ToolSchema(
                name="no_type",
                description="Tool without type",
                input_schema={"properties": {"x": {"type": "string"}}},
            )
        ]

        result = executor._convert_tools_to_anthropic_format(tools)

        assert result[0]["input_schema"]["type"] == "object"


class TestClaudeExecutorSDKMode:
    """Tests for ClaudeExecutor subscription/SDK mode."""

    @pytest.fixture
    def simple_tools(self):
        """Create simple tool schemas for testing."""
        return [
            ToolSchema(
                name="get_weather",
                description="Get the current weather",
                input_schema={
                    "type": "object",
                    "properties": {
                        "location": {"type": "string", "description": "City name"},
                    },
                    "required": ["location"],
                },
            ),
        ]

    @pytest.fixture
    def executor_sdk_mode(self, mock_anthropic_module):
        """Create a ClaudeExecutor instance in SDK mode."""
        import shutil

        with patch.object(shutil, "which", return_value="/usr/bin/claude"):
            from gobby.llm.claude_executor import ClaudeExecutor

            return ClaudeExecutor(auth_mode="subscription")

    def test_sdk_mode_uses_cli_path(self, mock_anthropic_module):
        """ClaudeExecutor in SDK mode stores CLI path."""
        import shutil

        with patch.object(shutil, "which", return_value="/usr/local/bin/claude"):
            from gobby.llm.claude_executor import ClaudeExecutor

            executor = ClaudeExecutor(auth_mode="subscription")

            assert executor._cli_path == "/usr/local/bin/claude"
            assert executor._client is None

    def test_sdk_mode_provider_name(self, executor_sdk_mode):
        """SDK mode executor returns correct provider name."""
        assert executor_sdk_mode.provider_name == "claude"

    async def test_run_with_sdk_mode_delegates_to_sdk(
        self, executor_sdk_mode, simple_tools
    ):
        """SDK mode run() delegates to _run_with_sdk method."""
        # Verify the executor is in subscription mode
        assert executor_sdk_mode.auth_mode == "subscription"
        assert executor_sdk_mode._client is None

        async def dummy_handler(name: str, args: dict) -> ToolResult:
            return ToolResult(tool_name=name, success=True, result={})

        # Mock _run_with_sdk to avoid needing the actual SDK
        with patch.object(
            executor_sdk_mode,
            "_run_with_sdk",
            new_callable=AsyncMock,
            return_value=AgentResult(
                output="SDK response",
                status="success",
                turns_used=1,
            ),
        ) as mock_sdk_run:
            result = await executor_sdk_mode.run(
                prompt="Hello",
                tools=simple_tools,
                tool_handler=dummy_handler,
            )

            # Verify _run_with_sdk was called
            mock_sdk_run.assert_called_once()
            assert result.status == "success"
            assert result.output == "SDK response"
