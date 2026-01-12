---
name: nit
description: Quickly create a nitpick/minor cleanup task. Usage: /nit <title> [description]
---

# /nit - Create Nitpick Task

Create a minor cleanup or nitpick task with the provided title and optional description. These are small improvements that don't warrant a full feature or bug.

## Usage

```
/nit <title>
/nit <title> - <description>
```

## Examples

```
/nit Rename confusing variable
/nit Fix typo in error message - "authentification" should be "authentication"
/nit Remove unused import in utils.py
```

## Action

Call `gobby-tasks.create_task` with:
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
        "priority": 4
    }
)
```

After creating, confirm with the task reference (e.g., "Created nitpick #125: Rename confusing variable").
