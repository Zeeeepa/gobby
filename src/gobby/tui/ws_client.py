"""WebSocket client for real-time Gobby events."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any

import websockets
from websockets.asyncio.client import ClientConnection

logger = logging.getLogger(__name__)


class GobbyWebSocketClient:
    """WebSocket client with automatic reconnection for real-time updates."""

    def __init__(
        self,
        ws_url: str = "ws://localhost:60335",
        reconnect_interval: float = 5.0,
        max_reconnect_attempts: int = 10,
    ) -> None:
        self.ws_url = ws_url
        self.reconnect_interval = reconnect_interval
        self.max_reconnect_attempts = max_reconnect_attempts

        self._ws: ClientConnection | None = None
        self._running = False
        self._connected = False
        self._client_id: str | None = None
        self._subscriptions: set[str] = set()

        # Event handlers: event_type -> list of callbacks
        self._handlers: dict[str, list[Callable[[dict[str, Any]], None]]] = {}

        # Connection state callbacks
        self._on_connect_callbacks: list[Callable[[], None]] = []
        self._on_disconnect_callbacks: list[Callable[[], None]] = []

    @property
    def connected(self) -> bool:
        """Check if currently connected."""
        return self._connected

    @property
    def client_id(self) -> str | None:
        """Get the client ID assigned by server."""
        return self._client_id

    def on_event(
        self,
        event_type: str,
        handler: Callable[[dict[str, Any]], None],
    ) -> None:
        """Register a handler for a specific event type."""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    def on_connect(self, callback: Callable[[], None]) -> None:
        """Register a callback for when connection is established."""
        self._on_connect_callbacks.append(callback)

    def on_disconnect(self, callback: Callable[[], None]) -> None:
        """Register a callback for when connection is lost."""
        self._on_disconnect_callbacks.append(callback)

    async def subscribe(self, events: list[str]) -> None:
        """Subscribe to specific event types."""
        self._subscriptions.update(events)
        if self._ws and self._connected:
            await self._send({"type": "subscribe", "events": events})

    async def unsubscribe(self, events: list[str]) -> None:
        """Unsubscribe from specific event types."""
        self._subscriptions.difference_update(events)
        if self._ws and self._connected:
            await self._send({"type": "unsubscribe", "events": events})

    async def _send(self, message: dict[str, Any]) -> None:
        """Send a message to the server."""
        if self._ws and self._connected:
            await self._ws.send(json.dumps(message))

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> None:
        """Send a tool call request via WebSocket."""
        import uuid

        message = {
            "type": "tool_call",
            "request_id": request_id or str(uuid.uuid4()),
            "mcp": server_name,
            "tool": tool_name,
            "args": arguments or {},
        }
        await self._send(message)

    async def ping(self) -> None:
        """Send a ping to measure latency."""
        await self._send({"type": "ping"})

    async def connect(self) -> None:
        """Establish WebSocket connection with automatic reconnection."""
        self._running = True
        attempt = 0

        while self._running and attempt < self.max_reconnect_attempts:
            try:
                logger.info(f"Connecting to WebSocket at {self.ws_url}")
                async with websockets.connect(self.ws_url) as ws:
                    self._ws = ws
                    self._connected = True
                    attempt = 0  # Reset attempts on successful connection

                    # Notify connection callbacks
                    for callback in self._on_connect_callbacks:
                        try:
                            callback()
                        except Exception as e:
                            logger.error(f"Connection callback error: {e}")

                    # Resubscribe to events
                    if self._subscriptions:
                        await self._send(
                            {
                                "type": "subscribe",
                                "events": list(self._subscriptions),
                            }
                        )

                    # Listen for messages
                    await self._listen()

            except websockets.ConnectionClosed:
                logger.warning("WebSocket connection closed")
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
            finally:
                self._connected = False
                self._ws = None

                # Notify disconnect callbacks
                for callback in self._on_disconnect_callbacks:
                    try:
                        callback()
                    except Exception as e:
                        logger.error(f"Disconnect callback error: {e}")

            if self._running:
                attempt += 1
                logger.info(
                    f"Reconnecting in {self.reconnect_interval}s "
                    f"(attempt {attempt}/{self.max_reconnect_attempts})"
                )
                await asyncio.sleep(self.reconnect_interval)

    async def _listen(self) -> None:
        """Listen for incoming messages."""
        if not self._ws:
            return

        async for message in self._ws:
            try:
                data = json.loads(message)
                await self._handle_message(data)
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON received: {message!r}")
            except Exception as e:
                logger.error(f"Error handling message: {e}")

    async def _handle_message(self, data: dict[str, Any]) -> None:
        """Route incoming message to appropriate handlers."""
        msg_type = data.get("type", "unknown")

        # Handle connection established
        if msg_type == "connection_established":
            self._client_id = data.get("client_id")
            logger.info(f"Connected with client_id: {self._client_id}")
            return

        # Handle pong
        if msg_type == "pong":
            latency = data.get("latency", 0)
            logger.debug(f"Pong received, latency: {latency:.3f}s")
            return

        # Handle tool results
        if msg_type == "tool_result":
            request_id = data.get("request_id")
            logger.debug(f"Tool result for {request_id}")

        # Handle errors
        if msg_type == "error":
            logger.error(f"Server error: {data.get('message')}")

        # Dispatch to registered handlers (combine without mutating originals)
        handlers = self._handlers.get(msg_type, []) + self._handlers.get("*", [])

        for handler in handlers:
            try:
                handler(data)
            except Exception as e:
                logger.error(f"Handler error for {msg_type}: {e}")

    async def disconnect(self) -> None:
        """Close the WebSocket connection."""
        self._running = False
        if self._ws:
            await self._ws.close()
            self._ws = None
        self._connected = False


class WebSocketEventBridge:
    """Bridge WebSocket events to Textual message system."""

    def __init__(self, ws_client: GobbyWebSocketClient) -> None:
        self.ws_client = ws_client
        self._app: Any = None

    def bind_app(self, app: Any) -> None:
        """Bind to a Textual app for posting messages."""
        self._app = app

    def setup_handlers(self) -> None:
        """Register handlers that will post Textual messages."""
        # These will be implemented when we create custom Textual messages
        event_types = [
            "hook_event",
            "agent_event",
            "autonomous_event",
            "session_message",
            "worktree_event",
            "tool_result",
        ]

        for event_type in event_types:
            self.ws_client.on_event(event_type, self._make_handler(event_type))

    def _make_handler(self, event_type: str) -> Callable[[dict[str, Any]], None]:
        """Create a handler that posts to the Textual app."""

        def handler(data: dict[str, Any]) -> None:
            if self._app:
                # Post custom message to Textual app
                # The app will define how to handle these
                self._app.call_from_thread(self._app.post_ws_event, event_type, data)

        return handler
