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

## MCP Tool Semantic Search

The daemon includes semantic search for finding tools by natural language queries:

### Search Modes

| Mode | Description |
|------|-------------|
| `llm` | LLM-based recommendations using full server descriptions (default) |
| `semantic` | Embedding similarity search across all tools |
| `hybrid` | Semantic search followed by LLM re-ranking |

### MCP Tools

```python
# Search for tools by description
call_tool(server_name="gobby", tool_name="search_tools", arguments={
    "query": "send emails",
    "top_k": 5,
    "min_similarity": 0.3
})

# Get tool recommendations for a task
call_tool(server_name="gobby", tool_name="recommend_tools", arguments={
    "task_description": "I need to query a PostgreSQL database",
    "search_mode": "hybrid"  # llm, semantic, or hybrid
})

# Get alternative tools when one fails
call_tool(server_name="gobby", tool_name="get_tool_alternatives", arguments={
    "server_name": "supabase",
    "tool_name": "run_query",
    "error_message": "Connection refused"
})
```

### CLI Commands

```bash
# Refresh tool embeddings (detect schema changes)
gobby mcp-proxy refresh

# Force full refresh (regenerate all embeddings)
gobby mcp-proxy refresh --force

# Refresh only a specific server
gobby mcp-proxy refresh --server context7
```

### Configuration

```yaml
# ~/.gobby/config.yaml
mcp_client_proxy:
  search_mode: llm           # Default: llm, semantic, or hybrid
  embedding_model: text-embedding-3-small
  min_similarity: 0.3        # Threshold for semantic search
  top_k: 10                  # Default number of results
  refresh_on_server_add: true
  refresh_timeout: 300.0
```

## Tool Metrics

The daemon tracks call metrics for all MCP tools, useful for monitoring and debugging:

### Metrics Tracked

| Metric | Description |
|--------|-------------|
| `call_count` | Total number of calls to the tool |
| `success_count` | Number of successful calls |
| `failure_count` | Number of failed calls |
| `success_rate` | Ratio of successes to total calls (0.0-1.0) |
| `avg_latency_ms` | Average response time in milliseconds |
| `last_called_at` | Timestamp of most recent call |

### Database Tables

- `tool_metrics` - Real-time metrics per tool (retained 7 days by default)
- `tool_metrics_daily` - Aggregated historical data for long-term analysis

### Interpreting Metrics

- **Low success_rate** (< 0.5) - Tool may be misconfigured or server unreliable
- **High avg_latency_ms** (> 5000) - Consider increasing timeouts
- **call_count = 0** - Tool hasn't been used; may need discovery via recommend_tools

### Cleanup

Metrics older than 7 days are automatically aggregated to `tool_metrics_daily` and then deleted from `tool_metrics` to keep the main table lean.

## Tool Fallback Resolver

When a tool call fails, the fallback resolver suggests alternative tools:

### How It Works

1. Takes the failed tool name and error message
2. Uses semantic search to find similar tools
3. Weights results by similarity and historical success rate
4. Returns ranked alternatives with scores

### MCP Tool

```python
# Get alternatives after a tool failure
result = call_tool(server_name="gobby", tool_name="get_tool_alternatives", arguments={
    "server_name": "context7",
    "tool_name": "get_library_docs",
    "error_message": "Timeout exceeded",
    "top_k": 3
})
# Returns: {"alternatives": [{"server_name": "...", "tool_name": "...", "score": 0.85}, ...]}
```

### Scoring Algorithm

```
score = (similarity * 0.7) + (success_rate * 0.3)
```

- `similarity` - Semantic similarity to the failed tool (0.0-1.0)
- `success_rate` - Historical success rate of the alternative (0.0-1.0, default 0.5 if unknown)

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

Use the `gobby-tasks` MCP tools for persistent task tracking (requires daemon running).

### IMPORTANT: Workflow Requirement

Before editing files (Edit/Write tools), you MUST have an active task with `status: in_progress`. The workflow hook blocks file modifications when no task is active. Always create and start a task first:

```python
# Create a task
call_tool(server_name="gobby-tasks", tool_name="create_task", arguments={"title": "My task"})
# Returns: {"id": "gt-abc123"}

# Set it to in_progress before editing files
call_tool(server_name="gobby-tasks", tool_name="update_task", arguments={"task_id": "gt-abc123", "status": "in_progress"})
```

**Task Workflow:**

1. **Start of session**: Call `list_ready_tasks` or `suggest_next_task` to find work
2. **New requests**: Create tasks with `create_task(title="...", description="...")`
3. **Complex work**: Use `expand_task` to break into subtasks with AI, or use `parent_task_id` manually
4. **Track progress**: Use `update_task` to change status (`open` -> `in_progress` -> `closed`)
5. **Complete work**: After finishing a task:
   - Commit changes with `[task-id]` in the commit message (e.g., `[gt-abc123] feat: add feature`)
   - Close the task with `close_task(task_id="...", commit_sha="...")`
   - Never leave completed work uncommitted or tasks unclosed

**IMPORTANT - Closing Tasks with Code Changes:**
- When closing a task that involved code changes, ALWAYS commit first, then close with `commit_sha`
- If `close_task` returns an error about missing commits, commit the changes - do NOT use `no_commit_needed=true` to bypass
- The `no_commit_needed=true` option is ONLY for tasks that genuinely have no code changes (e.g., documentation review, research, planning)
- NEVER fabricate an `override_justification` - if you're uncertain whether to commit, ask the user
- When user says "close the task", this means: commit any code changes first, then close with the commit SHA

**Task Tools:**

| Tool | Description |
|------|-------------|
| `create_task` | Create a new task with title, priority, task_type, labels |
| `get_task` | Get task details including dependencies |
| `update_task` | Update task fields (status, priority, assignee, etc.) |
| `close_task` | Close a task. Requires linked commits (pass `commit_sha` inline, or `no_commit_needed=true` for non-code tasks) |
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
| `link_commit` | Link a git commit to a task |
| `unlink_commit` | Remove a commit link from a task |
| `auto_link_commits` | Auto-detect and link commits mentioning task ID |
| `get_task_diff` | Get combined diff for all commits linked to a task |

### Tool Signatures (gobby-tasks)

**IMPORTANT:** Always use `get_tool_schema` if uncertain about parameter names.

```python
# create_task - Create a new task
create_task(
    title: str,                    # Required
    description: str = None,
    priority: int = 2,             # 1=High, 2=Medium, 3=Low
    task_type: str = "task",       # task, bug, feature, epic (NOT "type")
    parent_task_id: str = None,
    blocks: list[str] = None,      # Task IDs this task blocks
    labels: list[str] = None,
    test_strategy: str = None,
    validation_criteria: str = None,
    session_id: str = None,
)

# get_task - Get task details
get_task(task_id: str)             # Required

# update_task - Update task fields
update_task(
    task_id: str,                  # Required
    title: str = None,
    description: str = None,
    status: str = None,            # open, in_progress, closed
    priority: int = None,
    assignee: str = None,
    labels: list[str] = None,
    validation_criteria: str = None,
    parent_task_id: str = None,
    test_strategy: str = None,
    workflow_name: str = None,
    verification: str = None,
    sequence_order: int = None,
)

# close_task - Close a task
close_task(
    task_id: str,                  # Required
    reason: str = "completed",     # completed, duplicate, already_implemented, wont_fix, obsolete
    changes_summary: str = None,   # Triggers LLM validation if provided
    skip_validation: bool = False,
    session_id: str = None,
    override_justification: str = None,  # Required when no_commit_needed=True
    no_commit_needed: bool = False,      # Only for non-code tasks
    commit_sha: str = None,        # Commit + close in one call
)

# list_tasks - List tasks with filters
list_tasks(
    status: str = None,
    priority: int = None,
    task_type: str = None,         # NOT "type"
    assignee: str = None,
    label: str = None,             # Single label filter (NOT "labels")
    parent_task_id: str = None,
    title_like: str = None,        # Fuzzy match
    limit: int = 50,
    all_projects: bool = False,
)

# list_ready_tasks - List tasks with no blockers
list_ready_tasks(
    priority: int = None,
    task_type: str = None,
    assignee: str = None,
    parent_task_id: str = None,
    limit: int = 10,
    all_projects: bool = False,
)

# add_dependency - Create dependency between tasks
add_dependency(
    task_id: str,                  # The dependent task (B)
    depends_on: str,               # The blocker task (A)
    dep_type: str = "blocks",
)

# add_label - Add a label to a task
add_label(
    task_id: str,                  # Required
    label: str,                    # Required (NOT "labels")
)

# link_commit - Link a commit to a task
link_commit(
    task_id: str,                  # Required
    commit_sha: str,               # Required
)

# expand_task - AI-powered task expansion
expand_task(
    task_id: str,                  # Required
    context: str = None,
    enable_web_research: bool = False,
    enable_code_context: bool = True,
)

# validate_task - AI-powered validation
validate_task(
    task_id: str,                  # Required
    changes_summary: str = None,
    context_files: str = None,
)

# suggest_next_task - AI-powered task suggestion
suggest_next_task(
    task_type: str = None,
    prefer_subtasks: bool = None,
)
```

### Tool Signatures (gobby-memory)

```python
# remember - Store a new memory
remember(
    content: str,                  # Required
    memory_type: str = None,       # fact, preference, pattern, context
    importance: str = None,        # 0.0-1.0 as string
    project_id: str = None,
    tags: str = None,              # Comma-separated
)

# recall - Retrieve memories
recall(
    query: str = None,
    project_id: str = None,
    limit: str = None,
    min_importance: str = None,
)
```

### Tool Signatures (gobby-skills)

```python
# create_skill - Create a skill directly
create_skill(
    name: str,                     # Required
    instructions: str,             # Required
    project_id: str = None,
    description: str = None,
    trigger_pattern: str = None,
    tags: str = None,              # Comma-separated
)

# apply_skill - Apply a skill
apply_skill(skill_id: str)         # Required
```

### Task Progressive Disclosure

List operations (`list_tasks`, `list_ready_tasks`, `list_blocked_tasks`) return **brief format** (8 fields) to minimize token usage:

```json
{"id", "title", "status", "priority", "type", "parent_task_id", "created_at", "updated_at"}
```

Use `get_task` to retrieve full task details (33 fields) including description, validation criteria, commits, etc.

```python
# Step 1: Discover tasks with brief format
tasks = call_tool(server_name="gobby-tasks", tool_name="list_ready_tasks", arguments={})
# Returns: {"tasks": [{"id": "gt-abc", "title": "...", "status": "open", ...}], "count": 5}

# Step 2: Get full details for a specific task
task = call_tool(server_name="gobby-tasks", tool_name="get_task", arguments={"task_id": "gt-abc"})
# Returns: full task with description, validation_criteria, commits, dependencies, etc.
```

```python
# Example MCP tool calls via daemon
call_tool(server_name="gobby-tasks", tool_name="list_ready_tasks", arguments={})
call_tool(server_name="gobby-tasks", tool_name="create_task", arguments={"title": "Fix auth bug"})
call_tool(server_name="gobby-tasks", tool_name="expand_task", arguments={"task_id": "gt-abc123"})
```

If tools fail, check daemon status: `uv run gobby status`

### Commit Linking

Link git commits to tasks for traceability and validation context. This enables:
- Validation against committed code (not just uncommitted changes)
- Audit trail of what was done for each task
- Context for validation even after changes are committed

**Auto-Linking Patterns:**

When committing, include the task ID in your commit message:
- `[gt-abc123]` - Task ID in brackets (recommended)
- `gt-abc123:` - Task ID with colon prefix
- `Implements gt-abc123` - Natural language reference

On session end, Gobby automatically scans new commits and links them to mentioned tasks.

**MCP Tools:**

```python
# Manually link a commit
call_tool(server_name="gobby-tasks", tool_name="link_commit", arguments={
    "task_id": "gt-abc123",
    "commit_sha": "abc1234"
})

# Auto-detect and link commits
call_tool(server_name="gobby-tasks", tool_name="auto_link_commits", arguments={
    "task_id": "gt-abc123",
    "since": "1 day ago"
})

# Get diff for validation
call_tool(server_name="gobby-tasks", tool_name="get_task_diff", arguments={
    "task_id": "gt-abc123",
    "include_uncommitted": true
})
```

**CLI Commands:**

```bash
# Link commits manually
gobby tasks commit link TASK_ID COMMIT_SHA
gobby tasks commit unlink TASK_ID COMMIT_SHA

# Auto-link from commit messages
gobby tasks commit auto TASK_ID [--since COMMIT]

# View linked commits
gobby tasks show TASK_ID --commits

# Get task diff (for validation)
gobby tasks diff TASK_ID [--no-uncommitted]
```

### Enhanced Validation

The validation system provides a robust QA loop with structured feedback, recurring issue detection, and escalation.

**Validation Features:**

- **Structured Issues**: Validation returns typed issues (acceptance_gap, test_failure, lint_error, type_error, security) with severity levels (blocker, major, minor)
- **Validation History**: All validation attempts are recorded with full context
- **Recurring Issue Detection**: Automatically detects when the same issues keep appearing
- **Escalation**: Tasks are escalated to human review after repeated failures
- **External Validator**: Optional separate agent validates with no prior context

**MCP Tools:**

| Tool | Description |
|------|-------------|
| `validate_task` | Run validation with optional max_iterations, external validator |
| `get_validation_history` | View all validation iterations for a task |
| `get_recurring_issues` | Analyze for issues appearing multiple times |
| `clear_validation_history` | Reset validation history after major changes |
| `de_escalate_task` | Return escalated task to open status |

```python
# Validate a task
call_tool(server_name="gobby-tasks", tool_name="validate_task", arguments={
    "task_id": "gt-abc123",
    "max_iterations": 3,
    "use_external_validator": True
})

# Check for recurring issues
call_tool(server_name="gobby-tasks", tool_name="get_recurring_issues", arguments={
    "task_id": "gt-abc123",
    "threshold": 2
})

# De-escalate after human fix
call_tool(server_name="gobby-tasks", tool_name="de_escalate_task", arguments={
    "task_id": "gt-abc123",
    "reason": "Fixed authentication issue manually",
    "reset_validation": True
})
```

**CLI Commands:**

```bash
# Validate with options
gobby tasks validate TASK_ID --max-iterations 3 --external --skip-build

# View validation history
gobby tasks validate TASK_ID --history
gobby tasks validation-history TASK_ID --json

# Check recurring issues
gobby tasks validate TASK_ID --recurring

# Clear history after major changes
gobby tasks validation-history TASK_ID --clear

# De-escalate a task
gobby tasks de-escalate TASK_ID --reason "Fixed manually"

# List escalated tasks
gobby tasks list --status escalated
```

**Configuration** (`~/.gobby/config.yaml`):

```yaml
gobby_tasks:
  validation:
    enabled: true
    provider: "claude"
    model: "claude-sonnet-4-20250514"
    max_iterations: 10
    recurring_issue_threshold: 3
    run_build_first: true
    build_command: "npm test"  # Or auto-detected
    use_external_validator: false
    external_validator_model: "claude-sonnet-4-20250514"
```

**Escalation Flow:**

1. Task fails validation repeatedly (same issues)
2. Gobby detects recurring issues and escalates
3. Task status changes to `escalated` with reason
4. Human reviews and fixes the issue
5. Use `de-escalate` to return task to `open` status

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

Gobby includes a workflow engine that enforces structured AI agent behavior through steps and tool restrictions.

### Workflow Types

**Lifecycle Workflows** - Event-driven, respond to session events (e.g., `session-handoff` for context handoff). Multiple can run simultaneously.

**Step-Based Workflows** - State machines with tool restrictions and transitions (e.g., `plan-execute`, `plan-act-reflect`). Only one active per session.

### Key Concepts

- **Steps**: Named states with allowed/blocked tools
- **Transitions**: Automatic step changes based on conditions
- **Exit Conditions**: Requirements to leave a step (e.g., user approval, artifact exists)
- **Actions**: Operations executed on step enter/exit (inject context, capture artifacts, etc.)

### Quick Start

```bash
# List available workflows
uv run gobby workflow list

# Activate a workflow for current session
uv run gobby workflow set plan-execute

# Check workflow status
uv run gobby workflow status

# Manual step override (escape hatch)
uv run gobby workflow step <step-name> --force
```

### Workflow YAML Schema

```yaml
name: my-workflow
type: stepped            # or "lifecycle"
extends: base-workflow   # Optional inheritance

steps:
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
    - action: enter_step
      step: plan
```

### Built-in Templates

| Template | Type | Description |
|----------|------|-------------|
| `session-handoff` | lifecycle | Session summary and context handoff (default) |
| `plan-execute` | stepped | Planning with tool restrictions, then execution |
| `react` | stepped | Reason-Act-Observe loop |
| `plan-act-reflect` | stepped | Periodic reflection checkpoints |
| `plan-to-tasks` | stepped | Decompose plan into tasks, execute with verification |
| `test-driven` | stepped | TDD: write-test -> implement -> refactor |

### Tool Filtering

When a step-based workflow is active, `list_tools()` returns only tools allowed in the current step. Blocked tools are hidden (not grayed out).

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

## Hook Extensions

Gobby supports extensible hook handling through plugins, webhooks, and WebSocket broadcasting.

### Supported Hook Event Types

| Event | Description |
|-------|-------------|
| `session_start` | Fired when a new session starts |
| `session_end` | Fired when a session ends |
| `before_agent` | Fired before agent turn starts |
| `after_agent` | Fired after agent turn completes |
| `stop` | Fired when agent attempts to stop (can block) |
| `before_tool` | Fired before a tool is executed (can block) |
| `after_tool` | Fired after a tool completes |
| `before_tool_selection` | Fired before tool selection (Gemini) |
| `before_model` | Fired before model call (Gemini) |
| `after_model` | Fired after model call (Gemini) |
| `pre_compact` | Fired before session context is compacted |
| `notification` | Notification event from CLI |

### Python Plugins

Plugins are Python modules that can handle hook events with custom logic.

**Plugin Locations:**

- `~/.gobby/plugins/` - Global plugins
- `.gobby/plugins/` - Project-specific plugins

**Example Plugin:**

```python
# ~/.gobby/plugins/my_plugin.py
from gobby.hooks.plugins import GobbyPlugin, hook_handler
from gobby.hooks.events import HookEventType

class MyPlugin(GobbyPlugin):
    name = "my-plugin"
    version = "1.0.0"
    description = "Custom hook handlers"

    @hook_handler(HookEventType.SESSION_START)
    def on_session_start(self, event):
        print(f"Session started: {event.data.get('session_id')}")
        return {"continue": True}

    @hook_handler(HookEventType.BEFORE_TOOL, priority=10)
    def on_before_tool(self, event):
        tool_name = event.data.get("tool_name")
        # Return continue=False to block the tool
        return {"continue": True}
```

**CLI Commands:**

```bash
# List loaded plugins
gobby plugins list

# Reload a plugin (hot-reload during development)
gobby plugins reload my-plugin
```

### Webhooks

HTTP webhooks dispatch hook events to external services.

**Configuration** (`~/.gobby/config.yaml`):

```yaml
hook_extensions:
  webhooks:
    enabled: true
    timeout: 10.0
    async_dispatch: true  # Non-blocking except for can_block endpoints
    endpoints:
      - name: slack-notifier
        url: https://hooks.slack.com/services/xxx
        events: [session_start, session_end]
        enabled: true
      - name: audit-logger
        url: https://audit.example.com/hook
        events: [before_tool, after_tool]
        can_block: true  # Can block tool execution
        headers:
          Authorization: "Bearer ${AUDIT_TOKEN}"
```

**CLI Commands:**

```bash
# List configured webhooks
gobby webhooks list

# Test a webhook endpoint
gobby webhooks test slack-notifier --event notification
```

### WebSocket Broadcasting

Real-time event broadcasting to connected WebSocket clients.

**Configuration** (`~/.gobby/config.yaml`):

```yaml
hook_extensions:
  websocket:
    enabled: true
    broadcast_events:
      - session-start
      - session-end
      - pre-tool-use
      - post-tool-use
    include_payload: true
```

**WebSocket Event Schema:**

```json
{
  "type": "hook_event",
  "event_type": "session_start",
  "timestamp": "2025-01-04T12:00:00Z",
  "data": {
    "session_id": "sess-abc123",
    "source": "claude",
    "project_id": "proj-xyz"
  }
}
```

**Connect to WebSocket:**

```python
import websockets
import json

async def listen_events():
    async with websockets.connect("ws://localhost:7778") as ws:
        # Subscribe to specific events (optional)
        await ws.send(json.dumps({
            "type": "subscribe",
            "events": ["session_start", "before_tool"]
        }))

        async for message in ws:
            event = json.loads(message)
            print(f"Received: {event['event_type']}")
```

### MCP Tools

Hook extension tools available via the gobby MCP server:

```python
# List registered hook handlers from plugins
call_tool(server_name="gobby", tool_name="list_hook_handlers", arguments={})

# Test a hook event
call_tool(server_name="gobby", tool_name="test_hook_event", arguments={
    "event_type": "session_start",
    "source": "claude",
    "data": {"session_id": "test-123"}
})

# List loaded plugins
call_tool(server_name="gobby", tool_name="list_plugins", arguments={})

# Reload a plugin
call_tool(server_name="gobby", tool_name="reload_plugin", arguments={
    "name": "my-plugin"
})
```

### Full Configuration Reference

```yaml
hook_extensions:
  # WebSocket broadcasting
  websocket:
    enabled: true
    broadcast_events: [session-start, session-end, pre-tool-use, post-tool-use]
    include_payload: true

  # HTTP webhooks
  webhooks:
    enabled: true
    timeout: 10.0
    async_dispatch: true
    endpoints: []

  # Python plugins
  plugins:
    enabled: false  # Disabled by default for security
    plugin_dirs:
      - ~/.gobby/plugins
      - .gobby/plugins
    auto_discover: true
    plugins: {}  # Per-plugin config by name
```

### Monitoring

Plugin status is included in `/admin/status`:

```json
{
  "plugins": {
    "enabled": true,
    "loaded": 2,
    "handlers": 5,
    "plugins": [
      {"name": "my-plugin", "version": "1.0.0", "handlers": 3, "actions": 1}
    ]
  }
}
```

## Testing

Tests use pytest with asyncio support. Key test configuration in `pyproject.toml`:

- `asyncio_mode = "auto"` - Automatic async test detection
- Coverage threshold: 80%
- Markers: `slow`, `integration`, `e2e`
