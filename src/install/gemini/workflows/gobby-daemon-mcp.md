---
description: How to manage the Gobby Daemon and discover/use downstream MCP tools
---

# Gobby Daemon & MCP Tool Workflow

This workflow guides you through managing the Gobby Daemon and using its proxied MCP tools.

## 1. Tool Discovery (Progressive Disclosure)

To save tokens, use this 3-step process instead of loading all schemas at once.

### Step A: List Servers & Tools

Discover what is available.

- **List Servers**: Call `mcp_list_mcp_servers()` to see connected downstream servers (e.g., `context7`, `supabase`).
- **List Tools**: Call `mcp_list_tools(server="<server_name>")` to see tools on a specific server.
  - *Note*: This uses the daemon's `list_tools` tool, NOT the `call_tool` proxy.

### Step B: Get Tool Schema

Get the full definition for a specific tool before using it.

- **Tool**: `mcp_get_tool_schema`
- **Arguments**:
  - `server_name`: The downstream server name (e.g., "context7")
  - `tool_name`: The tool you want to use (e.g., "get-library-docs")

### Step C: Call Tool

Execute the tool on the downstream server.

- **Tool**: `mcp_call_tool`
- **Arguments**:
  - `server_name`: The downstream server name (e.g., "context7")
  - `tool_name`: The tool name (e.g., "get-library-docs")
  - `arguments`: The actual arguments for the tool.

## 2. Daemon Management

**CRITICAL**: Always use these MCP tools. **NEVER** use CLI commands (like `gobby start`) directly.

| Operation | Tool Name | Description |
|-----------|-----------|-------------|
| **Check Status** | `mcp_status` | Check if daemon is running and healthy. |
| **Start Daemon** | `mcp_start` | Start the daemon if it's stopped. |
| **Restart** | `mcp_restart` | Restart the daemon (fix connection issues). |
| **Login** | `mcp_login` | Authenticate with the Gobby platform. |

**Example**:

1. Call `mcp_status`.
2. If `running` is false, call `mcp_start`.

> [!IMPORTANT]
> **Daemon Tools vs. Downstream Tools**
>
> - **Daemon Tools** (e.g., `add_mcp_server`, `status`, `restart`): Must be called **DIRECTLY** (e.g., `mcp_add_mcp_server`). They are **INCOMPATIBLE** with `call_tool`.
> - **Downstream Tools** (e.g., `get-library-docs` from `context7`): Must be called via the proxy tool `mcp_call_tool`.

## 3. Troubleshooting

- **Tools failing with `FileNotFoundError`?**
  - Check `~/.gobby/logs/gobby.log`.
  - Verify MCP config has absolute paths to executables (e.g., `/opt/homebrew/bin/uv`).
- **Daemon unhealthy?**
  - Call `mcp_restart`.
