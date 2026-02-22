# Orchestrator Refactor: Options

## Current State

### What the orchestrator does

The orchestrator (`orchestrator.yaml`) is a pipeline-type workflow that processes a task queue by spawning developer, QA, and merge agents in sequence. Its 14 steps do five distinct things:

| Concern | Steps | Tools Used |
|---------|-------|------------|
| Task queue consumption | `find_work`, `check_more_work`, `close_task` | `gobby-tasks:suggest_next_task`, `gobby-tasks:close_task` |
| Clone lifecycle | `create_clone`, `cleanup_clone` | `gobby-clones:create_clone`, `gobby-clones:delete_clone` |
| Agent dispatching | `spawn_developer`, `spawn_qa`, `spawn_merge` | `gobby-agents:spawn_agent` (×3) |
| Synchronization | `wait_developer`, `wait_qa`, `wait_merge` | `gobby-agents:wait_for_agent` (×3) |
| Loop control | `check_limit`, `next_iteration` | `invoke_pipeline` (self-recursive) |

### What's wrong

**1. Self-recursive pipeline.** The orchestrator calls `invoke_pipeline: orchestrator` to loop, passing `_current_iteration` as a parameter. Pipelines are designed for linear execution. This simulates a loop in a system that doesn't have one.

**2. Scattered task state.** Three different agents touch the same task's lifecycle:
- Developer marks `needs_review` (developer.yaml, commit step)
- QA marks `review_approved` (qa-reviewer.yaml, approve step)
- Orchestrator calls `close_task` (orchestrator.yaml, close_task step)

No single owner. If any agent fails mid-lifecycle, the task is left in an ambiguous state.

**3. Sequential-only execution.** The orchestrator spawns one developer, waits, spawns one QA, waits, spawns one merge, waits. There's no parallelism — it can only process one task at a time per loop iteration. The orchestration tools were specifically built for parallel dispatch.

**4. Clone lifecycle coupled to task discovery.** The clone is created after `find_work` but before `spawn_developer`, tying infrastructure setup to task resolution. The clone API shouldn't need to know about task state, and the orchestrator shouldn't need to manage clone IDs.

**5. Iteration control via inputs.** `_current_iteration` is passed through inputs and checked via a conditional `exec` that exits 1. This is control flow logic that belongs in the executor, not in step definitions.

### The unused orchestration suite

Meanwhile, `gobby-orchestration` exposes 11 tools (3,051 lines, well-tested) that address exactly these concerns:

| Tool | What it does | Orchestrator equivalent |
|------|-------------|----------------------|
| `orchestrate_ready_tasks` | Find ready subtasks, create worktrees, spawn agents in parallel | `find_work` + `create_clone` + `spawn_*` (but parallel) |
| `poll_agent_status` | Check running agents, move to completed/failed | `wait_*` steps (but non-blocking) |
| `get_orchestration_status` | Status dashboard for a parent task | No equivalent |
| `process_completed_agents` | Route completed work to review or cleanup | No equivalent |
| `spawn_review_agent` | Spawn a review agent for a completed task | Partially `spawn_qa` |
| `cleanup_reviewed_worktrees` | Merge branches, delete worktrees | `cleanup_clone` (but with merge) |
| `approve_and_cleanup` | Close task + delete worktree | `close_task` + `cleanup_clone` |
| `cleanup_stale_worktrees` | Clean up abandoned worktrees | No equivalent |
| `wait_for_task` | Block until task completes | `wait_*` steps |
| `wait_for_any_task` | Block until any of N tasks complete | No equivalent |
| `wait_for_all_tasks` | Block until all tasks complete | No equivalent |

The orchestration tools also handle concurrency limits (atomic slot reservation), dry-run mode, retry logic, and failure escalation — none of which the coordinator has.

---

## Option A: Refactor coordinator to delegate to orchestration tools

Replace the coordinator's inline steps with calls to the orchestration tools. The coordinator becomes a thin loop that calls `orchestrate_ready_tasks` → `poll_agent_status` → `process_completed_agents` → `cleanup_reviewed_worktrees`.

### What changes

```yaml
# Coordinator becomes ~5 steps instead of 14:
steps:
  - id: dispatch
    mcp: { server: gobby-orchestration, tool: orchestrate_ready_tasks, ... }
  - id: monitor
    mcp: { server: gobby-orchestration, tool: poll_agent_status, ... }
  - id: process
    mcp: { server: gobby-orchestration, tool: process_completed_agents, ... }
  - id: cleanup
    mcp: { server: gobby-orchestration, tool: cleanup_reviewed_worktrees, ... }
  - id: next
    invoke_pipeline: coordinator  # still self-recursive (problem remains)
```

### Pros
- Minimal disruption — coordinator still exists, just delegates
- Gains parallelism, retry logic, concurrency limits from orchestration tools
- Developer/QA/merge workflows unchanged
- Orchestration tools finally get used

### Cons
- Self-recursive loop problem remains unless pipeline system gets native loops
- Coordinator is still a "thing" even though it's now just 5 MCP calls
- Two layers of abstraction: pipeline steps wrapping orchestration tools wrapping spawn_agent
- The coordinator agent definition (agent YAML) still exists for a pipeline that barely needs an LLM

---

## Option B: Kill the coordinator, promote orchestration tools

Remove the coordinator entirely. Multi-agent orchestration is done by calling orchestration tools directly — either from a human session, a skill, or a parent agent.

### What changes

- Delete `coordinator.yaml` and `coordinator.yaml` agent definition
- The user (or a skill like `/orchestrate`) calls `orchestrate_ready_tasks` with a parent task ID
- Monitoring is done via `get_orchestration_status` or `poll_agent_status`
- Cleanup is done via `cleanup_reviewed_worktrees` or `approve_and_cleanup`
- No pipeline, no loop — the user drives the lifecycle or a cron job polls

### Pros
- Simplest architecture — orchestration tools are the interface, no wrapper
- No pipeline recursion hack
- Human-in-the-loop by default (user calls tools when ready)
- Orchestration tools already handle everything the coordinator does, plus more

### Cons
- Loses autonomous operation — someone has to drive the loop
- Could add a cron-based poller, but that's building a new coordinator by another name
- The developer/QA/merge agent pattern still needs someone to spawn the right agents in the right order — orchestration tools handle dispatch but the dev→QA→merge sequence is implicit in task state transitions, not explicit
- No single place to see "how does multi-agent work flow" — it's scattered across tool implementations

---

## Option C: Kill the coordinator, build orchestration into pipelines

Extend the pipeline system with native primitives for agent orchestration: `spawn`, `wait`, `loop`, `parallel`. The coordinator's logic moves into pipeline-native constructs rather than living in MCP tools.

### What changes

New pipeline step types alongside existing `exec`, `prompt`, `mcp`, `invoke_pipeline`, `activate_workflow`:

```yaml
steps:
  - id: dispatch
    spawn_agents:
      agent: developer-gemini
      for_each: "{{ ready_tasks }}"    # parallel fan-out
      isolation: worktree
      workflow: developer
      max_concurrent: 3

  - id: wait_all
    wait:
      for: "{{ steps.dispatch.agents }}"
      timeout: 600

  - id: review
    spawn_agents:
      agent: qa-claude
      for_each: "{{ steps.wait_all.completed }}"
      workflow: qa-reviewer

  # ... etc

# Native loop instead of invoke_pipeline recursion
loop:
  condition: "{{ has_ready_tasks }}"
  max_iterations: 50
```

### Pros
- Pipeline system becomes the single orchestration abstraction
- No MCP tools needed for basic orchestration patterns
- Loop control is native, not hacked via self-recursion
- Parallel fan-out is declarative
- Easy to reason about — read the YAML, understand the flow

### Cons
- Significant pipeline system work — new step types, new executor logic
- Pipeline system is already being retooled, this adds scope
- Duplicates functionality that already exists in orchestration tools (slot reservation, retry, cleanup)
- Tight coupling between pipelines and agent/worktree/task systems
- Risk of the pipeline system becoming a general-purpose workflow engine (scope creep)

---

## Option D: Decompose into focused, composable pieces

Break the coordinator's concerns into small, independent units that can be assembled differently depending on the use case. Not a single coordinator or a single set of orchestration tools — modular building blocks.

### What changes

Identify the atomic operations and make each one independently callable:

| Building block | Responsibility | Implemented as |
|---------------|---------------|----------------|
| Task selector | Pick next task(s) to work on | Already exists: `suggest_next_task`, `list_ready_tasks` |
| Agent dispatcher | Spawn agent(s) for task(s) with isolation | Already exists: `spawn_agent`, partially `orchestrate_ready_tasks` |
| Agent monitor | Track agent completion/failure | Already exists: `poll_agent_status`, `wait_for_*` |
| Task transitioner | Move task through its lifecycle states | Scattered today — consolidate into a state machine |
| Isolation manager | Create/merge/cleanup worktrees or clones | Partially exists: `gobby-clones`, `gobby-worktrees`, cleanup tools |

Then compose them:
- **Pipeline composition**: A pipeline YAML wires these blocks together via `mcp` steps (like today, but each step is focused)
- **Skill composition**: A skill like `/orchestrate` calls these blocks in sequence
- **Programmatic composition**: Python code assembles them (for complex custom flows)

### Pros
- Maximum flexibility — same blocks, different assemblies
- Each block is independently testable and understandable
- Task lifecycle becomes explicit (state machine) instead of scattered
- Doesn't require pipeline system changes
- Doesn't require killing anything — refactors what exists

### Cons
- "Composable building blocks" can mean "no opinions" — someone still has to define the happy path
- Risk of over-abstraction — 5 building blocks to do what 1 coordinator does today
- The task state machine is the hard part and it doesn't exist yet
- More surface area to maintain than a single coordinator

---

## Trade-offs Matrix

| | A: Refactor | B: Kill + tools | C: Kill + pipelines | D: Decompose |
|---|---|---|---|---|
| **Effort** | Low | Low | High | Medium |
| **Parallelism** | Yes (via tools) | Yes (via tools) | Yes (native) | Yes (via tools) |
| **Loop control** | Still hacked | No loop needed | Native | Depends on assembly |
| **Pipeline rework alignment** | Neutral | Neutral | Adds scope | Neutral |
| **Single source of truth** | Coordinator YAML | Orchestration tools | Pipeline YAML | No single source |
| **Autonomous operation** | Yes | No (needs driver) | Yes | Depends on assembly |
| **Task lifecycle clarity** | Still scattered | Still scattered | Could be explicit | Explicit (if built) |
| **Orchestration tools fate** | Used as-is | Used as-is | Mostly deprecated | Partially refactored |
| **New code required** | ~50 lines YAML | ~0 | ~500+ lines Python | ~200 lines Python |

---

## What happens to the 11 orchestration tools

| Tool | A: Refactor | B: Kill + tools | C: Pipelines | D: Decompose |
|------|------------|----------------|--------------|--------------|
| `orchestrate_ready_tasks` | Keep, called by coordinator | Keep, primary interface | Deprecate (native spawn) | Refactor into dispatcher block |
| `get_orchestration_status` | Keep | Keep | Keep (read-only) | Keep |
| `poll_agent_status` | Keep, called by coordinator | Keep | Deprecate (native wait) | Refactor into monitor block |
| `spawn_review_agent` | Keep | Keep | Deprecate (native spawn) | Refactor into dispatcher block |
| `process_completed_agents` | Keep, called by coordinator | Keep | Deprecate | Refactor into transitioner block |
| `approve_and_cleanup` | Keep | Keep | Keep (manual use) | Keep |
| `cleanup_reviewed_worktrees` | Keep, called by coordinator | Keep | Deprecate (native cleanup) | Refactor into isolation manager |
| `cleanup_stale_worktrees` | Keep | Keep | Keep (maintenance) | Keep |
| `wait_for_task` | Keep | Keep | Deprecate (native wait) | Keep in monitor block |
| `wait_for_any_task` | Keep | Keep | Deprecate (native wait) | Keep in monitor block |
| `wait_for_all_tasks` | Keep | Keep | Deprecate (native wait) | Keep in monitor block |

---

## Open Questions

1. **Does the pipeline rework already have plans for loop/parallel primitives?** If yes, Option C might be the natural path. If no, it's a big addition.
2. **Is autonomous operation (no human driver) a requirement?** If yes, Options A/C/D. If human-in-the-loop is fine, Option B is simplest.
3. **Should the dev→QA→merge sequence be hardcoded or configurable?** The coordinator hardcodes it. Orchestration tools don't enforce it. The answer affects whether we need a coordinator-like thing at all.
4. **What's the future of clones vs worktrees?** The coordinator uses clones. The orchestration tools use worktrees. Picking one simplifies the isolation story.
