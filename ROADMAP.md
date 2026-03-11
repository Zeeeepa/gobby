# Gobby Roadmap

Gobby is a **local-first control plane for AI coding tools**: sessions + hooks + tasks + workflows + MCP at scale.

Legend:

- ✅ Shipped
- 🚧 In progress
- 🗺️ Planned

---

## Guiding principles

- **Local-first by default** (your code/data stays on your machine)
- **Determinism beats vibes** (hooks + workflows + guardrails)
- **Progressive discovery everywhere** (tools, schemas, context)
- **Interoperability > lock-in** (plugins + adapters + open interfaces)

---

## Shipped

### MCP hub + progressive tool discovery

- ✅ Persistent daemon MCP server
- ✅ Downstream MCP proxy with progressive discovery (metadata → schema → call)
- ✅ Tool browsing/search utilities
- ✅ Dynamic MCP server management (add/remove/import)

### Sessions + handoffs

- ✅ Session tracking + local persistence
- ✅ Auto-compact, `/clear`, `/compact` with enhanced handoff context + injection
- ✅ Session handoff & digest overhaul (0.2.23)
- ✅ Session title synthesis (0.2.23)

### Hooks (determinism layer)

- ✅ Claude Code hook integration
- ✅ Gemini CLI hook integration
- ✅ Codex CLI: approval handler, context injection, app-server mode routing (0.2.13)
- ✅ Cursor, Windsurf, Copilot adapters (0.2.10)

### Tasks + TDD expansion

- ✅ `gobby-tasks` MCP: tasks, labels, dependencies, sync (`.gobby/tasks.jsonl`)
- ✅ Commit linking, validation gates, TDD expansion v2
- ✅ TF-IDF task search, Claude Code task interop
- ✅ Task status simplification (8 → 6 statuses), Gantt scheduling fields

### Rule engine

- ✅ Declarative rule enforcement (block, inject_context, set_variable, mcp_call)
- ✅ Named rule definitions with RuleStore (three-tier CRUD + bundled sync)
- ✅ 13 bundled rule groups
- ✅ SafeExpressionEvaluator replacing eval()
- ✅ Stop-gate & tool error recovery — hardcoded engine plumbing (0.2.23)

### Pipeline system

- ✅ PipelineExecutor with exec, prompt, invoke_pipeline, spawn_session, activate_workflow step types
- ✅ Approval gates, safe expression evaluator, result_variable, failure handling
- ✅ Lobster format import, WebSocket streaming
- ✅ CLI, MCP tools, and HTTP API endpoints
- ✅ Orchestrator pipeline with step workflow enforcement (0.2.23)
- ✅ Pipeline resume on daemon restart (0.2.23)

### Orchestration + agents

- ✅ Coordinator pipeline + developer/QA/merge agent trio (0.2.23)
- ✅ Autonomous SDK agent execution (0.2.23)
- ✅ Unified `spawn_agent` API with isolation: current, worktree, clone
- ✅ DB-backed agent registry with prompt fields and YAML export
- ✅ Tmux first-class agent spawning, auto terminal detection
- ✅ Inter-agent messaging: parent↔child message passing
- ✅ Conductor daemon, token budget tracking, review gates
- ✅ Orchestration v3: tick-based pipeline, clone-based isolation, single clone per epic (0.2.28)
- ✅ Provider fallback rotation — comma-separated provider lists with auto-retry (0.2.28)
- ✅ Provider stall detection — lifecycle monitor triggers rotation on provider-side stalls (0.2.28)
- ✅ QA-Dev agent template — reviews AND fixes in one pass (0.2.28)
- ✅ Agent idle detection + stalled buffer detection (0.2.28)
- ✅ Persistent agent runtime state survives daemon restarts (0.2.28)

### Workflows

- ✅ Observer engine with YAML-declared observers and behavior registry
- ✅ Multi-workflow support with concurrent instances per session
- ✅ Session variables, scoped variable MCP tools
- ✅ Unified workflow format (lifecycle + step YAMLs migrated)
- ✅ Legacy workflow system removal — WorkflowEngine, step/lifecycle, legacy digest (0.2.23)

### Memory

- ✅ `gobby-memory` MCP: lightweight, local, user-initiated memory (TF-IDF search)
- ✅ Memory v3–v4: backend abstraction, embedding persistence, lifecycle hooks, automated capture
- ✅ Memory v5: Qdrant vector store, LLM-powered dedup/extraction, KnowledgeGraphService, Mem0 fully removed (0.2.16)

### Web UI

- ✅ Chat with MCP tool support, voice chat (VAD), model switching, slash commands
- ✅ Tasks: kanban board, tree view, dependency graph, Gantt chart, detail panel, creation form
- ✅ Memory: table, filters, Neo4j 3D knowledge graph
- ✅ Sessions: lineage tree, transcript viewer, AI summary generation
- ✅ Cron Jobs, Configuration, Skills, Projects, Agent Registry pages
- ✅ File browser/editor with save/cancel, undo/redo
- ✅ Visual workflow builder with @xyflow/react (0.2.16)
- ✅ Smart tool headers, improved tool rendering (0.2.23)
- ✅ Mobile: drawer replacing sidebar, click-outside-to-close, conversation picker toggle (0.2.23)

### Skills system

- ✅ `gobby-skills` MCP: list, search, install, update, remove
- ✅ SKILL.md format (Agent Skills spec + SkillPort compatible)
- ✅ Core skills bundled, TF-IDF search, install from GitHub/local/ZIP
- ✅ Skill usage tracking in session stats

### Integrations + extensibility

- ✅ GitHub integration, Linear integration
- ✅ Plugin architecture (extensible domains/tools)

### OpenTelemetry observability

- ✅ Tool call tracing (latency, success/error, payload size) (0.2.28)
- ✅ Metrics instruments for MCP calls, pipelines, tasks, hooks (0.2.28)
- ✅ Replace custom logging/metrics with OpenTelemetry logging bridge (0.2.28)
- ✅ OTLP gRPC export + Prometheus exporter (0.2.28)
- ✅ Trace viewer UI: TracesPage, TraceWaterfall, TraceDetail (0.2.28)
- ✅ SQLite span storage with trace query API (0.2.28)
- Built autonomously via orchestrator pipeline — Epic #9915, 10 tasks, ~3 hours

### Infrastructure

- ✅ DB-first config resolution, $secret:NAME pattern, encrypted secrets store
- ✅ Cron scheduler with CLI, HTTP, and MCP interfaces
- ✅ Code decomposition rounds 1–3 (strangler fig), canonical imports only
- ✅ Worktree creation + agent spawning primitives
- ✅ Terminal: consolidated tmux spawners, pane monitoring, title synthesis
- ✅ Native AST code indexing via gobby-code server (0.2.26)
- ✅ `gobby secrets` CLI with encrypted store (0.2.28)

---

## In progress — v1 release prep

Orchestration v3 is complete and in battle-hardening. Focus is now on stability, polish, and documentation for the first stable release.

- 🚧 Bug fixing and orchestration battle-hardening
- 🚧 Documentation refresh (guides, changelog, README)
- 🚧 Mobile responsiveness pass
- 🚧 Visual workflow builder completion (additional node types, validation, undo/redo)
- 🚧 Hook inspector
- 🚧 General UX polish pass

---

## After v1

### Ollama support

- 🗺️ Local model provider for chat, task expansion, summarization

---

## Future

### Pro / cloud features

- 🗺️ Fleet management (multi-machine coordination)
- 🗺️ Team workflows and shared task boards
- 🗺️ Enterprise hardening (auth, audit, compliance)

### Plugin ecosystem v2

- 🗺️ Dedicated MCP server for plugin management
- 🗺️ Plugin registry conventions + compatibility checks
- 🗺️ Community examples: integrations, workflows, hook packs

### Additional CLI support

- 🗺️ Aider
- 🗺️ Continue
- 🗺️ Amazon Q Developer CLI

### Additional memory adapters

- 🗺️ Stable Memory API (store/retrieve/summarize/evict)
- 🗺️ Additional vector DB adapters (Chroma, Weaviate, etc.)

### Starter packs

- 🗺️ Curated hook + workflow + task bundles by stack (Python/Node/Go/etc.)

---

## Explicit non-goals (unless proven necessary)

- Moving core execution to a hosted SaaS
- Forcing a single agent framework
- Hiding behavior behind "magic prompts"

Gobby wins by being the **boring, reliable system layer** under your AI tools.
