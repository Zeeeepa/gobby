---
name: claiming-tasks
description: Quick reference when blocked by "no active task" error. Shows how to create or claim a task before using Edit, Write, or NotebookEdit tools.
category: core
alwaysApply: true
injectionFormat: full
---

# Claiming Tasks - Resolving Edit Blocks

This skill helps when you're blocked from using Edit, Write, or NotebookEdit tools due to missing an active task.

## Tool Schema Reminder

**First time calling a tool this session?** Use `get_tool_schema(server_name, tool_name)` before `call_tool` to get correct parameters. Schemas are cached per session—no need to refetch.

## You've Been Blocked

The workflow system requires an active task before using Edit, Write, or NotebookEdit. If you see:

```text
Blocked: No active task. Create or claim a task before using Edit, Write, or NotebookEdit tools.
```

Follow the steps below to resolve.

## Quick Fix

### Option 1: Create a New Task

```python
# Create the task (automatically claims it - sets status to in_progress)
result = call_tool("gobby-tasks", "create_task", {
    "title": "Your task title",
    "description": "What you're doing",
    "task_type": "task",  # or bug, feature, epic
    "session_id": "<your_session_id>"  # Required - from SessionStart context
})

# Now you can edit files - task is already in_progress and assigned to your session
```

### Option 2: Claim an Existing Task

```python
# Get suggested next task
result = call_tool("gobby-tasks", "suggest_next_task", {
    "session_id": "<your_session_id>"
})

# Extract task ID from suggestion (ref preferred, id as fallback)
suggestion = result.get("suggestion", {})
task_id = suggestion.get("ref") or suggestion.get("id")

# Claim it (sets status to in_progress and assignee to your session)
call_tool("gobby-tasks", "claim_task", {
    "task_id": task_id,
    "session_id": "<your_session_id>"
})
```

## Finding Your Session ID

Your `session_id` is injected at session start. Look for `Gobby Session Ref:` or `Gobby Session ID:` in your system context:

```text
Gobby Session Ref: #5
Gobby Session ID: <uuid>
```

**Note**: All `session_id` parameters accept #N, N, UUID, or prefix formats.

If not present, retrieve it with `get_current_session`:

```python
call_tool("gobby-sessions", "get_current_session", {
    "external_id": "<your-cli-session-id>",
    "source": "claude"
})
```

## Why This Matters

Tasks ensure:

- All code changes are tracked
- Work can be reviewed and linked to commits
- Dependencies between tasks are respected
- Session handoff preserves context
