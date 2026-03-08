---
name: test-battery
description: "Use when user asks to 'run test battery', 'orchestrator test', 'e2e test', 'test the orchestrator'. Interactive skill that walks through the orchestrator test battery step by step. Supports testing individual components (expand-task, dev-loop) or the full orchestrator."
version: "2.0.0"
category: testing
triggers: test battery, orchestrator test, run test battery, e2e test, test expand, test dev-loop
metadata:
  gobby:
    audience: interactive
    depth: 0
---

# /gobby test-battery — Orchestrator Test Battery

Interactive skill for testing orchestrator components individually or end-to-end. Each section is a self-contained test with structured output.

**Components testable independently:**
- **Expand-task** (Section 2) — Task decomposition pipeline
- **Dev-loop** (Section 3) — Developer/QA dispatch cycle
- **Full orchestrator** (Section 4) — Integrated expand + worktree + dev-loop

**Regression suite** (Section 5) — Checks for bugs found in the 2026-03-07 smoke test

## Before Starting

1. Read the full test battery reference: `docs/guides/orchestrator-test-battery.md`
2. Verify prerequisites:
   - Daemon running: `gobby status`
   - Clean git state: `git status`
   - No other orchestrator pipelines running
3. Ask the user which sections to run:
   - **All** — Full battery (Sections 1-8)
   - **Expand only** — Sections 1-2 (setup + expand-task)
   - **Dev-loop only** — Sections 1, 3 (setup + dev-loop, requires pre-expanded epic)
   - **Integration only** — Sections 1, 4 (setup + full orchestrator)
   - **Regression only** — Section 5 (run during any of the above)

## Workflow

Walk through each selected section interactively, reporting results as you go.

### Section 1: Setup

1. Create a minimal test plan at `.gobby/plans/test-battery.md` with 2-3 code tasks and 1 docs task
2. Create an epic task from the plan
3. Report:
   ```
   Section 1: Setup
   PASS Plan created: .gobby/plans/test-battery.md
   PASS Epic created: #<N> "Test Battery Feature"
   ```

### Section 2: Expand-Task Pipeline (Standalone)

Tests expansion in isolation. Use `wait_for_completion: true` since expansion is synchronous (waits for researcher agent).

1. Run `expand-task` pipeline on the epic
2. Verify subtasks created with categories, validation criteria, and dependencies
3. Check file annotations on subtasks
4. Check dependency analysis (file overlap detection between tasks)
5. Report:
   ```
   Section 2: Expand-Task Pipeline
   PASS Pipeline completed: <execution_id>
   PASS Subtasks created: N tasks
   PASS Dependencies wired: [list]
   PASS File annotations: [count] files annotated
   FAIL Dependency analysis: [issue]  (if applicable)
   ```

### Section 3: Dev-Loop Pipeline (Standalone)

Tests the dev/QA dispatch loop in isolation. Requires a pre-expanded epic from Section 2 or an existing one.

**Setup:** Create a worktree manually before running dev-loop:
```python
wt = call_tool("gobby-worktrees", "create_worktree", {
    "branch": "test-dev-loop-<epic_num>",
    "base": "HEAD",
    "session_id": "<session_id>"
})
```

**Run:** Use `continuation_prompt` — the dev-loop is event-driven, each pass dispatches agents then exits:
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

**Do NOT use `wait_for_completion`** — the dev-loop completes quickly per pass. Continuations handle re-invocation.

Check these across multiple passes:

1. Developer dispatch and task claiming
2. Agent step workflow (claim -> implement -> terminate)
3. Idle detection + reprompt cycle (if agent stalls)
4. QA dispatch on `needs_review`
5. Continuation registration (event-driven re-invocation)
6. Iteration counting and `max_iterations` guard
7. Report:
   ```
   Section 3: Dev-Loop Pipeline
   PASS Worktree created: <wt_id>
   PASS First pass completed, iteration 1
   PASS Developer dispatched: agent <run_id>
   PASS Step workflow: claim -> implement -> terminate
   PASS QA dispatched on needs_review
   PASS Continuation fired, iteration 2
   PASS Iteration count increments correctly
   FAIL Idle detection: [issue]  (if applicable)
   ```

**Monitoring:** Use `gobby pipelines history dev-loop` to see the chain of passes and `gobby agents ps` to watch agent states.

### Section 4: Full Orchestrator (Integration)

Tests the complete flow. Run this after verifying components individually in Sections 2-3, or as a standalone integration test.

1. Start the orchestrator pipeline on a fresh (unexpanded) epic with `continuation_prompt`
2. Monitor progress — each pass is a separate execution triggered by agent completions
3. Verify expansion, worktree creation, developer dispatch, QA review
4. Run standalone task test (non-epic single task)
5. Report:
   ```
   Section 4: Full Orchestrator
   PASS Epic expanded: N subtasks
   PASS Worktree created: epic-<N>
   PASS Dev/QA cycle completed
   PASS All tasks reached review_approved
   PASS orchestration_complete: true
   PASS Standalone task: detected and completed
   FAIL [component]: [issue]  (if applicable)
   ```

**Monitoring:** Use `gobby pipelines history orchestrator` to see the chain of passes. Check `orchestration_complete` in execution results to know when done.

### Section 5: Regression Checks

Verify fixes for bugs found during the 2026-03-07 smoke test. Run these checks during any orchestrator test (Sections 3 or 4). Watch daemon logs: `tail -f ~/.gobby/logs/gobby.log`

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

Report:
```
Section 5: Regression Checks
PASS Dead-end retry counter increments
PASS No session lineage warnings
PASS Single retry chain (no parallel forks)
PASS Agent exits within 30s
PASS Pipeline executions: N (< 50 threshold)
PASS Stop hooks scoped to interactive only
PASS Idle detection accurate
PASS review_approved satisfies dependencies
```

**Red flags** (any of these means FAIL):
- Retry counter stuck at "1/10"
- "Lineage exceeded safety limit" in logs
- Pipeline executions > 50 for a 3-task epic
- Agent idle > 3 minutes before exit
- "stop hook error" in agent logs

### Section 6: Cleanup

1. Verify all tasks reached `review_approved` or `closed`
2. Clean up test files and worktrees
3. Report:
   ```
   Section 6: Cleanup
   PASS All subtasks review_approved or closed
   PASS Test files removed
   PASS Worktree cleaned up
   ```

### Section 7: Issue Tracking

Create gobby tasks for any issues discovered during the test:

```python
call_tool("gobby-tasks", "create_task", {
    "title": "Bug: <description>",
    "task_type": "bug",
    "category": "code",
    "description": "Found during orchestrator test battery: ...",
    "session_id": "<session_id>"
})
```

### Section 8: Final Report

Compile the full results:

```
=============================================
  Orchestrator Test Battery Results
=============================================

Section 1: Setup              [2/2 PASS]
Section 2: Expand-Task        [4/4 PASS]
Section 3: Dev-Loop            [8/8 PASS]
Section 4: Full Orchestrator  [3/3 PASS]
Section 5: Regression          [8/8 PASS]
Section 6: Cleanup            [2/2 PASS]

Total: 27/27 PASS

Pipeline Executions: N (target: < 50)
Agent Spawns: N
Bugs Found: N
  #<N> Bug: ...

Overall: PASS
=============================================
```

## Tips

- Use `gobby pipelines history <name>` to see the chain of event-driven passes
- Use `gobby pipelines status <id>` to check a specific pass and its outputs
- Use `gobby agents ps` to see running agents
- Use `gobby tasks list --parent <epic_id>` to check task states
- If an agent gets stuck, use `gobby agents kill <run_id>`
- Watch for retry spirals: `tail -f ~/.gobby/logs/gobby.log | grep -E "(dead.end|retry)"`
- The full battery typically takes 10-30 minutes depending on task complexity and LLM speed
- Run component tests first (Sections 2-3) to isolate failures before full integration
