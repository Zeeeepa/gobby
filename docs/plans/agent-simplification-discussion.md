# Workflow & Agent Simplification Discussion

*Date: 2026-01-10*

This document captures the design discussion for simplifying Gobby's workflow actions and agent system.

## Overview

Two simplification efforts:
1. **Workflows**: Most actions become MCP calls, with a minimal set of built-in primitives
2. **Agents**: Delegate execution to Claude Code's `/agents`, Gobby adds workflow/variable layer

---

## Part 1: Workflow Action Simplification

### Current State

The workflow system has **40+ built-in action types**:

| Category | Count | Examples |
|----------|-------|----------|
| Context Management | 7 | `inject_context`, `inject_message`, `restore_context` |
| State Management | 5 | `load_workflow_state`, `save_workflow_state`, `set_variable` |
| Session Management | 5 | `mark_session_status`, `start_new_session`, `switch_mode` |
| Task Management | 3 | `persist_tasks`, `write_todos`, `mark_todo_complete` |
| Memory Management | 5 | `memory_sync_import`, `memory_recall_relevant`, `memory_save` |
| LLM & MCP | 2 | `call_llm`, `call_mcp_tool` |
| External Integration | 1 | `webhook` |
| Task Enforcement | 6 | `require_active_task`, `require_commit_before_stop` |
| Stop Signal | 3 | `check_stop_signal`, `request_stop`, `clear_stop_signal` |
| Progress Tracking | 4 | `start_progress_tracking`, `record_progress` |
| Anomaly Detection | 3 | `detect_stuck`, `detect_task_loop` |

Plus plugin actions: `plugin:<name>:<action>`

### Workflow Components

1. **Hook references** - `triggers` section mapping events to action lists
2. **Variables** - Session-scoped state, persisted to DB
3. **Conditionals** - Python `eval()` with restricted namespace (`when: "condition"`)
4. **Actions** - 40+ built-in types + plugin actions + `call_mcp_tool`

### Goal

**Author simplicity** - workflow authors only need to know MCP tool patterns for most operations.

### Key Insight

The workflow engine does two things:
1. **Orchestrate** - Decide what to do based on events and conditions
2. **Execute** - Perform the actual actions

MCP can handle (2) - most execution could be MCP calls.

The engine must handle (1) - condition evaluation, state persistence, and critically, **context injection** which must happen at the hook level before returning to the agent.

### Proposed Architecture

#### Built-in Actions (Minimal Set)

These **must** remain built-in because they couple to the hook system:

| Action | Reason |
|--------|--------|
| `inject_context` | Must modify hook response to inject into next prompt |
| `inject_message` | Same - modifies hook response |
| `set_variable` | Workflow engine state management |
| `load_workflow_state` | Engine persistence |
| `save_workflow_state` | Engine persistence |
| `transition` | Step workflow state machine |
| `call_llm` | LLM calls with template rendering |
| `webhook` | HTTP requests with retry logic |
| `capture_artifact` / `read_artifact` | Local filesystem access |

#### MCP Actions (Everything Else)

All other actions become `mcp: server.tool` calls:

| Current Action | Becomes |
|----------------|---------|
| `memory_save` | `mcp: gobby-memory.remember` |
| `memory_recall_relevant` | `mcp: gobby-memory.recall` |
| `memory_sync_*` | `mcp: gobby-memory.sync_*` |
| `memory_extract` | `mcp: gobby-memory.extract` |
| `persist_tasks` | `mcp: gobby-tasks.create_task` (batched) |
| `require_active_task` | `mcp: gobby-tasks.validate_active_task` |
| `require_commit_*` | `mcp: gobby-tasks.validate_commit` |
| `mark_session_status` | `mcp: gobby-sessions.update_status` |
| `start_new_session` | `mcp: gobby-sessions.spawn` |
| `generate_handoff` | `mcp: gobby-sessions.generate_handoff` |
| `synthesize_title` | `mcp: gobby-sessions.synthesize_title` |
| `start/stop_progress_tracking` | `mcp: gobby-metrics.progress_*` |
| `check_stop_signal` | `mcp: gobby-workflows.check_stop` |
| `request_stop` | `mcp: gobby-workflows.request_stop` |

#### Simplified Workflow Syntax

**Before (current):**
```yaml
actions:
  - action: memory_recall_relevant
    query: "project context"
    threshold: 0.7
  - action: inject_context
    content: "{{ recalled_memories }}"
```

**After (proposed):**
```yaml
actions:
  - mcp: gobby-memory.recall
    args:
      query: "project context"
      min_importance: 0.7
    store_result: recalled_memories
  - inject_context: "{{ recalled_memories }}"
```

The `mcp:` prefix signals MCP call, `inject_context:` is a built-in primitive.

### Benefits

1. **Single pattern** - Authors learn `mcp: server.tool` for most operations
2. **Discoverable** - `list_tools()` shows available actions
3. **Extensible** - Add capabilities by adding MCP tools, not engine code
4. **Testable** - MCP tools can be tested independently

---

## Part 2: Agent Simplification

### Current State

gobby-agents has significant custom infrastructure:
- Agent definitions (YAML with lifecycle_variables, mode, model)
- Execution modes (in_process, terminal, embedded, headless)
- Context injection system (parent session, transcripts, files)
- Child session management with depth tracking
- Multiple terminal spawners (Ghostty, iTerm, Kitty, etc.)

### Proposed Direction

**Use Claude Code's `/agents` as the execution engine.** Gobby adds:
- Workflow attachment
- Variable injection
- Session/task tracking

### What Gobby-Agents Would Do

```
start_agent(agent="validator", prompt="run tests", workflow="test-driven")
  → Load agent definition (role, prompt, allowed_tools)
  → Create child session for tracking
  → Set workflow variables (session_task, etc.)
  → Spawn via Claude Code's agent infrastructure
  → Return session_id for monitoring
```

### Agent Definition Format

**Current (gobby-specific)**:
```yaml
name: validation-runner
description: "Runs validation"
model: claude-3-haiku
mode: headless
lifecycle_variables:
  validation_model: null
```

**Proposed (Claude Code compatible)**:
```yaml
name: validation-runner
description: "Runs validation"
prompt: "You are a validation expert. Run tests and report results."
model: haiku
tools:
  - Bash
  - Read
  - Grep

# Gobby extensions
workflow: test-driven
variables:
  timeout: 300
```

### Integration Points

| Gobby Responsibility | Claude Code Responsibility |
|---------------------|---------------------------|
| Agent definition loading | Agent execution loop |
| Workflow/variable injection | Tool routing & permissions |
| Session tracking (parent/child) | Terminal spawning |
| Task linking | Context window management |

### Benefits

1. **Less code** - Remove custom spawning, execution modes, terminal detection
2. **Better UX** - Inherit Claude Code's polished agent experience
3. **Single pattern** - Agents are just Claude agents with Gobby workflow overlay
4. **Maintainable** - Claude Code team maintains the hard parts

---

## Decisions Made

1. **Keep call_llm, webhook, capture/read_artifact as built-ins** - not worth MCP overhead
2. **Clean break** - no backwards compatibility for workflow syntax, convert all at once
3. **Remove restore_context** - redundant with `inject_context(source="previous_session_summary")`

---

## Open Questions

### Workflow Syntax (Phase 2)
- Parser changes to support `mcp: server.tool` syntax
- How `store_result` works with MCP call results
- Error handling for MCP failures

### Agent Integration (Phase 3)
- How does Claude Code's `/agents` handle tool restrictions?
- Can we inject workflow state before agent starts (via hooks)?
- How to track agent completion and sync back to gobby sessions?

---

## Implementation Phases

### Phase 1: Remove `restore_context` (Done)
Quick win - consolidate redundant action.

### Phase 2: New Workflow Syntax
Design and implement `mcp: server.tool` syntax.

### Phase 3: Agent Integration
Investigate Claude Code `/agents` and design integration layer.
