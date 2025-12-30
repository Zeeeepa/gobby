---
description: How to discover and use MCP tools through the Gobby daemon proxy
---

# Gobby MCP Tool Discovery Workflow

This workflow guides you through discovering and using MCP tools via the Gobby daemon proxy.

## 1. Daemon Management (Use CLI)

Daemon lifecycle should be managed via CLI commands:

```bash
uv run gobby start    # Start daemon
uv run gobby stop     # Stop daemon
uv run gobby status   # Check status
uv run gobby restart  # Restart daemon
```

**Why CLI?** MCP tools require a running daemon. You can't start via MCP if it isn't running.

## 2. Tool Discovery (Progressive Disclosure)

To save tokens, use this 3-step process instead of loading all schemas at once.

### Step A: List Servers & Tools

Discover what is available.

- **List Servers**: Call `mcp_list_mcp_servers()` to see connected downstream servers.
- **List Tools**: Call `mcp_list_tools(server="<server_name>")` to see tools on a specific server.
  - For downstream servers: `mcp_list_tools(server="context7")`
  - For internal tools: `mcp_list_tools(server="gobby-tasks")`

### Step B: Get Tool Schema

Get the full definition for a specific tool before using it.

- **Tool**: `mcp_get_tool_schema`
- **Arguments**:
  - `server_name`: Server name (e.g., "context7" or "gobby-tasks")
  - `tool_name`: The tool you want to use

### Step C: Call Tool

Execute the tool on the appropriate server.

- **Tool**: `mcp_call_tool`
- **Arguments**:
  - `server_name`: Server name (downstream or internal)
  - `tool_name`: The tool name
  - `arguments`: The actual arguments for the tool

**Routing:**

- `gobby-*` servers → handled locally by internal registries
- All others → proxied to downstream MCP servers

## 3. Internal Task Management

Use `gobby-tasks` for persistent task tracking.

```python
# Create a task
mcp_call_tool(
    server_name="gobby-tasks",
    tool_name="create_task",
    arguments={"title": "Fix auth bug", "priority": 1}
)

# Find ready work (no blocking dependencies)
mcp_call_tool(
    server_name="gobby-tasks",
    tool_name="list_ready_tasks",
    arguments={"limit": 5}
)

# Close a task
mcp_call_tool(
    server_name="gobby-tasks",
    tool_name="close_task",
    arguments={"task_id": "gt-abc123", "reason": "completed"}
)
```

**Available task tools:**
- CRUD: `create_task`, `get_task`, `update_task`, `close_task`, `delete_task`, `list_tasks`, `add_label`, `remove_label`
- Dependencies: `add_dependency`, `remove_dependency`, `get_dependency_tree`, `list_ready_tasks`, `list_blocked_tasks`
- Session: `link_task_to_session`, `get_session_tasks`, `get_task_sessions`
- Sync: `sync_tasks`, `get_sync_status`
- Expansion: `expand_task`, `analyze_complexity`, `expand_all`, `expand_from_spec`, `suggest_next_task`
- Validation: `validate_task`, `get_validation_status`, `reset_validation_count`

## 4. Troubleshooting

- **Tools failing with `FileNotFoundError`?**
  - Check `~/.gobby/logs/gobby.log`.
  - Verify MCP config has absolute paths to executables (e.g., `/opt/homebrew/bin/uv`).
- **Daemon not running?**
  - Run `uv run gobby status` to check.
  - Run `uv run gobby start` to start it.
