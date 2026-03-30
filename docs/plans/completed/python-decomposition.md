# Monolith Decomposition

## Overview

Decompose 12+ Python files exceeding the 1000-line guideline into smaller, focused modules. Serialized by blast radius — lowest-coupling files first, highest last. Each decomposition is one PR, independently reviewable and revertible.

## Constraints

- Re-export from old paths to avoid breaking importers. Remove re-exports in follow-up.
- One monolith per task. No multi-file decompositions in a single task.
- Targeted tests per decomposition — do NOT run the full 11,000+ test suite.
- Keep existing CLI flat-module pattern (`cli/agents.py`, `cli/sessions.py`). No `commands/` subpackage.
- `runner.py` extracts must NOT use the name `bootstrap.py` (conflicts with `config/bootstrap.py`).

## Phase 1: Migration Squash

**Goal**: Shrink migrations.py by squashing v134-v169 into BASELINE_SCHEMA

### 1.1 Squash migrations v134-v169 into baseline [category: code]

Target: `src/gobby/storage/migrations.py` (1,645 lines)

Squash the MIGRATIONS list entries for v134-v169 into BASELINE_SCHEMA:
- Apply all ALTER TABLE ADD COLUMN from v134-v169 to the baseline CREATE TABLE statements
- Apply all CREATE TABLE from v134-v169 to the baseline
- Apply all INSERT seed data from v134-v169 to the baseline
- Update `BASELINE_VERSION` to 169
- Update `_MIN_MIGRATION_VERSION` to 169
- Delete all `_migrate_v*` helper functions for v134-v169
- Keep the migration framework (`run_migrations`, `MigrationAction`, callable migrations pattern) intact for future v170+ migrations
- Remember: BASELINE_SCHEMA splits on `;` — triggers with BEGIN...END blocks must use callable migrations with `executescript()`

Tests: `uv run pytest tests/storage/db_migrations/ tests/storage/test_migrations.py -v`

## Phase 2: Low-Coupling Decompositions

**Goal**: Decompose files with 2 or fewer importers

### 2.1 Decompose workflows/rule_engine.py into engine/ package [category: refactor]

Target: `src/gobby/workflows/rule_engine.py` (1,271 lines, 2 lazy importers)

Split into a package:
- `engine/__init__.py` — re-exports `RuleEngine` (preserves import path)
- `engine/core.py` — `RuleEngine` class (orchestrator, `evaluate` method, stop counting, consecutive block tracking)
- `engine/effects.py` — `_apply_effect` and all effect handling (block, set_variable, inject_context, mcp_call)
- `engine/templating.py` — `_build_eval_context`, Jinja2 rendering, `SafeExpressionEvaluator` integration
- `engine/enforcement.py` — agent/step tool enforcement logic

Keep `rule_engine.py` as a thin re-export shim:

```python
from gobby.workflows.engine.core import RuleEngine
__all__ = ["RuleEngine"]
```

Tests: `uv run pytest tests/workflows/test_rule_engine*.py tests/workflows/test_enforcement*.py -v`

### 2.2 Split workflows/sync.py into per-type modules [category: refactor]

Target: `src/gobby/workflows/sync.py` (1,082 lines)

Split by sync target:
- `sync_pipelines.py` — `sync_bundled_pipelines()` and pipeline-specific helpers
- `sync_rules.py` — `sync_bundled_rules()` and rule-specific helpers
- `sync_variables.py` — `sync_bundled_variables()` and variable-specific helpers
- `sync.py` — becomes thin re-export shim importing from the three modules

Do NOT create a `sync_utils.py` — there's no demonstrated shared logic between the three sync types.

Tests: `uv run pytest tests/workflows/test_sync*.py -v`

## Phase 3: Medium-Coupling Decompositions

**Goal**: Decompose files with moderate importer counts

### 3.1 Decompose servers/routes/sessions.py into package [category: refactor] (depends: Phase 2)

Target: `src/gobby/servers/routes/sessions.py` (1,329 lines)

Convert to package:
- `sessions/__init__.py` — re-exports `create_sessions_router`
- `sessions/core.py` — CRUD routes (create, get, list, update, delete)
- `sessions/messages.py` — chat history and message routes
- `sessions/analytics.py` — stats, analytics, and reporting routes

Tests: `uv run pytest tests/servers/test_session_routes*.py -v`

### 3.2 Extract servers/http.py into focused modules [category: refactor] (depends: Phase 2)

Target: `src/gobby/servers/http.py` (1,135 lines)

Extract:
- `servers/app_factory.py` — `_create_app()` function, middleware registration, route mounting
- `servers/exception_handlers.py` — all exception handler registrations
- `http.py` retains `HTTPServer` class with server lifecycle (start/stop/bind) and the `ServiceContainer` wiring

Tests: `uv run pytest tests/servers/test_http*.py -v`

### 3.3 Split hooks/event_handlers/_session.py [category: refactor] (depends: Phase 2)

Target: `src/gobby/hooks/event_handlers/_session.py` (1,262 lines)

Split by event type:
- `_session_start.py` — `handle_session_start` and related helpers (~394 lines)
- `_session_end.py` — session end handling and cleanup
- `_session_responses.py` — response processing, context injection, variable management
- `_session.py` — re-export shim that imports from the three modules

Tests: `uv run pytest tests/hooks/test_session*.py tests/hooks/test_event*.py -v`

### 3.4 Decompose servers/websocket/session_control.py via command pattern [category: refactor] (depends: Phase 2)

Target: `src/gobby/servers/websocket/session_control.py` (1,147 lines)

Apply command pattern:
- `websocket/handlers/` directory with one module per handler (continue_in_chat, attach_session, view_session, etc.)
- Each handler module exports a single async function
- `session_control.py` becomes a thin router dispatching to handler modules based on message type

Tests: `uv run pytest tests/servers/test_websocket*.py -v`

## Phase 4: High-Coupling Decompositions

**Goal**: Carefully decompose files with many importers by extracting internals only

### 4.1 Extract hook_manager.py dispatchers [category: refactor] (depends: Phase 3)

Target: `src/gobby/hooks/hook_manager.py` (1,125 lines, **11 importers**)

Extract internal methods only — `HookManager` class stays in `hook_manager.py`:
- `hooks/dispatchers/webhook.py` — webhook evaluation and dispatch (`_evaluate_blocking_webhooks`, `_dispatch_webhook`)
- `hooks/dispatchers/mcp.py` — MCP call routing (`_dispatch_mcp_calls`, `_format_discovery_result`)
- `hook_manager.py` retains `HookManager` as coordinator, delegates to dispatchers

**Critical**: Zero import changes needed for the 11 importers. They all import `HookManager` from `hook_manager.py` — that stays put.

Tests: `uv run pytest tests/hooks/ -v`

### 4.2 Extract runner.py internals [category: refactor] (depends: Phase 3)

Target: `src/gobby/runner.py` (1,409 lines, 13 importers)

Extract internal logic — `GobbyRunner` class stays in `runner.py`:
- `runner_init.py` — initialization logic (component wiring, dependency injection, service container setup)
- `runner_lifecycle.py` — `run()` method internals (event loop setup, signal handling, shutdown sequence)
- `runner.py` retains `GobbyRunner` class, delegates to extracted modules

**NOT** `bootstrap.py` — that name conflicts with `config/bootstrap.py`.

**Critical**: Zero import changes for 13 importers. They all import `GobbyRunner` from `runner.py`.

Tests: `uv run pytest tests/test_runner*.py tests/test_daemon*.py -v`

## Phase 5: MCP Tool Registries

**Goal**: Convert large tool registration files to packages

### 5.1 Convert mcp_proxy/tools/skills to package [category: refactor] (depends: Phase 4)

Target: `src/gobby/mcp_proxy/tools/skills/__init__.py`

Convert to package:
- `__init__.py` re-exports the registry builder function
- Extract each tool handler into its own file (one function per file)
- Registry builder imports and assembles all handlers

### 5.2 Convert mcp_proxy/tools/worktrees.py to package [category: refactor] (depends: Phase 4)

Target: `src/gobby/mcp_proxy/tools/worktrees.py`

Same pattern as 5.1 — package with per-handler files and registry builder.

### 5.3 Convert mcp_proxy/tools/tasks/_lifecycle.py to submodules [category: refactor] (depends: Phase 4)

Target: `src/gobby/mcp_proxy/tools/tasks/_lifecycle.py`

Same pattern — split lifecycle handlers into focused submodules.

Tests for all 5.x: `uv run pytest tests/mcp_proxy/ -v`

## Phase 6: Remaining Files

**Goal**: Complete the decomposition of remaining oversized files

### 6.1 Split storage/skills/_manager.py [category: refactor] (depends: Phase 5)

Target: `src/gobby/storage/skills/_manager.py` (1,035 lines)

Split `LocalSkillManager` into focused modules:
- `_metadata.py` — skill metadata CRUD (create, get, list, update, delete)
- `_files.py` — file I/O operations (read skill files, write skill files, path resolution)
- `_templates.py` — template management (sync templates, install templates, list templates)
- `_manager.py` re-exports or composes from the three modules

### 6.2 Slim down cli/install.py [category: refactor] (depends: Phase 5)

Target: `src/gobby/cli/install.py` (1,054 lines)

Extract helpers — keep `install` and `uninstall` Click commands in `install.py`:
- `cli/_detectors.py` — CLI detector functions (`_is_cursor_installed`, `_is_windsurf_installed`, etc.)
- `cli/_install_prompts.py` — interactive prompt/UI flow helpers

Keep flat module pattern — no `commands/` subpackage.

Tests: `uv run pytest tests/cli/test_install*.py -v`

## Task Mapping

<!-- Updated after task creation -->
| Plan Item | Task Ref | Status |
|-----------|----------|--------|
