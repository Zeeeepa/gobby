# Strangler Fig Decomposition — Wave 2

## Overview

Decompose 6 oversized files (~6,825 lines total) into focused modules using the Strangler Fig pattern. This is Wave 2 of the decomposition effort; Wave 1 (epic #7084) covers cli/skills.py, storage/sessions.py, llm/claude.py, servers/websocket.py, and hooks/hook_manager.py.

Each extraction maintains backward compatibility via re-exports in the original file, followed by a cleanup phase to remove shims and update importers to canonical paths.

## Constraints

- Every extraction must maintain backward-compatible imports via re-exports
- All existing tests must pass after each extraction task; patch target updates are permitted, test logic changes are deferred to Phase 7 cleanup
- Follow established patterns: flat sibling files (like `claude_models.py`), existing subpackages (like `memory/services/`)
- Each task is atomic — completable in one session
- Phases 1–5 can execute in parallel (no cross-phase dependencies); Phase 6 is optional/deferrable; Phase 7 cleanup depends on all extraction phases

## Phase 1: Workflow Loader Extraction

**Goal**: Extract discovery, validation, caching, and sync concerns from `src/gobby/workflows/loader.py` (1,279 lines) into flat sibling files.

**Tasks:**
- [ ] Extract `DiscoveredWorkflow`, `_CachedEntry`, `_CachedDiscovery` dataclasses and cache helpers (`_is_stale`, `_is_discovery_stale`, `clear_cache`) to `src/gobby/workflows/loader_cache.py`; re-export `DiscoveredWorkflow` in `loader.py` (category: refactor)
- [ ] Extract `_validate_pipeline_references`, `_extract_step_refs`, `_check_refs` to `src/gobby/workflows/loader_validation.py` as standalone functions; add delegation methods on `WorkflowLoader` (category: refactor)
- [ ] Extract `discover_workflows`, `discover_lifecycle_workflows`, `discover_pipeline_workflows`, `_scan_directory`, `_scan_pipeline_directory` to `src/gobby/workflows/loader_discovery.py` as standalone async functions; add delegation methods on `WorkflowLoader` (depends: Phase 1 Task 1) (category: refactor)
- [ ] Extract sync wrapper infrastructure (`_sync_executor`, `_sync_executor_lock`, `_get_sync_executor`, `shutdown_sync_executor`, `_run_sync`, and all `*_sync` methods) to `src/gobby/workflows/loader_sync.py` as `WorkflowLoaderSyncMixin`; `WorkflowLoader` inherits from it (category: refactor)

## Phase 2: Memory Manager Extraction

**Goal**: Extract embedding, mem0, graph, and maintenance concerns from `src/gobby/memory/manager.py` (1,251 lines) into the existing `services/` subpackage.

**Tasks:**
- [ ] Extract `_store_embedding_sync`, `_store_embedding_async`, `reindex_embeddings` to `src/gobby/memory/services/embeddings.py` as `EmbeddingService`; `MemoryManager` delegates to it (category: refactor)
- [ ] Extract `_index_in_mem0`, `_extract_mem0_id`, `_delete_from_mem0`, `_search_mem0`, `_get_unsynced_memories`, `_lazy_sync` to `src/gobby/memory/services/mem0_sync.py` as `Mem0Service`; `MemoryManager` delegates to it (category: refactor)
- [ ] Extract `get_entity_graph`, `get_entity_neighbors` to `src/gobby/memory/services/graph.py` as `GraphService`; `MemoryManager` delegates to it (category: refactor)
- [ ] Extract `export_markdown`, `get_stats`, `decay_memories` to `src/gobby/memory/services/maintenance.py` as standalone functions; `MemoryManager` delegates to them (depends: Phase 2 Task 2) (category: refactor)

## Phase 3: Workflow Engine Extraction

**Goal**: Extract models, context building, transitions, and activation from `src/gobby/workflows/engine.py` (1,109 lines) into flat sibling files, continuing the existing pattern of `detection_helpers`, `approval_flow`, `audit_helpers`.

**Tasks:**
- [ ] Extract `DotDict` class and `TransitionResult` dataclass to `src/gobby/workflows/engine_models.py`; re-export both in `engine.py` (category: refactor)
- [ ] Extract `_resolve_session_and_project`, `_build_eval_context`, `_resolve_check_rules` to `src/gobby/workflows/engine_context.py` as standalone functions; add delegation methods on `WorkflowEngine` (category: refactor)
- [ ] Extract `transition_to`, `_execute_actions`, `_render_status_message`, `_auto_transition_chain` to `src/gobby/workflows/engine_transitions.py` as standalone async functions; add delegation methods on `WorkflowEngine` (depends: Phase 3 Task 1, Phase 3 Task 2) (category: refactor)
- [ ] Extract `activate_workflow` to `src/gobby/workflows/engine_activation.py` as standalone async function; add delegation method on `WorkflowEngine` (category: refactor)

### Phase 3 Risk Analysis

**Why high-risk:** `handle_event` is the critical hot path for all workflow processing, and `transition_to` / `_auto_transition_chain` have complex state mutation. Extraction must preserve exact sequencing and state save points.

**Precautions:**
- Extract incrementally — one task at a time with full test pass between each
- Phase 3 Task 3 (transitions) should be done last within its phase since it depends on Tasks 1 and 2
- Run integration tests exercising full workflow lifecycle after each extraction

## Phase 4: CLI Installers Shared Extraction

**Goal**: Extract MCP config, skill installation, and IDE config from `src/gobby/cli/installers/shared.py` (1,165 lines) into sibling files within the `installers/` directory.

**Tasks:**
- [ ] Extract `configure_project_mcp_server`, `remove_project_mcp_server`, `configure_mcp_server_json`, `remove_mcp_server_json`, `configure_mcp_server_toml`, `remove_mcp_server_toml`, `install_default_mcp_servers` to `src/gobby/cli/installers/mcp_config.py`; re-export in `shared.py` (category: refactor)
- [ ] Extract `backup_gobby_skills`, `install_shared_skills`, `install_router_skills_as_commands`, `install_router_skills_as_gemini_skills` to `src/gobby/cli/installers/skill_install.py`; re-export in `shared.py` (category: refactor)
- [ ] Extract `_get_ide_config_dir`, `configure_ide_terminal_title` to `src/gobby/cli/installers/ide_config.py`; re-export in `shared.py` (depends: Phase 4 Task 1) (category: refactor)

## Phase 5: Agents Runner Extraction

**Goal**: Extract dataclasses, in-memory tracking, and query methods from `src/gobby/agents/runner.py` (1,022 lines) into flat sibling files.

**Tasks:**
- [ ] Extract `AgentConfig` and `AgentRunContext` dataclasses to `src/gobby/agents/runner_models.py`; re-export in `runner.py` and update `agents/__init__.py` import source (category: refactor)
- [ ] Extract `_track_running_agent`, `_untrack_running_agent`, `_update_running_agent`, `get_running_agent`, `get_running_agents`, `get_running_agents_count`, `is_agent_running` to `src/gobby/agents/runner_tracking.py` as `RunTracker` class; `AgentRunner` delegates to it (depends: Phase 5 Task 1) (category: refactor)
- [ ] Extract `get_run`, `get_run_id_by_session`, `list_runs`, `cancel_run` to `src/gobby/agents/runner_queries.py` as standalone functions; `AgentRunner` delegates to them (category: refactor)

## Phase 6: CLI Workflows Extraction (Optional)

**Goal**: Extract formatting logic from `src/gobby/cli/workflows.py` (1,000 lines) into a sibling module. At threshold — deferrable if higher-priority work takes precedence.

**Tasks:**
- [ ] Extract formatting blocks (JSON output, rich table building, human-readable formatting) from `list_workflows`, `check_workflow`, `show_workflow`, `workflow_status`, `audit_workflow` into `src/gobby/cli/workflows_formatting.py` (category: refactor)
- [ ] Extract helper functions `get_workflow_loader`, `get_state_manager`, `get_project_path` to `src/gobby/cli/workflows_helpers.py`; re-import in `workflows.py` (category: refactor)

## Phase 7: Cleanup — Remove Re-exports

**Goal**: Remove backward-compat re-export shims and update all importers to canonical paths. Run per-phase after extraction is stable.

**Tasks:**
- [ ] Phase 1 cleanup: update importers of `DiscoveredWorkflow` to import from `loader_cache`; remove re-exports from `loader.py` (category: refactor)
- [ ] Phase 2 cleanup: verify no test patch targets reference moved private methods; no re-exports to remove (category: refactor)
- [ ] Phase 3 cleanup: update importers of `DotDict`/`TransitionResult` to import from `engine_models`; remove re-exports from `engine.py` (category: refactor)
- [ ] Phase 4 cleanup: update ~7 sibling installer files to import from `mcp_config`, `skill_install`, `ide_config`; remove re-exports from `shared.py` (category: refactor)
- [ ] Phase 5 cleanup: update `agents/__init__.py` and test files to import from `runner_models`; remove re-exports from `runner.py` (category: refactor)
- [ ] Phase 6 cleanup: no re-exports needed (no external importers of `cli/workflows.py`) (category: refactor)

## Task Mapping

| Plan Item | Task Ref | Status |
|-----------|----------|--------|
| **Root Epic** | #8153 | open |
| **Phase 1: Workflow Loader** | | |
| Extract cache dataclasses to loader_cache.py | #8155 | open |
| Extract validation functions to loader_validation.py | #8156 | open |
| Extract discovery functions to loader_discovery.py | #8157 | blocked by #8155 |
| Extract sync wrappers to loader_sync.py | #8158 | open |
| **Phase 2: Memory Manager** | | |
| Extract embedding service to services/embeddings.py | #8159 | open |
| Extract mem0 sync service to services/mem0_sync.py | #8160 | open |
| Extract graph service to services/graph.py | #8161 | open |
| Extract maintenance functions to services/maintenance.py | #8162 | blocked by #8160 |
| **Phase 3: Workflow Engine** | | |
| Extract DotDict/TransitionResult to engine_models.py | #8163 | open |
| Extract context building to engine_context.py | #8164 | open |
| Extract transition logic to engine_transitions.py | #8165 | blocked by #8163, #8164 |
| Extract activate_workflow to engine_activation.py | #8166 | open |
| **Phase 4: CLI Installers** | | |
| Extract MCP config to installers/mcp_config.py | #8167 | open |
| Extract skill install to installers/skill_install.py | #8168 | open |
| Extract IDE config to installers/ide_config.py | #8169 | blocked by #8167 |
| **Phase 5: Agents Runner** | | |
| Extract AgentConfig/AgentRunContext to runner_models.py | #8170 | open |
| Extract run tracking to runner_tracking.py | #8171 | blocked by #8170 |
| Extract runner queries to runner_queries.py | #8172 | open |
| **Phase 6: CLI Workflows (Optional)** | | |
| Extract formatting to workflows_formatting.py | #8173 | open |
| Extract helpers to workflows_helpers.py | #8174 | open |
| **Phase 7: Cleanup** | | |
| Phase 1 cleanup | #8175 | blocked by #8155-#8158 |
| Phase 2 cleanup | #8176 | blocked by #8159-#8162 |
| Phase 3 cleanup | #8177 | blocked by #8163-#8166 |
| Phase 4 cleanup | #8178 | blocked by #8167-#8169 |
| Phase 5 cleanup | #8179 | blocked by #8170-#8172 |
| Phase 6 cleanup | #8180 | blocked by #8173-#8174 |
