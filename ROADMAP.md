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
- ✅ Gemini CLI integration ready on your side
- 🚧 Gemini CLI: enable on day-1 when upstream hooks v1 is fully landed and stable (tracked upstream)  [oai_citation:1‡GitHub](https://github.com/google-gemini/gemini-cli/issues/9070?utm_source=chatgpt.com)
- ⚠️ Codex CLI: partial (basic notify/handoff); expand once the right extension points are stable

### Tasks + TDD expansion (red/green/blue)

- ✅ `gobby-tasks` MCP: tasks, labels, dependencies, sync (`.gobby/tasks.jsonl`)
- 🚧 Refactor TDD expansion engine for repeatability + better coverage
- 🧪 Publish comparisons + guidance: “Gobby tasks vs Beads vs Task Master”
  - Beads is dependency-graph-first for agent planning/memory  [oai_citation:2‡GitHub](https://github.com/steveyegge/beads?utm_source=chatgpt.com)

### Workflows

- 🚧 Workflow engine (phases, tool restrictions, exit conditions)
- 🚧 Autonomous runner over a dependency graph (task list execution with guardrails)

### Worktrees

- ✅ Worktree creation + agent spawning primitives
- 🧪 Production hardening + test matrix
- 🗺️ UI integration for worktree lifecycle + agent terminals/PTY

### Memory

- 🚧 `gobby-memory` MCP: lightweight, local, user-initiated memory (fast retrieval, no embeddings required)
- 🗺️ Pluggable Memory API + adapters for popular memory backends (embeddings/vector DBs/graphs/etc.)

### Integrations + extensibility

- ✅ GitHub integration
- ✅ Linear integration
- ✅ Plugin architecture (extensible domains/tools)

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
- 🗺️ Session timeline view (hooks fired, tools invoked, compactions, files changed)
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

### 2) Controlled autonomy (safe automation, not chaos)

- 🗺️ Workflow runner can execute tasks end-to-end with policy constraints
- 🗺️ Guardrails: tool allowlists, budget caps, approvals, rollback strategy
- 🗺️ “Stop/resume” semantics and deterministic replay where possible

### 3) Worktree production readiness

- 🗺️ Cleanup/GC, conflict strategy, concurrency rules
- 🗺️ Run workflows per worktree; merge automation hooks

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

