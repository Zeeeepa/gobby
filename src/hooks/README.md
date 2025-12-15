# Gobby Client Hooks

> **Production-ready Python hooks for Claude Code integration**

This directory contains Python hook implementations for integrating Gobby Client with Claude Code. Bash hooks are deprecated but still available for compatibility.

## Overview

Gobby Client provides 9 hook implementations (Python + legacy bash) that integrate with Claude Code's hook system to enable:
- Memory persistence (conversation saving)
- Context restoration
- Session lifecycle management
- Pre-compact snapshots
- User prompt validation
- Stop/notification handling

## Quick Start (Python Hooks - Recommended)

### Installation

```bash
# Install dependencies
uv pip install -e ".[dev]"

# Test a hook
echo '{"session_id": "test-123"}' | python3 src/gobby/hooks/session-start.py

# Check logs
tail -f ~/.gobby/logs/hook-session-start.log
```

### Configuration

Configure Python hooks in `.claude/settings.json` or via command-line:

```bash
# Using Python hooks
claude --on-session-start "python3 /path/to/gobby_platform/src/gobby/hooks/session-start.py"
```

See [Hook Development Guide](../../../docs/architecture_v3/04-gobby-client/hook-development-guide.md) for complete documentation.

---

## Available Hooks

### Python Hooks (Production - v2.0+)

| Hook | File | Description |
|------|------|-------------|
| **session-start** | `session-start.py` | Session initialization with metadata extraction |
| **session-end** | `session-end.py` | Session cleanup and archival |
| **user-prompt-submit** | `user-prompt-submit.py` | Prompt validation and machine ID display |
| **post-tool-use-memory** | `post-tool-use-memory.py` | Save tool execution context |
| **pre-tool-use-restore** | `pre-tool-use-restore.py` | Restore relevant context |
| **pre-compact** | `pre-compact.py` | Save pre-compaction snapshot |
| **notification** | `notification.py` | System notifications |
| **stop** | `stop.py` | Graceful shutdown |
| **subagent-stop** | `subagent-stop.py` | Sub-agent termination handling |

**Benefits:**
- ✅ Built-in error handling and retry logic
- ✅ Automatic log rotation
- ✅ Better performance (< 2s for critical hooks)
- ✅ Comprehensive testing with pytest
- ✅ Type safety and validation
- ✅ Easier to debug and maintain

### Legacy Bash Hooks (Deprecated - v1.0)

### Core Memory & Session Hooks

1. **save-conversation.sh** - PostToolUse hook
   - Saves conversation context after tool usage
   - Fire-and-forget pattern for non-blocking operation
   - Endpoint: `POST /memory/save`

2. **restore-context.sh** - PreToolUse hook
   - Restores context before tool usage
   - Synchronous operation for immediate context availability
   - Endpoint: `POST /context/restore`

3. **session-start.sh** - SessionStart hook
   - Runs when Claude Code session starts
   - Injects initial context from memory
   - Endpoint: `POST /session/start`

4. **session-end.sh** - SessionEnd hook
   - Runs when Claude Code session ends
   - Performs cleanup and final memory save
   - Endpoint: `POST /session/end`

5. **pre-compact.sh** - PreCompact hook
   - Saves full conversation before auto-compact
   - Prevents context loss during compaction
   - Endpoint: `POST /session/precompact`

### Additional Control Hooks (4)

6. **user-prompt-submit.sh** - UserPromptSubmit hook
   - Validates user prompts before submission
   - Can check costs, perform validation
   - Endpoint: `POST /prompt/validate`

7. **stop.sh** - Stop hook
   - Handles agent stop events
   - Workflow control and cleanup
   - Endpoint: `POST /agent/stop`

8. **subagent-stop.sh** - SubagentStop hook
   - Handles subagent lifecycle events
   - Tracks subagent completion
   - Endpoint: `POST /subagent/stop`

9. **notification.sh** - Notification hook
   - Handles generic notification events
   - Monitoring and logging
   - Endpoint: `POST /notification`

## Configuration

### Prerequisites

1. Gobby Client daemon must be running:
   ```bash
   gobby-client start
   ```

2. Configure daemon URL (optional, defaults to localhost:8765):
   ```bash
   export GOBBY_DAEMON_HOST=localhost
   export GOBBY_DAEMON_PORT=8765
   ```

### Claude Code Integration

Add hooks configuration to your Claude Code settings. You can either:

**Option 1: Use settings.json** (if supported)
```json
{
  "hooks": {
    "PostToolUse": [{
      "matcher": "*",
      "hooks": [{"type": "command", "command": "src/gobby/hooks/save-conversation.sh"}]
    }],
    "SessionStart": [{
      "matcher": "*",
      "hooks": [{"type": "command", "command": "src/gobby/hooks/session-start.sh"}]
    }]
    // ... add other hooks as needed
  }
}
```

**Option 2: Use command-line flags**
```bash
claude \
  --on-post-tool-use src/gobby/hooks/save-conversation.sh \
  --on-session-start src/gobby/hooks/session-start.sh \
  --on-pre-compact src/gobby/hooks/pre-compact.sh
```

See `.claude/hooks-example.json` for a complete configuration example with all 9 hooks.

## Hook Script Behavior

### Fire-and-Forget Pattern
Used by: `save-conversation.sh`, `session-end.sh`, `pre-compact.sh`, `notification.sh`
- Scripts exit immediately (return 200)
- Processing happens in background
- Never blocks Claude Code operations

### Synchronous Pattern
Used by: `restore-context.sh`, `session-start.sh`
- Wait for response before continuing
- Return data (context) to Claude Code
- Used when immediate feedback is needed

### Validation Pattern
Used by: `user-prompt-submit.sh`, `stop.sh`, `subagent-stop.sh`
- Can return errors to prevent action
- Perform checks before operations
- Used for workflow control

## Environment Variables

All hook scripts support these environment variables:

- `GOBBY_DAEMON_HOST` - Daemon hostname (default: localhost)
- `GOBBY_DAEMON_PORT` - Daemon port (default: 8765)

## Logging

All hooks log to `~/.gobby/logs/hook-<name>.log`

View logs:
```bash
# All hook logs
tail -f ~/.gobby/logs/hook-*.log

# Specific hook
tail -f ~/.gobby/logs/hook-session-start.log
```

## Troubleshooting

### Hook not running
1. Check daemon is running: `gobby-client status`
2. Verify hook script is executable: `chmod +x src/gobby/hooks/*.sh`
3. Check hook logs in `~/.gobby/logs/`

### Daemon not available
Hooks check daemon health using `GET /status` endpoint. If daemon is not running:
- Fire-and-forget hooks: log warning, exit gracefully
- Synchronous hooks: return empty response, exit gracefully

### Context not restoring
1. Check session-start.sh logs
2. Verify daemon can access Gobby Memory MCP server
3. Check for previous session context in memory

## Development

### Testing Hooks Locally

```bash
# Test session-start hook
echo '{"session_id": "test-123", "transcript_path": "/path/to/transcript", "hook_event_name": "SessionStart", "source": "startup"}' | \
  src/gobby/hooks/session-start.sh

# Test save-conversation hook
echo '{"session_id": "test-123", "messages": [], "hook_event_name": "PostToolUse"}' | \
  src/gobby/hooks/save-conversation.sh
```

### Custom Hook Scripts

You can customize these templates or create new hooks:
1. Copy template to `.claude/hooks/`
2. Modify as needed (change endpoint, add logic)
3. Update hooks configuration to point to custom script

## Architecture

```
Claude Code Session
    ↓ (hook trigger)
hook script (bash)
    ↓ (HTTP POST)
gobby-client daemon (FastAPI)
    ↓ (MCP call)
Gobby Memory Server
    ↓ (store/retrieve)
Graphiti Knowledge Graph
```

## Complete Documentation

### Python Hooks (v2.0) - Comprehensive Guides

1. **[Python Hooks Architecture](../../../docs/architecture_v3/04-gobby-client/python-hooks-architecture.md)**
   - System architecture with 15+ Mermaid diagrams
   - Complete hook lifecycle and state machines
   - Communication patterns (HTTP/WebSocket)
   - Memory operations and flows
   - Performance budgets and optimization

2. **[Hook Development Guide](../../../docs/architecture_v3/04-gobby-client/hook-development-guide.md)**
   - Complete BaseHook API reference
   - 6+ extension examples with full code
   - Testing guide (unit, integration, performance)
   - Best practices and patterns
   - Deployment checklist

3. **[Troubleshooting & Migration Guide](../../../docs/architecture_v3/04-gobby-client/troubleshooting-and-migration-guide.md)**
   - 12+ detailed troubleshooting scenarios
   - Performance tuning recommendations
   - Complete bash-to-Python migration guide
   - Debugging techniques
   - Comprehensive FAQ

4. **[Integration Testing README](../../../tests/integration/README.md)**
   - Docker-based test infrastructure
   - Complete test examples
   - Performance benchmarking
   - CI/CD integration

### Legacy Documentation (v1.0)

- [Gobby Client V1 Specification](../../../docs/architecture_v2/gobby-client-v1-spec.md)
- [Gobby Memory MCP Server](../../../docs/architecture_v2/)

## Support

### Getting Help with Python Hooks

1. **Check comprehensive guides above** - Most questions answered there
2. **Check logs:** `tail -f ~/.gobby/logs/hook-*.log`
3. **Run integration tests:** `./tests/docker-test-env.sh start && uv run pytest tests/integration/`
4. **Review examples:** See [Hook Development Guide](../../../docs/architecture_v3/04-gobby-client/hook-development-guide.md)

### For Legacy Bash Hooks

1. Check logs in `~/.gobby/logs/`
2. Verify daemon status: `gobby-client status`
3. Review hook configuration in Claude Code settings
4. Consider migrating to Python hooks (see migration guide)
