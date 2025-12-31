---
description: List available skills
argument-hint: [query]
---

List available skills using gobby-skills MCP tools.

**Filter:** $ARGUMENTS

Use the `list_skills` tool on the `gobby-skills` server:

```
mcp__gobby__call_tool(
  server_name="gobby-skills",
  tool_name="list_skills",
  arguments={
    "query": "<optional filter from input>"
  }
)
```

Display skills in a table format with: ID, Name, Description, Usage Count.

To apply a skill, use:
```
mcp__gobby__call_tool(
  server_name="gobby-skills",
  tool_name="apply_skill",
  arguments={"skill_id": "<id>"}
)
```
