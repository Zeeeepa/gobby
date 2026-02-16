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
            patch(
                "gobby.servers.chat_session._load_chat_system_prompt", return_value="test prompt"
            ),
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


class TestHistoryInjection:
    """Tests for history injection on session recreation."""

    def test_needs_history_injection_default_false(self) -> None:
        """New sessions should not need history injection by default."""
        s = ChatSession(conversation_id="test-default")
        assert s._needs_history_injection is False

    @pytest.mark.asyncio
    async def test_load_history_context_no_manager(self, session: ChatSession) -> None:
        """_load_history_context returns None when no message_manager is set."""
        session.db_session_id = "some-id"
        session._message_manager = None
        result = await session._load_history_context()
        assert result is None

    @pytest.mark.asyncio
    async def test_load_history_context_no_db_session_id(self, session: ChatSession) -> None:
        """_load_history_context returns None when db_session_id is not set."""
        session._message_manager = AsyncMock()
        session.db_session_id = None
        result = await session._load_history_context()
        assert result is None

    @pytest.mark.asyncio
    async def test_load_history_context_formats_messages(self, session: ChatSession) -> None:
        """_load_history_context correctly formats user/assistant messages."""
        mock_manager = AsyncMock()
        mock_manager.get_messages.return_value = [
            {"role": "user", "content_type": "text", "content": "Hello there"},
            {"role": "assistant", "content_type": "text", "content": "Hi! How can I help?"},
            {"role": "user", "content_type": "text", "content": "Tell me about Python"},
        ]
        session.db_session_id = "test-db-id"
        session._message_manager = mock_manager

        result = await session._load_history_context()
        assert result is not None
        assert "<conversation-history>" in result
        assert "</conversation-history>" in result
        assert "**User:** Hello there" in result
        assert "**Assistant:** Hi! How can I help?" in result
        assert "**User:** Tell me about Python" in result

    @pytest.mark.asyncio
    async def test_load_history_context_truncates_long_messages(self, session: ChatSession) -> None:
        """Messages longer than 2000 chars should be truncated."""
        long_text = "x" * 3000
        mock_manager = AsyncMock()
        mock_manager.get_messages.return_value = [
            {"role": "user", "content_type": "text", "content": long_text},
        ]
        session.db_session_id = "test-db-id"
        session._message_manager = mock_manager

        result = await session._load_history_context()
        assert result is not None
        # 2000 chars + "..." = truncated
        assert "x" * 2000 + "..." in result
        assert "x" * 2001 not in result

    @pytest.mark.asyncio
    async def test_load_history_context_filters_non_text(self, session: ChatSession) -> None:
        """Tool use and tool result messages should be excluded."""
        mock_manager = AsyncMock()
        mock_manager.get_messages.return_value = [
            {"role": "user", "content_type": "text", "content": "Do something"},
            {"role": "assistant", "content_type": "tool_use", "content": '{"name": "Read"}'},
            {"role": "user", "content_type": "tool_result", "content": "file contents"},
            {"role": "assistant", "content_type": "text", "content": "Done!"},
        ]
        session.db_session_id = "test-db-id"
        session._message_manager = mock_manager

        result = await session._load_history_context()
        assert result is not None
        assert "Do something" in result
        assert "Done!" in result
        assert "Read" not in result
        assert "file contents" not in result

    @pytest.mark.asyncio
    async def test_load_history_context_empty_messages(self, session: ChatSession) -> None:
        """Returns None when no messages exist."""
        mock_manager = AsyncMock()
        mock_manager.get_messages.return_value = []
        session.db_session_id = "test-db-id"
        session._message_manager = mock_manager

        result = await session._load_history_context()
        assert result is None

    @pytest.mark.asyncio
    async def test_load_history_context_respects_total_limit(self, session: ChatSession) -> None:
        """History should stop before exceeding 30KB total."""
        mock_manager = AsyncMock()
        # Each message is ~1100 chars, 30 messages = ~33KB > 30KB limit
        mock_manager.get_messages.return_value = [
            {"role": "user", "content_type": "text", "content": "a" * 1100}
            for _ in range(30)
        ]
        session.db_session_id = "test-db-id"
        session._message_manager = mock_manager

        result = await session._load_history_context()
        assert result is not None
        # Should have fewer than 30 entries due to 30KB cap
        count = result.count("**User:**")
        assert count < 30
        assert count > 0

    @pytest.mark.asyncio
    async def test_load_history_context_handles_error(self, session: ChatSession) -> None:
        """Returns None on error instead of raising."""
        mock_manager = AsyncMock()
        mock_manager.get_messages.side_effect = RuntimeError("DB error")
        session.db_session_id = "test-db-id"
        session._message_manager = mock_manager

        result = await session._load_history_context()
        assert result is None
