---
description: Store a memory for future sessions
argument-hint: <content to remember>
---

Store this memory using gobby-memory MCP tools:

**Content to remember:** $ARGUMENTS

Use the `remember` tool on the `gobby-memory` server:

```
mcp__gobby__call_tool(
  server_name="gobby-memory",
  tool_name="remember",
  arguments={
    "content": "<the content above>",
    "memory_type": "preference",
    "importance": 0.7
  }
)
```

After storing, confirm the memory was saved and show its ID.

**Memory types:** `fact`, `preference`, `pattern`, `context`
- Use `preference` for user preferences and coding style choices
- Use `fact` for project facts and technical details
- Use `pattern` for recurring code patterns
- Use `context` for background project context
