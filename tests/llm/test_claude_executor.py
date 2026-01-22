"""Tests for ClaudeExecutor class.

Note: ClaudeExecutor only supports subscription mode. API key mode is handled
by LiteLLMExecutor with provider='claude'. See test_litellm_executor.py for
API key mode tests.
"""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.llm.executor import AgentResult, ToolResult, ToolSchema


@pytest.fixture
def mock_anthropic_module():
    """Mock the anthropic module."""
    mock_anthropic = MagicMock()
    mock_anthropic.AsyncAnthropic = MagicMock()

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

    def test_init_with_subscription_mode(self, mock_anthropic_module):
        """ClaudeExecutor initializes with subscription mode."""
        import shutil

        with patch.object(shutil, "which", return_value="/usr/bin/claude"):
            from gobby.llm.claude_executor import ClaudeExecutor

            executor = ClaudeExecutor(auth_mode="subscription")

            assert executor.auth_mode == "subscription"
            assert executor._cli_path == "/usr/bin/claude"

    def test_init_default_is_subscription_mode(self, mock_anthropic_module):
        """ClaudeExecutor defaults to subscription mode."""
        import shutil

        with patch.object(shutil, "which", return_value="/usr/bin/claude"):
            from gobby.llm.claude_executor import ClaudeExecutor

            executor = ClaudeExecutor()

            assert executor.auth_mode == "subscription"

    def test_init_with_custom_model(self, mock_anthropic_module):
        """ClaudeExecutor accepts custom default model."""
        import shutil

        with patch.object(shutil, "which", return_value="/usr/bin/claude"):
            from gobby.llm.claude_executor import ClaudeExecutor

            executor = ClaudeExecutor(
                auth_mode="subscription", default_model="claude-opus-4-5-20251101"
            )

            assert executor.default_model == "claude-opus-4-5-20251101"

    def test_init_subscription_mode_without_cli_raises(self, mock_anthropic_module):
        """ClaudeExecutor raises ValueError when CLI not found in subscription mode."""
        import shutil

        with patch.object(shutil, "which", return_value=None):
            from gobby.llm.claude_executor import ClaudeExecutor

            with pytest.raises(ValueError, match="Claude CLI not found"):
                ClaudeExecutor(auth_mode="subscription")

    def test_init_api_key_mode_raises(self, mock_anthropic_module):
        """ClaudeExecutor raises ValueError for api_key mode (now unsupported)."""
        from gobby.llm.claude_executor import ClaudeExecutor

        with pytest.raises(ValueError, match="only supports subscription mode"):
            ClaudeExecutor(auth_mode="api_key")

    def test_init_unknown_auth_mode_raises(self, mock_anthropic_module):
        """ClaudeExecutor raises ValueError for unknown auth mode."""
        from gobby.llm.claude_executor import ClaudeExecutor

        with pytest.raises(ValueError, match="only supports subscription mode"):
            ClaudeExecutor(auth_mode="unknown")  # type: ignore[arg-type]


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

    def test_sdk_mode_provider_name(self, executor_sdk_mode):
        """SDK mode executor returns correct provider name."""
        assert executor_sdk_mode.provider_name == "claude"

    async def test_run_with_sdk_mode_delegates_to_sdk(self, executor_sdk_mode, simple_tools):
        """SDK mode run() delegates to _run_with_sdk method."""
        # Verify the executor is in subscription mode
        assert executor_sdk_mode.auth_mode == "subscription"

        async def dummy_handler(name: str, args: dict) -> ToolResult:
            return ToolResult(tool_name=name, success=True, result={"ok": True})

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


class TestClaudeExecutorProviderName:
    """Tests for provider_name property."""

    def test_provider_name_subscription_mode(self, mock_anthropic_module):
        """Provider name is 'claude' in subscription mode."""
        import shutil

        with patch.object(shutil, "which", return_value="/usr/bin/claude"):
            from gobby.llm.claude_executor import ClaudeExecutor

            executor = ClaudeExecutor(auth_mode="subscription")
            assert executor.provider_name == "claude"
