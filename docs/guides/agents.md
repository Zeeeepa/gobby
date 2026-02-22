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

### Agent Definitions

Agent definitions are stored in `workflow_definitions` with `workflow_type='agent'`. Each definition has 12 fields:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | string | -- | Unique agent identifier |
| `description` | string | -- | Human-readable description |
| `instructions` | string | -- | System prompt / instructions for the agent |
| `provider` | string | `"claude"` | LLM provider (claude, gemini, codex) |
| `model` | string | -- | Model override (provider default if not set) |
| `mode` | string | `"headless"` | Execution mode: terminal, embedded, headless |
| `isolation` | string | -- | Isolation: current, worktree, clone |
| `base_branch` | string | `"main"` | Branch to create worktree/clone from |
| `timeout` | float | `120.0` | Max execution time in seconds |
| `max_turns` | int | `10` | Max agent turns |
| `rules` | list | `[]` | Rule groups to activate for this agent |
| `enabled` | bool | `true` | Whether the definition is available |

Behavior is defined by **rules**, not embedded workflows. The `rules` field lists rule groups that are activated when this agent runs.

### Agent-Scoped Rules

Rules can be scoped to specific agent types using the `agent_scope` field:

```yaml
rules:
  no-push-for-workers:
    description: "Block git push for worker agents"
    event: before_tool
    agent_scope: [worker, developer]
    effect:
      type: block
      tools: [Bash]
      command_pattern: "git\\s+push"
      reason: "Worker agents cannot push. Let the parent handle it."
```

When `agent_scope` is set, the rule only fires for sessions whose `_agent_type` variable matches one of the listed types. Rules without `agent_scope` apply to all sessions.

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

## Inter-Agent Messaging

Gobby provides P2P messaging and command coordination between sessions. All messaging tools live on `gobby-agents`.

### send_message

Send a P2P message between sessions. Validates both sessions are in the same project. Auto-writes to `agent_runs.result` when sending to parent.

```python
call_tool(server_name="gobby-agents", tool_name="send_message", arguments={
    "from_session": "<your_session_id>",
    "to_session": "<target_session_id>",
    "content": "Task completed. All tests pass.",
    "priority": "normal"  # or "high"
})
```

### send_command

Send a command from an ancestor session to a descendant. Validates ancestry and rejects if the target already has an active command.

```python
call_tool(server_name="gobby-agents", tool_name="send_command", arguments={
    "from_session": "<parent_session_id>",
    "to_session": "<child_session_id>",
    "command_text": "Run the test suite and report results",
    "allowed_tools": ["Bash", "Read", "Grep"],
    "exit_condition": "task_complete()"
})
```

### complete_command

Complete a command: mark it done, clear session variables, and send the result back to the commanding session.

```python
call_tool(server_name="gobby-agents", tool_name="complete_command", arguments={
    "session_id": "<your_session_id>",
    "command_id": "<command_id>",
    "result": "All 47 tests pass. Coverage at 92%."
})
```

### deliver_pending_messages

Fetch undelivered messages for a session and mark them as delivered. Use this to inject pending messages as context.

```python
call_tool(server_name="gobby-agents", tool_name="deliver_pending_messages", arguments={
    "session_id": "<your_session_id>"
})
```

### activate_command

Activate a pending command: mark it running and set session variables (`command_id`, `command_text`, `allowed_tools`, `exit_condition`).

```python
call_tool(server_name="gobby-agents", tool_name="activate_command", arguments={
    "session_id": "<your_session_id>",
    "command_id": "<command_id>"
})
```

### Command Lifecycle

```text
Parent sends command (send_command)
  → Child receives (deliver_pending_messages)
  → Child activates (activate_command) → session variables set
  → Child works within constraints (allowed_tools, exit_condition)
  → Child completes (complete_command) → variables cleared, result sent to parent
```

## Rules with Agents

Agent behavior is enforced by rules, not embedded workflows. When spawning an agent with a definition that includes rule groups, those rules are activated for the agent's session.

```python
# Spawn agent using a definition with rules
call_tool(server_name="gobby-agents", tool_name="spawn_agent", arguments={
    "agent": "developer-claude",
    "task_id": "#123",
    "parent_session_id": "<parent_session_id>",
    "isolation": "worktree"
})
```

The agent definition's `rules` field activates rule groups (e.g., `worker-safety`, `task-enforcement`). These rules enforce behavior like requiring task claims before edits, blocking git push, and gating stop attempts.

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

1. Verify both sessions are in the same project
2. Use `deliver_pending_messages` to check for undelivered messages
3. Verify session IDs resolve correctly (accepts `#N`, UUID, or prefix)

## See Also

- [sessions.md](sessions.md) - Session management
- [worktrees.md](worktrees.md) - Git worktrees
- [workflows.md](workflows.md) - Workflow engine
- [mcp-tools.md](mcp-tools.md) - Full MCP tool reference
