# Plan: Tick-Based Orchestrator Pipeline + Cron Job

## Context

The orchestrator pipeline exists but is non-functional: it invokes `dev-loop` which relies on `register_pipeline_continuation` (removed in Phase 6 cleanup). The continuation-based re-invocation model is dead.

**New model:** Cron fires the orchestrator pipeline every 5 minutes. Each tick scans task state, dispatches agents, and exits. The cron schedule IS the loop. The pipeline is idempotent — safe to fire repeatedly.

The conductor is a separate concern: an LLM-powered cron handler for configurable scheduled reasoning tasks (stall detection, task cleanup, memory maintenance, etc.). Not part of this plan.

## Work Items

### 1. Rewrite orchestrator.yaml

**File:** `src/gobby/install/shared/workflows/pipelines/orchestrator.yaml`

Flat tick-based pipeline. Each cron tick does one pass:

```
Step 1:  RE-ENTRANCY GUARD
         list_pipeline_executions(pipeline_name="orchestrator", status="running")
         → if count > 1, exit (we're already running from a previous tick)

Step 2:  SCAN CHILD TASKS
         list_tasks(parent_task_id=task_id, status=open)
         list_tasks(parent_task_id=task_id, status=in_progress)
         list_tasks(parent_task_id=task_id, status=needs_review)
         list_tasks(parent_task_id=task_id, status=review_approved)

Step 3:  DETECT STANDALONE vs EPIC
         pipeline_eval: is_standalone = (all scans empty)
         If standalone, get_task for task_id itself

Step 4:  CHECK COMPLETION
         All subtasks closed/approved (epic) or task closed/approved (standalone) → done

Step 5:  WORKTREE (first tick only)
         get_worktree_by_task(task_id=task_id)
         If none: get_task for branch naming, create_worktree

Step 6:  DISPATCH DEVS (if not at max_concurrent)
         suggest_next_tasks(parent_task_id, max_count=available_slots)
         dispatch_batch(suggestions, agent=developer_agent, worktree_id=...)

Step 7:  DISPATCH QA (for needs_review tasks)
         For first needs_review task: update_observed_files, spawn_agent(qa-reviewer)

Step 8:  IF DONE: merge_worktree, close epic

Step 9:  RESULT
         pipeline_eval: {iteration complete, orchestration_complete, counts}
```

**Inputs** (set via cron `action_config.inputs`):

- `task_id` (required): epic or task ID
- `developer_agent`: "developer"
- `qa_agent`: "qa-reviewer"
- `developer_provider`: "gemini" / `qa_provider`: "claude"
- `developer_model`: null / `qa_model`: "opus"
- `agent_timeout`: 1200 (20 minutes)
- `max_concurrent`: 5
- `merge_target`: "main"

**Key design decisions:**

- No sub-pipeline invocation (dev-loop is dead)
- No continuations — cron is the loop
- Idempotent — `suggest_next_tasks` won't re-suggest tasks with active agents
- Worktree lookup per tick via `get_worktree_by_task` (stateless between runs)
- Re-entrancy guard via `list_pipeline_executions` (skip if already running)

### 2. Reopen task #9916

Clear the stale assignment: `reopen_task(task_id="#9916")`

### 3. Sync updated pipeline to DB

`WorkflowLoader.load_pipeline()` is DB-only at runtime. After rewriting the YAML:

- Call `reload_cache` on gobby-workflows to sync the template to DB
- OR restart the daemon (triggers `sync_bundled_content_to_db`)

### 4. Create cron job for epic #9915

Use gobby-cron MCP tools or `CronJobStorage.create_job()`:

```
name: "orchestrator:9915"
schedule_type: interval
interval_seconds: 300
action_type: pipeline
action_config:
  pipeline_name: orchestrator
  inputs:
    task_id: "#9915"
enabled: true
```

Fires through `CronExecutor._execute_pipeline()` at `src/gobby/scheduler/executor.py:134`.

### 5. Fix CronExecutor for pipeline execution

**File:** `src/gobby/scheduler/executor.py`

Two bugs in `_execute_pipeline`:

**a) No DB on WorkflowLoader (line 149):** `WorkflowLoader()` created with no DB — `load_pipeline()` fails at runtime. Fix: use `self.pipeline_executor.loader` instead.

**b) No project context for MCP tools:** Pipeline MCP steps use `get_project_context()` to resolve task refs like `#9916`. When called from cron (no session), the contextvar is empty and falls back to cwd — which is project-implicit and breaks in multi-project setups. Fix: wrap pipeline execution with explicit project context:

```python
from gobby.utils.project_context import set_project_context, reset_project_context

token = set_project_context({"id": job.project_id})
try:
    execution = await self.pipeline_executor.execute(...)
finally:
    reset_project_context(token)
```

Same pattern needed in `_execute_handler` for conductor/custodian handlers that make MCP calls.

### 6. Add `timeout` to `dispatch_batch`

`dispatch_batch` calls `spawn_agent` internally but doesn't pass through `timeout`. Add it as a parameter.

**File:** `src/gobby/mcp_proxy/tools/spawn_agent/_factory.py:313`

- Add `timeout: int | None = None` to `dispatch_batch` signature
- Pass `timeout=timeout` to `spawn_agent` call at line 354

## Files to modify

| File | Action |
|------|--------|
| `src/gobby/install/shared/workflows/pipelines/orchestrator.yaml` | Rewrite as flat tick pipeline |
| `src/gobby/scheduler/executor.py` | Fix `_execute_pipeline` to use pipeline_executor's loader |
| `src/gobby/mcp_proxy/tools/spawn_agent/_factory.py` | Add `timeout` param to `dispatch_batch` |

## Infrastructure already in place

- `CronExecutor._execute_pipeline()` — handles `action_type: "pipeline"` (executor.py:134)
- `CronScheduler` — polling loop, backoff, cleanup (scheduler.py)
- `WorkflowLoader.load_pipeline()` — DB-only pipeline loading (loader.py:167)
- `PipelineExecutor.execute()` — deterministic step execution (pipeline_executor.py)
- `list_pipeline_executions` tool — supports `status` + `pipeline_name` filters (re-entrancy guard)
- `get_worktree_by_task` tool — worktree lookup by task (stateless between ticks)
- `suggest_next_tasks` + `dispatch_batch` — already handle concurrency + file overlap avoidance
- `gobby:pipeline-heartbeat` cron job — catches stalled executions (safety net)

## Verification

1. Reopen #9916: `call_tool("gobby-tasks", "reopen_task", {task_id: "#9916"})`
2. Rewrite orchestrator.yaml
3. Sync to DB: `call_tool("gobby-workflows", "reload_cache")`
4. Create cron job via MCP
5. Monitor: `gobby cron list` + `gobby cron runs <job-id>`
6. Verify pipeline executions: `list_pipeline_executions(pipeline_name="orchestrator")`
7. Watch task states transition: open → in_progress → needs_review → closed
8. Final: epic #9915 closes when all subtasks complete

## Follow-up (not in scope)

- **Stale in_progress task recovery:** If an agent completes successfully but the pipeline execution fails for an unrelated reason, tasks can get stuck in `in_progress` with no agent. The lifecycle monitor handles dead-agent recovery, but not this edge case. Candidate for the conductor's scheduled reasoning.
- **Failed execution cleanup:** Failed pipeline executions accumulate in the DB. No auto-cleanup exists. Low priority — they're just history records.
- **Conductor wiring:** The conductor (LLM-powered scheduled reasoning) exists but is dormant (`enabled: false`, no tool access verified). Separate effort to wire up for stall detection, task recovery, and other reasoning tasks.
