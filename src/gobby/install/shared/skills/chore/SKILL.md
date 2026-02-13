---
name: chore
description: "Quickly create a chore/maintenance task. Usage: /gobby:chore <title> [description]"
category: core
metadata:
  gobby:
    audience: all
    format_overrides:
      autonomous: full
---

# /gobby:chore - Create Chore Task

Create a maintenance or housekeeping task with the provided title and optional description. For tasks that keep the codebase healthy but aren't features or bugs.

## Usage

```
/gobby:chore <title>
/gobby:chore <title> - <description>
```

## Examples

```
/gobby:chore Update dependencies
/gobby:chore Clean up CI pipeline - Remove deprecated jobs and consolidate test stages
/gobby:chore Add missing type hints to utils module
/gobby:chore Rotate API keys
```

## Tool Schema Reminder

**First time calling a tool this session?** Use `get_tool_schema(server_name, tool_name)` before `call_tool` to get correct parameters. Schemas are cached per session—no need to refetch.

## Action

Create a chore task by invoking `call_tool()` with the following parameters:

- `title`: The chore title from user input
- `task_type`: "chore"
- `priority`: 3 (low - maintenance tasks are important but rarely urgent)

Parse the user input:
- Split on the **last** occurrence of a delimiter to preserve titles containing dashes
- Use right-split (rsplit with maxsplit=1) on ` - ` or switch to ` -- ` as delimiter
- If a delimiter is found: title = left part, description = right part
- If no delimiter is found: title = entire input, description = null

```python
call_tool(
    server_name="gobby-tasks",
    tool_name="create_task",
    arguments={
        "title": "<parsed title>",
        "description": "<parsed description or null>",  # Must be null (None in Python), not omitted or empty string
        "task_type": "chore",
        "priority": 3,
        "session_id": "<session_id>"  # Required - from session context
    }
)
```

**Note on `description`**: When no description is provided, explicitly set the key to `null` (or `None` in Python). Do not omit the key or use an empty string.

```python
# Correct - explicit null
{"description": None}  # Python
{"description": null}  # JSON

# Incorrect - do not use
{}                     # Omitting the key
{"description": ""}    # Empty string
```

After creating, confirm with the task reference (e.g., "Created chore #128: Update dependencies").
