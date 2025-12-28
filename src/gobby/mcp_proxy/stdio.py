"""
Stdio MCP server implementation.

This server runs as a stdio process for Claude Code and proxies
tool calls to the HTTP daemon.
"""

import asyncio
import logging
import sys
from typing import Any

import httpx
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

__all__ = [
    "create_stdio_mcp_server",
    "check_daemon_http_health",
    "get_daemon_pid",
    "is_daemon_running",
    "restart_daemon_process",
    "start_daemon_process",
    "stop_daemon_process",
]

logger = logging.getLogger("gobby.mcp.stdio")


class DaemonProxy:
    """Proxy for HTTP daemon API calls."""

    def __init__(self, port: int):
        self.port = port
        self.base_url = f"http://localhost:{port}"

    async def _request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """Make HTTP request to daemon."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.request(
                    method,
                    f"{self.base_url}{path}",
                    json=json,
                    timeout=timeout,
                )
                if resp.status_code == 200:
                    data: dict[str, Any] = resp.json()
                    return data
                else:
                    return {"success": False, "error": f"HTTP {resp.status_code}: {resp.text}"}
        except httpx.ConnectError:
            return {"success": False, "error": "Daemon not running or not reachable"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_status(self) -> dict[str, Any]:
        """Get daemon status."""
        return await self._request("GET", "/admin/status")

    async def list_tools(self, server: str | None = None) -> dict[str, Any]:
        """List tools from MCP servers."""
        if server:
            return await self._request("GET", f"/mcp/{server}/tools")
        # List all - need to get server list first
        status = await self.get_status()
        if status.get("success") is False or status.get("status") == "error":
            return status
        servers = status.get("mcp_servers", {})
        all_tools: dict[str, list[dict[str, Any]]] = {}
        for srv_name in servers:
            result = await self._request("GET", f"/mcp/{srv_name}/tools")
            if result.get("status") == "success":
                all_tools[srv_name] = result.get("tools", [])
        return {
            "status": "success",
            "servers": [{"name": n, "tools": t} for n, t in all_tools.items()],
        }

    async def call_tool(
        self, server_name: str, tool_name: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Call a tool on an MCP server."""
        return await self._request(
            "POST",
            f"/mcp/{server_name}/tools/{tool_name}",
            json=arguments or {},
        )

    async def get_tool_schema(self, server_name: str, tool_name: str) -> dict[str, Any]:
        """Get schema for a specific tool."""
        result = await self._request("GET", f"/mcp/{server_name}/tools")
        if result.get("status") != "success":
            return result
        tools = result.get("tools", [])
        for tool in tools:
            if tool.get("name") == tool_name:
                return {
                    "status": "success",
                    "server": server_name,
                    "tool": {
                        "name": tool.get("name"),
                        "description": tool.get("description"),
                        "inputSchema": tool.get("inputSchema"),
                    },
                }
        return {
            "status": "error",
            "error": f"Tool '{tool_name}' not found on server '{server_name}'",
        }

    async def list_mcp_servers(self) -> dict[str, Any]:
        """List configured MCP servers."""
        status = await self.get_status()
        if status.get("success") is False or status.get("status") == "error":
            return status
        servers = status.get("mcp_servers", {})
        server_list = []
        for name, info in servers.items():
            server_list.append(
                {
                    "name": name,
                    "state": info.get("status", "unknown"),
                    "connected": info.get("connected", False),
                    "transport": info.get("transport", "unknown"),
                    "tools": info.get("tools", []),
                    "tool_count": info.get("tool_count", 0),
                }
            )
        return {
            "servers": server_list,
            "total_count": len(server_list),
            "connected_count": len([s for s in server_list if s["connected"]]),
        }

    async def recommend_tools(
        self, task_description: str, agent_id: str | None = None
    ) -> dict[str, Any]:
        """Get tool recommendations for a task."""
        # This would need a dedicated endpoint - for now return not implemented
        return {"status": "error", "error": "recommend_tools not yet available via stdio proxy"}

    async def add_mcp_server(self, **kwargs: Any) -> dict[str, Any]:
        """Add an MCP server - not available via stdio."""
        return {"status": "error", "error": "add_mcp_server not available via stdio proxy"}

    async def remove_mcp_server(self, name: str) -> dict[str, Any]:
        """Remove an MCP server - not available via stdio."""
        return {"status": "error", "error": "remove_mcp_server not available via stdio proxy"}

    async def import_mcp_server(self, **kwargs: Any) -> dict[str, Any]:
        """Import an MCP server - not available via stdio."""
        return {"status": "error", "error": "import_mcp_server not available via stdio proxy"}

    async def init_project(
        self, name: str | None = None, github_url: str | None = None
    ) -> dict[str, Any]:
        """Initialize a project - not available via stdio."""
        return {"status": "error", "error": "init_project not available via stdio proxy"}


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

    # Initialize MCP server and daemon proxy
    mcp = FastMCP("gobby")
    proxy = DaemonProxy(config.daemon_port)

    # --- Daemon Lifecycle Tools ---

    @mcp.tool()
    async def start() -> dict[str, Any]:
        """
        Start the Gobby daemon.

        Use this when the daemon is not running and you need to start it.
        The daemon provides access to Claude Code sessions, MCP servers, and Gobby platform features.

        Returns:
            Result with success status, PID, health check status, and formatted status message
        """
        result = await start_daemon_process(config.daemon_port, config.websocket.port)
        if result.get("success"):
            # Check health after start
            healthy = await check_daemon_http_health(config.daemon_port)
            return {
                "success": True,
                "pid": result.get("pid"),
                "healthy": healthy,
                "formatted_message": f"Daemon started with PID {result.get('pid')}",
            }
        return result

    @mcp.tool()
    async def stop() -> dict[str, Any]:
        """
        Stop the Gobby daemon.

        Use this to gracefully shut down the daemon process.
        WARNING: After stopping, MCP tools that require the daemon will not work until you call start().

        Returns:
            Result with success status and message
        """
        result = await stop_daemon_process()
        return result

    @mcp.tool()
    async def restart() -> dict[str, Any]:
        """
        Restart the Gobby daemon.

        Use this to apply configuration changes or recover from errors.
        The daemon will be stopped and then started with a fresh process.

        Returns:
            Result with success status, new PID, and health check status
        """
        pid = get_daemon_pid()
        result = await restart_daemon_process(pid, config.daemon_port, config.websocket.port)
        if result.get("success"):
            healthy = await check_daemon_http_health(config.daemon_port)
            return {
                "success": True,
                "pid": result.get("pid"),
                "healthy": healthy,
            }
        return result

    @mcp.tool()
    async def status() -> dict[str, Any]:
        """
        Get comprehensive daemon status and health information.

        Use this to check if the daemon is running and healthy before performing operations.
        Always call this first when troubleshooting issues.

        Returns:
            Daemon status dictionary with running, pid, healthy, and port information
        """
        pid = get_daemon_pid()
        healthy = await check_daemon_http_health(config.daemon_port)

        # Get detailed status from daemon if running
        daemon_details = None
        if healthy:
            result = await proxy.get_status()
            # Only accept explicitly successful responses (not error responses)
            if result.get("success") is False or result.get("status") == "error":
                logger.warning(
                    "Failed to get daemon details: %s",
                    result.get("error", "unknown error"),
                )
            else:
                daemon_details = result

        return {
            "running": pid is not None,
            "pid": pid,
            "healthy": healthy,
            "http_port": config.daemon_port,
            "websocket_port": config.websocket.port,
            "daemon_details": daemon_details,
            "formatted_message": _format_status_message(
                pid, healthy, config.daemon_port, config.websocket.port
            ),
        }

    # --- MCP Server Management Tools ---

    @mcp.tool()
    async def list_mcp_servers() -> dict[str, Any]:
        """
        List all MCP servers configured in the daemon.

        Returns details about each MCP server including connection status,
        available tools, and resources.

        Returns:
            Dict with servers list, total count, and connected count
        """
        return await proxy.list_mcp_servers()

    @mcp.tool()
    async def list_tools(server: str | None = None) -> dict[str, Any]:
        """
        List tools from MCP servers.

        Use this to discover tools available on servers.

        Args:
            server: Optional server name (e.g., "context7", "supabase").
                   If not provided, returns tools from all servers.

        Returns:
            Dict with tool listings
        """
        return await proxy.list_tools(server)

    @mcp.tool()
    async def get_tool_schema(server_name: str, tool_name: str) -> dict[str, Any]:
        """
        Get full schema (inputSchema) for a specific MCP tool.

        Use list_tools() first to discover available tools, then use this to get
        full details before calling the tool.

        Args:
            server_name: Name of the MCP server (e.g., "context7", "supabase")
            tool_name: Name of the tool (e.g., "get-library-docs", "list_tables")

        Returns:
            Dict with tool name, description, and full inputSchema
        """
        return await proxy.get_tool_schema(server_name, tool_name)

    @mcp.tool()
    async def call_tool(
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Execute a tool on a connected MCP server.

        This is the primary way to interact with MCP servers (Supabase, memory, etc.)
        through the Gobby daemon.

        Args:
            server_name: Name of the MCP server
            tool_name: Name of the specific tool to execute
            arguments: Dictionary of arguments required by the tool (optional)

        Returns:
            Dictionary with success status and tool execution result
        """
        return await proxy.call_tool(server_name, tool_name, arguments)

    @mcp.tool()
    async def recommend_tools(task_description: str, agent_id: str | None = None) -> dict[str, Any]:
        """
        Get intelligent tool recommendations for a given task.

        Args:
            task_description: Description of what you're trying to accomplish
            agent_id: Optional agent profile ID to filter tools by assigned permissions

        Returns:
            Dict with tool recommendations and usage suggestions
        """
        return await proxy.recommend_tools(task_description, agent_id)

    @mcp.tool()
    async def init_project(
        name: str | None = None, github_url: str | None = None
    ) -> dict[str, Any]:
        """
        Initialize a new Gobby project in the current directory.

        Args:
            name: Optional project name (auto-detected from directory name if not provided)
            github_url: Optional GitHub URL (auto-detected from git remote if not provided)

        Returns:
            Dict with success status and project details
        """
        return await proxy.init_project(name, github_url)

    @mcp.tool()
    async def add_mcp_server(
        name: str,
        transport: str,
        url: str | None = None,
        headers: dict[str, str] | None = None,
        command: str | None = None,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        enabled: bool = True,
    ) -> dict[str, Any]:
        """
        Add a new MCP server to the daemon's configuration.

        Args:
            name: Unique server name
            transport: Transport type - "http", "stdio", or "websocket"
            url: Server URL (required for http/websocket)
            headers: Custom HTTP headers (optional)
            command: Command to run (required for stdio)
            args: Command arguments (optional for stdio)
            env: Environment variables (optional for stdio)
            enabled: Whether server is enabled (default: True)

        Returns:
            Result dict with success status
        """
        return await proxy.add_mcp_server(
            name=name,
            transport=transport,
            url=url,
            headers=headers,
            command=command,
            args=args,
            env=env,
            enabled=enabled,
        )

    @mcp.tool()
    async def remove_mcp_server(name: str) -> dict[str, Any]:
        """
        Remove an MCP server from the daemon's configuration.

        Args:
            name: Server name to remove

        Returns:
            Result dict with success status
        """
        return await proxy.remove_mcp_server(name)

    @mcp.tool()
    async def import_mcp_server(
        from_project: str | None = None,
        servers: list[str] | None = None,
        github_url: str | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        """
        Import MCP servers from various sources.

        Args:
            from_project: Source project name to import servers from
            servers: Optional list of specific server names to import
            github_url: GitHub repository URL to parse for MCP server config
            query: Natural language search query

        Returns:
            Result dict with imported servers or config to fill in
        """
        return await proxy.import_mcp_server(
            from_project=from_project,
            servers=servers,
            github_url=github_url,
            query=query,
        )

    return mcp


def _format_status_message(pid: int | None, healthy: bool, http_port: int, ws_port: int) -> str:
    """Format a human-readable status message."""
    lines = [
        "=" * 70,
        "GOBBY DAEMON STATUS",
        "=" * 70,
        "",
        f"Status: {'Running' if pid else 'Not Running'}",
    ]
    if pid:
        lines.extend(
            [
                f"  PID: {pid}",
                "  PID file: ~/.gobby/gobby.pid",
                "  Log files: ~/.gobby/logs",
                "",
                "Server Configuration:",
                f"  HTTP Port: {http_port}",
                f"  WebSocket Port: {ws_port}",
            ]
        )
    lines.append("")
    lines.append("=" * 70)
    return "\n".join(lines)


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
            logger.error(
                "Failed to start daemon: %s (port=%d, ws_port=%d)",
                result.get("error", "unknown error"),
                port,
                ws_port,
            )
            sys.exit(1)

    # Wait for health
    last_health_response = None
    for i in range(10):
        last_health_response = await check_daemon_http_health(port)
        if last_health_response:
            return
        await asyncio.sleep(1)

    # Health check timed out
    pid = get_daemon_pid()
    logger.error(
        "Daemon failed to become healthy after 10 attempts (pid=%s, port=%d, ws_port=%d, last_health=%s)",
        pid,
        port,
        ws_port,
        last_health_response,
    )
    sys.exit(1)


async def main() -> None:
    """Main entry point for stdio MCP server."""
    # Ensure daemon is running first
    await ensure_daemon_running()

    # Create and run the MCP server
    mcp = create_stdio_mcp_server()
    await mcp.run_stdio_async()


if __name__ == "__main__":
    asyncio.run(main())
