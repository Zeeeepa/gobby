# Gobby CLI Commands

This document lists all CLI commands available in the Gobby daemon.

## Usage

All commands are invoked via the `gobby` CLI:

```bash
gobby <command> [options]
```

## Global Options

| Option | Description |
|--------|-------------|
| `--config PATH` | Path to custom configuration file |

---

## Commands

### `gobby start`

Start the Gobby daemon.

```bash
gobby start [--verbose]
```

**Options:**
| Option | Description |
|--------|-------------|
| `--verbose` | Enable verbose debug output |

**Behavior:**
- Initializes local SQLite storage and runs migrations
- Checks for and stops any existing daemon processes
- Verifies HTTP and WebSocket ports are available
- Starts the daemon as a detached subprocess
- Waits for health check confirmation
- Writes PID to `~/.gobby/gobby.pid`

---

### `gobby stop`

Stop the Gobby daemon.

```bash
gobby stop
```

**Behavior:**
- Reads PID from `~/.gobby/gobby.pid`
- Sends SIGTERM for graceful shutdown
- Waits up to 5 seconds for process to terminate
- Cleans up PID file

---

### `gobby status`

Show Gobby daemon status and information.

```bash
gobby status
```

**Output includes:**
- Running status
- Process ID (PID)
- Uptime
- HTTP and WebSocket ports
- Log file locations

---

### `gobby restart`

Restart the Gobby daemon (stop then start).

```bash
gobby restart [--verbose]
```

**Options:**
| Option | Description |
|--------|-------------|
| `--verbose` | Enable verbose debug output |

**Behavior:**
- Stops the running daemon
- Waits for cleanup
- Starts a fresh daemon instance

---

### `gobby init`

Initialize a new Gobby project in the current directory.

```bash
gobby init [--name NAME] [--github-url URL]
```

**Options:**
| Option | Description |
|--------|-------------|
| `--name NAME` | Project name (defaults to directory name) |
| `--github-url URL` | GitHub repository URL (auto-detected from git remote) |

**Behavior:**
- Creates project in local SQLite database
- Creates `.gobby/project.json` with project metadata
- Auto-detects name from current directory
- Auto-detects GitHub URL from git remote

---

### `gobby install`

Install Gobby hooks to AI coding CLIs.

```bash
gobby install [--claude] [--gemini] [--codex] [--all]
```

**Options:**
| Option | Description |
|--------|-------------|
| `--claude` | Install Claude Code hooks only |
| `--gemini` | Install Gemini CLI hooks only |
| `--codex` | Configure Codex notify integration |
| `--all` | Install hooks for all detected CLIs (default) |

**Behavior:**
- Detects installed AI coding CLIs
- For Claude Code: Installs hook dispatcher, settings, and skills to `.claude/`
- For Gemini CLI: Installs hook dispatcher and settings to `.gemini/`
- For Codex: Installs notify script to `~/.gobby/hooks/codex/` and configures `~/.codex/config.toml`

---

### `gobby uninstall`

Uninstall Gobby hooks from AI coding CLIs.

```bash
gobby uninstall [--claude] [--gemini] [--codex] [--all]
```

**Options:**
| Option | Description |
|--------|-------------|
| `--claude` | Uninstall Claude Code hooks only |
| `--gemini` | Uninstall Gemini CLI hooks only |
| `--codex` | Uninstall Codex notify integration |
| `--all` | Uninstall from all CLIs (default) |

**Behavior:**
- Removes hook configurations from settings files
- Deletes hook dispatcher scripts
- Removes installed skills
- Creates backups before modifying settings

**Note:** Requires confirmation before proceeding.

---

### `gobby mcp-server`

Run stdio MCP server for Claude Code integration.

```bash
gobby mcp-server
```

**Behavior:**
- Auto-starts daemon if not running
- Provides daemon lifecycle tools (start/stop/restart)
- Proxies all HTTP MCP tools from the daemon
- Communicates via stdio (stdin/stdout)

**Usage with Claude Code:**
```bash
claude mcp add --transport stdio gobby-daemon -- gobby mcp-server
```

---

## File Locations

| File | Purpose |
|------|---------|
| `~/.gobby/config.yaml` | Daemon configuration |
| `~/.gobby/gobby.pid` | Daemon process ID |
| `~/.gobby/gobby.db` | Local SQLite database |
| `~/.gobby/.mcp.json` | MCP server configurations |
| `~/.gobby/logs/` | Log files |
| `.gobby/project.json` | Project-level configuration |
