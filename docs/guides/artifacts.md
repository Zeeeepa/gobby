# Artifacts Guide

Gobby captures and indexes artifacts from agent sessions, enabling search and retrieval of code snippets, diffs, errors, and plans.

## Quick Start

```bash
# List recent artifacts
gobby artifacts list --limit 10

# Search artifacts by content
gobby artifacts search "authentication"

# Show specific artifact
gobby artifacts show ARTIFACT_ID

# View session timeline
gobby artifacts timeline #42
```

## Concepts

### What Are Artifacts?

Artifacts are structured outputs captured from agent sessions:

| Type | Description | Example |
|------|-------------|---------|
| `code` | Code snippets written | Function implementations |
| `diff` | Git diffs | Changes to files |
| `error` | Error messages | Stack traces, failures |
| `plan` | Plans and specs | Implementation plans |
| `output` | Command output | Test results, build logs |

### Artifact Capture

Artifacts are automatically captured when agents:

- Write or edit code
- Generate diffs
- Encounter errors
- Create plans or specifications
- Run commands with output

### Session Association

Every artifact is linked to a session:

```text
Session #42
├── Artifact: code - "Login component"
├── Artifact: diff - "auth.py changes"
├── Artifact: error - "Type error in handler"
└── Artifact: plan - "Authentication spec"
```

## CLI Commands

### `gobby artifacts list`

List artifacts with optional filters.

```bash
gobby artifacts list [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--session` | Filter by session ID |
| `--type` | Filter by type: code, diff, error, plan, output |
| `--limit N` | Max results (default: 50) |
| `--json` | Output as JSON |

**Examples:**

```bash
# List recent artifacts
gobby artifacts list --limit 20

# List code artifacts from a session
gobby artifacts list --session #42 --type code

# List all errors
gobby artifacts list --type error
```

### `gobby artifacts show`

Display a single artifact by ID.

```bash
gobby artifacts show ARTIFACT_ID
```

Shows full artifact content with metadata.

### `gobby artifacts search`

Search artifacts by content.

```bash
gobby artifacts search QUERY [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--session` | Limit to specific session |
| `--type` | Filter by type |
| `--limit N` | Max results |
| `--json` | Output as JSON |

**Examples:**

```bash
# Search for authentication-related artifacts
gobby artifacts search "authentication"

# Search errors containing specific text
gobby artifacts search "TypeError" --type error

# Search within a session
gobby artifacts search "login" --session #42
```

### `gobby artifacts timeline`

Show artifacts for a session in chronological order.

```bash
gobby artifacts timeline SESSION_ID
```

Displays artifacts as a timeline showing what the agent produced during the session.

**Example output:**

```
Session #42 Timeline
====================

10:30:15  [plan]   Implementation plan for auth
10:32:47  [code]   Login component (src/Login.tsx)
10:35:22  [code]   Auth hook (src/hooks/useAuth.ts)
10:38:01  [error]  Type error in useAuth
10:40:15  [diff]   Fixed type error
10:42:30  [output] Tests passing
```

## MCP Tools

Artifact tools are accessed via the `gobby-sessions` server or dedicated artifact endpoints.

### search_artifacts

Search artifacts by content.

```python
call_tool(server_name="gobby-sessions", tool_name="search_artifacts", arguments={
    "query": "authentication",
    "session_id": "#42",  # optional
    "artifact_type": "code",  # optional
    "limit": 20
})
```

### list_artifacts

List artifacts with filters.

```python
call_tool(server_name="gobby-sessions", tool_name="list_artifacts", arguments={
    "session_id": "#42",
    "artifact_type": "error",
    "limit": 10
})
```

### get_artifact

Get a specific artifact by ID.

```python
call_tool(server_name="gobby-sessions", tool_name="get_artifact", arguments={
    "artifact_id": "<artifact_id>"
})
```

### get_timeline

Get artifacts for a session in chronological order.

```python
call_tool(server_name="gobby-sessions", tool_name="get_timeline", arguments={
    "session_id": "#42"
})
```

## Artifact Types in Detail

### Code Artifacts

Captured when agents write or modify code.

**Metadata includes:**
- File path
- Language
- Line count
- Operation (create, update, delete)

### Diff Artifacts

Captured from git operations.

**Metadata includes:**
- Files changed
- Lines added/removed
- Commit SHA (if committed)

### Error Artifacts

Captured when errors occur.

**Metadata includes:**
- Error type
- Stack trace
- Context (file, line)
- Resolution status

### Plan Artifacts

Captured from planning operations.

**Metadata includes:**
- Plan type (implementation, refactor, etc.)
- Steps/phases
- Associated tasks

### Output Artifacts

Captured from command execution.

**Metadata includes:**
- Command run
- Exit code
- Duration

## Use Cases

### Debugging

Find errors from a specific session:

```bash
gobby artifacts list --session #42 --type error
```

### Code Review

See all code written in a session:

```bash
gobby artifacts timeline #42
```

### Knowledge Mining

Search for patterns across all sessions:

```bash
gobby artifacts search "API endpoint" --type code
```

### Audit Trail

Track what an agent produced:

```bash
gobby artifacts list --session #42
```

## Integration with Other Features

### Tasks

Artifacts can be linked to tasks:

```text
Task #123: Implement auth
├── Session #42
│   ├── Artifact: code - "auth.py"
│   └── Artifact: diff - "auth changes"
└── Commits linked via get_task_diff
```

### Memory

Key artifacts can inform memory creation:

```python
# After finding useful pattern
call_tool("gobby-memory", "create_memory", {
    "content": "Authentication uses JWT with refresh tokens",
    "memory_type": "pattern",
    "importance": 0.8
})
```

### Workflows

Artifacts can satisfy workflow requirements:

```yaml
steps:
  - name: plan
    requires_artifact: plan
  - name: implement
    requires_artifact: code
```

## Best Practices

### Do

- Search artifacts before starting similar work
- Use timeline to understand session flow
- Link important artifacts to tasks
- Create memories from valuable patterns

### Don't

- Rely on artifacts for long-term storage
- Expect artifacts to persist forever
- Store sensitive data in artifacts

## Data Storage

| Path | Description |
|------|-------------|
| `~/.gobby/gobby-hub.db` | Artifact metadata and content |

## See Also

- [sessions.md](sessions.md) - Session management
- [tasks.md](tasks.md) - Task system
- [memory.md](memory.md) - Persistent memory
