# Gobby Roadmap

Gobby is a **local-first control plane for AI coding tools**: sessions + hooks + tasks + workflows + MCP at scale.

This roadmap is organized by outcomes (what developers feel), not internal modules.

Legend:

- ✅ Shipped
- 🧪 Beta / needs hardening
- 🚧 In progress
- 🗺️ Planned

---

## Guiding principles

- **Local-first by default** (your code/data stays on your machine)
- **Determinism beats vibes** (hooks + workflows + guardrails)
- **Progressive disclosure everywhere** (tools, schemas, context)
- **Interoperability > lock-in** (plugins + adapters + open interfaces)

---

## Current (shipped + in progress)

### MCP hub + progressive tool discovery

- ✅ Persistent daemon MCP server
- ✅ Downstream MCP proxy with progressive discovery (metadata → schema → call)
- ✅ Tool browsing/search utilities
- ✅ Dynamic MCP server management (add/remove/import)
- 🧪 Harden: timeouts, retries, partial failures, metrics

> Rationale: large MCP toolsets can blow up token usage; progressive discovery / dynamic toolsets is the direction the ecosystem is moving.  [oai_citation:0‡Anthropic](https://www.anthropic.com/engineering/code-execution-with-mcp?utm_source=chatgpt.com)

### Sessions + handoffs

- ✅ Session tracking + local persistence
- ✅ `/clear`, `/compact`, auto-compact: enhanced handoff context + injection
- ✅ Summaries persisted locally

### Hooks (determinism layer)

- ✅ Claude Code hook integration
- ✅ Gemini CLI hook integration
- ✅ Codex CLI: approval handler, context injection, app-server mode routing (0.2.13)

### Tasks + TDD expansion (red/green/blue)

- ✅ `gobby-tasks` MCP: tasks, labels, dependencies, sync (`.gobby/tasks.jsonl`)
- ✅ Commit linking (task IDs in commit messages auto-link)
- ✅ Validation gates (criteria checked before task close)
- ✅ TDD expansion v2: integrated pipeline (context → expand → embedded TDD steps)
- ✅ TF-IDF task search with MCP and CLI interfaces
- ✅ Claude Code Task Interop: transparent sync between CC TaskCreate/TaskUpdate and Gobby tasks
- ✅ Task status simplification (8 → 6 statuses) (0.2.14)
- ✅ Rename task status approved → review_approved + Gantt scheduling fields (0.2.15)
- 🧪 Publish comparisons + guidance: "Gobby tasks vs Beads vs Task Master"
  - Beads is dependency-graph-first for agent planning/memory  [oai_citation:2‡GitHub](https://github.com/steveyegge/beads?utm_source=chatgpt.com)

### Workflows

- ✅ Workflow engine (phases, tool restrictions, exit conditions)
- ✅ Autonomous orchestration: inter-agent messaging, review gates, conductor daemon
- ✅ Skill slash command system rework (0.2.14)
- ✅ Agent-type-aware skill discovery and injection (0.2.14)
- ✅ Visual workflow builder with drag-and-drop canvas, property panel, expression editor (0.2.16)
- ✅ DB-backed workflow definitions with CRUD API and templates (0.2.16)
- ✅ background:true workflow action dispatch (0.2.16)
- ✅ regex_search Jinja2 filter for MCP output extraction (0.2.16)

### Pipeline system

- ✅ PipelineExecutor with exec, prompt, invoke_pipeline step types
- ✅ Approval gates (approve/reject via CLI, MCP, HTTP API)
- ✅ Lobster format import and migration guide
- ✅ WebSocket streaming for pipeline execution
- ✅ Safe expression evaluator for conditions
- ✅ Pipeline CLI, MCP tools, and HTTP API endpoints
- ✅ spawn_session and activate_workflow step types (0.2.15)
- ✅ result_variable and failure handling for run_pipeline action (0.2.15)
- ✅ Pipeline fixes: template_engine/tool_proxy wiring, CallToolResult serialization, default provider for prompt steps (0.2.16)

### Codex adapter enhancements (0.2.13)

- ✅ Approval handler for CodexAppServerClient
- ✅ App-server mode routing for Codex hooks
- ✅ Context injection via translate_from_hook_response
- ✅ context_prefix parameter for start_turn()

### Workflow enhancements (0.2.13)

- ✅ Async WorkflowLoader with aiofiles and mtime-based cache invalidation
- ✅ Shell/run action for workflows (cross-platform)
- ✅ Inject context action (multi-source: skills, task_context, memories)
- ✅ File-based PromptLoader (migrated from config.yaml)
- ✅ Structured HandoffContext with git diff summary
- ✅ Async hook dispatchers
- ✅ Proactive memory capture

### Unified workflow engine (0.2.15)

- ✅ Observer engine with YAML-declared observers and behavior registry
- ✅ Built-in behaviors: task_claim_tracking, detect_plan_mode, mcp_call_tracking
- ✅ Plugin support for custom observer behaviors
- ✅ Unified evaluator: single evaluation loop replacing fragmented evaluators
- ✅ Named rule definitions with RuleStore (three-tier CRUD + bundled sync)
- ✅ Multi-workflow support: WorkflowInstanceManager, concurrent workflow instances per session
- ✅ Session variables: shared state visible across all workflow instances
- ✅ Scoped variable MCP tools (get/set)
- ✅ tool_rules field on WorkflowDefinition with lifecycle evaluation
- ✅ Unified workflow format: lifecycle + step YAMLs migrated to single format
- ✅ enabled/priority fields replace type field for workflow distinction
- ✅ exit_when shorthand and expression-based exit conditions
- ✅ SafeExpressionEvaluator replacing eval() in ConditionEvaluator
- ✅ spawn_session and activate_workflow pipeline step types
- ✅ result_variable and failure handling for run_pipeline action

### Strangler fig decomposition wave 2 (0.2.15)

- ✅ workflow/loader.py → loader_cache.py, loader_discovery.py, loader_validation.py, loader_sync.py
- ✅ workflow/engine.py → engine_models.py, engine_context.py, engine_transitions.py, engine_activation.py
- ✅ memory/manager.py → services/embeddings.py, services/mem0_sync.py, services/graph.py, services/maintenance.py
- ✅ cli/installers/shared.py → installers/mcp_config.py, skill_install.py, ide_config.py
- ✅ runner.py → runner_models.py, runner_tracking.py, runner_queries.py
- ✅ Removed re-exports from loader.py, engine.py, shared.py, runner.py — canonical imports only

### Config system (0.2.15)

- ✅ DB-first config resolution — store config in SQLite instead of YAML
- ✅ $secret:NAME config pattern for secrets-store-only resolution
- ✅ Secrets store priority: secrets store first, env vars as fallback
- ✅ Config write isolation + lightweight health endpoint
- ✅ gobby-config MCP server for agent config access

### Memory v5: Qdrant + Knowledge Graph (0.2.16)

- ✅ Replace Mem0 with native Qdrant-based VectorStore
- ✅ MemoryManager rewritten to use VectorStore with method names matching MCP tools
- ✅ LLM-powered fact extraction, dedup decision, entity/relationship extraction prompt templates
- ✅ DedupService for LLM-based memory deduplication (fire-and-forget)
- ✅ KnowledgeGraphService with entity/relationship extraction wired into MemoryManager
- ✅ search_knowledge_graph MCP tool (replaces export_memory_graph)
- ✅ Standalone docker-compose.neo4j.yml and installer; CLI --mem0 replaced with --neo4j
- ✅ generate_json() added to LLM providers for structured output
- ✅ Migrations 103-104: drop memory_embeddings table and mem0_id column
- ✅ Complete removal of Mem0 dependency, imports, config fields, and tests

### Mem0 + memory improvements (0.2.15)

- ✅ Async Mem0 queueing with background sync
- ✅ Configurable mem0 client timeout (default 90s)
- ✅ Mem0 Docker setup fixes (correct image, env vars, neo4j credentials)
- ✅ Knowledge graph idle animation with manual camera rotation

### Terminal + tmux (0.2.15)

- ✅ Consolidated terminal spawners to tmux-only
- ✅ Tmux window rename after title synthesis
- ✅ TmuxPaneMonitor for detecting dead panes
- ✅ Permanent set-titles-string and IDE terminal title auto-config
- ✅ Show terminal title instead of tmux pane ID
- ✅ Terminal rename via double-click

### Web UI

- ✅ Chat interface with React + Vite and MCP tool support
- ✅ Terminal panel with xterm.js
- ✅ Syntax highlighting, streaming, chat history persistence
- ✅ Auto-start with daemon
- ✅ Tasks page: kanban board, tree view, dependency graph, Gantt chart, detail panel, creation form, comments, handoff, assignee management, audit log, oversight views (0.2.14)
- ✅ Memory page: table, filters, graph view, Neo4j 3D knowledge graph (0.2.14)
- ✅ Sessions page: lineage tree, transcript viewer, AI summary generation (0.2.14)
- ✅ Chat: Claude SDK backend, model switching, AskUserQuestion interactive UI, voice chat (0.2.14)
- ✅ Cron Jobs page with two-panel layout (0.2.14)
- ✅ Configuration page with secrets, prompts, raw YAML (0.2.14)
- ✅ Skills page with CRUD, hub browsing, safety scanning (0.2.14)
- ✅ Unified Projects page (0.2.14)
- ✅ DB-backed agent registry + configuration catalog UI (0.2.14)
- ✅ File browser/viewer/editor (0.2.14)
- ✅ File editor: save/cancel with confirmation, undo/redo (0.2.15)
- ✅ Agent definition editing from UI (0.2.15)
- ✅ Needs Review + In Review overview cards for tasks and memory (0.2.15)
- ✅ Web UI accessible over Tailscale (0.2.15)
- ✅ Auto-start Vite dev server on daemon startup (0.2.15)
- ✅ Standardized sidebar widths via CSS variable (0.2.15)
- ✅ Visual workflow builder with @xyflow/react: canvas, dagre layout, node types, property panel, expression editor, settings modal, save/load (0.2.16)
- ✅ Workflows page: list view, templates API, DB-backed CRUD (0.2.16)
- ✅ Mobile chat: drawer replacing sidebar, click-outside-to-close, conversation picker toggle (0.2.16)
- ✅ Chat: delete chat, resume placeholder for remote sessions, stale event drain on interrupt (0.2.16)
- 🗺️ Hook inspector

### Worktrees

- ✅ Worktree creation + agent spawning primitives
- 🧪 Production hardening + test matrix
- 🗺️ UI integration for worktree lifecycle + agent terminals/PTY

### Memory

- ✅ `gobby-memory` MCP: lightweight, local, user-initiated memory (TF-IDF search)
- ✅ Memory v3: backend abstraction layer (SQLite, MemU, Mem0, OpenMemory)
- ✅ Memory v4: embedding persistence, lifecycle hooks, reindex CLI, automated capture (0.2.14)
- ✅ Mem0 integration with Docker-compose bundle (0.2.14)
- ✅ Memory v4.5: async Mem0 queueing, configurable timeouts, background sync (0.2.15)
- ✅ Memory v5: Qdrant vector store, LLM-powered dedup/extraction, KnowledgeGraphService, Mem0 fully removed (0.2.16)

### Integrations + extensibility

- ✅ GitHub integration
- ✅ Linear integration
- ✅ Plugin architecture (extensible domains/tools)
- ✅ Gobby-plugins internal MCP server (0.2.14)

### Skills system

- ✅ `gobby-skills` MCP: list, search, install, update, remove
- ✅ SKILL.md format (Agent Skills spec + SkillPort compatible)
- ✅ Core skills bundled with Gobby
- ✅ TF-IDF search for skill discovery
- ✅ Install from GitHub, local paths, ZIP archives
- ✅ Project-scoped and global skill management
- ✅ Skill profile replaced with typed SkillProfileConfig model (0.2.14)
- ✅ Skill usage tracking in get_skill() MCP handler (0.2.15)
- ✅ Skills-used tracking in session stats (0.2.15)

### Orchestration

- ✅ Coordinator pipeline + developer/QA step workflows (0.2.14)
- ✅ Atomic slot reservation and partial failure recovery (0.2.14)
- 🧪 Conductor daemon: persistent monitoring, TARS-style haiku status
- 🧪 Inter-agent messaging: parent↔child message passing during execution
- 🧪 Token budget tracking: aggregation, pricing, throttling
- 🧪 Review gates: `review` status, blocking wait tools
- 🧪 Callme alerts: plumbing ready, needs MCP client wiring

### Agent spawning

- ✅ Unified `spawn_agent` API with `isolation`: current, worktree, clone
- ✅ Model passthrough and terminal override
- ✅ Tmux promoted to first-class agent spawning module (0.2.14)
- ✅ Auto terminal detection prefers tmux when installed (0.2.14)
- ✅ Automatic interactive/autonomous mode via tmux focus (0.2.14)
- ✅ DB-backed agent registry with prompt fields and YAML export (0.2.14)
- ✅ Provider-dependent model selection in agent definitions (0.2.15)
- ✅ Running agents tracking on agents page (0.2.15)

### Cron scheduler (0.2.14)

- ✅ Storage foundation and config
- ✅ Scheduler engine with executor and runner integration
- ✅ CLI, HTTP, and MCP interfaces

### Code decomposition

- ✅ Round 1: mcp/tools.py, workflows/actions.py, event_handlers.py, adapters/codex.py
- ✅ Round 2: websocket.py, claude.py, skills.py, sessions.py, hook_manager.py (0.2.14)
- ✅ Orchestration tools extracted to standalone gobby-orchestration server (0.2.14)
- ✅ Round 3 (strangler fig wave 2): loader.py, engine.py, runner.py, shared.py, memory/manager.py decomposed into 20+ focused modules (0.2.15)
- ✅ Removed re-export shims — canonical imports only (0.2.15)
- ✅ Removed hardcoded model aliases and resolve_model_id (0.2.15)

### Personal workspace (0.2.14)

- ✅ Project-optional tasks with personal workspace fallbacks + project filter

### Project management v2

- ✅ Rename, delete, update, repair CLI commands

---

## Current work (in progress)

### Database-backed prompt storage

- 🚧 Migrate prompts from filesystem to SQLite (three-tier: bundled → global → project)
- 🚧 `LocalPromptManager` with bundled read-only enforcement (dev mode exception)
- 🚧 `PromptLoader` refactor: database-only at runtime, no filesystem fallback

### Coordinator finalization

- 🚧 Production-ready orchestration with review/merge cycles
- 🚧 Finalizing coordinator workflow end-to-end

### Web UI polish

- 🚧 Mobile responsiveness and UX improvements
- 🚧 Visual workflow builder: additional node types, validation, undo/redo

---

## Next (make it undeniable)

Goal: a developer installs Gobby and immediately understands the value in minutes.

### 1) Workflow engine simplification

- 🗺️ Unify evaluators and named rule definitions
- 🗺️ tool_rules shorthand syntax
- 🗺️ Hybrid observer registry
- 🗺️ Simplify exit conditions

### 2) Task expansion into workflows

- 🗺️ Research agent for context gathering
- 🗺️ Expansion workflow with validation workflow
- 🗺️ Coordinator integration
- 🗺️ Task-ops agent

### ~~3) Artifact system removal~~ ✅ Done (0.2.15)

### 4) CLI auto-detection

- 🗺️ Auto-discover CLIs, auth modes, models at daemon startup
- 🗺️ Replace manual llm_providers config

### 5) Security posture for tool access (must-have for "1000 MCP servers")

- 🗺️ MCP server allow/deny lists
- 🗺️ Quarantine unknown servers until approved
- 🗺️ Per-tool risk levels + confirmation gates (filesystem write, shell, network, etc.)
- 🗺️ Audit log for tool calls (who/what/when/args summary)

### 6) SWE-bench evaluation

- 🗺️ Evaluation infrastructure for SWE-bench Lite/Verified/Live
- 🗺️ Track scores over time, A/B test Gobby features
- 🗺️ Leaderboard submission when ready to show off

### 7) Flagship demos (distribution)

- 🗺️ "MCP at scale without token tax" demo (progressive discovery)
- 🗺️ "Spec → tasks → TDD red/green/blue → validated PR" demo
- 🗺️ "Hooks enforce discipline" demo pack (format/lint/test gates)

### 8) Bug fix sprint

- 🗺️ Stabilization pass across the platform

---

## Near term (make it visible: autonomy + production readiness)

Goal: reduce cognitive load; make the daemon's behavior legible.

### 1) Additional CLI support

- ✅ Cursor (0.2.10)
- ✅ Windsurf (0.2.10)
- ✅ Copilot (0.2.10)
- 🗺️ Aider
- 🗺️ Continue
- 🗺️ Amazon Q Developer CLI

### 2) Worktree production readiness

- 🗺️ Cleanup/GC, conflict strategy, concurrency rules
- 🗺️ Run workflows per worktree; merge automation hooks

### 3) Remote access

- 🗺️ Authentication for daemon HTTP/WebSocket endpoints
- 🗺️ Tailscale integration for secure remote access
- 🗺️ SSH tunneling support

### 4) Production-ready workflows

- 🗺️ Automated code review pipelines
- 🗺️ Retry logic and error recovery
- 🗺️ Parallel worker execution

### 5) Plugin ecosystem v2

- 🗺️ Dedicated MCP server for plugin management
- 🗺️ Plugin registry conventions + compatibility checks

### 6) Multi-agent orchestration improvements

- 🗺️ P2P mailboxes for agent communication
- 🗺️ Agent checkpointing and resume

---

## Longer term (ecosystem + enterprise hardening)

Goal: make Gobby the obvious substrate for serious local agentic coding.

### 1) Observability + OpenTelemetry

- 🗺️ Tool call tracing (latency, success/error, payload size)
- 🗺️ Session timeline view (event stream: hooks fired, tools invoked, compactions, files changed)
- 🗺️ Replace custom logging/metrics with OpenTelemetry
- 🗺️ OTLP export + console fallback for local dev
- 🗺️ Exportable run reports (for PR descriptions / team sharing)

### 2) Memory adapters + open Memory API

- ✅ Qdrant vector store adapter (0.2.16)
- ✅ Neo4j knowledge graph adapter with entity/relationship extraction (0.2.16)
- 🗺️ Stable Memory API (store/retrieve/summarize/evict)
- 🗺️ Additional vector DB adapters (Chroma, Weaviate, etc.)
- 🗺️ Clear guidance: baseline local memory vs advanced backends

### 3) Plugin ecosystem + templates

- 🗺️ Curated "starter packs" (hooks + workflows + tasks) by stack (Python/Node/Go/etc.)
- 🗺️ Plugin registry conventions + compatibility checks
- 🗺️ Community examples: integrations, workflows, hook packs

---

## Explicit non-goals (unless proven necessary)

- Moving core execution to a hosted SaaS
- Forcing a single agent framework
- Hiding behavior behind "magic prompts"

Gobby wins by being the **boring, reliable system layer** under your AI tools.
