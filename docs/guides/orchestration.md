# Task Orchestration

The `gobby-orchestration` MCP server provides tools for automated task orchestration — spawning agents for ready subtasks, monitoring their progress, handling review, and cleaning up worktrees.

All orchestration tools live on the **`gobby-orchestration`** server (not `gobby-tasks`). Task CRUD, dependencies, and readiness queries remain on `gobby-tasks`.

## Quick Reference

| Tool | Purpose |
| :--- | :--- |
| `orchestrate_ready_tasks` | Spawn agents in worktrees for ready subtasks |
| `get_orchestration_status` | Get subtask summary (open/in_progress/review/closed) |
| `poll_agent_status` | Check spawned agents, move completed to tracking list |
| `spawn_review_agent` | Spawn a review agent for a completed task |
| `process_completed_agents` | Route completed agents to review or cleanup |
| `approve_and_cleanup` | Approve reviewed task, merge and delete worktree |
| `cleanup_reviewed_worktrees` | Merge branches and delete worktrees for reviewed agents |
| `cleanup_stale_worktrees` | Delete worktrees with no active agent |
| `wait_for_task` | Block until a single task completes |
| `wait_for_any_task` | Block until the first of multiple tasks completes |
| `wait_for_all_tasks` | Block until all tasks complete |

## Spawning Agents

`orchestrate_ready_tasks` finds open subtasks under a parent that have no unresolved dependencies, then spawns an agent in an isolated worktree for each:

```python
call_tool(server_name="gobby-orchestration", tool_name="orchestrate_ready_tasks", arguments={
    "parent_task_id": "#100",
    "session_id": "<orchestrator_session_id>"
})
```

Each agent gets its own worktree branched from the current branch. The tool tracks spawned agents in workflow state so they can be polled later.

## Monitoring

### Orchestration status

`get_orchestration_status` returns a summary of all subtasks under a parent, grouped by status:

```python
call_tool(server_name="gobby-orchestration", tool_name="get_orchestration_status", arguments={
    "parent_task_id": "#100",
    "project_path": "/path/to/project"
})
# Returns: summary, open_tasks, in_progress_tasks, review_tasks, closed_tasks
```

### Polling agents

`poll_agent_status` checks whether spawned agents have finished and updates the tracking lists:

```python
call_tool(server_name="gobby-orchestration", tool_name="poll_agent_status", arguments={
    "parent_task_id": "#100"
})
```

## Review and Completion

### Processing completed agents

`process_completed_agents` routes finished agents — spawns review agents for validation or moves directly to cleanup:

```python
call_tool(server_name="gobby-orchestration", tool_name="process_completed_agents", arguments={
    "parent_task_id": "#100"
})
```

### Approving and merging

`approve_and_cleanup` transitions a task from `needs_review` to `closed`, merges its branch, and deletes the worktree:

```python
call_tool(server_name="gobby-orchestration", tool_name="approve_and_cleanup", arguments={
    "task_id": "#101"
})
```

## Waiting

Block until tasks reach `closed` or `needs_review` status. All wait tools accept a `timeout_seconds` parameter.

```python
# Single task
call_tool(server_name="gobby-orchestration", tool_name="wait_for_task", arguments={
    "task_id": "#101",
    "timeout_seconds": 300
})

# First of multiple tasks
call_tool(server_name="gobby-orchestration", tool_name="wait_for_any_task", arguments={
    "task_ids": ["#101", "#102", "#103"],
    "timeout_seconds": 300
})

# All tasks
call_tool(server_name="gobby-orchestration", tool_name="wait_for_all_tasks", arguments={
    "task_ids": ["#101", "#102", "#103"],
    "timeout_seconds": 600
})
```

## Cleanup

```python
# Merge branches and delete worktrees for reviewed agents
call_tool(server_name="gobby-orchestration", tool_name="cleanup_reviewed_worktrees", arguments={
    "parent_task_id": "#100"
})

# Delete stale worktrees with no active agent
call_tool(server_name="gobby-orchestration", tool_name="cleanup_stale_worktrees", arguments={
    "max_age_hours": 24
})
```

## Related

- [MCP Tools Reference](mcp-tools.md#task-orchestration-gobby-orchestration) — full tool table
- [Agents Guide](agents.md) — agent spawning and isolation modes
- [CLI Commands](cli-commands.md#conductor) — conductor CLI for persistent orchestration loops
