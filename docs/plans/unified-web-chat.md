# Unified Web Chat Plan

## Context

Provider purge (Cursor/Windsurf/Copilot/Antigravity removal) is done. SDK headless calls (title synthesis, session summaries) work fine and stay as-is. Focus: **one web chat interface, three CLIs, provider-switchable, with local LLM support**.

**Strategy:** Add `provider` field to the existing `useChat` hook and `chat_message` WS payload. Backend routes based on it. Default (no provider) = existing SDK path. Explicit provider = new CLI path. Side-by-side testing with zero frontend duplication.

**Prior attempt failed** — the branch that had `stream_json_parser.py`, `ClaudeCLI`, and `CLIChatSession` was rejected. All code in this plan is written fresh. The prior commits serve only as conceptual reference for what the final shape should look like, not as code to cherry-pick.

---

## Phase 0: Cleanup + Source Identity Migration

**Goal:** Clean house first. Remove old Codex web chat implementation, normalize source identity, make `session_type` first-class everywhere. `ChatSession` (SDK-backed) stays as default fallback during build.

### Remove old Codex web chat (Finding R8 — must be atomic)
Phase 0 deletes `codex_chat_session.py` but the websocket and lifecycle code still imports and branches on it. **All of the following must land in the same change** to keep the tree compilable:
- Delete `src/gobby/servers/codex_chat_session.py`
- Delete `src/gobby/servers/codex_chat_session_permissions.py` (if exists)
- Remove Codex branch from `_create_chat_session_inner` in `src/gobby/servers/websocket/chat/_session.py` (the `use_codex` path)
- Remove `CodexChatSession` imports from `_session.py`, `_lifecycle.py`, `_messaging.py`, and anywhere else that references it
- Remove `isinstance(session, CodexChatSession)` checks in `_lifecycle.py`
- Update or remove Codex-specific test files that import the deleted module
- Web chat temporarily Claude-only until Phase 2 (CLIChatSession) and Phase 3 (Gemini + Codex) land

### Source identity migration (schema)
- `src/gobby/storage/migrations.py` — Add migration:
  ```sql
  ALTER TABLE sessions ADD COLUMN session_type TEXT NOT NULL DEFAULT 'terminal';
  UPDATE sessions SET session_type = 'web_chat' WHERE source LIKE '%web_chat%';
  UPDATE sessions SET source = 'claude' WHERE source IN ('claude_sdk', 'claude_sdk_web_chat');
  UPDATE sessions SET source = 'codex' WHERE source = 'codex_web_chat';
  DROP INDEX idx_sessions_unique;
  CREATE UNIQUE INDEX idx_sessions_unique ON sessions(external_id, machine_id, source, project_id, session_type);
  ```
- `src/gobby/storage/baseline_schema.sql` — Add `session_type` to sessions DDL + update unique index to include `session_type`

### Session uniqueness fix (Finding #1)
Current unique index is `(external_id, machine_id, source, project_id)`. Once source becomes bare provider, web and terminal sessions can collide. **Add `session_type` to the unique index and all lookup helpers:**
- `src/gobby/storage/sessions.py:48,70,186,204` — `find_by_external_id()` and `register()` must accept and filter by `session_type`
- `src/gobby/storage/baseline_schema.sql:222` — Unique index includes `session_type`

### Enum cleanup
- `src/gobby/hooks/events.py` — Remove `CLAUDE_SDK`, `CLAUDE_SDK_WEB_CHAT`, `CODEX_WEB_CHAT` from `SessionSource`. Only `CLAUDE`, `GEMINI`, `CODEX` remain.

### Session model
- `src/gobby/storage/session_models.py` — Add `session_type: str = "terminal"` to Session + `from_row`/`to_dict`/`to_brief`
- `src/gobby/storage/sessions.py` — Accept `session_type` in `register()`. Leave `find_pending_plans()` and `pending_plan_path` as-is in Phase 0 (transitional — eliminated in Phase 2 when `PendingInteractionManager` replaces them). **No new code may depend on `find_pending_plans()` or `pending_plan_path` after Phase 0.**

### Backend callsite migration
- `src/gobby/servers/websocket/chat/_session.py:210,333,434` — Use bare `"claude"`, pass `session_type="web_chat"`
- `src/gobby/servers/websocket/chat/_lifecycle.py:24,239` — Replace `isinstance` source detection with provider attribute on session
- `src/gobby/servers/chat_session.py` — `GOBBY_SOURCE` env → `"claude"`
- `src/gobby/servers/routes/mcp/hooks.py:120-141` — Remove `claude_sdk`/`claude_sdk_web_chat` branches

### Frontend source migration (Finding #2)
These files hardcode old source strings for filtering, labeling, and icons:
- `web/src/App.tsx:499,590` — `claude_sdk_web_chat` filter → use `session_type === 'web_chat'`
- `web/src/hooks/useSessions.ts:36` — source filter → `session_type`
- `web/src/components/shared/SourceIcon.tsx:1,7,45` — Remove `claude_sdk_web_chat` type/color/case, use bare `claude`
- `web/src/components/chat/ResumeSessionModal.tsx:7,19` — Remove `claude_sdk_web_chat` label/color
- `web/src/components/sessions/SessionSidebar.tsx:32,42,62,63,206` — Web/CLI split → filter by `session_type` not `source`
- `web/src/components/sessions/SessionsPage.tsx:24` — Source label → use `session_type`
- `web/src/components/sessions/SessionDetail.tsx:237,250` — Terminal detection → use `session_type === 'terminal'`
- `web/src/components/dashboard/SessionsCard.tsx:10,22` — Remove `claude_sdk_web_chat`
- `web/src/components/dashboard/UsageCard.tsx:21` — Remove `claude_sdk_web_chat`
- `web/src/components/tasks/SessionViewer.tsx:59` — Remove `claude_sdk_web_chat`

**Key design:** Frontend uses `session_type` for web-vs-terminal distinction, `source` for provider identity. `session_type='web_chat'` means "originated in web chat", not "only visible in web chat" — any session can be displayed in the main chat panel.

### Agent/skill source migration (Finding #3)
- `src/gobby/install/shared/workflows/agents/default-web-chat.yaml:3` — `sources: [claude_sdk_web_chat]` → `sources: [claude, gemini, codex]`
- `src/gobby/install/shared/skills/canvas/SKILL.md:10` — `sources: [claude_sdk_web_chat, gemini_sdk_web_chat]` → `sources: [claude, gemini, codex]`
- `src/gobby/skills/injector.py:215-216` — Source matching now uses bare provider names. Verify matching logic works with new values.
- `src/gobby/hooks/event_handlers/_session_start.py:75` — Verify source-sensitive logic works with bare providers
- `src/gobby/workflows/agent_resolver.py:23` — Verify resolver works with bare provider as `cli_source`

### REST API — expose session_type (Finding #9)
- Session REST serialization must include `session_type` so frontend can filter/distinguish
- `src/gobby/servers/routes/sessions.py` (or wherever session REST lives) — include `session_type` in response
- `web/src/types/` — Add `session_type` to GobbySession type
- `web/src/hooks/useSessions.ts` — Use `session_type` for web/terminal filtering

### Tests
- ~18 test files reference old source values → update all
- Remove Codex web chat tests
- Frontend tests referencing old source strings

**Verification:** `grep -r 'claude_sdk_web_chat\|codex_web_chat\|claude_sdk' src/ web/src/` returns zero hits. `SessionSource` has exactly 3 values. `codex_chat_session.py` deleted. Session uniqueness index includes `session_type`.

---

## Phase 1: ClaudeCLI Launcher + Stream Parser

**Goal:** Build CLI subprocess infrastructure for multi-turn web chat.

### Stream parser (new)
- `src/gobby/llm/stream_json_parser.py` (~200 lines) — Parse Claude's `--output-format stream-json` NDJSON output. StreamEvent hierarchy (InitEvent, ContentBlockDelta, MessageDelta, CompletionEvent, RateLimitEvent), async stream iterator over `asyncio.StreamReader`.

### ClaudeCLI session launcher (new)
- `src/gobby/llm/claude_cli.py` — Extend existing file (currently has `find_cli_path()` + `verify_cli_path()`) with:
  - `ClaudeCLI` class with `session()` method only (no `query()` — headless calls stay on SDK)
  - `ClaudeCLI.session()` spawns `claude --output-format stream-json --verbose --input-format stream-json --session-id <id>`
  - `CLISession` class: `send()`, `stream()`, `interrupt()`, `stop()`

### Hook timeout bump
- `src/gobby/install/shared/hooks/hook_dispatcher.py:716` — httpx async path: Change `timeout=90.0` to `httpx.Timeout(10.0, read=600.0)` (keeps short connect timeout, allows 600s read for hold-open approvals)
- `src/gobby/install/shared/hooks/hook_dispatcher.py:688` — curl fire-and-forget path: Change `--max-time 90` to `--max-time 600`. Only used for `SessionEnd` (not approval-bearing), but should match for consistency.

### Verified CLI streaming schemas (April 2026)

**Claude** (`--output-format stream-json --verbose` + `--input-format stream-json` for multi-turn):
```
system/init → system/hook_* → assistant{content:[{type:"thinking"|"text"|"tool_use"}]} → rate_limit_event → result
```

**Gemini** (`--output-format stream-json` for single-turn, `--acp` for multi-turn):
```
init → message(role:user) → message(role:assistant,delta:true) → result{stats}
```

**Codex** (app-server `item/agentMessage/delta` for streaming, `exec --json` only gives `item.completed`):
```
thread.started → turn.started → item/agentMessage/delta → item.completed → turn.completed{usage}
```

Each CLI needs its own NDJSON normalizer → common `ChatEvent` types.

**Verification:** Unit tests for each normalizer with captured sample NDJSON. Unit tests for CLISession with mocked subprocess.

---

## Phase 2: CLIChatSession + Permission Gate

**Goal:** New `ChatSessionProtocol` implementation backed by `ClaudeCLI.session()`, with unified approval model. Runs parallel to existing SDK-backed `ChatSession`.

### Key architectural insight

With SDK: lifecycle events are in-process callbacks (`_on_pre_tool`, `_on_post_tool`).
With CLI subprocess: hooks fire via `hook_dispatcher.py` → HTTP POST to `/api/hooks/execute`. **The daemon already handles these** through the existing adapter/lifecycle pipeline. `CLIChatSession` does NOT wire `_on_pre_tool` etc. — those events arrive via HTTP naturally.

The only new thing: **hold-open pattern for approvals**. When CLI fires `PreToolUse` for a gated tool, the hook endpoint holds the HTTP response until the user acts in the web UI.

### New: CLIChatSession
- `src/gobby/servers/cli_chat_session.py` (~300 lines) — Fresh implementation:
  - `provider` attribute for lifecycle source detection
  - `start()`: resolve CLI path, spawn `ClaudeCLI.session()`
  - `send_message()`: write to stdin, parse NDJSON → yield `ChatEvent`
  - Local LLM: pass `ANTHROPIC_BASE_URL` in subprocess env when configured
  - Note: approval resolution lives in `PendingInteractionManager`, not in this class

### Unified pending interactions model (Findings #4, #5)

Replace the bifurcated approval state (`pending_plan_path` column + in-memory `asyncio.Event` in `chat_session_permissions.py`) with a single durable `pending_interactions` table and a process-local coordinator.

#### Schema

```sql
CREATE TABLE pending_interactions (
    id TEXT PRIMARY KEY,              -- durable request ID
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,               -- 'tool', 'plan', 'ask_user'
    provider TEXT NOT NULL,           -- 'claude', 'gemini', 'codex'
    tool_name TEXT,
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',  -- 'pending', 'resolved', 'expired'
    decision TEXT,                    -- 'approve', 'reject', 'approve_always'
    response_json TEXT,
    timeout_seconds INTEGER NOT NULL DEFAULT 300,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    resolved_at TEXT
);
CREATE INDEX idx_pending_interactions_session ON pending_interactions(session_id, status);
```

#### PendingInteractionManager (Finding R1)

New component: `src/gobby/servers/pending_interactions.py` (~150 lines)

Owns DB rows + in-memory waiters + timeout cleanup. Single process-local instance on `app.state`.

```python
class PendingInteractionManager:
    """Coordinates durable pending interactions with in-memory waiters."""

    _waiters: dict[str, asyncio.Event]  # keyed by interaction_id
    _timeouts: dict[str, asyncio.Task]  # timeout tasks per interaction_id

    async def create(self, session_id, kind, provider, payload, timeout_seconds=300) -> str:
        """Insert DB row, create asyncio.Event, start timeout task. Returns interaction_id."""

    async def wait(self, interaction_id) -> dict:
        """Block until resolved or timeout. Returns decision + response."""

    async def resolve(self, interaction_id, decision, response=None) -> bool:
        """Set decision, wake waiter, update DB. Returns False if expired/missing."""

    async def expire(self, interaction_id) -> None:
        """Mark expired in DB, wake waiter with timeout decision."""

    async def rebroadcast(self, session_id) -> list[dict]:
        """Return all pending (non-expired, non-resolved) interactions for session.
        Scoped by db_session_id. Only latest non-expired per (session_id, kind) returned."""

    async def cleanup(self) -> None:
        """Cancel all timeout tasks. Called on daemon shutdown."""

    async def supersede(self, session_id, kind) -> None:
        """Expire any existing pending interaction of same (session_id, kind)."""
```

**Supersession:** Before creating a new interaction, `supersede()` expires any existing one of the same `(session_id, kind)`.

**Daemon restart:** All pending rows marked expired on startup (fail-closed). Sessions get "approval lost, please retry" on next hook.

#### WS message schemas (Finding R2)

Lock exact shapes for all interaction messages:

**Server → Client:**
```typescript
// Pending tool approval
{ type: "pending_interaction", interaction_id: string, kind: "tool",
  session_id: string, tool_name: string, arguments: object, server_name?: string }

// Pending ask-user question
{ type: "pending_interaction", interaction_id: string, kind: "ask_user",
  session_id: string, question: string, tool_call_id: string }

// Pending plan approval
{ type: "pending_interaction", interaction_id: string, kind: "plan",
  session_id: string, plan_path: string, plan_content?: string }

// Interaction resolved (confirmation back to frontend)
{ type: "interaction_resolved", interaction_id: string, decision: string }

// Interaction expired (timeout notification)
{ type: "interaction_expired", interaction_id: string, kind: string }
```

**Client → Server:**
```typescript
// Resolve tool approval
{ type: "resolve_interaction", interaction_id: string,
  decision: "approve" | "reject" | "approve_always" }

// Resolve ask-user question
{ type: "resolve_interaction", interaction_id: string,
  decision: "answer", response: { answers: Record<string, string> } }

// Resolve plan approval
{ type: "resolve_interaction", interaction_id: string,
  decision: "approve" | "reject", feedback?: string }
```

**Reconnect rebroadcast:** On WS reconnect, server calls `manager.rebroadcast(db_session_id)` and sends all pending interactions. Scoped by `db_session_id` (the Gobby session, not conversation_id). Only latest non-expired per `(session_id, kind)` is sent.

#### Migration path for plan approvals
- Remove `pending_plan_path` column from sessions table
- Remove `find_pending_plans()` from `src/gobby/storage/sessions.py`
- Refactor `src/gobby/servers/websocket/handlers/plan_approval.py` to use `PendingInteractionManager`
- Plan file path stored in `payload_json`, approval state in `pending_interactions`

### ChatSessionProtocol revision (Finding R3)

The current protocol assumes SDK-style in-process pending state (`provide_answer()`, `provide_approval()`, `provide_plan_decision()`). For CLI-backed sessions, approval resolution lives in `PendingInteractionManager`, not in the session object.

**Decision:** Move approval resolution outside the session. Protocol becomes minimal. **Blast radius:** every protocol consumer and test that currently calls `has_pending_*` or `provide_*` must be updated:
- `start()`, `send_message()`, `interrupt()`, `stop()`, `switch_model()` — session lifecycle only
- `provider: str` attribute — required on all implementations
- Remove: `provide_answer()`, `provide_approval()`, `provide_plan_decision()`, `has_pending_question`, `has_pending_approval`, `has_pending_plan`
- `ChatSession` (SDK fallback) wraps the old methods internally during transition but doesn't expose them via protocol
- `_messaging.py` routes all approval responses through `PendingInteractionManager.resolve()`, not through session methods
- **Files affected by protocol change:** `chat_session_base.py`, `chat_session.py`, `chat_session_permissions.py`, `_messaging.py` (approval handlers), `_session.py` (callback wiring), plus tests in `tests/servers/` that mock `provide_*` or assert `has_pending_*`

### Permission gate (hold-open)
- `src/gobby/servers/routes/mcp/hooks.py` — Extend `execute_hook()`:
  1. Check `session_type` via `X-Gobby-Session-Id` header → DB lookup
  2. **`session_type == 'web_chat'`**: For `PreToolUse` on gated tools → `PendingInteractionManager.create()` + `wait()`. Hold HTTP response until resolved or timeout. Return decision in hook response. `AskUserQuestion`: same hold-open, return answer in `additionalContext`.
  3. **`session_type == 'terminal'`**: Existing adapter path, no hold-open, no persistence. Terminal hooks process and return immediately as today.

### Provider routing (backend)
- `src/gobby/servers/websocket/chat/_session.py` — `_create_chat_session_inner` reads `provider` parameter:
  ```python
  match provider:
      case "claude":
          session = CLIChatSession(conversation_id=conversation_id)
      case "codex":
          session = CodexCLIChatSession(conversation_id=conversation_id)
      case "gemini":
          session = GeminiCLIChatSession(conversation_id=conversation_id)
      case _:
          # Default: existing SDK path (backwards compat during transition)
          session = ChatSession(conversation_id=conversation_id)
  ```
  All CLI-backed sessions receive lifecycle events via HTTP hooks — no in-process callback wiring. The `_on_pre_tool` etc. callbacks only wire for the legacy `ChatSession` fallback during transition.
- `src/gobby/servers/websocket/chat/_messaging.py` — Read `provider` from `chat_message` payload, pass through to session creation. Approval responses now target `interaction_id`.

### Provider precedence (Finding #6)

Explicit rules for which provider wins when multiple sources of truth exist:

1. **Explicit UI provider** (from `chat_message.provider`) — highest priority
2. **Agent definition provider** (from resolved agent body's `provider` field) — if no explicit UI choice
3. **Resumed/continued session's source** (from DB `source` column on the session being resumed) — preserves original provider on resume
4. **Default fallback** — `None` (existing SDK `ChatSession` path during transition)

Defined in `_create_chat_session_inner`. When switching provider mid-conversation, a new session is created (the old one stays alive in background).

### Provider selection (frontend) — same useChat hook (Phase 2)
- `web/src/hooks/useChat.ts`:
  - Add `provider` state + `setProvider` callback
  - Include `provider` in `chat_message` payload (line ~2227) when set
  - Expose `provider`, `setProvider` in return value
- `web/src/types/chat.ts` — Add `provider?: string` and `onProviderChange?: (p: string) => void` to `ChatState`
- `web/src/components/chat/ChatPage.tsx` — Provider picker UI (dropdown/segmented control in header bar or command bar)

### Reconnect semantics (Finding R5)

On WS reconnect:
1. Client sends `conversation_id` in reconnect handshake
2. Server looks up `db_session_id` from `conversation_id` mapping
3. `PendingInteractionManager.rebroadcast(db_session_id)` returns latest non-expired per `(session_id, kind)`
4. Server sends each as `pending_interaction` WS message
5. If user switched providers and has background sessions, only the **active conversation's** pending interactions are rebroadcast — background sessions' interactions timed out when they lost their WS listener

Replaces hardcoded `find_pending_plans()` source filter and `pending_plan_path` column.

**Verification:**
1. No provider selected → existing SDK path, everything works as before
2. Select "Claude" provider → CLIChatSession, streaming text works
3. Hold-open: PreToolUse fires → pending interaction in UI → approve by interaction_id → hook returns → CLI proceeds
4. Plan approval via `pending_interactions` (not `pending_plan_path`) — approve, request changes, reconnect rebroadcast
5. Timeout: expires → auto-deny
6. Reconnect: WS drops + reconnects → all pending interactions rebroadcast

---

## Phase 3: Gemini + Codex Web Chat

**Goal:** All three CLIs get the same treatment. CodexChatSession (app-server) is replaced.

### Gemini (ACP)
- `src/gobby/servers/gemini_cli_chat_session.py` (~300 lines) — Implements `ChatSessionProtocol` wrapping `gemini --acp` subprocess. ACP provides bidirectional JSON-RPC over stdio.
- `src/gobby/adapters/gemini_acp_client.py` (~250 lines) — ACP protocol client (subprocess lifecycle, JSON-RPC messaging, async event streaming)

### Codex (app-server protocol, fresh session implementation)
- `src/gobby/servers/codex_cli_chat_session.py` (~300 lines) — Fresh `ChatSessionProtocol` implementation using `CodexAppServerClient` (app-server JSON-RPC). The app-server provides streaming deltas via `item/agentMessage/delta`, unlike `exec --json` which only gives `item.completed`. `CodexAppServerClient` infrastructure is solid — the chat session wrapper is what gets rewritten.

### Provider-specific resume capability (Finding #7 — PROVISIONAL)

Resume capabilities are **asserted, not verified in this codebase**. Phase 3 must verify actual CLI/app-server resume behavior before relying on it. If provider-native resume is missing or partial, fallback is observable-only or history injection.

| Provider | Resume mechanism (claimed) | `external_id` meaning | Status |
|---|---|---|---|
| Claude | `--session-id <id>` / `--resume <id>` | Claude native session UUID | **Verified** — works in CLI |
| Gemini | `--resume <id>` | Gemini session ID | **Provisional** — verify in Phase 3 |
| Codex | `resume <thread_id>` / `--last` | Codex thread UUID | **Provisional** — verify app-server thread reuse in Phase 3 |

- `src/gobby/servers/websocket/handlers/session_observe.py` — `continue_in_chat` currently assumes Claude SDK/native-resume behavior. Must dispatch to provider-specific resume logic.
- Sessions where resume isn't verified are observable but not continuable until verified.

### Wire into routing
- `src/gobby/servers/websocket/chat/_session.py` — `"gemini"` and `"codex"` branches already stubbed in Phase 2

### Cleanup
- `src/gobby/adapters/codex_impl/client.py` — CodexAppServerClient stays during development; after Phase 3 verification, audit for dead code and clean up
- `src/gobby/sessions/transcripts/gemini.py` (or wherever old Gemini parser lives) — old Gemini transcript parser becomes dead code after ACP implementation, clean up post-verification

**Verification:** Select Gemini → streaming response. Select Codex → streaming response. Resume works per provider. All three providers work through the same pattern.

---

## Phase 4: Session Switching + Provider Picker Polish

**Goal:** Switch providers mid-conversation, observe terminal sessions, local LLM.

### Provider endpoint
- `src/gobby/servers/routes/providers.py` (new) — `GET /api/providers`: available CLIs (`shutil.which()`), local LLM config
- `src/gobby/servers/app_factory.py` — Register route

### Session switching canonical model (Finding R6)

Three distinct UI states already exist in useChat. Define how provider switching interacts:

| State | Meaning | Mutable? |
|---|---|---|
| **Active conversation** (`conversationId`) | The web-chat session the user is driving. Read-write. | Yes — provider switch creates new session, old moves to background |
| **Viewed session** (`viewingSessionId`) | Read-only observation of a terminal session via REST polling | Yes — cleared on switch, or kept if user explicitly set it |
| **Attached session** (`attachedSessionId`) | Bidirectional WS subscription to a terminal session | Yes — detached on provider switch |

`switch_provider` behavior:
1. Stop streaming on active conversation (don't kill subprocess — it stays alive)
2. Detach from any attached session
3. Create new active conversation with new provider
4. Old conversation moves to background (visible in activity panel, times out per daemon policy)
5. Viewed session state is preserved (independent of active conversation)

- `web/src/hooks/useChat.ts` — `switchProvider` function implements above
- `src/gobby/servers/websocket/chat/_messaging.py` — Handle `switch_provider` WS message

### Local LLM
- `provider == "claude"` + local endpoint configured → `CLIChatSession` passes `ANTHROPIC_BASE_URL` in subprocess env

### Terminal session observation
- Already partially wired (viewSession/attachToSession in useChat). Extend to stream via `ChatEvent` in web UI.
- `session_type` enables proper distinction: terminal sessions are observable, web_chat sessions are controllable

---

## Phase 5: Agent Spawning Unification (deferrable)

- `src/gobby/agents/spawners/command_builder.py` — Consolidate into single `build_cli_command()`
- Delete preflight functions from `spawn.py`
- Delete `capture_codex_session_id()` from `codex_session.py`

---

## Invariants

These are design constraints that must hold throughout implementation:

1. **One active web-chat session per conversation.** A `conversation_id` maps to exactly one active CLI subprocess at a time. Provider switching creates a new session.
2. **One outstanding blocking interaction per session per kind.** Claude CLI blocks on one tool approval, one AskUserQuestion, or one plan approval at a time. Supersession is safe per `(session_id, kind)`.
3. **Switching provider abandons unresolved interactions in the old active conversation.** This is intentional. Pending approvals in the background session expire via timeout. The user must re-trigger them if they switch back.
4. **Terminal sessions stay on the tmux/piggyback messaging path even when shown in the main panel.** `session_type` means origin, not current display location. A terminal session viewed in the main panel uses the existing tmux message injection path (via `send_to_cli_session`), never `resolve_interaction`.
5. **Reconnect source of truth:** Active web chat reconnect resolves through the in-memory session registry (keyed by `conversation_id`) if present. If the session was evicted from memory (daemon restart), falls back to DB session metadata via `external_id` lookup.
6. **Web chat `external_id` == `conversation_id`.** Web-chat sessions use the frontend's `conversation_id` as `external_id` in the DB. This is the reconnect fallback lookup key.

### Supersession rules

| Kind | Supersession scope | Rationale |
|---|---|---|
| `tool` | `(session_id, kind)` | CLI blocks on one tool approval at a time |
| `plan` | `(session_id, kind)` | One plan review at a time |
| `ask_user` | `(session_id, kind)` | CLI blocks on one AskUserQuestion at a time |

All three providers guarantee single-outstanding-blocking per kind. If a provider ever allows multiple concurrent questions (none currently do), this would need to change to per-interaction-id tracking instead of supersession.

---

## Execution Order

```
Phase 0 (Cleanup + Source Identity)  ← clean house first
    │
    v
Phase 1 (ClaudeCLI + StreamParser)   ← infrastructure
    │
    v
Phase 2 (CLIChatSession + Unified Pending Interactions + frontend provider) ← Claude web chat on CLI
    │
    ├──────────────┐
    v              v
Phase 3          Phase 4            ← parallel after Phase 2
(Gemini+Codex)   (Switching)
    │              │
    └──────┬───────┘
           v
       Phase 5 (deferrable)
```

## Risks — Investigated and Resolved

1. **Hold-open hook pattern: SAFE.** Uvicorn has no response timeout. FastAPI `async def` endpoints can await indefinitely. Fix: httpx async path (`timeout=90.0` → `Timeout(10.0, read=600.0)`) and curl fire-and-forget path (`--max-time 90` → `--max-time 600`). No spike needed.
2. **Stream parser: COMPLETE schema.** Captured real CLI stream-json output for all three providers. Multi-turn via `--input-format stream-json` (Claude) and `--acp` (Gemini).
3. **Codex: REPLACED.** Fresh implementation over `CodexAppServerClient` (streaming deltas via `item/agentMessage/delta`).
4. **Session uniqueness: ADDRESSED.** `session_type` added to unique index and all lookup helpers.
5. **Approval model: UNIFIED.** `PendingInteractionManager` owns DB rows + in-memory waiters + timeout cleanup. WS schemas locked. `pending_plan_path` eliminated.
6. **Protocol: REVISED.** `ChatSessionProtocol` simplified to lifecycle only. Approval resolution lives in `PendingInteractionManager`.
7. **Frontend: COMPREHENSIVE.** 12+ frontend files with old source strings identified. `session_type` in REST + frontend types.
8. **Resume: PROVISIONAL.** Claude verified, Gemini/Codex pending Phase 3 verification.

## Critical Files

| File | Phases | Role |
|------|--------|------|
| `src/gobby/servers/websocket/chat/_session.py` | 0,2,3 | Provider routing hub |
| `src/gobby/servers/websocket/chat/_messaging.py` | 2,4 | WS message handling, provider passthrough, interaction_id responses |
| `src/gobby/servers/routes/mcp/hooks.py` | 0,2 | Hold-open approval gate |
| `src/gobby/hooks/events.py` | 0 | SessionSource cleanup |
| `src/gobby/storage/sessions.py` | 0 | Unique index, session_type in lookups |
| `src/gobby/storage/session_models.py` | 0 | session_type in model + serialization |
| `src/gobby/llm/claude_cli.py` | 1 | CLI subprocess management |
| `src/gobby/llm/stream_json_parser.py` | 1 | NDJSON → StreamEvent |
| `src/gobby/servers/cli_chat_session.py` | 2 | Claude web chat on CLI |
| `src/gobby/servers/pending_interactions.py` | 2 | PendingInteractionManager — owns approval lifecycle |
| `src/gobby/servers/chat_session_base.py` | 2 | ChatSessionProtocol revision — lifecycle only |
| `src/gobby/storage/migrations.py` | 0,2 | session_type + pending_interactions |
| `src/gobby/servers/websocket/handlers/plan_approval.py` | 2 | Migrate to pending_interactions |
| `src/gobby/install/shared/hooks/hook_dispatcher.py` | 1 | Timeout bump 90→600s |
| `src/gobby/install/shared/workflows/agents/default-web-chat.yaml` | 0 | Sources update |
| `src/gobby/install/shared/skills/canvas/SKILL.md` | 0 | Sources update |
| `src/gobby/skills/injector.py` | 0 | Source matching verification |
| `web/src/hooks/useChat.ts` | 2,4 | Provider state + payload |
| `web/src/hooks/useSessions.ts` | 0 | session_type filtering |
| `web/src/components/shared/SourceIcon.tsx` | 0 | Source type cleanup |
| `web/src/components/sessions/SessionSidebar.tsx` | 0 | Web/CLI filter → session_type |
| `web/src/components/chat/ChatPage.tsx` | 2,4 | Provider picker UI |
