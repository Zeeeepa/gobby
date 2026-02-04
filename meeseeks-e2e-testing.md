# Meeseeks Agent E2E Testing

End-to-end functional test criteria for the meeseeks agent system.

## Overview

The meeseeks system consists of two complementary workflows:
- **meeseeks-box** (orchestrator): Runs in Claude Code, spawns workers, reviews code, merges
- **meeseeks:worker** (worker): Runs in Gemini CLI within isolated git worktrees

## Test Approach

**Two-level spawn pattern**: The tester activates the orchestrator, which spawns workers.

1. Tester creates a parent task (the "session task")
2. Tester calls `spawn_agent(agent="meeseeks", workflow="box", task_id="<parent_task>")`
3. meeseeks-box activates in tester's session (mode: self)
4. meeseeks-box loops until parent task tree is complete:
   - Find ready subtasks via `suggest_next_task`
   - Spawn Gemini workers via `spawn_agent(workflow="worker")`
   - Wait for task completion via `wait_for_task`
   - Review and merge changes
   - Repeat until all subtasks closed
5. Workflow exits when `task_tree_complete(session_task)` returns true

## Prerequisites

Before testing:
- [ ] Gobby daemon running (`gobby status` shows running)
- [ ] MCP servers connected: `gobby-tasks`, `gobby-agents`, `gobby-workflows`, `gobby-worktrees`
- [ ] Gemini CLI installed and authenticated
- [ ] Git repository with clean working tree
- [ ] Terminal emulator available (ghostty or configured alternative)

## Test Scenario

**Objective**: Create a simple task, spawn a meeseeks worker to complete it, review the changes, and merge.

### Phase 1: Setup

| Step | Action | Success Criteria |
|------|--------|------------------|
| 1.1 | Create a parent task (session task) | Task created with status `open`, has valid task_id |
| 1.2 | Create subtask(s) under parent | Subtasks created, linked to parent |
| 1.3 | Note current git state | `git worktree list` shows only main worktree |

### Phase 2: Activate Orchestrator

| Step | Action | Success Criteria |
|------|--------|------------------|
| 2.1 | Call `spawn_agent(agent="meeseeks", workflow="box", task_id="<parent_task>")` | Returns success, workflow activates in tester's session |
| 2.2 | meeseeks-box workflow active | Workflow state shows `find_work` step, `session_task` variable set |

### Phase 3: Orchestrator Spawns Worker

| Step | Action | Success Criteria |
|------|--------|------------------|
| 3.1 | meeseeks-box calls `suggest_next_task` | Returns ready subtask |
| 3.2 | meeseeks-box calls `spawn_agent(workflow="worker", task_id=subtask)` | Returns `run_id`, `worktree_id`, `branch_name` |
| 3.3 | Worktree created | `git worktree list` shows new worktree |
| 3.4 | Terminal opened | New terminal window/pane visible with Gemini CLI |
| 3.5 | Worker workflow auto-activated | Worker starts in `claim_task` step |

### Phase 4: Worker Lifecycle (Autonomous)

| Step | Action | Success Criteria |
|------|--------|------------------|
| 4.1 | Worker calls `claim_task` | Task status changes to `in_progress`, task `assigned_to` set |
| 4.2 | Worker transitions to `work` step | `task_claimed` variable is `true` |
| 4.3 | Worker completes implementation | Files modified/created as required by task |
| 4.4 | Worker commits changes | Git commit created with `[task_id]` in message |
| 4.5 | Worker calls `close_task` with `commit_sha` | Task status changes to `closed`, `commit_sha` recorded |
| 4.6 | Worker transitions to `report_to_parent` | `task_closed` variable is `true` |
| 4.7 | Worker calls `send_to_parent` | Message delivered to orchestrator session |
| 4.8 | Worker calls `close_terminal` | Terminal session terminates cleanly |
| 4.9 | Worker workflow reaches `complete` | Workflow exit condition met |

### Phase 5: Orchestrator Wait & Review

| Step | Action | Success Criteria |
|------|--------|------------------|
| 5.1 | meeseeks-box calls `wait_for_task` | Blocks until subtask closed or timeout |
| 5.2 | `wait_for_task` returns | `completed: true`, `timed_out: false` |
| 5.3 | meeseeks-box transitions to `code_review` | Can access diff via `git diff dev...<branch>` |
| 5.4 | Review code changes | Changes meet acceptance criteria |
| 5.5 | Set `review_approved` to true | Workflow variable updated |

### Phase 6: Orchestrator Merge & Cleanup

| Step | Action | Success Criteria |
|------|--------|------------------|
| 6.1 | meeseeks-box merges branch | `git merge --squash <branch>` succeeds |
| 6.2 | meeseeks-box deletes worktree | `git worktree remove <path>` succeeds |
| 6.3 | meeseeks-box deletes feature branch | `git branch -D <branch>` succeeds |
| 6.4 | Workflow transitions to `find_work` | Loop continues for more subtasks |

### Phase 7: Loop Completion

| Step | Action | Success Criteria |
|------|--------|------------------|
| 7.1 | meeseeks-box calls `suggest_next_task` | Returns null (no more ready tasks) |
| 7.2 | `task_tree_complete(session_task)` returns true | All subtasks closed |
| 7.3 | Workflow transitions to `complete` | Exit condition met |
| 7.4 | meeseeks-box workflow exits | Tester's session returns to normal |

### Phase 8: Final Validation

| Step | Action | Success Criteria |
|------|--------|------------------|
| 8.1 | Verify no orphaned worktrees | `git worktree list` shows only main worktree |
| 8.2 | Verify all tasks closed | Parent and subtasks all `closed` |
| 8.3 | Verify commits linked | Each subtask has `commit_sha` |
| 8.4 | Verify terminal cleaned up | No lingering Gemini CLI processes |

## MCP Tool Verification

Each MCP server must respond correctly:

### gobby-tasks
| Tool | Test |
|------|------|
| `create_task` | Creates task with all fields |
| `claim_task` | Sets status, assigned_to, session_id |
| `close_task` | Records commit_sha, updates status |
| `suggest_next_task` | Returns ready task or null |
| `wait_for_task` | Blocks until closed or timeout |
| `get_task` | Returns full task details |

### gobby-agents
| Tool | Test |
|------|------|
| `spawn_agent` | Creates worktree, starts terminal, returns IDs |
| `send_to_parent` | Delivers message to parent session |
| `poll_messages` | Returns messages from children |

### gobby-workflows
| Tool | Test |
|------|------|
| `close_terminal` | Terminates session cleanly |
| `end_workflow` | Allows early exit if needed |

Note: `activate_workflow` is called internally by `spawn_agent` when a workflow is specified.

### gobby-worktrees
| Tool | Test |
|------|------|
| `create_worktree` | Creates isolated worktree with branch |
| `delete_worktree` | Removes worktree and optionally branch |
| `list_worktrees` | Shows all active worktrees |

## Error Scenarios

### Worker Timeout
| Step | Expected Behavior |
|------|-------------------|
| Worker exceeds timeout | `wait_for_task` returns `timed_out: true` |
| Tester observes | Task status remains `in_progress` |
| Recovery | Tester can spawn new worker or manually complete |

### Worker Crash
| Step | Expected Behavior |
|------|-------------------|
| Terminal closes unexpectedly | Task remains `in_progress` |
| Tester timeout | `wait_for_task` times out |
| Recovery | Task can be reclaimed by new worker |

### Worker Fails to Commit
| Step | Expected Behavior |
|------|-------------------|
| Worker makes changes but doesn't commit | Task closed without `commit_sha` |
| Tester observes | Changes exist in worktree but not committed |
| Recovery | Tester can manually commit or discard worktree |

### No Parent Found
| Step | Expected Behavior |
|------|-------------------|
| `send_to_parent` fails | `parent_notified` still set to true (error handler) |
| Worker continues | Proceeds to shutdown normally |

## Validation Commands

```bash
# Check daemon status
gobby status

# List active sessions
gobby sessions list

# Check task state
gobby tasks get <task_id>

# List worktrees
git worktree list

# Check workflow state (via MCP)
# call_tool("gobby-workflows", "get_workflow_state", {"session_id": "..."})
```

## Success Definition

The E2E test passes when:

1. **Task lifecycle complete**: Task goes from `open` → `in_progress` → `closed`
2. **Worker lifecycle complete**: Worker transitions through workflow steps to `complete`
3. **Spawn successful**: `spawn_agent` returns valid run_id, worktree_id, branch_name
4. **Git state correct**: Commit created with task reference, changes mergeable
5. **No orphaned resources**: No lingering worktrees, terminals, or in-progress tasks
6. **Messages delivered**: Tester received completion message from worker via `poll_messages`
7. **Terminal cleanup**: Worker called `close_terminal` and process exited

## Test Task Suggestions

Simple tasks suitable for E2E testing:

1. **Add a comment**: Add a docstring to a specific function
2. **Create a file**: Create a new empty module with basic structure
3. **Fix a typo**: Correct a deliberate typo in documentation
4. **Update a constant**: Change a version number or configuration value

These tasks have clear, verifiable outcomes and minimal complexity.
