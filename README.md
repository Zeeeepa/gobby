<p align="center">
  <img src="logo.png" alt="Gobby" width="200">
</p>

# Gobby

![CodeRabbit Pull Request Reviews](https://img.shields.io/coderabbit/prs/github/GobbyAI/gobby?utm_source=oss&utm_medium=github&utm_campaign=GobbyAI%2Fgobby&labelColor=171717&color=FF570A&link=https%3A%2F%2Fcoderabbit.ai&label=CodeRabbit+Reviews)

**A Unified AI Coding Assistant Daemon**

Gobby is an open-source local daemon designed to make AI coding assistants more powerful by unifying multiple AI coding agent tools (Anthropic's Claude Code, Google's Gemini CLI, OpenAI's Codex CLI) under one persistent, extensible platform. It acts as a "manager" for these AI coding assistants, providing session persistence, tool orchestration, and memory beyond what each tool offers individually.

## Key Features

### Multi-Model Orchestration
Gobby unifies several AI coding assistants into one system. Claude Code is known for its powerful coding capabilities and hook system, Gemini CLI offers speed and integration with Google services, and Codex CLI provides access to OpenAI's latest models. Normally, these tools operate separately, but Gobby can coordinate them—effectively enabling AI agents to leverage each model's strengths within one workflow.

### Persistent Sessions with Long-Term Memory
Unlike ephemeral CLI agents that forget context once closed, Gobby runs as a background daemon maintaining state across sessions. Agents can remember project-specific conventions, previously solved bugs, and user preferences—accumulating knowledge over time. This gives AI assistants the continuity of a human team member rather than starting fresh each session.

### MCP Server with Lazy Tool Discovery
Gobby implements an MCP client proxy that can connect to multiple external MCP servers simultaneously with **lazy tool acquisition**. Rather than loading all tool definitions upfront (which can consume 50k+ tokens), Gobby discovers and fetches tool definitions on-demand, achieving ~96% context savings.

### Intelligent Workflow Engine
The workflow engine breaks down and tracks tasks, manages multi-step processes, and enforces structured patterns like Plan-Execute or Test-Driven Development. Define workflows in YAML with tool restrictions per step, exit conditions, and automated context injection.

### Local-First Architecture
All data lives in SQLite on your machine—no cloud dependencies, works offline. HTTP and WebSocket servers enable integration with IDEs, dashboards, or team environments while keeping everything under your control.

## CLI Support Status

| CLI             | Status     | Notes                                                                           |
|:----------------|:-----------|:--------------------------------------------------------------------------------|
| **Claude Code** | ✅ Full    | All 14 hook types supported                                                     |
| **Gemini CLI**  | ⏳ Pending | Waiting on [PR #9070](https://github.com/google-gemini/gemini-cli/pull/9070) for hook system |
| **Codex CLI**   | 🔸 Limited | Only `after_agent` notify hook currently implemented                            |

## For AI Agents

**Are you an AI Agent?** Read [docs/AGENT_INSTRUCTIONS.md](docs/AGENT_INSTRUCTIONS.md) first. This file contains your standard operating procedures, session workflows, and "landing the plane" protocols.

## What Makes Gobby Different?

| Capability | Claude Code | Codex CLI | Gemini CLI | **Gobby** |
|------------|-------------|-----------|------------|-----------|
| Multi-model orchestration | No | No | No | **Yes** |
| Persistent memory | Session only | Session only | Session only | **Cross-session** |
| Long-term skill learning | No | No | No | **Yes** |
| Lazy tool discovery | No | No | No | **Yes (~96% savings)** |
| Workflow enforcement | Hooks only | Limited | No | **Full YAML workflows** |
| Task tracking | No | No | No | **Yes (with git sync)** |
| Local-first | Yes | Yes | Yes | **Yes** |

### vs AutoGPT/BabyAGI

These frameworks introduced autonomy and multi-step planning, but typically use a single model and run to completion. Gobby combines autonomy with interactivity—allowing both hands-free operation and user guidance—while orchestrating multiple AI models and maintaining persistent state across sessions.

### vs LangChain/Agent Frameworks

Frameworks like LangChain require custom coding to achieve multi-model orchestration with memory. Gobby is a turnkey solution: a daemon configured to be an out-of-the-box AI developer assistant with best practices (like lazy tool loading) already implemented.

```bash
# Install
git clone https://github.com/GobbyAI/gobby.git
cd gobby
uv sync

# Start daemon
uv run gobby start

# Initialize project (in your project directory)
uv run gobby init

# Install hooks for your AI CLIs
uv run gobby install

# Optional: Install globally to use 'gobby' without 'uv run'
uv pip install -e .
```

## Requirements

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) package manager
- At least one supported AI CLI:
  - [Claude Code](https://claude.ai/code) - `npm install -g @anthropic-ai/claude-code`
  - [Gemini CLI](https://github.com/google-gemini/gemini-cli) - `npm install -g @google/gemini-cli`
  - [Codex CLI](https://github.com/openai/codex) - `npm install -g @openai/codex`

## MCP Server Configuration

After starting the daemon, configure your AI CLI to connect to Gobby's MCP server:

### Claude Code

Add to `.claude/settings.json` (project) or `~/.claude/settings.json` (global):

```json
{
  "mcpServers": {
    "gobby": {
      "url": "http://localhost:8765/mcp",
      "transport": "http"
    }
  }
}
```

### Gemini CLI

Add to `.gemini/settings.json` (project) or `~/.gemini/settings.json` (global):

```json
{
  "mcpServers": {
    "gobby": {
      "uri": "http://localhost:8765/mcp"
    }
  }
}
```

### Codex CLI

Add to `~/.codex/config.toml`:

```toml
[mcp_servers.gobby]
url = "http://localhost:8765/mcp"
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `gobby start [--verbose]` | Start the daemon |
| `gobby stop` | Stop the daemon |
| `gobby status` | Show daemon status |
| `gobby restart` | Restart the daemon |
| `gobby init` | Initialize a Gobby project in current directory |
| `gobby install` | Install hooks for detected AI CLIs |
| `gobby uninstall` | Remove hooks from AI CLIs |
| `gobby mcp-server` | Run stdio MCP server for any MCP client |
| `gobby memory list` | List stored memories |
| `gobby memory add` | Add a new memory |
| `gobby memory sync` | Sync memories to/from JSONL |
| `gobby skills list` | List learned skills |
| `gobby skills learn` | Learn skills from a session |
| `gobby skills export` | Export skills to markdown files |
| `gobby mcp-proxy search-tools` | Semantic search for tools |
| `gobby mcp-proxy recommend-tools` | Get tool recommendations (with `--mode` option) |

## MCP Tools

The daemon exposes tools via MCP that can be used by Claude Code and other MCP clients:

### Daemon Management

- `start()`, `stop()`, `restart()`, `status()` - Lifecycle control
- `init_project()` - Initialize a new project

### MCP Server Management

- `list_mcp_servers()` - List connected downstream servers
- `add_mcp_server()` - Dynamically add an MCP server
- `remove_mcp_server()` - Remove an MCP server
- `import_mcp_server()` - Import servers from projects, GitHub, or web search

### Tool Proxy (Progressive Disclosure)

- `list_tools(server?)` - Get lightweight tool metadata
- `get_tool_schema(server, tool)` - Get full inputSchema for a tool
- `call_tool(server, tool, arguments?)` - Execute a tool on a downstream server

### Code Execution

- `execute_code(code)` - Run Python in Claude's sandbox
- `process_large_dataset(data, operation)` - Token-optimized data processing

### AI-Powered Tool Discovery

- `recommend_tools(task_description, search_mode?)` - Get intelligent tool recommendations
  - `search_mode`: `llm` (default), `semantic`, or `hybrid`
- `search_tools(query, top_k?, min_similarity?, server?)` - Semantic similarity search over tools

### Internal Tools (via Proxy)

Internal tools are accessed via `call_tool(server_name="gobby-*", ...)`:

**Task Management** (`gobby-tasks`):

- `create_task`, `get_task`, `update_task`, `close_task`, `delete_task`, `list_tasks`
- `add_label`, `remove_label` - Label management
- `add_dependency`, `remove_dependency`, `get_dependency_tree`, `check_dependency_cycles`
- `list_ready_tasks`, `list_blocked_tasks`
- `link_task_to_session`, `get_session_tasks`, `get_task_sessions`
- `sync_tasks`, `get_sync_status`
- `expand_task`, `analyze_complexity`, `expand_all`, `expand_from_spec`, `suggest_next_task` - LLM-powered expansion
- `validate_task`, `get_validation_status`, `reset_validation_count`, `generate_validation_criteria` - Task validation (auto-fetches git diff)
- `link_commit`, `unlink_commit`, `auto_link_commits`, `get_task_diff` - Commit linking (Task System V2)

See [docs/guides/tasks.md](docs/guides/tasks.md) for the full Task System guide.

**Memory Management** (`gobby-memory`):

- `remember` - Store a memory with content, type, importance, and tags
- `recall` - Retrieve memories by query with importance ranking
- `forget` - Delete a memory by ID
- `list_memories` - List all memories with filtering (type, importance, project)
- `get_memory`, `update_memory` - CRUD operations
- `memory_stats` - Get statistics (count by type, average importance)

**Skill Management** (`gobby-skills`):

- `learn_skill_from_session` - Extract skills from completed sessions via LLM
- `create_skill`, `get_skill`, `update_skill`, `delete_skill` - CRUD operations
- `list_skills` - List available skills with filtering
- `match_skills` - Find skills matching a prompt (trigger pattern)
- `apply_skill` - Return skill instructions and mark as used
- `export_skills` - Export skills to `.gobby/skills/` as markdown files

## Configuration

Configuration is stored at `~/.gobby/config.yaml`:

```yaml
# Auto-generated machine identifier
machine_id: <auto-generated-uuid>

# Server settings
daemon_port: 8765
daemon_health_check_interval: 60.0

# WebSocket server
websocket:
  enabled: true
  port: 8766
  ping_interval: 30
  ping_timeout: 10

# Logging (separate log files per component)
logging:
  level: warning  # debug, info, warning, error
  format: text    # text or json
  client: ~/.gobby/logs/gobby-client.log
  client_error: ~/.gobby/logs/gobby-client-error.log
  hook_manager: ~/.gobby/logs/hook-manager.log
  mcp_server: ~/.gobby/logs/mcp-server.log
  mcp_client: ~/.gobby/logs/mcp-client.log
  max_size_mb: 10
  backup_count: 5

# MCP client proxy for downstream servers
mcp_client_proxy:
  enabled: true
  proxy_timeout: 30
  tool_timeout: 30

# LLM providers configuration
llm_providers:
  claude:
    models: claude-haiku-4-5,claude-sonnet-4-5,claude-opus-4-5
    auth_mode: subscription  # subscription, api_key, or adc
  codex:
    models: gpt-4o-mini,gpt-5-mini,gpt-5,gpt-5-high
    auth_mode: subscription
  gemini:
    models: gemini-3
    auth_mode: subscription
  litellm:
    models: gpt-4o-mini,gpt-5-mini
    auth_mode: api_key  # litellm always uses api_key
  # API keys - prefer environment variables (OPENAI_API_KEY, etc.)
  # or uncomment below for config-based keys:
  # api_keys:
  #   OPENAI_API_KEY: "<YOUR_OPENAI_API_KEY>"
  #   MISTRAL_API_KEY: "<YOUR_MISTRAL_API_KEY>"

# Session summaries (LLM-powered)
session_summary:
  enabled: true
  provider: claude
  model: claude-haiku-4-5
  summary_file_path: ~/.gobby/session_summaries/
  prompt: |
    # Custom prompt template (optional)
    # Uses {transcript_summary}, {last_messages}, {git_status}, {file_changes}

# Title synthesis for sessions
title_synthesis:
  enabled: true
  provider: claude
  model: claude-haiku-4-5
  prompt: |
    # Custom prompt template (optional)
    # Uses {user_prompt}

# Code execution (sandbox via Claude)
code_execution:
  enabled: true
  provider: claude
  model: claude-sonnet-4-5
  max_turns: 5
  default_timeout: 30
  max_dataset_preview: 3
  prompt: |
    # Custom prompt template (optional)
    # Uses {context}, {language}, {code}

# Tool recommendations
recommend_tools:
  enabled: true
  provider: claude
  model: claude-sonnet-4-5
  prompt: |
    # Custom prompt template (optional)
```

## File Locations

| Path | Description |
|------|-------------|
| `~/.gobby/config.yaml` | Daemon configuration |
| `~/.gobby/gobby.db` | SQLite database (sessions, projects, tasks, memories, skills, MCP servers) |
| `~/.gobby/logs/` | Log files |
| `~/.gobby/session_summaries/` | Generated session summaries |
| `.gobby/project.json` | Project-level configuration |
| `.gobby/tasks.jsonl` | Task data for git sync |
| `.gobby/tasks_meta.json` | Task sync metadata |
| `.gobby/memories.jsonl` | Memory data for git sync |
| `.gobby/memories_meta.json` | Memory sync metadata |
| `.gobby/skills/` | Exported skill markdown files |

## Architecture

```text
AI CLI (Claude/Gemini/Codex)
        │ hook fires
        ▼
Hook Dispatcher Script
        │ HTTP POST
        ▼
Gobby HTTP Server (:8765)
        │
        ▼
┌───────────────────────────────────┐
│  FastAPI + FastMCP Server         │
│  ┌─────────────┬────────────────┐ │
│  │ HookManager │ MCPClientManager│ │
│  └──────┬──────┴───────┬────────┘ │
│         │              │          │
│    ┌────▼────┐   ┌─────▼─────┐   │
│    │ SQLite  │   │ Downstream │   │
│    │ Storage │   │ MCP Servers│   │
│    └─────────┘   └───────────┘   │
└───────────────────────────────────┘
```

### Key Components

- **Hook System** - Unified interface capturing 14 event types across Claude Code, Gemini CLI, and Codex CLI
- **Session Manager** - Tracks sessions with metadata, status, parent relationships, and handoff context
- **Workflow Engine** - YAML-defined lifecycle and phase-based workflows with LLM-powered actions
- **MCP Proxy** - Connects to downstream servers (Supabase, Context7, etc.) with progressive tool discovery
- **Internal Tool Registry** - Domain-specific tools (`gobby-tasks`, `gobby-memory`, `gobby-skills`) accessed via the proxy pattern
- **Session Handoff** - LLM-powered session summaries with git status, file changes, and context injection

### Autonomous Session Handoff

When you use `/compact` in Claude Code, Gobby automatically extracts and persists session context for seamless continuation:

**Flow:**
1. `/compact` triggers `pre-compact` hook
2. Gobby extracts structured context from transcript (files modified, git status, initial goal, recent activity)
3. Context is formatted as markdown and saved to `session.compact_markdown` in the database
4. On next session start (after compaction), context is automatically injected

**What gets captured:**
- Initial goal (first user message)
- Files modified (from Edit/Write tool calls)
- Git status (uncommitted changes)
- Git commits made during session
- Active gobby-task (if using task tracking)
- Recent tool activity (last 5 tool calls)

**Configuration** (`~/.gobby/config.yaml`):

```yaml
compact_handoff:
  enabled: true
  prompt: |
    ## Continuation Context

    {active_task_section}
    {todo_state_section}
    {git_commits_section}
    {git_status_section}
    {files_modified_section}
    {initial_goal_section}
    {recent_activity_section}
```

The prompt template uses placeholders that are replaced with pre-rendered markdown sections. Empty sections are automatically omitted.

### Internal Tool Pattern

Internal tools use the same progressive disclosure pattern as downstream MCP servers:

```python
# List internal task tools
list_tools(server="gobby-tasks")

# Get schema for a specific tool
get_tool_schema(server_name="gobby-tasks", tool_name="create_task")

# Call an internal tool
call_tool(server_name="gobby-tasks", tool_name="create_task", arguments={"title": "Fix bug"})
```

This pattern enables:

- Consistent interface for all tools (internal and external)
- Progressive disclosure to reduce token usage
- Easy extensibility for new internal domains

## Development

```bash
# Install dependencies
uv sync

# Run daemon in development
uv run gobby start --verbose

# Run tests
uv run pytest

# Linting
uv run ruff check src/
uv run ruff format src/

# Type checking
uv run mypy src/
```

## Hook Types

Gobby normalizes hook events to a unified internal model. Currently only Claude Code has full hook support.

### Claude Code Hook Events (Full Support)

| Event | Hook Name | Description |
|-------|-----------|-------------|
| `SESSION_START` | `session-start` | Session begins |
| `SESSION_END` | `session-end` | Session ends |
| `BEFORE_AGENT` | `user-prompt-submit` | Before processing prompt |
| `AFTER_AGENT` | `stop` | Agent stops |
| `BEFORE_TOOL` | `pre-tool-use` | Before tool execution |
| `AFTER_TOOL` | `post-tool-use` | After tool execution |
| `PRE_COMPACT` | `pre-compact` | Before context compaction |
| `SUBAGENT_START` | `subagent-start` | Subagent spawned |
| `SUBAGENT_STOP` | `subagent-stop` | Subagent finished |
| `PERMISSION_REQUEST` | `permission-request` | Permission requested |
| `NOTIFICATION` | `notification` | System notification |

### Gemini CLI (Pending PR #9070)

Gobby includes adapters for Gemini CLI's planned hook system. Once [PR #9070](https://github.com/google-gemini/gemini-cli/pull/9070) is merged, the following events will be supported: `SessionStart`, `SessionEnd`, `BeforeAgent`, `AfterAgent`, `BeforeTool`, `AfterTool`, `BeforeToolSelection`, `BeforeModel`, `AfterModel`, `PreCompress`, `Notification`.

### Codex CLI (Limited)

Currently only supports the `after_agent` notify hook for session-end notifications. Full hook support pending Codex CLI updates.

See [docs/hooks/CLAUDE_HOOKS_SCHEMA.md](docs/hooks/CLAUDE_HOOKS_SCHEMA.md) for detailed payload schemas.

## Roadmap

See [ROADMAP.md](ROADMAP.md) for the full implementation plan with sprint ordering and dependencies.

### Completed Features

| Feature | Description | Details |
|---------|-------------|---------|
| **Task Tracking** | Persistent tasks with dependencies and git sync | [TASKS.md](docs/plans/TASKS.md) |
| **Workflow Engine** | YAML-defined workflows with lifecycle triggers, phase enforcement, and LLM actions | [WORKFLOWS.md](docs/plans/WORKFLOWS.md) |
| **WebSocket Broadcasting** | Real-time hook event streaming to connected clients | [HOOK_EXTENSIONS.md](docs/plans/HOOK_EXTENSIONS.md) |
| **Memory System** | Persistent memory with remember/recall/forget operations, JSONL sync | [MEMORY.md](docs/plans/MEMORY.md) |
| **Skill Learning** | Extract skills from sessions via LLM, trigger matching, auto-apply | [MEMORY.md](docs/plans/MEMORY.md) |
| **Semantic Tool Search** | Embeddings-based tool discovery with OpenAI, hybrid recommend_tools | [MCP_PROXY_IMPROVEMENTS.md](docs/plans/MCP_PROXY_IMPROVEMENTS.md) |
| **Autonomous Handoff** | Pre-compact context extraction and session chaining | [AUTONOMOUS_HANDOFF.md](docs/plans/AUTONOMOUS_HANDOFF.md) |

### In Progress

| Feature | Description | Plan |
|---------|-------------|------|
| **Task System V2** | Commit linking for validation context, enhanced QA loops | [TASKS_V2.md](docs/plans/TASKS_V2.md) |

### Planned Features

| Feature | Description | Plan |
|---------|-------------|------|
| **Webhooks & Plugins** | HTTP callouts, Python plugin system | [HOOK_EXTENSIONS.md](docs/plans/HOOK_EXTENSIONS.md) |
| **Tool Metrics & Self-Healing** | Track tool success rates, suggest alternatives on failure | [MCP_PROXY_IMPROVEMENTS.md](docs/plans/MCP_PROXY_IMPROVEMENTS.md) |
| **Session Management** | Session CRUD MCP tools, handoff management | [SESSION_MANAGEMENT.md](docs/plans/SESSION_MANAGEMENT.md) |
| **Worktree Orchestration** | Parallel development with multiple agents in worktrees | [POST_MVP_ENHANCEMENTS.md](docs/plans/POST_MVP_ENHANCEMENTS.md) |
| **GitHub/Linear Integration** | Sync issues and PRs with gobby-tasks | [POST_MVP_ENHANCEMENTS.md](docs/plans/POST_MVP_ENHANCEMENTS.md) |
| **Subagent System** | Spawn specialized agents with different LLM providers | [SUBAGENTS.md](docs/plans/SUBAGENTS.md) |
| **Web Dashboard** | Real-time visualization of sessions, tasks, and agents | [UI.md](docs/plans/UI.md) |

### Milestones

**MVP (Complete)**
1. **Observable Gobby** — WebSocket event streaming + task system
2. **Workflow Engine** — Context sources, Jinja2 templating, 7 built-in workflow templates
3. **Memory-First Agents** — Persistent memory, skill learning, MCP tools, CLI, and JSONL sync

**In Progress**
4. **Extensible Gobby** — Webhooks and Python plugin system
5. **Smart MCP Proxy** — Semantic tool search complete; tool metrics and self-healing pending
6. **Production Ready** — Full integration and documentation
7. **Task System V2** — Commit linking, enhanced validation loops

**Post-MVP Vision**
8. **Worktree Orchestration** — Parallel development with multiple agents
9. **External Integrations** — GitHub/Linear sync
10. **Intelligence Layer** — Artifact index, enhanced skill routing, semantic memory
11. **Autonomous Execution** — Hands-off task execution with stuck detection
12. **Multi-Agent Orchestration** — Spawn agents with Claude, Gemini, Codex, or LiteLLM
13. **Visual Control Center** — Web dashboard for everything

## Contributing

We welcome contributions! Please see our development setup above and open a PR with your changes.

## License

MIT
