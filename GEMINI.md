# Gobby - Project Context & Instructions

## Project Overview

**Gobby** is a local-first daemon that unifies AI coding assistants (Claude Code, Gemini CLI, Codex) into a persistent, orchestrated environment. It provides long-term memory, session management, and an MCP (Model Context Protocol) proxy with lazy tool discovery.

* **Core Tech:** Python 3.11+, FastAPI, FastMCP, SQLite, Click.
* **Key Concept:** "Unified Agent Manager" - Gobby sits between the AI CLI and the OS/Tools.

## Environment & Setup

This project uses **[uv](https://github.com/astral-sh/uv)** for dependency management.

### Installation

```bash
uv sync
```

### Running the Daemon

```bash
# Start daemon (verbose for dev)
uv run gobby start --verbose

# Check status
uv run gobby status
```

## Development Workflow

### Quality Checks (Mandatory)

All changes must pass these checks.

```bash
# Linting & Formatting
uv run ruff check src/
uv run ruff format src/

# Type Checking (Strict)
uv run mypy src/

# Testing
uv run pytest
```

### Directory Structure

* `src/gobby/cli/`: Click CLI entry points.
* `src/gobby/runner.py`: Main daemon process runner.
* `src/gobby/servers/`: HTTP (:8765) and WebSocket (:8766) servers.
* `src/gobby/hooks/`: Central hook management logic.
* `src/gobby/mcp_proxy/`: Logic for connecting to downstream MCP servers.
* `src/gobby/storage/`: SQLite database layer (`~/.gobby/gobby-hub.db`).

## Architecture Quick Reference

1. **CLI Hook** (from Claude/Gemini) -> **Hook Script** -> **HTTP POST** (`/api/v1/hooks/...`)
2. **Daemon** (`HookManager`) processes event -> Updates **Session** / **Memory**.
3. **MCP Proxy**:
   * Tools are *not* loaded at startup.
   * `list_tools` fetches metadata only.
   * `get_tool_schema` fetches full schema on-demand.

## Agent Protocol (CRITICAL)

> "If it's not a task, it didn't happen."

You are operating within a Gobby-enabled environment. You **must** use the `gobby-tasks` system to track your work. Do not rely on chat history or loose files.

## 🛑 CRITICAL: NO CODE EDITS WITHOUT TASK ID

**Required Sequence (Progressive Disclosure):**
1. **List Tools:** `mcp_list_tools(server_name="gobby-tasks")` (Metadata only, finding tools)
2. **Get Schema:** `mcp_get_tool_schema(server="gobby-tasks", tool="create_task")`
    * *Constraint:* You MUST fetch the schema for a specific tool **at least once** in the current session before calling it.
3. **Create Task:** `mcp_call_tool(server="gobby-tasks", tool="create_task", ...)`
4. **Link Session:** `mcp_call_tool(server="gobby-tasks", tool="link_task_to_session", ...)`

> "If it's not a task, it didn't happen."

You are operating within a Gobby-enabled environment. You **must** use the `gobby-tasks` system to track your work. Do not rely on chat history or loose files.

### Getting Your Session ID

**Tasks require a `session_id` parameter.** The session_id may be injected into your context by the Gobby daemon via the `session-start` hook.

**Where to find it**: Look for `session_id:` in your system context at the start of the conversation.

**Fallback - Using `get_current`**: If `session_id` wasn't injected in your context, you can look it up using your CLI's external session ID:

```python
# Extract external_id from your transcript path filename
# The external_id is typically the session ID portion of the path

mcp_call_tool(server="gobby-sessions", tool="get_current", arguments={
    "external_id": "<your-session-id>",
    "source": "gemini"  # or "antigravity" if running in Antigravity IDE
})
# Returns: {"session_id": "...", "found": true, ...}
```

### ⚠️ Common Mistake: Using list_sessions to Find Your Session

**WRONG:**
```python
# ❌ This will NOT work with multiple active sessions!
result = mcp_call_tool("gobby-sessions", "list_sessions", {"status": "active", "limit": 1})
my_session_id = result["sessions"][0]["id"]  # Could be ANY active session!
```

**CORRECT:**
```python
# ✅ Use get_current with your unique identifiers
result = mcp_call_tool("gobby-sessions", "get_current", {"external_id": "...", "source": "gemini"})
my_session_id = result["session_id"]
```

Multiple sessions can be active simultaneously (parallel agents, multiple terminals). The `get_current` tool uses a composite key (external_id + source + machine_id + project_id) to reliably find YOUR session.

### 1. Start of Session

1. **Check Context:**
    * `mcp_call_tool("gobby-tasks", "list_ready_tasks", {})`
    * `mcp_call_tool("gobby-tasks", "get_task", {"task_id": "..."})` (if ID is known)

2. **Define Work:**
    * **Get Schema:** `mcp_get_tool_schema(server="gobby-tasks", tool="create_task")`
        * *Constraint:* You MUST fetch the schema for a specific tool **at least once** in the current session before calling it.
    * **Create Task:** `mcp_call_tool(server="gobby-tasks", tool="create_task", arguments={"title": "...", "session_id": "<your_session_id>"})`

3. **Link Session:**
    * `mcp_call_tool(server="gobby-tasks", tool="link_task_to_session", {})`

### 2. Execution Loop

* **Update Status:** Mark task as `in_progress`.
* **Dependencies:** If blocked, use `add_dependency`.
* **Bugs:** Found a side-issue? `create_task` (don't get distracted).

### Task Workflow (Mandatory)

1. **Start Task**:
   * **Get Schema:** `mcp_get_tool_schema(..., tool="update_task")` (If not yet fetched this session)
   * **Update Status:** `mcp_call_tool(..., tool="update_task", arguments={..., "status": "in_progress"})`
2. **Understand**: Read the task details and linked issues.
3. **Work**: Implement the changes.
4. **Confirm**: `gobby-tasks.list_tasks(status="in_progress")` to verify tracking.
5. **Close**: See Exit Protocol below.

> **CRITICAL**: Do NOT leave tasks `in_progress` if you are done. Always close them with a commit SHA.

### 3. End of Session ("Landing the Plane")

## 🏁 EXIT PROTOCOL

1. **Commit Work:** `git commit -m "..."`
2. **Verify SHA:** `git rev-parse HEAD`
3. **Get Schema:** `mcp_get_tool_schema(..., tool="close_task")` (If not yet fetched this session)
4. **Close Task:** `mcp_call_tool(..., tool="close_task", arguments={..., "commit_sha": "..."})`

## MCP Tool Usage Guide

Gobby uses a proxy pattern for tools.

* **List Tools:** `mcp_list_tools(server_name="gobby-tasks")`
* **Get Schema:** `mcp_get_tool_schema(server_name="gobby-tasks", tool_name="create_task")`
* **Call Tool:** `mcp_call_tool(server_name="gobby-tasks", tool_name="create_task", arguments={...})`

*Note: Replace "gobby-tasks" with "gobby-memory" for other internal domains.*

## Task Validation Overrides

* **Task #2124 (Workflow Cache Reload):** Validation criteria demanded comprehensive automatic cache invalidation (watchdog/mtime), but implementation followed the simpler manual reload approach specified in the task description. User authorized override on 2026-01-12.
