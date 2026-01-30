---
name: starting-sessions
description: First 5 things every session should do. Use at session start or when asked "how do I begin" with Gobby.
category: core
alwaysApply: true
---

# Starting Sessions - Session Startup Checklist

This skill guides you through the essential steps at the start of every Gobby session.

## Session Startup Checklist

### 1. Discover Available Servers

```python
list_mcp_servers()
```

Returns server names and connection status. This shows what MCP servers are available.

### 2. Check Your Session Context

Look for `Gobby Session Ref:` or `Gobby Session ID:` in your system context (injected by SessionStart hook):

```text
Gobby Session Ref: #5
Gobby Session ID: <uuid>
```

**Note**: All `session_id` parameters accept #N, N, UUID, or prefix formats.

If not present, retrieve it:

```python
call_tool("gobby-sessions", "get_current_session", {
    "external_id": "<your-cli-session-id>",
    "source": "claude"  # or "gemini", "codex"
})
```

### 3. Discover Available Skills

```python
list_skills()
```

Returns skill names and descriptions (~100 tokens/skill). Use `get_skill(name="...")` for full content when needed.

### 4. Create or Claim a Task

**Before editing any files**, you must have an active task:

```python
# Create new task
call_tool("gobby-tasks", "create_task", {
    "title": "Your task title",
    "task_type": "task",  # or bug, feature, epic
    "session_id": "<your_session_id>"
})

# Set to in_progress
call_tool("gobby-tasks", "update_task", {
    "task_id": "<task_id>",
    "status": "in_progress"
})
```

Or claim an existing task:

```python
call_tool("gobby-tasks", "suggest_next_task", {"session_id": "<your_session_id>"})
```

### 5. Use Progressive Tool Disclosure

Never assume tool schemas. Before calling an unfamiliar tool:

```python
# First, list tools on the server
list_tools(server="gobby-tasks")

# Then get full schema when needed
get_tool_schema(server_name="gobby-tasks", tool_name="create_task")

# Now call the tool
call_tool(server_name="gobby-tasks", tool_name="create_task", arguments={...})
```

## Key Rules

- **Always have a task** before using Edit/Write tools
- **Pass session_id** to `create_task` (required), `claim_task` (required), and `close_task` (optional, for tracking)
- **Never load all schemas upfront** - use progressive disclosure
- **Check skills** when stuck - `search_skills(query="your problem")`
