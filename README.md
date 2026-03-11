<!-- markdownlint-disable MD033 MD041 -->
<p align="center">
  <img src="logo.png" alt="Gobby" width="200" />
</p>

<h1 align="center">Gobby</h1>

<p align="center">
  <strong>The control plane for AI coding tools.</strong><br>
  One daemon. All your agents. No more context window roulette.
</p>

<p align="center">
  <a href="https://github.com/GobbyAI/gobby"><img src="built-with-gobby.svg" alt="Built with Gobby"></a>
  <a href="https://github.com/GobbyAI/gobby/blob/main/LICENSE.md"><img src="https://img.shields.io/badge/license-Apache%202.0-blue.svg" alt="License"></a>
  <a href="https://github.com/GobbyAI/gobby/stargazers"><img src="https://img.shields.io/github/stars/GobbyAI/gobby?style=flat" alt="Stars"></a>
  <a href="https://github.com/GobbyAI/gobby/issues"><img src="https://img.shields.io/github/issues/GobbyAI/gobby" alt="Issues"></a>
</p>

---

Gobby is a local-first daemon that unifies your AI coding assistants—Claude Code, Gemini CLI, Cursor, Windsurf, Copilot, and Codex—under one persistent, extensible platform. It handles the stuff these tools forget: sessions that survive restarts, context that carries across compactions, declarative rules that keep agents from going off the rails, and an MCP proxy that doesn't eat half your context window just loading tool definitions.

**Gobby is built with Gobby.** Most of this codebase was written by AI agents running through Gobby's own task system and workflows — over 10,000 tasks tracked and counting. Case in point: the entire OpenTelemetry observability stack (tracing, metrics, logging bridge, trace viewer UI) was built autonomously — 10 tasks dispatched across Gemini devs and Claude Opus reviewers, orchestrated by a cron-driven pipeline, completed in ~3 hours with six infrastructure bugs discovered and fixed live. See [test-battery.md](test-battery.md) for the full story.

Note: Gobby is currently in alpha. Expect rough edges and breaking changes until the first stable release.

## Why Gobby?

### 🎯 A Task System That Actually Works

If you've tried Beads or TaskMaster, you know the pain: databases that corrupt, agents that can't figure out the schema, worktrees that fall out of sync. Gobby's task system was designed by someone who got fed up with all of them.

- **Dependency graphs** that agents actually understand
- **TDD expansion** — describe a feature, get red/green/blue subtasks with test-first ordering
- **Validation gates** — tasks can't close without passing criteria (with git diff context)
- **Git-native sync** — `.gobby/tasks.jsonl` lives in your repo, works with worktrees
- **Commit linking** — `[task-id] feat: thing` auto-links commits to tasks

```bash
# Create a task
gobby tasks create "Add user authentication" --type feature

# Let the AI break it down with TDD ordering
gobby tasks expand <task-id>

# See what's ready to work on
gobby tasks list --ready
```

### 🔌 MCP Proxy Without the Token Tax

Connect 5 MCP servers and watch 50K+ tokens vanish before you write a single line of code. Gobby's proxy uses **progressive discovery**—tools stay as lightweight metadata until you actually need them:

```text
list_tools()           → Just names and descriptions (~200 tokens)
get_tool_schema(name)  → Full inputSchema when you need it
call_tool(name, args)  → Execute
```

Add servers dynamically. Import from GitHub repos. Search semantically. Your context window stays yours.

### 🔄 Session Handoffs That Don't Lose the Plot

When you `/compact` in Claude Code, Gobby captures what matters: the goal, what you changed, git status, recent tool calls. Next session, it injects that context automatically. No more "wait, what were we doing?"

Works across CLIs too. Start in Claude Code, pick up in Gemini. Gobby remembers.

### 🛤️ Rules That Enforce Discipline

Declarative rules that enforce behavior without relying on prompt compliance. The LLM doesn't need to remember constraints—the rule engine evaluates every event and enforces behavior through tool blocks, context injection, and state mutations:

```yaml
# Block git push - let the parent session handle pushing
no-push:
  event: before_tool
  effect:
    type: block
    tools: [Bash]
    command_pattern: "git\\s+push"
    reason: "Do not push to remote. Let the parent session handle pushing."

# Block file edits without a claimed task
require-task:
  event: before_tool
  when: "not task_claimed and not plan_mode"
  effect:
    type: block
    tools: [Edit, Write, NotebookEdit]
    reason: "Claim a task before editing files."
```

13 bundled rule groups covering safety, tool hygiene, task enforcement, stop gates, memory lifecycle, and more. Plus on-demand step-based workflows and deterministic pipelines.

### 🌳 Worktree Orchestration

Spawn agents in isolated git worktrees. Run tasks in parallel without stepping on each other. Gobby tracks which agent is where and what they're doing.

```python
call_tool("gobby-agents", "spawn_agent", {
    "prompt": "Implement OAuth flow",
    "task_id": "#123",
    "isolation": "worktree",
    "branch_name": "feature/oauth"
})
```

### 🔗 Claude Code Task Integration

Gobby transparently intercepts Claude Code's built-in task system (TaskCreate, TaskUpdate, etc.) and syncs operations to Gobby's persistent task store. Benefits:

- **Tasks persist** across sessions (unlike CC's session-scoped tasks)
- **Commit linking** — tasks auto-link to git commits
- **Validation gates** — define criteria for task completion
- **LLM expansion** — break complex tasks into subtasks

No configuration needed — just use Claude Code's native task tools and Gobby handles the rest.

### 📚 Skills System

Reusable instruction sets that teach agents how to perform specific tasks. Skills follow the SKILL.md format and are managed through the database.

- **Core skills** bundled with Gobby — synced to the database on daemon startup
- **Project skills** in `.gobby/skills/` for team-specific patterns
- **Auto-injection** — skills with `alwaysApply: true` inject into every session
- **Search and discovery** — find relevant skills via MCP tools or CLI

```bash
# List installed skills
gobby skills list

# Search for relevant skills
gobby skills search "testing coverage"
```

### 🌐 Web UI

Gobby ships a built-in web interface that auto-starts with the daemon:

- **Chat** with MCP tool support, voice chat, model switching, slash commands
- **Tasks** — kanban board, tree view, dependency graph, Gantt chart, detail panel
- **Memory** — table view, Neo4j 3D knowledge graph
- **Sessions** — lineage tree, transcript viewer, AI summary generation
- **Cron Jobs**, **Configuration**, **Skills**, **Projects**, **Agent Registry** pages
- File browser/editor, terminal panel with xterm.js

Access at `http://localhost:60887` when the daemon is running.

### 🔍 Observability (OpenTelemetry)

Full observability built on OpenTelemetry — no custom metrics frameworks, no vendor lock-in:

- **Tracing** — `@traced` decorator, span context propagation, SQLite span storage
- **Metrics** — instruments for MCP calls, pipeline executions, task lifecycle, hook events
- **Logging** — OTel logging bridge replaces custom logging
- **Exporters** — OTLP gRPC, Prometheus
- **Trace viewer** — built-in UI with waterfall visualization and span detail panel

### 🧬 Code Indexing

AST-based symbol indexing via the `gobby-code` MCP server. Search and retrieve code by symbol instead of reading entire files — saves 90%+ tokens on large codebases:

```text
search_symbols("TaskExpander")  → Find symbols by name
get_file_outline("src/foo.py")  → Hierarchical symbol map
get_symbol(symbol_id)           → Just the source you need
```

Tree-sitter parsing for 15+ languages. Auto-indexes on commit, on init, and on session start.

### 🚀 Pipelines & Orchestration

Deterministic automation with approval gates — from simple scripts to autonomous multi-agent orchestration:

- Step types: `exec`, `prompt`, `invoke_pipeline`, `spawn_session`
- Tick-based orchestrator pipeline with cron scheduling
- Clone-based agent isolation — one clone per epic, sequential or parallel dispatch
- Provider fallback rotation — auto-retry across providers on failures
- Approval gates for human-in-the-loop workflows
- Condition evaluation with safe expression engine
- CLI, MCP, and HTTP API access

## Installation

### Try it instantly
```bash
uvx gobby --help
```

### Install globally
```bash
# With uv (recommended)
uv tool install gobby

# With pipx
pipx install gobby

# With pip
pip install gobby
```

**Requirements:** Python 3.13+

## Quick Start

```bash
# Start the daemon
gobby start

# In your project directory
gobby init
gobby install  # Installs hooks for detected CLIs
```

**Requirements:** At least one AI CLI ([Claude Code](https://claude.ai/code), [Gemini CLI](https://github.com/google-gemini/gemini-cli), or [Codex CLI](https://github.com/openai/codex))

Works with your Claude, Gemini, or Codex subscriptions—or bring your own API keys. Local model support coming soon.

## Configure Your AI CLI

Add Gobby as an MCP server. Choose the `command` and `args` that match your installation:

- **pip/pipx install**: `"command": "gobby"`, `"args": ["mcp-server"]`
- **uv tool install**: `"command": "uv"`, `"args": ["run", "gobby", "mcp-server"]`

**Claude Code** (`.mcp.json` or `~/.claude.json`):

```json
{
  "mcpServers": {
    "gobby": {
      "command": "gobby",
      "args": ["mcp-server"]
    }
  }
}
```

Or with uv:

```json
{
  "mcpServers": {
    "gobby": {
      "command": "uv",
      "args": ["run", "gobby", "mcp-server"]
    }
  }
}
```

**Gemini CLI** (`.gemini/settings.json`):

```json
{
  "mcpServers": {
    "gobby": {
      "command": "gobby",
      "args": ["mcp-server"]
    }
  }
}
```

**Codex CLI** (`~/.codex/config.toml`):

```toml
[mcp_servers.gobby]
command = "gobby"
args = ["mcp-server"]
```

**Gemini Antigravity** (`~/.gemini/antigravity/mcp_config.json`):

```json
{
  "mcpServers": {
    "gobby": {
      "command": "/path/to/uv",
      "args": ["run", "--directory", "/path/to/gobby", "gobby", "mcp-server"],
      "disabled": false
    }
  }
}
```

## CLI Support

| CLI | Hooks | Status |
| :--- | :--- | :--- |
| **Claude Code** | ✅ Full support | Native adapter, 12 hook types |
| **Gemini CLI** | ✅ Full support | Native adapter, all hook types |
| **Codex CLI** | ⚠️ Partial | Notify hooks only (fire-and-forget) — no blocking or context injection for interactive sessions* |
| **Cursor** | ✅ Full support | Native adapter, 17 hook types |
| **Windsurf** | ✅ Full support | Native adapter, 11 hook types |
| **Copilot** | ✅ Full support | Native adapter, 6 hook types |

\* **Codex hook limitation:** Codex CLI only supports fire-and-forget notify hooks for interactive terminal sessions. Bidirectional hook enforcement (tool blocking, context injection, workflow enforcement) is not possible because Codex lacks a blocking hook protocol — see [openai/codex#2109](https://github.com/openai/codex/issues/2109). Gobby includes a Codex app-server adapter that provides full bidirectional control via JSON-RPC, but this runs Codex as a daemon-controlled subprocess rather than an interactive terminal session. Codex agents spawned via pipelines (`--full-auto`) work fully but bypass hook enforcement. All CLIs connect via MCP for tool access regardless of hook support.

### Hook Installation

Gobby uses Python hook dispatchers that capture terminal context and communicate with the daemon. Run `gobby install` in your project to set up hooks:

```bash
gobby install           # Auto-detect and install hooks for all CLIs
gobby install --claude  # Install for specific CLI
gobby install --gemini
gobby install --codex
gobby install --cursor
gobby install --windsurf
gobby install --copilot
```

The dispatchers handle:
- Terminal context capture (TTY, parent PID, session IDs)
- Proper JSON serialization and HTTP communication
- Exit code handling for blocking actions

All CLIs can also connect via MCP for tool access (see configuration examples above).

## How It Compares

| | Gobby | TaskMaster | Beads | mcp-agent |
| :--- | :---: | :---: | :---: | :---: |
| Task dependencies | ✅ | ✅ | ✅ | ❌ |
| TDD expansion | ✅ | ❌ | ❌ | ❌ |
| Validation gates | ✅ | ❌ | ❌ | ❌ |
| Progressive MCP discovery | ✅ | Partial | ❌ | ❌ |
| Multi-CLI orchestration | ✅ | ❌ | ❌ | ❌ |
| Session handoffs | ✅ | ❌ | ❌ | ❌ |
| Declarative rules | ✅ | ❌ | ❌ | ✅ |
| Worktree/clone orchestration | ✅ | ❌ | ❌ | ❌ |
| Pipeline automation | ✅ | ❌ | ❌ | ❌ |
| Observability (OTel) | ✅ | ❌ | ❌ | ❌ |
| Code indexing (AST) | ✅ | ❌ | ❌ | ❌ |
| Zero external deps | ✅ | ❌ | ✅ | ❌ |
| Local-first | ✅ | ✅ | ✅ | ✅ |

## Architecture

```text
AI CLI (Claude/Gemini/Cursor/Windsurf/Copilot)
        │ hooks fire
        ▼
   Hook Dispatcher
        │ HTTP POST
        ▼
  Gobby Daemon (:60887)
        │
   ┌────┼────────┐
   ▼    ▼        ▼
FastAPI WebSocket FastMCP
   │    │         │
   ▼    ▼         ▼
┌──────────────────────┐
│  RuleEngine          │
│  HookManager         │
│  SessionManager      │
│  AgentRunner         │
│  WorkflowEngine      │
│  PipelineExecutor    │
│  MCPClientProxy      │
│  TaskStore           │
│  MemoryStore         │
│  WebUI               │
└──────────────────────┘
        │
        ▼
     SQLite
  (~/.gobby/gobby-hub.db)
```

Everything runs locally. No cloud. No API keys required (beyond what your AI CLIs need). Works offline.

## MCP Tools

Gobby exposes tools via MCP that your AI coding assistant can use:

**Task Management** (`gobby-tasks`)
`create_task`, `expand_task`, `validate_task`, `close_task`, `claim_task`, `list_ready_tasks`, `suggest_next_task`, `link_commit`, and more.

**Orchestration** (`gobby-orchestration`)
`orchestrate_ready_tasks`, `wait_for_task`, `poll_agent_status`, `spawn_review_agent`, `approve_and_cleanup`, and more.

**Session Management** (`gobby-sessions`)
`get_current_session`, `pickup` (restore context), `get_handoff_context`, `list_sessions`, `send_message`

**Memory** (`gobby-memory`)
`remember`, `recall`, `forget` — persistent facts across sessions

**Workflows and Rules** (`gobby-workflows`)
`list_rules`, `toggle_rule`, `get_rule_detail`, `activate_workflow`, `set_variable`, `get_variable`, `get_workflow_status`

**Agents** (`gobby-agents`)
`spawn_agent` (unified API with `isolation`: current/worktree/clone), `list_agents`, `get_agent`, `kill_agent`, `send_message`, `send_command`, `complete_command`, `deliver_pending_messages`

**Worktrees** (`gobby-worktrees`)
`create_worktree`, `list_worktrees`, `delete_worktree`, `merge_worktree`

**Clones** (`gobby-clones`)
`create_clone`, `list_clones`, `delete_clone`, `merge_clone`

**Pipelines** (`gobby-pipelines`)
`list_pipelines`, `run_pipeline`, `approve_pipeline`, `reject_pipeline`, `get_pipeline_status`

**MCP Proxy**
`list_mcp_servers`, `add_mcp_server`, `import_mcp_server`, `list_tools`, `get_tool_schema`, `call_tool`, `recommend_tools`, `search_tools`

**Skills** (`gobby-skills`)
`list_skills`, `get_skill`, `search_skills`, `install_skill`, `remove_skill`, `update_skill`

## For AI Agents

**If you're an AI agent reading this:** Check out [CLAUDE.md](CLAUDE.md) for operating guidance.

## Authentication & AI Vendor Policies

Gobby uses the Claude Agent SDK for web chat and workflow agents (subscription mode by default, intended for individual use). For commercial/production use, configure API keys per your AI vendor's terms. Recent Gemini CLI TOS changes prohibit using Gemini CLI OAuth tokens in third-party software.

See [AUTH.md](AUTH.md) for details on authentication modes and AI vendor policies.

## Roadmap

See [ROADMAP.md](ROADMAP.md) for the full plan, but highlights:

**Shipped:** Task system v2, TDD expansion, rule engine (13 bundled rule groups), MCP proxy with progressive discovery, session handoffs, memory v5 (Qdrant + knowledge graph), hooks for all 6 CLIs, orchestration v3 (tick-based pipeline, clone isolation, provider fallback rotation, QA-dev agent), OpenTelemetry observability (tracing, metrics, logging, trace viewer UI), native AST code indexing, autonomous SDK agent execution, session handoff & digest overhaul, stop-gate enforcement, pipeline system with approval gates, web UI (tasks, memory, sessions, chat with voice, cron, config, skills, projects, agents, file browser, traces), skills system, worktree/clone orchestration

**In progress:** v1 release prep — bug fixing, orchestration battle-hardening, UI polish, documentation

**After v1:** Ollama support

**Future:** Pro cloud features, fleet management, plugin ecosystem v2

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for release history and detailed changes.

## Development

```bash
uv sync                    # Install deps
uv run gobby start -v      # Run daemon (verbose)
uv run pytest              # Tests
uv run ruff check src/     # Lint
uv run mypy src/           # Type check
```

### Using Gobby in other projects (from source)

If you're running Gobby from a source checkout, use `-C` to target another project directory:

```bash
uv run --project ~/Projects/gobby gobby init -C /path/to/other/project
uv run --project ~/Projects/gobby gobby install -C /path/to/other/project
```

The `--project` flag tells uv to use the Gobby installation from your source repo, and `-C` tells Gobby which directory to operate on.

Coverage threshold: 80%. We're serious about it.

## Contributing

We'd love your help. Gobby is built by developers who got frustrated with the state of AI coding tool orchestration. If that's you too, jump in:

- **Found a bug?** Open an issue
- **Have a feature idea?** Open a discussion first
- **Want to contribute code?** PRs welcome — check the roadmap for what's in flight
- **UI/UX skills?** We *really* need you. The maintainer is colorblind and Photoshop makes him itch.

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## License

[Apache 2.0](LICENSE.md) — Use it, fork it, build on it.

---

<p align="center">
  <sub>Built with 🤖 by humans and AI, working together.</sub>
</p>
