---
name: task-creation
description: "How to create and claim tasks via gobby-tasks MCP. Covers progressive discovery, required fields, and writing effective validation criteria."
category: core
metadata:
  gobby:
    audience: all
---

# Task Creation

Create and claim tasks via gobby-tasks MCP tools.

---

## Progressive Discovery

Before calling any tool, discover it:

```python
# 1. List servers (once per session)
list_mcp_servers()

# 2. List tools on gobby-tasks (once per server)
list_tools(server_name="gobby-tasks")

# 3. Get schema (once per tool)
get_tool_schema(server_name="gobby-tasks", tool_name="create_task")

# 4. Call the tool
call_tool("gobby-tasks", "create_task", {...})
```

## Creating a Task

```python
call_tool("gobby-tasks", "create_task", {
    "title": "Imperative description of what to do",
    "description": "Context, requirements, and acceptance criteria",
    "category": "code",  # code | config | docs | test | research | planning | manual
    "validation_criteria": "Observable criteria for 'done'",  # Required for category=code
    "session_id": "#session",
    "claim": true  # Auto-claim: sets status to in_progress
})
```

### Required Fields

| Field | When | Notes |
|-------|------|-------|
| `title` | Always | Imperative form: "Fix X", "Add Y" |
| `session_id` | Always | Your Gobby session ID |
| `category` | Always | Determines validation behavior |
| `validation_criteria` | `category=code` | Creation fails without it |

### Writing Effective Validation Criteria

Validation criteria are checked against the diff when closing. Write them so an independent reviewer can verify completion:

**Good:** "The `close_task` tests in `test_tasks_coverage.py` pass. `LocalSessionManager` is patched at the correct import path in both tests."

**Bad:** "Tests pass." / "It works." / "Bug is fixed."

Criteria should be:
- **Observable** — can be verified by reading code or running tests
- **Specific** — names files, functions, or behaviors
- **Complete** — covers all acceptance conditions, not just the happy path

## Claiming an Existing Task

```python
call_tool("gobby-tasks", "claim_task", {
    "task_id": "#N",
    "session_id": "#session"
})
```

This sets the task to `in_progress` and assigns it to your session. You must claim or create a task before editing files.
