"""
WebSocket server for real-time bidirectional communication.

Provides tool call proxying, session broadcasting, and connection management
with optional authentication and ping/pong keepalive.

Local-first version: Authentication is optional (defaults to always-allow).
"""

import asyncio
import json
import logging
import os
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4

from websockets.asyncio.server import serve
from websockets.datastructures import Headers
from websockets.exceptions import ConnectionClosed, ConnectionClosedError
from websockets.http11 import Response

from gobby.agents.registry import get_running_agent_registry
from gobby.mcp_proxy.manager import MCPClientManager

logger = logging.getLogger(__name__)


# Protocol for WebSocket connection to include custom attributes
class WebSocketClient(Protocol):
    user_id: str
    subscriptions: set[str]
    latency: float
    remote_address: Any

    async def send(self, message: str) -> None: ...
    async def close(self, code: int = 1000, reason: str = "") -> None: ...
    async def wait_closed(self) -> None: ...
    def __aiter__(self) -> Any: ...


@dataclass
class WebSocketConfig:
    """Configuration for WebSocket server."""

    host: str = "localhost"
    port: int = 60888
    ping_interval: int = 30  # seconds
    ping_timeout: int = 10  # seconds
    max_message_size: int = 2 * 1024 * 1024  # 2MB


class WebSocketServer:
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

        # Server instance (set when started)
        self._server: Any = None
        self._serve_task: asyncio.Task[None] | None = None

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
            # Send welcome message
            await websocket.send(
                json.dumps(
                    {
                        "type": "connection_established",
                        "client_id": client_id,
                        "user_id": user_id,
                        "latency": websocket.latency,
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
            # Always cleanup client state
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

        else:
            logger.warning(f"Unknown message type: {msg_type}")
            await self._send_error(websocket, f"Unknown message type: {msg_type}")

    async def _handle_tool_call(self, websocket: Any, data: dict[str, Any]) -> None:
        """
        Handle tool_call message and route to MCP server.

        Message format:
        {
            "type": "tool_call",
            "request_id": "uuid",
            "mcp": "memory",
            "tool": "add_messages",
            "args": {...}
        }

        Response format:
        {
            "type": "tool_result",
            "request_id": "uuid",
            "result": {...}
        }

        Args:
            websocket: Client WebSocket connection
            data: Parsed tool call message
        """
        request_id = data.get("request_id")
        mcp_name = data.get("mcp")
        tool_name = data.get("tool")
        args = data.get("args", {})

        if (
            not isinstance(request_id, str)
            or not isinstance(mcp_name, str)
            or not isinstance(tool_name, str)
        ):
            await self._send_error(
                websocket,
                "Missing or invalid required fields: request_id, mcp, tool (must be strings)",
                request_id=str(request_id) if request_id else None,
            )
            return

        try:
            # Route to MCP via manager
            result = await self.mcp_manager.call_tool(mcp_name, tool_name, args)

            # Send result back to client
            await websocket.send(
                json.dumps(
                    {
                        "type": "tool_result",
                        "request_id": request_id,
                        "result": result,
                    }
                )
            )

        except ValueError as e:
            # Unknown MCP server
            await self._send_error(websocket, str(e), request_id=request_id)

        except Exception as e:
            logger.exception(f"Tool call error: {mcp_name}.{tool_name}")
            await self._send_error(websocket, f"Tool call failed: {str(e)}", request_id=request_id)

    async def _handle_ping(self, websocket: Any, data: dict[str, Any]) -> None:
        """
        Handle manual ping message for latency measurement.

        Sends pong response with latency value.

        Args:
            websocket: Client WebSocket connection
            data: Ping message (ignored)
        """
        await websocket.send(
            json.dumps(
                {
                    "type": "pong",
                    "latency": websocket.latency,
                }
            )
        )

    async def _send_error(
        self,
        websocket: Any,
        message: str,
        request_id: str | None = None,
        code: str = "ERROR",
    ) -> None:
        """
        Send error message to client.

        Args:
            websocket: Client WebSocket connection
            message: Error message
            request_id: Optional request ID for correlation
            code: Error code (default: "ERROR")
        """
        error_msg = {
            "type": "error",
            "code": code,
            "message": message,
        }

        if request_id:
            error_msg["request_id"] = request_id

        await websocket.send(json.dumps(error_msg))

    async def _handle_subscribe(self, websocket: Any, data: dict[str, Any]) -> None:
        """
        Handle subscribe message to register for specific events.

        Args:
            websocket: Client WebSocket connection
            data: Subscribe message with "events" list
        """
        events = data.get("events", [])
        if not isinstance(events, list):
            await self._send_error(websocket, "events must be a list of strings")
            return

        if not hasattr(websocket, "subscriptions"):
            websocket.subscriptions = set()

        websocket.subscriptions.update(events)
        logger.debug(f"Client {websocket.user_id} subscribed to: {events}")

        await websocket.send(
            json.dumps(
                {
                    "type": "subscribe_success",
                    "events": list(websocket.subscriptions),
                }
            )
        )

    async def _handle_unsubscribe(self, websocket: Any, data: dict[str, Any]) -> None:
        """
        Handle unsubscribe message to unregister from specific events.

        Args:
            websocket: Client WebSocket connection
            data: Unsubscribe message with "events" list
        """
        events = data.get("events", [])
        if not isinstance(events, list):
            await self._send_error(websocket, "events must be a list of strings")
            return

        current_subscriptions: set[str] = getattr(websocket, "subscriptions", set())

        # If events list is empty or contains "*", unsubscribe from all
        if not events or "*" in events:
            current_subscriptions.clear()
        else:
            for event in events:
                current_subscriptions.discard(event)

        logger.debug(f"Client {websocket.user_id} unsubscribed from: {events}")

        await websocket.send(
            json.dumps(
                {
                    "type": "unsubscribe_success",
                    "events": list(current_subscriptions),
                }
            )
        )

    async def _handle_stop_request(self, websocket: Any, data: dict[str, Any]) -> None:
        """
        Handle stop_request message to signal a session to stop.

        Message format:
        {
            "type": "stop_request",
            "session_id": "uuid",
            "reason": "optional reason string"
        }

        Response format:
        {
            "type": "stop_response",
            "session_id": "uuid",
            "success": true,
            "signal_id": "uuid"
        }

        Args:
            websocket: Client WebSocket connection
            data: Parsed stop request message
        """
        session_id = data.get("session_id")
        reason = data.get("reason", "WebSocket stop request")

        if not session_id:
            await self._send_error(websocket, "Missing required field: session_id")
            return

        if not self.stop_registry:
            await self._send_error(websocket, "Stop registry not available", code="UNAVAILABLE")
            return

        try:
            # Signal the stop
            signal = self.stop_registry.signal_stop(
                session_id=session_id,
                reason=reason,
                source="websocket",
            )

            # Send acknowledgment
            await websocket.send(
                json.dumps(
                    {
                        "type": "stop_response",
                        "session_id": session_id,
                        "success": True,
                        "signal_id": signal.session_id,
                        "signaled_at": signal.requested_at.isoformat(),
                    }
                )
            )

            # Broadcast the stop_requested event to all clients
            await self.broadcast_autonomous_event(
                event="stop_requested",
                session_id=session_id,
                reason=reason,
                source="websocket",
                signal_id=signal.session_id,
            )

            logger.info(f"Stop requested for session {session_id} via WebSocket")
        except Exception as e:
            logger.error(f"Error handling stop request: {e}")
            await self._send_error(websocket, f"Failed to signal stop: {str(e)}")

    async def _handle_terminal_input(self, websocket: Any, data: dict[str, Any]) -> None:
        """
        Handle terminal input for a running agent.

        Message format:
        {
            "type": "terminal_input",
            "run_id": "uuid",
            "data": "raw input string"
        }

        Args:
            websocket: Client WebSocket connection
            data: Parsed terminal input message
        """
        run_id = data.get("run_id")
        input_data = data.get("data")

        if not run_id or input_data is None:
            # Don't send error for every keystroke if malformed, just log debug
            logger.debug(
                f"Invalid terminal_input: run_id={run_id}, data_len={len(str(input_data)) if input_data else 0}"
            )
            return

        if not isinstance(input_data, str):
            # input_data must be a string to encode; log and skip non-strings
            logger.debug(
                f"Invalid terminal_input type: run_id={run_id}, data_type={type(input_data).__name__}"
            )
            return

        registry = get_running_agent_registry()
        # Look up by run_id
        agent = registry.get(run_id)

        if not agent:
            # Be silent on missing agent to avoid spamming errors if frontend is out of sync
            # or if agent just died.
            return

        if agent.master_fd is None:
            logger.warning(f"Agent {run_id} has no PTY master_fd")
            return

        try:
            # Write key/input to PTY off the event loop
            encoded_data = input_data.encode("utf-8")
            await asyncio.to_thread(os.write, agent.master_fd, encoded_data)
        except OSError as e:
            logger.warning(f"Failed to write to agent {run_id} PTY: {e}")

    async def broadcast(self, message: dict[str, Any]) -> None:
        """
        Broadcast message to all connected clients.

        Filters messages based on client subscriptions:
        1. If message type is NOT 'hook_event', always send (system messages)
        2. If message type IS 'hook_event':
           - If client has NO subscriptions, send ALL events (default behavior)
           - If client HAS subscriptions, only send if event_type in subscriptions

        Args:
            message: Dictionary to serialize and send
        """
        if not self.clients:
            return  # No clients connected, silently skip

        message_str = json.dumps(message)
        sent_count = 0
        failed_count = 0

        # Pre-calculate filtering criteria
        is_hook_event = message.get("type") == "hook_event"
        event_type = message.get("event_type")

        for websocket in list(self.clients.keys()):
            try:
                # Filter logic
                if is_hook_event:
                    # If subscriptions are present, we MUST match.
                    # If NO subscriptions present, we default to sending everything (backward compatibility)
                    subs = getattr(websocket, "subscriptions", None)
                    if subs is not None:
                        # Filtering active
                        if event_type not in subs and "*" not in subs:
                            continue

                # Session Message Logic
                elif message.get("type") == "session_message":
                    # Only send to clients subscribed to "session_message" or "*"
                    # If NO subscriptions present (None), we invoke backward compat logic?
                    # Actually for new feature session_message, let's say:
                    # If subscriptions is None => Receive All (simple tools)
                    # If subscriptions is set => Must include "session_message" or "*"

                    subs = getattr(websocket, "subscriptions", None)
                    if subs is not None:
                        if "session_message" not in subs and "*" not in subs:
                            continue

                await websocket.send(message_str)
                sent_count += 1
            except ConnectionClosed:
                # Client disconnecting, will be cleaned up in handler
                failed_count += 1
            except Exception as e:
                logger.warning(f"Broadcast failed for client: {e}")
                failed_count += 1

        logger.debug(f"Broadcast complete: {sent_count} sent, {failed_count} failed")

    async def broadcast_session_update(self, event: str, **kwargs: Any) -> None:
        """
        Broadcast session update to all clients.

        Convenience method for sending session_update messages.

        Args:
            event: Event type (e.g., "token_refreshed", "logout")
            **kwargs: Additional event data
        """
        message = {
            "type": "session_update",
            "event": event,
            **kwargs,
        }

        await self.broadcast(message)

    async def broadcast_agent_event(
        self,
        event: str,
        run_id: str,
        parent_session_id: str,
        **kwargs: Any,
    ) -> None:
        """
        Broadcast agent event to all clients.

        Used for agent lifecycle events like started, completed, cancelled.

        Args:
            event: Event type (agent_started, agent_completed, agent_failed, agent_cancelled)
            run_id: Agent run ID
            parent_session_id: Parent session that spawned the agent
            **kwargs: Additional event data (provider, status, etc.)
        """
        message = {
            "type": "agent_event",
            "event": event,
            "run_id": run_id,
            "parent_session_id": parent_session_id,
            "timestamp": datetime.now(UTC).isoformat(),
            **kwargs,
        }

        await self.broadcast(message)

    async def broadcast_worktree_event(
        self,
        event: str,
        worktree_id: str,
        **kwargs: Any,
    ) -> None:
        """
        Broadcast worktree event to all clients.

        Used for worktree lifecycle events like created, claimed, released, merged.

        Args:
            event: Event type (worktree_created, worktree_claimed, worktree_released, worktree_merged)
            worktree_id: Worktree ID
            **kwargs: Additional event data (branch_name, task_id, session_id, etc.)
        """
        message = {
            "type": "worktree_event",
            "event": event,
            "worktree_id": worktree_id,
            "timestamp": datetime.now(UTC).isoformat(),
            **kwargs,
        }

        await self.broadcast(message)

    async def broadcast_autonomous_event(
        self,
        event: str,
        session_id: str,
        **kwargs: Any,
    ) -> None:
        """
        Broadcast autonomous execution event to all clients.

        Used for autonomous loop lifecycle and progress events:
        - task_started: A task was selected for work
        - task_completed: A task was completed
        - validation_failed: Task validation failed
        - stuck_detected: Loop detected stuck condition
        - stop_requested: External stop signal received
        - progress_recorded: Progress event recorded
        - loop_started: Autonomous loop started
        - loop_stopped: Autonomous loop stopped

        Args:
            event: Event type
            session_id: Session ID of the autonomous loop
            **kwargs: Additional event data (task_id, reason, details, etc.)
        """
        message = {
            "type": "autonomous_event",
            "event": event,
            "session_id": session_id,
            "timestamp": datetime.now(UTC).isoformat(),
            **kwargs,
        }

        await self.broadcast(message)

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

        logger.debug(f"WebSocket server started on ws://{self.config.host}:{self.config.port}")

    async def stop(self) -> None:
        """
        Stop WebSocket server and close all connections.

        Gracefully closes all client connections and shuts down server.
        """
        if self._server is None:
            logger.warning("WebSocket server not started")
            return

        logger.debug("Stopping WebSocket server...")

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
