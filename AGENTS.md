# AGENTS.md

This file provides guidance to AI Agents (Claude Code, Gemini, Codex, etc.) when working with this repository.

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
- Database: `~/.gobby/gobby-hub.db` (SQLite database for sessions, projects, tasks, memories, MCP servers)
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
| `gobby-workflows` | Workflow activation, session variables |
| `gobby-sessions` | Session lookup, handoff context |
| `gobby-metrics` | Tool metrics and statistics |

Use `get_tool_schema` to look up parameter details for any tool.

## Task Management (gobby-tasks)

### Getting Your Session ID

**Tasks require a `session_id` parameter.** The session_id may be injected into your context by the Gobby daemon via the `session-start` hook.

**Where to find it**: Look for `session_id:` in your system context at the start of the conversation.

**Fallback - Using `get_current`**: If `session_id` wasn't injected in your context, you can look it up using your CLI's external session ID:

```python
# Extract external_id from your Codex session/transcript path

call_tool(server_name="gobby-sessions", tool_name="get_current", arguments={
    "external_id": "<your-codex-session-id>",
    "source": "codex"
})
# Returns: {"session_id": "...", "found": true, ...}
```

### CRITICAL: Workflow Requirement

**Before editing files (Edit/Write), you MUST have a task with `status: in_progress`.** The hook blocks file modifications without an active task.

```python
# 1. Create task (task_type: task, bug, feature, epic)
call_tool(server_name="gobby-tasks", tool_name="create_task", arguments={"title": "My task", "task_type": "feature", "session_id": "<your_session_id>"})

# 2. Set to in_progress BEFORE editing
call_tool(server_name="gobby-tasks", tool_name="update_task", arguments={"task_id": "gt-xxx", "status": "in_progress"})
```

### Task Workflow

1. **Start of session**: `list_ready_tasks` or `suggest_next_task`
2. **New work**: `create_task(title, description, session_id)` - session_id required
3. **Complex work**: `expand_task` for subtasks
4. **Track progress**: `update_task(status="in_progress")`
5. **Complete work**: Commit with `[task-id]` in message, then `close_task(commit_sha="...")`

### Available MCP Tools

**Task CRUD:**

| Tool | Description |
|------|-------------|
| `create_task` | Create a new task |
| `get_task` | Get task details with dependencies |
| `update_task` | Update task fields |
| `close_task` | Close a task with reason |
| `delete_task` | Delete a task |
| `list_tasks` | List tasks with filters |
| `add_label` | Add a label to a task |
| `remove_label` | Remove a label from a task |

**Dependencies:**

| Tool | Description |
|------|-------------|
| `add_dependency` | Add dependency between tasks |
| `remove_dependency` | Remove a dependency |
| `get_dependency_tree` | Get blockers/blocking tasks |
| `check_dependency_cycles` | Detect circular dependencies |
| `list_ready_tasks` | List unblocked tasks |
| `list_blocked_tasks` | List blocked tasks |

**Session & Sync:**

| Tool | Description |
|------|-------------|
| `link_task_to_session` | Associate task with session |
| `get_session_tasks` | Tasks linked to a session |
| `get_task_sessions` | Sessions that touched a task |
| `sync_tasks` | Trigger import/export |
| `get_sync_status` | Get sync status |

**LLM Expansion:**

| Tool | Description |
|------|-------------|
| `expand_task` | Break task into subtasks with AI |
| `analyze_complexity` | Get complexity score |
| `expand_all` | Expand all unexpanded tasks |
| `suggest_next_task` | AI suggests next task to work on |

**Validation:**

| Tool | Description |
|------|-------------|
| `validate_task` | Validate task completion |
| `get_validation_status` | Get validation details |
| `reset_validation_count` | Reset failure count for retry |

### Task Metadata

**Task Types:**

- `bug` - Something broken
- `feature` - New functionality
- `task` - Work item (tests, docs, refactoring)
- `epic` - Large feature with subtasks
- `chore` - Maintenance (dependencies, tooling)

**Priorities:**

- `1` - High (major features, important bugs)
- `2` - Medium (default)
- `3` - Low (polish, optimization)

### IMPORTANT: Closing Tasks

- **Always commit first**, then close with `commit_sha`
- If `close_task` errors about missing commits, commit the changes
- `no_commit_needed=true` is ONLY for non-code tasks (research, planning)
- Never fabricate `override_justification`

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
    "session_context": "summary_markdown" # default
})
```

**Context sources** (`session_context` param):

- `summary_markdown`: Parent session's summary (default)
- `compact_markdown`: Handoff context
- `transcript:N`: Last N messages from transcript
- `file:path`: Content of a file in the project

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
uv run gobby workflows list       # Available workflows
uv run gobby workflows set NAME   # Activate workflow
uv run gobby workflows status     # Current state
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

## Memory

**Memory** (`gobby-memory`): `remember`, `recall`, `forget` - persistent facts across sessions

## Hook Events

| Event | Description |
|-------|-------------|
| `session_start/end` | Session lifecycle |
| `before_tool/after_tool` | Tool execution (can block) |
| `stop` | Agent stop (can block) |
| `pre_compact` | Before context compaction |

Plugins: `~/.gobby/plugins/` or `.gobby/plugins/`

## Planning & Documentation

### Managing AI-Generated Planning Documents

AI assistants often create planning and design documents (PLAN.md, IMPLEMENTATION.md, etc.).

**Best Practice: Use a dedicated directory**

- Create a `history/` directory in the project root
- Store ALL AI-generated planning/design docs in `history/`
- Keep the repository root clean
- Only access `history/` when explicitly asked to review past planning

## Testing

```bash
uv run pytest                    # All tests
uv run pytest tests/file.py -v   # Single file
uv run pytest -m "not slow"      # Skip slow tests
```

Coverage threshold: 80%. Markers: `slow`, `integration`, `e2e`
