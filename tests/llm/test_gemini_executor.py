"""Tests for GeminiExecutor class."""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.llm.executor import ToolResult, ToolSchema


@pytest.fixture
def mock_google_module():
    """Mock the google.generativeai module."""
    mock_genai = MagicMock()
    mock_genai.configure = MagicMock()
    mock_genai.protos = MagicMock()
    mock_genai.protos.Part = MagicMock()
    mock_genai.protos.FunctionResponse = MagicMock()
    mock_genai.GenerativeModel = MagicMock()

    # Create mock google and google.generativeai modules
    mock_google = MagicMock()
    mock_google.generativeai = mock_genai
    mock_google.auth = MagicMock()
    mock_google.auth.default = MagicMock(return_value=(MagicMock(), "test-project"))

    with patch.dict(
        sys.modules,
        {
            "google": mock_google,
            "google.generativeai": mock_genai,
            "google.auth": mock_google.auth,
        },
    ):
        yield mock_genai


class TestGeminiExecutorInit:
    """Tests for GeminiExecutor initialization."""

    def test_init_with_api_key(self, mock_google_module):
        """GeminiExecutor initializes with API key."""
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            from gobby.llm.gemini_executor import GeminiExecutor

            executor = GeminiExecutor(auth_mode="api_key")

            assert executor.provider_name == "gemini"
            assert executor.auth_mode == "api_key"
            assert executor.default_model == "gemini-2.0-flash"
            mock_google_module.configure.assert_called_with(api_key="test-key")

    def test_init_with_explicit_api_key(self, mock_google_module):
        """GeminiExecutor uses explicit API key over environment."""
        from gobby.llm.gemini_executor import GeminiExecutor

        executor = GeminiExecutor(auth_mode="api_key", api_key="explicit-key")

        mock_google_module.configure.assert_called_with(api_key="explicit-key")
        assert executor.auth_mode == "api_key"

    def test_init_with_custom_model(self, mock_google_module):
        """GeminiExecutor accepts custom default model."""
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            from gobby.llm.gemini_executor import GeminiExecutor

            executor = GeminiExecutor(
                auth_mode="api_key", default_model="gemini-1.5-pro"
            )

            assert executor.default_model == "gemini-1.5-pro"

    def test_init_without_api_key_raises(self, mock_google_module):
        """GeminiExecutor raises ValueError without API key."""
        # Clear environment of any GEMINI_API_KEY
        with patch.dict("os.environ", {}, clear=True):
            from gobby.llm.gemini_executor import GeminiExecutor

            with pytest.raises(ValueError, match="API key required"):
                GeminiExecutor(auth_mode="api_key")

    def test_init_with_adc_mode(self, mock_google_module):
        """GeminiExecutor initializes with ADC mode."""
        from gobby.llm.gemini_executor import GeminiExecutor

        executor = GeminiExecutor(auth_mode="adc")

        assert executor.auth_mode == "adc"
        # Configure should have been called with credentials
        mock_google_module.configure.assert_called()

    def test_init_missing_package_raises(self):
        """GeminiExecutor raises ImportError when package not installed."""
        # Create a fresh mock that raises ImportError when accessing google.generativeai
        with patch.dict(sys.modules, {"google": None, "google.generativeai": None}):
            # Need to reimport to get fresh module state
            import importlib

            # This should raise ImportError since google module is None
            with pytest.raises((ImportError, ModuleNotFoundError, TypeError)):
                import gobby.llm.gemini_executor as module

                importlib.reload(module)
                module.GeminiExecutor(auth_mode="api_key", api_key="test")


class TestGeminiExecutorRun:
    """Tests for GeminiExecutor.run() method."""

    @pytest.fixture
    def executor(self, mock_google_module):
        """Create a GeminiExecutor instance."""
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            from gobby.llm.gemini_executor import GeminiExecutor

            return GeminiExecutor(auth_mode="api_key")

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
        self, executor, mock_google_module, simple_tools
    ):
        """run() returns text response when no tools are called."""
        # Setup mock response
        mock_model = MagicMock()
        mock_chat = MagicMock()
        mock_response = MagicMock()

        # Create a mock part with only text
        mock_part = MagicMock()
        mock_part.text = "Hello, I'm Gemini!"
        mock_part.function_call = None

        mock_candidate = MagicMock()
        mock_candidate.content.parts = [mock_part]
        mock_response.candidates = [mock_candidate]

        mock_chat.send_message_async = AsyncMock(return_value=mock_response)
        mock_model.start_chat = MagicMock(return_value=mock_chat)
        mock_google_module.GenerativeModel = MagicMock(return_value=mock_model)

        async def dummy_handler(name: str, args: dict) -> ToolResult:
            return ToolResult(tool_name=name, success=True, result={"ok": True})

        result = await executor.run(
            prompt="Hello!",
            tools=simple_tools,
            tool_handler=dummy_handler,
        )

        assert result.status == "success"
        assert result.output == "Hello, I'm Gemini!"
        assert len(result.tool_calls) == 0

    async def test_run_handles_function_call(
        self, executor, mock_google_module, simple_tools
    ):
        """run() handles function calls and sends results back."""
        mock_model = MagicMock()
        mock_chat = MagicMock()

        # First response with function call
        mock_fc = MagicMock()
        mock_fc.name = "get_weather"
        mock_fc.args = {"location": "San Francisco"}

        mock_part1 = MagicMock()
        mock_part1.text = ""
        mock_part1.function_call = mock_fc

        mock_candidate1 = MagicMock()
        mock_candidate1.content.parts = [mock_part1]
        mock_response1 = MagicMock()
        mock_response1.candidates = [mock_candidate1]

        # Second response with text (after function result)
        mock_part2 = MagicMock()
        mock_part2.text = "The weather in San Francisco is sunny."
        mock_part2.function_call = None

        mock_candidate2 = MagicMock()
        mock_candidate2.content.parts = [mock_part2]
        mock_response2 = MagicMock()
        mock_response2.candidates = [mock_candidate2]

        mock_chat.send_message_async = AsyncMock(
            side_effect=[mock_response1, mock_response2]
        )
        mock_model.start_chat = MagicMock(return_value=mock_chat)
        mock_google_module.GenerativeModel = MagicMock(return_value=mock_model)

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
        self, executor, mock_google_module, simple_tools
    ):
        """run() handles tool execution errors gracefully."""
        mock_model = MagicMock()
        mock_chat = MagicMock()

        # Response with function call
        mock_fc = MagicMock()
        mock_fc.name = "get_weather"
        mock_fc.args = {"location": "Unknown"}

        mock_part1 = MagicMock()
        mock_part1.text = ""
        mock_part1.function_call = mock_fc

        mock_candidate1 = MagicMock()
        mock_candidate1.content.parts = [mock_part1]
        mock_response1 = MagicMock()
        mock_response1.candidates = [mock_candidate1]

        # Response after error
        mock_part2 = MagicMock()
        mock_part2.text = "I couldn't get the weather."
        mock_part2.function_call = None

        mock_candidate2 = MagicMock()
        mock_candidate2.content.parts = [mock_part2]
        mock_response2 = MagicMock()
        mock_response2.candidates = [mock_candidate2]

        mock_chat.send_message_async = AsyncMock(
            side_effect=[mock_response1, mock_response2]
        )
        mock_model.start_chat = MagicMock(return_value=mock_chat)
        mock_google_module.GenerativeModel = MagicMock(return_value=mock_model)

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
        self, executor, mock_google_module, simple_tools
    ):
        """run() stops after max_turns is reached."""
        mock_model = MagicMock()
        mock_chat = MagicMock()

        # Always return function call (to exhaust turns)
        mock_fc = MagicMock()
        mock_fc.name = "get_weather"
        mock_fc.args = {"location": "SF"}

        mock_part = MagicMock()
        mock_part.text = ""
        mock_part.function_call = mock_fc

        mock_candidate = MagicMock()
        mock_candidate.content.parts = [mock_part]
        mock_response = MagicMock()
        mock_response.candidates = [mock_candidate]

        mock_chat.send_message_async = AsyncMock(return_value=mock_response)
        mock_model.start_chat = MagicMock(return_value=mock_chat)
        mock_google_module.GenerativeModel = MagicMock(return_value=mock_model)

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
        self, executor, mock_google_module, simple_tools
    ):
        """run() returns timeout status when execution exceeds timeout."""
        import asyncio

        mock_model = MagicMock()
        mock_chat = MagicMock()

        async def slow_response(*args):
            await asyncio.sleep(2)  # Longer than timeout
            return MagicMock()

        mock_chat.send_message_async = slow_response
        mock_model.start_chat = MagicMock(return_value=mock_chat)
        mock_google_module.GenerativeModel = MagicMock(return_value=mock_model)

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

    async def test_run_handles_api_error(
        self, executor, mock_google_module, simple_tools
    ):
        """run() returns error status on API error."""
        mock_model = MagicMock()
        mock_chat = MagicMock()
        mock_chat.send_message_async = AsyncMock(
            side_effect=Exception("API Error: Rate limited")
        )
        mock_model.start_chat = MagicMock(return_value=mock_chat)
        mock_google_module.GenerativeModel = MagicMock(return_value=mock_model)

        async def dummy_handler(name: str, args: dict) -> ToolResult:
            return ToolResult(tool_name=name, success=True, result={})

        result = await executor.run(
            prompt="Error request",
            tools=simple_tools,
            tool_handler=dummy_handler,
        )

        assert result.status == "error"
        assert "API Error" in result.error

    async def test_run_uses_system_prompt(
        self, executor, mock_google_module, simple_tools
    ):
        """run() passes system prompt to model."""
        mock_model = MagicMock()
        mock_chat = MagicMock()

        mock_part = MagicMock()
        mock_part.text = "Response"
        mock_part.function_call = None

        mock_candidate = MagicMock()
        mock_candidate.content.parts = [mock_part]
        mock_response = MagicMock()
        mock_response.candidates = [mock_candidate]

        mock_chat.send_message_async = AsyncMock(return_value=mock_response)
        mock_model.start_chat = MagicMock(return_value=mock_chat)
        mock_google_module.GenerativeModel = MagicMock(return_value=mock_model)

        async def dummy_handler(name: str, args: dict) -> ToolResult:
            return ToolResult(tool_name=name, success=True, result={})

        await executor.run(
            prompt="Hello",
            tools=simple_tools,
            tool_handler=dummy_handler,
            system_prompt="You are a weather assistant.",
        )

        # Verify system prompt was passed to model
        mock_google_module.GenerativeModel.assert_called_once()
        call_kwargs = mock_google_module.GenerativeModel.call_args.kwargs
        assert call_kwargs["system_instruction"] == "You are a weather assistant."

    async def test_run_uses_model_override(
        self, executor, mock_google_module, simple_tools
    ):
        """run() uses model override when provided."""
        mock_model = MagicMock()
        mock_chat = MagicMock()

        mock_part = MagicMock()
        mock_part.text = "Response"
        mock_part.function_call = None

        mock_candidate = MagicMock()
        mock_candidate.content.parts = [mock_part]
        mock_response = MagicMock()
        mock_response.candidates = [mock_candidate]

        mock_chat.send_message_async = AsyncMock(return_value=mock_response)
        mock_model.start_chat = MagicMock(return_value=mock_chat)
        mock_google_module.GenerativeModel = MagicMock(return_value=mock_model)

        async def dummy_handler(name: str, args: dict) -> ToolResult:
            return ToolResult(tool_name=name, success=True, result={})

        await executor.run(
            prompt="Hello",
            tools=simple_tools,
            tool_handler=dummy_handler,
            model="gemini-1.5-pro",
        )

        # Verify model override was used
        mock_google_module.GenerativeModel.assert_called_once()
        call_kwargs = mock_google_module.GenerativeModel.call_args.kwargs
        assert call_kwargs["model_name"] == "gemini-1.5-pro"


class TestGeminiExecutorToolConversion:
    """Tests for tool schema conversion."""

    @pytest.fixture
    def executor(self, mock_google_module):
        """Create a GeminiExecutor instance."""
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            from gobby.llm.gemini_executor import GeminiExecutor

            return GeminiExecutor(auth_mode="api_key")

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

        result = executor._convert_tools_to_gemini_format(tools)

        assert len(result) == 1
        assert result[0]["name"] == "test_tool"
        assert result[0]["description"] == "A test tool"
        assert result[0]["parameters"]["type"] == "object"
        assert "arg1" in result[0]["parameters"]["properties"]

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

        result = executor._convert_tools_to_gemini_format(tools)

        assert len(result) == 2
        assert result[0]["name"] == "tool1"
        assert result[1]["name"] == "tool2"

    def test_convert_empty_tools(self, executor):
        """Converts empty tool list correctly."""
        result = executor._convert_tools_to_gemini_format([])

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

        result = executor._convert_tools_to_gemini_format(tools)

        assert result[0]["parameters"]["type"] == "object"
