---
name: epic
description: Quickly create an epic (parent task for large features). Usage: /epic <title> [description]
---

# /epic - Create Epic Task

Create an epic task - a parent container for a large feature or initiative that will be broken down into subtasks.

## Usage

```
/epic <title>
/epic <title> - <description>
```

## Examples

```
/epic User authentication system
/epic API v2 migration - Migrate all endpoints from REST to GraphQL with backwards compatibility
/epic Performance optimization sprint
```

## Action

Call `gobby-tasks.create_task` with:
- `title`: The epic title from user input
- `task_type`: "epic"
- `priority`: 2 (medium - epics are tracked but individual subtasks drive priority)

Parse the user input:
- If input contains " - ", split into title and description
- Otherwise, use entire input as title with no description

**Important**: When no description is provided (no " - " separator), omit the `description` parameter entirely from the `create_task` call. Do not include it with an empty string or null.

```python
# With description (input: "API v2 migration - Migrate endpoints to GraphQL")
call_tool(
    server_name="gobby-tasks",
    tool_name="create_task",
    arguments={
        "title": "API v2 migration",
        "description": "Migrate endpoints to GraphQL",
        "task_type": "epic",
        "priority": 2,
        "session_id": "<session_id>"  # Required - from session context
    }
)

# Without description (input: "User authentication system")
call_tool(
    server_name="gobby-tasks",
    tool_name="create_task",
    arguments={
        "title": "User authentication system",
        "task_type": "epic",
        "priority": 2,
        "session_id": "<session_id>"  # Required - from session context
    }
)
```

After creating, confirm with the task reference and suggest next steps:
- "Created epic #127: User authentication system"
- "Use `expand_task` or `expand_from_spec` to break this down into subtasks."
