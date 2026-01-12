---
name: bug
description: Quickly create a bug task. Usage: /bug <title> [description]
---

# /bug - Create Bug Task

Create a bug/defect task with the provided title and optional description.

## Usage

```
/bug <title>
/bug <title> - <description>
```

## Examples

```
/bug Fix login timeout
/bug Database connection drops - Users report intermittent connection failures after 5 minutes of inactivity
```

## Action

Call `gobby-tasks.create_task` with:
- `title`: The bug title from user input
- `task_type`: "bug"
- `priority`: 1 (high - bugs are important)

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
        "task_type": "bug",
        "priority": 1
    }
)
```

After creating, confirm with the task reference (e.g., "Created bug #123: Fix login timeout").
