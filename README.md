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

Gobby is a local-first daemon that unifies your AI coding assistants—Claude Code, Gemini CLI, and Codex—under one persistent, extensible platform. It handles the stuff these tools forget: sessions that survive restarts, context that carries across compactions, workflows that keep agents from going off the rails, and an MCP proxy that doesn't eat half your context window just loading tool definitions.

**Gobby is built with Gobby.** Most of this codebase was written by AI agents running through Gobby's own task system and workflows. Dogfooding isn't a buzzword here—it's the development process.

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

Connect 5 MCP servers and watch 50K+ tokens vanish before you write a single line of code. Gobby's proxy uses **progressive disclosure**—tools stay as lightweight metadata until you actually need them:

```
list_tools()           → Just names and descriptions (~200 tokens)
get_tool_schema(name)  → Full inputSchema when you need it
call_tool(name, args)  → Execute
```

Add servers dynamically. Import from GitHub repos. Search semantically. Your context window stays yours.

### 🔄 Session Handoffs That Don't Lose the Plot

When you `/compact` in Claude Code, Gobby captures what matters: the goal, what you changed, git status, recent tool calls. Next session, it injects that context automatically. No more "wait, what were we doing?"

Works across CLIs too. Start in Claude Code, pick up in Gemini. Gobby remembers.

### 🛤️ Workflows That Enforce Discipline

YAML-defined workflows with state machines, tool restrictions, and exit conditions:

```yaml
# auto-task workflow: autonomous execution until task tree is complete
name: auto-task
steps:
  - name: work
    description: "Work on assigned task until complete"
    allowed_tools: all
    transitions:
      - to: complete
        when: "task_tree_complete(variables.session_task)"

  - name: complete
    description: "Task work finished - terminal step"

exit_condition: "task_tree_complete(variables.session_task)"

on_premature_stop:
  action: guide_continuation
  message: "Task has incomplete subtasks. Use suggest_next_task() and continue."
```

Built-in workflows: `auto-task`, `plan-execute`, `test-driven`. Or write your own.

### 🌳 Worktree Orchestration

Spawn agents in isolated git worktrees. Run tasks in parallel without stepping on each other. Gobby tracks which agent is where and what they're doing.

```python
call_tool("gobby-worktrees", "spawn_agent_in_worktree", {
    "prompt": "Implement OAuth flow",
    "branch_name": "feature/oauth",
    "task_id": "task-123"
})
```

## Quick Start

```bash
# Clone and install
git clone https://github.com/GobbyAI/gobby.git
cd gobby
uv sync

# Start the daemon
uv run gobby start

# In your project directory
uv run gobby init
uv run gobby install  # Installs hooks for detected CLIs

# Optional: install globally
uv pip install -e .
```

**Requirements:** Python 3.11+, [uv](https://github.com/astral-sh/uv), at least one AI CLI ([Claude Code](https://claude.ai/code), [Gemini CLI](https://github.com/google-gemini/gemini-cli), or [Codex CLI](https://github.com/openai/codex))

Works with your Claude, Gemini, or Codex subscriptions—or bring your own API keys. Local model support coming soon.

## Configure Your AI CLI

Add Gobby as an MCP server:

**Claude Code** (`.mcp.json` or `~/.claude.json`):
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
      "command": "uv",
      "args": ["run", "gobby", "mcp-server"]
    }
  }
}
```

**Codex CLI** (`~/.codex/config.toml`):
```toml
[mcp_servers.gobby]
command = "uv"
args = ["run", "gobby", "mcp-server"]
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
|-----|-------|--------|
| **Claude Code** | ✅ All 14 types | Full support |
| **Gemini CLI** | ⏳ Ready | Waiting on upstream PR (see [#9070](https://github.com/google-gemini/gemini-cli/issues/9070)) |
| **Codex CLI** | 🔸 Basic | `after_agent` only |

## How It Compares

| | Gobby | TaskMaster | Beads | mcp-agent |
|---|:---:|:---:|:---:|:---:|
| Task dependencies | ✅ | ✅ | ✅ | ❌ |
| TDD expansion | ✅ | ❌ | ❌ | ❌ |
| Validation gates | ✅ | ❌ | ❌ | ❌ |
| Progressive MCP discovery | ✅ | Partial | ❌ | ❌ |
| Multi-CLI orchestration | ✅ | ❌ | ❌ | ❌ |
| Session handoffs | ✅ | ❌ | ❌ | ❌ |
| YAML workflows | ✅ | ❌ | ❌ | ✅ |
| Worktree orchestration | ✅ | ❌ | ❌ | ❌ |
| Zero external deps | ✅ | ❌ | ✅ | ❌ |
| Local-first | ✅ | ✅ | ✅ | ✅ |

## Architecture

```
AI CLI (Claude/Gemini/Codex)
        │ hooks fire
        ▼
   Hook Dispatcher
        │ HTTP POST
        ▼
  Gobby Daemon (:8765)
        │
   ┌────┴────┐
   ▼         ▼
FastAPI   FastMCP
   │         │
   ▼         ▼
┌─────────────────────┐
│  HookManager        │
│  SessionManager     │
│  WorkflowEngine     │
│  MCPClientProxy     │
│  TaskStore          │
│  MemoryStore        │
└─────────────────────┘
        │
        ▼
     SQLite
  (~/.gobby/gobby-hub.db)
```

Everything runs locally. No cloud. No API keys required (beyond what your AI CLIs need). Works offline.

## MCP Tools

Gobby exposes tools via MCP that your AI coding assistant can use:

**Task Management** (`gobby-tasks`)  
`create_task`, `expand_task`, `validate_task`, `close_task`, `list_ready_tasks`, `suggest_next_task`, `add_dependency`, `get_dependency_tree`, and more.

**Session Management** (`gobby-sessions`)  
`pickup` (restore context), `get_handoff_context`, `list_sessions`

**Memory** (`gobby-memory`)  
`remember`, `recall`, `forget` — persistent facts across sessions

**Workflows** (`gobby-workflows`)  
`activate`, `advance`, `set_variable`, `get_status`

**Worktrees** (`gobby-worktrees`)  
`create_worktree`, `spawn_agent_in_worktree`, `list_worktrees`

**MCP Proxy**  
`list_mcp_servers`, `add_mcp_server`, `import_mcp_server`, `list_tools`, `get_tool_schema`, `call_tool`, `recommend_tools`

## For AI Agents

**If you're an AI agent reading this:** Check out [docs/AGENT_INSTRUCTIONS.md](docs/AGENT_INSTRUCTIONS.md) for your operating procedures, and [CLAUDE.md](CLAUDE.md) for Claude Code-specific guidance.

## Roadmap

See [ROADMAP.md](ROADMAP.md) for the full plan, but highlights:

**Shipped:** Task system v2 (commit linking, validation gates), workflow engine, MCP proxy with progressive discovery, session handoffs, memory, hooks integration, worktree primitives

**In Progress:** TDD expansion v2 (more robust red/green/blue generation)

**Next:** Security posture for MCP (allow/deny lists, audit logging), observability (tool call tracing, session timelines), minimal web UI

**Vision:** Plugin ecosystem, team workflows (still local-first), enterprise hardening

## Development

```bash
uv sync                    # Install deps
uv run gobby start -v      # Run daemon (verbose)
uv run pytest              # Tests
uv run ruff check src/     # Lint
uv run mypy src/           # Type check
```

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

