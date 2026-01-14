# Plan: Worktree Agent Workflow Improvements

## Problem Statement

Testing revealed gaps in the worktree agent workflow:
1. Only terminal mode is useful for worktree spawning (embedded/headless don't integrate properly)
2. GEMINI.md lacks critical task workflow instructions
3. No mechanism for parent Claude to wait for worktree agent completion
4. No clear merge workflow back to dev
5. No support for autonomous review loops (Claude orchestrating Gemini agents)

## Target Workflow: Autonomous Review Loop

```
┌─────────────────────────────────────────────────────────────────┐
│  Claude (Orchestrator) - auto-task mode with session_task=epic │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
    ┌─────────────────┐
    │ 1. Create       │
    │    worktree     │
    └────────┬────────┘
             │
         ▼
    ┌─────────────────┐
    │ 2. Spawn Gemini │
    │    on task      │
    └────────┬────────┘
             │
         ▼
    ┌─────────────────┐
    │ 3. Wait for     │  ← BLOCKING WAIT (new tool)
    │    completion   │
    └────────┬────────┘
             │
         ▼
    ┌─────────────────┐
    │ 4. Review code  │  ← Read files from worktree path
    │    in worktree  │
    └────────┬────────┘
             │
         ▼
    ┌──────────────────────────────────────┐
    │ 5. Quality check                     │
    │    ├─ GOOD → merge to dev, close     │
    │    └─ BAD → reopen, fix, close       │
    └────────┬─────────────────────────────┘
             │
         ▼
    ┌─────────────────┐
    │ 6. Delete       │
    │    worktree     │
    └────────┬────────┘
             │
         ▼
    ┌─────────────────┐
    │ 7. Next task    │  ← Loop until epic exhausted
    │    in epic      │
    └─────────────────┘
```

## Design Decisions

### Task Status Flow

```
pending → in_progress → pending_review → completed
                 ↑              │
                 └──────────────┘  (reopen if review fails)
```

- Agent closes task → `pending_review` (work done, awaiting orchestrator review)
- Orchestrator approves → `completed`
- Orchestrator finds issues → reopen to `in_progress`, fix, close again

### Blocking Wait Mechanism

New tool: `wait_for_task(task_id, timeout_seconds=300)`
- Polls task status every 5 seconds
- Returns when task leaves `in_progress` (becomes `pending_review` or `completed`)
- Returns early if timeout exceeded
- Returns task data including commit_sha, worktree info

### Merge Target

All worktree branches merge to `dev` (not main). Main branch updated via normal PR flow.

### Auto-Cleanup

Worktrees auto-deleted after successful merge to keep environment clean.

### Worktree Agent Tool Restrictions

**Critical design principle**: Gemini (worktree agent) is sandboxed to ONE task. It cannot navigate the task tree, spawn agents, or manage worktrees.

**ALLOWED tools for worktree agent:**
```
# Task tools (minimal set)
gobby-tasks.get_task          # See assigned task details
gobby-tasks.update_task       # Set status to in_progress
gobby-tasks.close_task        # Signal completion with commit_sha

# Memory (optional)
gobby-memory.remember         # Store learnings
gobby-memory.recall           # Retrieve context

# All upstream MCP tools (context7, etc.)
# All native file/code tools (read, write, edit, bash, glob, grep)
```

**BLOCKED tools for worktree agent:**
```
# Task navigation (orchestrator's job)
gobby-tasks.list_tasks
gobby-tasks.list_ready_tasks
gobby-tasks.suggest_next_task
gobby-tasks.create_task
gobby-tasks.expand_task
gobby-tasks.expand_from_spec
gobby-tasks.validate_task_tree

# Agent/worktree management (orchestrator's job)
gobby-agents.*                # No spawning subagents
gobby-worktrees.*             # No managing worktrees
gobby-workflows.set_*         # No changing workflows

# Wait tools (orchestrator only)
gobby-tasks.wait_for_task
gobby-tasks.wait_for_any_task
gobby-tasks.wait_for_all_tasks
```

**Implementation**: Create `worktree-agent` workflow that auto-activates on spawn. Uses workflow tool filtering to enforce restrictions.

---

## Implementation Plan

### Phase 1: Simplify Worktree Spawning

**Goal**: Remove unused modes, standardize on terminal-only

**Files**: `src/gobby/mcp_proxy/tools/worktrees.py`

**Changes**:
- Remove `mode` parameter from `spawn_agent_in_worktree` (always terminal)
- Remove embedded/headless code paths (~100 lines)
- Keep terminal spawning logic, ensure it works with all supported terminals
- Update tool schema/docstring

### Phase 2: Fix Agent Completion Tracking

**Goal**: Close the loop when external terminal agents complete

**Files**:
- `src/gobby/hooks/event_handlers.py`
- `src/gobby/storage/agents.py`

**Changes**:
- In SESSION_END handler, detect agent-spawned sessions (`spawned_by_agent_id` set)
- Query linked agent_run, update status to "success"/"error"
- Set `completed_at` timestamp
- Kill the terminal process (from registry by run_id)
- Clean up from `RunningAgentRegistry`

### Phase 3: Add `pending_review` Task Status

**Goal**: Enable orchestrator-agent coordination

**Files**:
- `src/gobby/storage/tasks.py`
- `src/gobby/mcp_proxy/tools/tasks.py`
- `src/gobby/mcp_proxy/tools/task_sync.py`

**Changes**:
- Add "pending_review" to valid task statuses
- Add `pending_review_at` timestamp field
- Modify `close_task`:
  - Check if session is agent session (depth > 0)
  - If agent: status → "pending_review" instead of "completed"
  - Add `force_complete=False` param for edge cases
- Update JSONL sync to handle new status

### Phase 4: Add Blocking Wait Tool

**Goal**: Let orchestrator sleep efficiently while agent works

**Files**: `src/gobby/mcp_proxy/tools/tasks.py`

**New Tool**: `wait_for_task(task_id, timeout_seconds=300, poll_interval=5)`
```python
# Polls task status until it leaves in_progress
# Returns: task data with status, commit_sha, worktree_path
# Timeout: returns with current state + timed_out=True
```

**Alternative**: `wait_for_agent(run_id, timeout_seconds)` if we want agent-level granularity

### Phase 5: Enable & Enhance gobby-merge Server

**Goal**: Use existing gobby-merge infrastructure for worktree merges

**Context**: gobby-merge already exists with:
- `merge_start(worktree_id, source_branch, target_branch, strategy)`
- `merge_status(resolution_id)`
- `merge_resolve(conflict_id, resolved_content, use_ai)`
- `merge_apply(resolution_id)`
- `merge_abort(resolution_id)`

**Files**:
- `src/gobby/mcp_proxy/registries.py` - Ensure merge registry is always initialized
- `src/gobby/worktrees/merge.py` - Complete MergeResolver implementation (if missing)
- `src/gobby/mcp_proxy/tools/merge.py` - Add convenience tool

**Changes**:

1. **Ensure gobby-merge is always registered** (currently conditional on merge_storage/resolver)

2. **Complete MergeResolver if needed** - AI-powered conflict resolution with tiers:
   - `auto` - Try conflict-only, escalate to full-file if needed
   - `conflict_only` - Only resolve conflict markers
   - `full_file` - Regenerate entire files with AI

3. **Add convenience wrapper** `merge_to_dev(worktree_id)`:
   - Calls `merge_start(worktree_id, source_branch=worktree.branch, target_branch="dev")`
   - Auto-applies if no conflicts
   - Returns resolution_id and status

4. **Add cleanup integration** `approve_and_cleanup(task_id, worktree_id)`:
   - Verifies merge is complete
   - Transitions task from "pending_review" → "completed"
   - Deletes worktree and branch
   - Single tool for the happy path

### Phase 6: Add Reopen Task Capability

**Goal**: Support review-fail-fix cycle

**Files**: `src/gobby/mcp_proxy/tools/tasks.py`

**New Tool**: `reopen_task(task_id, reason=None)`
- Transitions from "pending_review" → "in_progress"
- Clears commit_sha (new work incoming)
- Logs reopen reason for debugging
- Allows orchestrator to fix and re-close

### Phase 7: Update GEMINI.md

**Goal**: Feature parity with CLAUDE.md + worktree agent instructions

**File**: `GEMINI.md`

**Add sections**:
- Task blocking workflow (in_progress before editing)
- Full close_task requirements (commit_sha mandatory)
- Commit message format: `[task-id] type: description`
- No commit trailer rule
- Internal servers reference table

**Key instruction for worktree agents**:
```markdown
## Worktree Agent Mode

When spawned in a worktree by an orchestrator (Claude):

**Your scope is LIMITED to one task.** You cannot create tasks, expand epics,
spawn agents, or manage worktrees. Focus on the assigned task only.

### Available Tools
- `get_task(task_id)` - View your assigned task details
- `update_task(task_id, status="in_progress")` - Mark task active
- `close_task(task_id, commit_sha)` - Signal completion
- All file/code tools and upstream MCP servers

### Workflow
1. `get_task(<your-task-id>)` - understand the requirement
2. `update_task(status="in_progress")` - BEFORE any edits
3. Do the work, commit with `[task-id]` prefix
4. `close_task(commit_sha="<sha>")` - signals orchestrator you're done
5. Session ends, orchestrator reviews your work

### You CANNOT
- Create, expand, or navigate tasks
- Spawn subagents or manage worktrees
- Pick your next task (orchestrator decides)
```

### Phase 8: Add Worktree Agent Workflow

**Goal**: Enforce tool restrictions for spawned agents

**Files**:
- `src/gobby/workflows/definitions/worktree_agent.yaml`
- `src/gobby/mcp_proxy/tools/worktrees.py` (auto-activate on spawn)

**New workflow**:
```yaml
name: worktree-agent
description: Restricted workflow for agents working in worktrees
auto_activate_on: worktree_spawn

tool_allowlist:
  gobby-tasks:
    - get_task
    - update_task
    - close_task
  gobby-memory:
    - remember
    - recall
    - forget
  # All other gobby-* servers blocked by default

# Allow all upstream MCP servers
upstream_servers: allow_all

steps:
  - name: work
    description: Execute the assigned task
    # No step transitions - single continuous work phase
```

**Changes to spawn_agent_in_worktree**:
- Auto-set `workflow="worktree-agent"` if not specified
- Pass task_id via environment or prompt injection
- Workflow activates on session start hook

### Phase 9: Add Parallel Wait Tools

**Goal**: Support parallel worktree orchestration

**Files**: `src/gobby/mcp_proxy/tools/tasks.py`

**New Tools**:

1. `wait_for_any_task(task_ids, timeout_seconds=300)`
   - Polls multiple tasks
   - Returns when ANY task leaves `in_progress`
   - Returns: completed task data + remaining task_ids still in progress

2. `wait_for_all_tasks(task_ids, timeout_seconds=600)`
   - Polls multiple tasks
   - Returns when ALL tasks leave `in_progress` (or timeout)
   - Returns: list of task data with their statuses

### Phase 10: Add Orchestration Workflows

**Goal**: Formalize sequential and parallel patterns as workflows

**Files**:
- `src/gobby/workflows/definitions/sequential_orchestrator.yaml`
- `src/gobby/workflows/definitions/parallel_orchestrator.yaml`

**Sequential Orchestrator Workflow**:
```yaml
name: sequential-orchestrator
description: Process epic subtasks one at a time with worktree agents
steps:
  - name: select_task
    allowed_tools: [list_ready_tasks, suggest_next_task, get_task]
  - name: spawn_agent
    allowed_tools: [create_worktree, spawn_agent_in_worktree]
  - name: wait
    allowed_tools: [wait_for_task]
  - name: review
    allowed_tools: [read, glob, grep, get_worktree_status]
  - name: decide
    allowed_tools: [merge_worktree, approve_and_cleanup, reopen_task, close_task]
  - name: loop
    transitions:
      - condition: "has_ready_tasks"
        next: select_task
      - condition: "no_ready_tasks"
        next: complete
```

**Parallel Orchestrator Workflow**:
```yaml
name: parallel-orchestrator
description: Process multiple subtasks in parallel worktrees
config:
  max_parallel_worktrees: 3
steps:
  - name: select_batch
    allowed_tools: [list_ready_tasks, get_task]
  - name: spawn_batch
    allowed_tools: [create_worktree, spawn_agent_in_worktree]
    # Called N times for N tasks
  - name: wait_any
    allowed_tools: [wait_for_any_task, wait_for_all_tasks]
  - name: review_completed
    allowed_tools: [read, glob, grep, get_worktree_status]
  - name: process_completed
    allowed_tools: [merge_worktree, approve_and_cleanup, reopen_task]
  - name: loop
    transitions:
      - condition: "agents_still_running"
        next: wait_any
      - condition: "has_ready_tasks"
        next: select_batch
      - condition: "all_done"
        next: complete
```

### Phase 11: Create gobby-merge Skill

**Goal**: Create skill file for AI-powered merge conflict resolution

**Files**:
- `src/gobby/install/claude/commands/gobby-merge.md` (install template)
- `.claude/commands/gobby-merge.md` (project-local copy)

**Content structure** (following gobby-tasks.md pattern):
```markdown
---
description: This skill should be used when the user asks to "/gobby-merge",
"merge worktree", "resolve conflicts", "merge to dev". Manage AI-powered
merge conflict resolution - start merges, resolve conflicts, apply resolutions.
version: "1.0"
---

# /gobby-merge - Merge Conflict Resolution Skill

## Core Subcommands

### `/gobby-merge start <worktree-id>` - Start merge operation
Call `gobby-merge.merge_start` with:
- `worktree_id`: (required) Worktree to merge
- `source_branch`: Branch being merged (auto-detected from worktree)
- `target_branch`: Target branch (default: "dev")
- `strategy`: "auto", "conflict_only", "full_file", "manual"

### `/gobby-merge status <resolution-id>` - Get merge status
Call `gobby-merge.merge_status` with:
- `resolution_id`: (required) Resolution ID from merge_start

### `/gobby-merge resolve <conflict-id>` - Resolve conflict
Call `gobby-merge.merge_resolve` with:
- `conflict_id`: (required) Conflict to resolve
- `resolved_content`: Manual resolution (skips AI)
- `use_ai`: Use AI resolution (default: true)

### `/gobby-merge apply <resolution-id>` - Apply and complete
Call `gobby-merge.merge_apply` with:
- `resolution_id`: (required) Resolution to apply

### `/gobby-merge abort <resolution-id>` - Abort merge
Call `gobby-merge.merge_abort` with:
- `resolution_id`: (required) Resolution to abort

## Resolution Tiers
1. **git_auto** - Git handles it (no conflicts)
2. **conflict_only_ai** - Send only conflict hunks to LLM
3. **full_file_ai** - Send full file for complex conflicts
4. **human_review** - Escalate to human

## Workflow Example
1. `merge_start(worktree_id)` - Start merge, get resolution_id
2. If conflicts: `merge_status(resolution_id)` - See conflicts
3. For each conflict: `merge_resolve(conflict_id)` - AI or manual
4. `merge_apply(resolution_id)` - Complete merge
```

### Phase 12: Update CLAUDE.md with Both Patterns

**Goal**: Document orchestrator workflows

**File**: `CLAUDE.md`

**Add section**:
```markdown
## Autonomous Task Orchestration

### Sequential Pattern (One at a time)

Best for: dependent tasks, limited resources, simpler review

1. Set `session_task` to epic ID, activate `sequential-orchestrator` workflow
2. Loop:
   a. `suggest_next_task()` → get ready subtask
   b. `create_worktree(branch=f"feature/{task_id}")`
   c. `spawn_agent_in_worktree(task_id, provider="gemini")`
   d. `wait_for_task(task_id, timeout=600)`
   e. Review code at worktree_path
   f. If good: `merge_worktree()` → `approve_and_cleanup()`
   g. If bad: `reopen_task()`, fix in worktree, `close_task()`
3. Repeat until no ready tasks

### Parallel Pattern (Multiple simultaneous)

Best for: independent tasks, faster throughput, available resources

1. Set `session_task` to epic ID, activate `parallel-orchestrator` workflow
2. Spawn phase:
   a. `list_ready_tasks()` → get up to N independent tasks
   b. For each: `create_worktree()` + `spawn_agent_in_worktree()`
   c. Track: {task_id: worktree_id} mapping
3. Wait phase:
   a. `wait_for_any_task(task_ids)` → returns first completed
   b. Review completed task's worktree
   c. Merge/approve or reopen/fix
   d. If agents still running: goto 3a
4. Refill phase:
   a. If ready tasks remain and slots available: spawn more
   b. Goto wait phase
5. Complete when all tasks done
```

---

## File Summary

| File | Changes |
|------|---------|
| `src/gobby/mcp_proxy/tools/worktrees.py` | Remove modes, auto-activate worktree-agent workflow |
| `src/gobby/mcp_proxy/tools/tasks.py` | pending_review, wait_for_task, wait_for_any_task, wait_for_all_tasks, reopen_task, approve_and_cleanup |
| `src/gobby/mcp_proxy/tools/task_sync.py` | Handle pending_review in JSONL |
| `src/gobby/mcp_proxy/tools/merge.py` | Add merge_to_dev convenience wrapper |
| `src/gobby/mcp_proxy/registries.py` | Ensure gobby-merge always initialized |
| `src/gobby/storage/tasks.py` | pending_review status + timestamp |
| `src/gobby/hooks/event_handlers.py` | Update agent_runs on SESSION_END |
| `src/gobby/worktrees/merge.py` | Complete MergeResolver implementation (if needed) |
| `src/gobby/workflows/definitions/worktree_agent.yaml` | New workflow - tool restrictions for spawned agents |
| `src/gobby/workflows/definitions/sequential_orchestrator.yaml` | New workflow - one task at a time |
| `src/gobby/workflows/definitions/parallel_orchestrator.yaml` | New workflow - multiple concurrent worktrees |
| `GEMINI.md` | Full task workflow + worktree agent mode docs |
| `CLAUDE.md` | Sequential + parallel orchestrator docs |
| `src/gobby/install/claude/commands/gobby-merge.md` | New skill for merge conflict resolution (install template) |
| `.claude/commands/gobby-merge.md` | New skill for merge conflict resolution (project-local) |

---

## Verification

### Unit Tests
- `close_task` → `pending_review` when session.agent_depth > 0
- `wait_for_task` returns on status change or timeout
- `wait_for_any_task` returns when first task completes
- `wait_for_all_tasks` returns when all tasks complete
- `merge_worktree` performs git merge correctly
- `reopen_task` transitions status back
- SESSION_END handler updates agent_runs

### Integration Test: Sequential Workflow
```bash
# 1. Create epic with subtasks
gobby tasks create "Epic" --type=epic
gobby tasks expand <epic-id>

# 2. Activate sequential workflow
gobby workflows set sequential-orchestrator

# 3. Run orchestration loop manually
gobby tasks suggest-next
gobby worktrees create feature/task-1
gobby worktrees spawn feature/task-1 --task=<task-id> --provider=gemini

# 4. Wait for Gemini to complete, then verify
gobby tasks list --status=pending_review

# 5. Merge using gobby-merge
# Via MCP: merge_start(worktree_id, source_branch, target_branch="dev")
# Or convenience: merge_to_dev(worktree_id)

# 6. Approve and cleanup
# Via MCP: approve_and_cleanup(task_id, worktree_id)
```

### Integration Test: Parallel Workflow
```bash
# 1. Create epic with 3 independent subtasks
gobby tasks create "Parallel Epic" --type=epic
# ... add subtasks

# 2. Spawn multiple agents
gobby worktrees spawn feature/task-1 --task=<task-1> --provider=gemini
gobby worktrees spawn feature/task-2 --task=<task-2> --provider=gemini

# 3. Wait for any to complete
# (via MCP tool: wait_for_any_task)

# 4. Process completed, spawn more if ready tasks remain
```

### End-to-End Test: Full Sequential Loop
1. Create epic with 2 subtasks
2. Claude activates `sequential-orchestrator` workflow
3. Spawns Gemini for subtask 1, waits, reviews, merges
4. Spawns Gemini for subtask 2, waits, reviews, merges
5. Epic marked complete when all subtasks done

### End-to-End Test: Full Parallel Loop
1. Create epic with 4 independent subtasks
2. Claude activates `parallel-orchestrator` workflow
3. Spawns Gemini in 2 worktrees (max_parallel=2)
4. As each completes: review, merge, spawn next
5. All 4 tasks processed with max 2 concurrent agents
