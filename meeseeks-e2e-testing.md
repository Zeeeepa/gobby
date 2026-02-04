# Meeseeks Agent E2E Testing

End-to-end functional test criteria for the meeseeks agent system.

## Overview

The meeseeks system consists of two complementary workflows:
- **meeseeks-box** (orchestrator): Runs in Claude Code, spawns workers, reviews code, merges
- **meeseeks:worker** (worker): Runs in Gemini CLI within isolated git worktrees

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
| 1.1 | Create a test task | Task created with status `open`, has valid task_id |
| 1.2 | Activate meeseeks-box workflow | Workflow state shows `find_work` step, session_task variable set |

### Phase 2: Orchestrator - Find Work

| Step | Action | Success Criteria |
|------|--------|------------------|
| 2.1 | Call `suggest_next_task` | Returns task_id matching created task |
| 2.2 | Workflow transitions to `spawn_worker` | `current_task_id` variable populated |

### Phase 3: Worker Spawn

| Step | Action | Success Criteria |
|------|--------|------------------|
| 3.1 | Call `spawn_agent` with worker workflow | Returns `run_id`, `worktree_id`, `branch_name` |
| 3.2 | Worktree created | `git worktree list` shows new worktree |
| 3.3 | Terminal opened | New terminal window/pane visible with Gemini CLI |
| 3.4 | Workflow transitions to `wait_for_worker` | Variables `current_worker_id`, `current_worktree_id`, `current_branch` set |

### Phase 4: Worker Lifecycle

| Step | Action | Success Criteria |
|------|--------|------------------|
| 4.1 | Worker calls `activate_workflow` | Worker workflow state shows `claim_task` step |
| 4.2 | Worker calls `claim_task` | Task status changes to `in_progress`, task `assigned_to` set |
| 4.3 | Worker transitions to `work` step | `task_claimed` variable is `true` |
| 4.4 | Worker completes implementation | Files modified/created as required by task |
| 4.5 | Worker commits changes | Git commit created with `[task_id]` in message |
| 4.6 | Worker calls `close_task` with `commit_sha` | Task status changes to `closed`, `commit_sha` recorded |
| 4.7 | Worker transitions to `report_to_parent` | `task_closed` variable is `true` |
| 4.8 | Worker calls `send_to_parent` | Message delivered to orchestrator session |
| 4.9 | Worker calls `close_terminal` | Terminal session terminates cleanly |
| 4.10 | Worker workflow reaches `complete` | Workflow exit condition met |

### Phase 5: Orchestrator - Wait & Review

| Step | Action | Success Criteria |
|------|--------|------------------|
| 5.1 | `wait_for_task` returns | `completed: true`, `timed_out: false` |
| 5.2 | Workflow transitions to `code_review` | Orchestrator can access diff |
| 5.3 | Review code changes | `git diff main...<branch>` shows worker's changes |
| 5.4 | Set `review_approved` to true | Variable updated in workflow state |
| 5.5 | Workflow transitions to `merge_worktree` | Review passed |

### Phase 6: Merge & Cleanup

| Step | Action | Success Criteria |
|------|--------|------------------|
| 6.1 | Merge branch | Changes merged into dev/main branch |
| 6.2 | Workflow transitions to `cleanup_worktree` | Merge successful |
| 6.3 | Delete worktree | `git worktree list` no longer shows worktree |
| 6.4 | Delete feature branch | `git branch -a` no longer shows branch |
| 6.5 | Workflow transitions to `find_work` | Ready for next task |

### Phase 7: Completion

| Step | Action | Success Criteria |
|------|--------|------------------|
| 7.1 | `suggest_next_task` returns null | No more tasks available |
| 7.2 | `task_tree_complete` evaluates true | All subtasks closed |
| 7.3 | Workflow transitions to `complete` | Exit condition met |
| 7.4 | Orchestrator workflow ends | Session returns to normal mode |

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
| `activate_workflow` | Sets workflow state, injects message |
| `close_terminal` | Terminates session cleanly |
| `end_workflow` | Allows early exit if needed |

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
| Orchestrator handles timeout | Transitions to `handle_timeout`, polls messages |
| Recovery | Can respawn worker or escalate |

### Code Review Failure
| Step | Expected Behavior |
|------|-------------------|
| Set `review_deficiencies` | List of issues populated |
| Attempt < max | Transitions to `respawn_for_fixes` |
| Worker respawned | Same worktree, new terminal, fix prompt |
| Attempt >= max | Transitions to `cleanup_worktree`, abandons |

### Worker Crash
| Step | Expected Behavior |
|------|-------------------|
| Terminal closes unexpectedly | Task remains `in_progress` |
| Orchestrator timeout | `wait_for_task` times out |
| Recovery | Task can be reclaimed by new worker |

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
2. **Worker lifecycle complete**: Worker transitions through all 6 steps to `complete`
3. **Orchestrator lifecycle complete**: Orchestrator finds work, spawns, waits, reviews, merges, cleans up
4. **Git state correct**: Feature branch merged, worktree deleted, commit history clean
5. **No orphaned resources**: No lingering worktrees, terminals, or in-progress tasks
6. **Messages delivered**: Parent received completion message from worker

## Test Task Suggestions

Simple tasks suitable for E2E testing:

1. **Add a comment**: Add a docstring to a specific function
2. **Create a file**: Create a new empty module with basic structure
3. **Fix a typo**: Correct a deliberate typo in documentation
4. **Update a constant**: Change a version number or configuration value

These tasks have clear, verifiable outcomes and minimal complexity.
