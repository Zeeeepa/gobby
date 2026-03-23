# Plan: Multi-Provider Web Chat — Unified Session Interaction

**Task:** #10591
**Category:** Planning (comprehensive design)

## Context

Today the web UI has three disconnected surfaces for session interaction:

1. **SessionsTab** (Activity Panel) — shows active agents/CLI sessions with an inline transcript preview. Self-contained; no connection to the chat area. Read-only.
2. **TerminalsPage** (standalone page) — xterm.js terminal emulator for tmux sessions. Full interactive control. Being removed.
3. **Chat area** — web chat conversations. Can `viewSession` (REST transcript load) and `attachToSession` (WS subscription + `send_to_cli_session` injection) but these flows are only reachable from ConversationPicker or ActiveSessionsModal, not from the SessionsTab.

The result: you can *watch* a session in the activity panel, but you can't *interact* with it. You can interact via the chat area, but only if you find the session through the conversation picker. Terminal sessions require an entirely separate page.

**Goal:** Collapse these into one model. The **SessionsTab** becomes the session control surface. The **chat area** becomes the universal session viewport. Any session — web chat, terminal, SDK, API, any provider/model — renders as chat-style messages and can be swapped to/interacted with from the same surface.

---

## 1. The Interaction Model

Three modes, progressively escalating:

| Mode | What happens | Input bar | Destructive? | Works for |
|---|---|---|---|---|
| **View** | Load transcript via REST (static snapshot) | Hidden | No | All sessions |
| **Attach** | WS subscription for live events + input via `send_to_cli_session` | Enabled, labeled "Send to session" | No | Active sessions with terminal or hook injection |
| **Take Over** | Kill CLI process, create web chat session via resume strategy | Full web chat input | Yes (kills CLI) | Any session with resume capability |

**Swap = click a different session.** The chat area updates to show that session. Previous session detaches automatically.

---

## 2. SessionsTab Enhancement

**File:** `web/src/components/activity/SessionsTab.tsx`

### Current state
- Props: `{ projectId, onKillAgent, onExpireSession }`
- Clicking a session toggles an inline `MessageItem` preview within the panel
- No callbacks to the chat area

### Changes

**Add new callback props:**
```typescript
interface SessionsTabProps {
  projectId?: string | null
  onKillAgent?: (runId: string) => void
  onExpireSession?: (sessionId: string) => void
  // NEW:
  onViewSession?: (sessionId: string) => void
  onAttachSession?: (sessionId: string) => void
  onTakeOverSession?: (sessionId: string, projectId?: string) => void
}
```

**Replace inline message preview with session action buttons:**

When a session is selected, instead of showing messages inline in the panel, show:
- **"View"** button → calls `onViewSession(id)` → chat area loads transcript
- **"Attach"** button (if active + has terminal/hook) → calls `onAttachSession(id)` → chat area subscribes to live events + enables input
- **"Take Over"** button (if resumable) → confirmation dialog → calls `onTakeOverSession(id, projectId)` → chat area creates new web chat session
- Keep the **"Expire"** button for killing sessions

**Session capability indicators:**
- Show "Live" badge for active sessions (attachable)
- Show provider icon + model badge
- Highlight which session the chat area is currently viewing/attached to

**Wire into ChatPage:**
```typescript
// In ChatPage.tsx, pass callbacks to SessionsTab:
<SessionsTab
  onViewSession={viewSession}
  onAttachSession={attachToSession}
  onTakeOverSession={(id, pid) => continueSessionInChat(id, pid)}
  onKillAgent={handleKillAgent}
  onExpireSession={handleExpireSession}
/>
```

---

## 3. Chat Area as Universal Viewport

**File:** `web/src/hooks/useChat.ts`

### Current capabilities (already working)
- `viewSession(sessionId)` — REST transcript load, read-only (line 2154)
- `attachToSession(sessionId)` — WS subscription for live events (line 2298)
- `attachToViewed()` — upgrade from view to attached (line 2326)
- `detachFromSession()` — downgrade from attached to view (line 2334)
- `continueSessionInChat(sourceDbSessionId, projectId)` — takeover/resume (line 1701)
- `sendMessage()` — routes to `send_to_cli_session` when attached (line 1966-1984)
- `clearViewingSession()` — return to previous web chat (line 2241)

### Changes needed

**Interaction mode state:**
```typescript
type SessionInteractionMode = "chat" | "view" | "attached" | "takeover";

// Derived from existing state:
// - viewingSessionId && !attachedSessionId → "view"
// - attachedSessionId → "attached"
// - neither → "chat" (normal web chat)
// - takeover transitions from view/attached → "chat" (new web chat session)
```

This is mostly a **naming/UX layer** on top of existing primitives. The core state machine already exists:
- `viewingSessionId` (string | null)
- `attachedSessionId` (string | null)
- `viewingSessionMeta` / `attachedSessionMeta`

**Add to the return type:**
```typescript
interactionMode: SessionInteractionMode  // computed from existing state
activeSessionSource: string | null       // provider of viewed/attached session
canAttach: boolean                       // from attach_to_session_result
canTakeOver: boolean                     // from session resumability
```

**Input bar behavior** (in ChatInput or CommandBar):
- `mode === "view"` → input hidden or disabled, show "Viewing session #N" + "Attach" / "Take Over" buttons
- `mode === "attached"` → input enabled with "Send to #N" label, show "Detach" / "Take Over" buttons
- `mode === "chat"` → normal web chat input
- `mode === "takeover"` → same as "chat" (it becomes a web chat session)

---

## 4. Provider-Agnostic Resume (Backend)

**File:** `src/gobby/servers/websocket/session_control.py`

### Problem
`_handle_continue_in_chat()` (line 325) is Claude-specific:
- Resolves `sdk_resume_id` from `external_id` or `agent_runs` (Claude paths only)
- Non-Claude sessions get `resume_id = None` → fresh conversation with no history
- History injection was removed when `session_messages` table was dropped

### Solution: Resume Strategy Pattern

**New file:** `src/gobby/servers/chat_resume_strategy.py`

```python
class ResumeStrategy(Protocol):
    provider_name: str
    def can_native_resume(self, source_session) -> bool: ...
    async def resolve_resume_id(self, source_session, session_manager, agent_run_manager) -> str | None: ...
    async def kill_owner(self, source_session, session_manager) -> None: ...
    async def build_history_context(self, source_session, max_chars: int) -> str | None: ...
```

| Strategy | Providers | Resume method |
|---|---|---|
| `ClaudeResumeStrategy` | claude_code, claude_sdk_web_chat | SDK native via `ClaudeAgentOptions.resume` |
| `CodexResumeStrategy` | codex, codex_web_chat, cursor, windsurf, copilot | `CodexChatSession.resume_thread(thread_id)` |
| `GeminiResumeStrategy` | gemini, gemini_cli | Transcript injection (no native resume) |
| `LiteLLMResumeStrategy` | litellm, ollama, lmstudio, llama_cpp | Transcript injection (stateless API, no native resume) |
| `TranscriptResumeStrategy` | Any (fallback) | Parse JSONL via existing `TranscriptParser` subclasses |

**Registry:**
```python
def get_resume_strategy(source: str) -> ResumeStrategy:
    return RESUME_STRATEGIES.get(source, TranscriptResumeStrategy())
```

### Refactored `_handle_continue_in_chat()`:

```python
strategy = get_resume_strategy(source_session.source)
resume_id = await strategy.resolve_resume_id(...)
await strategy.kill_owner(...)
history_context = None if resume_id else await strategy.build_history_context(...)
session = await self._create_chat_session(
    conversation_id,
    resume_session_id=resume_id,
    history_context=history_context,
    provider_source=source_session.source,
)
```

### History Context Reconstruction

For non-native-resume providers, reconstruct from transcripts:

1. Look up `session.jsonl_path` → check archive at `~/.gobby/session_transcripts/`
2. Select parser based on `session.source` (existing parsers in `src/gobby/sessions/transcripts/`)
3. Extract last N turns → format as `<conversation-history>` XML block
4. Inject via `system_prompt_override` or new `history_context` param on `ChatSession.start()`

### Session type routing in `_create_chat_session()`

**File:** `src/gobby/servers/websocket/chat/_session.py`

Add source-based routing for resume scenarios:
- Claude sources → `ChatSession`
- Codex sources → `CodexChatSession`
- Gemini sources → `GeminiChatSession` wrapping `google-genai` SDK (Phase 5)
- LiteLLM sources (litellm, ollama, lmstudio, llama_cpp) → `LiteLLMChatSession` (Phase 6)

---

## 5. Backend: Attach Enrichment

**File:** `src/gobby/servers/websocket/handlers.py` (or wherever `attach_to_session` is handled)

When the frontend attaches to a session, the backend response should include capability info:

```python
{
    "type": "attach_to_session_result",
    "session_id": "...",
    # EXISTING:
    "ref": "#42",
    "source": "gemini_cli",
    "status": "active",
    # NEW:
    "can_interact": bool(session.terminal_context),  # has tmux for input injection
    "can_take_over": strategy.can_native_resume(session) or bool(session.jsonl_path),
    "resume_method": "sdk_native" | "thread_resume" | "history_injection" | "fresh",
    "provider": session.source,
    "model": session.model,
}
```

This lets the frontend show the right buttons without guessing.

---

## 6. Phased Implementation

### Phase 1: Wire SessionsTab → Chat Area (frontend only, 3 tasks)
1. Add `onViewSession`, `onAttachSession`, `onTakeOverSession` props to `SessionsTab`
2. Wire callbacks in `ChatPage.tsx` to `useChat` methods (`viewSession`, `attachToSession`, `continueSessionInChat`)
3. Replace inline message preview with action buttons + session capability indicators

### Phase 2: Chat Area Mode UX (frontend, 3 tasks)
4. Add computed `interactionMode` to `useChat.ts` return value
5. Update `ChatInput` / `CommandBar` — mode-specific input bar (hidden for view, "Send to #N" for attached, normal for chat)
6. Add mode transition buttons in CommandBar (Attach / Detach / Take Over / Back to Chat)

### Phase 3: Resume Strategy Pattern (backend, 4 tasks)
7. Create `chat_resume_strategy.py` — protocol + `ClaudeResumeStrategy` (extract from `session_control.py:325-490`)
8. Create `CodexResumeStrategy` — wire `CodexChatSession.resume_thread()` into resume flow
9. Create `TranscriptResumeStrategy` — generic history injection using existing transcript parsers
10. Refactor `_handle_continue_in_chat()` to use strategy dispatch

### Phase 4: Attach Enrichment (backend + frontend, 2 tasks)
11. Enrich `attach_to_session_result` with `can_interact`, `can_take_over`, `resume_method`, `provider`
12. Frontend reads capabilities and conditionally shows Attach / Take Over buttons

### Phase 5: Gemini Web Chat (3 tasks)
13. Create `GeminiChatSession` implementing `ChatSessionProtocol` — wraps `google-genai` SDK with streaming chat (`generate_content_stream`), native tool calling, and Gemini-specific features (grounding, code execution). Manages conversation history as Gemini `Content` objects.
14. Create `GeminiResumeStrategy` — parse native Gemini session JSON (`~/.gemini/tmp/{hash}/chats/session-*.json`) via `GeminiTranscriptParser.parse_session_json()`, reconstruct as Gemini `Content` history for seamless resume on the same model.
15. Extend `_create_chat_session()` with gemini provider routing — gemini sources create `GeminiChatSession` with the original model.

### Phase 6: LiteLLM / Local Model Web Chat (3 tasks)
16. Create `LiteLLMChatSession` implementing `ChatSessionProtocol` — wraps `litellm.acompletion(stream=True)` for streaming chat. OpenAI-compatible protocol works with LM Studio, Ollama, llama.cpp, and any OpenAI-compatible endpoint. Manages conversation history in-memory (stateless API). Supports tool calling via LiteLLM's function calling abstraction.
17. Create `LiteLLMResumeStrategy` — transcript injection only (stateless API, no native resume). Uses existing transcript parsers.
18. Extend `_create_chat_session()` with litellm provider routing + model selection UI. Config reads from `llm_providers.litellm.models` (already exists in `DaemonConfig`) and local endpoint discovery (Ollama `http://localhost:11434/api/tags`, LM Studio `http://localhost:1234/v1/models`).

### Phase 7: Cleanup (2 tasks)
19. Remove standalone Sessions page (`web/src/components/sessions/`) and its nav entry
20. Remove standalone Terminals page (`web/src/components/terminals/TerminalsPage.tsx`) and its nav entry

---

## 7. Key Design Decisions

1. **SessionsTab is the control surface, chat area is the viewport.** SessionsTab gets action callbacks; chat area renders whatever session is selected. Clean separation of navigation from display.

2. **Three existing `useChat` primitives are sufficient.** `viewSession` / `attachToSession` / `continueSessionInChat` already implement view / attach / takeover. No new WebSocket message types needed for Phase 1-2. Just need to wire them to SessionsTab and add UX polish.

3. **Strategy pattern for resume.** Keeps provider-specific logic out of the 165-line `_handle_continue_in_chat()`. Easy to add providers.

4. **Transcript-based history for non-native-resume.** Parsers already exist for all providers in `src/gobby/sessions/transcripts/`. No new DB tables needed.

5. **Gemini gets a dedicated `GeminiChatSession` (Phase 5).** Wraps `google-genai` SDK directly for full control over Gemini-specific features (grounding, code execution, native tool use). Resuming a Gemini session keeps you on Gemini — provider agnostic means staying on the same provider, not funneling through Claude.

6. **No database changes.** Existing `sessions` table has `source`, `external_id`, `jsonl_path`, `terminal_context`, `parent_session_id` — everything needed.

7. **LiteLLM for local models.** Rather than separate Ollama/LM Studio/llama.cpp integrations, use LiteLLM as the universal adapter. It already speaks all their protocols via model prefixes (`ollama/llama3`, `openai/lm-studio-model`, etc.). The existing `LiteLLMProvider` handles config and API key management; `LiteLLMChatSession` adds the interactive streaming layer on top.

---

## 8. Messaging Architecture (for reference)

Three message delivery mechanisms exist, each at a different layer:

| Mechanism | Path | Used by | Terminal injection? |
|---|---|---|---|
| `send_to_cli_session` (WS) | tmux `send-keys` (idle) or DB + hook piggyback (mid-exec) | Web UI (`useChat.ts:1980`) | Yes |
| `send_message` (MCP, gobby-agents) | DB + hook piggyback only | Agents messaging other agents | No |
| `terminal_input` (WS) | Raw keystrokes to tmux PTY bridge | Terminals page xterm.js | Yes (raw) |

For web UI session interaction, `send_to_cli_session` is the right tool — it already handles both the "idle at prompt" (tmux) and "mid-execution" (hook) cases. No new messaging infrastructure needed.

Related future work: An MCP tool wrapping the tmux `send-keys` path so agents can also inject terminal commands into other sessions (separate task).

---

## 9. Critical Files

| File | Changes |
|---|---|
| `web/src/components/activity/SessionsTab.tsx` | Add action callbacks, replace inline preview with buttons, show capability indicators |
| `web/src/components/chat/ChatPage.tsx` | Wire SessionsTab callbacks to useChat methods |
| `web/src/hooks/useChat.ts` | Add computed `interactionMode`, expose `canAttach`/`canTakeOver` from attach result |
| `web/src/components/chat/CommandBar.tsx` | Mode-specific buttons (Attach/Detach/Take Over/Back) |
| `web/src/components/chat/ChatInput.tsx` | Mode-specific input bar behavior |
| `src/gobby/servers/chat_resume_strategy.py` | NEW — ResumeStrategy protocol + per-provider implementations |
| `src/gobby/servers/websocket/session_control.py` | Refactor `_handle_continue_in_chat()` to use strategy dispatch |
| `src/gobby/servers/websocket/chat/_session.py` | Add source-based session type routing for resume |
| `src/gobby/servers/chat_session.py` | Add `history_context` support in `start()` |
| `src/gobby/servers/gemini_chat_session.py` | NEW — `GeminiChatSession` implementing `ChatSessionProtocol` via `google-genai` SDK |
| `src/gobby/servers/litellm_chat_session.py` | NEW — `LiteLLMChatSession` implementing `ChatSessionProtocol` via `litellm.acompletion(stream=True)` |
| `src/gobby/llm/litellm.py` | Existing `LiteLLMProvider` — reuse config/API key management for `LiteLLMChatSession` |
| `src/gobby/sessions/transcripts/` | Existing parsers reused for history reconstruction |

## 10. Verification

- **Phase 1-2:** Open web UI → Sessions tab shows active agents/CLI sessions → click "View" → chat area loads transcript → click "Attach" → input bar enables with "Send to #N" → type message → delivered via `send_to_cli_session` → click "Take Over" → confirmation → new web chat session created
- **Phase 3:** Resume a Codex session → verify `resume_thread()` called with thread ID. Resume a Gemini session → verify transcript parsed and injected as history context.
- **Phase 4:** Attach to session → verify response includes `can_interact`, `can_take_over`, `resume_method` → frontend conditionally shows buttons
- **Swap test:** View session A → click session B in SessionsTab → chat area auto-detaches from A, loads B
- **LiteLLM test:** Configure `llm_providers.litellm.models` with an Ollama model → start web chat → verify `LiteLLMChatSession` streams responses via `acompletion(stream=True)` → verify tool calls work
- **Local model test:** Start Ollama/LM Studio → web chat auto-discovers available models → select one → chat works
- **Provider agnostic:** Repeat all above for Claude, Gemini, Codex, LiteLLM/local, and terminal sessions
