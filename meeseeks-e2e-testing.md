# Meeseeks Agent E2E Testing

End-to-end functional test criteria for the meeseeks agent system.

## Overview

The meeseeks system consists of two complementary workflows:
- **meeseeks-box** (orchestrator): Runs in Claude Code, spawns workers, reviews code, merges
- **meeseeks:worker** (worker): Runs in Gemini CLI within isolated git worktrees

## Test Approach

**Manual orchestration**: The tester acts as the parent/orchestrator, NOT running the meeseeks-box workflow. Instead:

1. Tester creates a test task manually
2. Tester calls `spawn_agent` directly with the meeseeks worker workflow
3. Worker runs autonomously through its full lifecycle
4. Tester monitors and verifies results

This approach isolates the worker lifecycle for focused testing. The meeseeks-box workflow automation is tested separately.

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
| 1.2 | Note current git state | `git worktree list` shows only main worktree |

### Phase 2: Spawn Worker

| Step | Action | Success Criteria |
|------|--------|------------------|
| 2.1 | Call `spawn_agent` with `agent="meeseeks"`, `workflow="worker"`, `task_id` | Returns `run_id`, `worktree_id`, `branch_name` |
| 2.2 | Worktree created | `git worktree list` shows new worktree |
| 2.3 | Terminal opened | New terminal window/pane visible with Gemini CLI |
| 2.4 | Worker workflow auto-activated | Worker starts in `claim_task` step (workflow applied by spawn_agent) |

### Phase 3: Worker Lifecycle (Autonomous)

| Step | Action | Success Criteria |
|------|--------|------------------|
| 3.1 | Worker calls `claim_task` | Task status changes to `in_progress`, task `assigned_to` set |
| 3.2 | Worker transitions to `work` step | `task_claimed` variable is `true` |
| 3.3 | Worker completes implementation | Files modified/created as required by task |
| 3.4 | Worker commits changes | Git commit created with `[task_id]` in message |
| 3.5 | Worker calls `close_task` with `commit_sha` | Task status changes to `closed`, `commit_sha` recorded |
| 3.6 | Worker transitions to `report_to_parent` | `task_closed` variable is `true` |
| 3.7 | Worker calls `send_to_parent` | Message delivered to tester's session |
| 3.8 | Worker calls `close_terminal` | Terminal session terminates cleanly |
| 3.9 | Worker workflow reaches `complete` | Workflow exit condition met |

### Phase 4: Tester Monitoring (During Worker Execution)

| Step | Action | Success Criteria |
|------|--------|------------------|
| 4.1 | Call `wait_for_task` or poll task status | Task eventually reaches `closed` status |
| 4.2 | Call `poll_messages` | Receive completion message from worker |
| 4.3 | Verify task state | `get_task` shows status=closed, commit_sha populated |

### Phase 5: Tester Verification (Post-Completion)

| Step | Action | Success Criteria |
|------|--------|------------------|
| 5.1 | Review code changes | `git diff dev...<branch>` shows worker's changes |
| 5.2 | Verify commit message | Commit includes `[task_id]` reference |
| 5.3 | Run tests if applicable | Tests pass on feature branch |
| 5.4 | Merge branch manually | `git merge --squash <branch>` succeeds |
| 5.5 | Clean up worktree | `git worktree remove <path>` succeeds |
| 5.6 | Delete feature branch | `git branch -D <branch>` succeeds |

### Phase 6: Final Validation

| Step | Action | Success Criteria |
|------|--------|------------------|
| 6.1 | Verify no orphaned worktrees | `git worktree list` shows only main worktree |
| 6.2 | Verify task state | Task is `closed` with linked commit |
| 6.3 | Verify message delivery | `poll_messages` returned worker's completion report |
| 6.4 | Verify terminal cleaned up | No lingering Gemini CLI processes |

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
