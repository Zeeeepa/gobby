---
description: List all stored memories
argument-hint: [--type TYPE] [--min-importance N]
---

List memories using gobby-memory MCP tools.

**Filters:** $ARGUMENTS

Use the `list_memories` tool on the `gobby-memory` server:

```
mcp__gobby__call_tool(
  server_name="gobby-memory",
  tool_name="list_memories",
  arguments={
    "limit": 20
  }
)
```

If the user specified filters like `--type preference` or `--min-importance 0.5`, include those in the arguments.

Display memories in a table format with: ID, Type, Importance, Content (truncated).
