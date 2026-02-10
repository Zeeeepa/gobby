"""WebSocket chat message handling.

ChatMixin provides chat session management and streaming for WebSocketServer.
Extracted from server.py as part of the Strangler Fig decomposition.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from websockets.exceptions import ConnectionClosed, ConnectionClosedError

from gobby.servers.chat_session import ChatSession
from gobby.servers.websocket.models import (
    CLEANUP_INTERVAL_SECONDS,
    IDLE_TIMEOUT_SECONDS,
)
from gobby.utils.machine_id import get_machine_id

logger = logging.getLogger(__name__)


class ChatMixin:
    """Mixin providing chat handler methods for WebSocketServer.

    Requires on the host class:
    - ``self.clients: dict[Any, dict[str, Any]]``
    - ``self._chat_sessions: dict[str, ChatSession]``
    - ``self._active_chat_tasks: dict[str, asyncio.Task[None]]``
    - ``self._send_error(...)`` (from HandlerMixin)
    """

    clients: dict[Any, dict[str, Any]]
    _chat_sessions: dict[str, ChatSession]
    _active_chat_tasks: dict[str, asyncio.Task[None]]

    # Provided by HandlerMixin – declared here only for type checking
    # to avoid shadowing the real implementation at runtime (MRO).
    if TYPE_CHECKING:

        async def _send_error(
            self,
            websocket: Any,
            message: str,
            request_id: str | None = None,
            code: str = "ERROR",
        ) -> None: ...

    async def _cancel_active_chat(self, conversation_id: str) -> None:
        """Cancel any active chat streaming task for a conversation.

        Attempts a graceful interrupt first so the SDK can clean up its
        internal task group, then force-cancels if the task is still running.
        """
        session = self._chat_sessions.get(conversation_id)
        if session:
            try:
                await asyncio.wait_for(session.interrupt(), timeout=0.5)
            except (TimeoutError, Exception):
                pass

        active_task = self._active_chat_tasks.pop(conversation_id, None)
        if active_task and not active_task.done():
            active_task.cancel()
            try:
                await active_task
            except asyncio.CancelledError:
                pass

    async def _handle_stop_chat(self, websocket: Any, data: dict[str, Any] | None = None) -> None:
        """
        Handle stop_chat message to cancel the active chat stream.

        Message format:
        {
            "type": "stop_chat",
            "conversation_id": "optional-id"
        }
        """
        conversation_id = (data or {}).get("conversation_id")

        if conversation_id:
            await self._cancel_active_chat(conversation_id)
        else:
            # Legacy: stop all active chats (backwards compatibility)
            for conv_id in list(self._active_chat_tasks.keys()):
                await self._cancel_active_chat(conv_id)

    async def _handle_chat_message(self, websocket: Any, data: dict[str, Any]) -> None:
        """
        Handle chat_message using a persistent ClaudeSDKClient-backed ChatSession.

        Sessions are keyed by conversation_id (stable across reconnections).
        Each session maintains full multi-turn context including tool calls.

        Message format:
        {
            "type": "chat_message",
            "content": "user message",
            "message_id": "client-generated-id",
            "conversation_id": "optional-stable-id",
            "model": "optional-model-override",
            "request_id": "client-uuid-for-stream-correlation"
        }

        Response format (streamed):
        {
            "type": "chat_stream",
            "message_id": "assistant-uuid",
            "conversation_id": "stable-id",
            "request_id": "echoed-client-uuid",
            "content": "chunk of text",
            "done": false
        }

        Tool status format:
        {
            "type": "tool_status",
            "message_id": "assistant-uuid",
            "conversation_id": "stable-id",
            "tool_call_id": "unique-id",
            "status": "calling" | "completed" | "error",
            "tool_name": "mcp__gobby-tasks__create_task",
            "server_name": "gobby-tasks",
            "arguments": {...},
            "result": {...},
            "error": "..."
        }

        Args:
            websocket: Client WebSocket connection
            data: Parsed chat message
        """
        content: str | list[dict[str, Any]] = data.get("content", "")
        content_blocks = data.get("content_blocks")
        conversation_id = data.get("conversation_id") or str(uuid4())
        model = data.get("model")
        request_id = data.get("request_id", "")

        # Use content_blocks (multimodal) if provided, otherwise plain text
        if content_blocks and isinstance(content_blocks, list):
            content = content_blocks
        elif not content or not isinstance(content, str) or not content.strip():
            await self._send_error(websocket, "Missing or invalid 'content' field")
            return

        client_info = self.clients.get(websocket)
        if not client_info:
            logger.warning("Chat message from unregistered client")
            return

        # Cancel any active stream for this conversation
        await self._cancel_active_chat(conversation_id)

        # Run streaming as a cancellable task
        task = asyncio.create_task(
            self._stream_chat_response(websocket, conversation_id, content, model, request_id)
        )
        task.add_done_callback(self._on_chat_task_done)
        self._active_chat_tasks[conversation_id] = task

    def _on_chat_task_done(self, task: asyncio.Task) -> None:  # type: ignore[type-arg]
        """Log unhandled exceptions from chat tasks."""
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error("Unhandled exception in chat task", exc_info=exc)

    async def _stream_chat_response(
        self,
        websocket: Any,
        conversation_id: str,
        content: str | list[dict[str, Any]],
        model: str | None,
        request_id: str = "",
    ) -> None:
        """Stream a ChatSession response to the client. Runs as a cancellable task."""
        from gobby.llm.claude_models import (
            DoneEvent,
            TextChunk,
            ThinkingEvent,
            ToolCallEvent,
            ToolResultEvent,
        )

        assistant_message_id = f"assistant-{uuid4().hex[:12]}"

        def _base_msg(**fields: Any) -> dict[str, Any]:
            """Build a response dict, always including request_id for stream correlation."""
            msg: dict[str, Any] = fields
            msg["request_id"] = request_id
            return msg

        gen: AsyncIterator[Any] | None = None
        try:
            # Get or create ChatSession for this conversation
            session = self._chat_sessions.get(conversation_id)
            if session is None:
                session = ChatSession(conversation_id=conversation_id)
                try:
                    await session.start(model=model)
                except Exception as e:
                    logger.error(f"Failed to start chat session: {e}")
                    await websocket.send(
                        json.dumps(
                            _base_msg(
                                type="chat_error",
                                message_id=assistant_message_id,
                                conversation_id=conversation_id,
                                error=f"Failed to start chat session: {e}",
                            )
                        )
                    )
                    return
                self._chat_sessions[conversation_id] = session

                # Register in database so it appears in session list
                session_manager = getattr(self, "session_manager", None)
                if session_manager:
                    try:
                        db_session = session_manager.register(
                            external_id=conversation_id,
                            machine_id=get_machine_id(),
                            source="web-chat",
                            project_id="",
                        )
                        session.db_session_id = db_session.id
                    except Exception as e:
                        logger.warning(f"Failed to register web-chat session in DB: {e}")

            elif model and session.model and model != session.model:
                # Mid-conversation model switch
                old_model = session.model
                try:
                    await session.switch_model(model)
                    await websocket.send(
                        json.dumps(
                            {
                                "type": "model_switched",
                                "conversation_id": conversation_id,
                                "old_model": old_model,
                                "new_model": model,
                            }
                        )
                    )
                except Exception as e:
                    logger.warning(f"Failed to switch model to {model}: {e}")
                    await websocket.send(
                        json.dumps(
                            _base_msg(
                                type="chat_error",
                                message_id=assistant_message_id,
                                conversation_id=conversation_id,
                                error=f"Failed to switch model: {e}",
                            )
                        )
                    )

            # Stream events from ChatSession.
            # Hold a reference to the generator so we can explicitly aclose()
            # it in the finally block — this prevents Python's GC from
            # finalizing it in a different asyncio task (which triggers
            # RuntimeError from anyio cancel scope mismatch).
            gen = session.send_message(content)
            async for event in gen:
                if isinstance(event, ThinkingEvent):
                    await websocket.send(
                        json.dumps(
                            _base_msg(
                                type="chat_thinking",
                                message_id=assistant_message_id,
                                conversation_id=conversation_id,
                                content=event.content,
                            )
                        )
                    )
                elif isinstance(event, TextChunk):
                    await websocket.send(
                        json.dumps(
                            _base_msg(
                                type="chat_stream",
                                message_id=assistant_message_id,
                                conversation_id=conversation_id,
                                content=event.content,
                                done=False,
                            )
                        )
                    )
                elif isinstance(event, ToolCallEvent):
                    await websocket.send(
                        json.dumps(
                            _base_msg(
                                type="tool_status",
                                message_id=assistant_message_id,
                                conversation_id=conversation_id,
                                tool_call_id=event.tool_call_id,
                                status="calling",
                                tool_name=event.tool_name,
                                server_name=event.server_name,
                                arguments=event.arguments,
                            )
                        )
                    )
                elif isinstance(event, ToolResultEvent):
                    await websocket.send(
                        json.dumps(
                            _base_msg(
                                type="tool_status",
                                message_id=assistant_message_id,
                                conversation_id=conversation_id,
                                tool_call_id=event.tool_call_id,
                                status="completed" if event.success else "error",
                                result=event.result,
                                error=event.error,
                            )
                        )
                    )
                elif isinstance(event, DoneEvent):
                    await websocket.send(
                        json.dumps(
                            _base_msg(
                                type="chat_stream",
                                message_id=assistant_message_id,
                                conversation_id=conversation_id,
                                content="",
                                done=True,
                                tool_calls_count=event.tool_calls_count,
                            )
                        )
                    )

        except asyncio.CancelledError:
            # Stream was interrupted (stop button or new message replacing old)
            try:
                await websocket.send(
                    json.dumps(
                        _base_msg(
                            type="chat_stream",
                            message_id=assistant_message_id,
                            conversation_id=conversation_id,
                            content="",
                            done=True,
                            interrupted=True,
                        )
                    )
                )
            except (ConnectionClosed, ConnectionClosedError):
                pass

        except (ConnectionClosed, ConnectionClosedError):
            # Client disconnected mid-stream — not an error
            logger.debug(f"Client disconnected during chat stream for {conversation_id}")

        except Exception:
            logger.exception(f"Chat error for conversation {conversation_id}")
            try:
                await websocket.send(
                    json.dumps(
                        _base_msg(
                            type="chat_error",
                            message_id=assistant_message_id,
                            conversation_id=conversation_id,
                            error="An internal error occurred",
                        )
                    )
                )
            except (ConnectionClosed, ConnectionClosedError):
                pass

        finally:
            # Explicitly close the async generator in THIS task to prevent
            # Python's GC from finalizing it in a different asyncio task
            # (which causes RuntimeError from anyio cancel scope mismatch).
            if gen is not None:
                _aclose = getattr(gen, "aclose", None)
                if _aclose is not None:
                    try:
                        await _aclose()
                    except BaseException:
                        pass
            self._active_chat_tasks.pop(conversation_id, None)

    async def _handle_ask_user_response(self, websocket: Any, data: dict[str, Any]) -> None:
        """Handle ask_user_response message from the web UI.

        Looks up the ChatSession by conversation_id and forwards the user's
        answers to unblock the pending AskUserQuestion callback.
        """
        conversation_id = data.get("conversation_id")
        answers = data.get("answers", {})

        session = self._chat_sessions.get(conversation_id) if conversation_id else None
        if session is None:
            logger.warning(f"ask_user_response for unknown conversation: {conversation_id}")
            return

        if not session.has_pending_question:
            logger.warning(f"ask_user_response but no pending question for {conversation_id}")
            return

        session.provide_answer(answers)

    async def _cleanup_idle_sessions(self) -> None:
        """Periodically disconnect chat sessions that have been idle too long."""
        while True:
            try:
                await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
                now = datetime.now(UTC)
                stale_ids = [
                    conv_id
                    for conv_id, session in self._chat_sessions.items()
                    if (now - session.last_activity).total_seconds() > IDLE_TIMEOUT_SECONDS
                ]
                for conv_id in stale_ids:
                    session = self._chat_sessions.pop(conv_id)
                    await self._cancel_active_chat(conv_id)
                    # Mark as paused in database before stopping
                    if session.db_session_id:
                        session_manager = getattr(self, "session_manager", None)
                        if session_manager:
                            try:
                                session_manager.update(session.db_session_id, status="paused")
                            except Exception as e:
                                logger.warning(f"Failed to update session status: {e}")
                    await session.stop()
                    logger.debug(f"Cleaned up idle chat session {conv_id}")
                if stale_ids:
                    logger.info(f"Cleaned up {len(stale_ids)} idle chat session(s)")
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in idle session cleanup")
