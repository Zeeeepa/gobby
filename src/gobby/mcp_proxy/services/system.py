"""System status service."""

import logging
import os
from typing import Any

from gobby.mcp_proxy.manager import MCPClientManager

logger = logging.getLogger("gobby.mcp.server")


class SystemService:
    """Service for system status and information."""

    def __init__(
        self, mcp_manager: MCPClientManager, port: int, websocket_port: int, start_time: float
    ):
        self._mcp_manager = mcp_manager
        self._port = port
        self._websocket_port = websocket_port
        self._start_time = start_time

    def get_status(self) -> dict[str, Any]:
        """Get system status."""
        health = self._mcp_manager.get_server_health()

        return {
            "running": True,
            "pid": os.getpid(),
            "healthy": True,  # Aggregate health logic here
            "http_port": self._port,
            "websocket_port": self._websocket_port,
            "mcp_servers": health,
        }
