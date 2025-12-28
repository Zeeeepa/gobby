"""Transport connection factory."""

from collections.abc import Callable, Coroutine
from typing import Any

from gobby.mcp_proxy.models import MCPServerConfig
from gobby.mcp_proxy.transports.base import BaseTransportConnection
from gobby.mcp_proxy.transports.http import HTTPTransportConnection
from gobby.mcp_proxy.transports.stdio import StdioTransportConnection
from gobby.mcp_proxy.transports.websocket import WebSocketTransportConnection


def create_transport_connection(
    config: MCPServerConfig,
    auth_token: str | None = None,
    token_refresh_callback: Callable[[], Coroutine[Any, Any, str]] | None = None,
) -> BaseTransportConnection:
    """
    Factory function to create appropriate transport connection.

    Args:
        config: Server configuration
        auth_token: Optional auth token
        token_refresh_callback: Optional token refresh callback

    Returns:
        Transport-specific connection instance

    Raises:
        ValueError: If transport type is unsupported
    """
    transport_map: dict[str, type[BaseTransportConnection]] = {
        "http": HTTPTransportConnection,
        "stdio": StdioTransportConnection,
        "websocket": WebSocketTransportConnection,
    }

    transport_class = transport_map.get(config.transport)
    if not transport_class:
        raise ValueError(
            f"Unsupported transport: {config.transport}. Supported: {list(transport_map.keys())}"
        )

    return transport_class(config, auth_token, token_refresh_callback)
