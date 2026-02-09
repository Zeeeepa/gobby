"""Tests for ChatSession can_use_tool callback and pending question state."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.servers.chat_session import ChatSession

pytestmark = pytest.mark.unit


@pytest.fixture
def session() -> ChatSession:
    return ChatSession(conversation_id="test-conv-123")


class TestCanUseTool:
    """Tests for the _can_use_tool callback integration."""

    @pytest.mark.asyncio
    async def test_start_uses_can_use_tool_not_bypass(self, session: ChatSession) -> None:
        """start() should pass can_use_tool callback, not permission_mode=bypassPermissions."""
        captured_options = {}

        def capture_options(**kwargs):  # type: ignore[no-untyped-def]
            captured_options.update(kwargs)
            return MagicMock()

        with (
            patch("gobby.servers.chat_session._find_cli_path", return_value="/usr/bin/claude"),
            patch("gobby.servers.chat_session._find_mcp_config", return_value=None),
            patch("gobby.servers.chat_session._find_project_root", return_value=None),
            patch("gobby.servers.chat_session._load_chat_system_prompt", return_value="test prompt"),
            patch("gobby.servers.chat_session.ClaudeAgentOptions", side_effect=capture_options),
            patch("gobby.servers.chat_session.ClaudeSDKClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client_cls.return_value = mock_client

            await session.start()

            # Should NOT have permission_mode="bypassPermissions"
            assert captured_options.get("permission_mode") is None
            # Should have can_use_tool callback
            assert captured_options.get("can_use_tool") is not None
            assert callable(captured_options["can_use_tool"])

    @pytest.mark.asyncio
    async def test_auto_approves_non_ask_user_question(self, session: ChatSession) -> None:
        """_can_use_tool should auto-approve tools that aren't AskUserQuestion."""
        from claude_agent_sdk import PermissionResultAllow, ToolPermissionContext

        result = await session._can_use_tool(
            "mcp__gobby__create_task",
            {"title": "test"},
            ToolPermissionContext(),
        )

        assert isinstance(result, PermissionResultAllow)
        assert result.updated_input == {"title": "test"}

    @pytest.mark.asyncio
    async def test_ask_user_question_blocks_until_answer(self, session: ChatSession) -> None:
        """_can_use_tool should block on AskUserQuestion until provide_answer() is called."""
        from claude_agent_sdk import PermissionResultAllow, ToolPermissionContext

        input_data = {"questions": [{"question": "Which auth?", "options": [{"label": "OAuth"}]}]}
        answers = {"Which auth?": "OAuth"}

        async def provide_answer_after_delay() -> None:
            await asyncio.sleep(0.05)
            session.provide_answer(answers)

        # Start the answer provider concurrently
        answer_task = asyncio.create_task(provide_answer_after_delay())

        result = await session._can_use_tool(
            "AskUserQuestion",
            input_data,
            ToolPermissionContext(),
        )

        await answer_task

        assert isinstance(result, PermissionResultAllow)
        assert result.updated_input is not None
        assert result.updated_input["questions"] == input_data["questions"]
        assert result.updated_input["answers"] == answers

    @pytest.mark.asyncio
    async def test_has_pending_question_true_while_blocked(self, session: ChatSession) -> None:
        """has_pending_question should be True while waiting for answer."""
        from claude_agent_sdk import ToolPermissionContext

        assert session.has_pending_question is False

        input_data = {"questions": [{"question": "Pick one"}]}

        async def check_and_answer() -> None:
            await asyncio.sleep(0.05)
            assert session.has_pending_question is True
            session.provide_answer({"Pick one": "A"})

        answer_task = asyncio.create_task(check_and_answer())
        await session._can_use_tool("AskUserQuestion", input_data, ToolPermissionContext())
        await answer_task

        assert session.has_pending_question is False

    @pytest.mark.asyncio
    async def test_provide_answer_stores_answers(self, session: ChatSession) -> None:
        """provide_answer() should store answers and unblock the callback."""
        from claude_agent_sdk import PermissionResultAllow, ToolPermissionContext

        input_data = {"questions": [{"question": "Name?"}]}
        answers = {"Name?": "Alice"}

        async def answer() -> None:
            await asyncio.sleep(0.05)
            session.provide_answer(answers)

        task = asyncio.create_task(answer())
        result = await session._can_use_tool("AskUserQuestion", input_data, ToolPermissionContext())
        await task

        assert isinstance(result, PermissionResultAllow)
        assert result.updated_input["answers"] == answers
