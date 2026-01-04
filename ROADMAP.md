# Gobby Implementation Roadmap

## Overview

This document defines the implementation order across all Gobby planning documents. Each phase is designed to deliver standalone value while building toward the complete vision: transforming Gobby from a session tracker into a full **agent orchestration platform**.

## Document References

### Core MVP Plans

| Document | Location | Focus |
|----------|----------|-------|
| HOOK_EXTENSIONS | `docs/plans/HOOK_EXTENSIONS.md` | WebSocket events, webhooks, plugins |
| WORKFLOWS | `docs/plans/WORKFLOWS.md` | Phase-based workflow enforcement |
| TASKS | `docs/plans/TASKS.md` | Persistent task tracking system |
| SESSION_TRACKING | `docs/plans/SESSION_TRACKING.md` | Async JSONL processing, multi-CLI message storage |
| MEMORY | `docs/plans/MEMORY.md` | Persistent memory and skill learning |
| SKILLS | `docs/plans/SKILLS.md` | Skills module decoupling (from memory) |
| MCP_PROXY_IMPROVEMENTS | `docs/plans/MCP_PROXY_IMPROVEMENTS.md` | Tool metrics, semantic search, self-healing |

### Enhancement Plans

| Document | Location | Focus |
|----------|----------|-------|
| AUTONOMOUS_HANDOFF | `docs/plans/AUTONOMOUS_HANDOFF.md` | Pre-compact context extraction, session chaining |
| TASKS_V2 | `docs/plans/TASKS_V2.md` | Commit linking, enhanced QA validation |
| SESSION_MANAGEMENT | `docs/plans/SESSION_MANAGEMENT.md` | Session CRUD tools, handoff MCP tools |

### Post-MVP Plans

| Document | Location | Focus |
|----------|----------|-------|
| POST_MVP_ENHANCEMENTS | `docs/plans/POST_MVP_ENHANCEMENTS.md` | 10 major phases: worktrees, merge resolution, GitHub/Linear, autonomous loops |
| SUBAGENTS | `docs/plans/SUBAGENTS.md` | Multi-provider agent spawning system |
| UI | `docs/plans/UI.md` | Web dashboard, real-time visualization |

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
│ Sprint 5: Workflow Hook Integration 🔶 PARTIAL                               │
│ WORKFLOWS Phase 3                                                            │
│                                                                              │
│ Deliverable: Workflows evaluate on hook events, tool blocking               │
│ Dependencies: Sprint 4                                                       │
│ Done: session_start, session_end hooks. Pending: prompt_submit, tool hooks  │
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
│ Sprint 7.1: Session Message Foundation                                       │
│ SESSION_TRACKING Phase 1                                                     │
│                                                                              │
│ Deliverable: Database schema, LocalMessageManager, ParsedMessage dataclass  │
│ Dependencies: None                                                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Sprint 7.2: Async Message Processor                                          │
│ SESSION_TRACKING Phase 2                                                     │
│                                                                              │
│ Deliverable: SessionMessageProcessor with byte-offset polling, debouncing   │
│ Dependencies: Sprint 7.1                                                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Sprint 7.3: Session Tracking Integration                                     │
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
│ Sprint 8: Webhooks                                                           │
│ HOOK_EXTENSIONS Phase 2                                                      │
│                                                                              │
│ Deliverable: Config-driven HTTP callouts on hook events                     │
│ Dependencies: Sprint 1 (broadcaster pattern)                                 │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Sprint 9: Python Plugins                                                     │
│ HOOK_EXTENSIONS Phase 3                                                      │
│                                                                              │
│ Deliverable: Dynamic plugin loading, custom hook handlers                   │
│ Dependencies: Sprint 1                                                       │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Sprint 10: Workflow CLI & MCP Tools                                          │
│ WORKFLOWS Phases 7-8                                                         │
│                                                                              │
│ Deliverable: gobby workflow commands, workflow MCP tools                    │
│ Dependencies: Sprint 7                                                       │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Sprint 11: Workflow-Task Integration                                         │
│ TASKS Phases 11-13                                                           │
│                                                                              │
│ Deliverable: Tasks linked to workflows, LLM expansion, agent instructions   │
│ Dependencies: Sprint 3 + Sprint 7                                            │
└─────────────────────────────────────────────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════════════════
                              MCP PROXY ENHANCEMENTS
═══════════════════════════════════════════════════════════════════════════════

┌─────────────────────────────────────────────────────────────────────────────┐
│ Sprint 12: Tool Metrics                                                      │
│ MCP_PROXY_IMPROVEMENTS Phase 1                                               │
│                                                                              │
│ Deliverable: Track tool call/success rates, expose in recommendations       │
│ Dependencies: None                                                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Sprint 13: Lazy Server Init                                                  │
│ MCP_PROXY_IMPROVEMENTS Phase 2                                               │
│                                                                              │
│ Deliverable: Deferred MCP server connections, faster startup                │
│ Dependencies: None                                                           │
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
│ Sprint 15: Self-Healing & Incremental Indexing                               │
│ MCP_PROXY_IMPROVEMENTS Phases 4-5                                            │
│                                                                              │
│ Deliverable: Fallback suggestions on failure, hash-based schema refresh     │
│ Dependencies: Sprint 14                                                      │
└─────────────────────────────────────────────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════════════════
                              POLISH & DOCUMENTATION
═══════════════════════════════════════════════════════════════════════════════

┌─────────────────────────────────────────────────────────────────────────────┐
│ Sprint 16: Hook Extensions CLI & Workflow Integration                        │
│ HOOK_EXTENSIONS Phases 4-5                                                   │
│                                                                              │
│ Deliverable: Webhook as workflow action, plugin-defined actions/conditions  │
│ Dependencies: Sprint 9 + Sprint 7                                            │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Sprint 17: Testing & Error Recovery                                          │
│ WORKFLOWS Phases 9-11                                                        │
│                                                                              │
│ Deliverable: Comprehensive tests, crash recovery, escape hatches            │
│ Dependencies: Sprint 10                                                      │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Sprint 18: Documentation                                                     │
│ ALL PLANS Documentation Phases                                               │
│                                                                              │
│ Deliverable: User guides, examples, updated CLAUDE.md                       │
│ Dependencies: All previous sprints                                           │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Sprint Summary Table

### MVP Sprints (Completed)

| Sprint | Focus | Plan Reference | Dependencies | Status |
|--------|-------|----------------|--------------|--------|
| 1 | WebSocket Broadcasting | HOOK_EXTENSIONS Phase 1 | None | ✅ Completed |
| 2 | Core Task System | TASKS Phases 1-6 | None | ✅ Completed |
| 3 | Task MCP/CLI | TASKS Phases 7-10 | Sprint 2 | ✅ Completed |
| 3.5 | Task Extensions | TASKS Phases 9.5-9.9 | Sprint 3 | ✅ Completed |
| 4 | Workflow Foundation | WORKFLOWS Phases 0-2 | None | ✅ Completed |
| 5 | Workflow Hooks | WORKFLOWS Phase 3 | Sprint 4 | ✅ Completed (session lifecycle) |
| 6 | Workflow Actions | WORKFLOWS Phase 4 | Sprint 5 | ✅ Completed (all actions) |
| 7 | Context & Templates | WORKFLOWS Phases 5-6 | Sprint 6 | ✅ Completed |
| 7.1 | Session Message Foundation | SESSION_TRACKING Phase 1 | None | ✅ Completed |
| 7.2 | Async Message Processor | SESSION_TRACKING Phase 2 | Sprint 7.1 | ✅ Completed |
| 7.3 | Session Tracking Integration | SESSION_TRACKING Phases 3-4 | Sprint 7.2 | ✅ Completed |
| 7.4 | Multi-CLI Parsers & API | SESSION_TRACKING Phases 5-6 | Sprint 7.3 | ✅ Completed |
| 7.5 | Memory Storage & Operations | MEMORY Phases 1-2 | Sprint 7.4 | ✅ Completed |
| 7.6 | Skill Learning | MEMORY Phases 3-4 | Sprint 7.5 | ✅ Completed |
| 7.7 | Memory MCP/CLI | MEMORY Phases 5-6 | Sprint 7.6 | ✅ Completed |
| 7.8 | Memory Sync & Enhancements | MEMORY Phases 7-10 | Sprint 7.7 | ✅ Completed |
| 14 | Semantic Tool Search | MCP_PROXY Phase 3 | None | ✅ Completed |

### Current Sprint

| Sprint | Focus | Plan Reference | Dependencies | Status |
|--------|-------|----------------|--------------|--------|
| 16.5 | Task System V2 (Commit Linking) | TASKS_V2 Phases 1-4 | Sprint 3 | 🔶 In Progress |

### Upcoming Sprints

| Sprint | Focus | Plan Reference | Dependencies | Status |
|--------|-------|----------------|--------------|--------|
| 8 | Webhooks | HOOK_EXTENSIONS Phase 2 | Sprint 1 | Pending |
| 9 | Python Plugins | HOOK_EXTENSIONS Phase 3 | Sprint 1 | Pending |
| 10 | Workflow CLI/MCP | WORKFLOWS Phases 7-8 | Sprint 7 | Pending |
| 11 | Workflow-Task Integration | TASKS Phases 11-13 | Sprints 3, 7 | Pending |
| 12 | Tool Metrics | MCP_PROXY Phase 1 | None | Pending |
| 13 | Lazy Init | MCP_PROXY Phase 2 | None | Pending |
| 15 | Self-Healing MCP | MCP_PROXY Phases 4-5 | Sprint 14 | Pending |
| 16 | Hook Workflow Integration | HOOK_EXTENSIONS Phases 4-5 | Sprints 7, 9 | Pending |
| 17 | Testing & Recovery | WORKFLOWS Phases 9-11 | Sprint 10 | Pending |
| 18 | Documentation | All Plans | All | Pending |

### Post-MVP Sprints

| Sprint | Focus | Plan Reference | Dependencies | Status |
|--------|-------|----------------|--------------|--------|
| 19 | Session Management Tools | SESSION_MANAGEMENT | Sprint 7.4 | Pending |
| 20 | Task V2: Enhanced Validation | TASKS_V2 Phases 5-9 | Sprint 16.5 | Pending |
| 21 | Worktree Coordination | POST_MVP Phase 1 | Sprint 7.4 | Pending |
| 22 | Merge Resolution | POST_MVP Phase 2 | Sprint 21 | Pending |
| 23 | GitHub Integration | POST_MVP Phase 4 | Sprint 3 | Pending |
| 24 | Linear Integration | POST_MVP Phase 5 | Sprint 3 | Pending |
| 25 | Artifact Index | POST_MVP Phase 7 | Sprint 7.4 | Pending |
| 26 | Enhanced Skill Routing | POST_MVP Phase 8 | Sprint 7.6 | Pending |
| 27 | Semantic Memory Search | POST_MVP Phase 9 | Sprint 7.5 | Pending |
| 28 | Autonomous Work Loop | POST_MVP Phase 10 | Sprints 3, 7 | Pending |
| 29 | Subagent System | SUBAGENTS Phases 1-4 | Sprint 7 | Pending |
| 30 | Web Dashboard | UI Phases 1-7 | Sprint 1 | Pending |

---

## Parallel Tracks

Some sprints can run in parallel if multiple contributors are available:

### Track A: Core Platform

Sprints 1 → 4 → 5 → 6 → 7 → 10 → 17

### Track B: Task System

Sprints 2 → 3 → 3.5 → 16.5 → 20 → 11 (Task V2 then workflow integration)

### Track C: Hook Extensions

Sprints 1 → 8 → 9 → 16 (joins Track A at Sprint 7)

### Track D: MCP Improvements

Sprints 12 → 13 → 14 → 15 (independent, can run anytime)

### Track E: Session & Memory

Sprints 7.1 → 7.2 → 7.3 → 7.4 → 7.5 → 7.6 → 7.7 → 7.8 (Session Tracking feeds Memory System)

### Track F: Post-MVP Intelligence

Sprints 25 → 26 → 27 → 28 (Artifact Index → Skill Routing → Semantic Memory → Autonomous Loop)

### Track G: Integrations

Sprints 21 → 22 → 23 → 24 (Worktrees → Merge → GitHub → Linear)

### Track H: Agent Orchestration

Sprint 29 (Subagent System - can start after Sprint 7)

### Track I: Visualization

Sprint 30 (Web Dashboard - can start after Sprint 1)

---

## Milestones

### Milestone 1: "Observable Gobby" (Sprints 1-3) ✅ COMPLETE

- WebSocket event streaming
- Full task system with CLI
- **Value**: External tools can monitor sessions, agents can track work

### Milestone 2: "Workflow Engine" (Sprints 4-7) ✅ COMPLETE

- [x] Workflow foundation (loader, state manager, engine)
- [x] Session lifecycle hooks (session_start, session_end)
- [x] Handoff actions (find_parent, restore_context, generate_handoff)
- [x] LLM-powered session summaries with context handoff
- [x] Context sources (previous_session_summary, handoff, artifacts, observations, workflow_state)
- [x] Jinja2 templating for context injection
- [x] All 7 built-in templates (session-handoff, plan-execute, react, plan-act-reflect, plan-to-tasks, architect, test-driven)
- **Value**: Complete workflow templating system ready for phase-based enforcement

### Milestone 2.5: "Session Recording" (Sprints 7.1-7.4) ✅ COMPLETE

- Async JSONL message processing for all CLIs
- Multi-CLI parsers (Claude, Gemini, Codex, Antigravity)
- Real-time WebSocket message streaming
- Message search and query API
- **Value**: Full conversation history for memory, analytics, and debugging

### Milestone 3: "Memory-First Agents" (Sprints 7.5-7.8) ✅ COMPLETE

- [x] Persistent memory across sessions (remember/recall/forget operations)
- [x] Skill learning from session trajectories via LLM extraction
- [x] MCP tools for memory and skill management (`gobby-memory`, `gobby-skills`)
- [x] CLI commands for memory and skill operations
- [x] JSONL sync for memories and skills (`.gobby/memories.jsonl`, `.gobby/skills/`)
- [x] Cross-CLI memory sharing via unified storage
- **Value**: Agents that learn and remember like coworkers, not contractors

### Milestone 4: "Extensible Gobby" (Sprints 8-9)

- Webhook integrations
- Python plugin system
- **Value**: Infinite customization without forking

### Milestone 5: "Smart MCP Proxy" (Sprints 12-15) 🔶 PARTIAL

- [ ] Tool metrics and recommendations (Sprint 12)
- [ ] Lazy server initialization (Sprint 13)
- [x] Semantic search with OpenAI embeddings (Sprint 14) ✅
- [ ] Self-healing fallbacks (Sprint 15)
- **Value**: Intelligent tool orchestration across MCP servers
- **Done**: `search_tools` MCP/CLI, `recommend_tools` with semantic/hybrid/llm modes

### Milestone 6: "Production Ready" (Sprints 16-18)

- Full integration
- Comprehensive testing
- Documentation
- **Value**: Ship it!

---

## Post-MVP Milestones

### Milestone 7: "Task System V2" (Sprints 16.5, 20) 🔶 IN PROGRESS

- [x] Commit linking infrastructure (migration, storage) ✅
- [x] MCP tools: `link_commit`, `auto_link_commits`, `get_task_diff` ✅
- [x] CLI commands: `gobby tasks commit link/unlink/auto/list` ✅
- [x] Close_task uses commit-based diff when available ✅
- [ ] Validation history tracking
- [ ] Structured issues with recurring detection
- [ ] Build verification before LLM validation
- [ ] External validator support
- [ ] Escalation workflow
- **Value**: Production-grade QA loops with traceability

### Milestone 8: "Worktree Orchestration" (Sprints 21-22)

- [ ] Daemon-managed worktree registry
- [ ] Agent spawning in worktrees
- [ ] Stale worktree detection and cleanup
- [ ] Tiered merge conflict resolution (Auto-Claude inspired)
- **Value**: True parallel development with multiple agents

### Milestone 9: "External Integrations" (Sprints 23-24)

- [ ] GitHub Issues ↔ gobby-tasks sync
- [ ] PR creation from completed tasks
- [ ] Linear Issues ↔ gobby-tasks sync
- **Value**: Bridge between local AI development and team workflows

### Milestone 10: "Intelligence Layer" (Sprints 25-27)

- [ ] Artifact Index with FTS5 (Continuous-Claude v2 inspired)
- [ ] Enhanced skill routing: USE_EXISTING, IMPROVE, CREATE_NEW, COMPOSE (SkillForge inspired)
- [ ] Semantic memory search with sqlite-vec (KnowNote inspired)
- **Value**: Agents that get smarter over time

### Milestone 11: "Autonomous Execution" (Sprint 28)

- [ ] Multi-surface stop signals (HTTP, MCP, WebSocket, CLI, slash commands)
- [ ] Progress tracking with stuck detection (3 layers)
- [ ] Session chaining for context limits
- [ ] Task-driven work loops
- **Value**: Hands-off task execution overnight

### Milestone 12: "Multi-Agent Orchestration" (Sprint 29)

- [ ] `AgentExecutor` interface with multi-provider support
- [ ] Claude, Gemini, Codex, LiteLLM executors
- [ ] `complete()` tool for structured subagent completion
- [ ] Workflow tool filtering for subagents
- [ ] Agent depth tracking and safety limits
- **Value**: Orchestrate specialized agents with different models

### Milestone 13: "Visual Control Center" (Sprint 30)

- [ ] React + Vite web dashboard
- [ ] Real-time WebSocket updates
- [ ] Task graph visualization (Cytoscape.js)
- [ ] MCP Observatory (server health, tool analytics)
- [ ] Memory & Skills browser
- **Value**: See everything happening across all agents

---

## Quick Start Recommendations

**If you want immediate value**: Start with Sprint 1 (WebSocket broadcasting) - unlocks real-time monitoring.

**If you want agent productivity**: Start with Sprints 2-3 (Task system) - agents can track and manage work.

**If you want deterministic agents**: Start with Sprints 4-7 (Workflow engine) - enforce plan-act-reflect patterns.

**If you want learning agents**: Start with Sprints 7.5-7.8 (Memory system) - agents that remember and improve.

**If you have performance issues**: Start with Sprints 12-13 (Tool metrics + lazy init) - faster startup, better tool selection.

---

## Post-MVP Recommendations

**If you want parallel development**: Start with Sprints 21-22 (Worktree orchestration) - multiple agents working simultaneously.

**If you want better QA**: Start with Sprints 16.5, 20 (Task V2) - commit linking and enhanced validation loops.

**If you want smarter context**: Start with Sprint 25 (Artifact Index) - searchable session history for better handoffs.

**If you want autonomous agents**: Start with Sprint 28 (Autonomous Loop) - hands-off task execution.

**If you want multi-model workflows**: Start with Sprint 29 (Subagent System) - orchestrate Claude, Gemini, Codex together.

**If you want visibility**: Start with Sprint 30 (Web Dashboard) - see everything happening in real-time.
