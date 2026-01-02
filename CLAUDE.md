# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Gobby is a local daemon that unifies Claude Code, Gemini CLI, and Codex through a hook interface for session tracking, and provides an MCP proxy with progressive tool discovery for efficient access to downstream servers.

## Development Commands

```bash
# Install dependencies (Python 3.11+)
uv sync

# Run the daemon in development
uv run gobby start --verbose

# Stop the daemon
uv run gobby stop

# Check daemon status
uv run gobby status

# Install hooks to current project for all detected CLIs
uv run gobby install

# Install hooks for specific CLI
uv run gobby install --claude
uv run gobby install --gemini
uv run gobby install --codex

# Initialize a new project
uv run gobby init

# Run tests
uv run pytest

# Run single test file
uv run pytest tests/test_example.py -v

# Run tests with specific marker
uv run pytest -m "not slow"

# Linting and formatting
uv run ruff check src/
uv run ruff format src/

# Type checking
uv run mypy src/
```

## Architecture

### Core Components

**Daemon Entry Points:**

- `src/cli.py` - Click-based CLI commands (`gobby start`, `gobby stop`, etc.)
- `src/runner.py` - Main daemon process that runs HTTP server, WebSocket server, and MCP connections

**Server Layer:**

- `src/servers/http.py` - FastAPI HTTP server with REST endpoints and MCP server
- `src/servers/websocket.py` - WebSocket server for real-time communication
- `src/mcp_proxy/server.py` - FastMCP server with MCP proxy tools (call_tool, list_tools, get_tool_schema, etc.)
- `src/mcp_proxy/stdio.py` - Stdio MCP server for Claude Code (proxies to HTTP daemon)

**MCP Proxy & Internal Tools:**

- `src/mcp_proxy/manager.py` - MCPClientManager handles connections to downstream MCP servers (context7, supabase, etc.) with multiple transport support (HTTP, stdio, WebSocket)
- `src/mcp_proxy/tools/internal.py` - InternalToolRegistry and InternalRegistryManager for `gobby-*` prefixed servers
- `src/mcp_proxy/tools/tasks.py` - Task tool registry (create_task, list_ready_tasks, etc.)
- `src/config/mcp.py` - MCP configuration management
- `src/storage/mcp.py` - LocalMCPManager for MCP server and tool storage in SQLite

**Hook System:**

- `src/hooks/hook_manager.py` - Central coordinator that delegates to subsystems
- `src/hooks/events.py` - HookEvent and HookEventType definitions
- `src/install/claude/hooks/hook_dispatcher.py` - Claude Code hook dispatcher script
- `src/install/gemini/hooks/hook_dispatcher.py` - Gemini CLI hook dispatcher script

**Session Management:**

- `src/sessions/manager.py` - SessionManager for registration, lookup, and status updates
- `src/sessions/summary.py` - SummaryGenerator for LLM-powered session summaries
- `src/sessions/transcripts/` - Transcript parsers (claude.py, base.py)

**Storage:**

- `src/storage/database.py` - SQLite database manager with thread-local connections
- `src/storage/sessions.py` - LocalSessionManager for session CRUD operations
- `src/storage/projects.py` - LocalProjectManager for project CRUD operations
- `src/storage/tasks.py` - LocalTaskManager for task CRUD operations
- `src/storage/task_dependencies.py` - TaskDependencyManager for dependency relationships
- `src/storage/session_tasks.py` - SessionTaskManager for session-task linking
- `src/storage/migrations.py` - Database migration system
- `src/sync/tasks.py` - TaskSyncManager for JSONL import/export

**Configuration:**

- `src/config/app.py` - DaemonConfig with YAML-based configuration (`~/.gobby/config.yaml`)
- Configuration hierarchy: CLI args > YAML file > Defaults

**LLM Providers:**

- `src/llm/service.py` - LLMService for multi-provider management
- `src/llm/claude.py`, `src/llm/gemini.py`, `src/llm/codex.py`, `src/llm/litellm.py` - Provider implementations

### Data Flow

1. **Hook Invocation**: CLI (Claude Code/Gemini/Codex) triggers hook via dispatcher script
2. **Hook Processing**: HookManager coordinates subsystems (DaemonClient, SessionManager, SummaryGenerator)
3. **Session Tracking**: Sessions stored in SQLite (`~/.gobby/gobby.db`)
4. **MCP Proxy**: Requests flow through MCPClientManager to downstream servers

### Key File Locations

- Config: `~/.gobby/config.yaml`
- Database: `~/.gobby/gobby.db` (sessions, projects, tasks, MCP servers, tools)
- Logs: `~/.gobby/logs/`
- Session summaries: `~/.gobby/session_summaries/`
- Project config: `.gobby/project.json`
- Task sync: `.gobby/tasks.jsonl`, `.gobby/tasks_meta.json`

## Autonomous Session Handoff

When a session is compacted (via `/compact`), Gobby automatically extracts and injects continuation context:

### What Happens on `/compact`

1. The `pre-compact` hook fires, triggering `extract_handoff_context`
2. Context is extracted from the transcript and git state
3. Formatted markdown is saved to `session.compact_markdown` in the database
4. On the next session start, this context is automatically injected

### Continuation Context Sections

When you see a `## Continuation Context` block at session start, it contains:

- **Active Task** - The gobby-task being worked on (if using task tracking)
- **In-Progress Work** - TodoWrite state from the previous session
- **Commits This Session** - Git commits made during the previous session
- **Uncommitted Changes** - Current `git status` output
- **Files Being Modified** - Files touched by Edit/Write tool calls
- **Original Goal** - The first user message from the previous session
- **Recent Activity** - Last 5 tool calls from the previous session

### Working with Continuation Context

When you see continuation context:

1. **Review the Original Goal** - Understand what the user was trying to accomplish
2. **Check Uncommitted Changes** - See what files have pending changes
3. **Resume from Recent Activity** - Understand where work left off
4. **Continue the task** - Pick up where the previous session ended

The context is rule-based extraction (no LLM summarization), so it preserves exact details like file paths and git status.

### Configuration

The handoff template is configurable in `~/.gobby/config.yaml`:

```yaml
compact_handoff:
  enabled: true
  prompt: |
    ## Continuation Context
    {active_task_section}
    {todo_state_section}
    ...
```

### Manual Pickup (for CLIs without hooks)

For CLIs and IDEs without a hooks system, use the `pickup` MCP tool to restore context:

```python
# Pickup from the most recent handoff-ready session
call_tool(server_name="gobby-sessions", tool_name="pickup", arguments={})

# Pickup from a specific session
call_tool(server_name="gobby-sessions", tool_name="pickup", arguments={
    "session_id": "sess-abc123"
})

# Pickup and link the current session as a child
call_tool(server_name="gobby-sessions", tool_name="pickup", arguments={
    "link_child_session_id": "current-session-id"
})
```

The tool returns the handoff context (prefers `compact_markdown`, falls back to `summary_markdown`).

## MCP Tool Progressive Disclosure

The daemon implements progressive tool discovery to reduce token usage:

1. **list_tools()** - Returns lightweight tool metadata (name + brief description)
2. **get_tool_schema()** - Returns full inputSchema for a specific tool from SQLite cache
3. **call_tool()** - Executes the tool on the appropriate server

Tool schemas are cached in SQLite (`mcp_servers` and `tools` tables) via `LocalMCPManager`.

## Internal Tool Registry Pattern

Internal tools use a `gobby-*` prefix for server names and are handled locally:

```python
# List internal task tools
list_tools(server="gobby-tasks")

# Get schema for a specific tool
get_tool_schema(server_name="gobby-tasks", tool_name="create_task")

# Call an internal tool
call_tool(server_name="gobby-tasks", tool_name="create_task", arguments={"title": "Fix bug"})
```

**Routing logic:**

- `gobby-*` servers → handled locally by `InternalRegistryManager`
- All others → proxied to downstream MCP servers via `MCPClientManager`

**Available internal servers:**

- `gobby-tasks` - Task CRUD, dependencies, ready work detection, git sync
- `gobby-memory` - Memory CRUD, recall, forget, list, stats
- `gobby-skills` - Skill CRUD, learning, matching, apply, export

## Task Management with gobby-tasks

Use the `gobby-tasks` MCP tools for persistent task tracking (requires daemon running):

1. **Start of session**: Call `list_ready_tasks` or `suggest_next_task` to find work
2. **New requests**: Create tasks with `create_task(title="...", description="...")`
3. **Complex work**: Use `expand_task` to break into subtasks with AI, or use `parent_task_id` manually
4. **Track progress**: Use `update_task` to change status (`open` -> `in_progress` -> `closed`)
5. **End of session**: Close completed tasks with `close_task(task_id="...")`

**Task Tools:**

| Tool | Description |
|------|-------------|
| `create_task` | Create a new task with title, priority, type, labels |
| `get_task` | Get task details including dependencies |
| `update_task` | Update task fields (status, priority, assignee, etc.) |
| `close_task` | Close a task with reason |
| `delete_task` | Delete a task (cascade optional) |
| `list_tasks` | List tasks with filters |
| `add_label` | Add a label to a task |
| `remove_label` | Remove a label from a task |
| `add_dependency` | Create dependency between tasks |
| `remove_dependency` | Remove a dependency |
| `list_ready_tasks` | List tasks with no unresolved blockers |
| `list_blocked_tasks` | List blocked tasks with their blockers |
| `expand_task` | Break task into subtasks using AI |
| `suggest_next_task` | AI suggests best next task to work on |
| `validate_task` | Validate task completion with AI |
| `sync_tasks` | Trigger git sync (import/export) |

```python
# Example MCP tool calls via daemon
call_tool(server_name="gobby-tasks", tool_name="list_ready_tasks", arguments={})
call_tool(server_name="gobby-tasks", tool_name="create_task", arguments={"title": "Fix auth bug"})
call_tool(server_name="gobby-tasks", tool_name="expand_task", arguments={"task_id": "gt-abc123"})
```

If tools fail, check daemon status: `uv run gobby status`

## Memory Management with gobby-memory

Use the `gobby-memory` MCP tools for persistent memory across sessions:

**Memory Tools:**

| Tool | Description |
|------|-------------|
| `remember` | Store a new memory with content, type, importance, tags |
| `recall` | Retrieve memories by query/filters with importance ranking |
| `forget` | Delete a memory by ID |
| `list_memories` | List all memories with filtering (type, importance, project) |
| `get_memory` | Get full details of a specific memory |
| `update_memory` | Update content, importance, or tags of a memory |
| `memory_stats` | Get statistics (count by type, average importance) |

```python
# Example memory operations
call_tool(server_name="gobby-memory", tool_name="remember", arguments={
    "content": "This project uses pytest with conftest.py fixtures",
    "memory_type": "fact",
    "importance": 0.8
})
call_tool(server_name="gobby-memory", tool_name="recall", arguments={"query": "testing"})
```

**Memory Types:** `fact`, `preference`, `pattern`, `context`

## Skill Management with gobby-skills

Use the `gobby-skills` MCP tools for reusable instructions:

**Skill Tools:**

| Tool | Description |
|------|-------------|
| `learn_skill_from_session` | Extract skills from a completed session via LLM |
| `list_skills` | List available skills with optional filtering |
| `get_skill` | Get full skill details including instructions |
| `delete_skill` | Delete a skill |
| `match_skills` | Find skills matching a prompt (trigger pattern) |
| `create_skill` | Create a skill directly with provided instructions |
| `update_skill` | Update skill name, instructions, trigger, or tags |
| `apply_skill` | Return skill instructions and mark as used |
| `export_skills` | Export skills to .gobby/skills/ as markdown files |

```python
# Example skill operations
call_tool(server_name="gobby-skills", tool_name="create_skill", arguments={
    "name": "run-tests",
    "instructions": "Run tests with: uv run pytest -v",
    "trigger_pattern": "test|pytest"
})
call_tool(server_name="gobby-skills", tool_name="apply_skill", arguments={"skill_id": "sk-abc123"})
```

## Workflow Engine

Gobby includes a workflow engine that enforces structured AI agent behavior through phases and tool restrictions.

### Workflow Types

**Lifecycle Workflows** - Event-driven, respond to session events (e.g., `session-handoff` for context handoff). Multiple can run simultaneously.

**Phase-Based Workflows** - State machines with tool restrictions and transitions (e.g., `plan-execute`, `plan-act-reflect`). Only one active per session.

### Key Concepts

- **Phases**: Named states with allowed/blocked tools
- **Transitions**: Automatic phase changes based on conditions
- **Exit Conditions**: Requirements to leave a phase (e.g., user approval, artifact exists)
- **Actions**: Operations executed on phase enter/exit (inject context, capture artifacts, etc.)

### Quick Start

```bash
# List available workflows
uv run gobby workflow list

# Activate a workflow for current session
uv run gobby workflow set plan-execute

# Check workflow status
uv run gobby workflow status

# Manual phase override (escape hatch)
uv run gobby workflow phase <phase-name> --force
```

### Workflow YAML Schema

```yaml
name: my-workflow
type: phase              # or "lifecycle"
extends: base-workflow   # Optional inheritance

phases:
  - name: plan
    allowed_tools: [Read, Glob, Grep, WebSearch]
    blocked_tools: [Edit, Write, Bash]
    exit_conditions:
      - type: user_approval
        prompt: "Ready to implement?"

  - name: execute
    allowed_tools: all

triggers:
  on_session_start:
    - action: enter_phase
      phase: plan
```

### Built-in Templates

| Template | Type | Description |
|----------|------|-------------|
| `session-handoff` | lifecycle | Session summary and context handoff (default) |
| `plan-execute` | phase | Planning with tool restrictions, then execution |
| `react` | phase | Reason-Act-Observe loop |
| `plan-act-reflect` | phase | Periodic reflection checkpoints |
| `plan-to-tasks` | phase | Decompose plan into tasks, execute with verification |
| `test-driven` | phase | TDD: write-test -> implement -> refactor |

### Tool Filtering

When a phase-based workflow is active, `list_tools()` returns only tools allowed in the current phase. Blocked tools are hidden (not grayed out).

### Configuration

Workflows can be disabled globally via `~/.gobby/config.yaml`:

```yaml
workflow:
  enabled: false  # Disable all workflow enforcement (default: true)
  timeout: 30.0   # Timeout for workflow operations in seconds
```

When `workflow.enabled: false`, all workflow hooks pass through (allow all tools, no blocking).

### State Behavior

- **Workflow state resets when session ends** - Each session starts fresh
- **Tasks persist across sessions** - Use `gobby-tasks` for durable work items
- **Lifecycle workflows auto-run** - `session-handoff` is always active by default

### Platform Notes

- **Claude Code / Gemini CLI**: Full enforcement (tool blocking, context injection)
- **Codex**: Notify hook only - can track state but cannot enforce restrictions

### File Locations

| Location | Purpose |
|----------|---------|
| `~/.gobby/workflows/` | Global workflow definitions |
| `.gobby/workflows/` | Project-specific workflows |
| `~/.gobby/workflows/templates/` | Built-in templates |

For complete documentation, see [docs/guides/workflows.md](docs/guides/workflows.md).

## Testing

Tests use pytest with asyncio support. Key test configuration in `pyproject.toml`:

- `asyncio_mode = "auto"` - Automatic async test detection
- Coverage threshold: 80%
- Markers: `slow`, `integration`, `e2e`
