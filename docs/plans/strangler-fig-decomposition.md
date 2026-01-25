# Strangler Fig Decomposition Plan

This document outlines the strategy for decomposing the "God Object" identified in the Gobby codebase using the **Strangler Fig** pattern. This pattern allows us to incrementally migrate functionality from a monolithic system to a modular one without rewriting the entire system at once.

## Core Strategy

For each candidate, we will follow these steps:
1.  **Identify Seams**: Find logical groupings of functionality (e.g., by domain, feature, or resource).
2.  **Create New Structure**: Establish a new package directory to house the decomposed modules.
3.  **Route/Proxy**: For the first slice, implement it in the new module and update the original file to import and use the new module (aliasing/proxying).
4.  **Iterate**: Repeat for each subsequent slice.
5.  **Withering**: Once the original file is empty or purely a re-export layer, **delete it completely**. We prioritize a clean codebase over backward compatibility for these internal modules. This means updating all importers to point to the new locations.

---

## 1. Candidate: `src/gobby/servers/routes/mcp/tools.py` (1512 lines)

**Target**: Decompose into domain-specific routers.

### New Structure
```text
src/gobby/servers/routes/mcp/
├── __init__.py
├── tools.py              # (The Monolith - to be strangled)
└── endpoints/            # [NEW]
    ├── __init__.py
    ├── discovery.py      # list_tools, search_tools
    ├── execution.py      # call_tool
    ├── server.py         # list_servers, add_server, etc.
    └── registry.py       # import_server, specialized registry logic
```

### Steps
1.  **Skeleton**: Create `src/gobby/servers/routes/mcp/endpoints/`.
2.  **Slice 1 (Discovery)**: Move `list_mcp_tools`, `search_mcp_tools`, and `recommend_mcp_tools` to `endpoints/discovery.py`.
    *   *Strangler*: In `tools.py`, import the router from `discovery.py` and mount it, or re-implement the route functions to call the new logic.
3.  **Slice 2 (Server Management)**: Move `list_mcp_servers`, `add_mcp_server`, `remove_mcp_server` to `endpoints/server.py`.
4.  **Slice 3 (Execution)**: Move `call_mcp_tool` and `get_tool_schema` to `endpoints/execution.py`.
5.  **Finalize**: Update `tools.py` to simply aggregate these routers into the main MCP router.

---

## 2. Candidate: `src/gobby/workflows/actions.py` (1385 lines)

**Target**: Decompose into a registry of Action Handlers.

### New Structure
```text
src/gobby/workflows/
├── actions.py            # (The Monolith - execution engine)
└── handlers/             # [NEW]
    ├── __init__.py
    ├── base.py           # ActionHandler protocol/interface
    ├── state.py          # save/load workflow state, set_variable
    ├── io.py             # inject_message, read_artifact
    ├── execution.py      # verify_step, mark_loop_complete
    └── web.py            # webhook related
```

### Steps
1.  **Interface**: Formalize the `ActionHandler` protocol in `handlers/base.py` (extract from `actions.py`).
2.  **Slice 1 (State Actions)**: Move `_handle_save_workflow_state`, `_handle_load_workflow_state`, and `_handle_set_variable` to `handlers/state.py` as standalone classes/functions calling `db`.
3.  **Registry Update**: refactor `ActionExecutor` in `actions.py` to register these external handlers instead of having hardcoded `_handle_*` methods.
4.  **Iterate**: Continue moving IO, Execution, and Webhook actions to their respective modules.

---

## 3. Candidate: `src/gobby/mcp_proxy/tools/worktrees.py` (1270 lines)

**Target**: Decompose into granular Worktree toolsets.

### New Structure
```text
src/gobby/mcp_proxy/tools/
├── worktrees.py          # (The Monolith - registry entry point)
└── worktree_funcs/       # [NEW] (name to be decided, e.g. `worktree_impl`)
    ├── __init__.py
    ├── lifecycle.py      # create_worktree, delete_worktree
    ├── ops.py            # claim_worktree, release_worktree
    ├── git.py            # sync_worktree, reset_worktree
    └── spawn.py          # spawn_agent_in_worktree
```

### Steps
1.  **Slice 1 (Lifecycle)**: Extract `create_worktree` and `delete_worktree` (and their helpers like `_generate_worktree_path`) to `worktree_funcs/lifecycle.py`.
    *   *Note*: These functions share `WorktreeGitManager`. Ensure this dependency is injected or shared cleanly.
2.  **Slice 2 (Operations)**: Extract claim/release logic to `ops.py`.
3.  **Refactor Registry**: Update `create_worktrees_registry` in `worktrees.py` to import these functions. `create_worktrees_registry` becomes a simple configuration function that maps tool names to these imported functions.

---

## 4. Candidate: `src/gobby/adapters/codex.py` (1333 lines)

**Target**: Separate Protocol/Types from Client Logic.

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

### Steps
1.  **Slice 1 (Types)**: Move all dataclasses and Enums (`CodexConnectionState`, etc.) to `codex_impl/types.py`. Update `codex.py` to import them.
2.  **Slice 2 (Client)**: Move `CodexAppServerClient` to `codex_impl/client.py`. This is the bulk of the logic.
3.  **Slice 3 (Adapter)**: Keep the `CodexAdapter` integration layer in `codex.py` (or move to `adapter.py` if meaningful), but it should now rely on the clean imports from `codex_impl` rather than defining everything inline.

---

## General Rules for Decomposition

1.  **Tests First**: Ensure existing tests pass before touching any file.
2.  **Atomic Commits**: Move one slice at a time and commit. Do not try to move everything in one PR.
3.  **Verify Imports**: Moving code often breaks circular imports. Be prepared to introduce `TYPE_CHECKING` blocks or dependency injection to resolve these.
4.  **No Logic Changes**: The primary goal is structural refactoring. Avoid changing business logic simultaneously unless absolutely necessary to untangle dependencies.
