"""Tests for ClaudeLLMProvider methods: generate_summary, synthesize_title."""

import asyncio
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

import pytest

from gobby.config.app import (
    DaemonConfig,
    LLMProviderConfig,
    LLMProvidersConfig,
    SessionSummaryConfig,
    TitleSynthesisConfig,
)
from gobby.llm.claude import ClaudeLLMProvider

# --- Mocks for claude_agent_sdk ---


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
    def __init__(self, id, name, input):
        self.id = id
        self.name = name
        self.input = input


class MockToolResultBlock:
    def __init__(self, tool_use_id, content):
        self.tool_use_id = tool_use_id
        self.content = content


class MockClaudeAgentOptions:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


# --- Fixtures ---


@pytest.fixture
def claude_config():
    return DaemonConfig(
        llm_providers=LLMProvidersConfig(
            claude=LLMProviderConfig(models="claude-3-5-sonnet"),
        ),
        session_summary=SessionSummaryConfig(enabled=True),
        title_synthesis=TitleSynthesisConfig(enabled=True),
    )


@contextmanager
def mock_claude_sdk(mock_query_func):
    with (
        patch("gobby.llm.claude.shutil.which", return_value="/mock/claude"),
        patch("os.path.exists", return_value=True),
        patch("os.access", return_value=True),
        patch("gobby.llm.claude.query", mock_query_func),
        patch("gobby.llm.claude.AssistantMessage", MockAssistantMessage),
        patch("gobby.llm.claude.ResultMessage", MockResultMessage),
        patch("gobby.llm.claude.TextBlock", MockTextBlock),
        patch("gobby.llm.claude.ToolUseBlock", MockToolUseBlock),
        patch("gobby.llm.claude.ToolResultBlock", MockToolResultBlock),
        patch("gobby.llm.claude.UserMessage", MockUserMessage),
        patch("gobby.llm.claude.ClaudeAgentOptions", MockClaudeAgentOptions),
    ):
        yield


# --- Tests ---


@pytest.mark.asyncio
async def test_generate_summary_success(claude_config):
    async def mock_query(prompt, options):
        yield MockAssistantMessage([MockTextBlock("Summary of session.")])
        yield MockResultMessage(result="Summary of session.")

    with mock_claude_sdk(mock_query):
        provider = ClaudeLLMProvider(claude_config)
        context = {"transcript_summary": "prev", "last_messages": []}
        summary = await provider.generate_summary(
            context, prompt_template="Sum: {transcript_summary}"
        )
        assert summary == "Summary of session."


@pytest.mark.asyncio
async def test_generate_summary_no_cli(claude_config):
    with patch("gobby.llm.claude.shutil.which", return_value=None):
        provider = ClaudeLLMProvider(claude_config)
        summary = await provider.generate_summary({}, prompt_template="test")
        assert "unavailable" in summary.lower()


@pytest.mark.asyncio
async def test_synthesize_title_success(claude_config):
    async def mock_query(prompt, options):
        yield MockAssistantMessage([MockTextBlock("New Title")])

    with mock_claude_sdk(mock_query):
        provider = ClaudeLLMProvider(claude_config)
        title = await provider.synthesize_title("prompt", prompt_template="{user_prompt}")
        assert title == "New Title"


@pytest.mark.asyncio
async def test_synthesize_title_retry(claude_config):
    # Fail twice, succeed third time
    attempts = 0

    async def mock_query(prompt, options):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise Exception("Fail")
        yield MockAssistantMessage([MockTextBlock("Success Title")])

    with mock_claude_sdk(mock_query):
        provider = ClaudeLLMProvider(claude_config)
        with patch("asyncio.sleep", AsyncMock()):  # skip sleep
            title = await provider.synthesize_title("prompt", prompt_template="test")
            assert title == "Success Title"
            assert attempts == 3


@pytest.mark.asyncio
async def test_verify_cli_path_retry(claude_config):
    """Test race condition handling in _verify_cli_path."""

    # Mock shutil.which to fail twice then succeed
    side_effects = [None, None, "/found/now"]

    with patch("gobby.llm.claude.shutil.which", side_effect=side_effects) as mock_which:
        with patch("gobby.llm.claude.time.sleep") as mock_sleep:
            with patch("os.path.exists", return_value=True):
                provider = ClaudeLLMProvider(claude_config)
                # Manually trigger verify logic
                # Initial find failed (in __init__ which calls _find_cli_path)
                # provider._claude_cli_path is None or whatever __init__ set it to.
                # Let's force it to be set but then "disappear"

                provider._claude_cli_path = "/old/path"
                # Patch exists to return False for /old/path

                def exists_side_effect(path):
                    return path == "/found/now"

                with patch("os.path.exists", side_effect=exists_side_effect):
                    path = provider._verify_cli_path()
                    assert path == "/found/now"
                    assert mock_which.call_count >= 1
                    assert mock_sleep.call_count >= 1


@pytest.mark.asyncio
async def test_generate_text(claude_config):
    async def mock_query(prompt, options):
        yield MockAssistantMessage([MockTextBlock("Generated text")])

    with mock_claude_sdk(mock_query):
        provider = ClaudeLLMProvider(claude_config)
        text = await provider.generate_text("prompt")
        assert text == "Generated text"
