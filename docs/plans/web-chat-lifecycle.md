# Plan: Headless Lifecycle for Web UI Chat Agent

## Context

The web UI chat agent uses `ClaudeSDKClient` (Claude Agent SDK) which doesn't fire `SessionStart` or `SessionEnd` hooks. But it DOES support `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `PreCompact`, and `Stop` hooks. This means we can bridge most lifecycle events — just not session start/end.

Rather than faking session_start with synthetic events, we create a clean separation:

- **`headless-lifecycle.yaml`**: a lifecycle workflow designed for non-hook clients. No `on_session_start`. Uses `on_before_agent` first-run detection for initialization. Same enforcement/tracking as `session-lifecycle.yaml` for tool blocking, progressive disclosure, etc.
- **Backend (ChatMixin)**: handles what the workflow can't — session DB registration, lifecycle activation, wiring SDK hooks to the workflow engine, and /clear (summary generation + session teardown).

## Architecture

```
SDK Hook Callbacks (ChatSession)
  ├─ UserPromptSubmit → workflow engine → headless-lifecycle on_before_agent
  ├─ PreToolUse       → workflow engine → headless-lifecycle on_before_tool
  ├─ PostToolUse      → workflow engine → headless-lifecycle on_after_tool
  ├─ PreCompact       → workflow engine → headless-lifecycle on_pre_compact
  └─ Stop             → workflow engine → headless-lifecycle on_stop

Backend (ChatMixin)
  ├─ Session registration  → session_manager.register_session()
  ├─ Lifecycle activation  → activate_workflow("headless-lifecycle")
  └─ /clear handling       → generate_summary() + stop session
```

## Implementation

### Step 1: Create `headless-lifecycle.yaml`

**File: `src/gobby/install/shared/workflows/lifecycle/headless-lifecycle.yaml`**

New lifecycle workflow with same variables and enforcement as `session-lifecycle.yaml`, but:
- No `on_session_start` section
- `on_before_agent` has a first-run guard (`_session_initialized`) that runs init actions
- `on_pre_compact` resets progressive disclosure variables directly (not via `pending_context_reset` flag since there's no session_start to consume it)
- No `on_session_end` (backend handles handoff)

Key sections:

```yaml
name: headless-lifecycle
description: "Lifecycle for headless/SDK clients without session_start hooks"
type: lifecycle

settings:
  priority: 10

variables:
  # Same as session-lifecycle, plus:
  _session_initialized: false

triggers:
  on_before_agent:
    # --- First-run init (replaces on_session_start) ---
    - action: set_variable
      when: "not variables.get('_session_initialized')"
      name: plan_mode
      value: false

    - action: capture_baseline_dirty_files
      when: "not variables.get('_session_initialized')"

    - action: memory_sync_import
      when: "not variables.get('_session_initialized')"

    - action: task_sync_import
      when: "not variables.get('_session_initialized')"

    - action: inject_context
      when: "not variables.get('_session_initialized')"
      source: skills
      filter: always_apply
      template: |
        {{ skills_list }}

    - action: inject_context
      when: "not variables.get('_session_initialized')"
      source: task_context
      template: |
        {{ task_context }}

    - action: inject_context
      when: "not variables.get('_session_initialized')"
      template: |
        ## Pre-Existing Error/Warning/Failure Policy
        ...same as session-lifecycle...

    - action: set_variable
      when: "not variables.get('_session_initialized')"
      name: _session_initialized
      value: true

    # --- Per-turn resets (same as session-lifecycle) ---
    - action: set_variable
      name: stop_attempts
      value: 0
    # ... etc (same as session-lifecycle on_before_agent)

  on_before_tool:
    # Same as session-lifecycle (block_tools rules)

  on_after_tool:
    # Same as session-lifecycle (track_schema_lookup, track_discovery_step, etc.)

  on_pre_compact:
    # Reset progressive disclosure directly (no pending_context_reset dance)
    - action: set_variable
      name: unlocked_tools
      value: []
    - action: set_variable
      name: servers_listed
      value: false
    - action: set_variable
      name: listed_servers
      value: []
    - action: reset_memory_injection_tracking
    - action: set_variable
      name: memories_extracted
      value: false

    # Extract handoff context for compact continuation
    - action: extract_handoff_context
    - action: memory_sync_export
    - action: task_sync_export

  on_stop:
    # Same as session-lifecycle (block_stop rules, memory_extraction_gate)
```

### Step 2: Wire workflow engine to WebSocketServer

**File: `src/gobby/servers/websocket/server.py`**

Add attributes for the workflow engine and session manager:

```python
self.workflow_handler: WorkflowHookHandler | None = None
self.session_manager: LocalSessionManager | None = None
```

**File: `src/gobby/servers/http.py`** (startup lifespan, after hook_manager is created)

Wire these through, following the existing `stop_registry` pattern:

```python
if self.services.websocket_server:
    self.services.websocket_server.workflow_handler = app.state.hook_manager._workflow_handler
    self.services.websocket_server.session_manager = self.services.session_manager
```

### Step 3: Register SDK hooks in ChatSession

**File: `src/gobby/servers/chat_session.py`**

Add callback attributes and SDK hook registration. The callbacks let the ChatMixin bridge events to the workflow engine.

```python
@dataclass
class ChatSession:
    ...
    _on_before_agent: Callable | None = field(default=None, repr=False)
    _on_pre_tool: Callable | None = field(default=None, repr=False)
    _on_post_tool: Callable | None = field(default=None, repr=False)
    _on_pre_compact: Callable | None = field(default=None, repr=False)
    _on_stop: Callable | None = field(default=None, repr=False)
```

Register hooks in `start()`:

```python
hooks = {}
if self._on_before_agent:
    hooks['UserPromptSubmit'] = [HookMatcher(matcher=None, hooks=[self._make_prompt_hook()])]
if self._on_pre_compact:
    hooks['PreCompact'] = [HookMatcher(matcher=None, hooks=[self._make_compact_hook()])]
# ... etc for PreToolUse, PostToolUse, Stop

options = ClaudeAgentOptions(
    ...
    hooks=hooks if hooks else None,
)
```

Each hook callback calls the corresponding `_on_*` callback, passing event data.

### Step 4: Backend bootstrap in ChatMixin

**File: `src/gobby/servers/websocket/chat.py`**

When creating a new ChatSession:

```python
async def _create_chat_session(self, conversation_id: str, model: str | None) -> ChatSession:
    """Create and bootstrap a new ChatSession."""
    session = ChatSession(conversation_id=conversation_id)

    # 1. Register session in DB (with transcript path for monitoring + handoff)
    session_id = None
    if self.session_manager:
        project_root = _find_project_root()
        cwd = str(project_root) if project_root else str(Path.cwd())
        project_id = self._resolve_project_id(cwd)
        # Claude CLI writes transcripts here (derived from conversation_id)
        jsonl_path = Path.home() / ".claude" / "sessions" / conversation_id
        session_id = self.session_manager.register_session(
            external_id=conversation_id,
            machine_id=self._get_machine_id(),
            project_id=project_id,
            jsonl_path=str(jsonl_path),
            source="claude_sdk",
            project_path=cwd,
        )

    # 2. Activate headless-lifecycle for this session
    if self.workflow_handler and session_id:
        self.workflow_handler.activate_workflow(
            "headless-lifecycle", session_id, project_path=cwd
        )

    # 3. Wire SDK hook callbacks → workflow engine
    session._on_before_agent = lambda data: self._fire_lifecycle(
        conversation_id, HookEventType.BEFORE_AGENT, data)
    session._on_pre_compact = lambda data: self._fire_lifecycle(
        conversation_id, HookEventType.PRE_COMPACT, data)
    # ... etc

    # 4. Start session
    await session.start(model=model)
    return session
```

### Step 5: Lifecycle event bridge in ChatMixin

**File: `src/gobby/servers/websocket/chat.py`**

```python
async def _fire_lifecycle(self, conversation_id: str, event_type: HookEventType,
                           data: dict) -> HookResponse | None:
    """Bridge SDK hook events to workflow engine lifecycle triggers."""
    if not self.workflow_handler:
        return None

    event = HookEvent(
        event_type=event_type,
        session_id=conversation_id,
        source=SessionSource.CLAUDE_SDK,
        data=data,
    )

    return await asyncio.to_thread(
        self.workflow_handler.handle_all_lifecycles, event
    )
```

### Step 6: /clear command for web UI chat

Add a `/clear` slash command to the web UI that ends the current conversation (generating a session summary) and starts a fresh one.

**Compact handoff** is handled entirely by the workflow: PreCompact SDK hook → on_pre_compact (resets variables, extracts context, stores compact_markdown) → next UserPromptSubmit → on_before_agent injects compact context. No backend involvement needed.

**/clear** is backend-driven:

**File: `src/gobby/servers/websocket/chat.py`**

Add `_handle_clear_chat()` method:

```python
async def _handle_clear_chat(self, websocket: Any, data: dict[str, Any]) -> None:
    """Handle /clear command: generate summary, end session, start fresh."""
    conversation_id = data.get("conversation_id")
    if not conversation_id:
        return

    session = self._chat_sessions.get(conversation_id)
    if not session:
        return

    # 1. Generate session summary from JSONL transcript
    if self.session_manager:
        db_session = self.session_manager.find_by_external_id(conversation_id)
        if db_session:
            from gobby.workflows.summary_actions import generate_summary
            await generate_summary(db_session.id, mode="clear")
            self.session_manager.update_status(db_session.id, "completed")

    # 2. Stop the old ChatSession
    await self._cancel_active_chat(conversation_id)
    await session.stop()
    del self._chat_sessions[conversation_id]

    # 3. Notify frontend to start fresh conversation
    await websocket.send(json.dumps({
        "type": "chat_cleared",
        "conversation_id": conversation_id,
    }))
```

Register the handler in the WebSocket message router.

**File: `web/src/hooks/useChat.ts`** (line 459, `clearHistory`)

Currently `clearHistory` only resets frontend state (messages, localStorage, new conversation_id) and never notifies the backend. Update to send `clear_chat` to backend first:

```typescript
const clearHistory = useCallback(() => {
  const oldConversationId = conversationIdRef.current
  // Notify backend to generate summary + teardown session
  if (wsRef.current?.readyState === WebSocket.OPEN) {
    wsRef.current.send(JSON.stringify({
      type: 'clear_chat',
      conversation_id: oldConversationId,
    }))
  }
  // Reset frontend state
  setMessages([])
  localStorage.removeItem(STORAGE_KEY)
  activeRequestIdRef.current = null
  conversationIdRef.current = uuid()
  localStorage.removeItem(CONVERSATION_ID_KEY)
}, [])
```

No change needed to the trash icon in `App.tsx:89` — it already calls `clearHistory`.

Add `/clear` as a recognized slash command in the chat input (alongside any existing command handling in `executeCommand`).

**Note**: The Claude CLI writes JSONL transcripts (via `--output-format stream-json`) at `~/.claude/sessions/<session-id>/`. Since we register the `jsonl_path` in Step 4, `generate_summary` can read the transcript for summary generation — same as CLI sessions.

## Files to modify

| # | File | Change |
|---|------|--------|
| 1 | `src/gobby/install/shared/workflows/lifecycle/headless-lifecycle.yaml` | **New file** — lifecycle workflow for SDK/headless clients |
| 2 | `src/gobby/servers/websocket/server.py` | Add `workflow_handler` and `session_manager` attributes |
| 3 | `src/gobby/servers/http.py` | Wire `workflow_handler` + `session_manager` to WebSocket server |
| 4 | `src/gobby/servers/chat_session.py` | Add lifecycle callbacks (`_on_*`), SDK hook registration in `start()` |
| 5 | `src/gobby/servers/websocket/chat.py` | Add `_create_chat_session()`, `_fire_lifecycle()`, `_handle_clear_chat()`, register `clear_chat` message handler |
| 6 | `web/src/hooks/useChat.ts` | Update `clearHistory` to send `clear_chat` to backend, add `/clear` slash command |

## Verification

1. **Bootstrap**: Start daemon, open web UI, start new chat → check logs for headless-lifecycle `on_before_agent` first-run init firing
2. **DB registration**: Verify session appears in sessions list with source=`claude_sdk`
3. **Context injection**: Verify agent receives skills context on first prompt (via SDK UserPromptSubmit hook → workflow → additional context)
4. **Progressive disclosure**: Verify `on_before_tool` enforcement — agent should call `list_mcp_servers()` first
5. **Compaction**: Long conversation → auto-compact → check `on_pre_compact` resets progressive disclosure variables → next prompt agent re-discovers tools
6. **/clear**: Type /clear in web chat or click trash icon → verify session summary generated → verify new conversation starts fresh
7. **Per-turn behavior**: Verify stop gates, memory recall, title synthesis all work across multiple turns
