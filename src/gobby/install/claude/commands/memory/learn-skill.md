---
description: Learn a skill from the current session
argument-hint: Use this tool to automatically extract skills from a session that went well.
---

**Usage**:

```bash
mcp_call_tool("gobby-skills", "learn_skills_from_session", {"session_id": "<session_id>"})
```

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
