---
description: Search and retrieve memories
argument-hint: [query]
---

Search memories using gobby-memory MCP tools.

**Query:** $ARGUMENTS

Use the `recall` tool on the `gobby-memory` server:

```
mcp__gobby__call_tool(
  server_name="gobby-memory",
  tool_name="recall",
  arguments={
    "query": "<the query above, or empty for recent memories>",
    "limit": 10
  }
)
```

Display the matching memories with their IDs, types, and importance scores.
