"""
WebSocket server for real-time bidirectional communication.

Provides tool call proxying, session broadcasting, and connection management
with optional authentication and ping/pong keepalive.

Local-first version: Authentication is optional (defaults to always-allow).
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Callable, Coroutine
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from websockets.asyncio.server import serve
from websockets.datastructures import Headers
from websockets.exceptions import ConnectionClosed, ConnectionClosedError
from websockets.http11 import Response

from gobby.mcp_proxy.manager import MCPClientManager
from gobby.servers.chat_session import ChatSession
from gobby.servers.websocket.broadcast import BroadcastMixin
from gobby.servers.websocket.handlers import HandlerMixin
from gobby.servers.websocket.models import (
    CLEANUP_INTERVAL_SECONDS,
    IDLE_TIMEOUT_SECONDS,
    WebSocketConfig,
)

logger = logging.getLogger(__name__)


class WebSocketServer(HandlerMixin, BroadcastMixin):
    """
    WebSocket server for real-time communication.

    Provides:
    - Optional Bearer token authentication via handshake headers
    - JSON-RPC style message protocol
    - Tool call routing to MCP servers
    - Session update broadcasting
    - Automatic ping/pong keepalive
    - Connection tracking and cleanup

    Example:
        ```python
        config = WebSocketConfig(host="0.0.0.0", port=60888)

        async with WebSocketServer(config, mcp_manager) as server:
            await server.serve_forever()
        ```
    """

    def __init__(
        self,
        config: WebSocketConfig,
        mcp_manager: MCPClientManager,
        auth_callback: Callable[[str], Coroutine[Any, Any, str | None]] | None = None,
        stop_registry: Any = None,
    ):
        """
        Initialize WebSocket server.

        Args:
            config: WebSocket server configuration
            mcp_manager: MCP client manager for tool routing
            auth_callback: Optional async function that validates token and returns user_id.
                          If None, all connections are accepted (local-first mode).
            stop_registry: Optional StopRegistry for handling stop requests from clients.
        """
        self.config = config
        self.mcp_manager = mcp_manager
        self.auth_callback = auth_callback
        self.stop_registry = stop_registry

        # Connected clients: {websocket: client_metadata}
        self.clients: dict[Any, dict[str, Any]] = {}

        # Persistent chat sessions keyed by conversation_id (survive disconnects)
        self._chat_sessions: dict[str, ChatSession] = {}

        # Active chat streaming tasks per conversation_id (for cancellation)
        self._active_chat_tasks: dict[str, asyncio.Task[None]] = {}

        # Server instance (set when started)
        self._server: Any = None
        self._serve_task: asyncio.Task[None] | None = None
        self._cleanup_task: asyncio.Task[None] | None = None

    async def __aenter__(self) -> "WebSocketServer":
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.stop()

    async def _authenticate(self, websocket: Any, request: Any) -> Response | None:
        """
        Authenticate WebSocket connection via Bearer token.

        In local-first mode (no auth_callback), all connections are accepted
        with a generated local user ID.

        Args:
            websocket: WebSocket connection
            request: HTTP request with headers

        Returns:
            None to accept connection, Response to reject
        """
        # Local-first mode: accept all connections
        if self.auth_callback is None:
            websocket.user_id = f"local-{uuid4().hex[:8]}"
            return None

        # Auth callback provided - require Bearer token
        auth_header = request.headers.get("Authorization")

        if not auth_header:
            logger.warning(
                f"Connection rejected: Missing Authorization header from {websocket.remote_address}"
            )
            return Response(401, "Unauthorized: Missing Authorization header\n", Headers())

        if not auth_header.startswith("Bearer "):
            logger.warning(
                f"Connection rejected: Invalid Authorization format from {websocket.remote_address}"
            )
            return Response(401, "Unauthorized: Expected Bearer token\n", Headers())

        token = auth_header.removeprefix("Bearer ")

        try:
            user_id = await self.auth_callback(token)

            if not user_id:
                logger.warning(
                    f"Connection rejected: Invalid token from {websocket.remote_address}"
                )
                return Response(403, "Forbidden: Invalid token\n", Headers())

            # Store user_id on websocket for handler
            websocket.user_id = user_id
            return None

        except Exception as e:
            logger.error(f"Authentication error from {websocket.remote_address}: {e}")
            return Response(500, "Internal server error\n", Headers())

    async def _handle_connection(self, websocket: Any) -> None:
        """
        Handle WebSocket connection lifecycle.

        Registers client, processes messages, and ensures cleanup
        on disconnect. Always cleans up client state even on error.

        Args:
            websocket: Connected WebSocket client
        """
        user_id = websocket.user_id
        client_id = str(uuid4())

        # Register client
        self.clients[websocket] = {
            "id": client_id,
            "user_id": user_id,
            "connected_at": datetime.now(UTC),
            "remote_address": websocket.remote_address,
        }

        logger.debug(
            f"Client {user_id} ({client_id}) connected from {websocket.remote_address}. "
            f"Total clients: {len(self.clients)}"
        )

        try:
            # Send welcome message with active conversation IDs
            active_conversations = list(self._chat_sessions.keys())
            await websocket.send(
                json.dumps(
                    {
                        "type": "connection_established",
                        "client_id": client_id,
                        "user_id": user_id,
                        "latency": websocket.latency,
                        "conversation_ids": active_conversations,
                    }
                )
            )

            # Message processing loop
            async for message in websocket:
                try:
                    await self._handle_message(websocket, message)
                except json.JSONDecodeError:
                    await self._send_error(websocket, "Invalid JSON format")
                except Exception:
                    logger.exception(f"Message handling error for client {client_id}")
                    await self._send_error(websocket, "Internal server error")

        except ConnectionClosedError as e:
            logger.warning(f"Client {client_id} connection error: {e}")

        except ConnectionClosed:
            logger.debug(f"Client {client_id} disconnected normally")

        except Exception:
            logger.exception(f"Unexpected error for client {client_id}")

        finally:
            # Always cleanup client state (but NOT chat sessions — they persist)
            self.clients.pop(websocket, None)
            logger.debug(f"Client {client_id} cleaned up. Remaining clients: {len(self.clients)}")

    async def _handle_message(self, websocket: Any, message: str) -> None:
        """
        Route incoming message to appropriate handler.

        Supports message types:
        - tool_call: Route to MCP server
        - ping: Manual latency check
        - Other types: Log warning

        Args:
            websocket: Sender's WebSocket connection
            message: JSON string message
        """
        data = json.loads(message)
        msg_type = data.get("type")

        if msg_type == "tool_call":
            await self._handle_tool_call(websocket, data)

        elif msg_type == "ping":
            await self._handle_ping(websocket, data)

        elif msg_type == "subscribe":
            await self._handle_subscribe(websocket, data)

        elif msg_type == "unsubscribe":
            await self._handle_unsubscribe(websocket, data)

        elif msg_type == "stop_request":
            await self._handle_stop_request(websocket, data)

        elif msg_type == "terminal_input":
            await self._handle_terminal_input(websocket, data)

        elif msg_type == "chat_message":
            await self._handle_chat_message(websocket, data)

        elif msg_type == "stop_chat":
            await self._handle_stop_chat(websocket, data)

        else:
            logger.warning(f"Unknown message type: {msg_type}")
            await self._send_error(websocket, f"Unknown message type: {msg_type}")

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
            "model": "optional-model-override"
        }

        Response format (streamed):
        {
            "type": "chat_stream",
            "message_id": "assistant-uuid",
            "conversation_id": "stable-id",
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
        content = data.get("content")
        conversation_id = data.get("conversation_id") or str(uuid4())
        model = data.get("model")

        if not content or not isinstance(content, str):
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
            self._stream_chat_response(websocket, conversation_id, content, model)
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
        content: str,
        model: str | None,
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
                            {
                                "type": "chat_error",
                                "message_id": assistant_message_id,
                                "conversation_id": conversation_id,
                                "error": f"Failed to start chat session: {e}",
                            }
                        )
                    )
                    return
                self._chat_sessions[conversation_id] = session
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
                            {
                                "type": "chat_error",
                                "message_id": assistant_message_id,
                                "conversation_id": conversation_id,
                                "error": f"Failed to switch model: {e}",
                            }
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
                            {
                                "type": "chat_thinking",
                                "message_id": assistant_message_id,
                                "conversation_id": conversation_id,
                                "content": event.content,
                            }
                        )
                    )
                elif isinstance(event, TextChunk):
                    await websocket.send(
                        json.dumps(
                            {
                                "type": "chat_stream",
                                "message_id": assistant_message_id,
                                "conversation_id": conversation_id,
                                "content": event.content,
                                "done": False,
                            }
                        )
                    )
                elif isinstance(event, ToolCallEvent):
                    await websocket.send(
                        json.dumps(
                            {
                                "type": "tool_status",
                                "message_id": assistant_message_id,
                                "conversation_id": conversation_id,
                                "tool_call_id": event.tool_call_id,
                                "status": "calling",
                                "tool_name": event.tool_name,
                                "server_name": event.server_name,
                                "arguments": event.arguments,
                            }
                        )
                    )
                elif isinstance(event, ToolResultEvent):
                    await websocket.send(
                        json.dumps(
                            {
                                "type": "tool_status",
                                "message_id": assistant_message_id,
                                "conversation_id": conversation_id,
                                "tool_call_id": event.tool_call_id,
                                "status": "completed" if event.success else "error",
                                "result": event.result,
                                "error": event.error,
                            }
                        )
                    )
                elif isinstance(event, DoneEvent):
                    await websocket.send(
                        json.dumps(
                            {
                                "type": "chat_stream",
                                "message_id": assistant_message_id,
                                "conversation_id": conversation_id,
                                "content": "",
                                "done": True,
                                "tool_calls_count": event.tool_calls_count,
                            }
                        )
                    )

        except asyncio.CancelledError:
            # Stream was interrupted (stop button or new message replacing old)
            try:
                await websocket.send(
                    json.dumps(
                        {
                            "type": "chat_stream",
                            "message_id": assistant_message_id,
                            "conversation_id": conversation_id,
                            "content": "",
                            "done": True,
                            "interrupted": True,
                        }
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
                        {
                            "type": "chat_error",
                            "message_id": assistant_message_id,
                            "conversation_id": conversation_id,
                            "error": "An internal error occurred",
                        }
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
                    await session.stop()
                    logger.debug(f"Cleaned up idle chat session {conv_id}")
                if stale_ids:
                    logger.info(f"Cleaned up {len(stale_ids)} idle chat session(s)")
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in idle session cleanup")

    async def start(self) -> None:
        """
        Start WebSocket server.

        Creates server instance and begins accepting connections.
        Does not block - use serve_forever() or context manager.
        """
        if self._server is not None:
            logger.warning("WebSocket server already started")
            return

        self._server = await serve(
            self._handle_connection,
            host=self.config.host,
            port=self.config.port,
            process_request=self._authenticate,
            ping_interval=self.config.ping_interval,
            ping_timeout=self.config.ping_timeout,
            max_size=self.config.max_message_size,
            compression="deflate",
        )

        # Start idle session cleanup background task
        self._cleanup_task = asyncio.create_task(self._cleanup_idle_sessions())

        logger.debug(f"WebSocket server started on ws://{self.config.host}:{self.config.port}")

    async def stop(self) -> None:
        """
        Stop WebSocket server and close all connections.

        Gracefully closes all client connections, chat sessions, and shuts down server.
        """
        if self._server is None:
            logger.warning("WebSocket server not started")
            return

        logger.debug("Stopping WebSocket server...")

        # Cancel idle cleanup task
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        # Stop all chat sessions
        for conv_id, session in list(self._chat_sessions.items()):
            await self._cancel_active_chat(conv_id)
            await session.stop()
        self._chat_sessions.clear()

        # Close server (stops accepting new connections)
        self._server.close()
        await self._server.wait_closed()

        # Close remaining client connections with timeout
        for websocket in list(self.clients.keys()):
            try:
                await asyncio.wait_for(
                    websocket.close(code=1001, reason="Server shutting down"), timeout=2.0
                )
            except TimeoutError:
                logger.warning("Client connection close timed out")
            except Exception as e:
                logger.warning(f"Error closing client connection: {e}")

        self._server = None
        logger.debug("WebSocket server stopped")

    async def serve_forever(self) -> None:
        """
        Run server until cancelled.

        Blocks forever until interrupted (Ctrl+C) or task cancelled.
        Use in main() for standalone server operation.
        """
        if self._server is None:
            raise RuntimeError("Server not started. Call start() first.")

        try:
            await asyncio.Future()  # Run forever
        except asyncio.CancelledError:
            logger.debug("Server cancelled, shutting down...")
            await self.stop()
            raise

    def get_client_count(self) -> int:
        """
        Get number of connected clients.

        Returns:
            Count of active client connections
        """
        return len(self.clients)

    def get_clients_info(self) -> list[dict[str, Any]]:
        """
        Get information about all connected clients.

        Returns:
            List of client metadata dictionaries
        """
        return [
            {
                "id": metadata["id"],
                "user_id": metadata["user_id"],
                "connected_at": metadata["connected_at"].isoformat(),
                "remote_address": str(metadata["remote_address"]),
            }
            for metadata in self.clients.values()
        ]
