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
uv sync                          # Install dependencies (Python 3.13+)

# Daemon management
uv run gobby start --verbose     # Start daemon with verbose logging
uv run gobby stop                # Stop daemon
uv run gobby status              # Check daemon status

# Code quality
uv run ruff check src/           # Lint
uv run ruff format src/          # Auto-format
uv run mypy src/                 # Type check

# Testing (run specific tests, not full suite)
uv run pytest tests/test_file.py -v    # Run specific test file
uv run pytest tests/storage/ -v        # Run specific module
```

**Coverage threshold**: 80% (enforced in CI)

**Test markers**: `unit`, `slow`, `integration`, `e2e`

## Architecture Overview

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
| `~/.gobby/gobby-hub.db` | SQLite database |
| `.gobby/project.json` | Project metadata |
| `.gobby/tasks.jsonl` | Task sync file |

## MCP Tool Discovery

Gobby uses progressive disclosure for MCP tools. Use `list_mcp_servers()` to discover available servers, then `list_tools(server="...")` for lightweight metadata, and `get_tool_schema(server, tool)` only when you need the full schema.

**Never load all schemas upfront** - it wastes your context window.

See skill: **discovering-tools** for the complete pattern.

## Task Management

Before editing files, create or claim a task:

```python
# Create task
call_tool("gobby-tasks", "create_task", {
    "title": "Fix bug",
    "task_type": "bug",
    "session_id": "<your_session_id>"  # From SessionStart context
})

# Set to in_progress
call_tool("gobby-tasks", "update_task", {
    "task_id": "...",
    "status": "in_progress"
})

# After work: commit with [task-id] prefix, then close
call_tool("gobby-tasks", "close_task", {
    "task_id": "...",
    "commit_sha": "..."
})
```

**If blocked**: See skill: **claiming-tasks** for help.

## Session Context

Your `session_id` is injected at session start. Look for:

```
session_id: fd59c8fc-...
```

If not present, use `get_current`:

```python
call_tool("gobby-sessions", "get_current", {
    "external_id": "<your-codex-session-id>",
    "source": "codex"
})
```

## Spawned Agent Protocol

When spawned as a subagent (via `start_agent` or `spawn_agent_in_worktree`), use these tools to communicate and terminate:

### 1. Get your session info

```python
call_tool("gobby-sessions", "get_current", {
    "external_id": "<your-session-id>",
    "source": "codex"
})
# Returns: {"session_id": "...", "agent_run_id": "..."}
```

### 2. Send results to parent

```python
call_tool("gobby-agents", "send_to_parent", {
    "message": "Task completed: implemented authentication flow"
})
```

### 3. Mark work complete

```python
call_tool("gobby-sessions", "mark_loop_complete", {
    "session_id": "<session_id>"
})
```

### 4. Terminate yourself

```python
call_tool("gobby-agents", "kill_agent", {
    "run_id": "<agent_run_id>"  # From get_current response
})
```

**IMPORTANT**: Do NOT use `/quit` or similar CLI commands - always use `kill_agent` to properly terminate.

## Code Conventions

- **Type Hints**: Required for all functions
- **Python Version**: 3.13+
- **Formatting**: `ruff format`
- **Linting**: `ruff check`
- **Testing**: 80% coverage minimum with `pytest`
- **Async**: Use `async/await` for I/O operations

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Edit/Write blocked" | Create or claim a task first (see **claiming-tasks** skill) |
| "Task has no commits" | Commit with `[task-id]` in message before closing |
| "Agent depth exceeded" | Max nesting is 3 - reduce agent spawning depth |
| Import errors | Run `uv sync` |
