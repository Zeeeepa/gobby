# Agent Management Guide

Gobby enables spawning subagents to work on tasks in parallel, with full session tracking and isolation options.

## Quick Start

```bash
# Spawn an agent
gobby agents spawn "Implement the login feature" --session SESSION_ID --task #123

# List running agents
gobby agents list --status running

# Check agent status
gobby agents status RUN_ID

# View agent result
gobby agents show RUN_ID
```

```python
# MCP: Spawn an agent
call_tool(server_name="gobby-agents", tool_name="spawn_agent", arguments={
    "prompt": "Implement the login feature",
    "task_id": "#123",
    "session_id": "<parent_session_id>",
    "isolation": "worktree"
})

# Check if can spawn
call_tool(server_name="gobby-agents", tool_name="can_spawn_agent", arguments={
    "session_id": "<parent_session_id>"
})
```

## Concepts

### Agent Lifecycle

```text
spawned → running → completed/failed/cancelled
              ↓
           stopped → killed
```

- **spawned**: Agent process started
- **running**: Agent actively working
- **completed**: Agent finished successfully
- **failed**: Agent encountered error
- **cancelled**: Agent stopped by user
- **killed**: Agent process terminated

### Detailed Worker Lifecycle

When an agent is spawned with a workflow (e.g., `work-task-gemini`), it follows these stages:

```text
┌─────────────────────────────────────────────────────────────────┐
│                    AGENT WORKER LIFECYCLE                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. SPAWN          2. CLAIM           3. WORK                   │
│  ┌────────┐       ┌────────┐        ┌────────┐                  │
│  │ Parent │──────▶│ Claim  │───────▶│ Do the │                  │
│  │ spawns │       │ task   │        │ work   │                  │
│  │ agent  │       │        │        │        │                  │
│  └────────┘       └────────┘        └────────┘                  │
│                                          │                      │
│                                          ▼                      │
│  6. TERMINATE     5. SHUTDOWN      4. REPORT                    │
│  ┌────────┐       ┌────────┐        ┌────────┐                  │
│  │ Exit   │◀──────│ Update │◀───────│ Notify │                  │
│  │ process│       │ session│        │ parent │                  │
│  │        │       │ status │        │        │                  │
│  └────────┘       └────────┘        └────────┘                  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

#### Stage Details

| Stage | Actions | Failures Handled |
|-------|---------|------------------|
| **1. Spawn** | Parent calls `spawn_agent`, terminal opens, session created | Parent retries or reports error |
| **2. Claim** | Agent calls `update_task(status="in_progress")` | Agent retries or exits |
| **3. Work** | Agent reads task, makes changes, commits code | Normal error handling |
| **4. Report** | Agent calls `send_to_parent` with results | See "Fallback Reporting" below |
| **5. Shutdown** | Agent calls `update_session(status="completed")` | Session expires automatically |
| **6. Terminate** | Agent runs shutdown script or exits naturally | Process cleaned up by OS |

### Shutdown Mechanisms

Agents can terminate in several ways:

#### 1. Clean Shutdown (Preferred)

The agent completes its workflow and shuts down cleanly:

```python
# 1. Close the task with commit reference
call_tool("gobby-tasks", "close_task", {
    "task_id": "#123",
    "commit_sha": "abc123",
    "changes_summary": "Implemented feature X"
})

# 2. Report to parent (may fail if parent gone - that's OK)
call_tool("gobby-agents", "send_to_parent", {
    "session_id": "<your_session_id>",
    "content": "Task #123 completed. Implemented feature X."
})

# 3. Mark session completed
call_tool("gobby-sessions", "update_session", {
    "session_id": "<your_session_id>",
    "status": "completed"
})

# 4. Exit the terminal (optional - runs shutdown script)
# bash: ~/.gobby/scripts/agent_shutdown.sh
```

#### 2. Natural Exit

If the agent simply stops (e.g., user closes terminal, process ends):
- Session status changes to `expired` via heartbeat timeout
- Parent sees agent as completed/failed when polling
- No explicit cleanup needed - Gobby handles this automatically

#### 3. Forced Termination

Parent or user can forcefully terminate an agent:

```python
# Stop the agent (marks as cancelled, doesn't kill process)
call_tool("gobby-agents", "stop_agent", {"run_id": "<run_id>"})

# Kill the agent process
call_tool("gobby-agents", "kill_agent", {"run_id": "<run_id>"})
```

### Fallback Reporting

When `send_to_parent` fails (parent session closed, network error):

1. **It's OK to continue** - The parent will discover completion via polling
2. **Close your task anyway** - Task closure is the source of truth
3. **Update session status** - Allows cleanup to proceed

```python
# send_to_parent failed? That's fine.
# Just close task and update session:
try:
    call_tool("gobby-agents", "send_to_parent", {...})
except:
    pass  # Parent will poll for results

call_tool("gobby-tasks", "close_task", {...})  # Always close task
call_tool("gobby-sessions", "update_session", {...})  # Always update session
```

### Self-Termination

Agents not registered in the in-memory registry can still terminate cleanly:

| Scenario | What Happens | Agent Action |
|----------|--------------|--------------|
| `kill_agent` not available | Agent not in registry | Just exit - process terminates |
| `send_to_parent` fails | Parent session closed | Continue with shutdown |
| Session not found | Database issue | Exit - session expires automatically |
| Workflow error | Unexpected state | Close task if possible, then exit |

**Key insight**: Agents don't need explicit termination tools. Simply exiting the process is sufficient - Gobby's session heartbeat and task system handle the rest.

### Isolation Modes

Agents can run in different isolation modes:

| Mode | Description | Use Case |
|------|-------------|----------|
| `current` | Work in current directory | Quick tasks, no isolation needed |
| `worktree` | Work in git worktree | Parallel development, branch isolation |
| `clone` | Work in full repo clone | Complete isolation, separate remote |

### Parent-Child Relationships

```text
Parent Session
├── spawn_agent("task A") → Child Session A
├── spawn_agent("task B") → Child Session B
└── spawn_agent("task C") → Child Session C
```

- Parent tracks all spawned agents
- Children can send messages to parent
- Parent can broadcast to all children

### Terminal Spawning

Agents can spawn in various terminals:

| Terminal | Support |
|----------|---------|
| ghostty | Full support |
| iTerm2 | Full support |
| kitty | Full support |
| WezTerm | Full support |
| VS Code | Integrated terminal |

## CLI Commands

### `gobby agents spawn`

Spawn a new agent with the given prompt.

```bash
gobby agents spawn "PROMPT" --session SESSION_ID [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--session` | Parent session ID (required) |
| `--workflow` | Workflow to activate |
| `--task` | Task ID to link |
| `--isolation` | Isolation mode: current, worktree, clone |

### `gobby agents list`

List agent runs.

```bash
gobby agents list [--session SESSION_ID] [--status STATUS]
```

| Option | Description |
|--------|-------------|
| `--session` | Filter by parent session |
| `--status` | Filter: running, completed, failed, cancelled |

### `gobby agents show`

Show details for an agent run.

```bash
gobby agents show RUN_ID
```

### `gobby agents status`

Check status of an agent run.

```bash
gobby agents status RUN_ID
```

### `gobby agents stop`

Stop a running agent (marks as cancelled, does not kill process).

```bash
gobby agents stop RUN_ID
```

### `gobby agents kill`

Kill a running agent process.

```bash
gobby agents kill RUN_ID
```

### `gobby agents stats`

Show agent run statistics.

```bash
gobby agents stats
```

### `gobby agents cleanup`

Clean up stale agent runs.

```bash
gobby agents cleanup
```

## MCP Tools

### spawn_agent

Spawn a subagent to execute a task.

```python
call_tool(server_name="gobby-agents", tool_name="spawn_agent", arguments={
    "prompt": "Implement the login feature",
    "task_id": "#123",
    "session_id": "<parent_session_id>",
    "isolation": "worktree",  # or "current", "clone"
    "workflow": "tdd-workflow"  # optional
})
```

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `prompt` | string | Yes | Task description for the agent |
| `session_id` | string | Yes | Parent session ID |
| `task_id` | string | No | Task to link |
| `isolation` | string | No | Isolation mode (default: "current") |
| `workflow` | string | No | Workflow to activate |

### get_agent_result

Get the result of a completed agent run.

```python
call_tool(server_name="gobby-agents", tool_name="get_agent_result", arguments={
    "run_id": "<agent_run_id>"
})
```

### list_agents

List agent runs for a session.

```python
call_tool(server_name="gobby-agents", tool_name="list_agents", arguments={
    "session_id": "<parent_session_id>",
    "status": "completed"  # optional filter
})
```

### stop_agent

Stop a running agent (marks as cancelled in DB, does not kill process).

```python
call_tool(server_name="gobby-agents", tool_name="stop_agent", arguments={
    "run_id": "<agent_run_id>"
})
```

### kill_agent

Kill a running agent process.

```python
call_tool(server_name="gobby-agents", tool_name="kill_agent", arguments={
    "run_id": "<agent_run_id>",
    "stop": True  # also end its workflow
})
```

### can_spawn_agent

Check if an agent can be spawned from the current session.

```python
call_tool(server_name="gobby-agents", tool_name="can_spawn_agent", arguments={
    "session_id": "<parent_session_id>"
})
```

### list_running_agents

List all currently running agents (in-memory process state).

```python
call_tool(server_name="gobby-agents", tool_name="list_running_agents", arguments={})
```

### get_running_agent

Get in-memory process state for a running agent.

```python
call_tool(server_name="gobby-agents", tool_name="get_running_agent", arguments={
    "run_id": "<agent_run_id>"
})
```

### running_agent_stats

Get statistics about running agents.

```python
call_tool(server_name="gobby-agents", tool_name="running_agent_stats", arguments={})
```

### unregister_agent

Remove an agent from the in-memory running registry (internal use).

```python
call_tool(server_name="gobby-agents", tool_name="unregister_agent", arguments={
    "run_id": "<agent_run_id>"
})
```

## Messaging Between Sessions

### send_to_parent

Send a message from a child session to its parent.

```python
call_tool(server_name="gobby-agents", tool_name="send_to_parent", arguments={
    "session_id": "<child_session_id>",
    "message": "Task completed successfully",
    "message_type": "status"  # or "question", "result"
})
```

### send_to_child

Send a message from a parent to a specific child session.

```python
call_tool(server_name="gobby-agents", tool_name="send_to_child", arguments={
    "parent_session_id": "<parent_session_id>",
    "child_session_id": "<child_session_id>",
    "message": "Please also update the tests"
})
```

### broadcast_to_children

Broadcast a message to all running child sessions.

```python
call_tool(server_name="gobby-agents", tool_name="broadcast_to_children", arguments={
    "parent_session_id": "<parent_session_id>",
    "message": "Context update: API endpoint changed"
})
```

### poll_messages

Poll for messages sent to this session.

```python
call_tool(server_name="gobby-agents", tool_name="poll_messages", arguments={
    "session_id": "<your_session_id>",
    "unread_only": True
})
```

### mark_message_read

Mark a message as read.

```python
call_tool(server_name="gobby-agents", tool_name="mark_message_read", arguments={
    "message_id": "<message_id>"
})
```

## Workflows with Agents

Agents can be spawned with specific workflows:

```python
# Spawn agent with TDD workflow
call_tool(server_name="gobby-agents", tool_name="spawn_agent", arguments={
    "prompt": "Implement user authentication",
    "task_id": "#123",
    "session_id": "<parent_session_id>",
    "workflow": "tdd-workflow",
    "isolation": "worktree"
})
```

The agent will follow the workflow steps (e.g., write tests first, then implement, then refactor).

## Leaf Task Handling

When spawning an agent with a leaf task (no children), the meeseeks-box workflow handles it automatically. The `find_work` step first calls `suggest_next_task()` — if the task is a leaf with no subtasks, this returns nothing. The workflow then falls back to checking `session_task` directly: if it's still open, it assigns the task directly to a worker instead of entering `wait_for_workers`.

This means you can spawn a meeseeks agent with either:
- **A parent task** — workers are spawned for each ready subtask
- **A leaf task** — the task itself is assigned directly to a worker

```python
# Parent task with subtasks
call_tool(server_name="gobby-agents", tool_name="spawn_agent", arguments={
    "agent": "meeseeks-gemini",
    "task_id": "#100",  # Parent with children #101, #102
    "parent_session_id": "<session_id>"
})

# Leaf task (no children)
call_tool(server_name="gobby-agents", tool_name="spawn_agent", arguments={
    "agent": "meeseeks-gemini",
    "task_id": "#6908",  # Standalone task
    "parent_session_id": "<session_id>"
})
```

## Orchestration Pattern

For automated task orchestration, use the conductor or orchestration tools:

```python
# Orchestrate ready subtasks under a parent
call_tool(server_name="gobby-orchestration", tool_name="orchestrate_ready_tasks", arguments={
    "parent_task_id": "#100",
    "session_id": "<orchestrator_session_id>"
})

# Poll agent status
call_tool(server_name="gobby-orchestration", tool_name="poll_agent_status", arguments={
    "parent_task_id": "#100"
})

# Process completed agents
call_tool(server_name="gobby-orchestration", tool_name="process_completed_agents", arguments={
    "parent_task_id": "#100"
})
```

See [mcp-tools.md](mcp-tools.md#orchestration) for full orchestration tool reference.

## Best Practices

### Do

- Use worktree isolation for parallel work
- Link agents to tasks for traceability
- Use workflows to enforce quality
- Monitor agent status regularly
- Clean up stale agents

### Don't

- Spawn too many agents simultaneously
- Use `current` isolation for conflicting changes
- Ignore agent failures
- Kill agents without stopping first

## Troubleshooting

### Agent won't spawn

1. Check if can_spawn_agent returns true
2. Verify parent session is active
3. Check terminal availability
4. Review daemon logs

### Agent stuck in running state

1. Check if process is still alive
2. Use `kill_agent` to terminate
3. Clean up with `gobby agents cleanup`

### Messages not received

1. Verify session IDs are correct
2. Check if message was marked read
3. Use `poll_messages` with `unread_only=False`

## See Also

- [sessions.md](sessions.md) - Session management
- [worktrees.md](worktrees.md) - Git worktrees
- [workflows.md](workflows.md) - Workflow engine
- [mcp-tools.md](mcp-tools.md) - Full MCP tool reference
