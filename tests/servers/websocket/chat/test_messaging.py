"""Tests for WebSocket ChatMessagingMixin."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from websockets.exceptions import ConnectionClosed

from gobby.servers.websocket.chat._messaging import ChatMessagingMixin
from gobby.hooks.events import HookEventType
from gobby.llm.claude_models import (
    DoneEvent,
    TextChunk,
    ThinkingEvent,
    ToolCallEvent,
    ToolResultEvent,
)

pytestmark = pytest.mark.unit

class DummyMessagingMixin(ChatMessagingMixin):
    def __init__(self):
        self.clients = {}
        self._chat_sessions = {}
        self._active_chat_tasks = {}
        self._pending_modes = {}
        self._pending_worktree_paths = {}
        self._pending_agents = {}
        self.session_manager = None
        self.inter_session_msg_manager = None

    async def _send_error(self, ws, msg, request_id=None, code="ERROR"):
        await ws.send(json.dumps({"error": msg}))

    async def _cancel_active_chat(self, cid):
        pass

    async def _create_chat_session(self, cid, model=None, project_id=None, resume_session_id=None):
        sess = AsyncMock()
        sess.db_session_id = "db-id"
        sess.model = "opus"
        self._chat_sessions[cid] = sess
        return sess

    async def broadcast_session_event(self, event, sid, **kwargs):
        pass

@pytest.fixture
def mixin() -> DummyMessagingMixin:
    return DummyMessagingMixin()

@pytest.fixture
def ws() -> AsyncMock:
    return AsyncMock()


class TestClassifyChatError:
    def test_classify(self, mixin: DummyMessagingMixin):
        msg, code = mixin._classify_chat_error(ValueError("429 rate_limit exceeded"))
        assert code == "RATE_LIMITED"

        msg, code = mixin._classify_chat_error(RuntimeError("auth failed 401"))
        assert code == "AUTH_ERROR"

        msg, code = mixin._classify_chat_error(TimeoutError("oops"))
        assert code == "TIMEOUT"

        msg, code = mixin._classify_chat_error(ConnectionError("lost connection"))
        assert code == "CONNECTION_ERROR"

        msg, code = mixin._classify_chat_error(RuntimeError("unknown issue"))
        assert code == "INTERNAL_ERROR"

class TestInjectPendingMessages:
    def test_inject_wrong_event(self, mixin: DummyMessagingMixin):
        assert mixin._inject_pending_messages("1", HookEventType.SESSION_START) is None

    def test_inject_no_manager(self, mixin: DummyMessagingMixin):
        # Already set to None in Dummy init
        assert mixin._inject_pending_messages("1", HookEventType.BEFORE_AGENT) is None

    def test_inject_success(self, mixin: DummyMessagingMixin):
        mixin.inter_session_msg_manager = MagicMock()
        
        msg1 = MagicMock()
        msg1.id = "1"
        msg1.message_type = "web_chat"
        msg1.from_session = "1234567890"
        msg1.content = "hello"
        
        msg2 = MagicMock()
        msg2.id = "2"
        msg2.message_type = "p2p"
        msg2.priority = "urgent"
        msg2.from_session = None
        msg2.content = "help me"
        
        mixin.inter_session_msg_manager.get_undelivered_messages.return_value = [msg1, msg2]
        
        res = mixin._inject_pending_messages("sid", HookEventType.BEFORE_AGENT)
        
        assert res is not None
        assert "Pending messages from web chat user" in res
        assert "- Session 12345678: hello" in res
        assert "Pending P2P messages from other sessions" in res
        assert "- [URGENT] help me" in res
        
        mixin.inter_session_msg_manager.mark_delivered.assert_any_call("1")
        mixin.inter_session_msg_manager.mark_delivered.assert_any_call("2")

class TestHandleChatMessage:
    @pytest.mark.asyncio
    async def test_no_content(self, mixin: DummyMessagingMixin, ws: AsyncMock):
        await mixin._handle_chat_message(ws, {"content": ""})
        ws.send.assert_called_once()
        assert "Missing or invalid 'content' field" in ws.send.call_args[0][0]

    @pytest.mark.asyncio
    async def test_unregistered_client(self, mixin: DummyMessagingMixin, ws: AsyncMock):
        # mixin.clients is empty
        await mixin._handle_chat_message(ws, {"content": "hi"})
        # Should return silently after warning log
        assert not ws.send.called

    @pytest.mark.asyncio
    async def test_success_dispatch(self, mixin: DummyMessagingMixin, ws: AsyncMock):
        mixin.clients[ws] = {}
        
        with patch.object(mixin, "_stream_chat_response", new_callable=AsyncMock) as mock_stream:
            await mixin._handle_chat_message(ws, {"content": "hi", "conversation_id": "c1"})
            
            # Since task runs async, let event loop tick
            await asyncio.sleep(0.01)
            
            mock_stream.assert_awaited_once_with(
                ws, "c1", "hi", None, "", None, inject_context=None
            )
            assert "c1" in mixin._active_chat_tasks
            assert mixin.clients[ws]["conversation_id"] == "c1"


class TestStreamChatResponse:
    @pytest.mark.asyncio
    async def test_stream_model_switch(self, mixin: DummyMessagingMixin, ws: AsyncMock):
        mixin.clients[ws] = {"conversation_id": "c1"}
        session = AsyncMock()
        session.model = "opus"
        mixin._chat_sessions["c1"] = session
        
        async def dummy_generator(text):
            yield DoneEvent(sdk_session_id="sdk", input_tokens=10, output_tokens=5, tool_calls_count=0)
            
        session.send_message.return_value = dummy_generator("hi")
        
        await mixin._stream_chat_response(ws, "c1", "hi", "sonnet")
        
        session.switch_model.assert_awaited_once_with("sonnet")
        # Validate model switch message sent
        messages = [call[0][0] for call in ws.send.call_args_list]
        assert any("model_switched" in msg and "sonnet" in msg for msg in messages)

    @pytest.mark.asyncio
    async def test_stream_events(self, mixin: DummyMessagingMixin, ws: AsyncMock):
        mixin.clients[ws] = {"conversation_id": "c1"}
        session = AsyncMock()
        mixin._chat_sessions["c1"] = session
        
        async def mock_stream(content):
            yield ThinkingEvent(content="hmm")
            yield TextChunk(content="text block")
            yield ToolCallEvent(tool_call_id="call1", tool_name="read", server_name="srv", arguments={"p": 1})
            yield ToolResultEvent(tool_call_id="call1", result="ok", success=True)
            yield DoneEvent(sdk_session_id="sdk", input_tokens=10, output_tokens=5, tool_calls_count=1)
        
        session.send_message.return_value = mock_stream("hi")
        
        await mixin._stream_chat_response(ws, "c1", "hi", None)
        
        msgs = []
        for call in ws.send.call_args_list:
            msgs.append(json.loads(call[0][0]))
            
        types = [m.get("type") for m in msgs]
        assert "chat_thinking" in types
        assert "chat_stream" in types
        assert "tool_status" in types
        
        # Verify done event handling rekeys the session dict
        assert "c1" not in mixin._chat_sessions
        assert "sdk" in mixin._chat_sessions

    @pytest.mark.asyncio
    async def test_stream_cancellation_safely(self, mixin: DummyMessagingMixin, ws: AsyncMock):
        mixin.clients[ws] = {"conversation_id": "c1"}
        session = AsyncMock()
        mixin._chat_sessions["c1"] = session
        
        async def canceling_stream(content):
            raise asyncio.CancelledError()
            yield None
            
        session.send_message.return_value = canceling_stream("hi")
        
        await mixin._stream_chat_response(ws, "c1", "hi", None)
        
        msgs = [json.loads(c[0][0]) for c in ws.send.call_args_list]
        done_msg = [m for m in msgs if m.get("done") is True]
        assert len(done_msg) == 1
        assert done_msg[0]["interrupted"] is True

    @pytest.mark.asyncio
    async def test_stream_client_disconnect(self, mixin: DummyMessagingMixin, ws: AsyncMock):
        mixin.clients[ws] = {"conversation_id": "c1"}
        session = AsyncMock()
        mixin._chat_sessions["c1"] = session
        
        async def dummy_stream(content):
            yield ThinkingEvent(content="hmm")
            
        session.send_message.return_value = dummy_stream("hi")
        
        ws.send.side_effect = ConnectionClosed(None, None)
        
        # Should catch gracefully and not propagate
        await mixin._stream_chat_response(ws, "c1", "hi", None)
