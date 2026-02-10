# Artifacts Guide

Gobby captures and indexes artifacts from agent sessions, enabling search and retrieval of code snippets, diffs, errors, and plans. Agents can also explicitly save artifacts via MCP tools.

## Quick Start

```bash
# List recent artifacts
gobby artifacts list --limit 10

# Search artifacts by content
gobby artifacts search "authentication"

# Show specific artifact with tags
gobby artifacts show ARTIFACT_ID

# View session timeline
gobby artifacts timeline #42

# Export artifact to file
gobby artifacts export ARTIFACT_ID --output code.py
```

## Concepts

### What Are Artifacts?

Artifacts are structured outputs captured from agent sessions:

| Type | Value | Description | Example |
|------|-------|-------------|---------|
| Code | `code` | Code snippets written | Function implementations |
| Diff | `diff` | Git diffs | Changes to files |
| Error | `error` | Error messages | Stack traces, failures |
| Plan | `plan` | Plans and specs | Implementation plans |
| Command Output | `command_output` | Command output | Test results, build logs |
| File Path | `file_path` | File path references | Referenced source files |
| Structured Data | `structured_data` | JSON/YAML/structured content | Config objects, API responses |
| Text | `text` | General text content | Notes, explanations |

### Artifact Fields

Each artifact has:

| Field | Description |
|-------|-------------|
| `id` | Unique identifier |
| `session_id` | Session that produced it |
| `artifact_type` | One of the types above |
| `content` | The artifact content |
| `title` | Auto-generated or explicit title |
| `task_id` | Linked task (auto-inferred or explicit) |
| `source_file` | Source file path (if applicable) |
| `metadata` | Type-specific metadata (language, etc.) |
| `tags` | User/agent-assigned labels |
| `created_at` | Timestamp |

### Artifact Capture

Artifacts are captured in two ways:

**Automatic capture** — The auto-capture hook extracts artifacts from assistant messages:
- Code blocks (with language metadata)
- File path references
- Title auto-generated from content
- Task auto-inferred from session's active task

**Explicit save** — Agents use the `save_artifact` MCP tool to intentionally create artifacts with title, type, task link, and metadata.

### Tagging

Artifacts support tags for organization and discovery:

```python
# Add a tag
call_tool("gobby-artifacts", "tag_artifact", {
    "artifact_id": "<id>",
    "tag": "auth"
})

# Remove a tag
call_tool("gobby-artifacts", "untag_artifact", {
    "artifact_id": "<id>",
    "tag": "auth"
})
```

Tags appear in CLI `show` output and can be used to filter in the web UI.

### Session and Task Association

Every artifact is linked to a session. Artifacts can also be linked to tasks:

```text
Task #123: Implement auth
├── Session #42
│   ├── Artifact: code - "Login component" [auth, frontend]
│   ├── Artifact: diff - "auth.py changes"
│   └── Artifact: error - "Type error in handler"
└── Session #43
    └── Artifact: code - "Auth tests"
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
| `--type` | Filter by type (code, diff, error, plan, command_output, file_path, structured_data, text) |
| `--limit N` | Max results (default: 100) |
| `--offset N` | Pagination offset |
| `--json` | Output as JSON |

Output includes title and task ref columns.

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
gobby artifacts show ARTIFACT_ID [--verbose] [--json]
```

Shows full artifact content with metadata, title, task link, and tags. Use `--verbose` for full metadata JSON.

### `gobby artifacts search`

Search artifacts by content using full-text search.

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
gobby artifacts timeline SESSION_ID [--type TYPE] [--limit N] [--json]
```

Displays artifacts as a timeline with titles showing what the agent produced.

### `gobby artifacts export`

Export an artifact's content to stdout or a file.

```bash
gobby artifacts export ARTIFACT_ID [--output PATH]
```

If `--output` is given, writes to that path. The file extension is derived from the artifact type and language metadata if not specified in the path (e.g., `.py` for Python code, `.diff` for diffs, `.md` for plans).

**Examples:**

```bash
# Print content to stdout
gobby artifacts export abc123

# Export to file (extension auto-derived)
gobby artifacts export abc123 --output my_code

# Export with explicit extension
gobby artifacts export abc123 --output changes.patch
```

## MCP Tools

Artifact tools are accessed via the `gobby-artifacts` server. Use progressive disclosure:

```python
list_tools(server_name="gobby-artifacts")
get_tool_schema(server_name="gobby-artifacts", tool_name="save_artifact")
```

### Read Tools

#### search_artifacts

Search artifacts by content using full-text search.

```python
call_tool("gobby-artifacts", "search_artifacts", {
    "query": "authentication",
    "session_id": "#42",       # optional
    "artifact_type": "code",   # optional
    "task_id": "<task_id>",    # optional
    "tag": "auth",             # optional
    "limit": 20
})
```

#### list_artifacts

List artifacts with filters.

```python
call_tool("gobby-artifacts", "list_artifacts", {
    "session_id": "#42",
    "artifact_type": "error",
    "task_id": "<task_id>",    # optional
    "tag": "bugfix",           # optional
    "limit": 10
})
```

#### get_artifact

Get a specific artifact by ID.

```python
call_tool("gobby-artifacts", "get_artifact", {
    "artifact_id": "<artifact_id>"
})
```

#### get_timeline

Get artifacts for a session in chronological order.

```python
call_tool("gobby-artifacts", "get_timeline", {
    "session_id": "#42"
})
```

#### list_artifacts_by_task

List all artifacts linked to a specific task.

```python
call_tool("gobby-artifacts", "list_artifacts_by_task", {
    "task_id": "#123",
    "artifact_type": "code"    # optional
})
```

### Write Tools

#### save_artifact

Explicitly save an artifact. Auto-classifies type if not provided.

```python
call_tool("gobby-artifacts", "save_artifact", {
    "content": "def authenticate(user, password): ...",
    "session_id": "#42",
    "artifact_type": "code",         # optional — auto-classified if omitted
    "title": "Auth function",        # optional
    "task_id": "#123",               # optional
    "metadata": {"language": "python"},  # optional
    "source_file": "src/auth.py",    # optional
    "line_start": 10,                # optional
    "line_end": 25                   # optional
})
```

#### delete_artifact

Delete an artifact by ID.

```python
call_tool("gobby-artifacts", "delete_artifact", {
    "artifact_id": "<artifact_id>"
})
```

#### tag_artifact

Add a tag to an artifact.

```python
call_tool("gobby-artifacts", "tag_artifact", {
    "artifact_id": "<artifact_id>",
    "tag": "auth"
})
```

#### untag_artifact

Remove a tag from an artifact.

```python
call_tool("gobby-artifacts", "untag_artifact", {
    "artifact_id": "<artifact_id>",
    "tag": "auth"
})
```

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

### Task Audit

See everything produced for a specific task:

```python
call_tool("gobby-artifacts", "list_artifacts_by_task", {"task_id": "#123"})
```

### Export and Share

Export an artifact for use outside Gobby:

```bash
gobby artifacts export abc123 --output implementation.py
```

## Integration with Other Features

### Tasks

Artifacts are linked to tasks automatically (via active task inference) or explicitly (via `save_artifact` with `task_id`).

### Memory

Key artifacts can inform memory creation:

```python
call_tool("gobby-memory", "create_memory", {
    "content": "Authentication uses JWT with refresh tokens",
    "memory_type": "pattern",
    "importance": 0.8
})
```

### Web UI

The Artifacts tab in the web UI provides:
- Sidebar with search, type filter chips, and date-grouped artifact list
- Detail panel with syntax-highlighted content, tag management, and metadata
- Copy and delete actions

## Data Storage

| Path | Description |
|------|-------------|
| `~/.gobby/gobby-hub.db` | Artifact metadata and content (session_artifacts table) |
| `~/.gobby/gobby-hub.db` | Artifact tags (artifact_tags table) |

## See Also

- [sessions.md](sessions.md) - Session management
- [tasks.md](tasks.md) - Task system
- [memory.md](memory.md) - Persistent memory
