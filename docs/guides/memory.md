# Memory System Guide

Gobby's memory system enables AI agents to maintain persistent knowledge across sessions. Unlike traditional AI assistants that start fresh each conversation, agents using Gobby can remember facts, learn preferences, and apply patterns automatically.

## Quick Start

```bash
# Store a memory via CLI
gobby memory create "This project uses pytest fixtures in conftest.py" --type fact

# Recall memories
gobby memory recall "testing"

# List all memories
gobby memory list

# Via MCP tools (in AI session)
call_tool(server_name="gobby-memory", tool_name="create_memory", arguments={
    "content": "User prefers tabs over spaces",
    "memory_type": "preference",
    "importance": 0.9
})
```

## Concepts

### Memory Types

| Type | Purpose | Examples |
| ---- | ------- | -------- |
| `fact` | Objective information about the project | "Uses PostgreSQL with Prisma ORM", "Main entry point is src/index.ts" |
| `preference` | User preferences and coding style | "Prefers functional components", "Use single quotes" |
| `pattern` | Recurring patterns and conventions | "All API routes follow /api/v1/{resource}", "Tests use describe/it blocks" |
| `context` | Session-specific or temporary context | "Currently refactoring auth module", "Debugging production issue #123" |

### Importance Levels

Importance (0.0-1.0) determines recall priority:

| Range | Level | Use For |
| ----- | ----- | ------- |
| 0.8-1.0 | Critical | Must-know facts, breaking changes, security concerns |
| 0.5-0.8 | Important | Key patterns, strong preferences, architectural decisions |
| 0.3-0.5 | Useful | Helpful context, nice-to-know information |
| 0.0-0.3 | Low | Minor details, temporary notes |

### Memory Scope

- **Project memories**: Tied to a specific project (`project_id` set)
- **Global memories**: Available across all projects (`project_id` is NULL)

Use `--global` flag in CLI or omit `project_id` in MCP tools for global memories.

## CLI Commands

### Adding Memories

```bash
# Basic memory
gobby memory create "Content here"

# With type and importance
gobby memory create "API uses JWT auth" --type fact --importance 0.8

# Global memory (available in all projects)
gobby memory create "Always use conventional commits" --type preference --global

# With tags
gobby memory create "Use pnpm, not npm" --type preference --tags "tooling,package-manager"
```

### Searching and Listing

```bash
# Semantic search
gobby memory search "authentication"

# List all memories
gobby memory list

# Filter by type
gobby memory list --type preference

# Filter by minimum importance
gobby memory list --min-importance 0.7

# Limit results
gobby memory list --limit 10

# Include global memories
gobby memory list --include-global
```

### Tag Filtering

Filter memories using boolean tag logic with `--tags-all`, `--tags-any`, and `--tags-none`:

```bash
# Require ALL specified tags (AND logic)
gobby memory recall --tags-all "auth,security"

# Require ANY of the specified tags (OR logic)
gobby memory recall --tags-any "frontend,ui,react"

# Exclude memories with these tags (NOT logic)
gobby memory recall --tags-none "deprecated,legacy"

# Combine filters for precise queries
gobby memory recall "API" --tags-all "backend" --tags-none "deprecated"

# Works with list command too
gobby memory list --type fact --tags-any "database,storage"
```

| Flag | Logic | Description |
| ---- | ----- | ----------- |
| `--tags-all` | AND | Memory must have ALL specified tags |
| `--tags-any` | OR | Memory must have at least ONE of the tags |
| `--tags-none` | NOT | Memory must have NONE of the specified tags |

### Managing Memories

```bash
# Show details of a specific memory
gobby memory show MEMORY_ID

# Update an existing memory
gobby memory update MEMORY_ID --importance 0.9 --tags "updated,important"

# Delete a memory
gobby memory delete MEMORY_ID

# Export memories as markdown
gobby memory export [--output FILE]

# Get statistics
gobby memory stats
```

### Syncing to Git

```bash
# Export memories to .gobby/memories.jsonl
gobby memory sync --export

# Import memories from .gobby/memories.jsonl
gobby memory sync --import

# Full sync (import then export)
gobby memory sync
```

## MCP Tools

Access via `call_tool(server_name="gobby-memory", ...)`:

### create_memory

Store a new memory:

```python
call_tool(server_name="gobby-memory", tool_name="create_memory", arguments={
    "content": "This project uses ESLint with Prettier",
    "memory_type": "fact",
    "importance": 0.7,
    "tags": ["tooling", "linting"]
})
```

### search_memories

Retrieve memories with optional filtering:

```python
# Semantic search
call_tool(server_name="gobby-memory", tool_name="search_memories", arguments={
    "query": "testing setup"
})

# With filters
call_tool(server_name="gobby-memory", tool_name="search_memories", arguments={
    "memory_type": "preference",
    "min_importance": 0.5,
    "limit": 10
})

# With tag filtering (AND/OR/NOT logic)
call_tool(server_name="gobby-memory", tool_name="search_memories", arguments={
    "query": "API design",
    "tags_all": ["backend", "api"],     # Must have ALL these tags
    "tags_any": ["rest", "graphql"],    # Must have at least ONE
    "tags_none": ["deprecated"]         # Must not have any of these
})
```

### list_memories

List all memories with filtering:

```python
call_tool(server_name="gobby-memory", tool_name="list_memories", arguments={
    "memory_type": "fact",
    "limit": 20
})

# With tag filtering
call_tool(server_name="gobby-memory", tool_name="list_memories", arguments={
    "tags_any": ["architecture", "design-decision"],
    "min_importance": 0.6
})
```

### get_memory

Get full details of a specific memory:

```python
call_tool(server_name="gobby-memory", tool_name="get_memory", arguments={
    "memory_id": "mm-abc123"
})
```

### update_memory

Update an existing memory:

```python
call_tool(server_name="gobby-memory", tool_name="update_memory", arguments={
    "memory_id": "mm-abc123",
    "importance": 0.9,
    "tags": ["updated", "important"]
})
```

### delete_memory

Delete a memory:

```python
call_tool(server_name="gobby-memory", tool_name="delete_memory", arguments={
    "memory_id": "mm-abc123"
})
```

### memory_stats

Get memory statistics:

```python
call_tool(server_name="gobby-memory", tool_name="memory_stats", arguments={})
# Returns: count by type, average importance, total count
```

### get_related_memories

Get memories related via cross-references:

```python
call_tool(server_name="gobby-memory", tool_name="get_related_memories", arguments={
    "memory_id": "mm-abc123"
})
```

### remember_with_image

Create a memory from an image (uses LLM to describe):

```python
call_tool(server_name="gobby-memory", tool_name="remember_with_image", arguments={
    "image_path": "/path/to/screenshot.png",
    "memory_type": "context",
    "importance": 0.7
})
```

### remember_screenshot

Create a memory from raw screenshot bytes (base64 encoded):

```python
call_tool(server_name="gobby-memory", tool_name="remember_screenshot", arguments={
    "image_data": "<base64_encoded_bytes>",
    "memory_type": "context"
})
```

### export_memory_graph

Export memories as an interactive HTML knowledge graph:

```python
call_tool(server_name="gobby-memory", tool_name="export_memory_graph", arguments={
    "output_path": "/path/to/graph.html"
})
```

## Architecture

### Storage Model

SQLite is always the source of truth for memories. All memories are stored locally in `~/.gobby/gobby-hub.db` via the `LocalMemoryManager`. The `StorageAdapter` wraps this with an async `MemoryBackendProtocol` interface for consistent CRUD operations.

### Operating Modes

Gobby's memory system operates in one of two modes:

**Standalone mode** (default):
- SQLite storage + local search (TF-IDF, embeddings, or hybrid)
- Search powered by `SearchCoordinator` → `UnifiedSearcher`
- Zero external dependencies for TF-IDF; embedding modes require an API key (OpenAI, etc.)
- Works out of the box with no additional setup

### Search Pipeline

```
Query → SearchCoordinator
         ├─ tfidf/text modes → sync SearchBackend (TF-IDF or substring)
         ├─ auto/embedding/hybrid → UnifiedSearcher (async)
         │    ├─ TF-IDF scoring
         │    ├─ Embedding similarity (cosine)
         │    └─ Hybrid: weighted combination
         └─ Fallback → text search (on any error)
```

## Search Modes

The `search_backend` config controls how memories are recalled. Each mode trades off between accuracy and dependency requirements.

| Mode | Description | Requirements |
| ---- | ----------- | ------------ |
| `tfidf` | TF-IDF scoring — fast, local, no API calls | None |
| `text` | Simple substring matching — fastest, least accurate | None |
| `embedding` | Semantic search via embeddings — most accurate | Embedding API key |
| `auto` | Tries embeddings first, falls back to TF-IDF | None (degrades gracefully) |
| `hybrid` | Weighted combination of TF-IDF + embedding scores | Embedding API key |

### Choosing a Search Mode

- **Starting out?** Use `auto` (the default). It tries embeddings if an API key is available, otherwise falls back to TF-IDF.
- **No API key / air-gapped?** Use `tfidf` for zero-dependency local search.
- **Best recall quality?** Use `hybrid` — combines semantic understanding with keyword matching.
- **Minimal latency?** Use `tfidf` or `text` to avoid embedding API calls.

### Embedding Providers

Embedding generation uses LiteLLM under the hood, supporting multiple providers:

```yaml
# OpenAI (default)
memory:
  search_backend: auto
  embedding_model: text-embedding-3-small

# OpenAI large model (higher quality, slower)
memory:
  search_backend: hybrid
  embedding_model: text-embedding-3-large

# Local via Ollama (no API key needed)
memory:
  search_backend: embedding
  embedding_model: ollama/nomic-embed-text
```

### Hybrid Search Weights

In `hybrid` mode (and the hybrid component of `auto`), you can tune the balance between TF-IDF keyword matching and semantic embedding similarity:

```yaml
memory:
  search_backend: hybrid
  embedding_weight: 0.6    # Weight for semantic similarity (0.0-1.0)
  tfidf_weight: 0.4        # Weight for keyword matching (0.0-1.0)
```

Higher `embedding_weight` favors conceptual matches ("authentication" finds "login flow"). Higher `tfidf_weight` favors exact keyword overlap.

## Configuration

All memory settings live under `memory:` in `~/.gobby/config.yaml`:

```yaml
memory:
  enabled: true                     # Enable memory system
  backend: local                    # Storage backend: 'local' (SQLite) or 'null' (testing)

  # Search
  search_backend: auto              # tfidf | text | embedding | auto | hybrid
  embedding_model: text-embedding-3-small  # LiteLLM model for embeddings
  embedding_weight: 0.6             # Hybrid: embedding similarity weight
  tfidf_weight: 0.4                 # Hybrid: keyword matching weight

  # Importance & Decay
  importance_threshold: 0.7         # Minimum importance for memory injection
  decay_enabled: true               # Enable importance decay over time
  decay_rate: 0.05                  # Importance decay rate per month
  decay_floor: 0.1                  # Never decay below this importance

  # Cross-references
  auto_crossref: false              # Auto-link similar memories
  crossref_threshold: 0.3           # Minimum similarity for cross-references
  crossref_max_links: 5             # Max cross-references per memory

  # Access tracking
  access_debounce_seconds: 60       # Min seconds between access stat updates

memory_sync:
  enabled: true                     # Enable filesystem backup
  export_debounce: 5.0              # Seconds to wait before export
  export_path: .gobby/memories.jsonl  # Backup file path
```

### Environment Variable Expansion

Config values support `${VAR}` syntax for environment variable expansion at load time:

- `${VAR}` — replaced with the value of `VAR`, or left unchanged if unset
- `${VAR:-default}` — replaced with `VAR`'s value, or `default` if unset/empty

This is useful for API keys:

### Example Configurations

**Standalone with TF-IDF only** (zero dependencies):

```yaml
memory:
  enabled: true
  search_backend: tfidf
```

**Standalone with OpenAI embeddings**:

```yaml
memory:
  enabled: true
  search_backend: auto              # Falls back to TF-IDF if API unavailable
  embedding_model: text-embedding-3-small
```

**Standalone with local Ollama** (no API key needed):

```yaml
memory:
  enabled: true
  search_backend: embedding
  embedding_model: ollama/nomic-embed-text
```

**Hybrid search** (best quality):

```yaml
memory:
  enabled: true
  search_backend: hybrid
  embedding_model: text-embedding-3-small
  embedding_weight: 0.6
  tfidf_weight: 0.4
```

## Automatic Memory Injection

Gobby automatically injects relevant memories at session start via the `memory-lifecycle.yaml` workflow.

### How Injection Works

1. On `session-start`, the workflow triggers `memory_recall_relevant`
2. Memories are retrieved based on project context and importance
3. Formatted as `<project-memory>` block and injected into agent context

### What Gets Injected

```markdown
<project-memory>
## Preferences
- User prefers tabs over spaces
- Always use TypeScript strict mode

## Facts
- This project uses PostgreSQL with Prisma ORM
- Main entry point is src/index.ts

## Patterns
- API routes follow /api/v1/{resource} convention
</project-memory>
```

## Git Synchronization

Memories can be synced to `.gobby/memories.jsonl` for version control and team sharing.

### File Format

{"id":"mm-abc123","memory_type":"fact","content":"Uses PostgreSQL","importance":0.8,"tags":["database"]}
{"id":"mm-def456","memory_type":"preference","content":"Prefers functional style","importance":0.6,"tags":[]}

### Automatic Sync

Configure automatic sync in `~/.gobby/config.yaml`:

```yaml
memory_sync:
  enabled: true              # Enable filesystem backup
  export_debounce: 5.0       # Seconds to wait before export
  export_path: .gobby/memories.jsonl  # Relative to project root or absolute
```

## Cross-CLI Memory Sharing

Memories work seamlessly across Claude Code, Gemini CLI, and Codex CLI:

### How Sharing Works

1. **Unified Storage**: All memories stored in `~/.gobby/gobby-hub.db`
2. **Project Binding**: Memories linked to projects via `.gobby/project.json`
3. **Session Source Tracking**: Each memory tracks which CLI created it

### CLI-Specific Notes

| CLI | Memory Support | Notes |
| --- | -------------- | ----- |
| Claude Code | Full | All memory operations supported |
| Gemini CLI | Full | Requires PR #9070 for hooks |
| Codex CLI | Limited | Read-only via MCP tools |

## Workflow Actions

Use memory in workflow YAML files. See example workflow:

- `memory-aware-dev.yaml` - Development workflow with memory-driven context awareness

### memory_inject

Inject relevant project memories into context:

```yaml
on_session_start:
  - action: memory_inject
    min_importance: 0.3
    description: "Load project context from memories"
```

### memory_sync_import

Import memories from `.gobby/memories.jsonl`:

```yaml
on_session_start:
  - action: memory_sync_import
    description: "Import any new memories from filesystem"
```

### memory_sync_export

Export memories to `.gobby/memories.jsonl` for git sync:

```yaml
on_session_end:
  - action: memory_sync_export
    description: "Export memories to filesystem"
```

### Example: Memory-Aware Development Workflow

```yaml
name: memory-aware-dev
description: "Development workflow with memory-driven context"

phases:
  - name: understand
    on_enter:
      - action: memory_inject
        min_importance: 0.3
      - action: inject_message
        content: |
          Review the project memories above.
          Note new patterns for memory storage.

triggers:
  on_session_start:
    - action: memory_sync_import

  on_session_end:
    - action: memory_sync_export
```

## Best Practices

### Do

- Use high importance (0.8+) for critical project facts
- Store preferences early to establish coding style
- Use semantic descriptions for better recall
- Periodically review and clean up low-value memories
- Export memories to git for team sharing

### Don't

- Store sensitive data (API keys, passwords) in memories
- Create duplicate memories for the same fact
- Use memories for temporary task tracking (use gobby-tasks instead)
- Set all memories to high importance (dilutes signal)

## Troubleshooting

### Memories not being recalled

1. Check importance threshold: `gobby memory list --min-importance 0`
2. Verify project binding: memories may be in different project
3. Check if memory sync is enabled: `gobby memory sync --import`

### Memory injection not working

1. Verify daemon is running: `gobby status`
2. Check workflow is loaded: look for `memory-lifecycle.yaml`
3. Review config: ensure `memory.enabled: true`

### Sync conflicts

## File Locations

| Path | Description |
| ---- | ----------- |
| `~/.gobby/gobby-hub.db` | SQLite database with memories table |
| `.gobby/memories.jsonl` | Git-synced memory export |
| `.gobby/memories_meta.json` | Sync metadata (checksums, timestamps) |
| `~/.gobby/config.yaml` | Memory configuration |

## Related Documentation

- [Memory V4 Plan](../plans/memory-v4.md) - Embeddings integration plan
- [Task Tracking](tasks.md) - Task tracking system
