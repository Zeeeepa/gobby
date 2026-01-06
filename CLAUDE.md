# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Project Overview

Gobby is a local daemon that unifies Claude Code, Gemini CLI, and Codex through a hook interface for session tracking, and provides an MCP proxy with progressive tool discovery for efficient access to downstream servers.

## Development Commands

```bash
uv sync                          # Install dependencies (Python 3.11+)
uv run gobby start --verbose     # Run daemon
uv run gobby stop                # Stop daemon
uv run gobby status              # Check status
uv run gobby install             # Install hooks to project
uv run pytest                    # Run tests
uv run ruff check src/ && uv run ruff format src/  # Lint/format
uv run mypy src/                 # Type check
```

## Architecture

### Core Components

- `src/cli.py` - Click CLI commands
- `src/runner.py` - Main daemon process
- `src/servers/http.py` - FastAPI HTTP server
- `src/mcp_proxy/server.py` - MCP proxy tools
- `src/mcp_proxy/manager.py` - MCPClientManager for downstream servers
- `src/hooks/hook_manager.py` - Central hook coordinator
- `src/sessions/manager.py` - Session tracking
- `src/storage/` - SQLite storage (database.py, sessions.py, tasks.py, etc.)
- `src/config/app.py` - YAML config (`~/.gobby/config.yaml`)

### Key File Locations

- Config: `~/.gobby/config.yaml`
- Database: `~/.gobby/gobby.db`
- Logs: `~/.gobby/logs/`
- Project config: `.gobby/project.json`
- Task sync: `.gobby/tasks.jsonl`

## MCP Tool Discovery

Use progressive disclosure to minimize tokens:

1. `list_tools(server="...")` - Brief metadata only
2. `get_tool_schema(server_name, tool_name)` - Full schema when needed
3. `call_tool(server_name, tool_name, arguments)` - Execute

### Internal Servers (gobby-*)

| Server | Purpose |
|--------|---------|
| `gobby-tasks` | Task CRUD, dependencies, ready work, validation |
| `gobby-agents` | Subagent spawning with context injection |
| `gobby-worktrees` | Git worktree management |
| `gobby-memory` | Persistent memory across sessions |
| `gobby-skills` | Reusable instruction templates |
| `gobby-workflows` | Workflow activation, session variables |
| `gobby-sessions` | Session lookup, handoff context |
| `gobby-metrics` | Tool metrics and statistics |

Use `get_tool_schema` to look up parameter details for any tool.

## Task Management (gobby-tasks)

### CRITICAL: Workflow Requirement

**Before editing files (Edit/Write), you MUST have a task with `status: in_progress`.** The hook blocks file modifications without an active task.

```python
# 1. Create task (task_type: task, bug, feature, epic)
call_tool(server_name="gobby-tasks", tool_name="create_task", arguments={"title": "My task", "task_type": "feature"})

# 2. Set to in_progress BEFORE editing
call_tool(server_name="gobby-tasks", tool_name="update_task", arguments={"task_id": "gt-xxx", "status": "in_progress"})
```

### Task Workflow

1. **Start of session**: `list_ready_tasks` or `suggest_next_task`
2. **New work**: `create_task(title, description, task_type`
3. **Complex work**: `expand_task` or `expand_from_spec` for subtasks
4. **Track progress**: `update_task(status="in_progress")`
5. **Complete work**: Commit with `[task-id]` in message, then `close_task(commit_sha="...")`

### IMPORTANT: Closing Tasks

- **Always commit first**, then close with `commit_sha`
- If `close_task` errors about missing commits, commit the changes
- `no_commit_needed=true` is ONLY for non-code tasks (research, planning)
- Never fabricate `override_justification`

### Spec Documents

When creating tasks from a spec/PRD/design doc, use `expand_from_spec(spec_path)` - do NOT manually iterate. It ensures TDD pairs and proper dependencies.

### Commit Linking

Include task ID in commit messages for auto-linking:

- `[gt-abc123] feat: add feature` (recommended)
- `gt-abc123: fix bug`

## Session Handoff

On `/compact`, Gobby extracts continuation context (git state, tool calls, todo state) and injects it on next session start. Look for `## Continuation Context` blocks.

For CLIs without hooks, use `gobby-sessions.pickup()` to restore context.

## Agent Spawning (gobby-agents)

Spawn subagents with context injection:

```python
call_tool(server_name="gobby-agents", tool_name="start_agent", arguments={
    "prompt": "Implement the feature",
    "mode": "terminal",  # or in_process, embedded, headless
    "workflow": "plan-execute",
    "parent_session_id": "sess-abc",
})
```

**Context sources** (`session_context` param): `summary_markdown`, `compact_markdown`, `transcript:N`, `file:path`

**Safety**: Agent depth limited (default 3), tools filtered per workflow step.

## Worktree Management (gobby-worktrees)

Create isolated git worktrees for parallel development:

```python
# Create worktree + spawn agent in one call
call_tool(server_name="gobby-worktrees", tool_name="spawn_agent_in_worktree", arguments={
    "prompt": "Implement auth",
    "branch_name": "feature/auth",
    "task_id": "gt-abc123",
    "mode": "terminal",
})
```

Statuses: `active` → `stale` → `merged` → `abandoned`

## Workflows

Step-based workflows enforce tool restrictions:

```bash
uv run gobby workflow list       # Available workflows
uv run gobby workflow set NAME   # Activate workflow
uv run gobby workflow status     # Current state
```

Built-in: `plan-execute`, `test-driven`, `plan-act-reflect`

When active, `list_tools()` returns only allowed tools for current step.

### Session Variables

```python
# Link session to parent task (enforced by stop hook)
call_tool(server_name="gobby-workflows", tool_name="set_variable", arguments={
    "name": "session_task",
    "value": "gt-abc123"
})
```

## Memory & Skills

**Memory** (`gobby-memory`): `remember`, `recall`, `forget` - persistent facts across sessions

**Skills** (`gobby-skills`): `create_skill`, `apply_skill`, `match_skills` - reusable instructions

## Hook Events

| Event | Description |
|-------|-------------|
| `session_start/end` | Session lifecycle |
| `before_tool/after_tool` | Tool execution (can block) |
| `stop` | Agent stop (can block) |
| `pre_compact` | Before context compaction |

Plugins: `~/.gobby/plugins/` or `.gobby/plugins/`

## Testing

```bash
uv run pytest                    # All tests
uv run pytest tests/file.py -v   # Single file
uv run pytest -m "not slow"      # Skip slow tests
```

Coverage threshold: 80%. Markers: `slow`, `integration`, `e2e`
