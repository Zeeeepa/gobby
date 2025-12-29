"""Tests for the ClaudeLLMProvider, specifically generate_with_mcp_tools."""

import sys
from unittest.mock import MagicMock, patch

import pytest

from gobby.config.app import DaemonConfig, LLMProviderConfig, LLMProvidersConfig


# Define mock classes for claude_agent_sdk
class MockAssistantMessage:
    def __init__(self, content):
        self.content = content


class MockUserMessage:
    def __init__(self, content):
        self.content = content


class MockResultMessage:
    def __init__(self, result=None):
        self.result = result


class MockTextBlock:
    def __init__(self, text):
        self.text = text


class MockToolUseBlock:
    def __init__(self, id: str, name: str, input: dict):
        self.id = id
        self.name = name
        self.input = input


class MockToolResultBlock:
    def __init__(self, tool_use_id: str, content: str):
        self.tool_use_id = tool_use_id
        self.content = content


class MockClaudeAgentOptions:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


# Build the mock module
mock_sdk = MagicMock()
mock_sdk.AssistantMessage = MockAssistantMessage
mock_sdk.UserMessage = MockUserMessage
mock_sdk.ResultMessage = MockResultMessage
mock_sdk.TextBlock = MockTextBlock
mock_sdk.ToolUseBlock = MockToolUseBlock
mock_sdk.ToolResultBlock = MockToolResultBlock
mock_sdk.ClaudeAgentOptions = MockClaudeAgentOptions


@pytest.fixture
def claude_config() -> DaemonConfig:
    """Create a DaemonConfig with Claude provider configured."""
    return DaemonConfig(
        llm_providers=LLMProvidersConfig(
            claude=LLMProviderConfig(models="claude-sonnet-4-5"),
        ),
    )


@pytest.fixture(autouse=True)
def mock_claude_sdk():
    """Mock the claude_agent_sdk module before importing ClaudeLLMProvider."""
    with patch.dict(sys.modules, {"claude_agent_sdk": mock_sdk}):
        yield


class TestToolCallDataclass:
    """Tests for the ToolCall dataclass."""

    def test_tool_call_creation(self):
        """Test ToolCall can be created with required fields."""
        from gobby.llm.claude import ToolCall

        call = ToolCall(
            tool_name="mcp__gobby-tasks__create_task",
            server_name="gobby-tasks",
            arguments={"title": "Test task"},
        )

        assert call.tool_name == "mcp__gobby-tasks__create_task"
        assert call.server_name == "gobby-tasks"
        assert call.arguments == {"title": "Test task"}
        assert call.result is None

    def test_tool_call_with_result(self):
        """Test ToolCall with result."""
        from gobby.llm.claude import ToolCall

        call = ToolCall(
            tool_name="mcp__gobby-tasks__create_task",
            server_name="gobby-tasks",
            arguments={"title": "Test task"},
            result='{"task_id": "123"}',
        )

        assert call.result == '{"task_id": "123"}'


class TestMCPToolResultDataclass:
    """Tests for the MCPToolResult dataclass."""

    def test_mcp_tool_result_creation(self):
        """Test MCPToolResult can be created with required fields."""
        from gobby.llm.claude import MCPToolResult

        result = MCPToolResult(text="Task created successfully")

        assert result.text == "Task created successfully"
        assert result.tool_calls == []

    def test_mcp_tool_result_with_calls(self):
        """Test MCPToolResult with tool calls."""
        from gobby.llm.claude import MCPToolResult, ToolCall

        calls = [
            ToolCall(
                tool_name="mcp__gobby-tasks__create_task",
                server_name="gobby-tasks",
                arguments={"title": "Task 1"},
            )
        ]
        result = MCPToolResult(text="Created 1 task", tool_calls=calls)

        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].arguments["title"] == "Task 1"


class TestGenerateWithMcpToolsNoCli:
    """Tests for generate_with_mcp_tools when CLI is not available."""

    @pytest.mark.asyncio
    async def test_returns_error_when_cli_not_found(self, claude_config: DaemonConfig):
        """Test that method returns error when Claude CLI is not found."""
        with patch("gobby.llm.claude.shutil.which", return_value=None):
            from gobby.llm.claude import ClaudeLLMProvider

            provider = ClaudeLLMProvider(claude_config)

            result = await provider.generate_with_mcp_tools(
                prompt="Create a task",
                allowed_tools=["mcp__gobby-tasks__create_task"],
            )

            assert "unavailable" in result.text.lower() or "not found" in result.text.lower()
            assert result.tool_calls == []


class TestGenerateWithMcpToolsWithCli:
    """Tests for generate_with_mcp_tools with CLI available."""

    @pytest.mark.asyncio
    async def test_returns_text_only_no_tools(self, claude_config: DaemonConfig):
        """Test generation with no tool calls."""

        async def mock_query(prompt, options):
            yield MockAssistantMessage([MockTextBlock("Hello, world!")])
            yield MockResultMessage(result="Hello, world!")

        mock_sdk.query = mock_query

        with patch("gobby.llm.claude.shutil.which", return_value="/usr/bin/claude"):
            with patch("os.path.exists", return_value=True):
                with patch("os.access", return_value=True):
                    from gobby.llm.claude import ClaudeLLMProvider

                    provider = ClaudeLLMProvider(claude_config)

                    result = await provider.generate_with_mcp_tools(
                        prompt="Say hello",
                        allowed_tools=[],
                    )

                    assert "Hello, world!" in result.text
                    assert result.tool_calls == []

    @pytest.mark.asyncio
    async def test_tracks_tool_calls(self, claude_config: DaemonConfig):
        """Test that tool calls are tracked."""

        async def mock_query(prompt, options):
            # Assistant makes a tool call
            yield MockAssistantMessage(
                [
                    MockToolUseBlock(
                        id="call_123",
                        name="mcp__gobby-tasks__create_task",
                        input={"title": "New task", "description": "A test task"},
                    )
                ]
            )
            # Tool result comes back
            yield MockUserMessage(
                [MockToolResultBlock(tool_use_id="call_123", content='{"task_id": "task-456"}')]
            )
            # Final text response
            yield MockAssistantMessage([MockTextBlock("I created the task for you.")])
            yield MockResultMessage(result="I created the task for you.")

        mock_sdk.query = mock_query

        with patch("gobby.llm.claude.shutil.which", return_value="/usr/bin/claude"):
            with patch("os.path.exists", return_value=True):
                with patch("os.access", return_value=True):
                    from gobby.llm.claude import ClaudeLLMProvider

                    provider = ClaudeLLMProvider(claude_config)

                    result = await provider.generate_with_mcp_tools(
                        prompt="Create a task called 'New task'",
                        allowed_tools=["mcp__gobby-tasks__create_task"],
                    )

                    assert len(result.tool_calls) == 1
                    call = result.tool_calls[0]
                    assert call.tool_name == "mcp__gobby-tasks__create_task"
                    assert call.server_name == "gobby-tasks"
                    assert call.arguments == {"title": "New task", "description": "A test task"}
                    assert call.result == '{"task_id": "task-456"}'

    @pytest.mark.asyncio
    async def test_tracks_multiple_tool_calls(self, claude_config: DaemonConfig):
        """Test that multiple tool calls are tracked."""

        async def mock_query(prompt, options):
            # First tool call
            yield MockAssistantMessage(
                [
                    MockToolUseBlock(
                        id="call_1",
                        name="mcp__gobby-tasks__create_task",
                        input={"title": "Task 1"},
                    )
                ]
            )
            yield MockUserMessage(
                [MockToolResultBlock(tool_use_id="call_1", content='{"task_id": "t1"}')]
            )
            # Second tool call
            yield MockAssistantMessage(
                [
                    MockToolUseBlock(
                        id="call_2",
                        name="mcp__gobby-tasks__create_task",
                        input={"title": "Task 2"},
                    )
                ]
            )
            yield MockUserMessage(
                [MockToolResultBlock(tool_use_id="call_2", content='{"task_id": "t2"}')]
            )
            yield MockResultMessage(result="Created 2 tasks.")

        mock_sdk.query = mock_query

        with patch("gobby.llm.claude.shutil.which", return_value="/usr/bin/claude"):
            with patch("os.path.exists", return_value=True):
                with patch("os.access", return_value=True):
                    from gobby.llm.claude import ClaudeLLMProvider

                    provider = ClaudeLLMProvider(claude_config)

                    result = await provider.generate_with_mcp_tools(
                        prompt="Create two tasks",
                        allowed_tools=["mcp__gobby-tasks__create_task"],
                    )

                    assert len(result.tool_calls) == 2
                    assert result.tool_calls[0].arguments["title"] == "Task 1"
                    assert result.tool_calls[1].arguments["title"] == "Task 2"

    @pytest.mark.asyncio
    async def test_handles_exception(self, claude_config: DaemonConfig):
        """Test that exceptions are handled gracefully."""

        async def mock_query(prompt, options):
            raise RuntimeError("Connection failed")
            yield  # Make this a generator

        mock_sdk.query = mock_query

        with patch("gobby.llm.claude.shutil.which", return_value="/usr/bin/claude"):
            with patch("os.path.exists", return_value=True):
                with patch("os.access", return_value=True):
                    from gobby.llm.claude import ClaudeLLMProvider

                    provider = ClaudeLLMProvider(claude_config)

                    result = await provider.generate_with_mcp_tools(
                        prompt="Create a task",
                        allowed_tools=["mcp__gobby-tasks__create_task"],
                    )

                    assert "failed" in result.text.lower()
                    assert "Connection failed" in result.text

    @pytest.mark.asyncio
    async def test_parses_server_name_correctly(self, claude_config: DaemonConfig):
        """Test server name is extracted correctly from tool name."""

        async def mock_query(prompt, options):
            yield MockAssistantMessage(
                [
                    MockToolUseBlock(
                        id="call_1",
                        name="mcp__my-custom-server__do_something",
                        input={"arg": "value"},
                    )
                ]
            )
            yield MockUserMessage([MockToolResultBlock(tool_use_id="call_1", content="done")])
            yield MockResultMessage(result="Done")

        mock_sdk.query = mock_query

        with patch("gobby.llm.claude.shutil.which", return_value="/usr/bin/claude"):
            with patch("os.path.exists", return_value=True):
                with patch("os.access", return_value=True):
                    from gobby.llm.claude import ClaudeLLMProvider

                    provider = ClaudeLLMProvider(claude_config)

                    result = await provider.generate_with_mcp_tools(
                        prompt="Do something",
                        allowed_tools=["mcp__my-custom-server__do_something"],
                    )

                    assert result.tool_calls[0].server_name == "my-custom-server"

    @pytest.mark.asyncio
    async def test_handles_non_mcp_tool_names(self, claude_config: DaemonConfig):
        """Test handling of non-MCP tool names."""

        async def mock_query(prompt, options):
            yield MockAssistantMessage(
                [
                    MockToolUseBlock(
                        id="call_1",
                        name="code_execution",  # Built-in tool, not MCP
                        input={"code": "print(1)"},
                    )
                ]
            )
            yield MockUserMessage([MockToolResultBlock(tool_use_id="call_1", content="1")])
            yield MockResultMessage(result="Executed code")

        mock_sdk.query = mock_query

        with patch("gobby.llm.claude.shutil.which", return_value="/usr/bin/claude"):
            with patch("os.path.exists", return_value=True):
                with patch("os.access", return_value=True):
                    from gobby.llm.claude import ClaudeLLMProvider

                    provider = ClaudeLLMProvider(claude_config)

                    result = await provider.generate_with_mcp_tools(
                        prompt="Run code",
                        allowed_tools=["code_execution"],
                    )

                    assert result.tool_calls[0].server_name == "unknown"

    @pytest.mark.asyncio
    async def test_uses_custom_system_prompt(self, claude_config: DaemonConfig):
        """Test that custom system prompt is passed to options."""
        captured_options = []

        async def mock_query(prompt, options):
            captured_options.append(options)
            yield MockResultMessage(result="Done")

        mock_sdk.query = mock_query

        with patch("gobby.llm.claude.shutil.which", return_value="/usr/bin/claude"):
            with patch("os.path.exists", return_value=True):
                with patch("os.access", return_value=True):
                    from gobby.llm.claude import ClaudeLLMProvider

                    provider = ClaudeLLMProvider(claude_config)

                    await provider.generate_with_mcp_tools(
                        prompt="Create task",
                        allowed_tools=["mcp__gobby-tasks__create_task"],
                        system_prompt="You are a task manager.",
                    )

                    assert len(captured_options) == 1
                    opts = captured_options[0]
                    assert opts.kwargs["system_prompt"] == "You are a task manager."

    @pytest.mark.asyncio
    async def test_uses_custom_model(self, claude_config: DaemonConfig):
        """Test that custom model is passed to options."""
        captured_options = []

        async def mock_query(prompt, options):
            captured_options.append(options)
            yield MockResultMessage(result="Done")

        mock_sdk.query = mock_query

        with patch("gobby.llm.claude.shutil.which", return_value="/usr/bin/claude"):
            with patch("os.path.exists", return_value=True):
                with patch("os.access", return_value=True):
                    from gobby.llm.claude import ClaudeLLMProvider

                    provider = ClaudeLLMProvider(claude_config)

                    await provider.generate_with_mcp_tools(
                        prompt="Create task",
                        allowed_tools=[],
                        model="claude-haiku-4-5",
                    )

                    assert captured_options[0].kwargs["model"] == "claude-haiku-4-5"

    @pytest.mark.asyncio
    async def test_uses_custom_max_turns(self, claude_config: DaemonConfig):
        """Test that custom max_turns is passed to options."""
        captured_options = []

        async def mock_query(prompt, options):
            captured_options.append(options)
            yield MockResultMessage(result="Done")

        mock_sdk.query = mock_query

        with patch("gobby.llm.claude.shutil.which", return_value="/usr/bin/claude"):
            with patch("os.path.exists", return_value=True):
                with patch("os.access", return_value=True):
                    from gobby.llm.claude import ClaudeLLMProvider

                    provider = ClaudeLLMProvider(claude_config)

                    await provider.generate_with_mcp_tools(
                        prompt="Create task",
                        allowed_tools=[],
                        max_turns=5,
                    )

                    assert captured_options[0].kwargs["max_turns"] == 5
