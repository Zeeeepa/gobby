# Strangler Fig Decomposition

## Overview

Decompose 5 oversized files (~5,200 lines total) into focused modules using the Strangler Fig pattern. Each extraction maintains backward compatibility via re-exports, followed by a cleanup phase to remove shims and update importers to canonical paths.

## Constraints

- Every extraction must maintain backward-compatible imports via re-exports
- All existing tests must pass after each task without test modifications (except Phase 4B and Phase 5 where patch target updates are planned)
- Follow established patterns: mixin decomposition (event_handlers/), flat re-exports (storage/__init__), factory+re-exports (llm/__init__)
- Each task is atomic — completable in one session
- Phases 1, 2, 3 can execute in parallel; Phase 4A depends on 3.1; Phase 4B is independent but highest risk

## Phase 1: CLI Skills Extraction

**Goal**: Extract business logic from `src/gobby/cli/skills.py` (1068 lines) into the existing `src/gobby/skills/` package. CLI file stays as thin Click wrappers.

**Tasks:**
- [ ] Extract metadata helpers (_get_nested_value, _set_nested_value, _unset_nested_value, _get_skill_tags, _get_skill_category) to src/gobby/skills/metadata.py and re-import in CLI (category: refactor)
- [ ] Extract scaffold logic (name validation, dir creation, SKILL.md template from new/init commands) to src/gobby/skills/scaffold.py (category: refactor)
- [ ] Extract formatting helpers (_output_json, markdown table generation from doc command) to src/gobby/skills/formatting.py (category: refactor)

## Phase 2: Storage Sessions Extraction

**Goal**: Extract cohesive groups from `src/gobby/storage/sessions.py` (947 lines) into sibling modules. sessions.py stays as a file with LocalSessionManager as slim facade. Re-exports ensure `from gobby.storage.sessions import Session` continues working.

**Tasks:**
- [ ] Extract Session dataclass (including from_row, to_dict, parse helpers) to src/gobby/storage/session_models.py and re-export in sessions.py (category: refactor)
- [ ] Extract resolve_session_reference as standalone function to src/gobby/storage/session_resolution.py with delegation method on LocalSessionManager (depends: Phase 2 Task 1) (category: refactor)
- [ ] Extract expire_stale_sessions and pause_inactive_active_sessions to src/gobby/storage/session_lifecycle.py with delegation methods (depends: Phase 2 Task 1) (category: refactor)

## Phase 3: LLM Claude Provider Extraction

**Goal**: Extract from `src/gobby/llm/claude.py` (1114 lines) into sibling modules. claude.py stays as a file to avoid breaking 50+ patch targets.

**Tasks:**
- [ ] Extract 6 dataclasses (ToolCall, MCPToolResult, TextChunk, ToolCallEvent, ToolResultEvent, DoneEvent) and ChatEvent alias to src/gobby/llm/claude_models.py, re-export in claude.py, update llm/__init__.py import source (category: refactor)
- [ ] Extract _find_cli_path and _verify_cli_path to src/gobby/llm/claude_cli.py as standalone functions with delegation methods on ClaudeLLMProvider (category: refactor)
- [ ] Extract stream_with_mcp_tools and shared _parse_server_name helper to src/gobby/llm/claude_streaming.py as standalone async generator with delegation method (depends: Phase 3 Task 1) (category: refactor)

## Phase 4A: WebSocket Server Extraction

**Goal**: Convert `src/gobby/servers/websocket.py` (1135 lines) to a `websocket/` package. Only 4 importers all use `from gobby.servers.websocket import WebSocketServer, WebSocketConfig`.

**Tasks:**
- [ ] Create websocket package scaffold: __init__.py with re-exports, models.py with WebSocketClient/WebSocketConfig, server.py with full WebSocketServer class, delete websocket.py (category: refactor)
- [ ] Extract broadcast() and 7 broadcast_* methods to websocket/broadcast.py as BroadcastMixin inherited by WebSocketServer (depends: Phase 4A Task 1) (category: refactor)
- [ ] Extract _handle_tool_call, _handle_ping, _handle_subscribe, _handle_unsubscribe, _handle_stop_request, _handle_terminal_input to websocket/handlers.py (depends: Phase 4A Task 1) (category: refactor)
- [ ] Extract _handle_chat_message (207 lines, largest handler) to websocket/chat.py (depends: Phase 4A Task 1, Phase 3 Task 1) (category: refactor)
- [ ] Extract _authenticate to websocket/auth.py (depends: Phase 4A Task 1) (category: refactor)

## Phase 4B: Hook Manager Extraction

**Goal**: Continue Strangler Fig on `src/gobby/hooks/hook_manager.py` (944 lines, already partially decomposed). Extract 320-line __init__ and embedded handle() logic.

**Tasks:**
- [ ] Extract subsystem creation from __init__ (lines 137-424) to src/gobby/hooks/factory.py as HookManagerFactory with HookManagerComponents dataclass, update ~20 test patch targets (category: refactor)
- [ ] Extract session resolution from handle() (lines 538-615) to src/gobby/hooks/session_lookup.py as SessionLookupService (depends: Phase 4B Task 1) (category: refactor)
- [ ] Extract response metadata enrichment from handle() (lines 672-716) to src/gobby/hooks/event_enrichment.py as EventEnricher (depends: Phase 4B Task 1) (category: refactor)

## Phase 5: Cleanup — Remove Re-exports

**Goal**: Remove backward-compat re-export shims and update all importers to use canonical module paths. Run per-phase after extraction is stable.

**Tasks:**
- [ ] Phase 1 cleanup: update ~1 importer in cli/__init__.py to import from skills/ modules, remove re-exports from cli/skills.py (category: refactor)
- [ ] Phase 2 cleanup: update ~69 importers across codebase to import Session from session_models, update ~4 patch targets, remove re-exports from sessions.py (category: refactor)
- [ ] Phase 3 cleanup: update ~8 importers and llm/__init__.py to import from claude_models/claude_cli/claude_streaming, update ~50 patch targets, remove re-exports from claude.py (category: refactor)
- [ ] Phase 4A cleanup: update 4 importers to import from websocket/ submodules if needed (category: refactor)
- [ ] Phase 4B cleanup: update ~15 importers to import from factory/session_lookup/event_enrichment, remove re-exports from hook_manager.py (category: refactor)

## Task Mapping

| Plan Item | Task Ref | Status |
|-----------|----------|--------|
| **Root Epic** | #7084 | open |
| **Phase 1: CLI Skills** | #7085 | open |
| Extract metadata helpers | #7091 | open |
| Extract scaffold logic | #7092 | open |
| Extract formatting helpers | #7093 | open |
| **Phase 2: Storage Sessions** | #7086 | open |
| Extract Session dataclass | #7094 | open |
| Extract resolve_session_reference | #7095 | blocked by #7094 |
| Extract lifecycle methods | #7096 | blocked by #7094 |
| **Phase 3: LLM Claude** | #7087 | open |
| Extract claude models | #7097 | open |
| Extract CLI path management | #7098 | open |
| Extract streaming logic | #7099 | blocked by #7097 |
| **Phase 4A: WebSocket** | #7088 | open |
| Create websocket package scaffold | #7100 | open |
| Extract broadcast methods | #7101 | blocked by #7100 |
| Extract message handlers | #7102 | blocked by #7100 |
| Extract chat handler | #7103 | blocked by #7100, #7097 |
| Extract auth | #7104 | blocked by #7100 |
| **Phase 4B: Hook Manager** | #7089 | open |
| Extract HookManagerFactory | #7105 | open |
| Extract SessionLookupService | #7106 | blocked by #7105 |
| Extract EventEnricher | #7107 | blocked by #7105 |
| **Phase 5: Cleanup** | #7090 | open |
| Phase 1 cleanup | #7108 | blocked by #7091-#7093 |
| Phase 2 cleanup | #7109 | blocked by #7094-#7096 |
| Phase 3 cleanup | #7110 | blocked by #7097-#7099 |
| Phase 4A cleanup | #7111 | blocked by #7100-#7104 |
| Phase 4B cleanup | #7112 | blocked by #7105-#7107 |
