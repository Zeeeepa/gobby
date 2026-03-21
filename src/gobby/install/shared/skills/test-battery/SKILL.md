---
name: test-battery
description: "Setup wizard + autonomous monitoring loop for orchestrator test battery. Creates cron-driven orchestrator pipeline on a clone, monitors agent progress, and intervenes on infrastructure failures. Persists state in test-battery.md for compaction survival."
version: "3.1.0"
category: testing
triggers: test battery, orchestrator test, run test battery, e2e test, test the orchestrator
metadata:
  gobby:
    audience: interactive
    depth: 0
---

# /gobby test-battery — Orchestrator Test Battery v3

Autonomous monitoring loop for the orchestrator pipeline. Sets up a cron-driven orchestrator on a clone, then monitors continuously — fixing infrastructure bugs as they arise — until the epic completes.

**Three phases:**
1. **Phase 0: Resume** — Check for existing `test-battery.md` and resume monitoring
2. **Phase 1: Setup** — Interactive wizard (10 prompts)
3. **Phase 2: Init** — Create monitoring task, cron job, state file
4. **Phase 3: Monitor** — Autonomous polling loop with intervention protocol

---

## Phase 0: Resume Check

Before anything else, check if a monitoring session is already in progress:

1. Read `test-battery.md` from the project root
2. If it exists and contains `Status: RUNNING`:
   - Parse all configuration and state from the file
   - Report: "Resuming test battery monitoring from cycle N"
   - Skip directly to **Phase 3: Monitoring Loop**
3. If the file doesn't exist or status is COMPLETE/FAILED, proceed to Phase 1

**After compaction, you will land here.** The test-battery.md file is your memory. Trust it.

---

## Phase 1: Interactive Setup Wizard

Collect configuration through 10 sequential prompts. Show the default for each and accept enter/confirmation for defaults.

### Prompt 1: Reset Environment

Ask: "Reset environment? This will delete existing clones, kill running agents, and remove orchestrator cron jobs. (y/N)"

If yes:
```python
# Delete all clones
clones = call_tool("gobby-clones", "list_clones", {})
for clone in clones.clones:
    call_tool("gobby-clones", "delete_clone", {"clone_id": clone.id, "force": true})

# Kill running agents
agents = call_tool("gobby-agents", "list_agents", {"parent_session_id": "<session_id>", "status": "running"})
for agent in agents.runs:
    call_tool("gobby-agents", "kill_agent", {"run_id": agent.id})

# Delete orchestrator cron jobs (skip system jobs with gobby: prefix)
jobs = call_tool("gobby-cron", "list_cron_jobs", {})
for job in jobs where job.name contains "orchestrator" or "test-battery":
    if job.name.startswith("gobby:"):
        continue  # NEVER delete system cron jobs
    call_tool("gobby-cron", "delete_cron_job", {"job_id": job.id})
```

### Prompt 2: Commit Changes

Run `git status`. If there are uncommitted changes:
- Ask: "You have uncommitted changes. Commit them before proceeding? (Y/n)"
- If yes, use the committing-changes skill to commit everything
- If no, warn that uncommitted changes won't be in the clone

### Prompt 3: Target Task/Epic

Ask: "What task or epic should the orchestrator target? Enter a ref (#N) or 'new' to create one."

- If ref provided: fetch the task with `get_task` and confirm it exists
- If "new": ask for a title and create an epic task

### Prompt 4: Expansion

Ask: "How should subtasks be created?"
- **(a) Run expand-task pipeline now** — Will block until expansion completes (~2-5 min)
- **(b) Provide a plan file** — Path to .md plan file for the expander to use
- **(c) Skip** — Subtasks already exist under this epic

If (a): Run expand-task pipeline with `wait_for_completion: true`:
```python
call_tool("gobby-workflows", "run_pipeline", {
    "name": "expand-task",
    "inputs": {"task_id": "<epic_id>", "session_id": "<session_id>"},
    "wait_for_completion": true,
    "wait_timeout": 600
})
```

If (b): Run expand-task with the plan file:
```python
call_tool("gobby-workflows", "run_pipeline", {
    "name": "expand-task",
    "inputs": {"task_id": "<epic_id>", "plan_file": "<path>", "session_id": "<session_id>"},
    "wait_for_completion": true,
    "wait_timeout": 600
})
```

If (c): Verify subtasks exist with `list_tasks(parent_task_id=epic_id)`. Warn if zero subtasks found.

### Prompt 5: Developer Provider/Model

Ask: "Developer agent provider and model? (default: gemini / provider-default)"
- Parse as `provider / model` or just `provider`
- Default: `developer_provider="gemini"`, `developer_model=null`

### Prompt 6: QA Provider/Model

Ask: "QA agent provider and model? (default: claude / opus)"
- Default: `qa_provider="claude"`, `qa_model="opus"`

### Prompt 7: Agent Timeout

Ask: "Agent timeout in seconds? (default: 1200)"
- Default: 1200

### Prompt 8: Cron Interval

Ask: "Cron interval — how often should the orchestrator tick? (default: 5m)"
- Accept formats: "5m", "300", "300s", "10m"
- Convert to seconds
- Default: 300

### Prompt 9: Isolation Mode

Ask: "Agent isolation mode? (default: worktree)"
- **worktree** — Each agent gets a git worktree (fast, shared .git, recommended)
- **clone** — Each agent gets a full git clone (fully isolated, slower setup)
- **none** — Agents work in the main directory (no isolation, use for debugging)
- Default: `isolation="worktree"`

### Prompt 10: Confirm

Display the full configuration:

```
============================================
  Test Battery Configuration
============================================
Epic:           #<N> "<title>"
Subtasks:       <count> tasks
Dev Agent:      <provider> / <model>
QA Agent:       <provider> / <model>
Timeout:        <N>s
Cron Interval:  <N>s (<N>m)
Max Concurrent: 5
Merge Target:   <current_branch>
Isolation:      <worktree|clone|none>
============================================
```

Ask: "Proceed? (Y/n)"

---

## Phase 2: Initialization

Execute these steps in order. If any step fails, report the error and stop.

### Step 1: Create Monitoring Task

```python
task = call_tool("gobby-tasks", "create_task", {
    "title": "Test Battery Monitor: <epic_title>",
    "task_type": "task",
    "category": "testing",
    "validation_criteria": "Epic #<N> reaches orchestration_complete. All subtasks review_approved or closed.",
    "description": "Monitoring task for orchestrator test battery. Do not close until epic completes.",
    "session_id": "<session_id>",
    "claim": true
})
```

### Step 2: Create Cron Job

```python
job = call_tool("gobby-cron", "create_cron_job", {
    "name": "test-battery-orchestrator",
    "action_type": "pipeline",
    "action_config": {
        "pipeline_name": "orchestrator",
        "inputs": {
            "task_id": "<epic_id>",
            "developer_agent": "developer",
            "qa_agent": "qa-reviewer",
            "developer_provider": "<dev_provider>",
            "qa_provider": "<qa_provider>",
            "developer_model": "<dev_model>",
            "qa_model": "<qa_model>",
            "agent_timeout": <timeout>,
            "max_concurrent": 5,
            "merge_target": "<current_branch>",
            "isolation": "<isolation>"
        }
    },
    "schedule_type": "interval",
    "interval_seconds": <interval>,
    "description": "Orchestrator tick for test battery epic #<N>"
})
```

### Step 3: Write State File

Create `test-battery.md` in the project root with the template from the **State File Template** section below. Fill in all configuration values.

### Step 4: Trigger First Tick

```python
call_tool("gobby-cron", "run_cron_job", {"job_id": "<cron_job_id>"})
```

Report: "First orchestrator tick triggered. Entering monitoring loop."

### Step 5: Enter Monitoring Loop

Proceed to Phase 3.

---

## Phase 3: Monitoring Loop

This is the core autonomous loop. **Re-enter here after every compaction** by reading `test-battery.md` in Phase 0.

### Entry Point

1. Read and parse `test-battery.md`
2. Extract: `epic_id`, `cron_job_id`, `monitoring_task_id`, `cycle_number`, `interval_seconds`, `agent_timeout`
3. Report current state: "Monitoring cycle <N>. Epic #<ref>: <open> open, <in_progress> in progress, <needs_review> in review, <review_approved> approved."

### Loop Body (One Cycle)

Repeat this for each orchestrator tick:

#### 1. Poll for Tick Completion

Poll `list_cron_runs` every 30 seconds until a new completed or failed run appears:

```python
while True:
    sleep(30)
    runs = call_tool("gobby-cron", "list_cron_runs", {
        "job_id": "<cron_job_id>",
        "limit": 3
    })
    # Check if there's a run newer than last_run_id
    # A run with status "completed" or "failed" that we haven't seen
    if new_run_found:
        break
```

Extract `pipeline_execution_id` from the completed run.

#### 2. Inspect Tick Results

```python
status = call_tool("gobby-workflows", "get_pipeline_status", {
    "execution_id": "<pipeline_execution_id>"
})
```

Check:
- Did the tick complete successfully? (status = "completed")
- `orchestration_complete` in outputs?
- How many agents were dispatched?
- Did the re-entrancy guard skip this tick?

#### 3. Check Task States

```python
for s in ["open", "in_progress", "needs_review", "review_approved", "closed"]:
    tasks = call_tool("gobby-tasks", "list_tasks", {
        "parent_task_id": "<epic_id>",
        "status": s
    })
```

Record counts and task refs for each status.

#### 4. Check Agent Health

```python
agents = call_tool("gobby-agents", "list_agents", {
    "status": "running"
})
```

For each running agent:
- If running longer than `2 * agent_timeout`: it's a zombie
- Kill it: `call_tool("gobby-agents", "kill_agent", {"run_id": "<run_id>"})`
- Reopen its task: `call_tool("gobby-tasks", "reopen_task", {"task_id": "<task_id>"})`

#### 5. Check for Errors

Tail the daemon log for critical errors:
```bash
tail -50 ~/.gobby/logs/gobby.log | grep -E "(ERROR|CRITICAL|Traceback)"
```

Check recent failed pipeline executions:
```python
call_tool("gobby-workflows", "list_pipeline_executions", {
    "pipeline_name": "orchestrator",
    "status": "failed",
    "limit": 5
})
```

#### 6. Update State File

Increment `cycle_number`. Update task counts, last tick details, and agent activity in `test-battery.md`. Use Edit tool to update specific sections.

#### 7. Evaluate Completion

If `orchestration_complete` was true in tick outputs, OR all subtasks are in `review_approved`/`closed`:

```python
# Disable cron
call_tool("gobby-cron", "toggle_cron_job", {"job_id": "<cron_job_id>"})

# Close monitoring task
call_tool("gobby-tasks", "close_task", {
    "task_id": "<monitoring_task_id>",
    "session_id": "<session_id>"
})
```

Update `test-battery.md` status to `COMPLETE`. Write a final summary report. **Stop.**

#### 8. Evaluate Infrastructure Issues

If the tick failed, or 3+ consecutive ticks have failed, execute the **Intervention Protocol**.

#### 9. Wait for Next Tick

The cron handles scheduling. Wait approximately `interval_seconds` before polling again (the poll loop in step 1 handles this naturally).

---

## Intervention Protocol

When an **infrastructure or orchestration bug** is detected — not agent-level code failures.

### What Counts as Infrastructure

**Intervene on:**
- Pipeline execution failures (step errors in orchestrator pipeline)
- Clone/git errors (path issues, branch conflicts)
- Agent spawn failures (provider errors, config issues)
- Daemon crashes or MCP connection errors
- Task state machine bugs (tasks stuck in wrong states)

**Do NOT intervene on:**
- Agent producing incorrect code (normal — QA will catch it)
- QA rejecting agent work (normal — orchestrator retries)
- Agent timing out on a hard task (orchestrator handles retry)

### Protocol Steps

1. **Pause cron:**
   ```python
   call_tool("gobby-cron", "toggle_cron_job", {"job_id": "<cron_job_id>"})
   ```

2. **Kill running agents:**
   ```python
   agents = call_tool("gobby-agents", "list_agents", {"status": "running"})
   for agent in agents.runs:
       call_tool("gobby-agents", "kill_agent", {"run_id": agent.id})
   ```

3. **Kill orphaned tmux sessions:**
   ```bash
   tmux -L gobby list-sessions 2>/dev/null | grep -v attached | cut -d: -f1 | xargs -I{} tmux -L gobby kill-session -t {}
   ```

4. **Fix the issue** in the main worktree. Run targeted tests to verify the fix.

5. **Commit changes** using the committing-changes skill.

6. **Reset stuck tasks** — Any tasks stuck in `in_progress` from killed agents:
   ```python
   call_tool("gobby-tasks", "reopen_task", {"task_id": "<stuck_task_id>"})
   ```

7. **Restart daemon:**
   ```bash
   gobby restart
   ```
   Wait 5 seconds for daemon to come back. Verify with `gobby status`.

8. **Re-enable cron:**
   ```python
   call_tool("gobby-cron", "toggle_cron_job", {"job_id": "<cron_job_id>"})
   ```

9. **Log in test-battery.md:**
   Add an entry to the Issues Log section with: issue number, type, description, fix applied, commit SHA, cycle number.

10. **Continue monitoring loop.**

---

## State File Template

Create this as `test-battery.md` in the project root during Phase 2:

```markdown
# Test Battery State

> Persistent state for the test-battery monitoring loop.
> Survives context compaction. Read this file on every skill invocation.
> DO NOT DELETE while status is RUNNING.

## Status: RUNNING

## Configuration
- **Epic**: #<N> "<title>"
- **Epic ID**: <uuid>
- **Monitoring Task**: #<M> (ID: <uuid>)
- **Cron Job ID**: <uuid>
- **Current Branch**: <branch>
- **Merge Target**: <branch>
- **Dev Provider/Model**: <provider> / <model>
- **QA Provider/Model**: <provider> / <model>
- **Agent Timeout**: <N>s
- **Cron Interval**: <N>s
- **Max Concurrent**: 5
- **Isolation**: <worktree|clone|none>
- **Started At**: <ISO timestamp>

## Current Cycle: 0

### Task Summary
| Status | Count | Refs |
|--------|-------|------|
| open | 0 | |
| in_progress | 0 | |
| needs_review | 0 | |
| review_approved | 0 | |
| closed | 0 | |

### Last Tick
- **Cron Run ID**: (none yet)
- **Pipeline Execution ID**: (none yet)
- **Status**: (pending first tick)
- **Orchestration Complete**: false
- **Agents Dispatched**: 0
- **Timestamp**: (none yet)

## Issues Log

(No issues yet)

## Pipeline Executions

| Cycle | Execution ID | Status | Dispatched | Open | In Prog | Review | Approved |
|-------|-------------|--------|------------|------|---------|--------|----------|
```

---

## Regression Checks

While monitoring, watch for these known issues from previous smoke tests:

| Check | What to verify | Bug ref |
|-------|---------------|---------|
| Dead-end retry counter | Increments across retries (not stuck at 1/10) | #9937 |
| Session lineage | No "Lineage exceeded" warnings, depth < 5 | #9938 |
| No parallel retries | Single retry chain per epic | #9939 |
| Agent clean exit | Exits within 30s, no 3-min idle wait | #9940 |
| Pipeline efficiency | Total executions < 50 for 3-task epic | — |
| Stop hook scoping | No stop hook errors in agent logs | #9918 |
| Idle detection | Sees through status bar, detects true idle | #9932 |
| Dependency satisfaction | `review_approved` satisfies blocked tasks | #9933 |

**Red flags** (any of these warrants investigation, not necessarily intervention):
- Retry counter stuck at "1/10"
- "Lineage exceeded safety limit" in logs
- Pipeline executions > 50
- Agent idle > 3 minutes before exit

---

## Monitoring Commands

Useful commands for debugging during the monitoring loop:

```bash
# Pipeline pass history
gobby pipelines history orchestrator

# Specific execution details
gobby pipelines status <execution_id>

# Running agents
gobby agents ps

# Task states
gobby tasks list --parent <epic_id>

# Watch for issues
tail -f ~/.gobby/logs/gobby.log | grep -E "(ERROR|dead.end|lineage|retry)"

# Tmux agent sessions
tmux -L gobby list-sessions

# Cron job status
gobby cron list
gobby cron runs <job_id>
```
