---
name: epic
description: "Quickly create an epic (parent task for large features). Usage: /gobby:epic <title> [description]"
category: core
metadata:
  gobby:
    audience: all
    depth: [0, 1]
---

# /gobby:epic - Create Epic Task

Create an epic task - a parent container for a large feature or initiative that will be broken down into subtasks.

## Usage

```text
/gobby:epic <title>
/gobby:epic <title> - <description>
```

## Examples

```text
/gobby:epic User authentication system
/gobby:epic API v2 migration - Migrate all endpoints from REST to GraphQL with backwards compatibility
/gobby:epic Performance optimization sprint
```

## Tool Schema Reminder

**First time calling a tool this session?** Use `get_tool_schema(server_name, tool_name)` before `call_tool` to get correct parameters. Schemas are cached per session—no need to refetch.

## Action

Create an epic task with the following parameters:

- `title`: The epic title from user input
- `task_type`: "epic"
- `priority`: 2 (medium - epics are tracked but individual subtasks drive priority)

Parse the user input:
- If input contains " - ", split into title and description
- Otherwise, use entire input as title

```python
call_tool(
    server_name="gobby-tasks",
    tool_name="create_task",
    arguments={
        "title": "<parsed title>",
        "description": "<parsed description if any>",
        "task_type": "epic",
        "priority": 2,
        "session_id": "<session_id>"  # Required - from session context
    }
)
```

After creating, confirm with the task reference and suggest next steps:
- "Created epic #127: User authentication system"
- "Use `expand_task` to break this down into subtasks."
