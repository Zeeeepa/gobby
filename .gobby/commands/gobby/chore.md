---
name: chore
description: Quickly create a chore/maintenance task. Usage: /chore <title> [description]
---

# /chore - Create Chore Task

Create a maintenance or housekeeping task with the provided title and optional description. For tasks that keep the codebase healthy but aren't features or bugs.

## Usage

```
/chore <title>
/chore <title> - <description>
```

## Examples

```
/chore Update dependencies
/chore Clean up CI pipeline - Remove deprecated jobs and consolidate test stages
/chore Add missing type hints to utils module
/chore Rotate API keys
```

## Action

Call `gobby-tasks.create_task` with:
- `title`: The chore title from user input
- `task_type`: "chore"
- `priority`: 3 (low - maintenance tasks are important but rarely urgent)

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
        "priority": 3,
        "session_id": "<session_id>"  # Required - from session context
    }
)
```

After creating, confirm with the task reference (e.g., "Created chore #128: Update dependencies").
