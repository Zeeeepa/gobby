---
name: nit
description: "Quickly create a nitpick/minor cleanup task. Usage: /gobby:nit <title> [description]"
category: core
metadata:
  gobby:
    audience: interactive
    depth: 0
---

# /gobby:nit - Create Nitpick Task

Create a minor cleanup or nitpick task with the provided title and optional description. These are small improvements that don't warrant a full feature or bug.

## Usage

```text
/gobby:nit <title>
/gobby:nit <title> - <description>
```

## Examples

```text
/gobby:nit Rename confusing variable
/gobby:nit Fix typo in error message - "authentification" should be "authentication"
/gobby:nit Remove unused import in utils.py
```

## Tool Schema Reminder

**First time calling a tool this session?** Use `get_tool_schema(server_name, tool_name)` before `call_tool` to get correct parameters. Schemas are cached per session—no need to refetch.

## Action

Create a nitpick task with the following parameters:

- `title`: The nitpick title from user input
- `task_type`: "chore"
- `labels`: ["nitpick"]
- `priority`: 4 (backlog - low priority, do when convenient)

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
        "task_type": "chore",
        "labels": ["nitpick"],
        "priority": 4,
        "session_id": "<session_id>"  # Required - from session context
    }
)
```

After creating, confirm with the task reference (e.g., "Created nitpick #125: Rename confusing variable").
