# Gobby

A local daemon that unifies Claude Code, Gemini CLI, and Codex through a hook interface for session tracking, with an MCP proxy featuring progressive tool discovery for efficient access to downstream servers.

## Features

- **Multi-CLI Unification** - Single daemon handles hooks from Claude Code, Gemini CLI, and Codex
- **Session Tracking** - Captures AI coding sessions across CLIs for context continuity
- **MCP Proxy** - Progressive tool discovery (list → schema → execute) to reduce token usage
- **Local-First** - All data stored in SQLite with no cloud dependency
- **Smart Context** - Auto-detects parent sessions for seamless context handoff

## Quick Start

```bash
# Install
git clone https://github.com/GobbyAI/gobby.git
cd gobby
uv sync

# Start daemon
uv run gobby start

# Initialize project (in your project directory)
uv run gobby init

# Install hooks for your AI CLIs
uv run gobby install
```

## Requirements

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) package manager
- At least one supported AI CLI:
  - [Claude Code](https://claude.ai/code) - `npm install -g @anthropic-ai/claude-code`
  - [Gemini CLI](https://github.com/google-gemini/gemini-cli) - `npm install -g @google/gemini-cli`
  - [Codex CLI](https://github.com/openai/codex) - `npm install -g @openai/codex`

## CLI Commands

| Command | Description |
|---------|-------------|
| `gobby start [--verbose]` | Start the daemon |
| `gobby stop` | Stop the daemon |
| `gobby status` | Show daemon status |
| `gobby restart` | Restart the daemon |
| `gobby init` | Initialize a Gobby project in current directory |
| `gobby install` | Install hooks for detected AI CLIs |
| `gobby uninstall` | Remove hooks from AI CLIs |
| `gobby mcp-info` | Show MCP endpoint configuration |
| `gobby mcp-server` | Run stdio MCP server for Claude Code |

## MCP Tools

The daemon exposes tools via MCP that can be used by Claude Code and other MCP clients:

### Daemon Management
- `start()`, `stop()`, `restart()`, `status()` - Lifecycle control
- `init_project()` - Initialize a new project

### MCP Server Management
- `list_mcp_servers()` - List connected downstream servers
- `add_mcp_server()` - Dynamically add an MCP server
- `remove_mcp_server()` - Remove an MCP server

### Tool Proxy (Progressive Disclosure)
- `list_tools(server?)` - Get lightweight tool metadata
- `get_tool_schema(server, tool)` - Get full inputSchema for a tool
- `call_tool(server, tool, arguments?)` - Execute a tool on a downstream server

### Code Execution
- `execute_code(code)` - Run Python in Claude's sandbox
- `process_large_dataset(data, operation)` - Token-optimized data processing

### AI-Powered
- `recommend_tools(task_description)` - Get intelligent tool recommendations

## Configuration

Configuration is stored at `~/.gobby/config.yaml`:

```yaml
# Server ports
daemon_port: 8765
websocket:
  enabled: true
  port: 8766

# Logging
logging:
  level: info
  client: ~/.gobby/logs/gobby.log

# Session summaries
session_summary:
  enabled: true
  provider: claude
  model: claude-haiku-4-5

# Code execution
code_execution:
  enabled: true
  provider: claude
  model: claude-sonnet-4-5

# Tool recommendations
recommend_tools:
  enabled: true
  provider: claude
  model: claude-sonnet-4-5
```

## File Locations

| Path | Description |
|------|-------------|
| `~/.gobby/config.yaml` | Daemon configuration |
| `~/.gobby/gobby.db` | SQLite database |
| `~/.gobby/logs/` | Log files |
| `~/.gobby/session_summaries/` | Generated session summaries |
| `.gobby/project.json` | Project-level configuration |

## Architecture

```
AI CLI (Claude/Gemini/Codex)
        │ hook fires
        ▼
Hook Dispatcher Script
        │ HTTP POST
        ▼
Gobby HTTP Server (:8765)
        │
        ▼
┌───────────────────────────────────┐
│  FastAPI + FastMCP Server         │
│  ┌─────────────┬────────────────┐ │
│  │ HookManager │ MCPClientManager│ │
│  └──────┬──────┴───────┬────────┘ │
│         │              │          │
│    ┌────▼────┐   ┌─────▼─────┐   │
│    │ SQLite  │   │ Downstream │   │
│    │ Storage │   │ MCP Servers│   │
│    └─────────┘   └───────────┘   │
└───────────────────────────────────┘
```

### Key Components

- **Hook System** - Unified interface capturing 11+ event types across CLIs
- **Session Manager** - Tracks sessions with metadata, status, and parent relationships
- **MCP Proxy** - Connects to downstream servers (Supabase, Context7, etc.)
- **Summary Generator** - LLM-powered session summaries for context handoff

## Development

```bash
# Install dependencies
uv sync

# Run daemon in development
uv run gobby start --verbose

# Run tests
uv run pytest

# Linting
uv run ruff check src/
uv run ruff format src/

# Type checking
uv run mypy src/
```

## Hook Types

Gobby captures these hook events from AI CLIs:

| Hook | Description |
|------|-------------|
| `SessionStart` | New coding session begins |
| `SessionEnd` | Session ends |
| `UserPromptSubmit` | User sends a message |
| `PreToolUse` | Before tool execution |
| `PostToolUse` | After tool execution |
| `Stop` | Agent stops |
| `SubagentStart` | Subagent spawned |
| `SubagentStop` | Subagent finished |
| `PreCompact` | Before context compaction |
| `Notification` | System notification |
| `PermissionRequest` | Permission requested |

## License

MIT
