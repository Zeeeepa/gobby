---
name: proactive-memory
description: Guidelines for when to proactively save memories during work
category: core
alwaysApply: true
injectionFormat: full
---

# Proactive Memory Capture

When you discover something valuable during work, save it immediately using the gobby-memory MCP server.

## What to Save

Focus on **coding-specific insights** that would save a future session significant time:

- **Debugging insights** - root causes, misleading error messages, non-obvious failure modes
- **Architecture decisions** - why something is structured a certain way, trade-offs made
- **API/library behaviors** - undocumented quirks, version-specific gotchas, parameter edge cases
- **Project conventions** - naming patterns, file organization rules, commit message formats
- **Environment gotchas** - OS-specific issues, dependency conflicts, config requirements

### The Time-Savings Test

Ask: **"Would this save a future session more than 5 minutes of investigation?"**

- **YES** → Save it now while you have full context
- **NO** → Skip it, the information is readily discoverable

## Do NOT Save

- Generic programming knowledge (how pytest fixtures work, Pydantic validation, etc.)
- Information already in CLAUDE.md, README, or docstrings
- Vague observations ("may", "likely", "should be")
- Temporary state or debugging breadcrumbs
- Content from system-injected messages or hook output (these are generated, not discovered)

## Before Creating a Memory

**Check for duplicates first.** Call `search_memories` with a relevant query before creating a new memory. If a similar memory already exists, either skip or `update_memory` to refine it instead of creating a duplicate.

The `create_memory` response includes a `similar_existing` field showing the top 3 similar memories — review these after creation and `delete_memory` if you accidentally duplicated.

## How to Save

```python
call_tool("gobby-memory", "create_memory", {
    "content": "Specific insight with concrete details",
    "memory_type": "fact",  # or "pattern"
    "tags": "relevant-tag"
})
```

### Memory Types

| Type | Use For |
|------|---------|
| `fact` | Specific, verifiable information (file locations, API behaviors, config values) |
| `pattern` | Recurring approaches or conventions (code patterns, workflow steps) |

Importance defaults to 0.8 — don't override unless you have a strong reason. Decay handles the rest.

## Examples

### Good Memories

```python
# Root cause after debugging
call_tool("gobby-memory", "create_memory", {
    "content": "MCP tool calls fail silently when server disconnects mid-request. Check connection state in MCPClientManager.call_tool() before assuming tool execution failed.",
    "memory_type": "fact",
    "tags": "mcp,debugging"
})

# Undocumented behavior
call_tool("gobby-memory", "create_memory", {
    "content": "SQLite RETURNING clause requires SQLite 3.35+. Ubuntu 20.04 ships 3.31 - use INSERT then SELECT instead for compatibility.",
    "memory_type": "fact",
    "tags": "sqlite,compatibility"
})

# Project convention
call_tool("gobby-memory", "create_memory", {
    "content": "Task IDs use #N format (seq_num) for display but UUID internally. Always accept both formats in API parameters.",
    "memory_type": "pattern",
    "tags": "tasks,api"
})
```

### Bad Memories (Don't Save)

- "Use pytest fixtures for test setup" — generic practice
- "The config file is at ~/.gobby/config.yaml" — documented in CLAUDE.md
- "This function might need refactoring" — vague observation
- "Set breakpoint on line 42 to debug" — temporary debugging state
