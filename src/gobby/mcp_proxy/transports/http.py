"""HTTP transport connection."""

import asyncio
import logging
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from gobby.mcp_proxy.models import ConnectionState, MCPError
from gobby.mcp_proxy.transports.base import BaseTransportConnection

logger = logging.getLogger("gobby.mcp.client")


class HTTPTransportConnection(BaseTransportConnection):
    """HTTP/Streamable HTTP transport connection using MCP SDK.

    Uses a dedicated background task to own the streamablehttp_client lifecycle,
    ensuring that context entry and exit happen in the same task (required by anyio).
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._owner_task: asyncio.Task[None] | None = None
        self._disconnect_event: asyncio.Event | None = None
        self._session_ready: asyncio.Event | None = None
        self._connection_error: Exception | None = None
        self._session_context: ClientSession | None = None

    async def connect(self) -> Any:
        """Connect via HTTP transport using a dedicated owner task."""
        if self._state == ConnectionState.CONNECTED and self._session is not None:
            return self._session

        # Clean up old connection if reconnecting
        if self._owner_task is not None:
            await self.disconnect()

        self._state = ConnectionState.CONNECTING
        self._connection_error = None

        # Create synchronization events
        self._disconnect_event = asyncio.Event()
        self._session_ready = asyncio.Event()

        # Start owner task that manages the connection lifecycle
        self._owner_task = asyncio.create_task(
            self._run_connection(), name=f"http-conn-{self.config.name}"
        )

        # Wait for connection to be ready or fail
        timeout = self.config.connect_timeout
        try:
            await asyncio.wait_for(self._session_ready.wait(), timeout=timeout)
        except TimeoutError as e:
            self._disconnect_event.set()
            await self._cleanup_owner_task()
            self._state = ConnectionState.FAILED
            raise MCPError(f"Connection timeout for {self.config.name} after {timeout}s") from e

        if self._connection_error is not None:
            error = self._connection_error
            self._connection_error = None
            await self._cleanup_owner_task()
            self._state = ConnectionState.FAILED
            raise error

        return self._session

    async def _run_connection(self) -> None:
        """Background task that owns the streamablehttp_client lifecycle."""
        if self._disconnect_event is None or self._session_ready is None:
            raise RuntimeError("Connection events not initialized")

        try:
            # URL is required for HTTP transport
            if not self.config.url:
                raise ValueError("URL is required for HTTP transport")

            async with streamablehttp_client(
                self.config.url,
                headers=self.config.headers,
            ) as (read_stream, write_stream, _):
                self._session_context = ClientSession(read_stream, write_stream)
                async with self._session_context as session:
                    self._session = session
                    await self._session.initialize()

                    self._state = ConnectionState.CONNECTED
                    self._consecutive_failures = 0
                    logger.debug(f"Connected to HTTP MCP server: {self.config.name}")

                    # Signal that connection is ready
                    self._session_ready.set()

                    # Wait until disconnect is requested
                    await self._disconnect_event.wait()

                    logger.debug(f"Disconnect requested for {self.config.name}")

        except Exception as e:
            error_msg = str(e) if str(e) else f"{type(e).__name__}: Connection closed or timed out"
            logger.error(f"Failed to connect to HTTP server '{self.config.name}': {error_msg}")

            if isinstance(e, MCPError):
                self._connection_error = e
            else:
                self._connection_error = MCPError(f"HTTP connection failed: {error_msg}")

            self._session_ready.set()  # Unblock waiter with error

        finally:
            self._session = None
            self._session_context = None
            self._state = ConnectionState.DISCONNECTED

    async def _cleanup_owner_task(self) -> None:
        """Clean up the owner task."""
        if self._owner_task is not None:
            if not self._owner_task.done():
                self._owner_task.cancel()
                try:
                    await asyncio.wait_for(self._owner_task, timeout=2.0)
                except asyncio.CancelledError:
                    logger.debug(f"Owner task cancelled for {self.config.name}")
                except TimeoutError:
                    logger.warning(f"Owner task cleanup timed out for {self.config.name}")
            self._owner_task = None
        self._disconnect_event = None
        self._session_ready = None

    async def disconnect(self) -> None:
        """Disconnect from HTTP server by signaling the owner task."""
        if self._disconnect_event is not None:
            self._disconnect_event.set()

        await self._cleanup_owner_task()
        self._state = ConnectionState.DISCONNECTED
