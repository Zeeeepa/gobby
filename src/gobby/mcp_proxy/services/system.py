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
        lazy_states = self._mcp_manager.get_lazy_connection_states()

        # Merge lazy connection info into health
        for name, lazy_info in lazy_states.items():
            if name in health:
                health[name]["lazy_connection"] = lazy_info
            else:
                # Server registered but never connected (lazy mode)
                health[name] = {
                    "state": "configured",  # Not connected yet
                    "health": "unknown",
                    "last_check": None,
                    "failures": 0,
                    "response_time_ms": None,
                    "lazy_connection": lazy_info,
                }

        # Aggregate health: system is healthy if connected servers are healthy
        # In lazy mode, unconfigured servers don't count as unhealthy
        all_healthy = (
            all(
                server_health.get("state") in ["connected", "healthy", "configured"]
                for server_health in health.values()
            )
            if health
            else True
        )

        # Count configured vs connected
        configured_count = len(health)
        connected_count = sum(
            1
            for h in health.values()
            if h.get("state") == "connected" or h.get("lazy_connection", {}).get("is_connected")
        )

        return {
            "running": True,
            "pid": os.getpid(),
            "healthy": all_healthy,
            "http_port": self._port,
            "websocket_port": self._websocket_port,
            "mcp_servers": health,
            "lazy_mode": self._mcp_manager.lazy_connect,
            "configured_servers": configured_count,
            "connected_servers": connected_count,
        }
