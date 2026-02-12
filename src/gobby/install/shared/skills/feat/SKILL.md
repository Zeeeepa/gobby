---
name: feat
description: "Quickly create a feature task. Usage: /feat <title> [description]"
category: core
triggers: feature, new feature
metadata:
  gobby:
    audience: all
    format_overrides:
      autonomous: full
---

# /feat - Create Feature Task

Create a new feature task with the provided title and optional description.

## Usage

```
/feat <title>
/feat <title> - <description>
```

## Examples

```
/feat Add dark mode toggle
/feat User profile avatars - Allow users to upload custom profile pictures with cropping support
```

## Tool Schema Reminder

**First time calling a tool this session?** Use `get_tool_schema(server_name, tool_name)` before `call_tool` to get correct parameters. Schemas are cached per session—no need to refetch.

## Action

Create a feature task with the following parameters:

- `title`: The feature title from user input
- `task_type`: "feature"
- `priority`: 2 (medium - standard priority for new features)

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
        "task_type": "feature",
        "priority": 2,
        "session_id": "<session_id>"  # Required - from session context
    }
)
```

After creating, confirm with the task reference (e.g., "Created feature #124: Add dark mode toggle").
