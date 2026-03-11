# Orchestrator Test Battery

Autonomous test battery for the orchestrator pipeline. Invoke via `/gobby test-battery`.

The test battery sets up a cron-driven orchestrator pipeline on a clone, monitors agent progress continuously, and intervenes on infrastructure failures until the epic completes. State persists in `test-battery.md` at the project root, surviving context compaction.

**Reference:** The 2026-03-07 smoke test (`orchestrator-smoke-test.md`) ran the full orchestrator on a 10-task epic. It exposed 6 bugs (all fixed) and drove the regression checks below.

---

## Quick Start

```bash
# Start the test battery
/gobby test-battery

# The wizard will ask 9 questions:
# 1. Reset environment?
# 2. Commit changes?
# 3. Target epic (#N or 'new')
# 4. Expansion strategy (run now / plan file / skip)
# 5. Dev provider/model (default: gemini)
# 6. QA provider/model (default: claude/opus)
# 7. Agent timeout (default: 1200s)
# 8. Cron interval (default: 5m)
# 9. Confirm and go
```

After setup, the monitoring loop runs autonomously. It:
- Polls cron runs every 30s
- Inspects each orchestrator tick
- Checks task states and agent health
- Intervenes on infrastructure failures (pause cron, fix, restart, resume)
- Stops when the epic completes

---

## Prerequisites

- Gobby daemon running (`gobby status`)
- At least one LLM provider configured
- Git repository with clean working tree (skill will prompt to commit if dirty)
- No other orchestrator pipelines running (skill can reset environment)

---

## How It Works

### Architecture

```
┌─────────────────────────────────────────────┐
│  Monitoring Agent (this session)            │
│  ┌───────────────────────────────────────┐  │
│  │  Phase 3: Monitoring Loop             │  │
│  │  - Poll cron runs                     │  │
│  │  - Inspect tick results               │  │
│  │  - Check task/agent health            │  │
│  │  - Intervene on failures              │  │
│  │  - Update test-battery.md             │  │
│  └───────────────────────────────────────┘  │
└──────────────────┬──────────────────────────┘
                   │ polls
                   ▼
┌─────────────────────────────────────────────┐
│  Cron Job (interval: Ns)                    │
│  → Triggers orchestrator pipeline each tick │
└──────────────────┬──────────────────────────┘
                   │ executes
                   ▼
┌─────────────────────────────────────────────┐
│  Orchestrator Pipeline (one tick)           │
│  1. Re-entrancy guard                       │
│  2. Scan task states                        │
│  3. Create/reuse clone                      │
│  4. Dispatch dev agents (up to max_concurrent)│
│  5. Dispatch QA agent (for needs_review)    │
│  6. Merge on completion                     │
└──────────────────┬──────────────────────────┘
                   │ spawns
                   ▼
┌─────────────────────────────────────────────┐
│  Agents (in shared clone)                   │
│  - Developer agents (parallel, per task)    │
│  - QA reviewer (sequential, per task)       │
└─────────────────────────────────────────────┘
```

### State Persistence

All state lives in `test-battery.md` at the project root. This file survives context compaction. The monitoring loop reads it on every re-entry (Phase 0) to recover:

- Epic ID and ref
- Cron job ID
- Monitoring task ID
- Current cycle number
- Agent configuration
- Task status counts
- Issues found and fixes applied

### Clone Lifecycle

The orchestrator pipeline handles clone creation automatically:
1. First tick: `create_clone` with branch `epic-<N>`, linked to the epic task
2. Subsequent ticks: `get_clone_by_task` to reuse the existing clone
3. All agents share the same clone (parallel work in shared directory)
4. On completion: `merge-clone` pipeline attempts merge to target branch

---

## Intervention Protocol

When infrastructure/orchestration bugs are detected (not agent-level code failures):

1. **Pause** — Disable the cron job
2. **Kill** — Stop running agents and orphaned tmux sessions
3. **Fix** — Edit code in main worktree, run targeted tests
4. **Commit** — Commit the fix
5. **Reset** — Reopen tasks stuck in `in_progress` from killed agents
6. **Restart** — `gobby restart`
7. **Resume** — Re-enable cron job
8. **Log** — Record issue and fix in test-battery.md

### What to Fix vs Ignore

| Fix (infrastructure) | Ignore (normal operation) |
|----------------------|--------------------------|
| Pipeline step errors | Agent producing bad code |
| Clone/git failures | QA rejecting work |
| Agent spawn failures | Agent timeout on hard task |
| Daemon crashes | Test failures in agent work |
| Task state bugs | |

---

## Regression Checks

Watch for these known issues during monitoring:

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

**Red flags:**
- Retry counter stuck at "1/10"
- "Lineage exceeded safety limit" in logs
- Pipeline executions > 50
- Agent idle > 3 minutes before exit

---

## Monitoring Commands

```bash
# Pipeline history
gobby pipelines history orchestrator

# Execution details
gobby pipelines status <execution_id>

# Running agents
gobby agents ps

# Task states
gobby tasks list --parent <epic_id>

# Watch for issues
tail -f ~/.gobby/logs/gobby.log | grep -E "(ERROR|dead.end|lineage|retry)"

# Tmux agent sessions
tmux -L gobby list-sessions

# Cron status
gobby cron list
gobby cron runs <job_id>
```

---

## Resuming After Compaction

Context compaction is expected during long monitoring runs. When the skill is re-invoked (or the agent recovers), Phase 0 reads `test-battery.md` and resumes the monitoring loop from the last recorded cycle. No manual intervention needed.

If the daemon was restarted during compaction, verify it's running (`gobby status`) before resuming.
