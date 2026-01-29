# Session Management Guide

Gobby provides persistent session management that survives restarts and enables context handoff between sessions.

## Quick Start

```bash
# List recent sessions
gobby sessions list

# Show session details
gobby sessions show #42

# View session transcript
gobby sessions messages #42

# Create handoff for another session to pick up
gobby sessions create-handoff #42
```

```python
# MCP: Get your current session ID (the correct way)
call_tool(server_name="gobby-sessions", tool_name="get_current_session", arguments={
    "external_id": "<your_claude_session_id>",
    "source": "claude"
})

# Pick up context from a previous session
call_tool(server_name="gobby-sessions", tool_name="pickup", arguments={
    "from_session": "#42"
})
```

## Concepts

### Session Lifecycle

```text
created → active → paused → handoff_ready → completed
                     ↑          ↓
                   resumed ← picked_up
```

- **created**: Session registered but no work yet
- **active**: Currently in use
- **paused**: Temporarily stopped (can resume)
- **handoff_ready**: Handoff context generated
- **completed**: Session finished with summary

### Session Sources

Gobby tracks which CLI created each session:

| Source | Description |
|--------|-------------|
| `claude` | Claude Code |
| `gemini` | Gemini CLI |
| `codex` | OpenAI Codex CLI |
| `api` | Direct API/webhook |

### Parent-Child Sessions

Sessions can spawn child sessions (subagents):

```text
Parent Session (#42)
├── Child Session (#43) - "Implement auth"
├── Child Session (#44) - "Write tests"
└── Child Session (#45) - "Update docs"
```

Child sessions inherit project context and can send messages back to the parent.

### Session Context

Each session maintains:

- **Messages**: Full conversation transcript
- **Tasks**: Tasks created or touched during the session
- **Commits**: Git commits made during the session timeframe
- **Artifacts**: Code snippets, diffs, errors captured
- **Workflow state**: Active workflow and current step

## CLI Commands

### `gobby sessions list`

List sessions with optional filtering.

```bash
gobby sessions list [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--project REF` | Filter by project |
| `--status STATUS` | Filter by status |
| `--limit N` | Max sessions (default: 20) |
| `--json` | Output as JSON |

### `gobby sessions show`

Show session details.

```bash
gobby sessions show SESSION_ID
```

Accepts `#N` (project-scoped), UUID, or prefix.

### `gobby sessions messages`

View session transcript.

```bash
gobby sessions messages SESSION_ID [--limit N] [--role ROLE]
```

| Option | Description |
|--------|-------------|
| `--limit N` | Max messages (default: 50) |
| `--role ROLE` | Filter by role: user, assistant, tool |

### `gobby sessions search`

Search messages across sessions.

```bash
gobby sessions search QUERY [OPTIONS]
```

Uses full-text search (FTS) across message content.

### `gobby sessions stats`

Show session statistics.

```bash
gobby sessions stats
```

### `gobby sessions create-handoff`

Create handoff context for a session.

```bash
gobby sessions create-handoff SESSION_ID
```

Extracts structured context for another session to pick up.

### `gobby sessions delete`

Delete a session.

```bash
gobby sessions delete SESSION_ID
```

## MCP Tools

### get_current_session

**Get YOUR current session ID** - the correct way to look up your session.

```python
call_tool(server_name="gobby-sessions", tool_name="get_current_session", arguments={
    "external_id": "<your_external_session_id>",
    "source": "claude"  # or "gemini", "codex"
})
```

**Important**: Use this instead of `list_sessions` to find your own session. `list_sessions` is for browsing other sessions.

### get_session

Get session details by ID.

```python
call_tool(server_name="gobby-sessions", tool_name="get_session", arguments={
    "session_id": "#42"  # or UUID or prefix
})
```

### list_sessions

List sessions with filters (NOT for finding your own session).

```python
call_tool(server_name="gobby-sessions", tool_name="list_sessions", arguments={
    "status": "active",
    "limit": 10
})
```

### session_stats

Get session statistics for the project.

```python
call_tool(server_name="gobby-sessions", tool_name="session_stats", arguments={})
```

### get_session_messages

Get messages for a session.

```python
call_tool(server_name="gobby-sessions", tool_name="get_session_messages", arguments={
    "session_id": "#42",
    "limit": 50,
    "role": "assistant"  # optional filter
})
```

### search_messages

Search messages using Full Text Search (FTS).

```python
call_tool(server_name="gobby-sessions", tool_name="search_messages", arguments={
    "query": "authentication bug",
    "limit": 20
})
```

### get_session_commits

Get git commits made during a session timeframe.

```python
call_tool(server_name="gobby-sessions", tool_name="get_session_commits", arguments={
    "session_id": "#42"
})
```

### get_handoff_context

Get the handoff context (compact_markdown) for a session.

```python
call_tool(server_name="gobby-sessions", tool_name="get_handoff_context", arguments={
    "session_id": "#42"
})
```

### create_handoff

Create handoff context by extracting structured data from the transcript.

```python
call_tool(server_name="gobby-sessions", tool_name="create_handoff", arguments={
    "session_id": "#42"
})
```

### pickup

Restore context from a previous session's handoff.

```python
call_tool(server_name="gobby-sessions", tool_name="pickup", arguments={
    "from_session": "#42"
})
```

For CLIs/IDEs without hooks, this injects the handoff context.

### mark_loop_complete

Mark the autonomous loop as complete, preventing session chaining.

```python
call_tool(server_name="gobby-sessions", tool_name="mark_loop_complete", arguments={
    "session_id": "<your_session_id>"
})
```

## Session Handoff

Handoff enables seamless context transfer between sessions.

### Creating a Handoff

1. Session reaches a stopping point
2. Call `create_handoff` to extract structured context
3. Context includes: summary, active tasks, key decisions, next steps

### Picking Up a Handoff

1. New session starts
2. Call `pickup` with the previous session ID
3. Handoff context is injected into the new session

### Handoff Content

The handoff includes:

```markdown
## Session Summary
Brief description of what was accomplished.

## Active Tasks
- #123: Implement auth (in_progress)
- #124: Write tests (blocked by #123)

## Key Decisions
- Using JWT for authentication
- Storing tokens in httpOnly cookies

## Next Steps
1. Complete the login endpoint
2. Add refresh token support
```

## Cross-CLI Support

Sessions work seamlessly across Claude Code, Gemini CLI, and Codex CLI.

### How It Works

1. **Unified Storage**: All sessions stored in `~/.gobby/gobby-hub.db`
2. **Hook Integration**: CLIs trigger session events via hooks
3. **Context Restoration**: Each CLI can pick up context from any other

### Hook Events

| Event | Trigger | Action |
|-------|---------|--------|
| `SessionStart` | CLI starts | Register session, restore context |
| `PromptSubmit` | User sends message | Update title, track message |
| `Stop` | CLI pauses | Mark session as paused |
| `SessionEnd` | CLI exits | Generate summary |

## Best Practices

### Do

- Use `get_current_session` to find your session ID
- Create handoffs before long breaks
- Link tasks to sessions for traceability
- Use meaningful session titles

### Don't

- Use `list_sessions` to find your own session
- Delete sessions with important context
- Ignore handoff context when picking up work

## Troubleshooting

### Session not found

1. Check if daemon is running: `gobby status`
2. Verify project: session may be in different project
3. Use `#N` format for project-scoped lookup

### Handoff context empty

1. Ensure session has messages
2. Check if `create_handoff` was called
3. Verify session status is `handoff_ready`

### Hook not triggering

1. Verify hooks are installed: `gobby install`
2. Check hook configuration in CLI settings
3. Review daemon logs: `~/.gobby/logs/gobby.log`

## Data Storage

| Path | Description |
|------|-------------|
| `~/.gobby/gobby-hub.db` | SQLite database with sessions table |
| `~/.gobby/logs/` | Session-related logs |

## See Also

- [tasks.md](tasks.md) - Task management
- [agents.md](agents.md) - Subagent spawning
- [memory.md](memory.md) - Persistent memory
- [mcp-tools.md](mcp-tools.md) - Full MCP tool reference
