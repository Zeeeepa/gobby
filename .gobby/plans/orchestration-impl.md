# Gobby Conductor: Unified Orchestration System

## Overview

Implementation of the orchestration system from `docs/plans/orchestration.md`. This enables multi-agent coordination with parent-child messaging, blocking wait tools, review gates, token budgeting, and a persistent conductor daemon.

## Constraints

- Must integrate with existing orchestration tools in `src/gobby/mcp_proxy/tools/orchestration/`
- Must leverage existing workflow definitions in `.gobby/workflows/`
- Database migrations must be backward-compatible
- Token tracking uses existing session fields, adds aggregation layer
- All worktree branches merge to `dev`, not main

## Phase 1: Inter-Agent Messaging Foundation

**Goal**: Enable parent↔child message passing during agent execution

**Tasks:**
- [ ] Create `inter_session_messages` database migration (category: code)
- [ ] Create `src/gobby/storage/inter_session_messages.py` storage module (category: code) (depends: inter_session_messages migration)
- [ ] Add `send_to_parent` MCP tool to gobby-agents (category: code) (depends: inter_session_messages storage)
- [ ] Add `send_to_child` MCP tool to gobby-agents (category: code) (depends: inter_session_messages storage)
- [ ] Add `poll_messages` MCP tool to gobby-agents (category: code) (depends: inter_session_messages storage)
- [ ] Add `mark_read` MCP tool to gobby-agents (category: code) (depends: inter_session_messages storage)
- [ ] Add WebSocket broadcast for `message_sent` events (category: code) (depends: send_to_parent, send_to_child)

## Phase 2: Task Status Extensions (depends: Phase 1)

**Goal**: Add blocking wait tools and review workflow support

**Tasks:**
- [ ] Add `review_at` timestamp column to tasks table (category: code)
- [ ] Modify `close_task` to transition to `review` when agent_depth > 0 (category: code) (depends: review_at migration)
- [ ] Add `wait_for_task` blocking MCP tool (category: code) (depends: close_task modification)
- [ ] Add `wait_for_any_task` blocking MCP tool (category: code) (depends: wait_for_task)
- [ ] Add `wait_for_all_tasks` blocking MCP tool (category: code) (depends: wait_for_task)
- [ ] Add `reopen_task` MCP tool for review → in_progress transition (category: code) (depends: close_task modification)
- [ ] Add `approve_and_cleanup` MCP tool (category: code) (depends: reopen_task)

## Phase 3: Interactive Orchestration Workflows (depends: Phase 2)

**Goal**: Enable tool-restricted workflows for spawned agents

**Tasks:**
- [ ] Create `worktree-agent.yaml` workflow definition (category: config)
- [ ] Modify `spawn_agent_in_worktree` to auto-activate worktree-agent workflow (category: code) (depends: worktree-agent.yaml)
- [ ] Create `gobby-merge` skill documentation (category: docs)

## Phase 4: Token Budget & Throttling (parallel with Phase 3)

**Goal**: Enable resource-aware autonomous operation with cost tracking

**Tasks:**
- [ ] Add `model` column to sessions table migration (category: code)
- [ ] Extract model from Claude JSONL transcripts (category: code) (depends: model column migration)
- [ ] Extract model from Gemini transcripts (category: code) (depends: model column migration)
- [ ] Create `src/gobby/conductor/pricing.py` with model pricing data (category: code)
- [ ] Create `src/gobby/conductor/token_tracker.py` with aggregation API (category: code) (depends: model extraction, pricing.py)
- [ ] Add `token_budget` config section to DaemonConfig (category: config)
- [ ] Add `get_usage_report` MCP tool to gobby-metrics (category: code) (depends: token_tracker.py)
- [ ] Add `get_budget_status` MCP tool to gobby-metrics (category: code) (depends: token_tracker.py, token_budget config)

## Phase 5: Conductor Daemon (depends: Phase 4)

**Goal**: Persistent daemon that monitors tasks and agents

**Tasks:**
- [ ] Create `src/gobby/conductor/__init__.py` module init (category: code)
- [ ] Create `src/gobby/conductor/monitors/tasks.py` for stale task detection (category: code) (depends: conductor __init__)
- [ ] Create `src/gobby/conductor/monitors/agents.py` for stuck agent detection (category: code) (depends: conductor __init__)
- [ ] Create `src/gobby/conductor/alerts.py` for alert dispatch (category: code) (depends: conductor __init__)
- [ ] Create `src/gobby/conductor/loop.py` with ConductorLoop class (category: code) (depends: task monitor, agent monitor, alerts, token_tracker.py)
- [ ] Add conductor config section to DaemonConfig (category: config)
- [ ] Create `src/gobby/cli/conductor.py` with CLI commands (category: code) (depends: ConductorLoop, conductor config)
- [ ] Register conductor CLI group in main CLI (category: code) (depends: conductor CLI commands)
- [ ] Modify `src/gobby/runner.py` to start ConductorLoop (category: code) (depends: ConductorLoop, conductor config)

## Phase 6: Documentation & Testing (depends: Phase 5)

**Goal**: Validate the system end-to-end and update documentation

**Tasks:**
- [ ] Create `tests/e2e/test_inter_agent_messages.py` (category: test) (depends: Phase 1)
- [ ] Create `tests/e2e/test_sequential_review_loop.py` (category: test) (depends: Phase 2, Phase 3)
- [ ] Create `tests/e2e/test_token_budget.py` (category: test) (depends: Phase 4)
- [ ] Create `tests/e2e/test_autonomous_mode.py` (category: test) (depends: Phase 5)
- [ ] Create `tests/conductor/test_token_tracker.py` (category: test) (depends: token_tracker.py)
- [ ] Create `tests/conductor/test_loop.py` (category: test) (depends: ConductorLoop)
- [ ] Document worktree agent mode in GEMINI.md (category: docs) (depends: Phase 3)
- [ ] Document orchestrator patterns in CLAUDE.md (category: docs) (depends: Phase 3)

## Dependency Graph

```
Phase 1: Inter-Agent Messaging
    │
    ├── inter_session_messages migration
    │       │
    │       └── inter_session_messages storage
    │               │
    │               ├── send_to_parent tool ──┐
    │               ├── send_to_child tool ───┼─→ WebSocket broadcast
    │               ├── poll_messages tool
    │               └── mark_read tool
    │
    ▼
Phase 2: Task Status Extensions
    │
    ├── review_at migration
    │       │
    │       └── close_task modification
    │               │
    │               ├── wait_for_task tool
    │               │       │
    │               │       ├── wait_for_any_task tool
    │               │       └── wait_for_all_tasks tool
    │               │
    │               └── reopen_task tool
    │                       │
    │                       └── approve_and_cleanup tool
    │
    ▼
Phase 3: Workflows ◄──────────────────────────────┐
    │                                              │
    ├── worktree-agent.yaml                        │
    │       │                                      │
    │       └── spawn_agent_in_worktree mod        │
    │                                              │
    └── gobby-merge skill docs                     │
                                                   │
Phase 4: Token Budget (parallel) ─────────────────┘
    │
    ├── model column migration
    │       │
    │       ├── Claude model extraction
    │       └── Gemini model extraction
    │
    ├── pricing.py
    │       │
    │       └─┬── token_tracker.py
    │         │
    │         ├── get_usage_report tool
    │         └── get_budget_status tool
    │
    └── token_budget config
    │
    ▼
Phase 5: Conductor Daemon
    │
    ├── conductor __init__
    │       │
    │       ├── task monitor
    │       ├── agent monitor
    │       └── alerts
    │               │
    │               └── ConductorLoop
    │                       │
    │                       ├── conductor CLI
    │                       │       │
    │                       │       └── register CLI group
    │                       │
    │                       └── runner.py integration
    │
    └── conductor config
    │
    ▼
Phase 6: Documentation & Testing
    │
    ├── E2E tests (depend on respective phases)
    ├── Unit tests (depend on specific modules)
    └── Documentation updates
```

## Task Mapping

| Plan Item | Task Ref | Status |
|-----------|----------|--------|
| **Root Epic** | #4959 | in_progress |
| **Phase 1: Inter-Agent Messaging** | #4961 | open |
| inter_session_messages migration | #4967 | open |
| inter_session_messages storage | #4968 | open |
| send_to_parent MCP tool | #4969 | open |
| send_to_child MCP tool | #4970 | open |
| poll_messages MCP tool | #4971 | open |
| mark_read MCP tool | #4972 | open |
| WebSocket broadcast | #4973 | open |
| **Phase 2: Task Status Extensions** | #4962 | open |
| review_at migration | #4974 | open |
| close_task review transition | #4975 | open |
| wait_for_task tool | #4976 | open |
| wait_for_any_task tool | #4977 | open |
| wait_for_all_tasks tool | #4978 | open |
| reopen_task tool | #4979 | open |
| approve_and_cleanup tool | #4980 | open |
| **Phase 3: Orchestration Workflows** | #4963 | open |
| worktree-agent.yaml | #4981 | open |
| spawn_agent_in_worktree mod | #4982 | open |
| gobby-merge skill docs | #4983 | open |
| **Phase 4: Token Budget** | #4964 | open |
| model column migration | #4984 | open |
| Claude model extraction | #4985 | open |
| Gemini model extraction | #4986 | open |
| pricing.py | #4987 | open |
| token_tracker.py | #4988 | open |
| token_budget config | #4989 | open |
| get_usage_report tool | #4990 | open |
| get_budget_status tool | #4991 | open |
| **Phase 5: Conductor Daemon** | #4965 | open |
| conductor __init__.py | #4993 | open |
| monitors/tasks.py | #4994 | open |
| monitors/agents.py | #4995 | open |
| alerts.py | #4996 | open |
| loop.py | #4997 | open |
| conductor config | #4998 | open |
| conductor CLI | #4999 | open |
| register CLI group | #5000 | open |
| runner.py integration | #5001 | open |
| **Phase 6: Testing & Docs** | #4966 | open |
| E2E test_inter_agent_messages.py | #5002 | open |
| E2E test_sequential_review_loop.py | #5003 | open |
| E2E test_token_budget.py | #5004 | open |
| E2E test_autonomous_mode.py | #5005 | open |
| Unit test_token_tracker.py | #5006 | open |
| Unit test_loop.py | #5007 | open |
| GEMINI.md docs | #5008 | open |
| CLAUDE.md docs | #5009 | open |

