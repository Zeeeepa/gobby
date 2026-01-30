# Plan: Codex Hook Parity via App-Server Protocol

## Overview

Enable full hook parity for Codex CLI by leveraging the app-server protocol for real-time approval/blocking, context injection, and workflow enforcement. Currently Codex only supports fire-and-forget "notify" hooks - this plan adds bidirectional hook support matching Claude Code and Gemini capabilities.

## Current State

| Feature | Claude Code | Gemini | Codex (Current) | Gap |
|---------|-------------|--------|-----------------|-----|
| Session lifecycle | ✅ | ✅ | ✅ (notify) | - |
| Pre-tool blocking | ✅ | ✅ | ❌ | **Critical** |
| Context injection | ✅ | ✅ | ❌ | **Critical** |
| Session metadata | ✅ | ✅ | ❌ | Medium |
| Workflow enforcement | ✅ | ✅ | ❌ | **Critical** |

## Architecture

### App-Server Protocol (from Context7 research)

Codex app-server provides JSON-RPC over stdin/stdout:

```
Server → Client: item/commandExecution/requestApproval (JSON-RPC request)
Client → Server: {"decision": "accept" | "decline"} (JSON-RPC response)
```

**Two approval types:**
- `item/commandExecution/requestApproval` - Shell commands (Bash)
- `item/fileChange/requestApproval` / `applyPatchApproval` - File writes/edits

**Context injection option:**
- `instructions` field in `turn/start` - System prompt for the turn (one-time, not per-hook)

## Implementation Phases

### Phase 1: Approval Response Loop (Priority 1)
**Goal:** Enable real-time tool blocking via app-server approval requests

**Files to modify:**

1. **`src/gobby/adapters/codex_impl/adapter.py`**
   - Add `_pending_approvals: dict[str, asyncio.Future]` to track pending requests
   - Implement `handle_approval_request()` → translates to HookEvent, returns decision
   - Add callback registration for approval request methods

2. **`src/gobby/adapters/codex_impl/client.py`**
   - Add `register_approval_handler(callback)` method
   - Modify reader task to detect approval requests (JSON-RPC with `id` field)
   - Route approval requests to handler, await response, send back

3. **`src/gobby/servers/http.py`**
   - Wire `CodexAdapter` to `CodexAppServerClient` on startup
   - Call `codex_adapter.attach_to_client(client)` in init

4. **`src/gobby/servers/routes/mcp/hooks.py`**
   - Add routing for app-server mode Codex events
   - Keep CodexNotifyAdapter for notify-only installations

### Phase 2: Context Injection (Priority 2)
**Goal:** Inject session metadata and workflow context into Codex turns

**Challenge:** Codex doesn't have `additionalContext` in approval responses. Options:

**Option A: Turn-start injection (Recommended)**
- Inject context into `instructions` field when starting a turn
- One-time injection per turn (not per-tool like Claude)
- Simpler, aligns with Codex architecture

**Option B: MCP tool exposure**
- Codex calls Gobby MCP tools to get context
- Agent-driven (already works via MCP server config)
- No hook-level injection needed

**Files to modify (Option A):**

1. **`src/gobby/adapters/codex_impl/client.py`**
   - Add `context_prefix: str | None` parameter to `start_turn()`
   - Prepend context to `instructions` or use separate field if supported

2. **`src/gobby/adapters/codex_impl/adapter.py`**
   - Extend `translate_from_hook_response()` for BEFORE_AGENT hooks
   - Build context string with session metadata (like Claude/Gemini adapters)
   - Return context for injection into next turn

3. **`src/gobby/hooks/hook_manager.py`**
   - Ensure `_first_hook_for_session` tracking works for Codex source

### Phase 3: Workflow Enforcement (Priority 3)
**Goal:** Enable block_tools, task enforcement, commit policies for Codex

**Files to modify:**

1. **`src/gobby/adapters/codex_impl/adapter.py`**
   - Extract tool information from approval events
   - Normalize tool names via existing `TOOL_MAP`
   - Pass tool context to HookManager for workflow evaluation

2. **`src/gobby/workflows/enforcement/blocking.py`**
   - Verify Codex events are evaluated against block_tools rules
   - Test with existing workflows

3. **`src/gobby/workflows/enforcement/task_policy.py`**
   - Verify task enforcement works for Codex BEFORE_TOOL events

## Key Files Reference

| File | Purpose | Lines of Interest |
|------|---------|-------------------|
| `src/gobby/adapters/codex_impl/adapter.py` | CodexAdapter, CodexNotifyAdapter | 90-499, 506-716 |
| `src/gobby/adapters/codex_impl/client.py` | CodexAppServerClient | 600+ lines |
| `src/gobby/servers/http.py` | HTTPServer init | line 52 (codex_client param unused) |
| `src/gobby/servers/routes/mcp/hooks.py` | Hook routing | lines 73-92 |
| `src/gobby/hooks/hook_manager.py` | First-hook tracking | `_injected_sessions` set |

## Comparison: Context Injection Approaches

| Approach | Claude Code | Gemini | Codex (Proposed) |
|----------|-------------|--------|------------------|
| Mechanism | `additionalContext` in hook response | `additionalContext` in hook response | `instructions` at turn start |
| Timing | Every hook | Every hook | Once per turn |
| Token cost | ~8-60/hook (optimized) | ~8-60/hook (optimized) | ~60 once/turn |
| Flexibility | Per-tool injection | Per-tool injection | Per-turn only |

## Verification

### Phase 1 Testing
```bash
# Unit tests
uv run pytest tests/adapters/test_codex.py -v -k "approval"

# Integration test
# 1. Start gobby with app-server mode
# 2. Trigger Codex command that requires approval
# 3. Verify HookManager receives BEFORE_TOOL event
# 4. Verify approval response routes back to Codex
```

### Phase 2 Testing
```bash
# Verify context injection
# 1. Start Codex session via app-server
# 2. Check turn/start includes session metadata
# 3. Verify agent receives context in system prompt
```

### Phase 3 Testing
```bash
# Test workflow enforcement
# 1. Configure block_tools workflow
# 2. Trigger blocked tool in Codex
# 3. Verify tool is declined via approval response
```

## Scope Decisions

**In Scope:**
- App-server mode hook enforcement
- Turn-start context injection
- Tool blocking via approval decisions
- Session metadata injection

**Out of Scope (Future Work):**
- Per-tool context injection (would require Codex protocol changes)
- MCP-based hook system (Codex uses app-server, not MCP for approvals)
- Notify mode blocking (fire-and-forget by design)

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Codex protocol changes | Pin to known app-server version, monitor releases |
| Approval timeout | Use configurable timeout with fallback to allow |
| Async complexity | Use existing asyncio patterns from CodexAppServerClient |

## Implementation Order

1. **Phase 1: Approval Loop** - 4 files (adapter, client, http, routes)
2. **Phase 2: Context Injection** - 3 files (client, adapter, hook_manager)
3. **Phase 3: Workflow Enforcement** - 3 files (adapter, blocking, task_policy)
4. **Tests** - 2-3 test files
