# Gobby Implementation Roadmap

## Overview

This document defines the implementation order across all Gobby planning documents. Each phase is designed to deliver standalone value while building toward the complete vision: transforming Gobby from a session tracker into a full **agent orchestration platform**.

## Document References

### Completed Plans

| Document               | Location                                           | Focus                                                      |
| ---------------------- | -------------------------------------------------- | ---------------------------------------------------------- |
| WORKFLOWS              | `docs/plans/completed/WORKFLOWS.md`                | Step-based workflow enforcement                            |
| TASKS                  | `docs/plans/completed/TASKS.md`                    | Persistent task tracking system (includes V2 enhancements) |
| SESSION_TRACKING       | `docs/plans/completed/SESSION_TRACKING.md`         | Async JSONL processing, multi-CLI message storage          |
| SESSION_MANAGEMENT     | `docs/plans/completed/SESSION_MANAGEMENT.md`       | Session CRUD tools, handoff MCP tools                      |
| HOOK_EXTENSIONS        | `docs/plans/completed/HOOK_EXTENSIONS.md`          | WebSocket events, webhooks, plugins                        |
| MCP_PROXY_IMPROVEMENTS | `docs/plans/completed/MCP_PROXY_IMPROVEMENTS.md`   | Tool metrics, semantic search, self-healing                |
| MEMORY                 | `docs/plans/completed/MEMORY.md`                   | Persistent memory system                                   |
| AUTONOMOUS_HANDOFF     | `docs/plans/completed/AUTONOMOUS_HANDOFF.md`       | Pre-compact context extraction, session chaining           |
| SUBAGENTS              | `docs/plans/completed/SUBAGENTS.md`                | Multi-provider agent spawning system                       |

### Post-MVP Plans

| Document     | Location                     | Focus                                                                          | Status  |
| ------------ | ---------------------------- | ------------------------------------------------------------------------------ | ------- |
| ENHANCEMENTS | `docs/plans/enhancements.md` | 10 major phases: worktrees, merge resolution, GitHub/Linear, autonomous loops  | Partial |
| UI           | `docs/plans/UI.md`           | Web dashboard, real-time visualization                                         | Pending |

## Sprint Summary Table

### Completed Sprints

| Focus                        | Plan Reference                             |
| ---------------------------- | ------------------------------------------ |
| WebSocket Broadcasting       | HOOK_EXTENSIONS Phase 1                    |
| Core Task System             | TASKS Phases 1-6                           |
| Task MCP/CLI                 | TASKS Phases 7-10                          |
| Task Extensions              | TASKS Phases 9.5-9.9                       |
| Workflow Foundation          | WORKFLOWS Phases 0-2                       |
| Workflow Hooks               | WORKFLOWS Phase 3                          |
| Workflow Actions             | WORKFLOWS Phase 4                          |
| Context & Templates          | WORKFLOWS Phases 5-6                       |
| Session Message Foundation   | SESSION_TRACKING Phase 1                   |
| Async Message Processor      | SESSION_TRACKING Phase 2                   |
| Session Tracking Integration | SESSION_TRACKING Phases 3-4                |
| Multi-CLI Parsers & API      | SESSION_TRACKING Phases 5-6                |
| Memory Storage & Operations  | MEMORY Phases 1-2                          |
| Skill Learning               | MEMORY Phases 3-4                          |
| Memory MCP/CLI               | MEMORY Phases 5-6                          |
| Memory Sync & Enhancements   | MEMORY Phases 7-10                         |
| Webhooks                     | HOOK_EXTENSIONS Phase 2                    |
| Python Plugins               | HOOK_EXTENSIONS Phase 3                    |
| Workflow CLI/MCP             | WORKFLOWS Phases 7-8                       |
| Workflow-Task Integration    | TASKS Phases 11-13                         |
| Tool Metrics                 | MCP_PROXY Phase 1                          |
| Lazy Init                    | MCP_PROXY Phase 2                          |
| Semantic Tool Search         | MCP_PROXY Phase 3                          |
| Self-Healing MCP             | MCP_PROXY Phases 4-5                       |
| Hook Workflow Integration    | HOOK_EXTENSIONS Phases 4-5                 |
| Feature Gap Coverage         | MCP_PROXY, HOOK_EXT, MEMORY, HANDOFF gaps  |
| Session Management Tools     | SESSION_MANAGEMENT                         |
| Subagent System              | SUBAGENTS Phases 1-4                       |

### Remaining Sprints

| Focus                        | Plan Reference             | Notes                                                       |
| ---------------------------- | -------------------------- | ----------------------------------------------------------- |
| Task V2: Enhanced Validation | TASKS Phases 12.6-12.13    | 🔶 Remaining: external validator agent spawning             |
| Worktree Coordination        | ENHANCEMENTS Phase 1       | 🔶 Remaining: tiered merge conflict resolution              |
| Merge Resolution             | ENHANCEMENTS Phase 2       |                                                             |
| GitHub Integration           | ENHANCEMENTS Phase 4       |                                                             |
| Linear Integration           | ENHANCEMENTS Phase 5       |                                                             |
| Artifact Index               | ENHANCEMENTS Phase 6       |                                                             |
| Enhanced Skill Routing       | ENHANCEMENTS Phase 7       |                                                             |
| Semantic Memory Search       | ENHANCEMENTS Phase 8       |                                                             |
| Web Dashboard                | UI Phases 1-7              |                                                             |
| End-to-End Testing           | WORKFLOWS Phases 9-11      |                                                             |
| Documentation                | All Plans, User Guides     |                                                             |

---

## Parallel Tracks

Remaining work can run in parallel if multiple contributors are available:

### Track A: Intelligence

Artifact Index → Enhanced Skill Routing → Semantic Memory Search

### Track B: Integrations

Worktree Coordination → Merge Resolution → GitHub Integration → Linear Integration

### Track C: Visualization

Web Dashboard (can start independently)

### Track D: Final Polish

End-to-End Testing → Documentation (should be last)

---

## Completed Milestones

### "Monitoring" ✅

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
- MCP tools for memory management (`gobby-memory`)
- CLI commands for memory operations
- JSONL sync for memories (`.gobby/memories.jsonl`)
- Cross-CLI memory sharing via unified storage
- **Value**: Agents that remember like coworkers, not contractors

### "Extensible" 🔶

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
- [ ] Linear Issues ↔ gobby-tasks sync - deferred to Post MVP
- **Value**: Bridge between local AI development and team workflows

### "Intelligence Layer"

- [ ] Artifact Index with FTS5
- [ ] Semantic memory search with sqlite-vec
- **Value**: Agents that get smarter over time

### "Autonomous Execution" ✅

- [x] Session chaining for context limits (`autonomous-loop.yaml` workflow)
- [x] Task-driven work loops (`autonomous-task.yaml` workflow with exit conditions)
- [x] Stop signals via HTTP (`POST /sessions/{id}/stop`), StopRegistry, and workflow actions
- [x] Progress tracking (`ProgressTracker`) with stuck detection (`StuckDetector`)
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
