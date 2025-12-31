---
description: Learn a skill from the current session
argument-hint: <skill name or description>
---

Learn a new skill from this session using gobby-skills MCP tools.

**Skill:** $ARGUMENTS

Use the `learn_skill_from_session` tool on the `gobby-skills` server:

```
mcp__gobby__call_tool(
  server_name="gobby-skills",
  tool_name="learn_skill_from_session",
  arguments={
    "name": "<skill name derived from input>",
    "description": "<description of what the skill does>"
  }
)
```

The skill will be extracted from the current session's work patterns and saved for future use.

After learning, show the skill details and suggest exporting with:
```
mcp__gobby__call_tool(
  server_name="gobby-skills",
  tool_name="export_skills",
  arguments={}
)
```
