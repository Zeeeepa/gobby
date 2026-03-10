# Gobby – Copilot Instructions

## Project Overview

Gobby is a local-first daemon that unifies AI coding assistants (Claude Code, Gemini CLI, Codex, Cursor, Windsurf, Copilot) under one persistent platform. It exposes an HTTP API, a WebSocket server, and an MCP proxy that AI clients connect to as a tool server.

## Build, Test, and Lint

```bash
# Install / sync dependencies (Python 3.13+)
uv sync

# Lint and format
uv run ruff check src/
uv run ruff format src/

# Type check
uv run mypy src/

# Run a single test file
uv run pytest tests/storage/test_tasks.py -v

# Run a single test by name
uv run pytest tests/storage/test_tasks.py::test_create_task -v

# Run a module directory
uv run pytest tests/workflows/ -v

# Run with coverage (add to any test run)
uv run pytest tests/storage/ --cov=gobby --cov-report=term-missing

# Exclude slow tests
uv run pytest -m "not slow"

# Daemon management
uv run gobby start --verbose
uv run gobby stop
uv run gobby restart
uv run gobby status
```

**Do not run `uv run pytest` (full suite) without `-m "not slow"` or a specific path — the full suite has 11,000+ tests and takes 30+ minutes.**

Coverage threshold is 80% (enforced in CI and pre-push).

## Architecture

### Startup and Dependency Injection

`src/gobby/runner.py` bootstraps all services, wires them into a `ServiceContainer` (`app_context.py`), and calls `set_app_context()`. HTTP routes and other components retrieve services via `get_app_context()` — there is no constructor injection at the route level.

### Request Flow

1. An AI client (Claude Code, Gemini CLI, etc.) hits the **MCP proxy** (`mcp_proxy/server.py`) — a FastMCP server that exposes internal tools (tasks, sessions, memory, agents, etc.) and proxies to external MCP servers registered by the user.
2. The proxy uses **progressive discovery**: `list_mcp_servers → list_tools → get_tool_schema → call_tool`. Each step is a separate top-level tool. Never call one step through another.
3. AI client hook events (PreToolUse, PostToolUse, SessionStart, etc.) POST to `servers/http.py`, are dispatched through `hooks/hook_manager.py`, enriched by `hooks/event_enrichment.py`, and routed to event handlers in `hooks/event_handlers/`.
4. The **Rule Engine** (`workflows/rule_engine.py`) evaluates YAML-defined rules on every hook event. Rules can `block`, `set_variable`, `inject_context`, `mcp_call`, `observe`, `rewrite_input`, or `compress_output`.

### Storage Layer

- Single SQLite database at `~/.gobby/gobby-hub.db`.
- `storage/database.py` provides `LocalDatabase` (and a `DatabaseProtocol` interface for testing).
- Each domain (sessions, tasks, agents, workflows, etc.) has its own manager class in `storage/`.
- Use `with self.db.transaction() as conn:` for all writes.
- Schema is managed via `storage/migrations.py`. New columns go into both `MIGRATIONS` (incremental) and `BASELINE_SCHEMA` (for fresh installs). Current baseline version is tracked as `BASELINE_VERSION`.

### Workflow / Rule Engine

- Workflows and rules are YAML files **loaded into the `workflow_definitions` SQLite table** by `WorkflowLoader`. The DB is the source of truth for what's active, **not** the YAML files on disk.
- Templates in `src/gobby/install/shared/` have `enabled: false` by default — they must be installed and enabled to take effect.
- `workflows/safe_evaluator.py` provides a sandboxed AST-based evaluator for rule `when:` conditions.

### Adapters

Each supported AI CLI has an adapter in `adapters/` (e.g., `adapters/claude_code.py`, `adapters/copilot.py`) that normalises that CLI's hook payload format into the internal `HookEvent` / `HookResponse` models.

### Testing

- Fixtures are in `tests/conftest.py`. Key fixtures: `temp_db`, `session_manager`, `project_manager`, `task_manager`, `default_config`.
- An `autouse` fixture `protect_production_resources` redirects all DB and log paths to temp directories for every test. Opt out with `@pytest.mark.no_config_protection`.
- E2E tests (`tests/e2e/`) run last (sorted by `pytest_collection_modifyitems`).
- Async tests require `@pytest.mark.asyncio`.

## Key Conventions

### File Size Limit

Keep files under **1,000 lines**. Decompose larger files into submodules (see how `workflows/loader.py` splits into `loader_cache.py`, `loader_discovery.py`, `loader_sync.py`, `loader_validation.py`).

### Imports

- Use absolute imports (`from gobby.storage.tasks import ...`). Relative imports from parent packages (`from .. import`) are banned by ruff rule `TID252`.
- Use `from __future__ import annotations` at the top of files that use forward references.

### Type Hints

Strict mypy is enabled (`strict = true`). All functions require type hints. Use `TYPE_CHECKING` guards for imports only needed for type annotations.

### Datetime

Always use timezone-aware datetimes. Import `UTC` from `datetime` and use `datetime.now(UTC)` or `replace(tzinfo=UTC)`. SQLite adapters handle serialisation automatically (registered in `storage/database.py`).

### Ruff / Formatting

Line length is **100 characters**. Run `uv run ruff format src/` before committing. Ruff also enforces pyupgrade (`UP`) and flake8-bugbear (`B`) rules.

### Adding Database Migrations

1. Add a new entry to `MIGRATIONS` in `storage/migrations.py` with the next version number.
2. Also add the schema change to `BASELINE_SCHEMA` so fresh installs don't re-run it.
3. Bump `BASELINE_VERSION` to match.
