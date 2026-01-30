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
- ✅ Summaries/artifacts persisted locally

### Hooks (determinism layer)

- ✅ Claude Code hook integration
- ✅ Gemini CLI hook integration
- ⚠️ Codex CLI: partial (basic notify/handoff); expand once the right extension points are stable

### Tasks + TDD expansion (red/green/blue)

- ✅ `gobby-tasks` MCP: tasks, labels, dependencies, sync (`.gobby/tasks.jsonl`)
- ✅ Commit linking (task IDs in commit messages auto-link)
- ✅ Validation gates (criteria checked before task close)
- ✅ TDD expansion v2: integrated pipeline (context → expand → embedded TDD steps)
- ✅ TF-IDF task search with MCP and CLI interfaces
- ✅ Claude Code Task Interop: transparent sync between CC TaskCreate/TaskUpdate and Gobby tasks
- 🧪 Publish comparisons + guidance: "Gobby tasks vs Beads vs Task Master"
  - Beads is dependency-graph-first for agent planning/memory  [oai_citation:2‡GitHub](https://github.com/steveyegge/beads?utm_source=chatgpt.com)

### Workflows

- ✅ Workflow engine (phases, tool restrictions, exit conditions)
- ✅ Autonomous orchestration: inter-agent messaging, review gates, conductor daemon

### Worktrees

- ✅ Worktree creation + agent spawning primitives
- 🧪 Production hardening + test matrix
- 🗺️ UI integration for worktree lifecycle + agent terminals/PTY

### Memory

- ✅ `gobby-memory` MCP: lightweight, local, user-initiated memory (TF-IDF search)
- ✅ Memory v3: backend abstraction layer (SQLite, MemU, Mem0, OpenMemory)

### Integrations + extensibility

- ✅ GitHub integration
- ✅ Linear integration
- ✅ Plugin architecture (extensible domains/tools)

### Skills system

- ✅ `gobby-skills` MCP: list, search, install, update, remove
- ✅ SKILL.md format (Agent Skills spec + SkillPort compatible)
- ✅ Core skills bundled with Gobby
- ✅ TF-IDF search for skill discovery
- ✅ Install from GitHub, local paths, ZIP archives
- ✅ Project-scoped and global skill management

### Orchestration (beta - needs testing)

- 🧪 Conductor daemon: persistent monitoring, TARS-style haiku status
- 🧪 Inter-agent messaging: parent↔child message passing during execution
- 🧪 Token budget tracking: aggregation, pricing, throttling
- 🧪 Review gates: `review` status, blocking wait tools
- 🧪 Callme alerts: plumbing ready, needs MCP client wiring

---

## Current work (in progress)

### Skill enhancements

- ✅ Unified `/gobby` router skill (routes to skills and MCP servers)
- ✅ Add `category` and top-level `alwaysApply` support
- 🚧 Remove `gobby-` prefix from skill names

### Agent spawning v2

- ✅ Consolidate `start_agent`, `spawn_agent_in_worktree`, `spawn_agent_in_clone` into unified `spawn_agent` API
- ✅ Add `isolation` parameter: `current`, `worktree`, `clone`
- 🚧 Auto-generate branch names from task titles

### Code decomposition (strangler fig)

- ✅ Break up `mcp/tools.py` into domain-specific endpoints
- ✅ Break up `workflows/actions.py` into action handlers
- ✅ Break up `event_handlers.py` into domain-specific modules
- ✅ Break up `adapters/codex.py` into `codex_impl/` package (types/client/adapter)
- 🚧 Break up `mcp_proxy/tools/worktrees.py` into granular toolsets

### API versioning

- 🚧 Add `/api/v1.0` prefix to all API endpoints
- 🚧 Update clients and tests

### Migration flattening

- ✅ Flatten migrations into baseline schema (BASELINE_SCHEMA_V2)
- 🚧 Delete `migrations_legacy.py`

---

## Next (make it undeniable)

Goal: a developer installs Gobby and immediately understands the value in minutes.

### 1) Security posture for tool access (must-have for “1000 MCP servers”)

- 🗺️ MCP server allow/deny lists
- 🗺️ Quarantine unknown servers until approved
- 🗺️ Per-tool risk levels + confirmation gates (filesystem write, shell, network, etc.)
- 🗺️ Audit log for tool calls (who/what/when/args summary)

### 2) Observability (debugging + trust)

- 🗺️ Tool call tracing (latency, success/error, payload size)
- 🗺️ Session timeline view (event stream: hooks fired, tools invoked, compactions, files changed - distinct from session transcripts which capture raw conversation)
- 🗺️ Exportable run reports (for PR descriptions / team sharing)

### 3) Flagship demos (distribution)

- 🗺️ “MCP at scale without token tax” demo (progressive discovery)
- 🗺️ “Spec → tasks → TDD red/green/blue → validated PR” demo
- 🗺️ “Hooks enforce discipline” demo pack (format/lint/test gates)

---

## Near term (make it visible: UI + autonomy foundations)

Goal: reduce cognitive load; make the daemon’s behavior legible.

### 1) Minimal Web UI (read-only first)

- 🗺️ Sessions list + handoff summaries
- 🗺️ Task graph view (deps, blocked/ready, validation status)
- 🗺️ MCP servers + tools browser (search → schema → call)
- 🗺️ Workflow run status + logs
- 🗺️ Hook inspector (what ran, what changed, what was blocked)

### 2) Additional CLI support

- 🗺️ GitHub Copilot CLI
- 🗺️ Cursor IDE / Cursor CLI
- 🗺️ Aider
- 🗺️ Continue
- 🗺️ Amazon Q Developer CLI
- 🗺️ Other emerging coding agent CLIs

### 3) Worktree production readiness

- 🗺️ Cleanup/GC, conflict strategy, concurrency rules
- 🗺️ Run workflows per worktree; merge automation hooks

### 4) OpenTelemetry (optional enhancement)

- 🗺️ Replace custom logging/metrics with OpenTelemetry
- 🗺️ OTLP export + console fallback for local dev
- 🗺️ Tracing infrastructure ready for future fleet observability

### 5) SWE-bench evaluation

- 🗺️ Evaluation infrastructure for SWE-bench Lite/Verified/Live
- 🗺️ Track scores over time, A/B test Gobby features
- 🗺️ Leaderboard submission when ready to show off

---

## Longer term (ecosystem + enterprise hardening)

Goal: make Gobby the obvious substrate for serious local agentic coding.

### 1) Memory adapters + open Memory API

- 🗺️ Stable Memory API (store/retrieve/summarize/evict)
- 🗺️ Adapters for popular memory systems (vector DBs, knowledge graphs, etc.)
- 🗺️ Clear guidance: baseline local memory vs advanced backends

### 2) Plugin ecosystem + templates

- 🗺️ Curated “starter packs” (hooks + workflows + tasks) by stack (Python/Node/Go/etc.)
- 🗺️ Plugin registry conventions + compatibility checks
- 🗺️ Community examples: integrations, workflows, hook packs

### 3) Team workflows (still local-first)

- 🗺️ Optional shared artifacts (sanitized session summaries, workflow outcomes)
- 🗺️ Multi-dev coordination patterns without centralizing code/data
- 🗺️ Policy packs (security/logging/compliance defaults)

---

## Explicit non-goals (unless proven necessary)

- Moving core execution to a hosted SaaS
- Forcing a single agent framework
- Hiding behavior behind “magic prompts”

Gobby wins by being the **boring, reliable system layer** under your AI tools.

