---
name: doctor
description: This skill should be used when the user asks to "/gobby doctor", "run doctor", "security audit", "health check", "systems check", "run diagnostics". Run comprehensive systems check and security audit verifying CLI and MCP tools work correctly.
category: core
---

# /gobby-diagnostic - System Diagnostics Skill

This skill runs a comprehensive systems check to verify Gobby's CLI commands and MCP tools are functioning correctly. All tests use the `__diag__` prefix for automatic cleanup.

## Subcommands

### `/gobby-diagnostic` - Standard check (phases 1-3)
Run prerequisite checks, read-only tests, and write+cleanup tests.

### `/gobby-diagnostic --quick` - Quick check (phases 1-2 only)
Run prerequisite checks and read-only tests only. No resources created.

### `/gobby-diagnostic --full` - Full check (all phases)
Include resource-heavy tests (worktrees, clones). Takes longer but tests everything.

### `/gobby-diagnostic --cleanup` - Cleanup only
Scan for and remove stale `__diag__` artifacts from previous failed runs.

## Execution Protocol

Execute phases sequentially. Track all created resource IDs for cleanup. Report PASS/FAIL per test.

---

## Phase 1: Prerequisites

Run these first. If any fail, stop and report - other tests won't be reliable.

### 1.1 Daemon Status
```bash
gobby status
```
Expected: Daemon is running.

### 1.2 MCP Server Connectivity
Call `gobby.list_mcp_servers()`

Expected: Returns list of servers. Check that core servers are connected:
- `gobby-tasks`
- `gobby-memory`
- `gobby-sessions`

### 1.3 Database Connectivity
Call `gobby-sessions.list_sessions(limit=1)`

Expected: Returns without error (empty list is OK).

Report summary: "Prerequisites: X/3 PASS"

---

## Phase 2: Read-Only Tests

These tests only read data - no cleanup needed.

### 2.1 CLI List Commands
Run each command and verify no errors:

| Command | Expected |
|---------|----------|
| `gobby sessions list --limit 1` | Returns without error |
| `gobby tasks list --limit 1` | Returns without error |
| `gobby memory list --limit 1` | Returns without error |
| `gobby skills list --limit 1` | Returns without error |
| `gobby workflows list` | Returns without error |
| `gobby worktrees list` | Returns without error |
| `gobby clones list` | Returns without error |
| `gobby agents list` | Returns without error |

### 2.2 MCP List Tools
Call each tool and verify response:

| Server | Tool | Expected |
|--------|------|----------|
| `gobby-sessions` | `list_sessions` | Returns list/empty |
| `gobby-sessions` | `session_stats` | Returns stats object |
| `gobby-tasks` | `list_tasks` | Returns list/empty |
| `gobby-memory` | `list_memories` | Returns list/empty |
| `gobby-memory` | `memory_stats` | Returns stats object |
| `gobby-metrics` | `get_tool_metrics` | Returns metrics object |
| `gobby-metrics` | `get_top_tools` | Returns list |
| `gobby-workflows` | `list_workflows` | Returns list/empty |
| `gobby-worktrees` | `list_worktrees` | Returns list/empty |
| `gobby-clones` | `list_clones` | Returns list/empty |
| `gobby-agents` | `list_agents` | Returns list/empty |

### 2.3 MCP Get/Search Tools
Call tools that retrieve or search data:

| Server | Tool | Args | Expected |
|--------|------|------|----------|
| `gobby` | `search_tools` | `query="test"` | Returns results |
| `gobby` | `recommend_tools` | `task_description="list items"` | Returns recommendations |
| `gobby-memory` | `search_memories` | `query="__nonexistent__"` | Returns empty (no error) |

Report summary: "Read-Only: X/Y PASS"

---

## Phase 3: Write + Cleanup Tests

Create test resources, verify, then delete. Track all IDs for cleanup.

**CRITICAL**: Initialize cleanup tracker before starting:
```
cleanup_tracker = {
    "memories": [],
    "tasks": [],
    "worktrees": [],
    "clones": []
}
```

### 3.1 Memory Create/Delete Cycle

**Create:**
```
gobby-memory.create_memory(
    content="__diag__ diagnostic test memory - safe to delete",
    tags="__diag__,test",
    importance=0.1
)
```
Store returned `memory_id` in `cleanup_tracker["memories"]`.

**Verify:** Call `gobby-memory.get_memory(memory_id=<id>)` - should return the memory.

**Delete:** Call `gobby-memory.delete_memory(memory_id=<id>)`

**Verify deletion:** Call `gobby-memory.get_memory(memory_id=<id>)` - should return error/not found.

### 3.2 Task Create/Close Cycle

**Get session ID first:**
Call `gobby-sessions.get_current_session()` to retrieve the current session object.
Use the returned `id` field as the `session_id` parameter below.

**Create:**
```
gobby-tasks.create_task(
    title="__diag__ diagnostic test task",
    description="Diagnostic test task - safe to delete",
    task_type="chore",
    session_id=<id from gobby-sessions.get_current_session()>
)
```
Store returned `task_id` in `cleanup_tracker["tasks"]`.

**Verify:** Call `gobby-tasks.get_task(task_id=<id>)` - should return the task.

**Update:** Call `gobby-tasks.update_task(task_id=<id>, status="completed")`

**Verify update:** Call `gobby-tasks.get_task(task_id=<id>)` - status should be "completed".

**Close:** Call `gobby-tasks.close_task(task_id=<id>, reason="completed")`

### 3.3 Workflow Variable Cycle (session-scoped, auto-cleaned on session termination)

**Note:** Workflow variables are session-scoped and automatically cleaned up when the session ends. No `__diag__` prefix needed since they don't persist beyond the session.

**Set:**
```
gobby-workflows.set_variable(
    name="diag_test_var",
    value="diagnostic_value"
)
```

**Get:** Call `gobby-workflows.get_variable(name="diag_test_var")` - should return "diagnostic_value".

Report summary: "Write+Cleanup: X/3 PASS"

---

## Phase 4: Resource-Heavy Tests (--full only)

Only run with `--full` flag. These create filesystem resources.

### 4.1 Worktree Cycle

**Check spawn capability:**
```
gobby-worktrees.can_spawn_worktree()
```
If false, skip with note "Worktree spawn not available".

**Create:**
```
gobby-worktrees.create_worktree(
    branch="__diag__/test-branch",
    base_branch="HEAD"
)
```
Store returned `worktree_id`.

**Verify:** Call `gobby-worktrees.get_worktree(worktree_id=<id>)` - should return worktree.

**Delete:** Call `gobby-worktrees.delete_worktree(worktree_id=<id>, force=true)`

**Verify deletion:** Call `gobby-worktrees.get_worktree(worktree_id=<id>)` - should return error/not found.

### 4.2 Clone Cycle

**Check spawn capability:**
```
gobby-clones.can_spawn_clone()
```
If false, skip with note "Clone spawn not available".

**Create:**
```
gobby-clones.create_clone(
    name="__diag__-test-clone"
)
```
Store returned `clone_id`.

**Verify:** Call `gobby-clones.get_clone(clone_id=<id>)` - should return clone.

**Delete:** Call `gobby-clones.delete_clone(clone_id=<id>, force=true)`

**Verify deletion:** Call `gobby-clones.get_clone(clone_id=<id>)` - should return error/not found.

### 4.3 Agent Spawn Check (read-only)

**Check capability:**
```
gobby-agents.can_spawn_agent()
```
Report result (PASS if returns true/false without error, capability status is informational).

Report summary: "Resource-Heavy: X/3 PASS"

---

## Cleanup Protocol

Run cleanup in this order (reverse dependency):

### Step 1: Clean Clones
Search for clones with `__diag__` prefix:
```
gobby-clones.list_clones()
```
For each clone with name starting with `__diag__`:
```
gobby-clones.delete_clone(clone_id=<id>, force=true)
```

### Step 2: Clean Worktrees
Search for worktrees with `__diag__` prefix:
```
gobby-worktrees.list_worktrees()
```
For each worktree with branch starting with `__diag__`:
```
gobby-worktrees.delete_worktree(worktree_id=<id>, force=true)
```

### Step 3: Clean Tasks
Search for tasks with `__diag__` prefix:
```
gobby-tasks.list_tasks()
```
For each task with title starting with `__diag__`:
```
gobby-tasks.close_task(task_id=<id>, reason="obsolete")
```

### Step 4: Clean Memories
Search for memories with `__diag__` tag:
```
gobby-memory.list_memories(tags_any="__diag__")
```
For each memory:
```
gobby-memory.delete_memory(memory_id=<id>)
```

---

## Stale Artifact Detection

Before running tests, check for orphaned `__diag__` artifacts:

1. Call `gobby-memory.list_memories(tags_any="__diag__")`
2. Call `gobby-tasks.list_tasks()` and filter for `__diag__` prefix
3. Call `gobby-worktrees.list_worktrees()` and filter for `__diag__` prefix
4. Call `gobby-clones.list_clones()` and filter for `__diag__` prefix

If any found, report:
```
WARNING: Found X stale diagnostic artifacts from previous run.
Run `/gobby-diagnostic --cleanup` to remove them, or they will be cleaned after this run.
```

---

## Output Format

### Progress Reporting
For each test, report:
```
[PASS] <Test Name>
[FAIL] <Test Name>: <Error Message>
[SKIP] <Test Name>: <Reason>
```

### Summary
At the end, report:
```
=== Diagnostic Summary ===
Phase 1 (Prerequisites):  X/3 PASS
Phase 2 (Read-Only):      X/Y PASS
Phase 3 (Write+Cleanup):  X/3 PASS
Phase 4 (Resource-Heavy): X/3 PASS (or "Skipped - use --full")

Overall: X/Y tests passed
Cleanup: All __diag__ artifacts removed
```

### Failure Report
If any tests fail, include a failure summary:
```
=== Failures ===
1. [Phase 2] list_memories: Connection timeout after 10s
2. [Phase 3] create_task: Permission denied
```

---

## Timeouts

| Operation Type | Timeout |
|----------------|---------|
| Read operations | 10 seconds |
| Write operations | 30 seconds |
| Resource-heavy (worktree/clone) | 120 seconds |

If a timeout occurs, log the failure and continue to the next test.

---

## Error Handling

1. **Prerequisite failures**: Stop immediately - report which prerequisite failed
2. **Test failures**: Log failure, continue to next test, ensure cleanup still runs
3. **Cleanup failures**: Log warning but don't fail the diagnostic
4. **Timeout**: Treat as failure, continue to next test

---

## Examples

### Quick health check
User: `/gobby-diagnostic --quick`
Run phases 1-2 only, report results

### Standard diagnostic
User: `/gobby-diagnostic`
Run phases 1-3, create/delete test resources

### Full system test
User: `/gobby-diagnostic --full`
Run all phases including worktree/clone tests

### Cleanup stale artifacts
User: `/gobby-diagnostic --cleanup`
Only run cleanup protocol, report what was removed
