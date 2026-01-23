# AGENTS.md

This file provides guidance to Codex (OpenAI) when working with code in this repository.

## Project Overview

Gobby is a local-first daemon that unifies AI coding assistants (Codex, Claude Code, Gemini CLI) under one persistent, extensible platform. It provides:

- **Session management** that survives restarts and context compactions
- **Task system** with dependency graphs, TDD expansion, and validation gates
- **MCP proxy** with progressive disclosure (tools stay lightweight until needed)
- **Workflow engine** that enforces steps, tool restrictions, and transitions
- **Worktree orchestration** for parallel development
- **Memory system** for persistent facts across sessions

**Built with Gobby**: Most of this codebase was written by AI agents using Gobby's own task system and workflows.

## Development Commands

```bash
# Environment setup
uv sync                          # Install dependencies (Python 3.11+)

# Daemon management
uv run gobby start --verbose     # Start daemon with verbose logging
uv run gobby stop                # Stop daemon
uv run gobby restart             # Restart daemon
uv run gobby status              # Check daemon status

# Project initialization
uv run gobby init                # Initialize project (.gobby/)
uv run gobby install             # Install hooks for detected CLIs

# Code quality
uv run ruff check src/           # Lint
uv run ruff format src/          # Auto-format
uv run mypy src/                 # Type check

# Testing
uv run pytest tests/test_file.py -v    # Run specific test file
uv run pytest tests/storage/ -v        # Run specific module
```

**Coverage threshold**: 80% (enforced in CI)

**Test markers**: `unit`, `slow`, `integration`, `e2e`

## Architecture Overview

### Directory Structure

```text
src/gobby/
├── cli/                    # CLI commands (Click)
├── runner.py              # Main daemon entry point
├── servers/               # HTTP and WebSocket servers
├── mcp_proxy/            # MCP proxy layer (20+ tool modules)
├── hooks/                # Hook event system
├── adapters/             # CLI-specific hook adapters (codex.py)
├── sessions/             # Session lifecycle and parsers
├── tasks/                # Task system (expansion, validation)
├── workflows/            # Workflow engine (state machine)
├── agents/               # Agent spawning logic
├── worktrees/            # Git worktree management
├── memory/               # Memory system (TF-IDF, semantic)
├── storage/              # SQLite storage layer
├── llm/                  # Multi-provider LLM abstraction
├── config/               # Configuration (YAML/JSON)
└── utils/                # Git, logging, project utilities
```

### Key File Locations

| Path | Purpose |
| :--- | :--- |
| `~/.gobby/config.yaml` | Daemon configuration |
| `~/.gobby/gobby-hub.db` | SQLite database (sessions, tasks, etc.) |
| `~/.gobby/logs/` | Log files |
| `.gobby/project.json` | Project metadata |
| `.gobby/tasks.jsonl` | Task sync file (git-native) |

## MCP Tool Discovery (Progressive Disclosure)

When working on project tasks, Gobby uses progressive disclosure to minimize token usage. Follow this pattern:

1.  **Discover available servers**: `list_mcp_servers()`
2.  **List tools on a specific server (lightweight)**: `list_tools(server="gobby-tasks")`
3.  **Get full schema when you need to call a tool**: `get_tool_schema(server_name="gobby-tasks", tool_name="create_task")`
4.  **Execute the tool**: `call_tool(server_name="gobby-tasks", tool_name="create_task", arguments={...})`

### Internal MCP Servers

| Server | Purpose | Key Tools |
| :--- | :--- | :--- |
| `gobby-tasks` | Task management | `create_task`, `expand_task`, `close_task`, `suggest_next_task` |
| `gobby-sessions` | Session handoff | `pickup`, `get_handoff_context`, `list_sessions` |
| `gobby-memory` | Persistent memory | `create_memory`, `search_memories`, `delete_memory`, `update_memory` |
| `gobby-workflows` | Workflow control | `activate_workflow`, `set_variable`, `get_status` |
| `gobby-agents` | Agent spawning | `start_agent`, `list_agents` |
| `gobby-worktrees` | Git worktrees | `spawn_agent_in_worktree`, `list_worktrees` |
| `gobby-skills` | Skill management | `list_skills`, `get_skill`, `install_skill` |

## Task Management

When working on project tasks that require file modifications, use the task system for traceability.

### Getting Your Session ID

**Tasks require a `session_id` parameter.** This is usually injected by the Gobby daemon via the `session-start` hook.

**Where to find it**: Look for `session_id:` in your system context or initial prompt.

**Fallback - Using `get_current`**:
If `session_id` is missing, look it up:
```python
call_tool(server_name="gobby-sessions", tool_name="get_current", arguments={
    "external_id": "<your-codex-session-id>",
    "source": "codex"
})
```

### Workflow Requirements

When modifying files, you should have a task with `status: in_progress`. This ensures traceability of changes.

```python
# 1. Create task
call_tool("gobby-tasks", "create_task", {"title": "...", "session_id": "...", "task_type": "feature"})

# 2. Set to in_progress
call_tool("gobby-tasks", "update_task", {"task_id": "gt-xxx", "status": "in_progress"})

# 3. Perform edits...

# 4. Commit with task ID: [gt-xxx] feat: ...

# 5. Close task
call_tool("gobby-tasks", "close_task", {"task_id": "gt-xxx", "commit_sha": "..."})
```

## Session Handoff

Gobby preserves context across sessions. Look for `## Continuation Context` blocks at session start - this contains your previous state, git status, and pending tasks.

## Spawned Agent Protocol

When spawned as a subagent (by another agent using `start_agent` or `spawn_agent_in_worktree`), use these tools to communicate results and terminate cleanly:

### 1. Get your session info (for self-termination)

```python
call_tool(server_name="gobby-sessions", tool_name="get_current", arguments={
    "external_id": "<your-session-id>",  # From environment or transcript path
    "source": "codex"  # or "gemini", "claude", etc.
})
# Returns: {"session_id": "...", "project_id": "...", "status": "...", "agent_run_id": "..."}
```

### 2. Send results to parent

```python
call_tool(server_name="gobby-agents", tool_name="send_to_parent", arguments={
    "message": "Task completed: implemented authentication flow"
})
```

### 3. Mark work complete

```python
call_tool(server_name="gobby-sessions", tool_name="mark_loop_complete", arguments={
    "session_id": "<session_id>"
})
```

### 4. Terminate yourself (when fully done)

```python
call_tool(server_name="gobby-agents", tool_name="kill_agent", arguments={
    "run_id": "<agent_run_id>"  # From get_current response
})
```

**IMPORTANT**: Do NOT use `/quit` or similar CLI commands - they don't work for spawned agents. Always use `kill_agent` with your `agent_run_id` to properly terminate.

## Code Conventions

- **Type Hints**: Required for all functions.
- **Python Version**: Target Python 3.11+.
- **Formatting**: Use `ruff format`.
- **Linting**: Use `ruff check`.
- **Testing**: Minimum 80% coverage. Use `pytest`.
- **Async**: Use `async/await` for I/O operations (FastAPI, httpx).

## Commit & Pull Request Guidelines

Write clear, descriptive commit messages. PRs should be focused, include a concise description, reference related issues, and ensure CI passes. Update docs when behavior changes.

## Troubleshooting

- **"Edit/Write blocked"**: Ensure you have a task in `in_progress` status.
- **"Task has no commits"**: You must commit your changes with the task ID in the message before closing.
- **Agent depth exceeded**: You are too deep in nested agent spawns (limit is 3).
