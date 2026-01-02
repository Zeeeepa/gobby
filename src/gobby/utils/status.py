"""
Status message formatting for Gobby daemon.

Provides consistent status display across CLI and MCP server.
"""

from typing import Any


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
    # Memory & Skills
    memories_count: int | None = None,
    memories_avg_importance: float | None = None,
    skills_count: int | None = None,
    skills_total_uses: int | None = None,
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
        skills_count: Number of skills
        skills_total_uses: Total skill usage count

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

    # Memory & Skills section (only show if we have data)
    if memories_count is not None or skills_count is not None:
        lines.append("Memory & Skills:")
        parts = []
        if memories_count is not None:
            mem_str = f"Memories: {memories_count}"
            if memories_avg_importance is not None:
                mem_str += f" (avg importance: {memories_avg_importance:.2f})"
            parts.append(mem_str)
        if skills_count is not None:
            skill_str = f"Skills: {skills_count}"
            if skills_total_uses is not None:
                skill_str += f" ({skills_total_uses} total uses)"
            parts.append(skill_str)
        for part in parts:
            lines.append(f"  {part}")
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
