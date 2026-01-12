---
description: Delete a memory by ID
argument-hint: <memory_id>
---

Delete the specified memory using gobby-memory MCP tools.

**Memory ID:** $ARGUMENTS

Use the `forget` tool on the `gobby-memory` server:

```
mcp__gobby__call_tool(
  server_name="gobby-memory",
  tool_name="forget",
  arguments={
    "memory_id": "<the memory ID above>"
  }
)
```

Confirm the memory was deleted.
