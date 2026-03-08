# Orchestrator Smoke Test Report

**Date:** 2026-03-07
**Branch:** `0.2.28` / worktree `epic-9915`
**Epic:** #9915 — OpenTelemetry Full Observability Stack (10 subtasks)
**Pipeline:** `dev-loop` (event-driven dev/QA/merge loop)
**Worktree:** `/private/tmp/gobby-worktrees/gobby/epic-9915` (wt-a0ad15)

---

## Executive Summary

The orchestrator **partially works**. It successfully expands tasks, dispatches developer agents, detects idle agents, reprompts them, fails stuck ones, recovers tasks, and re-dispatches. 6 of 10 subtasks reached `review_approved` through autonomous QA. But the system cannot complete an end-to-end cycle without human intervention due to cascading failures in the dead-end retry mechanism, agent exit behavior, and session lineage management.

**Verdict: Not ready for fire-and-forget.** Requires fixes to 6 identified bugs before the next stress test.

---

## Task Progress

| Ref | Title | Status | Notes |
|-----|-------|--------|-------|
| #9916 | OTel dependencies + telemetry core | review_approved | Completed by agent, QA passed |
| #9917 | Logging migration: OTel bridge | review_approved | Self-recovered from stuck in_progress |
| #9918 | Metrics + TelemetryMiddleware | review_approved | Completed by agent, QA passed |
| #9919 | ToolMetricsManager dual-write | review_approved | Completed by agent, QA passed |
| #9920 | Route metrics migration | in_progress | Agent idle at prompt, 20 files uncommitted (-326 lines) |
| #9921 | Tracing: @traced decorator | in_progress | Agent idle at prompt, pre-commit hook failure |
| #9922 | Instrument key flows | open | Blocked by #9920, #9921 |
| #9923 | Span storage + trace API | open | Blocked by #9921 |
| #9924 | Trace viewer UI | open | Blocked by #9923 |
| #9925 | Config consolidation + cleanup | open | Blocked by all above |

**Score: 6/10 tasks QA-approved, 0/10 closed, 0/10 merged.**

---

## Agent Activity

| Metric | Value |
|--------|-------|
| Unique agent runs (run IDs) | 5 |
| Agent starts logged | 4 (this session) |
| Agent completions logged | 2 |
| Agent failures (idle timeout) | 1 (run-9f2434b02d4e, task #9920) |
| Task recoveries (failed agent -> reopen) | 1 (#9920 recovered to open, re-dispatched) |
| Reprompts sent | 6 |
| Currently running agents | 2 (both idle at prompt) |
| Active tmux sessions | 2 |

### Agent Lifecycle Timeline

```
17:23:37  run-1754b9381218 completed (19 tool calls, 34 turns) — prior session agent
17:23:38  run-afe5b2d76d4e completed (0 tool calls, 0 turns) — orphan cleanup
17:23:45  run-dd0ed83e5cb3 started -> #9921 (Tracing)
17:23:46  run-9f2434b02d4e started -> #9920 (Route metrics)
17:24:52  Both agents reprompted (idle at prompt)
17:25:52  run-9f2434b02d4e reprompted again (2/3)
17:26:52  run-9f2434b02d4e reprompted again (3/3)
17:27:22  run-9f2434b02d4e FAILED after 3 reprompts — task #9920 recovered to open
17:27:24  run-b044db2d2cac started -> #9920 (re-dispatched)
17:28:54  run-b044db2d2cac reprompted (idle)
          ... both agents still running, idle at prompt as of report time
```

### What Agents Actually Did

**run-dd0ed83e5cb3 (#9921 — Tracing):**
- Attempted to commit tracing code but hit pre-commit hook failure (ruff lint errors)
- Got reprompted, sitting at prompt
- Has uncommitted changes (+6, -14)

**run-b044db2d2cac (#9920 — Route metrics):**
- Working on removing manual counter calls from route files
- Hit "File must be read first" and "Error editing file" errors from Claude Code
- Got reprompted, sitting at prompt
- Has substantial uncommitted changes (20 files, +55, -326 lines)

### Code Quality of Agent Output

- Agents produced real, meaningful code (OTel dependencies, telemetry module, test suites)
- Agent code passed pre-commit hooks (ruff, formatting) on successful commits
- #9921 failed pre-commit (lint errors in context.py) — agent didn't recover
- #9920 has 20 files of uncommitted route migration work — substantial but stuck
- QA agents correctly reviewed and approved 6 tasks autonomously

---

## Pipeline Execution

| Metric | Value |
|--------|-------|
| Unique pipeline executions | 371 |
| Dead-end retries logged | 361 |
| Lineage exceeded warnings | 365 |
| Dead-end retry counter value | Always 1/10 (never increments) |
| Parallel retry chains observed | 2+ simultaneously |
| Pipeline execution efficiency | 2.7% (10 useful / 371 total) |

### What Happened

1. Pipeline dispatched agents successfully in early iterations
2. Agent completions fired continuations correctly (event-driven re-invocation worked)
3. When agents got stuck idle, pipeline entered dead-end state (no agents dispatched, not complete)
4. Dead-end retry mechanism activated but **never incremented its counter** (bug #9937)
5. Each retry created a child session of the previous retry's child session (bug #9938)
6. Multiple agent completions fired simultaneously, creating **parallel retry chains** (bug #9939)
7. Result: 371 pipeline executions, 361 dead-end retries, 365 lineage warnings — all saying "1/10"

### The Retry Spiral

```
Agent completes -> continuation fires -> pipeline runs -> no ready tasks -> dead-end retry
                                                                              |
                                                        10s later -> new pipeline -> same state -> retry
                                                                                                    |
Another agent completes -> SECOND continuation fires -> SECOND parallel chain starts
                                                                              |
                                                        Both chains retry independently forever
```

Each retry creates a child session, so session depth grows unboundedly. The counter never increments because `_dead_end_retries` isn't passed through the YAML inputs.

---

## Bugs Filed

| Ref | Title | Priority | Root Cause |
|-----|-------|----------|------------|
| #9935 | TaskOutput retrieval_status: success for failed commands | P2 | Misleading status field |
| #9937 | Dead-end retry counter never increments | P1 | `_dead_end_retries` missing from YAML inputs passthrough |
| #9938 | Dead-end retry creates infinite session lineage | P1 | Child-of-child session chaining |
| #9939 | Multiple parallel dead-end retry chains | P1 | No deduplication on continuation-triggered re-invocations |
| #9940 | Agents don't call kill_agent — stop hooks block exit | P2 | Stop hooks fire before agent can exit cleanly |
| #9941 | Agents stuck in pending after daemon restart | P2 | Session start hook never fires for pre-existing agents |

### Previously Fixed (This Test Cycle)

| Ref | Title | Commit |
|-----|-------|--------|
| #9934 | Event loop error in agent completion callbacks | `7960ab37` |
| #9936 | Stop hook errors make agents invisible to idle detector | `d20666c9` |
| #9933 | review_approved not treated as dependency-satisfied | `9ad2c894` |
| #9932 | Idle detector can't see through status bar | `7c47eedd` |
| #9931 | Agent idle detection + worktree code isolation | `acf741bc` |
| #9930 | Auto-claim only claims open tasks | `370b5afa` |
| #9928 | Accept 'args' alias in call_tool | `5aa291c6` |
| #9926/27 | Auto-claim on spawn + string truthiness | `4eb33e4a` |

---

## What's Working

1. **Task expansion** — Epic decomposed into 10 well-scoped subtasks with correct dependency chains
2. **Agent dispatching** — Pipeline reads task states, finds ready tasks, spawns agents with correct worktree/provider config
3. **Idle detection** — Lifecycle monitor correctly identifies idle agents through status bar noise and stop hook errors
4. **Reprompt cycle** — 3 reprompts with 60s intervals, then fail. Works reliably.
5. **Task recovery** — Failed agents trigger task recovery (in_progress -> open), enabling re-dispatch
6. **Event-driven continuation** — Agent completion events fire and trigger pipeline re-invocation
7. **Dependency-aware dispatch** — `suggest_next_tasks` respects dependency chains, only dispatches unblocked tasks
8. **QA pipeline** — QA agents review code and approve/reject tasks (6 approved this run)
9. **Pre-commit enforcement** — Hooks run in worktree, catch lint errors before bad code gets committed

## What's Not Working

1. **Dead-end retry is catastrophically broken** — Counter doesn't increment, sessions chain infinitely deep, parallel chains fork. This is the #1 issue.
2. **Agents can't exit cleanly** — Stop hooks trap agents in a loop. They sit idle for 3+ minutes until lifecycle monitor kills them. Wastes time and compute.
3. **Agents don't recover from errors** — When pre-commit fails or file edits error, agents stop trying and sit at the prompt instead of retrying.
4. **Merge phase never triggers** — Merge requires ALL tasks review_approved with zero open/in_progress. Since agents keep getting stuck, we never reach that state.
5. **No agent timeout** — Agents run indefinitely. No hard timeout to kill agents consuming context without producing results.
6. **Uncommitted work is lost on failure** — When an agent fails idle, its uncommitted changes stay in the worktree but the next agent may conflict with them.

---

## The Happy Path

### Goal

Run `dev-loop` pipeline on an epic, walk away, come back to a merged PR. No babysitting.

### Current Reality

Run pipeline, watch agents get stuck at prompts, watch dead-end retries spiral, manually kill agents, manually reset tasks, re-run.

### What Needs to Change (Priority Order)

#### 1. Fix Dead-End Retry (Bugs #9937, #9938, #9939) — CRITICAL

**#9937 (counter):** Add `_dead_end_retries` to `dev-loop.yaml` inputs passthrough (line 232). One-line fix.

**#9938 (lineage):** In `_pipelines.py`, dead-end retry should pass the ROOT session_id, not chain through child sessions. Add `_root_session_id` to inputs and propagate it.

**#9939 (deduplication):** Add a per-epic lock or timestamp to prevent multiple continuations from spawning parallel retry chains. Options:
- Session variable `_last_retry_scheduled_at` — skip if within 30s
- asyncio.Lock keyed by `session_task`
- Single-writer: only first continuation to arrive schedules a retry

#### 2. Fix Agent Exit (Bug #9940) — HIGH

Two options:

**Option A (preferred):** Disable gobby stop hooks for agent sessions. Agent sessions are identifiable by `agent_run_id`. Hook dispatcher can check and skip enforcement.

**Option B:** Agent definitions include explicit `kill_agent` in their completion flow before natural exit triggers stop hooks.

#### 3. Add Agent Hard Timeout — MEDIUM

30 min max runtime per agent. Lifecycle monitor already has infrastructure — add timeout check alongside idle check. Kill process, recover task, move on.

#### 4. Handle Uncommitted Work on Agent Failure — MEDIUM

Options:
- `git stash` before re-dispatching (preserves work)
- `git checkout -- .` to reset (loses work but ensures clean state)
- New agent gets a note about existing uncommitted changes

#### 5. Improve Agent Error Recovery — LOW (prompt engineering)

Agent instructions should handle:
- Pre-commit hook failures: read error output, fix lint, retry commit
- "File must be read first": read the file, then retry edit
- Context window pressure: commit partial work, close task with partial note

### The Ideal Flow

```
User: gobby pipelines run orchestrator --inputs '{"session_task": "#9915"}'

  1. expand-task decomposes epic -> 10 subtasks with deps
  2. create_worktree -> isolated branch
  3. dev-loop starts:
     a. Scan task states
     b. Dispatch dev agents to ready tasks (parallel, file-conflict-aware)
     c. Register continuations on agent run IDs
     d. EXIT (pipeline completes, daemon is idle)
  4. Agent completes -> hook fires -> continuation invokes dev-loop
  5. dev-loop scans -> dispatches QA for needs_review tasks
  6. QA approves -> continuation -> dev-loop dispatches more devs
  7. All tasks review_approved -> dev-loop triggers merge agent
  8. Merge agent: merge worktree branch, close tasks, delete worktree
  9. Done. PR ready for human review.

Dead-end handling:
  - No agents dispatched + not complete -> retry with backoff (10s..5min cap)
  - Counter increments, caps at 10
  - Single retry chain per epic (deduped)
  - After 10 retries: escalate task, stop pipeline

Agent lifecycle:
  - Hard timeout: 30 min per agent
  - Idle detection: 60s -> reprompt, 3 reprompts -> fail
  - Clean exit: agent calls kill_agent, no stop hook interference
  - Task recovery: failed agent -> task reopened -> re-dispatchable
```

### Success Criteria for Next Run

- [ ] Dead-end retry counter increments (2/10, 3/10, etc.)
- [ ] No "Lineage exceeded safety limit" warnings
- [ ] No parallel retry chains (single chain per epic)
- [ ] Agents exit within 30s of completing work (no 3-min idle wait)
- [ ] All 10 tasks reach review_approved without manual intervention
- [ ] Merge agent fires and produces mergeable branch
- [ ] Total pipeline executions < 50 (not 371)
- [ ] Zero human interventions required

---

## Raw Numbers

| Metric | Value |
|--------|-------|
| Total pipeline executions | 371 |
| Useful pipeline executions | ~10 |
| Wasted pipeline executions | ~361 (dead-end retries) |
| Pipeline execution efficiency | 2.7% |
| Agent spawns | 5 |
| Agent completions | 2 |
| Agent failures (idle timeout) | 1 |
| Agents still running (stuck) | 2 |
| Tasks completed (closed) | 0 |
| Tasks QA-approved | 6 |
| Tasks in progress | 2 |
| Tasks open (blocked) | 4 |
| Commits in worktree (meaningful) | 14 |
| Commits in worktree (merge/style) | 11 |
| Uncommitted changes | 20 files (+55, -326 lines) |
| Daemon restarts | 0 |
| Bugs found and filed | 6 |
| Bugs fixed during test | 8 |
| Lineage depth warnings | 365 |
| Reprompts sent | 6 |
