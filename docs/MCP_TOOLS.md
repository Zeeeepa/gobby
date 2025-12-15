# Gobby MCP Tools

This document lists all MCP tools provided by the Gobby daemon itself (not proxied downstream server tools).

## Overview

Gobby exposes MCP tools via two interfaces:
1. **HTTP MCP Server** - Mounted at `/mcp` on the daemon HTTP server
2. **Stdio MCP Server** - For Claude Code integration via `gobby mcp-server`

The stdio server proxies to the HTTP daemon and adds lifecycle management tools.

---

## Daemon Lifecycle Tools

These tools are available via the stdio MCP server and manage the daemon process.

### `start()`

Start the Gobby daemon.

**Returns:**
```json
{
  "success": true,
  "message": "Daemon started successfully",
  "pid": 12345,
  "healthy": true,
  "formatted_message": "..."
}
```

**Use When:**
- Daemon is not running
- Before using tools that require the daemon
- After a system restart

---

### `stop()`

Stop the Gobby daemon.

**Returns:**
```json
{
  "success": true,
  "message": "Daemon stopped successfully"
}
```

**Warning:** After stopping, MCP tools that require the daemon will not work until you call `start()`.

---

### `restart()`

Restart the Gobby daemon.

**Returns:**
```json
{
  "success": true,
  "message": "Daemon restarted successfully",
  "pid": 12346,
  "healthy": true
}
```

**Use When:**
- After updating daemon configuration
- When the daemon is unhealthy
- To clear stuck sessions or connections
- After updating MCP server configurations

---

### `status()`

Get comprehensive daemon status and health information.

**Returns:**
```json
{
  "running": true,
  "pid": 12345,
  "healthy": true,
  "http_port": 8765,
  "websocket_port": 8766,
  "daemon_details": { ... },
  "formatted_message": "..."
}
```

**Contains:**
- `running` - Whether the daemon process is running
- `pid` - Process ID if running
- `healthy` - Whether the daemon is responding to HTTP requests
- `http_port` / `websocket_port` - Server ports
- `daemon_details` - Additional status info from daemon
- `formatted_message` - Human-readable status display

---

### `init_project(name?, github_url?)`

Initialize a new Gobby project in the current directory.

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | string? | Project name (auto-detected from directory name) |
| `github_url` | string? | GitHub URL (auto-detected from git remote) |

**Returns:**
```json
{
  "success": true,
  "message": "Project 'my-project' initialized successfully",
  "project": {
    "id": "uuid",
    "name": "my-project",
    "created_at": "2024-01-01T00:00:00Z"
  },
  "paths": {
    "project_json": "/path/to/.gobby/project.json"
  }
}
```

---

## MCP Server Management Tools

### `list_mcp_servers(project_id?)`

List all configured MCP servers and their connection status.

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `project_id` | string? | Optional project ID to filter servers |

**Returns:**
```json
{
  "servers": [
    {
      "name": "context7",
      "description": "Library documentation server",
      "connected": true
    }
  ]
}
```

---

### `add_mcp_server(name, transport, ...)`

Dynamically add a new MCP server connection.

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | string | Unique server name |
| `transport` | string | Transport type: "http", "stdio", or "websocket" |
| `url` | string? | Server URL (required for http/websocket) |
| `headers` | object? | Custom HTTP headers |
| `command` | string? | Command to run (required for stdio) |
| `args` | string[]? | Command arguments (for stdio) |
| `env` | object? | Environment variables (for stdio) |
| `enabled` | boolean | Whether server is enabled (default: true) |

**Example - HTTP Server:**
```json
{
  "name": "supabase",
  "transport": "http",
  "url": "http://localhost:6543/mcp"
}
```

**Example - Stdio Server:**
```json
{
  "name": "weather",
  "transport": "stdio",
  "command": "uv",
  "args": ["run", "weather_server.py"],
  "env": {"API_KEY": "secret"}
}
```

**Returns:**
```json
{
  "success": true,
  "server": "supabase",
  "connected": true,
  "message": "Server added and connected"
}
```

---

### `remove_mcp_server(name)`

Remove an MCP server from the daemon's configuration.

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | string | Server name to remove |

**Returns:**
```json
{
  "success": true,
  "message": "Server 'supabase' removed"
}
```

---

## MCP Proxy Tools

These tools interact with downstream MCP servers.

### `call_tool(server_name, tool_name, arguments?)`

Execute a tool on a connected downstream MCP server.

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `server_name` | string | Name of the MCP server |
| `tool_name` | string | Name of the tool to invoke |
| `arguments` | object? | Tool arguments |

**Example:**
```json
{
  "server_name": "supabase",
  "tool_name": "list_tables",
  "arguments": {"schemas": ["public"]}
}
```

**Returns:**
```json
{
  "success": true,
  "server": "supabase",
  "tool": "list_tables",
  "result": { ... }
}
```

---

### `list_tools(server?)`

List tools from downstream MCP servers.

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `server` | string? | Specific server name, or all servers if not provided |

**Returns (specific server):**
```json
{
  "success": true,
  "server": "context7",
  "tools": [
    {"name": "get-library-docs", "brief": "Fetch documentation for a library"},
    {"name": "resolve-library-id", "brief": "Find library ID from name"}
  ]
}
```

**Returns (all servers):**
```json
{
  "success": true,
  "servers": [
    {"name": "context7", "tools": [...]},
    {"name": "supabase", "tools": [...]}
  ]
}
```

---

### `get_tool_schema(server_name, tool_name)`

Get full schema (inputSchema) for a specific MCP tool.

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `server_name` | string | Name of the MCP server |
| `tool_name` | string | Name of the tool |

**Returns:**
```json
{
  "success": true,
  "server": "context7",
  "tool": {
    "name": "get-library-docs",
    "description": "Fetches comprehensive documentation...",
    "inputSchema": {
      "type": "object",
      "properties": {
        "libraryId": {"type": "string"}
      },
      "required": ["libraryId"]
    }
  }
}
```

**Note:** Tool schemas are cached in `~/.gobby/tools/` for fast, offline access.

---

### `read_mcp_resource(server_name, resource_uri)`

Read a resource from a downstream MCP server.

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `server_name` | string | Name of the MCP server |
| `resource_uri` | string | URI of the resource to read |

**Returns:**
```json
{
  "success": true,
  "server": "context7",
  "uri": "context7://docs/react",
  "content": [...],
  "mime_type": "text/markdown"
}
```

---

## Code Execution Tools

These tools use Claude's code execution sandbox via the Claude Agent SDK.

### `execute_code(code, language?, context?, timeout?)`

Execute code in a secure sandbox.

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `code` | string | Code to execute |
| `language` | string | Programming language (default: "python") |
| `context` | string? | Optional context/instructions for Claude |
| `timeout` | integer? | Maximum execution time in seconds |

**Example:**
```json
{
  "code": "sum(x**2 for x in range(1000))",
  "context": "Calculate sum of squares from 1 to 1000"
}
```

**Returns:**
```json
{
  "success": true,
  "result": "332833500",
  "language": "python",
  "execution_time": 1.5,
  "context": "Calculate sum of squares from 1 to 1000"
}
```

**Use Cases:**
- Process large datasets
- Perform calculations
- Data transformations and analysis
- Generate visualizations

---

### `process_large_dataset(data, operation, parameters?, timeout?)`

Process large datasets using Claude's code execution for token optimization.

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `data` | array/object | Dataset to process |
| `operation` | string | Natural language description of operation |
| `parameters` | object? | Optional parameters for processing |
| `timeout` | integer? | Maximum execution time in seconds |

**Example:**
```json
{
  "data": [{"user_id": 1, "value": 150}, ...],
  "operation": "Filter rows where value > 100 and return top 10",
  "parameters": {"threshold": 100, "limit": 10}
}
```

**Returns:**
```json
{
  "success": true,
  "result": [...],
  "original_size": 10000,
  "processed_size": 10,
  "reduction_percent": 99.9,
  "execution_time": 2.3,
  "operation": "Filter rows where value > 100 and return top 10"
}
```

**Use Case:** Token optimization for large MCP results (e.g., million-row Supabase queries).

---

## AI-Powered Tools

### `recommend_tools(task_description, agent_id?)`

Get intelligent tool recommendations for a given task.

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `task_description` | string | Description of what you're trying to accomplish |
| `agent_id` | string? | Optional agent profile ID for filtering |

**Example:**
```json
{
  "task_description": "Find React hooks documentation"
}
```

**Returns:**
```json
{
  "success": true,
  "task": "Find React hooks documentation",
  "recommendation": "I recommend using context7 tools...",
  "available_servers": ["context7", "playwright"],
  "total_tools": 25
}
```

---

## Session Hook Tools

### `call_hook(hook_type, params?, source?)`

Trigger a session hook for non-Claude-Code CLIs.

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `hook_type` | string | Type of hook to trigger |
| `params` | object? | Hook-specific parameters |
| `source` | string? | CLI source identifier |

**Supported Hook Types:**
- `SessionStart` - Register session, restore context from parent
- `SessionEnd` - Generate summary and prepare for handoff
- `PromptSubmit` / `UserPromptSubmit` - Synthesize/update session title
- `Stop` - Mark session as paused
- `PreToolUse` / `PostToolUse` - Tool execution hooks
- `PreCompact` - Before context compaction
- `SubagentStart` / `SubagentStop` - Subagent lifecycle
- `Notification` - Notifications

**Example - Start Session:**
```json
{
  "hook_type": "SessionStart",
  "params": {
    "session_id": "codex-abc123",
    "source": "startup",
    "cwd": "/path/to/project"
  },
  "source": "Codex"
}
```

**Returns:**
```json
{
  "success": true,
  "hook_type": "SessionStart",
  "normalized_type": "session-start",
  "result": {
    "session_id": "uuid",
    "machine_id": "...",
    "restored_summary": "..."
  }
}
```

---

## Codex Integration Tools

These tools are available when `codex_client` is configured.

### `codex(prompt, thread_id?, cwd?, model?, sandbox?, approval_policy?)`

Run Codex with automatic Gobby session tracking.

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `prompt` | string | User prompt for Codex |
| `thread_id` | string? | Thread ID to continue existing session |
| `cwd` | string? | Working directory (defaults to current) |
| `model` | string? | Model override |
| `sandbox` | string? | Sandbox mode: "readOnly", "workspaceWrite", "dangerFullAccess" |
| `approval_policy` | string? | Approval policy: "never", "unlessTrusted", "always" |

**Returns:**
```json
{
  "success": true,
  "thread_id": "thr_abc123",
  "session_id": "uuid",
  "turn_id": "turn_xyz",
  "response": "Agent's response text...",
  "items": [...],
  "usage": {...},
  "is_continuation": false
}
```

---

### `codex_list_threads(limit?, cursor?)`

List available Codex conversation threads.

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `limit` | integer | Maximum threads to return (default: 25) |
| `cursor` | string? | Pagination cursor |

**Returns:**
```json
{
  "success": true,
  "threads": [
    {
      "id": "thr_abc123",
      "preview": "Help me refactor...",
      "model_provider": "openai",
      "created_at": "2024-01-01T00:00:00Z"
    }
  ],
  "next_cursor": "..."
}
```

---

### `codex_archive_thread(thread_id)`

Archive a Codex conversation thread.

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `thread_id` | string | ID of the thread to archive |

**Returns:**
```json
{
  "success": true,
  "thread_id": "thr_abc123",
  "message": "Thread thr_abc123 archived"
}
```

---

## MCP Resources

### `gobby://config`

Get daemon configuration as an MCP resource.

**Returns:**
```json
{
  "daemon_port": 8765,
  "mcp_servers": ["context7", "supabase"]
}
```

---

### `gobby://daemon/status`

Daemon status as an MCP resource (stdio server only).

**Returns:** Same as `status()` tool.

---

## Configuration

Tool behavior can be configured in `~/.gobby/config.yaml`:

```yaml
# Code execution settings
code_execution:
  enabled: true
  model: claude-sonnet-4-5
  max_turns: 5
  default_timeout: 30
  max_dataset_preview: 3

# Tool recommendations
recommend_tools:
  enabled: true
  model: claude-sonnet-4-5

# MCP proxy settings
mcp_client_proxy:
  enabled: true
  tool_timeout: 60.0
```
