# Strangler Fig Decomposition Plan

## Overview

This document outlines the strategy for decomposing "God Objects" in the Gobby codebase using the **Strangler Fig** pattern. This pattern allows incremental migration from a monolithic system to a modular one without rewriting everything at once.

## Constraints

- No logic changes during structural refactoring
- Tests must pass before and after each slice
- Atomic commits per slice (one PR per slice, not one PR for all)
- Internal modules prioritize clean code over backward compatibility

---

## Core Strategy

For each candidate, follow these steps:

1. **Identify Seams**: Find logical groupings of functionality (by domain, feature, or resource)
2. **Create New Structure**: Establish a new package directory or sibling modules
3. **Route/Proxy**: Implement the first slice in the new module; update the original to import and delegate
4. **Iterate**: Repeat for each subsequent slice
5. **Withering**: Once the original is empty or purely re-exports, **delete it completely** and update all importers

---

## Execution Priority

| Priority | Candidate | Rationale |
|----------|-----------|-----------|
| 1 | `actions.py` | Already in progress, minimal remaining work (delete wrappers) |
| 2 | `migrations.py` | High-value cleanup, isolated domain, pending decision on legacy support |
| 3 | `tools.py` | Largest file, requires careful router mounting |
| 4 | `codex.py` | Adapter code, can be done whenever |

---

## Phase 1: Actions Withering

**Goal**: Complete the withering phase for `actions.py`

### Candidate: `src/gobby/workflows/actions.py` (1392 lines)

**Status**: In Progress (Partial Decomposition)
**Target**: < 400 lines (registry + imports only)

**Current State**: Significant logic extracted into sibling modules (`autonomous_actions.py`, `context_actions.py`, `state_actions.py`, etc.). `actions.py` now primarily serves as the `ActionExecutor` registry with `_handle_*` wrapper methods that delegate to new modules.

**Tasks:**

- [ ] Refactor `ActionExecutor.register_defaults` to register external callables directly (category: refactor)
- [ ] Delete `_handle_*` wrapper methods from `ActionExecutor` (category: refactor)
- [ ] Verify all action imports work correctly (category: manual)

**Acceptance Criteria:**

- `actions.py` contains only registry logic and imports
- All existing tests pass
- No `_handle_*` methods remain in the file
- Line count < 400

---

## Phase 2: Migration Flattening

**Goal**: Flatten legacy migrations into a single v75 baseline with feature-flagged rollback.

### Candidate: `src/gobby/storage/migrations.py` (1046 lines) & `migrations_legacy.py` (1359 lines)

**Status**: Planned
**Detailed Plan**: [migration-flattening.md](./migration-flattening.md)

The migration flattening follows its own strangler fig approach with 6 phases:
1. Schema capture (add BASELINE_SCHEMA_V2 at v75)
2. Feature flag (`use_flattened_baseline`)
3. Branching logic in `run_migrations()`
4. Testing & validation (both paths)
5. Default to new baseline
6. Cleanup (remove old path)

See the detailed plan for tasks, acceptance criteria, and rollback procedures at each phase.

---

## Phase 3: Tools Decomposition

**Goal**: Decompose into domain-specific routers

### Candidate: `src/gobby/servers/routes/mcp/tools.py` (1526 lines)

**Status**: Pending
**Target**: < 100 lines (router aggregation only)

### Current Importers

Before decomposition, identify all modules importing from `tools.py`:

```bash
# Run to find importers
rg "from.*routes\.mcp\.tools import|from.*routes\.mcp import.*tools" src/
```

### New Structure

```text
src/gobby/servers/routes/mcp/
├── __init__.py
├── tools.py              # (The Monolith - to be strangled)
└── endpoints/            # [NEW]
    ├── __init__.py
    ├── discovery.py      # list_tools, search_tools, recommend_tools
    ├── execution.py      # call_tool, get_tool_schema
    ├── server.py         # list_servers, add_server, remove_server
    └── registry.py       # import_server, specialized registry logic
```

### Shared Dependencies

Identify before moving:
- Auth dependencies (API key validation, session context)
- Database session injection
- MCPClientManager instance
- Response models

**Tasks:**

- [ ] Create `endpoints/` skeleton with `__init__.py` (category: code)
- [ ] Slice 1: Move discovery endpoints to `endpoints/discovery.py` (category: refactor)
  - Target: `tools.py` reduced to ~1200 lines
- [ ] Slice 2: Move server management to `endpoints/server.py` (category: refactor)
  - Target: `tools.py` reduced to ~900 lines
- [ ] Slice 3: Move execution to `endpoints/execution.py` (category: refactor)
  - Target: `tools.py` reduced to ~600 lines
- [ ] Slice 4: Move registry logic to `endpoints/registry.py` (category: refactor)
  - Target: `tools.py` reduced to ~100 lines
- [ ] Finalize: Update `tools.py` to aggregate routers (category: refactor)
- [ ] Update all importers to use new locations (category: refactor)

**Acceptance Criteria:**

- `tools.py` < 100 lines (router aggregation only)
- All route tests pass
- No circular imports
- All importers updated

---

## Phase 4: Codex Decomposition

**Goal**: Separate Protocol/Types from Client Logic

### Candidate: `src/gobby/adapters/codex.py` (1332 lines)

**Status**: Pending
**Target**: < 200 lines (adapter facade only)

### New Structure

```text
src/gobby/adapters/
├── codex.py              # (The Monolith - adapter entry point)
└── codex_impl/           # [NEW]
    ├── __init__.py
    ├── types.py          # CodexConnectionState, CodexThread, CodexTurn, CodexItem
    ├── protocol.py       # JSON-RPC mappings, NotificationHandler
    ├── client.py         # CodexAppServerClient logic (transport layer)
    └── adapter.py        # High-level CodexAdapter class
```

**Tasks:**

- [ ] Slice 1: Move dataclasses and Enums to `codex_impl/types.py` (category: refactor)
  - Target: `codex.py` reduced to ~1100 lines
- [ ] Slice 2: Move `CodexAppServerClient` to `codex_impl/client.py` (category: refactor)
  - Target: `codex.py` reduced to ~400 lines
- [ ] Slice 3: Move adapter to `codex_impl/adapter.py`, keep facade in `codex.py` (category: refactor)
  - Target: `codex.py` reduced to ~200 lines

**Acceptance Criteria:**

- `codex.py` < 200 lines (re-exports and facade only)
- All adapter tests pass
- No circular imports

---

## Graduated Candidates

### `src/gobby/mcp_proxy/tools/worktrees.py` (926 lines)

**Status**: Optimized / Retained
**Rationale**:
- File is now < 1000 lines, graduating from the "God Object" list
- Worktrees provide efficient isolation for sequential development
- `clones.py` handles parallel orchestration separately
- No further decomposition required

---

## General Rules

1. **Tests First**: Ensure existing tests pass before touching any file
2. **Atomic Commits**: Move one slice at a time and commit
3. **Verify Imports**: Moving code often breaks circular imports; use `TYPE_CHECKING` blocks or dependency injection
4. **No Logic Changes**: Structural refactoring only; avoid business logic changes unless required to untangle dependencies
5. **Track Line Counts**: After each slice, verify line count matches target

---

## Task Mapping

<!-- Updated after task creation -->
| Plan Item | Task Ref | Status |
|-----------|----------|--------|
