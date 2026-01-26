---
name: ref
description: "Quickly create a refactoring task. Usage: /ref <title> [description]"
category: core
---

# /ref - Create Refactoring Task

Create a refactoring task with the provided title and optional description. For code improvements that don't change behavior.

## Usage

```
/ref <title>
/ref <title> - <description>
```

## Examples

```
/ref Extract database logic into repository class
/ref Simplify authentication middleware - Current implementation has too many nested conditionals
/ref Convert callbacks to async/await in file handlers
```

## Action

Call `gobby-tasks.create_task` with:
- `title`: The refactoring title from user input
- `task_type`: "chore"
- `labels`: ["refactor"]
- `priority`: 3 (low - important but not urgent)

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
        "labels": ["refactor"],
        "priority": 3,
        "session_id": "<session_id>"  # Required - from session context
    }
)
```

After creating, confirm with the task reference (e.g., "Created refactor #126: Extract database logic into repository class").
