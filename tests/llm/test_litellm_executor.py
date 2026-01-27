"""Tests for LiteLLMExecutor class."""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.llm.executor import ToolResult, ToolSchema


@pytest.fixture
def mock_litellm_module():
    """Mock the litellm module."""
    mock_litellm = MagicMock()
    mock_litellm.acompletion = AsyncMock()
    mock_litellm.completion_cost = MagicMock(return_value=0.001)

    with patch.dict(sys.modules, {"litellm": mock_litellm}):
        yield mock_litellm


class TestGetLitellmModel:
    """Tests for get_litellm_model function."""

    def test_claude_provider(self, mock_litellm_module):
        """Test Claude provider gets anthropic prefix."""
        from gobby.llm.litellm_executor import get_litellm_model

        assert (
            get_litellm_model("claude-sonnet-4-5", provider="claude")
            == "anthropic/claude-sonnet-4-5"
        )
        assert (
            get_litellm_model("claude-haiku-4-5", provider="claude") == "anthropic/claude-haiku-4-5"
        )

    def test_gemini_api_key_mode(self, mock_litellm_module):
        """Test Gemini with api_key gets gemini prefix."""
        from gobby.llm.litellm_executor import get_litellm_model

        result = get_litellm_model("gemini-2.0-flash", provider="gemini", auth_mode="api_key")
        assert result == "gemini/gemini-2.0-flash"

    def test_gemini_adc_mode(self, mock_litellm_module):
        """Test Gemini with adc gets vertex_ai prefix."""
        from gobby.llm.litellm_executor import get_litellm_model

        result = get_litellm_model("gemini-2.0-flash", provider="gemini", auth_mode="adc")
        assert result == "vertex_ai/gemini-2.0-flash"

    def test_codex_provider(self, mock_litellm_module):
        """Test Codex/OpenAI provider gets no prefix."""
        from gobby.llm.litellm_executor import get_litellm_model

        assert get_litellm_model("gpt-4o", provider="codex") == "gpt-4o"
        assert get_litellm_model("gpt-4o-mini", provider="openai") == "gpt-4o-mini"

    def test_already_prefixed_model(self, mock_litellm_module):
        """Test models with existing prefix are returned as-is."""
        from gobby.llm.litellm_executor import get_litellm_model

        assert get_litellm_model("anthropic/claude-3", provider="claude") == "anthropic/claude-3"
        assert get_litellm_model("gemini/gemini-pro", provider="gemini") == "gemini/gemini-pro"

    def test_no_provider_returns_as_is(self, mock_litellm_module):
        """Test no provider returns model as-is."""
        from gobby.llm.litellm_executor import get_litellm_model

        assert get_litellm_model("gpt-4o") == "gpt-4o"
        assert get_litellm_model("custom-model", provider=None) == "custom-model"


class TestSetupProviderEnv:
    """Tests for setup_provider_env function."""

    def test_gemini_adc_sets_vertex_env(self, mock_litellm_module):
        """Test Gemini ADC mode sets VERTEXAI env vars from GCP env."""
        from gobby.llm.litellm_executor import setup_provider_env

        with patch.dict("os.environ", {"GOOGLE_CLOUD_PROJECT": "my-project"}, clear=True):
            setup_provider_env("gemini", "adc")

            import os

            assert os.environ.get("VERTEXAI_PROJECT") == "my-project"
            assert "VERTEXAI_LOCATION" in os.environ

    def test_non_gemini_does_nothing(self, mock_litellm_module):
        """Test non-Gemini providers don't modify env."""
        from gobby.llm.litellm_executor import setup_provider_env

        with patch.dict("os.environ", {}, clear=True):
            setup_provider_env("claude", "api_key")

            import os

            assert "VERTEXAI_PROJECT" not in os.environ


class TestLiteLLMExecutorInit:
    """Tests for LiteLLMExecutor initialization."""

    def test_init_with_defaults(self, mock_litellm_module):
        """LiteLLMExecutor initializes with default settings."""
        from gobby.llm.litellm_executor import LiteLLMExecutor

        executor = LiteLLMExecutor()

        assert executor.provider_name == "litellm"
        assert executor.default_model == "gpt-4o-mini"
        assert executor.api_base is None

    def test_init_with_custom_model(self, mock_litellm_module):
        """LiteLLMExecutor uses custom default model."""
        from gobby.llm.litellm_executor import LiteLLMExecutor

        executor = LiteLLMExecutor(default_model="claude-3-sonnet-20240229")

        assert executor.default_model == "claude-3-sonnet-20240229"

    def test_init_with_api_base(self, mock_litellm_module):
        """LiteLLMExecutor accepts custom API base."""
        from gobby.llm.litellm_executor import LiteLLMExecutor

        executor = LiteLLMExecutor(api_base="https://openrouter.ai/api/v1")

        assert executor.api_base == "https://openrouter.ai/api/v1"

    def test_init_with_api_keys(self, mock_litellm_module):
        """LiteLLMExecutor sets API keys in environment."""
        with patch.dict("os.environ", {}, clear=True):
            import os

            from gobby.llm.litellm_executor import LiteLLMExecutor

            executor = LiteLLMExecutor(
                api_keys={"OPENAI_API_KEY": "sk-test", "ANTHROPIC_API_KEY": "sk-ant"}
            )

            assert executor._litellm is not None
            assert os.environ.get("OPENAI_API_KEY") == "sk-test"
            assert os.environ.get("ANTHROPIC_API_KEY") == "sk-ant"

    def test_init_with_provider_and_auth_mode(self, mock_litellm_module):
        """LiteLLMExecutor accepts provider and auth_mode parameters."""
        from gobby.llm.litellm_executor import LiteLLMExecutor

        executor = LiteLLMExecutor(
            default_model="claude-sonnet-4-5",
            provider="claude",
            auth_mode="api_key",
        )

        assert executor.provider == "claude"
        assert executor.auth_mode == "api_key"
        assert executor.default_model == "claude-sonnet-4-5"

    def test_init_gemini_adc_mode(self, mock_litellm_module):
        """LiteLLMExecutor with Gemini ADC sets up env vars."""
        with patch.dict("os.environ", {"GOOGLE_CLOUD_PROJECT": "test-project"}, clear=True):
            from gobby.llm.litellm_executor import LiteLLMExecutor

            executor = LiteLLMExecutor(
                default_model="gemini-2.0-flash",
                provider="gemini",
                auth_mode="adc",
            )

            assert executor.provider == "gemini"
            assert executor.auth_mode == "adc"

    def test_init_skips_existing_env_keys(self, mock_litellm_module):
        """LiteLLMExecutor doesn't override existing environment keys."""
        with patch.dict("os.environ", {"OPENAI_API_KEY": "existing-key"}):
            import os

            from gobby.llm.litellm_executor import LiteLLMExecutor

            LiteLLMExecutor(api_keys={"OPENAI_API_KEY": "new-key"})

            # Should keep existing key
            assert os.environ.get("OPENAI_API_KEY") == "existing-key"

    def test_init_missing_package_raises(self):
        """LiteLLMExecutor raises ImportError when package not installed."""
        with patch.dict(sys.modules, {"litellm": None}):
            import importlib

            with pytest.raises((ImportError, ModuleNotFoundError, TypeError)):
                import gobby.llm.litellm_executor as module

                importlib.reload(module)
                module.LiteLLMExecutor()


class TestLiteLLMExecutorRun:
    """Tests for LiteLLMExecutor.run() method."""

    @pytest.fixture
    def executor(self, mock_litellm_module):
        """Create a LiteLLMExecutor instance."""
        from gobby.llm.litellm_executor import LiteLLMExecutor

        return LiteLLMExecutor()

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

    async def test_run_returns_text_response(self, executor, mock_litellm_module, simple_tools):
        """run() returns text response when no tools are called."""
        # Setup mock response with usage info
        mock_message = MagicMock()
        mock_message.content = "Hello, I'm an AI!"
        mock_message.tool_calls = None

        mock_choice = MagicMock()
        mock_choice.message = mock_message

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 10
        mock_usage.completion_tokens = 5

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage

        mock_litellm_module.acompletion = AsyncMock(return_value=mock_response)
        mock_litellm_module.completion_cost = MagicMock(return_value=0.001)

        async def dummy_handler(name: str, args: dict) -> ToolResult:
            return ToolResult(tool_name=name, success=True, result={"ok": True})

        result = await executor.run(
            prompt="Hello!",
            tools=simple_tools,
            tool_handler=dummy_handler,
        )

        assert result.status == "success"
        assert result.output == "Hello, I'm an AI!"
        assert len(result.tool_calls) == 0
        # Verify cost tracking
        assert result.cost_info is not None
        assert result.cost_info.prompt_tokens == 10
        assert result.cost_info.completion_tokens == 5
        assert result.cost_info.total_cost == 0.001

    async def test_run_tracks_cost_across_turns(self, executor, mock_litellm_module, simple_tools):
        """run() accumulates cost across multiple turns."""
        # First response with function call
        mock_tool_call = MagicMock()
        mock_tool_call.id = "call-123"
        mock_tool_call.function.name = "get_weather"
        mock_tool_call.function.arguments = '{"location": "SF"}'

        mock_message1 = MagicMock()
        mock_message1.content = ""
        mock_message1.tool_calls = [mock_tool_call]
        mock_message1.model_dump = MagicMock(return_value={"role": "assistant"})

        mock_usage1 = MagicMock()
        mock_usage1.prompt_tokens = 100
        mock_usage1.completion_tokens = 20

        mock_response1 = MagicMock()
        mock_response1.choices = [MagicMock(message=mock_message1)]
        mock_response1.usage = mock_usage1

        # Second response with text
        mock_message2 = MagicMock()
        mock_message2.content = "Done"
        mock_message2.tool_calls = None

        mock_usage2 = MagicMock()
        mock_usage2.prompt_tokens = 150
        mock_usage2.completion_tokens = 10

        mock_response2 = MagicMock()
        mock_response2.choices = [MagicMock(message=mock_message2)]
        mock_response2.usage = mock_usage2

        mock_litellm_module.acompletion = AsyncMock(side_effect=[mock_response1, mock_response2])
        mock_litellm_module.completion_cost = MagicMock(side_effect=[0.002, 0.003])

        async def dummy_handler(name: str, args: dict) -> ToolResult:
            return ToolResult(tool_name=name, success=True, result={})

        result = await executor.run(
            prompt="Test",
            tools=simple_tools,
            tool_handler=dummy_handler,
        )

        # Cost should be accumulated across both turns
        assert result.cost_info is not None
        assert result.cost_info.prompt_tokens == 250  # 100 + 150
        assert result.cost_info.completion_tokens == 30  # 20 + 10
        assert result.cost_info.total_cost == 0.005  # 0.002 + 0.003

    async def test_run_applies_model_routing(self, mock_litellm_module, simple_tools):
        """run() applies model routing based on provider/auth_mode."""
        from gobby.llm.litellm_executor import LiteLLMExecutor

        executor = LiteLLMExecutor(
            default_model="gemini-2.0-flash",
            provider="gemini",
            auth_mode="adc",
        )

        mock_message = MagicMock()
        mock_message.content = "Response"
        mock_message.tool_calls = None

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=mock_message)]
        mock_response.usage = None

        mock_litellm_module.acompletion = AsyncMock(return_value=mock_response)

        async def dummy_handler(name: str, args: dict) -> ToolResult:
            return ToolResult(tool_name=name, success=True, result={})

        await executor.run(
            prompt="Test",
            tools=simple_tools,
            tool_handler=dummy_handler,
        )

        # Verify model was routed to vertex_ai prefix for ADC mode
        call_kwargs = mock_litellm_module.acompletion.call_args.kwargs
        assert call_kwargs["model"] == "vertex_ai/gemini-2.0-flash"

    async def test_run_handles_function_call(self, executor, mock_litellm_module, simple_tools):
        """run() handles function calls and sends results back."""
        # First response with function call
        mock_tool_call = MagicMock()
        mock_tool_call.id = "call-123"
        mock_tool_call.function.name = "get_weather"
        mock_tool_call.function.arguments = '{"location": "San Francisco"}'

        mock_message1 = MagicMock()
        mock_message1.content = ""
        mock_message1.tool_calls = [mock_tool_call]
        mock_message1.model_dump = MagicMock(
            return_value={
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "call-123", "function": {"name": "get_weather"}}],
            }
        )

        mock_choice1 = MagicMock()
        mock_choice1.message = mock_message1

        mock_response1 = MagicMock()
        mock_response1.choices = [mock_choice1]

        # Second response with text (after function result)
        mock_message2 = MagicMock()
        mock_message2.content = "The weather in San Francisco is sunny."
        mock_message2.tool_calls = None

        mock_choice2 = MagicMock()
        mock_choice2.message = mock_message2

        mock_response2 = MagicMock()
        mock_response2.choices = [mock_choice2]

        mock_litellm_module.acompletion = AsyncMock(side_effect=[mock_response1, mock_response2])

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

    async def test_run_handles_tool_error(self, executor, mock_litellm_module, simple_tools):
        """run() handles tool execution errors gracefully."""
        # Response with function call
        mock_tool_call = MagicMock()
        mock_tool_call.id = "call-123"
        mock_tool_call.function.name = "get_weather"
        mock_tool_call.function.arguments = '{"location": "Unknown"}'

        mock_message1 = MagicMock()
        mock_message1.content = ""
        mock_message1.tool_calls = [mock_tool_call]
        mock_message1.model_dump = MagicMock(return_value={"role": "assistant"})

        mock_choice1 = MagicMock()
        mock_choice1.message = mock_message1

        mock_response1 = MagicMock()
        mock_response1.choices = [mock_choice1]

        # Response after error
        mock_message2 = MagicMock()
        mock_message2.content = "I couldn't get the weather."
        mock_message2.tool_calls = None

        mock_choice2 = MagicMock()
        mock_choice2.message = mock_message2

        mock_response2 = MagicMock()
        mock_response2.choices = [mock_choice2]

        mock_litellm_module.acompletion = AsyncMock(side_effect=[mock_response1, mock_response2])

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

    async def test_run_respects_max_turns(self, executor, mock_litellm_module, simple_tools):
        """run() stops after max_turns is reached."""
        # Always return function call (to exhaust turns)
        mock_tool_call = MagicMock()
        mock_tool_call.id = "call-123"
        mock_tool_call.function.name = "get_weather"
        mock_tool_call.function.arguments = '{"location": "SF"}'

        mock_message = MagicMock()
        mock_message.content = ""
        mock_message.tool_calls = [mock_tool_call]
        mock_message.model_dump = MagicMock(return_value={"role": "assistant"})

        mock_choice = MagicMock()
        mock_choice.message = mock_message

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_litellm_module.acompletion = AsyncMock(return_value=mock_response)

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

    async def test_run_handles_timeout(self, executor, mock_litellm_module, simple_tools):
        """run() returns timeout status when execution exceeds timeout."""
        import asyncio

        async def slow_response(*args, **kwargs):
            await asyncio.sleep(2)  # Longer than timeout
            return MagicMock()

        mock_litellm_module.acompletion = slow_response

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

    async def test_run_handles_api_error(self, executor, mock_litellm_module, simple_tools):
        """run() returns error status on API error."""
        mock_litellm_module.acompletion = AsyncMock(
            side_effect=Exception("API Error: Rate limited")
        )

        async def dummy_handler(name: str, args: dict) -> ToolResult:
            return ToolResult(tool_name=name, success=True, result={})

        result = await executor.run(
            prompt="Error request",
            tools=simple_tools,
            tool_handler=dummy_handler,
        )

        assert result.status == "error"
        assert "API Error" in result.error

    async def test_run_uses_system_prompt(self, executor, mock_litellm_module, simple_tools):
        """run() passes system prompt in messages."""
        mock_message = MagicMock()
        mock_message.content = "Response"
        mock_message.tool_calls = None

        mock_choice = MagicMock()
        mock_choice.message = mock_message

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_litellm_module.acompletion = AsyncMock(return_value=mock_response)

        async def dummy_handler(name: str, args: dict) -> ToolResult:
            return ToolResult(tool_name=name, success=True, result={})

        await executor.run(
            prompt="Hello",
            tools=simple_tools,
            tool_handler=dummy_handler,
            system_prompt="You are a weather assistant.",
        )

        # Verify system prompt was passed in messages
        mock_litellm_module.acompletion.assert_called_once()
        call_kwargs = mock_litellm_module.acompletion.call_args.kwargs
        messages = call_kwargs["messages"]
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "You are a weather assistant."

    async def test_run_uses_model_override(self, executor, mock_litellm_module, simple_tools):
        """run() uses model override when provided."""
        mock_message = MagicMock()
        mock_message.content = "Response"
        mock_message.tool_calls = None

        mock_choice = MagicMock()
        mock_choice.message = mock_message

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_litellm_module.acompletion = AsyncMock(return_value=mock_response)

        async def dummy_handler(name: str, args: dict) -> ToolResult:
            return ToolResult(tool_name=name, success=True, result={})

        await executor.run(
            prompt="Hello",
            tools=simple_tools,
            tool_handler=dummy_handler,
            model="gpt-4-turbo",
        )

        # Verify model override was used
        mock_litellm_module.acompletion.assert_called_once()
        call_kwargs = mock_litellm_module.acompletion.call_args.kwargs
        assert call_kwargs["model"] == "gpt-4-turbo"

    async def test_run_uses_api_base(self, mock_litellm_module, simple_tools):
        """run() passes api_base when configured."""
        from gobby.llm.litellm_executor import LiteLLMExecutor

        executor = LiteLLMExecutor(api_base="https://openrouter.ai/api/v1")

        mock_message = MagicMock()
        mock_message.content = "Response"
        mock_message.tool_calls = None

        mock_choice = MagicMock()
        mock_choice.message = mock_message

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_litellm_module.acompletion = AsyncMock(return_value=mock_response)

        async def dummy_handler(name: str, args: dict) -> ToolResult:
            return ToolResult(tool_name=name, success=True, result={})

        await executor.run(
            prompt="Hello",
            tools=simple_tools,
            tool_handler=dummy_handler,
        )

        # Verify api_base was passed
        mock_litellm_module.acompletion.assert_called_once()
        call_kwargs = mock_litellm_module.acompletion.call_args.kwargs
        assert call_kwargs["api_base"] == "https://openrouter.ai/api/v1"

    async def test_run_handles_invalid_json_arguments(
        self, executor, mock_litellm_module, simple_tools
    ):
        """run() handles invalid JSON in function arguments."""
        # Response with function call with bad JSON
        mock_tool_call = MagicMock()
        mock_tool_call.id = "call-123"
        mock_tool_call.function.name = "get_weather"
        mock_tool_call.function.arguments = "not valid json"

        mock_message1 = MagicMock()
        mock_message1.content = ""
        mock_message1.tool_calls = [mock_tool_call]
        mock_message1.model_dump = MagicMock(return_value={"role": "assistant"})

        mock_choice1 = MagicMock()
        mock_choice1.message = mock_message1

        mock_response1 = MagicMock()
        mock_response1.choices = [mock_choice1]

        # Second response
        mock_message2 = MagicMock()
        mock_message2.content = "Handled gracefully"
        mock_message2.tool_calls = None

        mock_choice2 = MagicMock()
        mock_choice2.message = mock_message2

        mock_response2 = MagicMock()
        mock_response2.choices = [mock_choice2]

        mock_litellm_module.acompletion = AsyncMock(side_effect=[mock_response1, mock_response2])

        async def dummy_handler(name: str, args: dict) -> ToolResult:
            # Handler should receive empty dict for invalid JSON
            return ToolResult(tool_name=name, success=True, result={"received": args})

        result = await executor.run(
            prompt="Test",
            tools=simple_tools,
            tool_handler=dummy_handler,
        )

        assert result.status == "success"
        # Should have recorded the tool call with empty args
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].arguments == {}


class TestLiteLLMExecutorToolConversion:
    """Tests for tool schema conversion."""

    @pytest.fixture
    def executor(self, mock_litellm_module):
        """Create a LiteLLMExecutor instance."""
        from gobby.llm.litellm_executor import LiteLLMExecutor

        return LiteLLMExecutor()

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

        result = executor._convert_tools_to_openai_format(tools)

        assert len(result) == 1
        assert result[0]["type"] == "function"
        assert result[0]["function"]["name"] == "test_tool"
        assert result[0]["function"]["description"] == "A test tool"
        assert result[0]["function"]["parameters"]["type"] == "object"
        assert "arg1" in result[0]["function"]["parameters"]["properties"]

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

        result = executor._convert_tools_to_openai_format(tools)

        assert len(result) == 2
        assert result[0]["function"]["name"] == "tool1"
        assert result[1]["function"]["name"] == "tool2"

    def test_convert_empty_tools(self, executor):
        """Converts empty tool list correctly."""
        result = executor._convert_tools_to_openai_format([])

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

        result = executor._convert_tools_to_openai_format(tools)

        assert result[0]["function"]["parameters"]["type"] == "object"
