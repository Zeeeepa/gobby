"""
Status message formatting for Gobby daemon.

Provides consistent status display across CLI and MCP server.
"""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def fetch_rich_status(http_port: int, timeout: float = 2.0) -> dict[str, Any]:
    """
    Fetch rich status data from the daemon API.

    Args:
        http_port: HTTP port of the daemon
        timeout: Request timeout in seconds

    Returns:
        Dict of status kwargs to pass to format_status_message
    """
    status_kwargs: dict[str, Any] = {}

    try:
        response = httpx.get(f"http://localhost:{http_port}/admin/status", timeout=timeout)
        if response.status_code != 200:
            return status_kwargs

        data = response.json()

        # Process metrics
        process_data = data.get("process")
        if process_data:
            status_kwargs["memory_mb"] = process_data.get("memory_rss_mb")
            status_kwargs["cpu_percent"] = process_data.get("cpu_percent")

        # MCP servers
        mcp_servers = data.get("mcp_servers", {})
        if mcp_servers:
            total = len(mcp_servers)
            connected = sum(1 for s in mcp_servers.values() if s.get("connected"))
            status_kwargs["mcp_total"] = total
            status_kwargs["mcp_connected"] = connected
            status_kwargs["mcp_tools_cached"] = data.get("mcp_tools_cached", 0)

            # Find unhealthy servers
            unhealthy = []
            for name, info in mcp_servers.items():
                health = info.get("health")
                if health and health not in ("healthy", None):
                    unhealthy.append((name, health))
                elif info.get("consecutive_failures", 0) > 0:
                    unhealthy.append((name, f"{info['consecutive_failures']} failures"))
            if unhealthy:
                status_kwargs["mcp_unhealthy"] = unhealthy

        # Sessions
        sessions = data.get("sessions", {})
        if sessions:
            status_kwargs["sessions_active"] = sessions.get("active", 0)
            status_kwargs["sessions_paused"] = sessions.get("paused", 0)
            status_kwargs["sessions_handoff_ready"] = sessions.get("handoff_ready", 0)

        # Tasks
        tasks = data.get("tasks", {})
        if tasks:
            status_kwargs["tasks_open"] = tasks.get("open", 0)
            status_kwargs["tasks_in_progress"] = tasks.get("in_progress", 0)
            status_kwargs["tasks_ready"] = tasks.get("ready", 0)
            status_kwargs["tasks_blocked"] = tasks.get("blocked", 0)

        # Memory
        memory = data.get("memory", {})
        if memory and memory.get("count", 0) > 0:
            status_kwargs["memories_count"] = memory.get("count", 0)
            status_kwargs["memories_avg_importance"] = memory.get("avg_importance", 0.0)

        # Skills
        skills_data = data.get("skills", {})
        if skills_data:
            status_kwargs["skills_total"] = skills_data.get("total", 0)

        # Artifacts
        artifacts_data = data.get("artifacts", {})
        if artifacts_data and artifacts_data.get("count", 0) > 0:
            status_kwargs["artifacts_count"] = artifacts_data.get("count", 0)

    except (httpx.ConnectError, httpx.TimeoutException):
        # Daemon not responding - return empty
        pass
    except Exception as e:
        logger.debug(f"Failed to fetch daemon status: {e}")

    return status_kwargs


def format_status_message(
    *,
    running: bool,
    pid: int | None = None,
    pid_file: str | None = None,
    log_files: str | None = None,
    uptime: str | None = None,
    http_port: int | None = None,
    websocket_port: int | None = None,
    # Process metrics
    memory_mb: float | None = None,
    cpu_percent: float | None = None,
    # MCP proxy info
    mcp_connected: int | None = None,
    mcp_total: int | None = None,
    mcp_tools_cached: int | None = None,
    mcp_unhealthy: list[tuple[str, str]] | None = None,
    # Sessions info
    sessions_active: int | None = None,
    sessions_paused: int | None = None,
    sessions_handoff_ready: int | None = None,
    # Tasks info
    tasks_open: int | None = None,
    tasks_in_progress: int | None = None,
    tasks_ready: int | None = None,
    tasks_blocked: int | None = None,
    # Memory
    memories_count: int | None = None,
    memories_avg_importance: float | None = None,
    # Skills
    skills_total: int | None = None,
    # Artifacts
    artifacts_count: int | None = None,
    **kwargs: Any,
) -> str:
    """
    Format Gobby daemon status message with consistent styling.

    Args:
        running: Whether the daemon is running
        pid: Process ID
        pid_file: Path to PID file
        log_files: Path to log files directory
        uptime: Formatted uptime string (e.g., "1h 23m 45s")
        http_port: HTTP server port
        websocket_port: WebSocket server port
        memory_mb: Memory usage in MB
        cpu_percent: CPU usage percentage
        mcp_connected: Number of connected MCP servers
        mcp_total: Total number of configured MCP servers
        mcp_tools_cached: Number of cached tools
        mcp_unhealthy: List of (server_name, status) for unhealthy servers
        sessions_active: Number of active sessions
        sessions_paused: Number of paused sessions
        sessions_handoff_ready: Number of sessions ready for handoff
        tasks_open: Number of open tasks
        tasks_in_progress: Number of in-progress tasks
        tasks_ready: Number of ready tasks
        tasks_blocked: Number of blocked tasks
        memories_count: Total number of memories
        memories_avg_importance: Average memory importance


    Returns:
        Formatted status message string
    """
    lines = []

    # Header
    lines.append("=" * 70)
    lines.append("GOBBY DAEMON STATUS")
    lines.append("=" * 70)
    lines.append("")

    # Status section
    if running:
        status_line = "Status: Running"
        if pid:
            status_line += f" (PID: {pid})"
        lines.append(status_line)

        # Uptime and process metrics on same conceptual level
        metrics_parts = []
        if uptime:
            metrics_parts.append(f"Uptime: {uptime}")
        if memory_mb is not None:
            metrics_parts.append(f"Memory: {memory_mb:.1f} MB")
        if cpu_percent is not None:
            metrics_parts.append(f"CPU: {cpu_percent:.1f}%")

        if metrics_parts:
            lines.append(f"  {' | '.join(metrics_parts)}")
    else:
        lines.append("Status: Stopped")

    lines.append("")

    # Server Configuration section
    if http_port or websocket_port:
        lines.append("Server Configuration:")
        if http_port:
            lines.append(f"  HTTP: localhost:{http_port}")
        if websocket_port:
            lines.append(f"  WebSocket: localhost:{websocket_port}")
        lines.append("")

    # MCP Proxy section (only show if we have data)
    if mcp_total is not None:
        lines.append("MCP Proxy:")
        connected = mcp_connected if mcp_connected is not None else 0
        lines.append(f"  Servers: {connected} connected / {mcp_total} total")
        if mcp_tools_cached is not None:
            lines.append(f"  Tools cached: {mcp_tools_cached}")
        if mcp_unhealthy:
            unhealthy_str = ", ".join(f"{name} ({status})" for name, status in mcp_unhealthy)
            lines.append(f"  Unhealthy: {unhealthy_str}")
        lines.append("")

    # Skills section (only show if we have data)
    if skills_total is not None:
        lines.append("Skills:")
        lines.append(f"  Loaded: {skills_total}")
        lines.append("")

    # Sessions section (only show if we have data)
    if sessions_active is not None or sessions_paused is not None:
        lines.append("Sessions:")
        parts = []
        if sessions_active is not None:
            parts.append(f"Active: {sessions_active}")
        if sessions_paused is not None:
            parts.append(f"Paused: {sessions_paused}")
        if sessions_handoff_ready is not None:
            parts.append(f"Handoff Ready: {sessions_handoff_ready}")
        if parts:
            lines.append(f"  {' | '.join(parts)}")
        lines.append("")

    # Tasks section (only show if we have data)
    if tasks_open is not None or tasks_in_progress is not None:
        lines.append("Tasks:")
        parts = []
        if tasks_open is not None:
            parts.append(f"Open: {tasks_open}")
        if tasks_in_progress is not None:
            parts.append(f"In Progress: {tasks_in_progress}")
        if tasks_ready is not None:
            parts.append(f"Ready: {tasks_ready}")
        if tasks_blocked is not None:
            parts.append(f"Blocked: {tasks_blocked}")
        if parts:
            lines.append(f"  {' | '.join(parts)}")
        lines.append("")

    # Memory section (only show if we have data)
    if memories_count is not None:
        lines.append("Memory:")
        mem_str = f"Memories: {memories_count}"
        if memories_avg_importance is not None:
            mem_str += f" (avg importance: {memories_avg_importance:.2f})"
        lines.append(f"  {mem_str}")
        lines.append("")

    # Artifacts section (only show if we have data)
    if artifacts_count is not None:
        lines.append("Artifacts:")
        lines.append(f"  Captured: {artifacts_count}")
        lines.append("")

    # Paths section (only when running)
    if running and (pid_file or log_files):
        lines.append("Paths:")
        if pid_file:
            lines.append(f"  PID file: {pid_file}")
        if log_files:
            lines.append(f"  Logs: {log_files}")
        lines.append("")

    # Footer
    lines.append("=" * 70)

    return "\n".join(lines)
