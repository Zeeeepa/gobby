"""
Stdio MCP server implementation.
"""

import asyncio
import logging
import sys

from mcp.server.fastmcp import FastMCP

from gobby.config.app import load_config
from gobby.mcp_proxy.daemon_control import (
    check_daemon_http_health,
    get_daemon_pid,
    is_daemon_running,
    restart_daemon_process,
    start_daemon_process,
    stop_daemon_process,
)
from gobby.mcp_proxy.registries import setup_internal_registries

logger = logging.getLogger("gobby.mcp.stdio")


def create_stdio_mcp_server() -> FastMCP:
    """Create stdio MCP server."""
    # Load configuration
    config = load_config()

    # Initialize basic managers (mocked/simplified for this refactor example)
    session_manager = None
    memory_manager = None
    skill_learner = None

    # Setup internal registries using extracted function
    _ = setup_internal_registries(config, session_manager, memory_manager, skill_learner)

    # Initialize MCP server
    mcp = FastMCP("gobby")

    # --- Daemon Lifecycle Tools ---

    @mcp.tool()
    async def start() -> str:
        """Start the Gobby daemon."""
        result = await start_daemon_process(config.daemon_port, config.websocket.port)
        if result.get("success"):
            return f"Daemon started with PID {result['pid']}"
        return f"Failed to start: {result.get('message', 'Unknown error')}"

    @mcp.tool()
    async def stop() -> str:
        """Stop the Gobby daemon."""
        result = await stop_daemon_process()
        if result.get("success"):
            return "Daemon stopped"
        return f"Failed to stop: {result.get('error', 'Unknown error')}"

    @mcp.tool()
    async def restart() -> str:
        """Restart the Gobby daemon."""
        pid = get_daemon_pid()
        result = await restart_daemon_process(pid, config.daemon_port, config.websocket.port)
        if result.get("success"):
            return f"Daemon restarted with PID {result['pid']}"
        return f"Failed to restart: {result.get('error', 'Unknown error')}"

    @mcp.tool()
    async def status() -> dict:
        """Check daemon status."""
        healthy = await check_daemon_http_health(config.daemon_port)
        pid = get_daemon_pid()
        return {
            "running": pid is not None,
            "pid": pid,
            "healthy": healthy,
            "port": config.daemon_port,
            "websocket_port": config.websocket.port,
        }

    # --- Proxy Tools ---

    # Initialize connection manager
    # client_manager = MCPClientManager()

    # Register proxy tools (call_tool, list_tools, etc.)
    # In the real implementation this logic would delegate to the manager
    # similar to how server.py does, but stdio interface might be different.

    return mcp


async def ensure_daemon_running() -> None:
    """Ensure the Gobby daemon is running and healthy."""
    config = load_config()
    port = config.daemon_port
    ws_port = config.websocket.port

    # Check if running
    if is_daemon_running():
        # Check health
        if await check_daemon_http_health(port):
            return

        # Unhealthy, restart
        logger.warning("Daemon running but unhealthy, restarting...")
        pid = get_daemon_pid()
        await restart_daemon_process(pid, port, ws_port)
    else:
        # Start
        result = await start_daemon_process(port, ws_port)
        if not result.get("success"):
            sys.exit(1)

    # Wait for health
    for _ in range(10):
        if await check_daemon_http_health(port):
            return
        await asyncio.sleep(1)

    sys.exit(1)
