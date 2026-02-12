# Plan: Migrate Task Research/Expansion/Validation/Q&A to Coordinator/Agents/Workflows

**Task**: #7360
**Context**: Task expansion, validation, research, and Q&A currently live as standalone MCP tools and skill prompts, disconnected from the workflow/agent orchestration system. The coordinator pipeline assumes tasks are already expanded and handles only the work/review/merge cycle. This creates a gap: there's no structured way to expand unexpanded tasks in automation, no reusable research agent, no workflow-governed validation loop, and no Q&A mechanism for clarification during expansion.

---

## Current State

### What Exists

| Component | Location | Status |
| :--- | :--- | :--- |
| Task expansion | `mcp_proxy/tools/tasks/_expansion.py` (save_expansion_spec, execute_expansion) | MCP tools only, no workflow |
| Task validation | `tasks/validation.py`, `tasks/external_validator.py` | MCP tools + 3 modes (llm/agent/spawn) |
| validate_and_fix loop | `mcp_proxy/tools/tasks/_lifecycle_validation.py` | Code-based, not workflow |
| Research | Informal part of `/gobby:expand` skill prompt (being retired) | No agent, no structure |
| Q&A loop | Doesn't exist | - |
| Coordinator pipeline | `install/shared/workflows/coordinator.yaml` | Assumes expanded tasks |
| Worker workflows | developer.yaml, qa-reviewer.yaml, meeseeks-claude worker | claim → work → commit → report → shutdown |

### Key Constraint

**One step workflow per session.** `_handle_self_mode` (spawn_agent.py:83-98) rejects activation if a step workflow is already active. However, this rarely matters because the coordinator spawns each agent in a **fresh session** (terminal/headless/clone). Each spawned session starts with no active workflow, so expansion/validation workflows activate cleanly.

### Coordinator Pipeline Architecture

`coordinator.yaml` (pipeline, deterministic): find_work → clone → spawn_dev → wait → spawn_qa → wait → spawn_merge → wait → close → cleanup → recurse

Each step spawns an agent in its own session. Expansion/validation agents fit this same pattern — they get their own session, do their work, and complete.

---

## Migration Plan

### Phase 1: Research Agent

**Goal**: Create a reusable research agent that gathers codebase context for any task. Used by expansion, developer pre-work, validation context gathering.

**Create**:

- `src/gobby/install/shared/agents/researcher.yaml` — Agent definition
  - provider: configurable (default: claude)
  - mode: headless (runs in-process, no terminal)
  - timeout: 60s (from `TaskExpansionConfig.research_timeout`)
  - max_turns: 10 (from `TaskExpansionConfig.research_max_steps`)
  - Tools: Read, Glob, Grep, Bash (read-only), gobby-tasks (get_task), gobby-memory (search_memories)
  - Blocked: Edit, Write, NotebookEdit, spawn_agent
  - Prompt template: Takes `task_id`, returns structured research context (relevant files, patterns, test locations, dependencies)

- `src/gobby/install/shared/prompts/research/system.md` — Research agent system prompt
  - Structured output: files found, patterns observed, test file locations, key interfaces
  - References the existing `install/shared/prompts/research/step.md`

**Modify**:

- `src/gobby/config/tasks.py` — Add `research_agent` field to `TaskExpansionConfig` (default: "researcher")

**Usage pattern**: `spawn_agent(agent="researcher", task_id="#42", mode="headless")` → returns research context as `AgentResult.output`

**Why a separate agent (not a workflow step)**: Research is reusable across contexts. As an agent it can be spawned from any workflow step or pipeline step via `call_mcp_tool` → `spawn_agent`. It uses 1 depth level but provides isolation and reusability.

---

### Phase 2: Expansion Workflow

**Goal**: Structured multi-step expansion workflow. Can be activated interactively (mode=self on human session) or spawned by the coordinator pipeline in its own session.

**Create**:

- `src/gobby/install/shared/workflows/task-expansion.yaml` — Step workflow

  Steps:
  1. **check_resume** — Check for pending expansion spec (handles compaction recovery via `get_expansion_spec`). Auto-transitions to `execute` if found, else `research`.
  2. **research** — Spawn researcher agent via `call_mcp_tool` → `spawn_agent(agent="researcher", mode="headless")`. Wait for result. Read-only tools only.
  3. **clarify** — Optional Q&A step. Agent enters only when research is insufficient to determine the right decomposition. Most expansions proceed autonomously. Transitions back to `design` when answered.
  4. **design** — Generate expansion spec using research context + task details. Calls `save_expansion_spec` when done.
  5. **execute** — Call `execute_expansion` atomically. Transition to `complete`.
  6. **complete** — Expansion done. Workflow ends.

  Variables: `target_task_id`, `research_complete`, `spec_saved`, `needs_clarification`, `expansion_complete`

  Exit condition: `current_step == 'complete'`

---

### Phase 3: Validation Workflow (Autonomous)

**Goal**: Structured validate-fix-retry loop that runs autonomously. The agent fixes its own issues — the user is only involved at escalation (after max retries are exhausted).

**Create**:

- `src/gobby/install/shared/workflows/task-validation.yaml` — Step workflow

  Steps:
  1. **gather_context** — Run `get_validation_context_smart()` via the existing MCP tool. Read-only tools.
  2. **validate** — Call `validate_task`. Checks result.
  3. **fix** — Full tool access. Agent autonomously fixes issues based on validation feedback. Runs tests. No user interaction.
  4. **re_validate** — Re-run validation. Increment iteration counter. Loops back to `fix` if still failing.
  5. **passed** — Validation passed. Close task.
  6. **escalate** — Only reached when `validation_iteration >= max_iterations`. Marks task escalated — this is the only point where the user gets involved.
  7. **external_review** — Optional: spawn external validator agent for objectivity (uses existing `_run_spawn_validation`). Also autonomous.
  8. **complete** — Workflow ends.

  Variables: `target_task_id`, `validation_passed`, `validation_iteration`, `max_iterations` (from config), `escalated`

  The loop is fully autonomous: validate → fix → re-validate → fix → ... → escalate.

**No changes to existing tools**: `validate_task`, `close_task`, `get_validation_status` remain as primitives. The workflow composes them.

---

### Phase 4: Coordinator Pipeline Integration

**Goal**: Add expansion and validation steps to the coordinator pipeline so it can handle unexpanded tasks end-to-end.

**Modify `install/shared/workflows/coordinator.yaml`**:

Add steps before the existing `find_work`:

1. **check_expansion** — MCP call to `get_task` → check `is_expanded`
2. **spawn_expander** — Conditionally spawn task-ops agent with expansion workflow in a fresh session. Wait for completion.

Add validation step between `wait_qa` and `close_task`:
3. **spawn_validator** — Spawn task-ops agent with validation workflow. Autonomous fix loop runs in its own session.
4. **wait_validator** — Wait for validation agent to complete (pass or escalate).

The coordinator already spawns developer/QA/merge agents in separate sessions — expansion/validation agents follow the same pattern.

---

### Phase 5: Task-Ops Agent Definition

**Goal**: Bundle expansion, validation, and research workflows into a single agent definition. The coordinator spawns `task-ops` with the appropriate workflow key.

**Create**:

- `src/gobby/install/shared/agents/task-ops.yaml`

```yaml
name: task-ops
description: |
  Task operations agent for expansion, validation, and research.
  Coordinator spawns with workflow key: expansion, validation.
  Interactive sessions can use mode=self.

provider: claude
mode: terminal
default_workflow: expansion

workflows:
  expansion:
    file: task-expansion.yaml
    mode: self  # Interactive: activates on caller. Pipeline: runs in own session.
  validation:
    file: task-validation.yaml
    mode: self
```

**Usage from coordinator pipeline**:

```yaml
# Coordinator spawns expansion agent in fresh session
- id: spawn_expander
  condition: "${{ not steps.check_expansion.output.is_expanded }}"
  mcp:
    server: gobby-agents
    tool: spawn_agent
    arguments:
      agent: task-ops
      workflow: expansion
      task_id: "${{ inputs.session_task }}"
      mode: terminal
```

**Usage from interactive session**:

```text
spawn_agent(agent="task-ops", workflow="expansion", task_id="#42")
spawn_agent(agent="task-ops", workflow="validation", task_id="#42")
spawn_agent(agent="researcher", task_id="#42", mode="headless")
```

---

### Phase 6: Q&A Pattern Documentation

**Goal**: Document the workflow-based Q&A pattern for reuse.

Q&A is specifically for **expansion** (understanding user intent for task decomposition), not validation. Validation is autonomous — agents fix their own issues and only escalate after exhausting retries.

The Q&A pattern is a workflow step pattern:

1. Agent enters a `clarify` step when it genuinely can't proceed without user input
2. `on_enter` injects a message telling the agent to ask the user
3. Agent uses `AskUserQuestion` (in Claude Code) or the chat API (in web)
4. User responds (triggers `BEFORE_AGENT` event)
5. Agent processes response, sets variable (e.g., `needs_clarification = false`)
6. Workflow transitions to next step

The `clarify` step in the expansion workflow is **optional** — most expansions proceed autonomously based on research context alone.

---

## Migration Order

```text
Phase 1: Research Agent (foundation — no dependencies)
    ↓
Phase 2: Expansion Workflow (uses researcher from Phase 1)
    ↓                                    ↓
Phase 3: Validation Workflow          Phase 4: Coordinator Integration
    (independent, can parallelize)       (uses expansion from Phase 2)
    ↓                                    ↓
Phase 5: Task-Ops Agent (bundles Phases 1-3, used by Phase 4)
    ↓
Phase 6: Q&A Documentation
```

---

## Backward Compatibility

All existing MCP tools remain unchanged:

- `save_expansion_spec`, `execute_expansion`, `get_expansion_spec` — primitives
- `validate_task`, `close_task`, `get_validation_status` — primitives
- `orchestrate_ready_tasks` — unchanged
- Worker workflows (developer, qa-reviewer) — unchanged

`/gobby expand` skill is being deprecated after testing. The expansion workflow replaces it.

The new workflows compose existing primitives. No breaking changes.

---

## Key Files

| File | Action | Phase |
| :--- | :--- | :--- |
| `install/shared/agents/researcher.yaml` | Create | 1 |
| `install/shared/prompts/research/system.md` | Create | 1 |
| `config/tasks.py` | Modify (add research_agent field) | 1 |
| `install/shared/workflows/task-expansion.yaml` | Create | 2 |
| `install/shared/workflows/task-validation.yaml` | Create | 3 |
| `install/shared/workflows/coordinator.yaml` | Modify (add expansion/validation steps) | 4 |
| `install/shared/agents/task-ops.yaml` | Create | 5 |

---

## Verification

1. **Research agent**: `spawn_agent(agent="researcher", task_id="#N", mode="headless")` → returns structured context
2. **Expansion workflow**: `spawn_agent(agent="task-ops", workflow="expansion", task_id="#N")` → guides through research → design → execute
3. **Validation workflow**: `spawn_agent(agent="task-ops", workflow="validation", task_id="#N")` → autonomous validate → fix → re-validate loop
4. **Coordinator pipeline**: Create an unexpanded epic, run coordinator → should auto-expand, then spawn developer/QA/merge as before
5. **Backward compat**: Existing `validate_task` tool and worker workflows work unchanged
6. **Tests**: Workflow YAML validation tests, transition condition tests, coordinator integration test with expansion
