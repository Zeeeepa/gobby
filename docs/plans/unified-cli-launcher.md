# Epic: Unified CLI Launcher — SDK Removal + Interchangeable Web Chat Sessions (v2)

## Context

`claude_agent_sdk` is pinned `>=0.1.39,<=0.1.45` with a known break at `>0.1.45`. It wraps the CLI but the CLI provides everything natively. Removing the SDK is the primary driver. Secondary: make web chat sessions interchangeable across Claude, Gemini, and Codex so users can spawn, observe, and switch between sessions.

**Copilot deferred** until CLI hooks support matures. Built-in anticipation but hidden from agent launching and `/api/providers` response when CLI not detected.

---

## Verified CLI Capabilities (all tested April 2025 — RE-VERIFY IN PHASE 1)

| Concept | Claude | Gemini | Codex | Copilot (deferred) |
|---------|--------|--------|-------|---------|
| Binary | `claude` | `gemini` | `codex` | `copilot` |
| Non-interactive | `-p "prompt"` | `-p "prompt"` | `exec "prompt"` | `-p "prompt"` |
| Streaming JSONL | `--output-format stream-json --verbose` | `--output-format stream-json` | `exec --json` | `--output-format json` |
| ACP mode | No (FR [#6686](https://github.com/anthropics/claude-code/issues/6686)) | `--acp` (production) | `app-server` (ACP-adjacent) | `--acp` (production) |
| Model | `--model opus` | `--model gemini-3.1-pro` | `-c model="gpt-5.4"` | `--model claude-sonnet-4.6` |
| Session resume | `--session-id X` / `--resume X` | `--resume X` | `resume [ID]` / `--last` | `--resume[=ID]` / `--continue` |
| Hooks | `~/.claude/settings.json` (13+ events) | `~/.gemini/settings.json` | `~/.codex/hooks.json` (5 events) + `notify` | CLI: none. SDK: full in-process |
| MCP | `--mcp-config X` | `gemini mcp` | `codex mcp` | `--additional-mcp-config X` |
| Permission mode | `--permission-mode` | `--approval-mode` | `-c approval_policy=` | `--allow-tool/--deny-tool/--yolo` |
| Local LLM | `ANTHROPIC_BASE_URL` | N/A | N/A | N/A |

**Verified streaming event schemas:**

Claude (`--output-format stream-json --verbose`):
```
system/init → system/hook_* → assistant{content:[{type:text}]} → rate_limit_event → result
```

Gemini (`--output-format stream-json`):
```
init → message(role:user) → message(role:assistant,delta:true) → tool_use → tool_result → result
```

Codex (`exec --json`):
```
thread.started → turn.started → item.completed(agent_message) → turn.completed(usage)
```

Copilot (`--output-format json`):
```
session.mcp_servers_loaded → user.message → assistant.turn_start → assistant.message_delta → assistant.message → assistant.turn_end → result
```

---

## Rendering Pipeline (already unified)

```
ChatSession.send_message() yields ChatEvent (TextChunk, ToolCallEvent, ThinkingEvent, DoneEvent, etc.)
  ↓
_stream_chat_response() dispatches on isinstance(event, ...)
  ↓
WebSocket JSON messages (chat_stream, chat_thinking, tool_call, tool_result, chat_done)
  ↓
Frontend renders identically regardless of CLI source
```

**Key insight:** Any session that yields `ChatEvent` types renders identically in the web UI. Session switching only requires all session types to produce the same `ChatEvent` stream — which `ChatSessionProtocol` already guarantees.

---

## Phase 1: `ClaudeCLI` Launcher + Stream Parser + Spikes

### ClaudeCLI

**Modify:** `src/gobby/llm/claude_cli.py`

```python
@dataclass
class CliResult:
    text: str
    session_id: str
    usage: dict[str, Any]
    cost_usd: float
    duration_ms: int
    is_error: bool
    raw: dict[str, Any]

class CLISession:
    """Handle for a multi-turn CLI subprocess."""
    async def send(self, content: str) -> None: ...
    async def receive(self) -> AsyncIterator[StreamEvent]: ...
    async def interrupt(self) -> None: ...
    async def stop(self) -> None: ...
    @property
    def is_alive(self) -> bool: ...
    @property
    def session_id(self) -> str: ...

class ClaudeCLI:
    async def query(self, prompt, *, system_prompt, model, allowed_tools,
                    mcp_config, max_turns, timeout,
                    strip_hooks: bool = True, ...) -> CliResult:
        """Single-turn: claude -p --output-format json --no-session-persistence
        
        When strip_hooks=True (default for internal/headless calls):
          --settings ~/.gobby/settings/headless.json
        """

    async def session(self, *, session_id, system_prompt, model, permission_mode,
                      allowed_tools, mcp_config, settings, env, ...) -> CLISession:
        """Multi-turn: claude --output-format stream-json --verbose --session-id X"""
```

### Claude Stream Parser

**New file:** `src/gobby/llm/stream_json_parser.py`

Parses Claude's `--output-format stream-json` NDJSON → `StreamEvent` objects. Maps to `ChatEvent`:

| Claude stream event | ChatEvent |
|---|---|
| `assistant{content:[{type:"text"}]}` | `TextChunk` |
| `assistant{content:[{type:"thinking"}]}` | `ThinkingEvent` |
| `assistant{content:[{type:"tool_use"}]}` | `ToolCallEvent` |
| `result` | `DoneEvent` |

### Headless Settings File

**New file (written at `gobby install` time):** `~/.gobby/settings/headless.json`

```json
{
  "hooks": {
    "SessionStart": [],
    "SessionEnd": [],
    "UserPromptSubmit": [],
    "PreToolUse": [],
    "PostToolUse": [],
    "PreCompact": [],
    "Stop": [],
    "SubagentStart": [],
    "SubagentStop": [],
    "PermissionRequest": []
  }
}
```

All internal/headless `ClaudeCLI.query()` calls use `--settings ~/.gobby/settings/headless.json`. Zero hook process spawns, fail-closed (no hooks = physically impossible to fire rules). Daemon also marks session `is_internal=true` for defense-in-depth.

### Phase 1 Spikes (required before Phase 3 commits)

1. **600s hold-open hook spike:** Build toy PreToolUse hook that holds HTTP response for configurable duration against real `claude` subprocess. Verify: FastAPI holds, CLI accepts extended timeout (bump `src/gobby/install/shared/hooks/hook_dispatcher.py:745` from 90s → 600s), no HTTP connection drops.
2. **AskUserQuestion hook interception spike:** Verify PreToolUse fires for AskUserQuestion tool. Confirm hook denial returns clean UX to Claude CLI (no crash, no infinite retry).
3. **Re-verify CLI streaming schemas** for all four CLIs (year-old data). Update capability matrix if changed.

---

## Phase 2: Migrate Headless LLM Calls

All use `ClaudeCLI.query(strip_hooks=True)`:

| Current method | Replacement |
|---------------|-------------|
| `summarizer._summarize_description_with_claude()` | `ClaudeCLI.query(prompt, model=...)` |
| `summarizer.generate_server_description()` | `ClaudeCLI.query(prompt, model=...)` |
| `importer.import_from_github()` | `ClaudeCLI.query(prompt, allowed_tools=["WebFetch"], max_turns=3)` |
| `importer.import_from_query()` | `ClaudeCLI.query(prompt, allowed_tools=["WebSearch","WebFetch"], max_turns=5)` |
| `claude._generate_summary_sdk()` | `ClaudeCLI.query(prompt, model=...)` |
| `claude._generate_text_sdk()` | `ClaudeCLI.query(prompt, model=...)` |
| `claude._describe_image_sdk()` | `ClaudeCLI.query(prompt_with_file_path, allowed_tools=["Read"], model="haiku")` |
| `claude.generate_with_mcp_tools()` | **Remove.** Zero production callers. |

**All headless calls use `--settings ~/.gobby/settings/headless.json`** — no hooks fire, no rule evaluation, no MCP roundtrips, no context injection. Auth via OAuth/keychain (inherited). Per-call MCP config via `--mcp-config` flag for callers that need tools (importer → WebFetch/WebSearch, image description → Read).

**Perf note:** Tested at 2.4s with headless.json vs 6.3s with full hooks. For batch scenarios (many sequential summarizer calls), `ClaudeCLI.session()` multi-turn mode could batch into one subprocess later — not Phase 2 scope.

### Phase 2 Spot Checks (gate before Phase 3)

Verify headless CLI calls work in real production paths before touching web chat:

1. **Title synthesis:** Trigger a session title generation (new session → daemon generates title via summarizer). Confirm title appears in activity panel.
2. **Session summaries:** Trigger a session summary (context compaction or explicit summary request). Confirm summary stored and retrievable.
3. **MCP server description:** Import an MCP server (`gobby mcp add`). Confirm server description is auto-generated via summarizer.
4. **Image description:** If applicable, test `_describe_image` path with a real image file.
5. **GitHub import:** Run `import_from_github()` on a real repo. Confirm skill/tool import works with WebFetch via `--mcp-config`.

All five must pass before proceeding to Phase 3. If any fail, fix in Phase 2 scope — don't carry forward.

---

## Phase 3: `CLIChatSession` — Claude Web Chat

**New file:** `src/gobby/servers/cli_chat_session.py`

Implements `ChatSessionProtocol` using `ClaudeCLI.session()`, following `CodexChatSession` pattern.

### Permission Gate Architecture

Replaces SDK's in-process `can_use_tool` callbacks with hook-based hold-open pattern.

**Current SDK baseline (being replaced):**
- `ChatSessionPermissionsMixin._can_use_tool()` → `asyncio.Event` with 300s timeout
- `provide_approval()` called by WebSocket handler → sets event → SDK unblocks
- Plan approval already has DB persistence + rebroadcast on reconnect (`plan_approval.py:204-246`)

**New architecture (Shape A — uniform hold-open):**

All three approval types (tool, plan, AskUserQuestion) use the same pattern:

1. CLI fires PreToolUse hook → `hook_dispatcher.py` POSTs to `/api/hooks/execute`
2. Daemon identifies gated tool, persists to `pending_approvals` table
3. Daemon broadcasts `tool_approval_request` / `ask_user_question` / `plan_pending_approval` over WebSocket
4. Daemon holds HTTP response, blocks on `asyncio.Event` with timeout:
   - **Tool approval:** 300s (matches current `chat_session_permissions.py:514`)
   - **Plan approval / AskUserQuestion:** 600s (matches current `chat_session_permissions.py:133,214`)
5. User acts in web UI → WebSocket message → daemon sets event → HTTP response returns allow/deny/answer
6. If timeout → auto-deny, broadcast `tool_status: timed_out`

**`pending_approvals` table** (generalizes `pending_plan_path`):
```sql
CREATE TABLE pending_approvals (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    kind TEXT NOT NULL,  -- 'tool' | 'plan' | 'ask_user_question'
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);
```

**Reconnect resilience:** On WebSocket reconnect, daemon rebroadcasts all pending rows for session (generalizing existing `rebroadcast_pending_plans()` pattern).

**Daemon restart:** Fail-closed — pending rows cleared on startup, session gets "approval lost, please retry" message.

**Hook timeout bump:** `src/gobby/install/shared/hooks/hook_dispatcher.py:745` timeout 90s → 600s (matches max approval timeout).

**Parallel tool calls:** Serialized by CLI's sequential hook invocation (matches current SDK behavior — one approval at a time).

### Provider Routing

Route by `source` field (no feature flags needed — no feature flag infrastructure exists):

```python
match source:
    case "claude_web_chat":
        session = CLIChatSession(...)      # New (Phase 3)
    case "codex_web_chat":
        session = CodexChatSession(...)    # Existing
    case "gemini_web_chat":
        session = GeminiChatSession(...)   # New (Phase 4)
    case "claude_sdk_web_chat":
        session = ChatSession(...)         # SDK, removed in Phase 7
```

Rollback = change source routing. Kill-switch = revert one conditional.

### Local LLM support

Same `CLIChatSession` with `ANTHROPIC_BASE_URL` in env:
```python
env={"ANTHROPIC_BASE_URL": "http://localhost:1234"}  # LM Studio / Ollama
```

---

## Phase 4: Gemini Web Chat via ACP

Gemini's `--output-format stream-json` works for single-turn (`-p`), but web chat needs bidirectional multi-turn communication (send messages, receive streaming responses, handle tool approvals). `--acp` provides this via JSON-RPC over stdio.

### ACP Client

**New file:** `src/gobby/adapters/acp/client.py`

Wraps `gemini --acp` subprocess. Based on existing `CodexAppServerClient` pattern.

```python
class ACPClient:
    def __init__(self, command: list[str], env: dict | None = None): ...
    async def start(self) -> None: ...
    async def send_message(self, content: str) -> None: ...
    async def receive(self) -> AsyncIterator[ACPEvent]: ...
    async def send_approval(self, request_id: str, decision: str) -> None: ...
    async def interrupt(self) -> None: ...
    async def stop(self) -> None: ...
```

### Gemini Event Normalizer

**New file:** `src/gobby/adapters/acp/normalizer.py`

Maps Gemini ACP events → `ChatEvent`:

| Gemini event | ChatEvent |
|---|---|
| `message(role:assistant, delta:true)` | `TextChunk` |
| `tool_use` | `ToolCallEvent` |
| `tool_result` | `ToolResultEvent` |
| `result` | `DoneEvent` |

### GeminiChatSession

**New file:** `src/gobby/servers/gemini_chat_session.py`

Implements `ChatSessionProtocol` using `ACPClient`. See `docs/plans/web-chat-multi-provider-draft.md` Phase 1 for full specification.

---

## Phase 5: Unify Agent Spawning

All agents spawn via tmux (per epic #11295 — `AutonomousRunner` deleted, `SpawnMode` enum removed). This phase unifies spawning to use one command builder and eliminates preflight session capture.

### Unified `build_cli_command()`

Extend existing `build_cli_command()` (`command_builder.py:10`) with new params:

```python
def build_cli_command(
    cli: str,
    prompt: str | None = None,
    session_id: str | None = None,    # Claude: --session-id (pre-assigned)
    auto_approve: bool = False,
    working_directory: str | None = None,
    sandbox_args: list[str] | None = None,
    model: str | None = None,
    mcp_config: str | None = None,    # NEW: --mcp-config path
    settings: str | None = None,      # NEW: --settings path (headless.json or agent hooks)
) -> list[str]:
```

All three CLIs use this single function:
- **Claude:** `build_cli_command("claude", session_id=our_uuid, auto_approve=True, ...)`
- **Gemini:** `build_cli_command("gemini", auto_approve=True, ...)`
- **Codex:** `build_cli_command("codex", auto_approve=True, ...)`

### Eliminate preflight session capture

Gemini already runs without preflight (`spawn_executor.py:245` creates session with `external_id=None`). Codex adopts the same pattern:

1. Create Gobby session with `external_id=None`
2. Launch CLI into tmux via `build_cli_command()`
3. SessionStart hook fires synchronously → sets `external_id` to CLI's native session ID (`_session_start.py:240-244`)
4. Session cached for subsequent tool calls (`_session_start.py:246-250`)

**Safe because:** SessionStart fires before agent can make tool calls. Proven pattern — Gemini already uses it.

**Delete:**
- `prepare_gemini_spawn_with_preflight()` (`spawn.py:227`)
- `prepare_codex_spawn_with_preflight()` (`spawn.py:353`)
- `capture_codex_session_id()` (`codex_session.py:30`)
- `build_gemini_command_with_resume()` (`command_builder.py:98`)
- `build_codex_command_with_resume()` (`command_builder.py:148`)

### Codex adapter rename

Current naming is wrong — the hooks-based adapter should be the primary `CodexAdapter`, not the app-server one:

| Current name | New name | Purpose |
|---|---|---|
| `CodexAdapter` | **`CodexAppServerAdapter`** | App-server JSON-RPC (web chat, bidirectional streaming) |
| `CodexHooksAdapter` | **`CodexAdapter`** | Native hooks (terminal sessions, same role as `ClaudeCodeAdapter`) |
| `CodexNotifyAdapter` | **Delete** | Legacy notify (already being removed) |

Update all imports/references in `src/gobby/adapters/codex_impl/`.

### Prerequisites
- Wire `context_prefix` through to `CodexAppServerClient.start_turn()` (completing codex-app-server-v2 Phase 2)
- Wire `codex_client` in daemon startup (`http.py:55` accepts but never instantiates)

---

## Phase 6: Session Switching in Web UI

### Provider selection

- `/api/providers` endpoint returning available CLIs + models (filter Copilot when CLI not detected)
- Dynamic provider/model picker in Settings (replaces hardcoded Claude models)
- Local LLM endpoint configuration in settings

### Session switching

The DB already has the right shape — sessions table uses composite key `(external_id, machine_id, project_id, source)`. No schema redesign for namespacing.

1. **Live session registry:** Add `is_live` + `live_connection_id` to sessions table. `LiveSessionRegistry` wraps existing `_chat_sessions` dict with multi-provider awareness.
2. **WebSocket multiplexing:** Client subscribes to multiple streams. One active (read-write), others observed (read-only).
3. **Switch command:** `{"type": "switch_session", "session_id": "..."}` WebSocket message.
4. **All sessions produce `ChatEvent` stream** — guaranteed compatible via `ChatSessionProtocol`.

---

## Phase 7: Remove SDK + Cleanup

1. **Delete:** `chat_session.py` (SDK-backed), `chat_session_helpers.py`, `chat_session_permissions.py`
   - **Pre-deletion check:** `gcode callers ChatSession` + `gcode usages ChatSession` to confirm no other callers
2. **Remove** `claude-agent-sdk` from `pyproject.toml`
3. **Remove** `sdk_utils.py`
4. **Simplify** `ChatSessionProtocol` — shed SDK-specific lifecycle callbacks
5. **Update** tests
6. **Move** `docs/plans/web-chat-multi-provider-draft.md` to `docs/plans/completed/` with note pointing to this plan

---

## Phase 8: Dead Code & Settings Cleanup (post-verification)

Run after all phases verified and SDK removed. Full sweep for orphaned code, stale config, and dead references left behind by the migration.

### Code cleanup
1. **Dead imports:** `ruff check --select F401` across `src/gobby/` — remove all unused imports introduced by migration
2. **Dead functions/methods:** `gcode` blast-radius on every deleted module (`chat_session.py`, `sdk_utils.py`, `chat_session_helpers.py`, `chat_session_permissions.py`) — chase callers, remove any orphaned wrappers or helpers that only existed to serve SDK code
3. **Dead config fields:** Audit `DaemonConfig`, `LLMConfig`, and related Pydantic models for SDK-specific fields (e.g., `sdk_model`, `sdk_timeout`, `claude_sdk_*`). Remove fields + migration to drop columns if DB-backed.
4. **Dead test fixtures:** Remove SDK-specific test fixtures, mocks, and conftest entries (`mock_claude_sdk`, `sdk_client`, `ClaudeSDKClient` patches). Run `ruff check --select F811` for shadowed fixtures.
5. **`ClaudeSDKClient` references:** Grep for any remaining `ClaudeSDKClient`, `claude_agent_sdk`, `agent_sdk` strings in code, comments, docstrings, YAML, and config files. Remove all.
6. **Dead LLM provider code:** With SDK gone and headless calls on CLI, audit `src/gobby/llm/` for unused provider wrappers, fallback paths, or abstraction layers that no longer serve multiple backends.

### Settings & hook cleanup
7. **`hook_dispatcher.py` dead paths:** Remove any SDK-specific event handling, `is_sdk_session` checks, or `claude_sdk_web_chat` source routing.
8. **Settings.json templates:** Audit `src/gobby/install/shared/` for any SDK-related hook configs, MCP server entries, or settings that reference removed code.
9. **Source enum values:** Remove `claude_sdk_web_chat` from session source enum/constants once all sessions route through CLI. Migrate existing DB rows.

### Rule & workflow cleanup
10. **Rules referencing SDK:** Grep rule YAML templates for conditions referencing SDK-specific variables, source values, or tool names. Update or remove.
11. **Workflow definitions:** Check for any workflows that reference `ChatSession` (SDK), `ClaudeSDKClient`, or the old permission callback pattern.

### Verification
- `ruff check src/` clean (no F401, F811 violations)
- `uv run mypy src/` clean (no missing-import or unused-type-ignore errors from removed modules)
- `uv run pytest tests/ -x --timeout=300` on affected test directories (not full suite)
- `grep -r "claude_agent_sdk\|ClaudeSDKClient\|sdk_utils\|chat_session_helpers\|chat_session_permissions" src/` returns zero hits
- No `claude_sdk_web_chat` rows remain in sessions table

---

## Execution Order

```
Phase 1 (ClaudeCLI + parser + spikes)
  ├── Phase 2 (headless LLM calls) [after 1]
  ├── Phase 3 (CLIChatSession + permission gate) [after 1, spikes must pass]
  │     └── Phase 7 (remove SDK) [after 3 validated]
  │           └── Phase 8 (dead code cleanup) [after 7]
  ├── Phase 4 (Gemini ACP chat) [parallel with 2/3]
  ├── Phase 5 (agent spawning — all 3 CLIs) [after 1+4, Codex prereqs]
  └── Phase 6 (session switching) [after 3+4+5]
```

---

## Follow-up Epics

### ACP expansion
- Add Copilot ACP when CLI hooks mature
- Converge Codex `app-server` → ACP if/when Codex adds ACP mode
- Migrate Claude to ACP when `--acp` lands (FR #6686)

### Rust launcher
- `gobby-launcher` Rust binary — subprocess lifecycle, NDJSON/ACP parsing, session registry
- Python calls Rust binary via subprocess
- Eventually: entire daemon in Rust

---

## Files Modified/Created

| File | Action | Phase |
|------|--------|-------|
| `src/gobby/llm/claude_cli.py` | **Modify** — add ClaudeCLI, CLISession, CliResult | 1 |
| `src/gobby/llm/stream_json_parser.py` | **Create** — Claude NDJSON parser | 1 |
| `~/.gobby/settings/headless.json` | **Create** (at install time) — empty hooks for headless calls | 1 |
| `src/gobby/install/shared/hooks/hook_dispatcher.py` | **Modify** — bump timeout 90s → 600s (line 745) | 1 |
| `src/gobby/llm/claude.py` | **Modify** — replace SDK methods with ClaudeCLI.query() | 2 |
| `src/gobby/tools/summarizer.py` | **Modify** — replace SDK calls | 2 |
| `src/gobby/mcp_proxy/importer.py` | **Modify** — replace SDK calls | 2 |
| `src/gobby/servers/cli_chat_session.py` | **Create** — Claude CLI-backed ChatSession | 3 |
| `src/gobby/storage/migrations.py` | **Modify** — add `pending_approvals` table | 3 |
| `src/gobby/servers/websocket/chat/_session.py` | **Modify** — source-based provider routing | 3+4 |
| `src/gobby/servers/websocket/chat/_messaging.py` | **Modify** — generalize approval handling | 3 |
| `src/gobby/servers/websocket/handlers/plan_approval.py` | **Modify** — generalize rebroadcast to all approval types | 3 |
| `src/gobby/adapters/acp/client.py` | **Create** — ACP client for Gemini | 4 |
| `src/gobby/adapters/acp/normalizer.py` | **Create** — Gemini event → ChatEvent | 4 |
| `src/gobby/servers/gemini_chat_session.py` | **Create** — Gemini ACP-backed ChatSession | 4 |
| `src/gobby/agents/spawn.py` | **Modify** — unified tmux spawning, delete preflight functions | 5 |
| `src/gobby/agents/spawners/command_builder.py` | **Modify** — extend `build_cli_command()`, delete resume-only builders | 5 |
| `src/gobby/agents/codex_session.py` | **Delete** — preflight capture no longer needed | 5 |
| `src/gobby/agents/gemini_session.py` | **Delete** — only caller is `prepare_gemini_spawn_with_preflight()` (being deleted) | 5 |
| `src/gobby/adapters/codex_impl/adapter.py` | **Modify** — rename `CodexAdapter` → `CodexAppServerAdapter`, `CodexHooksAdapter` → `CodexAdapter`, delete `CodexNotifyAdapter` | 5 |
| `src/gobby/adapters/codex_impl/client.py` | **Modify** — wire context_prefix to start_turn() | 5 |
| `src/gobby/servers/http.py` | **Modify** — wire codex_client at startup | 5 |
| `src/gobby/storage/sessions.py` | **Modify** — add is_live, live_connection_id | 6 |
| `src/gobby/config/llm_providers.py` | **Modify** — local LLM endpoint config | 6 |
| `src/gobby/servers/routes/providers.py` | **Create** — /api/providers endpoint | 6 |
| `pyproject.toml` | **Modify** — remove `claude-agent-sdk` | 7 |
| `src/gobby/servers/chat_session.py` | **Delete** | 7 |
| `src/gobby/servers/chat_session_helpers.py` | **Delete** | 7 |
| `src/gobby/servers/chat_session_permissions.py` | **Delete** | 7 |
| `src/gobby/llm/` (various) | **Audit + remove** dead provider wrappers | 8 |
| `src/gobby/install/shared/hooks/hook_dispatcher.py` | **Modify** — remove SDK-specific event handling | 8 |
| `src/gobby/storage/migrations.py` | **Modify** — migrate `claude_sdk_web_chat` source rows, drop dead config columns | 8 |
| `src/gobby/install/shared/rules/` | **Audit** — remove SDK-referencing conditions | 8 |
| `src/gobby/config/` (various) | **Audit + remove** dead SDK config fields | 8 |
| `tests/` (various) | **Remove** dead SDK fixtures, mocks, conftest entries | 8 |

## Verification

- **Phase 1:** Unit tests for ClaudeCLI with mocked subprocess. Spikes pass (300s hold-open, AUQ interception, CLI schema re-verification).
- **Phase 2:** Existing LLM tests pass against new CLI paths. Headless calls complete in <5s (no hook overhead).
- **Phase 3:** Integration tests for CLIChatSession: timeout, deny, WS disconnect, daemon restart, parallel approvals. Manual web UI smoke test.
- **Phase 4:** Gemini ACP client tests + web UI with Gemini provider.
- **Phase 5:** Agent spawn lifecycle tests for all three CLIs. Codex context_prefix wired and tested.
- **Phase 6:** Session switching E2E tests (all provider combinations).
- **Phase 7:** `claude-agent-sdk` not in `uv pip list`, full test suite passes.
- **Phase 8:** Zero grep hits for SDK references. `ruff check` + `mypy` clean. No `claude_sdk_web_chat` rows in DB. Affected test directories pass.

### Cross-CLI Web UI Acceptance Test (required before Phase 6 ships)

1. **Claude:** Open web chat → select Claude provider → send message → verify streaming text, tool calls, thinking blocks, plan mode
2. **Gemini:** Open web chat → select Gemini provider → send message → verify streaming text, tool use events render correctly
3. **Codex:** Open web chat → select Codex provider → send message → verify streaming text, tool calls work, context_prefix passes through
4. **Session swap (all combinations):**
   - Start Claude session → start Gemini session → switch between them
   - Start Codex session → switch to Claude → switch back
   - Start local LLM session (Claude + `ANTHROPIC_BASE_URL`) → switch to cloud Claude → switch back
   - Verify all streams render correctly and state is preserved across switches
5. **Local LLM:** Configure `ANTHROPIC_BASE_URL` → open web chat → verify Claude CLI routes to local model → verify session appears in activity panel and is switchable

## Decisions Log

| # | Decision | Rationale |
|---|---|---|
| 1 | Hold-open for all approval types (tool=300s, plan/AUQ=600s) | Matches current SDK timeouts exactly. Simpler than mixed approaches. |
| 2 | `pending_approvals` table generalizing `pending_plan_path` | Enables reconnect resilience for all approval types. Plan approval pattern already proven. |
| 3 | Static `headless.json` for internal CLI calls (explicit empty arrays per hook type) | Zero hook overhead (2.4s vs 6.3s). Fail-closed. Inline `{"hooks": {}}` doesn't fully strip — file with explicit empty arrays required. |
| 4 | Source-based routing instead of feature flags | No feature flag infrastructure exists. `source` field already drives all routing. Rollback = revert one conditional. |
| 5 | No session-ID namespacing needed | DB already uses `(external_id, machine_id, project_id, source)` composite key. `source` column provides CLI-type namespacing. |
| 6 | Codex agent spawning included (not deferred) | All three CLIs spawn via tmux per epic #11295. Codex needs command builder + context_prefix wiring. |
| 7 | Hook timeout bump 90s → 600s | Matches max approval timeout (600s for plan/AUQ). `src/gobby/install/shared/hooks/hook_dispatcher.py:745`. |
| 8 | New `build_codex_command()` for agent spawning | Sibling to existing `build_codex_command_with_resume()` (resume-only). Fresh sessions use `codex exec`, not `codex resume`. |
