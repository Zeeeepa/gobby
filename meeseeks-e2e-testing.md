# Meeseeks Agent E2E Testing

End-to-end functional test criteria for the meeseeks agent system.

## Overview

The meeseeks system consists of two complementary workflows:

- **meeseeks-box** (orchestrator): Runs in Claude Code, spawns workers, reviews code, merges
- **meeseeks:worker** (worker): Runs in Gemini CLI within isolated git clones

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
- [ ] MCP servers connected: `gobby-tasks`, `gobby-agents`, `gobby-workflows`, `gobby-clones`
- [ ] Gemini CLI installed and authenticated
- [ ] Git repository with clean working tree
- [ ] Terminal emulator available (ghostty or configured alternative)

## Test Execution Steps

**Objective**: Create a simple task, activate meeseeks-box, let it spawn a Gemini worker, verify completion.

### Step 1: Create Parent Task

```python
mcp__gobby__call_tool(
    server_name="gobby-tasks",
    tool_name="create_task",
    arguments={
        "title": "Meeseeks E2E Test Parent",
        "description": "Parent task for E2E testing meeseeks agent system",
        "session_id": "#813"
    }
)

```

**Expected**: Returns `task_id` (e.g., `#6921`), status `open`

### Step 2: Create Subtask

```python
mcp__gobby__call_tool(
    server_name="gobby-tasks",
    tool_name="create_task",
    arguments={
        "title": "Add test comment to runner.py",
        "description": "Add a single-line comment '# Meeseeks E2E test' at the top of src/gobby/runner.py",
        "parent_task_id": "<parent_task_id>",
        "session_id": "#813"
    }
)

```

**Expected**: Returns subtask `task_id`, linked to parent

### Step 3: Verify Git State

```bash
git worktree list

```

**Expected**: Only main worktree shown

### Step 4: Activate Orchestrator

```python
mcp__gobby__call_tool(
    server_name="gobby-agents",
    tool_name="spawn_agent",
    arguments={
        "agent": "meeseeks",
        "workflow": "box",
        "task_id": "<parent_task_id>",
        "parent_session_id": "#813"
    }
)

```

**Expected**: meeseeks-box workflow activates in current session, `session_task` variable set

### Step 5: Orchestrator Finds Work (automatic)

meeseeks-box calls:

```python
mcp__gobby__call_tool(
    server_name="gobby-tasks",
    tool_name="suggest_next_task",
    arguments={"session_id": "#813"}
)

```

**Expected**: Returns subtask `task_id`

### Step 6: Orchestrator Spawns Worker (automatic)

meeseeks-box calls:

```python
mcp__gobby__call_tool(
    server_name="gobby-agents",
    tool_name="spawn_agent",
    arguments={
        "prompt": "...(activation instructions)...",
        "agent": "meeseeks",
        "workflow": "worker",
        "task_id": "<subtask_id>",
        "isolation": "clone",
        "provider": "gemini",
        "terminal": "ghostty",
        "parent_session_id": "#813"
    }
)

```

**Expected**: Returns `run_id`, `clone_id`, `branch_name`

### Step 7: Verify Clone Created

```python
mcp__gobby__call_tool(
    server_name="gobby-clones",
    tool_name="list_clones",
    arguments={}
)

```

**Expected**: Shows new clone for feature branch

### Step 8: Orchestrator Waits (automatic)

meeseeks-box calls:

```python
mcp__gobby__call_tool(
    server_name="gobby-tasks",
    tool_name="wait_for_task",
    arguments={
        "task_id": "<subtask_id>",
        "timeout": 600
    }
)

```

**Expected**: Blocks until worker closes task

### Step 9: Worker Lifecycle (autonomous in Gemini)

Worker executes these steps autonomously:

1. `claim_task` → task status `in_progress`
2. Work phase → edits file, runs tests
3. `git commit -m "[#subtask] Add test comment"`
4. `close_task` with `commit_sha` → task status `closed`
5. `send_to_parent` → message to orchestrator
6. `kill_agent` → session terminates

### Step 10: Wait Returns

**Expected**: `wait_for_task` returns `{"completed": true, "timed_out": false}`

### Step 11: Orchestrator Reviews (manual)

Review the diff:

```bash
git diff dev...<branch_name>
```

**Expected**: Shows single comment addition

### Step 12: Orchestrator Merges (manual/automatic)

```bash
git merge --squash <branch_name>
git commit -m "[#parent] Merge meeseeks worker changes"
```

### Step 13: Cleanup Clone

```python
mcp__gobby__call_tool(
    server_name="gobby-clones",
    tool_name="delete_clone",
    arguments={"clone_id": "<clone_id>"}
)
```

### Step 14: Verify Final State

```python
mcp__gobby__call_tool(
    server_name="gobby-clones",
    tool_name="list_clones",
    arguments={}
)

```

**Expected**: No active clones

```python
mcp__gobby__call_tool(
    server_name="gobby-tasks",
    tool_name="get_task",
    arguments={"task_id": "<parent_task_id>"}
)

```

**Expected**: Parent and subtask both `closed`

## MCP Tool Verification

Each MCP server must respond correctly:

### gobby-tasks

| Tool                | Test                                 |
| ------------------- | ------------------------------------ |
| `create_task`       | Creates task with all fields         |
| `claim_task`        | Sets status, assigned_to, session_id |
| `close_task`        | Records commit_sha, updates status   |
| `suggest_next_task` | Returns ready task or null           |
| `wait_for_task`     | Blocks until closed or timeout       |
| `get_task`          | Returns full task details            |

### gobby-agents

| Tool             | Test                                        |
| ---------------- | ------------------------------------------- |
| `spawn_agent`    | Creates clone, starts terminal, returns IDs |
| `send_to_parent` | Delivers message to parent session          |
| `poll_messages`  | Returns messages from children              |

### gobby-workflows

| Tool             | Test                        |
| ---------------- | --------------------------- |
| `end_workflow`   | Allows early exit if needed |

Note: `activate_workflow` is called internally by `spawn_agent` when a workflow is specified.
Agent self-termination uses `kill_agent` from gobby-agents (with `session_id` and `stop: true`).

### gobby-clones

| Tool           | Test                                |
| -------------- | ----------------------------------- |
| `create_clone` | Creates isolated clone with branch  |
| `delete_clone` | Removes clone and optionally branch |
| `list_clones`  | Shows all active clones             |

## Error Scenarios

### Worker Timeout

| Step                   | Expected Behavior                                |
| ---------------------- | ------------------------------------------------ |
| Worker exceeds timeout | `wait_for_task` returns `timed_out: true`        |
| Tester observes        | Task status remains `in_progress`                |
| Recovery               | Tester can spawn new worker or manually complete |

### Worker Crash

| Step                         | Expected Behavior                   |
| ---------------------------- | ----------------------------------- |
| Terminal closes unexpectedly | Task remains `in_progress`          |
| Tester timeout               | `wait_for_task` times out           |
| Recovery                     | Task can be reclaimed by new worker |

### Worker Fails to Commit

| Step | Expected Behavior |
| --- | --- |
| Worker makes changes but doesn't commit | Task closed without `commit_sha` |
| Tester observes | Changes exist in clone but not committed |
| Recovery | Tester can manually commit or discard clone |

### No Parent Found

| Step                   | Expected Behavior                                   |
| ---------------------- | --------------------------------------------------- |
| `send_to_parent` fails | `parent_notified` still set to true (error handler) |
| Worker continues       | Proceeds to shutdown normally                       |

## Validation Commands

```bash
# Check daemon status
gobby status

# List active sessions
gobby sessions list

# Check task state
gobby tasks get <task_id>

# List clones
gobby clones list

# Check workflow state (via MCP)
# call_tool("gobby-workflows", "get_workflow_state", {"session_id": "..."})
```

## Success Definition

The E2E test passes when:

1. **Task lifecycle complete**: Task goes from `open` → `in_progress` → `closed`
2. **Worker lifecycle complete**: Worker transitions through workflow steps to `complete`
3. **Spawn successful**: `spawn_agent` returns valid run_id, clone_id, branch_name
4. **Git state correct**: Commit created with task reference, changes mergeable
5. **No orphaned resources**: No lingering clones, terminals, or in-progress tasks
6. **Messages delivered**: Tester received completion message from worker via `poll_messages`
7. **Terminal cleanup**: Worker called `kill_agent` and process exited

## Recommended Test Task

Use a dedicated test marker file that can be reset between runs:

**File**: `tests/e2e/meeseeks_test_marker.py`

**Task Title**: "Update meeseeks E2E test marker"

**Task Description**:

```text
Update tests/e2e/meeseeks_test_marker.py with:

- Current run number (increment RUN_NUMBER)
- Current timestamp (update TIMESTAMP)
- Add a new entry to the RUNS list

The file already exists with the template structure.

```

**Initial File Content** (create once before first test):

```python
"""Meeseeks E2E test marker file.

This file is modified by meeseeks workers during E2E testing.
Reset RUN_NUMBER to 0 to restart test sequence.
"""

RUN_NUMBER = 0
TIMESTAMP = "never"
RUNS: list[str] = []

```

**Validation**:

```bash
# After worker completes:
cat tests/e2e/meeseeks_test_marker.py

# Expected: RUN_NUMBER incremented, TIMESTAMP updated, new entry in RUNS

```

**Why This Task**:

- Repeatable: Reset by reverting file or setting RUN_NUMBER = 0
- Verifiable: Clear success criteria (file changed, values updated)
- Safe: No production impact, isolated to test directory
- Simple: Single file edit, no external dependencies

### Step 2 (Updated): Create Subtask

```python
mcp__gobby__call_tool(
    server_name="gobby-tasks",
    tool_name="create_task",
    arguments={
        "title": "Update meeseeks E2E test marker",
        "description": "Update tests/e2e/meeseeks_test_marker.py: increment RUN_NUMBER, update TIMESTAMP to current ISO time, append run entry to RUNS list.",
        "parent_task_id": "<parent_task_id>",
        "session_id": "#813"
    }
)

```

---

## Test Run Log

Record each test run with timestamp, session ID, and results.

### Run Template

```text
### Run #N - YYYY-MM-DD HH:MM


**Session**: #XXX
**Parent Task**: #YYYY
**Subtask**: #ZZZZ

| Step | Status | Notes |
|------|--------|-------|
| 1. Create parent | ⏳/✅/❌ | |
| 2. Create subtask | ⏳/✅/❌ | |
| 3. Verify git state | ⏳/✅/❌ | |
| 4. Activate orchestrator | ⏳/✅/❌ | |
| 5. Orchestrator finds work | ⏳/✅/❌ | |
| 6. Spawn worker | ⏳/✅/❌ | |
| 7. Verify clone | ⏳/✅/❌ | |
| 8. Wait for task | ⏳/✅/❌ | |
| 9. Worker lifecycle | ⏳/✅/❌ | |
| 10. Wait returns | ⏳/✅/❌ | |
| 11. Review changes | ⏳/✅/❌ | |
| 12. Merge | ⏳/✅/❌ | |
| 13. Cleanup clone | ⏳/✅/❌ | |
| 14. Verify final state | ⏳/✅/❌ | |

**Result**: ⏳ IN PROGRESS / ✅ PASS / ❌ FAIL
**Failure Reason** (if any):
**Duration**:
```

### Run #1 - (pending)

**Session**: #813
**Parent Task**: (to be created)
**Subtask**: (to be created)

| Step                       | Status   | Notes |
| -------------------------- | -------- | ----- |
| 1. Create parent           | ⏳       |       |
| 2. Create subtask          | ⏳       |       |
| 3. Verify git state        | ⏳       |       |
| 4. Activate orchestrator   | ⏳       |       |
| 5. Orchestrator finds work | ⏳       |       |
| 6. Spawn worker            | ⏳       |       |
| 7. Verify clone            | ⏳       |       |
| 8. Wait for task           | ⏳       |       |
| 9. Worker lifecycle        | ⏳       |       |
| 10. Wait returns           | ⏳       |       |
| 11. Review changes         | ⏳       |       |
| 12. Merge                  | ⏳       |       |
| 13. Cleanup clone          | ⏳       |       |
| 14. Verify final state     | ⏳       |       |

**Result**: ⏳ IN PROGRESS
**Failure Reason**:
**Duration**:
