# Task Management Guide

Gobby includes a native task tracking system designed for AI-assisted development. Tasks are persistent across sessions, support dependencies, and sync with git.

## Core Concepts

- **Task**: A unit of work with title, description, priority, and status
- **Epic**: A parent task that groups subtasks
- **Dependencies**: Tasks can block other tasks (A must complete before B starts)
- **Ready Work**: Tasks with no unresolved blocking dependencies
- **Sync**: Tasks export to `.gobby/tasks.jsonl` for git versioning

## Quick Start

### MCP Tools (for AI Agents)

```python
# Check what's ready to work on
call_tool(server_name="gobby-tasks", tool_name="list_ready_tasks", arguments={})

# Create a task
call_tool(server_name="gobby-tasks", tool_name="create_task", arguments={
    "title": "Fix authentication bug",
    "priority": 1,
    "task_type": "bug"
})

# Claim and work on it
call_tool(server_name="gobby-tasks", tool_name="update_task", arguments={
    "task_id": "gt-abc123",
    "status": "in_progress"
})

# Complete it
call_tool(server_name="gobby-tasks", tool_name="close_task", arguments={
    "task_id": "gt-abc123",
    "reason": "completed"
})
```

### CLI Commands

```bash
# List ready work
gobby tasks list --ready

# Create a task
gobby tasks create "Fix login bug" -p 1 -t bug

# Update status
gobby tasks update gt-abc123 --status in_progress

# Close task
gobby tasks close gt-abc123 --reason "Fixed"

# Sync with git
gobby tasks sync
```

## Task Lifecycle

```
open → in_progress → closed
                  ↘ failed (validation failures)
```

- **open**: Ready or blocked, not started
- **in_progress**: Currently being worked on
- **closed**: Completed with reason
- **failed**: Exceeded validation retry limit

## Task Types

| Type | Use For |
|------|---------|
| `task` | General work items (default) |
| `bug` | Something broken |
| `feature` | New functionality |
| `epic` | Large feature with subtasks |
| `chore` | Maintenance, dependencies, tooling |

## Priority Levels

| Priority | Meaning |
|----------|---------|
| 1 | High (critical bugs, major features) |
| 2 | Medium (default) |
| 3 | Low (polish, optimization) |

## Dependencies

Tasks can block other tasks. A blocked task won't appear in `list_ready_tasks` until its blockers are closed.

```python
# Task A blocks Task B (B depends on A completing first)
call_tool(server_name="gobby-tasks", tool_name="add_dependency", arguments={
    "task_id": "gt-taskB",      # The dependent task
    "depends_on": "gt-taskA",   # The blocker
    "dep_type": "blocks"
})

# Create task with dependencies in one call
call_tool(server_name="gobby-tasks", tool_name="create_task", arguments={
    "title": "Implement feature",
    "blocks": ["gt-parent-epic"]  # This task blocks the parent
})
```

### Dependency Types

| Type | Behavior |
|------|----------|
| `blocks` | Hard dependency - prevents task from being "ready" |
| `related` | Soft link - informational only |
| `discovered-from` | Task found while working on another |

## LLM-Powered Expansion

Break down complex tasks into subtasks using AI:

```python
# Expand a task into subtasks
call_tool(server_name="gobby-tasks", tool_name="expand_task", arguments={
    "task_id": "gt-abc123",
    "enable_code_context": True
})

# Get complexity analysis
call_tool(server_name="gobby-tasks", tool_name="analyze_complexity", arguments={
    "task_id": "gt-abc123"
})

# Get AI suggestion for next task
call_tool(server_name="gobby-tasks", tool_name="suggest_next_task", arguments={})

# Create tasks from a PRD or spec
call_tool(server_name="gobby-tasks", tool_name="expand_from_spec", arguments={
    "spec_content": "# Feature: User Authentication\n..."
})
```

## Task Validation

Validate task completion with AI assistance:

```python
# Validate a task is complete
call_tool(server_name="gobby-tasks", tool_name="validate_task", arguments={
    "task_id": "gt-abc123",
    "changes_summary": "Added login form with validation"
})

# Check validation status
call_tool(server_name="gobby-tasks", tool_name="get_validation_status", arguments={
    "task_id": "gt-abc123"
})

# Reset validation count for retry
call_tool(server_name="gobby-tasks", tool_name="reset_validation_count", arguments={
    "task_id": "gt-abc123"
})
```

## Git Sync

Tasks automatically sync to `.gobby/tasks.jsonl`:

- **Export**: After task changes (5s debounce)
- **Import**: On daemon start
- **Manual**: `gobby tasks sync`

### Stealth Mode

Keep tasks out of git (store in `~/.gobby/` instead):

```bash
gobby tasks config --stealth on
```

## Complete MCP Tool Reference

### Task CRUD

| Tool | Description |
|------|-------------|
| `create_task` | Create a new task |
| `get_task` | Get task details with dependencies |
| `update_task` | Update task fields |
| `close_task` | Close a task with reason |
| `delete_task` | Delete a task (cascade optional) |
| `list_tasks` | List tasks with filters |
| `add_label` | Add a label to a task |
| `remove_label` | Remove a label from a task |

### Dependencies

| Tool | Description |
|------|-------------|
| `add_dependency` | Create dependency between tasks |
| `remove_dependency` | Remove a dependency |
| `get_dependency_tree` | Get blockers/blocking tree |
| `check_dependency_cycles` | Detect circular dependencies |

### Ready Work

| Tool | Description |
|------|-------------|
| `list_ready_tasks` | Tasks with no unresolved blockers |
| `list_blocked_tasks` | Tasks waiting on others |

### Session Integration

| Tool | Description |
|------|-------------|
| `link_task_to_session` | Associate task with session |
| `get_session_tasks` | Tasks linked to a session |
| `get_task_sessions` | Sessions that touched a task |

### Git Sync

| Tool | Description |
|------|-------------|
| `sync_tasks` | Trigger import/export |
| `get_sync_status` | Get sync status |

### LLM Expansion

| Tool | Description |
|------|-------------|
| `expand_task` | Break task into subtasks with AI |
| `analyze_complexity` | Get complexity score |
| `expand_all` | Expand all unexpanded tasks |
| `expand_from_spec` | Create tasks from PRD/spec |
| `suggest_next_task` | AI suggests next task to work on |

### Validation

| Tool | Description |
|------|-------------|
| `validate_task` | Validate task completion |
| `get_validation_status` | Get validation details |
| `reset_validation_count` | Reset failure count for retry |

## CLI Command Reference

```bash
# Task management
gobby tasks list [--status S] [--priority N] [--ready] [--json]
gobby tasks show TASK_ID
gobby tasks create "Title" [-d DESC] [-p PRIORITY] [-t TYPE]
gobby tasks update TASK_ID [--status S] [--priority P]
gobby tasks close TASK_ID --reason "Done"
gobby tasks delete TASK_ID [--cascade]

# Dependencies
gobby tasks dep add TASK BLOCKER
gobby tasks dep remove TASK BLOCKER
gobby tasks dep tree TASK
gobby tasks dep cycles

# Labels
gobby tasks label add TASK LABEL
gobby tasks label remove TASK LABEL

# Ready work
gobby tasks ready [--limit N]
gobby tasks blocked

# Sync
gobby tasks sync [--import] [--export]

# Expansion
gobby tasks expand TASK_ID [--strategy S]
gobby tasks complexity TASK_ID
gobby tasks suggest

# Stats
gobby tasks stats
```

## Data Storage

- **Database**: `~/.gobby/gobby.db` (SQLite)
- **Git sync**: `.gobby/tasks.jsonl` (or `~/.gobby/tasks/{project}.jsonl` in stealth mode)
- **Metadata**: `.gobby/tasks_meta.json`

## Task ID Format

- Generated: `gt-{6 hex chars}` (e.g., `gt-a1b2c3`)
- Hierarchical: `gt-a1b2c3.1`, `gt-a1b2c3.2` (subtasks)
- Prefix matching supported: `gt-a1b` matches `gt-a1b2c3`
