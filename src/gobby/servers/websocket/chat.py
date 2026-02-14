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

from gobby.hooks.events import HookEvent, HookEventType, HookResponse, SessionSource
from gobby.servers.chat_session import ChatSession
from gobby.servers.websocket.models import (
    CLEANUP_INTERVAL_SECONDS,
    IDLE_TIMEOUT_SECONDS,
)
from gobby.sessions.transcripts.base import ParsedMessage
from gobby.storage.projects import PERSONAL_PROJECT_ID
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
        After the task is cancelled, drains any stale response events from
        the SDK to prevent the off-by-one bug where the next query's
        ``receive_response()`` returns leftover events from the interrupted
        turn.
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
            # Let the SDK settle after interrupt+cancellation.
            # Without this pause, an immediate query() can get an empty
            # response because the SDK hasn't finished its internal cleanup.
            await asyncio.sleep(0.1)

        # Drain any stale response events buffered in the SDK.
        # Without this, receive_response() on the *next* query returns
        # leftover events from this interrupted turn (off-by-one bug).
        if session:
            await session.drain_pending_response()

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

    async def _create_chat_session(
        self,
        conversation_id: str,
        model: str | None = None,
        project_id: str | None = None,
    ) -> ChatSession:
        """Create and bootstrap a new ChatSession with lifecycle hooks wired."""
        session = ChatSession(conversation_id=conversation_id)

        # Wire lifecycle callbacks before start() so hooks are registered with the SDK
        session._on_before_agent = lambda data: self._fire_lifecycle(
            conversation_id, HookEventType.BEFORE_AGENT, data
        )
        session._on_pre_tool = lambda data: self._fire_lifecycle(
            conversation_id, HookEventType.BEFORE_TOOL, data
        )
        session._on_post_tool = lambda data: self._fire_lifecycle(
            conversation_id, HookEventType.AFTER_TOOL, data
        )
        session._on_pre_compact = lambda data: self._fire_lifecycle(
            conversation_id, HookEventType.PRE_COMPACT, data
        )
        session._on_stop = lambda data: self._fire_lifecycle(
            conversation_id, HookEventType.STOP, data
        )

        await session.start(model=model)
        self._chat_sessions[conversation_id] = session

        # Register in database so it appears in session list
        session_manager = getattr(self, "session_manager", None)
        if session_manager:
            try:
                db_session = await asyncio.to_thread(
                    session_manager.register,
                    external_id=conversation_id,
                    machine_id=get_machine_id(),
                    source="claude_sdk_web_chat",
                    project_id=project_id or PERSONAL_PROJECT_ID,
                )
                session.db_session_id = db_session.id
                logger.info(
                    f"Registered web-chat session {db_session.id} "
                    f"(conv={conversation_id[:8]}, project={project_id or PERSONAL_PROJECT_ID})"
                )
            except Exception as e:
                logger.warning(f"Failed to register web-chat session in DB: {e}")

        return session

    async def _fire_lifecycle(
        self,
        conversation_id: str,
        event_type: HookEventType,
        data: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Bridge SDK hook events to workflow engine lifecycle triggers.

        Returns a dict with HookResponse fields (decision, context, reason, etc.)
        or None if no workflow handler is available.
        """
        workflow_handler = getattr(self, "workflow_handler", None)
        if not workflow_handler:
            return None

        # Use the database session ID (not the external conversation_id) so that
        # workflow actions like synthesize_title can look up the session via
        # session_manager.get(session_id).
        session = self._chat_sessions.get(conversation_id)
        db_session_id = getattr(session, "db_session_id", None) or conversation_id

        event = HookEvent(
            event_type=event_type,
            session_id=db_session_id,
            source=SessionSource.CLAUDE_SDK_WEB_CHAT,
            timestamp=datetime.now(UTC),
            data=data,
            metadata={"_platform_session_id": conversation_id},
        )

        try:
            # WorkflowHookHandler.evaluate is sync (bridges to async internally)
            response: HookResponse = await asyncio.to_thread(workflow_handler.evaluate, event)
            return {
                "decision": response.decision,
                "context": response.context,
                "reason": response.reason,
                "system_message": response.system_message,
            }
        except Exception as e:
            logger.error(f"Lifecycle evaluation failed for {event_type}: {e}", exc_info=True)
            return None

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
        project_id = data.get("project_id")

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
            self._stream_chat_response(
                websocket, conversation_id, content, model, request_id, project_id
            )
        )
        task.add_done_callback(self._on_chat_task_done)
        self._active_chat_tasks[conversation_id] = task

    def _on_chat_task_done(self, task: asyncio.Task[None]) -> None:
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
        project_id: str | None = None,
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
        accumulated_text = ""

        def _base_msg(**fields: Any) -> dict[str, Any]:
            """Build a response dict, always including request_id for stream correlation."""
            msg: dict[str, Any] = fields
            msg["request_id"] = request_id
            return msg

        async def _persist_message(session: Any, role: str, text: str) -> None:
            """Persist a chat message to the database (best-effort)."""
            message_manager = getattr(self, "message_manager", None)
            db_sid = getattr(session, "db_session_id", None)
            if not message_manager or not db_sid or not text:
                return
            try:
                idx = session.message_index
                session.message_index = idx + 1
                msg = ParsedMessage(
                    index=idx,
                    role=role,
                    content=text,
                    content_type="text",
                    tool_name=None,
                    tool_input=None,
                    tool_result=None,
                    timestamp=datetime.now(UTC),
                    raw_json={},
                )
                await message_manager.store_messages(db_sid, [msg])
            except Exception as e:
                logger.warning(f"Failed to persist {role} message for {conversation_id[:8]}: {e}")

        gen: AsyncIterator[Any] | None = None
        try:
            # Get or create ChatSession for this conversation
            session = self._chat_sessions.get(conversation_id)
            if session is None:
                try:
                    session = await self._create_chat_session(
                        conversation_id, model=model, project_id=project_id
                    )
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

            # Persist user message to database
            user_text = content if isinstance(content, str) else json.dumps(content)
            await _persist_message(session, "user", user_text)

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
                    accumulated_text += event.content
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
                    # Feed TTS if voice mode is active
                    _voice_hook = getattr(self, "_voice_tts_hook", None)
                    if _voice_hook:
                        await _voice_hook(websocket, conversation_id, request_id, event.content)
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
                    # Persist assistant message to database
                    await _persist_message(session, "assistant", accumulated_text)

                    # Flush TTS if voice mode is active
                    _voice_flush = getattr(self, "_voice_tts_flush", None)
                    if _voice_flush:
                        await _voice_flush(websocket, conversation_id, request_id)

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

    async def _handle_clear_chat(self, websocket: Any, data: dict[str, Any]) -> None:
        """Handle clear_chat message: stop session, mark completed, notify frontend.

        Message format:
        {
            "type": "clear_chat",
            "conversation_id": "stable-id"
        }
        """
        conversation_id = data.get("conversation_id")
        if not conversation_id:
            return

        session = self._chat_sessions.get(conversation_id)
        if not session:
            # No active session — just acknowledge
            await websocket.send(
                json.dumps({"type": "chat_cleared", "conversation_id": conversation_id})
            )
            return

        # Mark session as completed in database
        if session.db_session_id:
            session_manager = getattr(self, "session_manager", None)
            if session_manager:
                try:
                    await asyncio.to_thread(
                        session_manager.update, session.db_session_id, status="completed"
                    )
                except Exception as e:
                    logger.warning(f"Failed to update session status on clear: {e}")

        # Stop the old ChatSession
        await self._cancel_active_chat(conversation_id)
        await session.stop()
        self._chat_sessions.pop(conversation_id, None)

        # Notify frontend
        await websocket.send(
            json.dumps({"type": "chat_cleared", "conversation_id": conversation_id})
        )
        logger.info(f"Chat cleared for conversation {conversation_id[:8]}")

    async def _handle_delete_chat(self, websocket: Any, data: dict[str, Any]) -> None:
        """Handle delete_chat message: stop session, delete from DB, notify frontend.

        Message format:
        {
            "type": "delete_chat",
            "conversation_id": "stable-id"
        }
        """
        conversation_id = data.get("conversation_id")
        if not conversation_id:
            return

        session = self._chat_sessions.get(conversation_id)
        db_session_id = getattr(session, "db_session_id", None) if session else None

        # Stop the ChatSession if active
        if session:
            await self._cancel_active_chat(conversation_id)
            await session.stop()
            self._chat_sessions.pop(conversation_id, None)

        # Delete from database
        if db_session_id:
            session_manager = getattr(self, "session_manager", None)
            message_manager = getattr(self, "message_manager", None)
            try:
                if message_manager:
                    await asyncio.to_thread(
                        message_manager.db.execute,
                        "DELETE FROM session_messages WHERE session_id = ?",
                        (db_session_id,),
                    )
                if session_manager:
                    await asyncio.to_thread(session_manager.delete, db_session_id)
            except Exception as e:
                logger.warning(f"Failed to delete session from DB: {e}")

        # Notify frontend
        await websocket.send(
            json.dumps({"type": "chat_deleted", "conversation_id": conversation_id})
        )
        logger.info(f"Chat deleted for conversation {conversation_id[:8]}")

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
                                await asyncio.to_thread(
                                    session_manager.update, session.db_session_id, status="paused"
                                )
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
