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
from gobby.sessions.transcripts.base import ParsedMessage
from gobby.storage.projects import PERSONAL_PROJECT_ID
from gobby.utils.machine_id import get_machine_id

logger = logging.getLogger(__name__)


async def _resolve_git_branch(project_path: str | None) -> tuple[str | None, str | None]:
    """Resolve the current git branch for a project directory.

    Returns (branch_name, worktree_path). branch_name is None for detached HEAD
    or non-git directories.
    """
    if not project_path:
        return None, None
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "branch",
            "--show-current",
            cwd=project_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        branch = stdout.decode().strip() or None
        # For detached HEAD, show short SHA instead of nothing
        if not branch:
            proc2 = await asyncio.create_subprocess_exec(
                "git",
                "rev-parse",
                "--short",
                "HEAD",
                cwd=project_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout2, _ = await asyncio.wait_for(proc2.communicate(), timeout=5.0)
            short_sha = stdout2.decode().strip()
            if short_sha:
                branch = f"detached:{short_sha}"
        return branch, project_path
    except Exception:
        return None, None


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
    _pending_modes: dict[str, str]
    _pending_worktree_paths: dict[str, str]

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

        # Wire mode-change callback so agent-initiated plan mode transitions
        # (EnterPlanMode/ExitPlanMode) are broadcast to all connected clients
        async def _notify_mode_changed(mode: str, reason: str) -> None:
            msg = json.dumps(
                {
                    "type": "mode_changed",
                    "conversation_id": conversation_id,
                    "mode": mode,
                    "reason": reason,
                }
            )
            for ws in list(self.clients.keys()):
                try:
                    await ws.send(msg)
                except (ConnectionClosed, ConnectionClosedError):
                    pass

        session._on_mode_changed = _notify_mode_changed

        # Wire plan-ready callback so ExitPlanMode sends plan content to frontend
        async def _notify_plan_ready(content: str | None, input_data: dict[str, Any]) -> None:
            msg = json.dumps(
                {
                    "type": "plan_pending_approval",
                    "conversation_id": conversation_id,
                    "plan_content": content,
                    "allowed_prompts": input_data.get("allowedPrompts"),
                }
            )
            for ws in list(self.clients.keys()):
                try:
                    await ws.send(msg)
                except (ConnectionClosed, ConnectionClosedError):
                    pass

        session._on_plan_ready = _notify_plan_ready

        # Wire tool approval config if available
        daemon_cfg = getattr(self, "daemon_config", None)
        if daemon_cfg is not None:
            tool_approval_cfg = getattr(daemon_cfg, "tool_approval", None)
            if tool_approval_cfg is not None and tool_approval_cfg.enabled:
                session._tool_approval_config = tool_approval_cfg

        # Apply pending chat mode (set before session existed)
        pending_modes = getattr(self, "_pending_modes", {})
        pending_mode = pending_modes.pop(conversation_id, None)
        if pending_mode:
            session.chat_mode = pending_mode
        else:
            # Apply configured default from daemon config
            if daemon_cfg is not None:
                chat_cfg = getattr(daemon_cfg, "chat", None)
                if chat_cfg is not None:
                    session.chat_mode = chat_cfg.default_mode

        # Set project context on session BEFORE start() so env vars and CWD
        # are correctly configured for the CLI subprocess.
        effective_pid = project_id or PERSONAL_PROJECT_ID
        session.project_id = effective_pid

        # Register in database BEFORE start() so that db_session_id is available
        # for the CLI subprocess env vars (GOBBY_SESSION_ID) during start().
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
                session.seq_num = db_session.seq_num
                logger.info(
                    f"Registered web-chat session {db_session.id} "
                    f"(conv={conversation_id[:8]}, project={project_id or PERSONAL_PROJECT_ID})"
                )
            except Exception as e:
                logger.warning(f"Failed to register web-chat session in DB: {e}")

        # Look up repo_path from DB so the subprocess CWD matches the selected project
        if session_manager and not session.project_path:
            try:
                from gobby.storage.projects import LocalProjectManager

                pm = LocalProjectManager(session_manager.db)
                project = pm.get(effective_pid)
                if project and project.repo_path:
                    session.project_path = project.repo_path
            except Exception as e:
                logger.warning(f"Failed to look up project repo_path: {e}")

        # Override project_path with pending worktree path (from set_worktree)
        pending_wt = getattr(self, "_pending_worktree_paths", {})
        wt_override = pending_wt.pop(conversation_id, None)
        if wt_override:
            session.project_path = wt_override

        await session.start(model=model)
        self._chat_sessions[conversation_id] = session

        # Detect returning sessions and set up history injection
        message_manager = getattr(self, "message_manager", None)
        if message_manager and session.db_session_id:
            try:
                max_idx = await message_manager.get_max_message_index(session.db_session_id)
                if max_idx >= 0:
                    session.message_index = max_idx + 1
                    session._needs_history_injection = True
                    session._message_manager = message_manager
                    logger.info(
                        "Returning session detected; history injection enabled",
                        extra={"max_idx": max_idx, "conversation_id": conversation_id[:8]},
                    )
            except Exception as e:
                logger.warning(
                    "Failed to check message history",
                    extra={"conversation_id": conversation_id[:8]},
                    exc_info=e,
                )

        # Fire SESSION_START (informational, fire-and-forget)
        asyncio.create_task(self._fire_lifecycle(conversation_id, HookEventType.SESSION_START, {}))

        return session

    async def _fire_session_end(self, conversation_id: str) -> None:
        """Fire SESSION_END event for a chat session (best-effort).

        Called before session cleanup in clear, delete, idle cleanup, and
        server shutdown paths to maintain parity with CLI adapters.
        """
        try:
            await self._fire_lifecycle(conversation_id, HookEventType.SESSION_END, {})
        except Exception:
            logger.debug("SESSION_END fire failed for %s", conversation_id[:8], exc_info=True)

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
            logger.warning("_fire_lifecycle: workflow_handler is None for %s", event_type)
            return None

        # Use the database session ID (not the external conversation_id) so that
        # workflow actions can look up the session via session_manager.get(session_id).
        session = self._chat_sessions.get(conversation_id)
        db_session_id = getattr(session, "db_session_id", None) or conversation_id
        project_path = getattr(session, "project_path", None)

        # Normalize MCP fields using shared logic (same as CLI adapters)
        if data:
            from gobby.hooks.normalization import normalize_tool_fields

            data = normalize_tool_fields(data)

        event = HookEvent(
            event_type=event_type,
            session_id=db_session_id,
            source=SessionSource.CLAUDE_SDK_WEB_CHAT,
            timestamp=datetime.now(UTC),
            data=data,
            metadata={"_platform_session_id": db_session_id},
            cwd=project_path,
        )

        try:
            # DEBUG: log event data to diagnose hook issues
            logger.debug(
                "_fire_lifecycle: %s event_data=%s",
                event_type.name,
                {k: (v if k != "tool_input" else "...") for k, v in (data or {}).items()},
            )
            # WorkflowHookHandler.evaluate is sync (bridges to async internally)
            response: HookResponse = await asyncio.to_thread(workflow_handler.evaluate, event)
            logger.debug(
                "_fire_lifecycle: %s → decision=%s, context_len=%d",
                event_type.name,
                response.decision,
                len(response.context) if response.context else 0,
            )

            # Dispatch mcp_call effects from rule engine (parity with CLI path)
            mcp_calls = (response.metadata or {}).get("mcp_calls", [])
            if mcp_calls:
                mcp_manager = getattr(self, "mcp_manager", None)
                if mcp_manager:
                    from gobby.hooks.mcp_dispatch import dispatch_mcp_calls

                    await dispatch_mcp_calls(mcp_calls, event, mcp_manager.call_tool, logger)

            # Build result dict
            result: dict[str, Any] = {
                "decision": response.decision,
                "context": response.context,
                "reason": response.reason,
                "system_message": response.system_message,
            }

            # Session context enrichment (parity with CLI adapter)
            if session and getattr(session, "seq_num", None):
                session_ref = f"#{session.seq_num}"
                ctx = result.get("context")
                result["context"] = (
                    f"Gobby Session ID: {session_ref}\n\n{ctx}"
                    if ctx
                    else f"Gobby Session ID: {session_ref}"
                )

            return result
        except Exception as e:
            logger.error("Lifecycle evaluation failed for %s: %s", event_type, e, exc_info=True)
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
        after_tool_call = False  # Track tool→text transitions to prevent sentence collisions
        has_sent_text = False  # Survives accumulated_text flushes for separator injection

        def _base_msg(**fields: Any) -> dict[str, Any]:
            """Build a response dict, always including request_id for stream correlation."""
            msg: dict[str, Any] = fields
            msg["request_id"] = request_id
            return msg

        def _session_ref() -> str | None:
            """Get the session ref (#N) for the current conversation."""
            s = self._chat_sessions.get(conversation_id)
            if s and getattr(s, "seq_num", None):
                return f"#{s.seq_num}"
            return None

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

        async def _emit_pending_approval(tool_name: str, arguments: dict[str, Any]) -> None:
            """Emit pending_approval tool_status to the client."""
            try:
                await websocket.send(
                    json.dumps(
                        _base_msg(
                            type="tool_status",
                            message_id=assistant_message_id,
                            conversation_id=conversation_id,
                            tool_call_id=f"approval-{uuid4().hex[:8]}",
                            status="pending_approval",
                            tool_name=tool_name,
                            arguments=arguments,
                        )
                    )
                )
            except (ConnectionClosed, ConnectionClosedError):
                pass

        gen: AsyncIterator[Any] | None = None
        try:
            # Get or create ChatSession for this conversation
            session = self._chat_sessions.get(conversation_id)
            if session is None:
                try:
                    session = await self._create_chat_session(
                        conversation_id, model=model, project_id=project_id
                    )
                    # Notify client of session identity + branch context
                    ref = _session_ref()
                    session_info_msg = _base_msg(
                        type="session_info",
                        conversation_id=conversation_id,
                    )
                    if ref:
                        session_info_msg["session_ref"] = ref
                    branch, wt_path = await _resolve_git_branch(
                        getattr(session, "project_path", None)
                    )
                    if branch:
                        session_info_msg["current_branch"] = branch
                    if wt_path:
                        session_info_msg["worktree_path"] = wt_path
                    await websocket.send(json.dumps(session_info_msg))
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

            # Wire tool approval callback for this request
            session._tool_approval_callback = _emit_pending_approval

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
                    # Plan approval boundary — start a fresh message so
                    # post-approval text doesn't concatenate with pre-approval text.
                    content = event.content
                    session_obj = self._chat_sessions.get(conversation_id)
                    if session_obj and getattr(session_obj, "_plan_approval_completed", False):
                        session_obj._plan_approval_completed = False
                        if accumulated_text.strip():
                            await _persist_message(session, "assistant", accumulated_text)
                            accumulated_text = ""
                        assistant_message_id = f"assistant-{uuid4().hex[:12]}"
                        after_tool_call = False
                        has_sent_text = False
                    elif after_tool_call:
                        # Prevent sentence collisions after tool calls by injecting
                        # a separator when the model resumes text output.
                        # Without this: "What do you think?Ok, let me do that."
                        # With this:    "What do you think?\n\nOk, let me do that."
                        after_tool_call = False
                        if has_sent_text:
                            content = "\n\n" + content
                    if content.strip():
                        has_sent_text = True
                    accumulated_text += content
                    await websocket.send(
                        json.dumps(
                            _base_msg(
                                type="chat_stream",
                                message_id=assistant_message_id,
                                conversation_id=conversation_id,
                                content=content,
                                done=False,
                            )
                        )
                    )
                    # Feed TTS if voice mode is active
                    _voice_hook = getattr(self, "_voice_tts_hook", None)
                    if _voice_hook:
                        try:
                            await _voice_hook(websocket, conversation_id, request_id, event.content)
                        except Exception:
                            logger.debug("TTS hook error (non-fatal)", exc_info=True)
                elif isinstance(event, ToolCallEvent):
                    # Flush accumulated text as a separate message before tool calls.
                    # This prevents text segments from merging across tool boundaries
                    # (e.g., "Want me to test it?Good call." running together).
                    if accumulated_text.strip():
                        await _persist_message(session, "assistant", accumulated_text)
                        accumulated_text = ""
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
                    after_tool_call = True
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
                    # Persist remaining assistant text (after last tool call, if any)
                    if accumulated_text.strip():
                        await _persist_message(session, "assistant", accumulated_text)

                    # Flush TTS if voice mode is active
                    _voice_flush = getattr(self, "_voice_tts_flush", None)
                    if _voice_flush:
                        try:
                            await _voice_flush(websocket, conversation_id, request_id)
                        except Exception:
                            logger.debug("TTS flush error (non-fatal)", exc_info=True)

                    done_msg = _base_msg(
                        type="chat_stream",
                        message_id=assistant_message_id,
                        conversation_id=conversation_id,
                        content="",
                        done=True,
                        tool_calls_count=event.tool_calls_count,
                    )
                    ref = _session_ref()
                    if ref:
                        done_msg["session_ref"] = ref
                    # Include usage data if available.
                    # total_input_tokens = uncached + cache_read + cache_creation
                    # (the real context size; input_tokens alone is tiny with caching)
                    if event.total_input_tokens is not None or event.input_tokens is not None:
                        done_msg["usage"] = {
                            "input_tokens": event.input_tokens,
                            "output_tokens": event.output_tokens,
                            "cache_read_input_tokens": event.cache_read_input_tokens,
                            "cache_creation_input_tokens": event.cache_creation_input_tokens,
                            "total_input_tokens": event.total_input_tokens,
                        }
                    if event.context_window is not None:
                        done_msg["context_window"] = event.context_window
                    logger.info(
                        "DoneEvent context_window=%s total_input=%s "
                        "(uncached=%s cache_read=%s cache_creation=%s) output=%s",
                        event.context_window,
                        event.total_input_tokens,
                        event.input_tokens,
                        event.cache_read_input_tokens,
                        event.cache_creation_input_tokens,
                        event.output_tokens,
                    )

                    # Adopt SDK session_id as external_id (replaces temp frontend UUID)
                    sdk_sid = event.sdk_session_id
                    if sdk_sid:
                        done_msg["sdk_session_id"] = sdk_sid
                    if sdk_sid and sdk_sid != conversation_id:
                        # Update DB external_id
                        db_sid = getattr(session, "db_session_id", None)
                        session_mgr = getattr(self, "session_manager", None)
                        if db_sid and session_mgr:
                            try:
                                await asyncio.to_thread(
                                    session_mgr.update, db_sid, external_id=sdk_sid
                                )
                            except Exception:
                                logger.debug(
                                    "Failed to update external_id to SDK session_id for %s",
                                    db_sid,
                                    exc_info=True,
                                )
                        # Re-key in-memory dicts
                        self._chat_sessions[sdk_sid] = self._chat_sessions.pop(
                            conversation_id, session
                        )
                        if conversation_id in self._active_chat_tasks:
                            self._active_chat_tasks[sdk_sid] = self._active_chat_tasks.pop(
                                conversation_id
                            )
                        logger.info(
                            "Re-keyed web chat session %s → %s",
                            conversation_id[:8],
                            sdk_sid[:8],
                        )
                        conversation_id = sdk_sid

                    await websocket.send(json.dumps(done_msg))

                    # Persist usage to DB (best-effort)
                    db_sid = getattr(session, "db_session_id", None)
                    session_manager = getattr(self, "session_manager", None)
                    if db_sid and session_manager:
                        has_usage = (
                            event.total_input_tokens is not None or event.output_tokens is not None
                        )
                        if has_usage:
                            try:
                                prev_output = getattr(session, "_accumulated_output_tokens", 0)
                                new_output = prev_output + (event.output_tokens or 0)
                                session._accumulated_output_tokens = new_output

                                prev_cost = getattr(session, "_accumulated_cost_usd", 0.0)
                                new_cost = prev_cost + (event.cost_usd or 0.0)
                                session._accumulated_cost_usd = new_cost

                                await asyncio.to_thread(
                                    session_manager.update_usage,
                                    db_sid,
                                    input_tokens=event.total_input_tokens or 0,
                                    output_tokens=new_output,
                                    cache_creation_tokens=event.cache_creation_input_tokens or 0,
                                    cache_read_tokens=event.cache_read_input_tokens or 0,
                                    total_cost_usd=new_cost,
                                    context_window=event.context_window,
                                    model=getattr(session, "_last_model", None),
                                )
                            except Exception:
                                logger.warning(
                                    "Failed to persist usage for %s", db_sid, exc_info=True
                                )
                        else:
                            # No token data — still persist context_window + model
                            try:
                                updates: dict[str, Any] = {}
                                if event.context_window is not None:
                                    updates["context_window"] = event.context_window
                                last_model = getattr(session, "_last_model", None)
                                if last_model:
                                    updates["model"] = last_model
                                if updates:
                                    updates["updated_at"] = datetime.now(UTC).isoformat()
                                    await asyncio.to_thread(
                                        session_manager.db.safe_update,
                                        "sessions",
                                        updates,
                                        "id = ?",
                                        (db_sid,),
                                    )
                            except Exception:
                                logger.debug(
                                    "Failed to persist context_window for %s",
                                    db_sid,
                                    exc_info=True,
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

    async def _handle_tool_approval_response(self, websocket: Any, data: dict[str, Any]) -> None:
        """Handle tool_approval_response message from the web UI.

        Looks up the ChatSession by conversation_id and forwards the user's
        approval decision to unblock the pending tool approval callback.
        """
        conversation_id = data.get("conversation_id")
        decision = data.get("decision", "reject")
        if decision not in ("approve", "reject", "approve_always"):
            decision = "reject"

        session = self._chat_sessions.get(conversation_id) if conversation_id else None
        if session is None:
            logger.warning(f"tool_approval_response for unknown conversation: {conversation_id}")
            return

        if not session.has_pending_approval:
            logger.warning(f"tool_approval_response but no pending approval for {conversation_id}")
            return

        session.provide_approval(decision)
