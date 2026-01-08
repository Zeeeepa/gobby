# Gobby Implementation Roadmap

## Overview

This document defines the implementation order across all Gobby planning documents. Each phase is designed to deliver standalone value while building toward the complete vision: transforming Gobby from a session tracker into a full **agent orchestration platform**.

## Document References

### Completed Plans

| Document | Location | Focus |
|----------|----------|-------|
| WORKFLOWS | `docs/plans/completed/WORKFLOWS.md` | Step-based workflow enforcement |
| TASKS | `docs/plans/completed/TASKS.md` | Persistent task tracking system (includes V2 enhancements) |
| SESSION_TRACKING | `docs/plans/completed/SESSION_TRACKING.md` | Async JSONL processing, multi-CLI message storage |
| SESSION_MANAGEMENT | `docs/plans/completed/SESSION_MANAGEMENT.md` | Session CRUD tools, handoff MCP tools |
| SKILLS | `docs/plans/completed/SKILLS.md` | Skills module decoupling (from memory) |
| HOOK_EXTENSIONS | `docs/plans/completed/HOOK_EXTENSIONS.md` | WebSocket events, webhooks, plugins |
| MCP_PROXY_IMPROVEMENTS | `docs/plans/completed/MCP_PROXY_IMPROVEMENTS.md` | Tool metrics, semantic search, self-healing |
| MEMORY | `docs/plans/completed/MEMORY.md` | Persistent memory and skill learning |
| AUTONOMOUS_HANDOFF | `docs/plans/completed/AUTONOMOUS_HANDOFF.md` | Pre-compact context extraction, session chaining |

### Post-MVP Plans

| Document | Location | Focus | Status |
|----------|----------|-------|--------|
| ENHANCEMENTS | `docs/plans/enhancements.md` | 10 major phases: worktrees, merge resolution, GitHub/Linear, autonomous loops | Partial |
| SUBAGENTS | `docs/plans/completed/SUBAGENTS.md` | Multi-provider agent spawning system | ✅ Complete |
| UI | `docs/plans/UI.md` | Web dashboard, real-time visualization | Pending |

---

## Implementation Order

```
═══════════════════════════════════════════════════════════════════════════════
                              FOUNDATION LAYER
═══════════════════════════════════════════════════════════════════════════════

┌─────────────────────────────────────────────────────────────────────────────┐
│ Sprint 1: Hook Event Broadcasting ✅ COMPLETED                               │
│ HOOK_EXTENSIONS Phase 1                                                      │
│                                                                              │
│ Deliverable: Real-time hook events via WebSocket                            │
│ Dependencies: None (uses existing WebSocket infrastructure)                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Sprint 2: Core Task System ✅ COMPLETED                                      │
│ TASKS Phases 1-6                                                             │
│                                                                              │
│ Deliverable: Task CRUD, dependencies, ready work detection, git sync        │
│ Dependencies: None (self-contained)                                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Sprint 3: Task MCP Tools & CLI ✅ COMPLETED                                  │
│ TASKS Phases 7-10                                                            │
│                                                                              │
│ Deliverable: Task management via MCP tools and CLI + gobby-* proxy       │
│ Dependencies: Sprint 2                                                       │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Sprint 3.5: Task Extensions ✅ COMPLETED                                     │
│ TASKS Phases 9.5-9.9                                                         │
│                                                                              │
│ Deliverable: Compaction, Labels, Maintenance, Import, Stealth Mode          │
│ Dependencies: Sprint 3                                                       │
└─────────────────────────────────────────────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════════════════
                              WORKFLOW ENGINE
═══════════════════════════════════════════════════════════════════════════════

┌─────────────────────────────────────────────────────────────────────────────┐
│ Sprint 4: Workflow Foundation ✅ COMPLETED                                   │
│ WORKFLOWS Phases 0-2                                                         │
│                                                                              │
│ Deliverable: YAML loader, state manager, core engine                        │
│ Dependencies: None                                                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Sprint 5: Workflow Hook Integration ✅ COMPLETED                             │
│ WORKFLOWS Phase 3                                                            │
│                                                                              │
│ Deliverable: Workflows evaluate on hook events, tool blocking               │
│ Dependencies: Sprint 4                                                       │
│ Done: All hooks (session, tool, stop, pre_compact) with trigger aliases     │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Sprint 6: Workflow Actions ✅ COMPLETED                                      │
│ WORKFLOWS Phase 4                                                            │
│                                                                              │
│ Deliverable: inject_context, capture_artifact, generate_handoff, etc.       │
│ Dependencies: Sprint 5                                                       │
│ Done: All scheduled actions (handoff, state, LLM, todo, mcp)                │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Sprint 7: Context Sources & Templates ✅ COMPLETED                           │
│ WORKFLOWS Phases 5-6                                                         │
│                                                                              │
│ Deliverable: Jinja2 templating, built-in workflow templates                 │
│ Dependencies: Sprint 6                                                       │
│                                                                              │
│ - [x] Jinja2 integration                                                     │
│ - [x] Template engine implementation                                         │
│ - [x] Context sources (previous_session_summary, handoff, artifacts, etc.)  │
│ - [x] LLM-powered generate_handoff action                                    │
│ - [x] Git status and file changes context gathering                          │
│ - [x] All 7 built-in templates (session-handoff, plan-execute, react,       │
│       plan-act-reflect, plan-to-tasks, architect, test-driven)               │
└─────────────────────────────────────────────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════════════════
                            SESSION MESSAGE TRACKING
═══════════════════════════════════════════════════════════════════════════════

┌─────────────────────────────────────────────────────────────────────────────┐
│ Sprint 7.1: Session Message Foundation ✅ COMPLETED                          │
│ SESSION_TRACKING Phase 1                                                     │
│                                                                              │
│ Deliverable: Database schema, LocalMessageManager, ParsedMessage dataclass  │
│ Dependencies: None                                                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Sprint 7.2: Async Message Processor ✅ COMPLETED                              │
│ SESSION_TRACKING Phase 2                                                     │
│                                                                              │
│ Deliverable: SessionMessageProcessor with byte-offset polling, debouncing   │
│ Dependencies: Sprint 7.1                                                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Sprint 7.3: Session Tracking Integration ✅ COMPLETED                         │
│ SESSION_TRACKING Phases 3-4                                                  │
│                                                                              │
│ Deliverable: Runner/HookManager integration, WebSocket broadcasting         │
│ Dependencies: Sprint 7.2                                                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Sprint 7.4: Multi-CLI Parsers & API ✅ COMPLETED                               │
│ SESSION_TRACKING Phases 5-6                                                  │
│                                                                              │
│ Deliverable: Gemini/Codex parsers, parser registry, query API, MCP tools    │
│ Dependencies: Sprint 7.3                                                     │
└─────────────────────────────────────────────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════════════════
                            MEMORY-FIRST AGENTS
═══════════════════════════════════════════════════════════════════════════════

┌─────────────────────────────────────────────────────────────────────────────┐
│ Sprint 7.5: Memory Storage & Operations ✅ COMPLETED                         │
│ MEMORY Phases 1-2                                                            │
│                                                                              │
│ Deliverable: Memory storage layer, remember/recall/forget operations        │
│ Dependencies: None (can start in parallel with workflow sprints)            │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Sprint 7.6: Skill Learning ✅ COMPLETED                                      │
│ MEMORY Phases 3-4                                                            │
│                                                                              │
│ Deliverable: Skill extraction from sessions, trigger matching, hook inject  │
│ Dependencies: Sprint 7.5                                                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Sprint 7.7: Memory MCP Tools & CLI ✅ COMPLETED                              │
│ MEMORY Phases 5-6                                                            │
│                                                                              │
│ Deliverable: Full MCP tool suite, CLI commands for memory/skill management  │
│ Dependencies: Sprint 7.6                                                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Sprint 7.8: Memory Git Sync & Enhancements ✅ COMPLETED                      │
│ MEMORY Phases 7-10                                                           │
│                                                                              │
│ Deliverable: JSONL sync, semantic search, auto-extraction, documentation    │
│ Dependencies: Sprint 7.7                                                     │
└─────────────────────────────────────────────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════════════════
                            EXTENSIONS & INTEGRATION
═══════════════════════════════════════════════════════════════════════════════

┌─────────────────────────────────────────────────────────────────────────────┐
│ Sprint 8: Webhooks ✅ COMPLETED                                              │
│ HOOK_EXTENSIONS Phase 2                                                      │
│                                                                              │
│ Deliverable: Config-driven HTTP callouts on hook events                     │
│ Dependencies: Sprint 1 (broadcaster pattern)                                 │
│ Done: WebhookDispatcher with retry logic, blocking webhooks, fire-and-forget│
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Sprint 9: Python Plugins ✅ COMPLETED                                        │
│ HOOK_EXTENSIONS Phase 3                                                      │
│                                                                              │
│ Deliverable: Dynamic plugin loading, custom hook handlers                   │
│ Dependencies: Sprint 1                                                       │
│ Done: PluginLoader, HookPlugin base class, @hook_handler, action/condition  │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Sprint 10: Workflow CLI & MCP Tools ✅ COMPLETED                             │
│ WORKFLOWS Phases 7-8                                                         │
│                                                                              │
│ Deliverable: gobby workflows commands, workflow MCP tools                   │
│ Dependencies: Sprint 7                                                       │
│ Done: All 8 CLI commands + 8 MCP tools implemented and tested               │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Sprint 11: Workflow-Task Integration ✅ COMPLETED                            │
│ TASKS Phases 11-13                                                           │
│                                                                              │
│ Deliverable: Tasks linked to workflows, LLM expansion, spec parsing         │
│ Dependencies: Sprint 3 + Sprint 7                                            │
│ Done: Schema updates, task-workflow bridge, LLM expansion, spec parser      │
│ Note: Agent instructions covered by gobby-skills system                      │
└─────────────────────────────────────────────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════════════════
                              MCP PROXY ENHANCEMENTS
═══════════════════════════════════════════════════════════════════════════════

┌─────────────────────────────────────────────────────────────────────────────┐
│ Sprint 12: Tool Metrics ✅ COMPLETED                                         │
│ MCP_PROXY_IMPROVEMENTS Phase 1                                               │
│                                                                              │
│ Deliverable: Track tool call/success rates, expose in recommendations       │
│ Dependencies: None                                                           │
│ Done: ToolMetricsManager, get_failing_tools, include_metrics in list_tools  │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Sprint 13: Lazy Server Init ✅ COMPLETED                                     │
│ MCP_PROXY_IMPROVEMENTS Phase 2                                               │
│                                                                              │
│ Deliverable: Deferred MCP server connections, faster startup                │
│ Dependencies: None                                                           │
│ Done: LazyServerConnector with circuit breaker, preconnect_servers config   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Sprint 14: Semantic Tool Search ✅ COMPLETED                                 │
│ MCP_PROXY_IMPROVEMENTS Phase 3                                               │
│                                                                              │
│ Deliverable: Embeddings-based tool search, hybrid recommend_tools           │
│ Dependencies: Sprint 12                                                      │
│ Done: SemanticToolSearch, search_tools MCP/CLI, recommend_tools modes       │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Sprint 15: Self-Healing & Incremental Indexing ✅ COMPLETED                  │
│ MCP_PROXY_IMPROVEMENTS Phases 4-5                                            │
│                                                                              │
│ Deliverable: Fallback suggestions on failure, hash-based schema refresh     │
│ Dependencies: Sprint 14                                                      │
│ Done: ToolFallbackResolver, SchemaHashManager, gobby mcp refresh CLI        │
└─────────────────────────────────────────────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════════════════
                              POLISH & DOCUMENTATION
═══════════════════════════════════════════════════════════════════════════════

┌─────────────────────────────────────────────────────────────────────────────┐
│ Sprint 16: Hook Extensions CLI & Workflow Integration ✅ COMPLETED           │
│ HOOK_EXTENSIONS Phases 4-5                                                   │
│                                                                              │
│ Deliverable: Webhook as workflow action, plugin-defined actions/conditions  │
│ Dependencies: Sprint 9 + Sprint 7                                            │
│ Done: WebhookAction, WebhookExecutor, plugin actions/conditions, CLI (6/6)  │
│ Polish: MCP tools, metrics, tests, docs tracked in gt-84d0d2                │
│ Future: Webhook as workflow condition (gt-bbe107)                            │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Sprint 17: Feature Gap Coverage ✅ COMPLETED                                  │
│ MCP_PROXY_IMPROVEMENTS, HOOK_EXTENSIONS, MEMORY, AUTONOMOUS_HANDOFF gaps    │
│                                                                              │
│ Deliverable: Close feature gaps before marking plans complete               │
│ Dependencies: None                                                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Sprint 18: End-to-End Testing                                                │
│ WORKFLOWS Phases 9-11 + AUTONOMOUS_HANDOFF tests                            │
│                                                                              │
│ Deliverable: Comprehensive tests, crash recovery, escape hatches            │
│ Dependencies: Sprint 17                                                      │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Sprint 19: Documentation                                                     │
│ ALL PLANS Documentation Phases                                               │
│                                                                              │
│ Deliverable: User guides, examples, updated CLAUDE.md                       │
│ Dependencies: All previous sprints                                           │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Sprint Summary Table

### Completed Sprints

| Focus | Plan Reference |
|-------|----------------|
| WebSocket Broadcasting | HOOK_EXTENSIONS Phase 1 |
| Core Task System | TASKS Phases 1-6 |
| Task MCP/CLI | TASKS Phases 7-10 |
| Task Extensions | TASKS Phases 9.5-9.9 |
| Workflow Foundation | WORKFLOWS Phases 0-2 |
| Workflow Hooks | WORKFLOWS Phase 3 |
| Workflow Actions | WORKFLOWS Phase 4 |
| Context & Templates | WORKFLOWS Phases 5-6 |
| Session Message Foundation | SESSION_TRACKING Phase 1 |
| Async Message Processor | SESSION_TRACKING Phase 2 |
| Session Tracking Integration | SESSION_TRACKING Phases 3-4 |
| Multi-CLI Parsers & API | SESSION_TRACKING Phases 5-6 |
| Memory Storage & Operations | MEMORY Phases 1-2 |
| Skill Learning | MEMORY Phases 3-4 |
| Memory MCP/CLI | MEMORY Phases 5-6 |
| Memory Sync & Enhancements | MEMORY Phases 7-10 |
| Webhooks | HOOK_EXTENSIONS Phase 2 |
| Python Plugins | HOOK_EXTENSIONS Phase 3 |
| Workflow CLI/MCP | WORKFLOWS Phases 7-8 |
| Workflow-Task Integration | TASKS Phases 11-13 |
| Tool Metrics | MCP_PROXY Phase 1 |
| Lazy Init | MCP_PROXY Phase 2 |
| Semantic Tool Search | MCP_PROXY Phase 3 |
| Self-Healing MCP | MCP_PROXY Phases 4-5 |
| Hook Workflow Integration | HOOK_EXTENSIONS Phases 4-5 |
| Feature Gap Coverage | MCP_PROXY, HOOK_EXT, MEMORY, HANDOFF gaps |
| Session Management Tools | SESSION_MANAGEMENT |
| Subagent System | SUBAGENTS Phases 1-4 |

### Remaining Sprints

| Focus | Plan Reference | Notes |
|-------|----------------|-------|
| Task V2: Enhanced Validation | TASKS Phases 12.6-12.13 | 🔶 Remaining: external validator agent spawning |
| Worktree Coordination | ENHANCEMENTS Phase 1 | 🔶 Remaining: tiered merge conflict resolution |
| Merge Resolution | ENHANCEMENTS Phase 2 | |
| GitHub Integration | ENHANCEMENTS Phase 4 | |
| Linear Integration | ENHANCEMENTS Phase 5 | |
| Artifact Index | ENHANCEMENTS Phase 7 | |
| Enhanced Skill Routing | ENHANCEMENTS Phase 8 | |
| Semantic Memory Search | ENHANCEMENTS Phase 9 | |
| Autonomous Work Loop | ENHANCEMENTS Phase 10 | 🔶 Remaining: multi-surface stop signals, stuck detection |
| Web Dashboard | UI Phases 1-7 | |
| End-to-End Testing | WORKFLOWS Phases 9-11 | |
| Documentation | All Plans, User Guides | |

---

## Parallel Tracks

Remaining work can run in parallel if multiple contributors are available:

### Track A: Intelligence

Artifact Index → Enhanced Skill Routing → Semantic Memory Search → Autonomous Work Loop

### Track B: Integrations

Worktree Coordination → Merge Resolution → GitHub Integration → Linear Integration

### Track C: Visualization

Web Dashboard (can start independently)

### Track D: Final Polish

End-to-End Testing → Documentation (should be last)

---

## Completed Milestones

### "Observable Gobby" ✅

- WebSocket event streaming
- Full task system with CLI
- **Value**: External tools can monitor sessions, agents can track work

### "Workflow Engine" ✅

- Workflow foundation (loader, state manager, engine)
- Session lifecycle hooks (session_start, session_end)
- Handoff actions (find_parent, restore_context, generate_handoff)
- LLM-powered session summaries with context handoff
- Context sources (previous_session_summary, handoff, artifacts, observations, workflow_state)
- Jinja2 templating for context injection
- All 7 built-in templates (session-handoff, plan-execute, react, plan-act-reflect, plan-to-tasks, architect, test-driven)
- **Value**: Complete workflow templating system ready for step-based enforcement

### "Session Recording" ✅

- Async JSONL message processing for all CLIs
- Multi-CLI parsers (Claude, Gemini, Codex, Antigravity)
- Real-time WebSocket message streaming
- Message search and query API
- **Value**: Full conversation history for memory, analytics, and debugging

### "Memory-First Agents" ✅

- Persistent memory across sessions (remember/recall/forget operations)
- Skill learning from session trajectories via LLM extraction
- MCP tools for memory and skill management (`gobby-memory`, `gobby-skills`)
- CLI commands for memory and skill operations
- JSONL sync for memories and skills (`.gobby/memories.jsonl`, `.gobby/skills/`)
- Cross-CLI memory sharing via unified storage
- **Value**: Agents that learn and remember like coworkers, not contractors

### "Extensible Gobby" 🔶

- [x] Webhook integrations (WebhookDispatcher with retry, blocking/non-blocking)
- [x] Python plugin system (PluginLoader, HookPlugin, @hook_handler decorator)
- [x] Plugin-defined workflow actions and conditions
- [ ] Webhook as workflow condition (conditional branching based on response) → gt-bbe107
- **Value**: Infinite customization without forking

### "Smart MCP Proxy" ✅

- Tool metrics and recommendations
- Lazy server initialization
- Semantic search with OpenAI embeddings
- Self-healing fallbacks
- **Value**: Intelligent tool orchestration across MCP servers

### "Multi-Agent Orchestration" ✅

- `AgentExecutor` interface with multi-provider support
- Claude, Gemini, Codex executors
- MCP tools: `start_agent`, `stop_agent`, `list_agents`, `get_agent_status`
- Context injection with `session_context` parameter
- Agent depth tracking and safety limits
- Terminal and headless spawn modes
- **Value**: Orchestrate specialized agents with different models

---

## Remaining Milestones

### "Task System V2" 🔶

- [x] Commit linking infrastructure
- [x] MCP tools: `link_commit`, `auto_link_commits`, `get_task_diff`
- [x] CLI commands: `gobby tasks commit link/unlink/auto/list`
- [x] Validation history tracking, structured issues, escalation workflow
- [ ] External validator agent (spawn separate agent, not just different LLM)
- **Value**: Production-grade QA loops with traceability

### "Worktree Orchestration" 🔶

- [x] Daemon-managed worktree registry
- [x] Agent spawning in worktrees (`spawn_agent_in_worktree`)
- [x] Stale worktree detection and cleanup
- [ ] Tiered merge conflict resolution (Auto-Claude inspired)
- **Value**: True parallel development with multiple agents

### "External Integrations"

- [ ] GitHub Issues ↔ gobby-tasks sync
- [ ] PR creation from completed tasks
- [ ] Linear Issues ↔ gobby-tasks sync
- **Value**: Bridge between local AI development and team workflows

### "Intelligence Layer"

- [ ] Artifact Index with FTS5
- [ ] Enhanced skill routing: USE_EXISTING, IMPROVE, CREATE_NEW, COMPOSE
- [ ] Semantic memory search with sqlite-vec
- **Value**: Agents that get smarter over time

### "Autonomous Execution" 🔶

- [x] Session chaining for context limits
- [x] Task-driven work loops
- [ ] Multi-surface stop signals (HTTP, MCP, WebSocket, CLI, slash commands)
- [ ] Progress tracking with stuck detection
- **Value**: Hands-off task execution overnight

### "Visual Control Center"

- [ ] React + Vite web dashboard
- [ ] Real-time WebSocket updates
- [ ] Task graph visualization (Cytoscape.js)
- [ ] MCP Observatory (server health, tool analytics)
- [ ] Memory & Skills browser
- **Value**: See everything happening across all agents

### "Production Ready" (Final)

- [ ] End-to-end testing, crash recovery
- [ ] Documentation and user guides
- **Value**: Ship it!

---

## What's Next Recommendations

**If you want parallel development**: Worktree Orchestration - multiple agents working simultaneously.

**If you want better QA**: Task V2 - commit linking and enhanced validation loops.

**If you want smarter context**: Artifact Index - searchable session history for better handoffs.

**If you want autonomous agents**: Autonomous Work Loop - hands-off task execution.

**If you want visibility**: Web Dashboard - see everything happening in real-time.
