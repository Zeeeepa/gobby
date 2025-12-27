"""HTTP transport connection."""

import logging
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from gobby.mcp_proxy.models import ConnectionState, MCPError
from gobby.mcp_proxy.transports.base import BaseTransportConnection

logger = logging.getLogger("gobby.mcp.client")


class HTTPTransportConnection(BaseTransportConnection):
    """HTTP/Streamable HTTP transport connection using MCP SDK."""

    async def connect(self) -> Any:
        """Connect via HTTP transport."""
        if self._state == ConnectionState.CONNECTED and self._session is not None:
            return self._session

        # Clean up old connection if reconnecting
        if self._session is not None or self._transport_context is not None:
            await self.disconnect()

        self._state = ConnectionState.CONNECTING

        # Track what was entered for cleanup
        transport_entered = False
        session_entered = False
        session_context: ClientSession | None = None

        try:
            # URL is required for HTTP transport
            assert self.config.url is not None, "URL is required for HTTP transport"

            # Create HTTP client context with custom headers
            self._transport_context = streamablehttp_client(
                self.config.url,
                headers=self.config.headers,  # Pass custom headers (e.g., API keys)
            )

            # Enter the transport context to get streams
            read_stream, write_stream, _ = await self._transport_context.__aenter__()
            transport_entered = True

            session_context = ClientSession(read_stream, write_stream)
            self._session = await session_context.__aenter__()
            session_entered = True

            await self._session.initialize()

            self._state = ConnectionState.CONNECTED
            self._consecutive_failures = 0
            logger.debug(f"Connected to HTTP MCP server: {self.config.name}")

            return self._session

        except Exception as e:
            # Handle exceptions with empty str() (EndOfStream, ClosedResourceError, CancelledError)
            error_msg = str(e) if str(e) else f"{type(e).__name__}: Connection closed or timed out"
            logger.error(f"Failed to connect to HTTP server '{self.config.name}': {error_msg}")

            # Cleanup in reverse order - session first, then transport
            if session_entered and session_context is not None:
                try:
                    await session_context.__aexit__(None, None, None)
                except Exception as cleanup_error:
                    logger.warning(
                        f"Error during session cleanup for {self.config.name}: {cleanup_error}"
                    )

            if transport_entered and self._transport_context is not None:
                try:
                    await self._transport_context.__aexit__(None, None, None)
                except Exception as cleanup_error:
                    logger.warning(
                        f"Error during transport cleanup for {self.config.name}: {cleanup_error}"
                    )

            # Reset state before raising
            self._session = None
            self._transport_context = None
            self._state = ConnectionState.FAILED

            # Re-raise wrapped in MCPError (don't double-wrap)
            if isinstance(e, MCPError):
                raise
            raise MCPError(f"HTTP connection failed: {error_msg}") from e

    async def disconnect(self) -> None:
        """Disconnect from HTTP server."""
        if self._session is not None:
            try:
                await self._session.__aexit__(None, None, None)
            except RuntimeError as e:
                # Expected when exiting cancel scope from different task
                if "cancel scope" not in str(e):
                    logger.warning(f"Error closing session for {self.config.name}: {e}")
            except Exception as e:
                logger.warning(f"Error closing session for {self.config.name}: {e}")
            self._session = None

        if self._transport_context is not None:
            try:
                await self._transport_context.__aexit__(None, None, None)
            except RuntimeError as e:
                # Expected when exiting cancel scope from different task
                if "cancel scope" not in str(e):
                    logger.warning(f"Error closing transport for {self.config.name}: {e}")
            except Exception as e:
                logger.warning(f"Error closing transport for {self.config.name}: {e}")
            self._transport_context = None

        self._state = ConnectionState.DISCONNECTED
