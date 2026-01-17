# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Gobby is a local-first daemon that unifies AI coding assistants (Claude Code, Gemini CLI, Codex) under one persistent, extensible platform. It provides:

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

# Testing (full suite runs pre-push - only run specific tests)
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
│   ├── __init__.py        # Main CLI group
│   ├── daemon.py          # start, stop, restart, status
│   ├── tasks/             # Task management commands
│   ├── sessions.py        # Session management
│   ├── workflows.py       # Workflow management
│   ├── mcp_proxy.py       # MCP server management
│   └── ...                # agents, worktrees, memory, etc.
│
├── runner.py              # Main daemon entry point (GobbyRunner)
│
├── servers/               # HTTP and WebSocket servers
│   ├── http.py           # FastAPI HTTP server (hooks, status)
│   └── websocket.py      # WebSocket server (real-time events)
│
├── mcp_proxy/            # MCP proxy layer
│   ├── server.py         # FastMCP server implementation
│   ├── manager.py        # MCPClientManager (connection pooling)
│   ├── tools/            # 20+ tool modules (sessions, tasks, agents, etc.)
│   └── transports/       # HTTP, stdio, WebSocket transports
│
├── hooks/                # Hook event system
│   ├── hook_manager.py   # Central coordinator
│   ├── events.py         # HookEvent, HookResponse models
│   └── hook_types.py     # Hook type enums
│
├── adapters/             # CLI-specific hook adapters
│   ├── claude_code.py    # Claude Code adapter
│   ├── gemini.py         # Gemini CLI adapter
│   └── codex.py          # Codex adapter + AppServerClient
│
├── sessions/             # Session lifecycle
│   ├── lifecycle.py      # Background jobs (expiry, transcript processing)
│   ├── processor.py      # SessionMessageProcessor
│   ├── summary.py        # Summary generation
│   └── transcripts/      # Parsers for Claude/Gemini/Codex
│
├── tasks/                # Task system
│   ├── expansion.py      # TaskExpander (LLM-based decomposition)
│   ├── validation.py     # TaskValidator (criteria checking)
│   ├── commits.py        # Commit linking logic
│   └── prompts/          # LLM prompts for expansion
│
├── workflows/            # Workflow engine
│   ├── engine.py         # WorkflowEngine (state machine)
│   ├── loader.py         # YAML workflow loading
│   ├── actions.py        # Workflow action implementations
│   └── evaluator.py      # Condition evaluation
│
├── agents/               # Agent spawning
│   ├── runner.py         # AgentRunner
│   ├── spawners/         # terminal, embedded, headless spawners
│   └── context_builder.py # Context injection
│
├── worktrees/            # Git worktree management
│   ├── manager.py        # WorktreeManager
│   └── merge/            # Merge utilities
│
├── memory/               # Memory system
│   ├── manager.py        # MemoryManager
│   └── search/           # Search implementations (TF-IDF, semantic)
│
├── storage/              # SQLite storage layer
│   ├── database.py       # LocalDatabase (connection management)
│   ├── migrations.py     # Schema migrations
│   ├── sessions.py       # Session CRUD
│   ├── tasks.py          # Task CRUD
│   ├── mcp.py            # MCP server/tool storage
│   └── ...               # worktrees, artifacts, etc.
│
├── llm/                  # Multi-provider LLM abstraction
│   ├── service.py        # LLMService manager
│   ├── claude.py         # Claude provider
│   ├── gemini.py         # Gemini provider
│   ├── codex.py          # Codex/OpenAI provider
│   └── litellm.py        # LiteLLM fallback
│
├── config/               # Configuration
│   ├── app.py            # DaemonConfig (YAML config model)
│   └── mcp.py            # MCP server config
│
└── utils/                # Utilities
    ├── git.py            # Git operations
    ├── logging.py        # Log setup
    └── project_init.py   # Project initialization
```

### Data Flow

**Inbound (Hook Events)**:

```text
CLI Hook → HTTP POST → Adapter → HookManager → Service Layer → Storage
```

**Outbound (MCP Tools)**:

```text
MCP Tool Call → MCPClientManager → [Internal Registry OR Downstream Server] → Response
```

### Key File Locations

| Path | Purpose |
| :--- | :--- |
| `~/.gobby/config.yaml` | Daemon configuration |
| `~/.gobby/gobby-hub.db` | SQLite database (sessions, tasks, etc.) |
| `~/.gobby/logs/` | Log files |
| `~/.gobby/workflows/` | Global workflow definitions |
| `.gobby/project.json` | Project metadata |
| `.gobby/tasks.jsonl` | Task sync file (git-native) |
| `.gobby/workflows/` | Project-specific workflows |

## MCP Tool Discovery (Progressive Disclosure)

**IMPORTANT**: Gobby uses progressive disclosure to minimize token usage. Follow this pattern:

```python
# 1. Discover available servers
list_mcp_servers()
# Returns: Server names and connection status

# 2. List tools on a specific server (lightweight)
list_tools(server="gobby-tasks")
# Returns: ~200 tokens per server (names + brief descriptions)

# 3. Get full schema when you need to call a tool
get_tool_schema(server_name="gobby-tasks", tool_name="create_task")
# Returns: Full inputSchema with all parameters

# 4. Execute the tool
call_tool(server_name="gobby-tasks", tool_name="create_task", arguments={
    "title": "Fix authentication bug",
    "task_type": "bug",
    "session_id": "<your_session_id>"  # Required - from SessionStart context
})
```

**Never load all tool schemas upfront** - it wastes your context window.

### Internal MCP Servers

| Server            | Purpose               | Key Tools                                                        |
|-------------------|-----------------------|------------------------------------------------------------------|
| `gobby-tasks`     | Task management       | `create_task`, `expand_task`, `close_task`, `suggest_next_task`  |
| `gobby-sessions`  | Session handoff       | `pickup`, `get_handoff_context`, `list_sessions`                 |
| `gobby-memory`    | Persistent memory     | `remember`, `recall`, `forget`                                   |
| `gobby-workflows` | Workflow control      | `activate_workflow`, `set_variable`, `get_status`                |
| `gobby-agents`    | Agent spawning        | `start_agent`, `list_agents`, `cancel_agent`                     |
| `gobby-worktrees` | Git worktrees         | `create_worktree`, `spawn_agent_in_worktree`, `list_worktrees`   |
| `gobby-merge`     | AI merge resolution   | `merge_start`, `merge_resolve`, `merge_apply`                    |
| `gobby-hub`       | Cross-project queries | `list_all_projects`, `hub_stats`                                 |
| `gobby-metrics`   | Tool metrics          | `get_metrics`, `get_failing_tools`                               |

Use `list_mcp_servers()` to see connected servers, then `list_tools(server="...")` for tools.

## Task Management (CRITICAL)

### Workflow Requirements

**BEFORE editing files (Edit/Write tools), you MUST have a task with `status: in_progress`.**

The workflow system blocks file modifications without an active task. This ensures all changes are tracked.

```python
# 1. Create task
call_tool(server_name="gobby-tasks", tool_name="create_task", arguments={
    "title": "Fix user authentication bug",
    "description": "Users cannot log in after password reset",
    "task_type": "bug",  # task, bug, feature, epic
    "priority": 1,
    "session_id": "<your_session_id>"  # Required
})
# Returns: {"task_id": "abc123", ...}

# 2. Set to in_progress BEFORE editing
call_tool(server_name="gobby-tasks", tool_name="update_task", arguments={
    "task_id": "abc123",
    "status": "in_progress"
})

# 3. Now you can use Edit/Write tools

# 4. Commit with task ID in message
git commit -m "[abc123] fix: resolve auth bug after password reset"

# 5. Close task with commit SHA
call_tool(server_name="gobby-tasks", tool_name="close_task", arguments={
    "task_id": "abc123",
    "commit_sha": "a1b2c3d"
})
```

### Task Workflow

1. **Start of session**:
   - `suggest_next_task()` - Get recommended next task based on priorities and dependencies
   - `list_ready_tasks()` - List all tasks ready to work on

2. **Create new work**:
   - `create_task(title, description, task_type, priority, session_id)` - session_id required
   - Task types: `task`, `bug`, `feature`, `epic`

3. **Complex tasks** (multi-step work):
   - `expand_task(task_id)` - LLM-based decomposition into subtasks with auto-TDD sandwich pattern
   - TDD sandwich: ONE [TEST] task → your impl tasks → ONE [REFACTOR] task
   - Expansion creates subtasks with proper dependencies and test strategies

4. **Track progress**:
   - `update_task(task_id, status="in_progress")` - Mark task as active
   - `update_task(task_id, assignee="session-id")` - Claim a task

5. **Complete work**:
   - Commit changes with `[task-id]` prefix
   - `close_task(task_id, commit_sha="...")` - Mark task complete or route to review
   - Alternative: `close_task(task_id, no_commit_needed=true)` for non-code tasks (research, planning)

6. **Review status** (HITL - Human-in-the-Loop):
   - Tasks may enter `review` status instead of `closed` when:
     - Task has `requires_user_review=true`
     - Agent uses `override_justification` to bypass validation
   - User must explicitly close reviewed tasks (sets `accepted_by_user=true`)
   - `reopen_task()` works from both `closed` and `review` statuses

**Task lifecycle**: `open → in_progress → review → closed`

Note: Tasks in `review` with `requires_user_review=false` unblock dependents (treated as complete for dependency resolution).

### Task Expansion and TDD Mode

Gobby automatically creates test/implement pairs when `tdd_mode=true` (default):

```python
# Expands "Add user authentication" into:
# 1. [TEST] Write tests for user authentication
# 2. [IMPL] Implement user authentication (depends_on: #1)
# 3. [TEST] Write tests for session management
# 4. [IMPL] Implement session management (depends_on: #3)
```

**To disable TDD mode for a session**:

```python
call_tool(server_name="gobby-workflows", tool_name="set_variable", arguments={
    "name": "tdd_mode",
    "value": False
})
```

### Task Expansion Workflow

When working with complex tasks, use the expansion workflow:

```bash
# 1. Create or identify the task to expand
gobby tasks create "Implement user authentication"

# 2. Expand into subtasks (includes research, decomposition, and auto-TDD)
gobby tasks expand #N

# 3. For cascading expansion of entire task trees
gobby tasks expand #N --cascade
```

Or via MCP tool:

```python
call_tool(server_name="gobby-tasks", tool_name="expand_task", arguments={
    "task_id": "#42"
})
```

For structured planning from specs, use the `/gobby:spec` skill which guides you through requirements gathering, spec writing, and task creation.

### Commit Linking

Include task ID in commit messages for automatic linking:

**Recommended format**:

```text
[<task-id>] <type>: <description>

Examples:
[abc123] feat: add user authentication
[xyz789] fix: resolve password reset bug
[def456] refactor: extract auth logic to service
```

**Also supported**:

```text
<task-id>: <description>
```

**IMPORTANT**: Do NOT add the following trailers to commit messages:

- ~~`Generated with Claude Code`~~

Gobby automatically links commits to tasks - no additional trailers needed.

### Closing Tasks: Rules and Gotchas

**Rule 1**: Always commit BEFORE closing

```python
# ❌ WRONG - close_task will error
call_tool("gobby-tasks", "close_task", {"task_id": "abc"})

# ✅ CORRECT - commit first
git commit -m "[abc] feat: implement feature"
call_tool("gobby-tasks", "close_task", {"task_id": "abc", "commit_sha": "a1b2c3"})
```

**Rule 2**: Use `no_commit_needed=true` ONLY for non-code tasks

```python
# ✅ Valid use cases:
# - Research tasks
# - Planning documents
# - Architecture reviews
call_tool("gobby-tasks", "close_task", {"task_id": "abc", "no_commit_needed": true})
```

**Rule 3**: Never fabricate `override_justification`

```python
# ❌ WRONG - lying to the system
call_tool("gobby-tasks", "close_task", {
    "task_id": "abc",
    "override_justification": "This is fine"  # No it's not!
})

# ✅ CORRECT - if validation fails, fix the issues first
```

### Task Validation

Tasks with validation criteria must pass checks before closing:

```python
# Create task with validation criteria
call_tool("gobby-tasks", "create_task", {
    "title": "Add user authentication",
    "validation": {
        "criteria": "Tests pass, no linting errors, auth flow works end-to-end"
    },
    "session_id": "<your_session_id>"  # Required
})

# Later, when closing, validation runs automatically
# If validation fails, you'll get feedback and the task stays open
```

## Session Handoff

Gobby preserves context across sessions through the hook system:

### How It Works

1. **pre-compact hook** fires before `/compact` - extracts:
   - Git state (branch, uncommitted changes)
   - Recent tool calls and file modifications
   - TodoWrite state and in-progress tasks
   - Generates `compact_markdown` summary

2. **session-start hook** fires on session resume - injects:
   - `## Continuation Context` block with previous state
   - Task context if `session_task` was set
   - Memory injection if enabled

### Automatic Handoff (Claude Code/Gemini)

Context is automatically extracted and injected. Look for `## Continuation Context` blocks at session start - this is your previous session state.

### Manual Handoff (Codex or cross-CLI)

```python
# Resume most recent session
call_tool(server_name="gobby-sessions", tool_name="pickup", arguments={})

# Resume specific session
call_tool(server_name="gobby-sessions", tool_name="pickup", arguments={
    "session_id": "previous-session-id"
})
```

Use `/gobby-sessions` skill for more commands: `list`, `show`, `handoff`, `search`.

## Agent Spawning

Spawn subagents with context injection for parallel work:

```python
call_tool(server_name="gobby-agents", tool_name="start_agent", arguments={
    "prompt": "Implement OAuth login flow",
    "mode": "terminal",  # terminal, embedded, headless, in_process
    "workflow": "plan-execute",  # Optional workflow to enforce
    "session_context": "summary_markdown",  # Context to inject
    "parent_session_id": "current-session-id"
})
```

**Context sources** (`session_context`):

- `summary_markdown` - Session summary
- `compact_markdown` - Compacted context
- `transcript:N` - Last N messages from transcript
- `file:path` - File content

**Safety limits**:

- Max agent depth: 3 (configurable)
- Tools filtered per workflow step
- Agents inherit workflow restrictions

## Worktree Orchestration

Create isolated git worktrees for parallel development:

```python
# Create worktree + spawn agent in one call
call_tool(server_name="gobby-worktrees", tool_name="spawn_agent_in_worktree", arguments={
    "prompt": "Implement authentication system",
    "branch_name": "feature/auth",
    "task_id": "task-123",
    "mode": "terminal"
})
```

**Worktree lifecycle**:

- `active` - Currently being used
- `stale` - No activity for N hours
- `merged` - Branch merged to main
- `abandoned` - Explicitly abandoned

**Cleanup**:

```bash
uv run gobby worktrees cleanup  # Remove merged/abandoned worktrees
```

## Workflows

Workflows enforce behavior through state machines with tool restrictions:

### Available Workflows

```bash
uv run gobby workflows list       # List all workflows
uv run gobby workflows show NAME  # Show workflow details
uv run gobby workflows set NAME   # Activate workflow
uv run gobby workflows status     # Show current state
uv run gobby workflows clear      # Deactivate workflow
```

### Built-in Workflows

| Workflow | Type | Purpose |
| :--- | :--- | :--- |
| `session-handoff` | lifecycle | Auto-generates handoff context (always active) |
| `plan-execute` | step | Enforces planning phase before implementation |
| `test-driven` | step | TDD workflow (test → implement → refactor) |
| `plan-act-reflect` | step | Reflection loop after N actions |
| `auto-task` | step | Autonomous task execution until completion |

### Workflow Types

**Lifecycle workflows**: Event-driven, no step restrictions, multiple can run simultaneously
**Step-based workflows**: State machines with tool restrictions, only one active at a time

### Tool Filtering

When a step-based workflow is active, tools are filtered:

```yaml
# In workflow YAML:
steps:
  - name: plan
    allowed_tools: [Read, Glob, Grep, WebSearch]  # Only these tools visible
    blocked_tools: [Edit, Write, Bash]            # Explicitly blocked
```

`list_tools()` returns only allowed tools for the current step.

### Session Variables

Control session behavior via workflow variables:

```python
# Link session to task (blocks stopping until task complete)
call_tool(server_name="gobby-workflows", tool_name="set_variable", arguments={
    "name": "session_task",
    "value": "task-id"  # Or "*" for all ready tasks
})

# Change TDD mode for session
call_tool(server_name="gobby-workflows", tool_name="set_variable", arguments={
    "name": "tdd_mode",
    "value": False
})
```

**Key variables**:

- `session_task` - Task that must complete before stopping
- `tdd_mode` - Generate test/implement pairs (default: `true`)
- `require_task_before_edit` - Block Edit/Write without active task (default: `false`)

**Workflow conditions**:

- `task_tree_complete()` - True when session_task and all subtasks are complete
- `task_needs_user_review()` - True when session_task is in `review` with `requires_user_review=true`

### Auto-Task Workflow

The `auto-task` workflow enables autonomous task execution:

```bash
# 1. Create/claim a task
uv run gobby tasks claim <task-id>

# 2. Activate auto-task workflow with the task ID
uv run gobby workflows set auto-task --variable session_task=<task-id>

# 3. Agent works autonomously until task tree is complete
# 4. Workflow exits when all subtasks are closed
```

**Features**:

- Stays in `work` step until `task_tree_complete()`
- Blocks session stop if task incomplete
- Auto-suggests next subtask when current one done
- Terminal step when all work complete

## Memory System

Persistent memory across sessions:

```python
# Store a fact
call_tool(server_name="gobby-memory", tool_name="remember", arguments={
    "content": "The API uses JWT tokens with 1-hour expiration",
    "importance": 0.8  # 0.0-1.0
})

# Recall facts
call_tool(server_name="gobby-memory", tool_name="recall", arguments={
    "query": "authentication tokens",
    "limit": 5
})

# Forget a memory
call_tool(server_name="gobby-memory", tool_name="forget", arguments={
    "memory_id": "mem-123"
})
```

**Search modes**:

- TF-IDF (default)
- Semantic (requires embeddings)

## Hook System

Gobby intercepts CLI events through hooks (13 total):

| Hook | Description | Can Block? |
| :--- | :--- | :--- |
| `session-start` | Session begins (startup/resume/compact) | No |
| `session-end` | Session ends | No |
| `user-prompt-submit` | Before prompt submitted | Yes |
| `pre-tool-use` | Before tool execution | Yes |
| `post-tool-use` | After tool execution | No |
| `pre-compact` | Before context compaction | No |
| `stop` | Agent stop request | Yes |
| `subagent-start` | Subagent spawned | No |
| `subagent-stop` | Subagent stopped | No |
| `notification` | System notifications | No |
| `before-model` | Before inference (Gemini only) | No |
| `after-model` | After inference (Gemini only) | No |
| `permission-request` | Permission requested (Claude only) | Yes |

**Plugins**: Place custom plugins in:

- `~/.gobby/plugins/` (global)
- `.gobby/plugins/` (project-specific)

## Code Conventions

### Type Hints

All functions require type hints:

```python
def process_task(task_id: str, config: TaskConfig) -> Task:
    """Process a task with given configuration."""
    ...
```

### Error Handling

Use specific exceptions, not bare `except`:

```python
# ✅ Good
try:
    result = process_data()
except ValueError as e:
    logger.error(f"Invalid data: {e}")
    raise

# ❌ Bad
try:
    result = process_data()
except:
    pass
```

### Async/Await

Use async for I/O-bound operations:

```python
async def fetch_data(url: str) -> dict[str, Any]:
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        return response.json()
```

### SQLite Connections

Always use connection context manager:

```python
with self.db.transaction() as conn:
    conn.execute("INSERT INTO tasks VALUES (?, ?)", (task_id, title))
```

### Logging

Use structured logging with context:

```python
logger.info(f"Created task {task_id} in project {project_id}")
logger.error(f"Failed to expand task {task_id}: {error}", exc_info=True)
```

## Testing Patterns

### Test Structure

```python
def test_task_creation(task_manager: LocalTaskManager) -> None:
    """Test creating a task with required fields."""
    task = task_manager.create_task(
        title="Test task",
        task_type="task"
    )

    assert task.id is not None
    assert task.title == "Test task"
    assert task.status == "open"
```

### Fixtures

Use pytest fixtures from `tests/conftest.py`:

```python
def test_with_database(db: LocalDatabase) -> None:
    """Test using database fixture."""
    ...

def test_with_task_manager(task_manager: LocalTaskManager) -> None:
    """Test using task manager fixture."""
    ...
```

### Async Tests

Mark async tests with `pytest.mark.asyncio`:

```python
@pytest.mark.asyncio
async def test_async_operation() -> None:
    """Test async operation."""
    result = await async_function()
    assert result is not None
```

### Test Markers

Use markers to categorize tests:

```python
@pytest.mark.slow
def test_expensive_operation() -> None:
    """This test takes a long time."""
    ...

@pytest.mark.integration
def test_integration() -> None:
    """This test requires multiple components."""
    ...
```

## Common Patterns

### Task Creation → Expansion → Execution

```python
# 1. Create parent task
parent = call_tool("gobby-tasks", "create_task", {
    "title": "Implement user authentication",
    "task_type": "feature",
    "session_id": "<your_session_id>"  # Required
})

# 2. Expand into subtasks (auto-creates TDD pairs)
call_tool("gobby-tasks", "expand_task", {
    "task_id": parent["task_id"]
})

# 3. Get next task to work on
next_task = call_tool("gobby-tasks", "suggest_next_task", {})

# 4. Set to in_progress
call_tool("gobby-tasks", "update_task", {
    "task_id": next_task["task_id"],
    "status": "in_progress"
})

# 5. Do the work, commit, close
```

### Worktree-based Parallel Development

```python
# Spawn agent in isolated worktree for each subtask
for task in subtasks:
    call_tool("gobby-worktrees", "spawn_agent_in_worktree", {
        "prompt": f"Work on: {task['title']}",
        "branch_name": f"task/{task['id']}",
        "task_id": task["id"],
        "mode": "terminal"
    })
```

### Progressive MCP Discovery

```python
# 1. Discover available servers
list_mcp_servers()

# 2. List tools on a server (lightweight metadata)
list_tools(server="gobby-tasks")

# 3. Get full schema when needed
get_tool_schema(server_name="gobby-tasks", tool_name="create_task")

# 4. Execute
call_tool(server_name="gobby-tasks", tool_name="create_task", arguments={
    "title": "Fix bug",
    "task_type": "bug",
    "session_id": "<your_session_id>"  # Required
})
```

## Troubleshooting

### "Task has no commits" when closing

**Problem**: Calling `close_task` without committing first

**Solution**: Always commit before closing:

```bash
git add .
git commit -m "[task-id] feat: implement feature"
uv run gobby tasks close <task-id> --commit <sha>
```

### "Edit/Write blocked: No active task"

**Problem**: Trying to modify files without a task set to `in_progress`

**Solution**: Create or update a task first:

```python
call_tool("gobby-tasks", "update_task", {
    "task_id": "abc123",
    "status": "in_progress"
})
```

### Workflow stuck in a step

**Problem**: Can't transition to next step

**Solution**: Force transition or clear workflow:

```bash
uv run gobby workflows step <target-step> --force
uv run gobby workflows clear --force
```

### Agent depth exceeded

**Problem**: Too many nested agent spawns

**Solution**: Reduce nesting or increase limit in config:

```yaml
agents:
  max_depth: 5  # Default is 3
```

## Performance Considerations

- **MCP Proxy**: Use progressive disclosure - don't load all schemas upfront
- **Task Expansion**: Expansion can take 10-30s for complex tasks - be patient
- **Session Transcripts**: Large transcripts (>10k messages) slow session loading
- **SQLite**: Database is local-first - no network latency
- **Workflow State**: Minimal overhead - state checks are fast

## See Also

- `README.md` - Project overview and architecture diagram
- `CONTRIBUTING.md` - Contribution guidelines and PR process
- `docs/guides/workflows.md` - Complete workflow guide
- `docs/guides/mcp-tools.md` - Full MCP tool reference
- `docs/architecture/source-tree.md` - Detailed source tree
