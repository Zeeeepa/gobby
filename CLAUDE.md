# CLAUDE.md

This file provides guidance for developing the Gobby codebase.

**For using Gobby's tools**: Use progressive disclosure via `list_mcp_servers()` → `list_tools(server)` → `get_tool_schema()`. The MCP server includes instructions.

**For skills and workflows**: Use `list_skills()` to discover available skills, then `get_skill(name)` for details.

## Project Overview

Gobby is a local-first daemon that unifies AI coding assistants (Claude Code, Gemini CLI, Codex) under one persistent, extensible platform. It provides:

- **Session management** that survives restarts and context compactions
- **Task system** with dependency graphs, TDD expansion, and validation gates
- **MCP proxy** with progressive disclosure (tools stay lightweight until needed)
- **Workflow engine** that enforces steps, tool restrictions, and transitions
- **Worktree orchestration** for parallel development
- **Memory system** for persistent facts across sessions

## Development Commands

```bash
# Environment setup
uv sync                          # Install dependencies (Python 3.13+)

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
│   └── ...                # agents, worktrees, memory, etc.
│
├── runner.py              # Main daemon entry point (GobbyRunner)
│
├── servers/               # HTTP and WebSocket servers
│   ├── http.py           # FastAPI HTTP server
│   └── websocket.py      # WebSocket server (real-time events)
│
├── mcp_proxy/            # MCP proxy layer
│   ├── server.py         # FastMCP server implementation
│   ├── manager.py        # MCPClientManager (connection pooling)
│   ├── instructions.py   # MCP server instructions (progressive disclosure)
│   ├── tools/            # 20+ internal tool modules
│   └── transports/       # HTTP, stdio, WebSocket transports
│
├── hooks/                # Hook event system
│   ├── hook_manager.py   # Central coordinator
│   ├── events.py         # HookEvent, HookResponse models
│   └── skill_manager.py  # Skill discovery for hooks
│
├── adapters/             # CLI-specific hook adapters
│   ├── claude_code.py    # Claude Code adapter
│   ├── gemini.py         # Gemini CLI adapter
│   └── codex.py          # Codex adapter
│
├── sessions/             # Session lifecycle
│   ├── lifecycle.py      # Background jobs
│   ├── processor.py      # SessionMessageProcessor
│   └── transcripts/      # Parsers for Claude/Gemini/Codex
│
├── tasks/                # Task system
│   ├── expansion.py      # TaskExpander (LLM-based decomposition)
│   ├── validation.py     # TaskValidator
│   └── prompts/          # LLM prompts for expansion
│
├── workflows/            # Workflow engine
│   ├── engine.py         # WorkflowEngine (state machine)
│   ├── loader.py         # YAML workflow loading
│   └── actions.py        # Workflow action implementations
│
├── skills/               # Skill management
│   ├── loader.py         # SkillLoader (filesystem, GitHub, ZIP)
│   ├── parser.py         # SKILL.md parser
│   └── sync.py           # Bundled skill sync on startup
│
├── storage/              # SQLite storage layer
│   ├── database.py       # LocalDatabase (connection management)
│   ├── migrations.py     # Schema migrations
│   ├── sessions.py       # Session CRUD
│   ├── tasks.py          # Task CRUD
│   └── skills.py         # Skill storage
│
├── llm/                  # Multi-provider LLM abstraction
│   ├── service.py        # LLMService manager
│   ├── claude.py         # Claude provider
│   ├── gemini.py         # Gemini provider
│   └── litellm.py        # LiteLLM fallback
│
└── config/               # Configuration
    ├── app.py            # DaemonConfig (YAML config model)
    └── mcp.py            # MCP server config
```

### Key File Locations

| Path | Purpose |
|------|---------|
| `~/.gobby/config.yaml` | Daemon configuration |
| `~/.gobby/gobby-hub.db` | SQLite database |
| `~/.gobby/logs/` | Log files |
| `.gobby/project.json` | Project metadata |
| `.gobby/tasks.jsonl` | Task sync file (git-native) |

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
# Good
try:
    result = process_data()
except ValueError as e:
    logger.error(f"Invalid data: {e}")
    raise

# Bad
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

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| Import errors | Run `uv sync` |
| Test failures | Check fixtures in `tests/conftest.py` |
| Type errors | Run `uv run mypy src/` |
| Lint errors | Run `uv run ruff check src/ --fix` |
| Daemon not starting | Check logs in `~/.gobby/logs/` |
| MCP connection issues | Verify daemon is running: `gobby status` |

### Debugging Tips

- Enable verbose logging: `gobby start --verbose`
- Check daemon logs: `tail -f ~/.gobby/logs/gobby.log`
- Test MCP tools: Use `list_mcp_servers()` to verify connections

## See Also

- `README.md` - Project overview
- `CONTRIBUTING.md` - Contribution guidelines
- Use `list_skills()` for workflow and usage guides
