# Gobby Orchestrator: Production Hardening Plan

## Context

The orchestrator has been built out as YAML workflows + MCP tools but never run end-to-end. The focus has been on testing workflows and agents in isolation. Now it's time to harden the infrastructure so the full orchestration loop works reliably.

### Architectural note: Separation of concerns

Tool distribution is clean. Orchestration tools live on `gobby-orchestration` as a standalone server; agent tools live on `gobby-agents`; workflows enforce behavior via the engine.

| Layer | Manages | Server |
|-------|---------|--------|
| **Orchestration** | Coordinate agents (orchestrate, wait, monitor) | `gobby-orchestration` |
| **Agents** | Spawn, terminals, worktrees, clones, workflow settings | `gobby-agents` |
| **Workflows** | Behavior enforcement (step transitions, tool restrictions) | Engine (engine.py + YAML) |

Related open tasks that affect scope:
- **#7334** - Skill discovery/injection for interactive vs autonomous agents

### Two orchestration paths

| Path | Workflow | Key Tools (server) |
|------|----------|--------------------|
| **Sequential** | `meeseeks-box.yaml` (step workflow, `mode: self`) | `spawn_agent` (gobby-agents), `wait_for_task` (gobby-orchestration), `merge_clone_to_target` (gobby-clones), `delete_clone` (gobby-clones) |
| **Parallel** | `orchestrate_ready_tasks` MCP tool | `orchestrate_ready_tasks` (gobby-orchestration), `poll_agent_status` (gobby-orchestration), etc. |

Both use `spawn_agent` for spawning and clone/worktree isolation. Note: meeseeks workflows are examples used during development; the final production workflow will be built after hardening is complete.

---

## Phase 1: Sequential Path Hardening (meeseeks-box)

The sequential path is simpler and should work first. These fixes target the tools that `meeseeks-box.yaml` actually calls.

### 1.0 ~~Fix #7244: Task claimed by orchestrator session instead of worker~~ NOT A BUG

**Status**: Investigated — template resolution is correct. `WorkflowState.session_id` (child UUID from `_auto_activate_workflow`) → `ActionContext.session_id` → `{{ session_id }}` resolves to the worker's session. `suggest_next_task` does not auto-claim. `spawn_agent` does not call `claim_task`. Original observation was not reproducible.

### 1.1 Fix merge_clone_to_target branch safety

**File**: `src/gobby/mcp_proxy/tools/clones.py` (lines 384-486)

**Problem**: `merge_clone_to_target` calls `git_manager.merge_branch()` which operates on the main repo. If the merge fails (conflict, network error), the main repo may be left on the wrong branch or in a dirty merge state. The orchestrator session is running in this repo.

**Fix**:
- In `CloneGitManager.merge_branch()`, save current branch before checkout, restore in `finally`
- On merge conflict: abort the merge, restore branch, return structured error
- On any other error: `git merge --abort` + restore branch

**File**: `src/gobby/clones/git.py` (find `merge_branch` method)

### 1.2 ~~Validate workflow engine call_mcp_tool + output_as~~ DONE

**Status**: Completed (commit `2d8bf683`). Tool calls routed through `ToolProxyService`; `output_as` stores results correctly in workflow variables.

### 1.3 ~~Validate workflow engine transition conditions~~ DONE

**Status**: Completed (commit `b706c121`). DotDict fix resolved condition evaluation issues; custom functions and variable access patterns work correctly.

### 1.4 Fix spawn_agent cleanup on isolation prepare failure

**File**: `src/gobby/mcp_proxy/tools/spawn_agent.py`

**Problem**: If `handler.prepare_environment()` partially creates a clone/worktree then throws, no cleanup happens. The clone/worktree is orphaned.

**Fix**: Wrap in try/except, call `handler.cleanup_environment()` on failure. Verify `IsolationHandler` has a cleanup method; add one if missing.

### 1.5 Fix premature stop counter for orchestrators

**File**: `src/gobby/workflows/engine.py`

**Problem**: The premature stop counter resets on every tool call (not just user prompts). For orchestrator workflows running in `mode: self`, the orchestrator's own MCP calls reset the counter, defeating the failsafe.

**Fix**: Only reset `_premature_stop_count` on `BEFORE_AGENT` events (user prompt), not on `BEFORE_TOOL` events.

---

## Phase 2: Parallel Path Hardening

### 2.1 Fix poll_agent_status TOCTOU race

**File**: `src/gobby/mcp_proxy/tools/orchestration/monitor.py` (lines 306-338)

**Problem**: `get_state()` -> modify lists -> `save_state()` is not atomic. A concurrent `orchestrate_ready_tasks` call can append to `spawned_agents` between get and save, and the save overwrites the append.

**Fix**: Add `update_orchestration_lists()` method to `WorkflowStateManager` that wraps the entire read-modify-write in `transaction_immediate()` (following the existing `merge_variables()` pattern):

```python
def update_orchestration_lists(
    self, session_id: str,
    remove_from_spawned: set[str],  # session_ids to remove
    append_to_completed: list[dict],
    append_to_failed: list[dict],
) -> bool:
    with self.db.transaction_immediate() as conn:
        # fetch, modify, write atomically
```

**File**: `src/gobby/workflows/state_manager.py` - add the new method

### 2.2 Fix orchestrate_ready_tasks max_concurrent race

**File**: `src/gobby/mcp_proxy/tools/orchestration/orchestrate.py` (lines 166-173)

**Problem**: Concurrent calls both check slot count, both see capacity, both spawn, exceeding max_concurrent.

**Fix**: Wrap the count-check-and-worktree-claim in a `transaction_immediate()` block. After creating the worktree record and claiming it, re-check the count inside the transaction. If exceeded, rollback.

### 2.3 Fix validation retry orphaning worktrees/clones

**File**: `src/gobby/mcp_proxy/tools/orchestration/review.py`

**Problem**: `process_completed_agents` reopens task for retry, making it eligible for new worktree creation. But old worktree may still exist.

**Fix**: Before reopening task, check if worktree/clone exists. If so, reuse it by clearing the agent_session_id (release) rather than creating a new environment. Store the worktree_id/clone_id in the retry info so the next spawn can pick it up.

### 2.4 Extract spawn helper to eliminate orchestrate.py duplication

**File**: `src/gobby/mcp_proxy/tools/orchestration/orchestrate.py` (lines 447-602)

**Problem**: Terminal/embedded/headless branches are 90% identical (3x ~50 lines each).

**Fix**: Extract into a single `_spawn_in_mode()` helper. Each mode becomes a 3-line call. Reduces orchestrate.py by ~100 lines and removes bug surface area.

**Note**: The extraction is valid regardless of future spawner simplification.

---

## Phase 3: Shared Infrastructure Fixes

### 3.1 Agent registry pre-registration

**File**: `src/gobby/mcp_proxy/tools/spawn_agent.py`

**Problem**: Agent registered AFTER spawn completes. Brief window where agent is running but `poll_agent_status` or `kill_agent` can't find it.

**Fix**: Register with `status="starting"` before `execute_spawn()`. Update to `status="running"` on success. Remove on failure.

**Note**: spawn_agent.py is the orchestration layer above spawners, so this fix is stable.

### 3.2 Configurable stuck timeout

**File**: `src/gobby/workflows/engine.py`

**Problem**: Hardcoded 30-minute stuck timeout. Orchestrator workflows legitimately wait longer (worker_timeout is 600s, with retries that's 30+ minutes).

**Fix**: Read `stuck_timeout` from workflow definition YAML. Default 1800s. Orchestrator workflows can set `stuck_timeout: 7200`.

### 3.3 Auto-transition depth limit logging

**File**: `src/gobby/workflows/engine.py`

**Problem**: Auto-transition chain silently truncates at depth 10. If a workflow hits this, it silently breaks.

**Fix**: Log an error (not warning) with the full chain of steps visited. Include workflow name and session_id for debugging.

### 3.4 Prompt file cleanup

**Files**: `src/gobby/agents/spawn.py`, `src/gobby/sessions/lifecycle.py`

**Problem**: Prompt files in `/tmp` accumulate indefinitely.

**Fix**: Track prompt file path in session metadata. Add cleanup in `lifecycle.py`'s periodic cleanup job: delete prompt files for sessions that ended more than 1 hour ago.

---

## Phase 4: Integration Tests

### 4.1 Sequential orchestrator integration test

**File**: New `tests/mcp_proxy/tools/orchestration/test_sequential_integration.py`

Test the meeseeks-box workflow end-to-end with mocked spawners:
1. Create parent task with 2 subtasks
2. Mock `spawn_agent` to create a session and immediately close the task
3. Mock `merge_clone_to_target` to return success
4. Mock `delete_clone` to return success
5. Drive the workflow engine through: find_work -> spawn_worker -> wait_for_worker -> code_review (auto-approve) -> merge -> cleanup -> find_work -> ... -> complete
6. Verify all tasks closed, clones cleaned up, workflow reaches `complete` step

### 4.2 Parallel orchestrator integration test

**File**: New `tests/mcp_proxy/tools/orchestration/test_parallel_integration.py`

Test orchestrate_ready_tasks -> poll_agent_status -> cleanup flow:
1. Create parent with 3 subtasks, max_concurrent=2
2. Call orchestrate_ready_tasks, verify 2 spawned + 1 skipped
3. Mock agent completion (close tasks)
4. Call poll_agent_status, verify newly_completed
5. Verify workflow state lists updated atomically

### 4.3 Failure scenario tests

**File**: New `tests/mcp_proxy/tools/orchestration/test_failure_scenarios.py`

- Worker crashes (agent exits without closing task)
- Clone creation fails mid-spawn
- Merge conflict during merge step
- Timeout in wait_for_worker with retry

---

## Phase 5: Dry Run Mode

### 5.1 Add dry_run to orchestrate_ready_tasks

**File**: `src/gobby/mcp_proxy/tools/orchestration/orchestrate.py`

Add `dry_run: bool = False` parameter. When true: resolve tasks, check slots, build prompts, return plan without spawning. Useful for validating the orchestrator sees the right tasks before committing.

**Partial progress**: Dry-run evaluator framework exists (commit `e1220c2d`). Needs integration into `orchestrate_ready_tasks`.

### 5.2 Add dry_run to workflow

Add a `dry_run` variable (default false) to the production orchestrator workflow. When true, `spawn_worker` step injects a message showing what WOULD be spawned instead of calling `spawn_agent`. Useful for testing the workflow progression without burning LLM credits. This applies to the final workflow built after hardening, not meeseeks-box specifically.

---

## Implementation Order

```
Phase 1 (Sequential) - Do first, gets the primary use case working
  1.0 NOT A BUG (investigated — template resolution correct)
  1.1 merge safety
  1.2 DONE (commit 2d8bf683)
  1.3 DONE (commit b706c121)
  1.4 spawn cleanup
  1.5 premature stop fix

Phase 4.1 (Sequential integration test) - Validates Phase 1

Phase 2 (Parallel) - Second priority
  2.1 TOCTOU fix
  2.2 max_concurrent fix
  2.3 retry cleanup
  2.4 code dedup

Phase 4.2-4.3 (Parallel + failure tests) - Validates Phase 2

Phase 3 (Shared) - Can be parallelized with Phase 2
  3.1 registry pre-registration
  3.2 stuck timeout
  3.3 auto-transition logging
  3.4 prompt cleanup

Phase 5 (Dry run) - Last, nice to have (5.1 has partial framework)
```

## Critical Files

| File | Changes |
|------|---------|
| `src/gobby/clones/git.py` | merge_branch branch safety (1.1) |
| `src/gobby/workflows/engine.py` | premature stop fix (1.5), stuck timeout (3.2), auto-transition logging (3.3) |
| `src/gobby/workflows/state_manager.py` | update_orchestration_lists (2.1) |
| `src/gobby/mcp_proxy/tools/spawn_agent.py` | cleanup on failure (1.4), pre-registration (3.1) |
| `src/gobby/mcp_proxy/tools/orchestration/monitor.py` | TOCTOU fix (2.1) |
| `src/gobby/mcp_proxy/tools/orchestration/orchestrate.py` | max_concurrent fix (2.2), spawn helper (2.4), dry run (5.1) |
| `src/gobby/mcp_proxy/tools/orchestration/review.py` | retry cleanup (2.3) |
| `src/gobby/install/shared/workflows/meeseeks-box.yaml` | dry run variable (5.2) |

## Verification

After all phases, manual end-to-end test using the production orchestrator workflow (meeseeks workflows serve as development examples; verification will use the final workflow):
1. Create parent task with 3 subtasks via `create_task`
2. Spawn orchestrator agent with the production workflow
3. Observe full loop: find -> spawn -> wait -> review -> merge -> cleanup
4. Verify all subtasks close, clones/worktrees cleaned up, `complete` step reached
5. Verify main repo on correct branch with merged changes
6. **Process Cleanup**: Verify no orphaned `gobby-agent` processes remain (check `ps aux`)
7. **File Cleanup**: Verify no temporary prompts or tool definitions remain in `/tmp`
8. **State Consistency**: Verify `tasks.jsonl` reflects the final state of all tasks
