# Orchestrator Test Battery

A structured test battery for verifying the orchestrator pipeline and its components. Tests can be run individually (Sections 2-3) or as a full integration (Section 4). Invoke interactively via `/gobby test-battery`.

**Reference:** The 2026-03-07 smoke test (`orchestrator-smoke-test.md`) ran the full orchestrator on a 10-task epic. It exposed 6 bugs (all fixed) and drove the regression checks in Section 5.

---

## Prerequisites

- Gobby daemon running (`gobby status`)
- At least one LLM provider configured (Claude recommended)
- Git repository with clean working tree
- No other orchestrator pipelines running

---

## Section 1: Setup

### 1.1 Create a Plan

Create a small test plan with 2-3 code tasks and 1 docs task:

```bash
cat > .gobby/plans/test-battery.md << 'EOF'
# Test Battery Feature

## Overview
A minimal feature for testing the orchestrator pipeline.

## Phase 1: Implementation

### 1.1 Create greeting module [category: code]
Target: `src/test_battery_greeting.py`
Create a simple greeting function that returns "Hello, {name}!".

### 1.2 Add greeting CLI command [category: code] (depends: 1.1)
Target: `src/test_battery_cli.py`
Add a CLI command that calls the greeting function.

### 1.3 Document the greeting feature [category: docs]
Target: `docs/test-battery-greeting.md`
Write brief documentation for the greeting module.
EOF
```

**Pass criteria:**
- [ ] Plan file created at `.gobby/plans/test-battery.md`
- [ ] Contains 2 code tasks and 1 docs task
- [ ] Dependencies specified correctly

### 1.2 Create Epic

```python
call_tool("gobby-tasks", "create_task", {
    "title": "Test Battery Feature",
    "description": "Minimal feature for orchestrator test battery",
    "task_type": "epic",
    "category": "code",
    "session_id": "<session_id>"
})
```

**Pass criteria:**
- [ ] Epic created with valid task ID
- [ ] Task type is "epic"
- [ ] Status is "open"

---

## Section 2: Expand-Task Pipeline (Standalone)

Tests the expansion pipeline in isolation. This can be run independently of the full orchestrator.

### 2.1 Run Expansion

```python
result = call_tool("gobby-workflows", "run_pipeline", {
    "name": "expand-task",
    "inputs": {"task_id": "<epic_id>", "session_id": "<session_id>"},
    "wait_for_completion": true
})
```

**Pass criteria:**
- [ ] Pipeline completes successfully (status: "completed")
- [ ] Expander agent spawned and completed
- [ ] Subtasks created under the epic

### 2.2 Verify Subtasks

```python
call_tool("gobby-tasks", "list_tasks", {"parent_task_id": "<epic_id>"})
```

**Pass criteria:**
- [ ] At least 2 subtasks created
- [ ] Each has `validation_criteria`
- [ ] Each has `category` assigned
- [ ] Dependencies wired (1.2 depends on 1.1)

### 2.3 Verify File Annotations

```python
call_tool("gobby-tasks", "get_affected_files", {"task_id": "<subtask_id>"})
```

**Pass criteria:**
- [ ] At least one subtask has `affected_files` populated
- [ ] File paths are relative to repo root
- [ ] No overlapping files between parallel-safe tasks

### 2.4 Verify Dependency Analysis

When multiple subtasks exist, the expansion pipeline runs file overlap detection:

**Pass criteria:**
- [ ] Dependency analysis step ran (check pipeline execution steps)
- [ ] Tasks sharing files have dependency edges between them
- [ ] Independent tasks have no spurious dependencies

---

## Section 3: Dev-Loop Pipeline (Standalone)

Tests the dev/QA dispatch loop in isolation. Requires a pre-expanded epic (run Section 2 first or use an existing expanded epic).

### 3.1 Create Worktree Manually

The dev-loop expects a pre-created worktree. Create one:

```python
wt = call_tool("gobby-worktrees", "create_worktree", {
    "branch": "test-dev-loop-<epic_num>",
    "base": "HEAD",
    "session_id": "<session_id>"
})
# Note the worktree_id from the result
```

**Pass criteria:**
- [ ] Worktree created successfully
- [ ] Branch exists and is checked out in worktree

### 3.2 Run Dev-Loop Directly

```python
call_tool("gobby-workflows", "run_pipeline", {
    "name": "dev-loop",
    "inputs": {
        "session_task": "<epic_ref>",
        "worktree_id": "<wt_id>",
        "merge_target": "<current_branch>",
        "max_concurrent": 1,
        "max_iterations": 10
    },
    "continuation_prompt": "Dev-loop pass completed. Check task states."
})
```

The dev-loop is event-driven: each pass dispatches agents then exits. Agent completions trigger the next pass via continuations.

**Pass criteria:**
- [ ] First pass completes with `orchestration_complete: false`
- [ ] Returns iteration count and task state summary

### 3.3 Verify Developer Dispatch

```python
call_tool("gobby-agents", "list_agents", {})
```

**Pass criteria:**
- [ ] Developer agent(s) spawned
- [ ] Agent uses the epic worktree (not a new worktree)
- [ ] Task claimed by the agent (status: "in_progress")
- [ ] Only `max_concurrent` agents running simultaneously

### 3.4 Verify Agent Step Workflow

Monitor a developer agent's step transitions:

**Pass criteria:**
- [ ] Agent starts in `claim` step
- [ ] After `claim_task` succeeds, transitions to `implement`
- [ ] After `mark_task_needs_review`, transitions to `terminate`
- [ ] Agent exits cleanly (no 3-minute idle wait at prompt)

### 3.5 Verify Idle Detection + Reprompt

If an agent stalls at the prompt:

**Pass criteria:**
- [ ] Lifecycle monitor detects idle agent within 60s
- [ ] Reprompt sent (up to 3 attempts)
- [ ] After 3 failed reprompts, agent is killed and task recovered to `open`
- [ ] Idle detector sees through status bar noise (not fooled by cursor updates)

### 3.6 Verify QA Dispatch

After a developer marks a task `needs_review`:

**Pass criteria:**
- [ ] Next dev-loop pass detects `needs_review` tasks
- [ ] QA reviewer agent spawned
- [ ] QA agent can see code changes (same worktree)
- [ ] Task transitions to `review_approved` or reopened with notes

### 3.7 Verify Continuation Registration

Check that event-driven re-invocation works:

**Pass criteria:**
- [ ] Continuations registered for dispatched agent run IDs
- [ ] Agent completion fires continuation callback
- [ ] Continuation triggers a fresh dev-loop pass
- [ ] No parallel continuation chains (single chain per epic)

### 3.8 Verify Iteration Control

**Pass criteria:**
- [ ] `_current_iteration` increments across passes
- [ ] `max_iterations` guard stops the loop when reached
- [ ] Iteration count visible in pipeline execution results

---

## Section 4: Full Orchestrator (Integration)

Tests the complete flow: expand epic, create worktree, run dev-loop. Run this after verifying components work individually in Sections 2-3.

### 4.1 Start Orchestrator on Fresh Epic

Create a new epic (or reuse from Section 1) that has NOT been expanded yet:

```python
call_tool("gobby-workflows", "run_pipeline", {
    "name": "orchestrator",
    "inputs": {
        "session_task": "<epic_ref>",
        "merge_target": "<current_branch>",
        "max_concurrent": 2,
        "max_iterations": 50
    },
    "continuation_prompt": "Orchestrator pass completed. Check task states and report."
})
```

**Pass criteria:**
- [ ] Pipeline starts (returns `execution_id`)
- [ ] Epic expanded (subtasks created)
- [ ] Worktree created with `epic-{N}` branch
- [ ] Dev-loop entered and first developer dispatched
- [ ] First pass completes with `orchestration_complete: false`

### 4.2 Monitor Through Completion

Use monitoring tools to watch the orchestrator progress:

```bash
gobby pipelines history orchestrator   # Chain of event-driven passes
gobby agents ps                        # Running agents
gobby tasks list --parent <epic_id>    # Task state transitions
```

**Pass criteria:**
- [ ] Dev agents complete and QA agents dispatch automatically
- [ ] All tasks reach `review_approved`
- [ ] Final pass returns `orchestration_complete: true`
- [ ] Total pipeline executions < 50 (no retry spiral)

### 4.3 Standalone Task Test

Run the orchestrator with a single non-epic task:

```python
task = call_tool("gobby-tasks", "create_task", {
    "title": "Standalone test task",
    "task_type": "task",
    "category": "code",
    "validation_criteria": "Creates a test file",
    "session_id": "<session_id>"
})

call_tool("gobby-workflows", "run_pipeline", {
    "name": "orchestrator",
    "inputs": {
        "session_task": task["ref"],
        "merge_target": "<current_branch>",
        "max_iterations": 20
    },
    "continuation_prompt": "Standalone orchestrator pass completed."
})
```

**Pass criteria:**
- [ ] Orchestrator detects standalone mode (`is_standalone: true`)
- [ ] Skips expansion (no children to create)
- [ ] Developer dispatched for the task itself
- [ ] QA dispatched when task reaches `needs_review`
- [ ] Final pass returns `orchestration_complete: true`

---

## Section 5: Regression Checks

These checks verify fixes for bugs discovered during the 2026-03-07 smoke test. Each references the original bug task.

### 5.1 Dead-End Retry Counter (#9937)

When no agents are dispatched and orchestration isn't complete, the dead-end retry mechanism activates.

**Pass criteria:**
- [ ] Retry counter increments across retries (2/10, 3/10, etc.)
- [ ] Counter resets when a real dispatch happens
- [ ] After max retries (10), pipeline stops

**How to check:** Look at daemon logs for dead-end retry messages. Counter should never stay at "1/10" across multiple retries.

### 5.2 Session Lineage (#9938)

Dead-end retries should reuse the root session, not chain child-of-child sessions.

**Pass criteria:**
- [ ] No "Lineage exceeded safety limit" warnings in daemon logs
- [ ] Session depth stays bounded (< 5 levels)
- [ ] Retry sessions reference the root pipeline session

**How to check:** `tail -f ~/.gobby/logs/gobby.log | grep -i lineage`

### 5.3 No Parallel Retry Chains (#9939)

Multiple agent completions firing simultaneously should not create parallel retry chains.

**Pass criteria:**
- [ ] Only one retry chain active per epic at a time
- [ ] Concurrent agent completions don't fork into independent retry loops
- [ ] Total pipeline executions stay reasonable (< 50 for a 3-task epic)

### 5.4 Agent Clean Exit (#9940)

Agents should exit promptly after completing their step workflow.

**Pass criteria:**
- [ ] Agent exits within 30s of completing work
- [ ] No 3-minute idle wait before lifecycle monitor kills the agent
- [ ] Stop hooks don't trap agent sessions in a loop

### 5.5 Pipeline Execution Efficiency

The smoke test ran 371 executions for 10 tasks (2.7% efficiency). This should be dramatically better.

**Pass criteria:**
- [ ] Total pipeline executions < 50 for a 3-task epic
- [ ] No runaway retry loops visible in `gobby pipelines history`
- [ ] Each pass does useful work (dispatches an agent or detects completion)

### 5.6 Stop Hook Scoping (#9918)

Stop hooks (memory/triage enforcement) should only apply to interactive sessions, not agent sessions.

**Pass criteria:**
- [ ] Agent sessions skip memory/triage stop gates
- [ ] Interactive sessions still enforce stop gates normally
- [ ] No "stop hook error" in agent logs

### 5.7 Idle Detection Accuracy (#9932)

The idle detector should correctly identify agents sitting at the prompt, even with status bar updates.

**Pass criteria:**
- [ ] Idle detector not fooled by Claude Code status bar output
- [ ] Correctly identifies true idle (waiting at prompt) vs active (running tools)
- [ ] Reprompt fires within 60s of agent going idle

### 5.8 Dependency Satisfaction (#9933)

Tasks in `review_approved` status should satisfy dependency requirements for blocked tasks.

**Pass criteria:**
- [ ] `list_ready_tasks` treats `review_approved` as a satisfied dependency
- [ ] Blocked tasks become dispatchable when blockers reach `review_approved`
- [ ] Only `open` and `in_progress` count as unsatisfied

---

## Section 6: Cleanup

### 6.1 Verify Completion

```python
call_tool("gobby-tasks", "list_tasks", {
    "parent_task_id": "<epic_id>",
    "status": "open"
})
```

**Pass criteria:**
- [ ] All subtasks reached `review_approved` or `closed`
- [ ] Final execution result has `orchestration_complete: true`

### 6.2 Clean Up Test Artifacts

```bash
# Delete test files created by the battery
rm -f src/test_battery_greeting.py src/test_battery_cli.py
rm -f docs/test-battery-greeting.md
rm -f .gobby/plans/test-battery.md

# Delete the epic worktree
gobby worktrees list
gobby worktrees delete <worktree_id>
```

**Pass criteria:**
- [ ] Test files removed
- [ ] Worktree cleaned up
- [ ] No dangling branches

---

## Section 7: Issue Tracking

### Discovered Issues

Record any issues found during the test battery:

| # | Severity | Description | Component | Task Created? |
|---|----------|-------------|-----------|---------------|
| 1 | | | | |
| 2 | | | | |
| 3 | | | | |

### Improvement Suggestions

| # | Description | Priority |
|---|-------------|----------|
| 1 | | |
| 2 | | |

---

## Section 8: Results Summary

| Section | Tests | Pass | Fail | Skip |
|---------|-------|------|------|------|
| 1. Setup | 2 | | | |
| 2. Expand-Task | 4 | | | |
| 3. Dev-Loop | 8 | | | |
| 4. Full Orchestrator | 3 | | | |
| 5. Regression | 8 | | | |
| 6. Cleanup | 2 | | | |
| **Total** | **27** | | | |

### Overall Result

- [ ] **PASS** — All critical tests pass, no blocking issues
- [ ] **PASS WITH ISSUES** — Core flow works, non-critical issues found
- [ ] **FAIL** — Blocking issues prevent orchestrator from completing

### Recommendations

_(Fill in based on results)_

---

## Monitoring Reference

Commands learned from the smoke test for debugging orchestrator issues:

```bash
# Pipeline pass history (see event-driven chain)
gobby pipelines history orchestrator

# Specific execution details
gobby pipelines status <execution_id>

# Running agents and states
gobby agents ps

# Agent activity logs
gobby agents logs <run_id>

# Task state overview
gobby tasks list --parent <epic_id>

# Watch for retry spirals and lineage issues
tail -f ~/.gobby/logs/gobby.log | grep -E "(dead.end|lineage|retry)"

# Check session depth
tail -f ~/.gobby/logs/gobby.log | grep -i "session.*depth"
```

### Red Flags to Watch For

| Signal | Indicates | Reference |
|--------|-----------|-----------|
| Retry counter stuck at "1/10" | Dead-end counter not incrementing | Bug #9937 |
| "Lineage exceeded safety limit" | Session chaining bug | Bug #9938 |
| Pipeline executions > 50 | Retry spiral or parallel chains | Bug #9939 |
| Agent idle > 3 minutes | Stop hooks blocking exit | Bug #9940 |
| "stop hook error" in agent logs | Stop gate scoping issue | Bug #9918 |
