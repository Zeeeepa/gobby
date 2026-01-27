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
| 2 | `tools.py` | Largest file, requires careful router mounting |
| 3 | `codex.py` | Adapter code, can be done whenever |

---

## Phase 1: Actions Withering

**Goal**: Complete the withering phase for `actions.py`

### Candidate: `src/gobby/workflows/actions.py` (1392 lines)

**Status**: In Progress (Partial Decomposition)
**Target**: < 400 lines (registry + imports only)

**Current State**: Significant logic extracted into sibling modules (`autonomous_actions.py`, `context_actions.py`, `state_actions.py`, etc.). `actions.py` now primarily serves as the `ActionExecutor` registry with `_handle_*` wrapper methods that delegate to new modules.

**Tasks:**

- [ ] P1-1: Refactor `ActionExecutor.register_defaults` to register external callables directly (category: refactor)
- [ ] P1-2: Delete `_handle_*` wrapper methods from `ActionExecutor` (category: refactor, depends: P1-1)
- [ ] P1-3: Verify all action imports work correctly (category: manual, depends: P1-2)

**Acceptance Criteria:**

- `actions.py` contains only registry logic and imports
- All existing tests pass
- No `_handle_*` methods remain in the file
- Line count < 400

---

## Phase 2: Tools Decomposition

**Goal**: Decompose into domain-specific routers

### Candidate: `src/gobby/servers/routes/mcp/tools.py` (1526 lines)

**Status**: Pending
**Target**: < 100 lines (router aggregation only)

### Current Importers

Run during P2-1 to identify all modules importing from `tools.py`:
- Pattern: `from.*routes\.mcp\.tools import|from.*routes\.mcp import.*tools`

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

- [ ] P2-1: Create `endpoints/` skeleton with `__init__.py` (category: code)
- [ ] P2-2: Move discovery endpoints to `endpoints/discovery.py` (category: refactor, depends: P2-1)
  - Move: `list_tools`, `search_tools`, `recommend_tools`
  - Target: `tools.py` reduced to ~1200 lines
- [ ] P2-3: Move server management to `endpoints/server.py` (category: refactor, depends: P2-2)
  - Move: `list_servers`, `add_server`, `remove_server`
  - Target: `tools.py` reduced to ~900 lines
- [ ] P2-4: Move execution to `endpoints/execution.py` (category: refactor, depends: P2-3)
  - Move: `call_tool`, `get_tool_schema`
  - Target: `tools.py` reduced to ~600 lines
- [ ] P2-5: Move registry logic to `endpoints/registry.py` (category: refactor, depends: P2-4)
  - Move: `import_server`, specialized registry logic
  - Target: `tools.py` reduced to ~100 lines
- [ ] P2-6: Update `tools.py` to aggregate routers only (category: refactor, depends: P2-5)
- [ ] P2-7: Update all importers to use new locations (category: refactor, depends: P2-6)

**Acceptance Criteria:**

- `tools.py` < 100 lines (router aggregation only)
- All route tests pass
- No circular imports
- All importers updated

---

## Phase 3: Codex Decomposition

**Goal**: Separate Protocol/Types from Client Logic

### Candidate: `src/gobby/adapters/codex.py` (1332 lines)

**Status**: Pending
**Target**: < 200 lines (adapter facade only)

### Current Importers

Run during P3-1 to identify all modules importing from `codex.py`:
- Pattern: `from.*adapters\.codex import|from.*adapters import.*codex`

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

- [ ] P3-1: Create `codex_impl/` skeleton with `__init__.py` (category: code)
- [ ] P3-2: Move dataclasses and Enums to `codex_impl/types.py` (category: refactor, depends: P3-1)
  - Move: `CodexConnectionState`, `CodexThread`, `CodexTurn`, `CodexItem`
  - Target: `codex.py` reduced to ~1100 lines
- [ ] P3-3: Move `CodexAppServerClient` to `codex_impl/client.py` (category: refactor, depends: P3-2)
  - Target: `codex.py` reduced to ~400 lines
- [ ] P3-4: Move adapter to `codex_impl/adapter.py`, keep facade in `codex.py` (category: refactor, depends: P3-3)
  - Target: `codex.py` reduced to ~200 lines
- [ ] P3-5: Update all importers to use new locations (category: refactor, depends: P3-4)

**Acceptance Criteria:**

- `codex.py` < 200 lines (re-exports and facade only)
- All adapter tests pass
- No circular imports
- All importers updated

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
