---
name: proactive-memory
description: Guidelines for when to proactively save memories during work
category: core
alwaysApply: true
injectionFormat: full
---

# Proactive Memory Capture

When you discover something valuable during work, save it immediately using the gobby-memory MCP server.

## Save a Memory When You:

- **Spent >5 minutes finding information** - root cause of a bug, file location, API behavior
- **Discovered undocumented behavior or limitation** - something not in docs/README/CLAUDE.md
- **Found a workaround for a known issue** - especially if non-obvious
- **Identified a format/schema requirement** - with concrete examples
- **Learned a project-specific convention** - naming patterns, architecture decisions

## Do NOT Save Memories For:

- Generic programming practices (pre-commit hooks, Pydantic validation, etc.)
- Information already in CLAUDE.md, README, or docstrings
- Vague observations ("may", "likely", "should be")
- Temporary state or debugging info
- Obvious code patterns anyone could infer

## How to Save

```python
call_tool("gobby-memory", "create_memory", {
    "content": "Specific insight with concrete details",
    "memory_type": "fact",  # or "pattern"
    "importance": "0.85",
    "tags": "relevant-tag"
})
```

### Memory Types

| Type | Use For |
|------|---------|
| `fact` | Specific, verifiable information (file locations, API behaviors, config values) |
| `pattern` | Recurring approaches or conventions (code patterns, workflow steps) |

### Importance Levels

| Score | When to Use |
|-------|-------------|
| 0.9+ | Critical gotchas that would cause bugs or significant time loss |
| 0.8-0.9 | Valuable insights that save meaningful investigation time |
| 0.7-0.8 | Useful context that helps understand the codebase |
| <0.7 | Skip - probably not worth remembering |

## The 5-Minute Rule

Ask yourself: **"Would finding this again take >5 minutes?"**

- **YES** - Save it now while you have full context
- **NO** - Skip it, the information is readily discoverable

## Examples

### Good Memories

```python
# Root cause after debugging
call_tool("gobby-memory", "create_memory", {
    "content": "MCP tool calls fail silently when server disconnects mid-request. Check connection state in MCPClientManager.call_tool() before assuming tool execution failed.",
    "memory_type": "fact",
    "importance": "0.9",
    "tags": "mcp,debugging"
})

# Undocumented behavior
call_tool("gobby-memory", "create_memory", {
    "content": "SQLite RETURNING clause requires SQLite 3.35+. Ubuntu 20.04 ships 3.31 - use INSERT then SELECT instead for compatibility.",
    "memory_type": "fact",
    "importance": "0.85",
    "tags": "sqlite,compatibility"
})

# Project convention
call_tool("gobby-memory", "create_memory", {
    "content": "Task IDs use #N format (seq_num) for display but UUID internally. Always accept both formats in API parameters.",
    "memory_type": "pattern",
    "importance": "0.8",
    "tags": "tasks,api"
})
```

### Bad Memories (Don't Save)

- "Use pytest fixtures for test setup" - generic practice
- "The config file is at ~/.gobby/config.yaml" - documented in CLAUDE.md
- "This function might need refactoring" - vague observation
- "Set breakpoint on line 42 to debug" - temporary debugging state
