# Monolith Decomposition Plan — Review & Improved Approach

## Context

Gemini identified 12+ files exceeding the 1000-line guideline. All claims validated — every file is genuinely oversized. However, the proposed plan has structural problems that would make execution painful. This is my critique and a phased alternative.

## Critique of Gemini's Plan

### What's Good
- Correctly identifies real monoliths (all validated at 1000+ lines)
- Migration squash from v133→v169 baseline is sound
- Most decomposition targets are reasonable

### What's Wrong

1. **No prioritization or phasing.** 12+ files, 640 test files, 11,000+ tests. This needs to be serialized carefully, not presented as a flat list.

2. **Migration question is already answered.** The baseline is at v133, `_MIN_MIGRATION_VERSION = 133`. Squashing v134-v169 into the baseline isn't a breaking change — databases below v133 are *already* unsupported. There's no decision to make here.

3. **`runner.py` → `bootstrap.py` conflicts with existing `config/bootstrap.py`.** Gemini didn't check what already exists.

4. **`cli/install.py` → `cli/commands/` breaks existing CLI pattern.** The CLI is organized as flat modules (`cli/agents.py`, `cli/sessions.py`, etc.). Creating a `commands/` subpackage is inconsistent. Keep the flat pattern.

5. **No import migration strategy.** When you move `RuleEngine` from `workflows/rule_engine.py` to `workflows/engine/core.py`, every importer breaks. Need re-exports from old paths or a bulk-update pass. This is the #1 source of bugs in decompositions.

6. **Blast radius not considered.** `hook_manager.py` has 11 direct importers across 5 layers (CLI adapters, HTTP server, MCP proxy, hook factory, hook base). `rule_engine.py` has only 2 (both lazy). The plan treats them equally.

7. **`sync_utils.py` is premature abstraction.** There's no demonstrated shared logic between pipeline sync, rule sync, and variable sync. Three files is fine; four (with a utils file) is over-engineering.

8. **Verification plan is "run pytest".** With 11,000+ tests that take 30+ minutes, you need targeted test runs per decomposition, not "run the full suite."

---

## Improved Plan — Phased Execution

### Guiding Principles
- **One monolith per PR.** Each decomposition is independently reviewable and revertible.
- **Re-export from old paths.** Every moved class/function gets a re-export in the original module's `__init__.py` to avoid breaking importers. Remove re-exports in a follow-up.
- **Lowest blast radius first.** Start with files that have few importers.
- **Targeted tests.** Run only the tests relevant to each decomposition.

### Phase 1: Migration Squash (Low risk, self-contained)

**File:** `src/gobby/storage/migrations.py` (1,645 lines)

- Squash MIGRATIONS list (v134-v169) into BASELINE_SCHEMA
- Update `_MIN_MIGRATION_VERSION` to 169
- Delete all `_migrate_v*` helper functions for v134-v169
- Keep the migration framework (`run_migrations`, `MigrationAction`, etc.) intact for future v170+ migrations
- **No breaking change:** databases below v133 were already rejected

**Tests:** `uv run pytest tests/storage/db_migrations/ tests/storage/test_migrations.py -v`

### Phase 2: Low-Coupling Decompositions (2 importers or fewer)

#### 2a. `workflows/rule_engine.py` → `workflows/engine/` package (1,271 lines, 2 lazy importers)

- `engine/__init__.py` — re-exports `RuleEngine`
- `engine/core.py` — `RuleEngine` class (orchestrator, evaluate method)
- `engine/effects.py` — `_apply_effect` and effect handling
- `engine/templating.py` — `_build_eval_context`, jinja rendering
- `engine/enforcement.py` — agent/step tool enforcement

**Tests:** `uv run pytest tests/workflows/test_rule_engine*.py tests/workflows/test_enforcement*.py -v`

#### 2b. `workflows/sync.py` → 3 files (1,082 lines)

- `sync_pipelines.py` — `sync_bundled_pipelines()`
- `sync_rules.py` — `sync_bundled_rules()`
- `sync_variables.py` — `sync_bundled_variables()`
- `sync.py` — becomes thin re-export shim

**Tests:** `uv run pytest tests/workflows/test_sync*.py -v`

### Phase 3: Medium-Coupling Decompositions

#### 3a. `servers/routes/sessions.py` → `servers/routes/sessions/` package (1,329 lines)

- `sessions/__init__.py` — re-exports `create_sessions_router`
- `sessions/core.py` — CRUD routes
- `sessions/messages.py` — chat history routes
- `sessions/analytics.py` — stats/analytics routes

**Tests:** `uv run pytest tests/servers/test_session_routes*.py -v`

#### 3b. `servers/http.py` decomposition (1,135 lines)

- Extract `_create_app` into `servers/app_factory.py`
- Extract exception handlers into `servers/exception_handlers.py`
- `http.py` retains server lifecycle (start/stop/bind)

**Tests:** `uv run pytest tests/servers/test_http*.py -v`

#### 3c. `hooks/event_handlers/_session.py` → split (1,262 lines)

- `_session_start.py` — `handle_session_start` (394 lines)
- `_session_end.py` — session end handling
- `_session_responses.py` — response processing
- `_session.py` — re-export shim

**Tests:** `uv run pytest tests/hooks/test_session*.py tests/hooks/test_event*.py -v`

#### 3d. `servers/websocket/session_control.py` → command pattern (1,147 lines)

- `websocket/handlers/` directory with per-handler modules
- `session_control.py` — thin router dispatching to handler modules

**Tests:** `uv run pytest tests/servers/test_websocket*.py -v`

### Phase 4: High-Coupling Decompositions (careful)

#### 4a. `hooks/hook_manager.py` (1,125 lines, **11 importers** — highest blast radius)

- `hooks/dispatchers/webhook.py` — webhook evaluation and dispatch
- `hooks/dispatchers/mcp.py` — MCP call routing
- `hook_manager.py` — retains `HookManager` class as coordinator, delegates to dispatchers
- **Critical:** `HookManager` stays in `hook_manager.py`. Only internal methods move. Zero import changes needed for the 11 importers.

**Tests:** `uv run pytest tests/hooks/ -v`

#### 4b. `runner.py` (1,409 lines, 13 importers)

- `runner_init.py` — extract initialization logic (component wiring, dependency injection)
- `runner_lifecycle.py` — extract `run()` method internals (event loop, shutdown)
- `runner.py` — retains `GobbyRunner` class, delegates to extracted modules
- **NOT** `bootstrap.py` — that name conflicts with `config/bootstrap.py`
- **Critical:** `GobbyRunner` stays in `runner.py`. Zero import changes for 13 importers.

**Tests:** `uv run pytest tests/test_runner*.py tests/test_daemon*.py -v`

### Phase 5: MCP Tool Registries (mechanical, low risk)

#### 5a-c. Convert `skills/__init__.py`, `worktrees.py`, `tasks/_lifecycle.py` to packages

Each follows the same pattern:
- Convert to package with `__init__.py` re-exporting the registry builder
- Extract each tool handler into its own file
- Registry builder imports and assembles

**Tests:** `uv run pytest tests/mcp_proxy/ -v`

### Phase 6: Remaining Files

#### 6a. `storage/skills/_manager.py` (1,035 lines)

- Split `LocalSkillManager` into `_metadata.py`, `_files.py`, `_templates.py`
- `_manager.py` re-exports or composes

#### 6b. `cli/install.py` (1,054 lines)

- Extract detector functions (`_is_cursor_installed`, etc.) → `cli/_detectors.py`
- Extract prompt/UI flow → `cli/_install_prompts.py`
- Keep `install` and `uninstall` commands in `install.py` but thinner

**Tests:** `uv run pytest tests/cli/test_install*.py -v`

---

## Files Modified Per Phase

| Phase | Files Touched | New Files | Blast Radius |
|-------|--------------|-----------|-------------|
| 1 | 1 | 0 | None |
| 2a | 1 | 4 | 2 importers (lazy) |
| 2b | 1 | 3 | Internal only |
| 3a | 1 | 4 | Route registration |
| 3b | 1 | 2 | Server startup |
| 3c | 1 | 3 | Event handler registry |
| 3d | 1 | ~13 | WebSocket router |
| 4a | 1 | 2 | 0 (internal extract) |
| 4b | 1 | 2 | 0 (internal extract) |
| 5 | 3 | ~15 | MCP tool registry |
| 6 | 2 | ~5 | Internal only |

## Verification Strategy

- **Per-phase:** Run targeted test suite (listed above) + `uv run mypy src/gobby/` for type checking
- **After all phases:** Full `uv run pytest tests/ -v` (once, at the end)
- **Manual:** Start daemon, connect a CLI, verify MCP tool discovery works end-to-end
- **Migration-specific:** Write a test that creates a fresh DB and asserts `get_current_version() == 169`
