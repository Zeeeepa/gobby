# Multi-Provider Web Chat Interaction (#10591)

## Context

Web chat currently works with Claude (SDK subprocess) and Codex (app-server subprocess). Both wrap CLI tools as child processes with rich programmatic interfaces. We want to extend web chat to support:

1. **Gemini CLI** — via its ACP mode (`--acp`), a bidirectional NDJSON protocol over stdin/stdout, structurally identical to Codex's app-server pattern
2. **Local LLMs** (Ollama, LM Studio, llama.cpp) — via OpenAI-compatible HTTP APIs through LiteLLM
3. **Cloud APIs** (OpenAI, Mistral, etc.) — also via LiteLLM

This yields a three-tier architecture: CLI-subprocess for providers with rich CLIs, API-direct for everything else.

## Architecture

```
_create_chat_session() provider routing:

  provider == "claude"                              → ChatSession (SDK subprocess)
  provider == "codex"                               → CodexChatSession (app-server JSON-RPC)
  provider == "gemini" (CLI available)               → GeminiChatSession (ACP NDJSON)
  provider in ("openai","ollama","lmstudio","litellm") → APIChatSession (LiteLLM streaming)
  provider == "gemini" (no CLI, API key only)        → APIChatSession (LiteLLM streaming)
```

### Three Tiers

| Tier | Mechanism | Providers | Tool Calling | Session State |
|------|-----------|-----------|-------------|---------------|
| **CLI subprocess** | SDK/app-server/ACP | Claude, Codex, Gemini CLI | Built-in (CLI handles it) | CLI-managed |
| **API + tools** | LiteLLM streaming | OpenAI, Gemini API, capable local LLMs | Function calling API + MCP bridge | In-memory + DB |
| **API chat-only** | LiteLLM streaming | Smaller local LLMs | None (chat only) | In-memory + DB |

## Phase 1: Gemini ACP Chat Session

### What is ACP?

Gemini CLI's `--acp` flag starts a long-running process with bidirectional NDJSON over stdin/stdout — the Agent Client Protocol. This mirrors Codex's `codex app-server` pattern:

| Feature | Codex app-server | Gemini ACP |
|---------|-----------------|------------|
| Transport | JSON-RPC over stdio | NDJSON over stdio |
| Multi-turn | Thread-based | Session-based |
| Streaming | Notification handlers | NDJSON events |
| Tool approval | `requestApproval` method | Confirmation events |
| Resume | `thread/resume(threadId)` | `--resume <session-id>` |

### New Files

**`src/gobby/adapters/gemini_acp/client.py`** (~500 lines)

`GeminiACPClient` — mirrors `CodexAppServerClient` pattern:
- Spawns `gemini --acp` subprocess
- Manages stdin/stdout NDJSON streams
- Event routing via notification handlers (same pattern as Codex)
- Methods: `start()`, `send_message(prompt)`, `stop()`, `interrupt()`
- Parses ACP events: `init`, `message` (with deltas), `tool_use`, `tool_result`, `result`, `error`

**`src/gobby/adapters/gemini_acp/types.py`** (~50 lines)

Data models for ACP protocol messages (mirrors `codex_impl/types.py`).

**`src/gobby/servers/gemini_chat_session.py`** (~400 lines)

`GeminiChatSession` — implements `ChatSessionProtocol`, mirrors `CodexChatSession`:
- Wraps `GeminiACPClient`
- Translates ACP events → `ChatEvent` stream (TextChunk, ToolCallEvent, ToolResultEvent, DoneEvent)
- Lifecycle callbacks (_on_before_agent, _on_pre_tool, etc.)
- Resume via `--resume <session-id>` (ACP supports it, and `gemini_session.py` already captures session IDs)
- Tool approval via ACP confirmation flow

**`src/gobby/servers/gemini_chat_session_permissions.py`** (~250 lines)

Fork of `CodexChatSessionPermissionsMixin` — same dict-based decision format. Tool approval decisions fed back through ACP confirmation response.

### Modified Files

**`src/gobby/servers/websocket/chat/_session.py`** (~15 lines)

Add Gemini branch in `_create_chat_session()`:

```python
elif use_gemini_acp:
    from gobby.servers.gemini_chat_session import GeminiChatSession
    session = GeminiChatSession(conversation_id=conversation_id)
```

Detection: `agent_body.provider == "gemini"` AND Gemini CLI is available in PATH.

**`src/gobby/agents/gemini_session.py`** (~0 lines, reference only)

Existing preflight capture utility — `GeminiChatSession.start()` can reuse `capture_gemini_session_id()` to grab the session ID from the ACP init event.

### Data Flow (Gemini ACP)

```
User message → WebSocket → GeminiChatSession.send_message()
  1. Write NDJSON message to gemini --acp subprocess stdin
  2. Read NDJSON events from stdout:
     - message delta → yield TextChunk
     - tool_use → yield ToolCallEvent (Gemini CLI executes tools itself)
     - tool_result → yield ToolResultEvent
     - result → yield DoneEvent
  3. Fire lifecycle callbacks at appropriate points
```

Key difference from APIChatSession: Gemini CLI manages its own tool execution, conversation history, and context. We just bridge events.

## Phase 2: API-Direct Chat Session (Local LLMs + Cloud APIs)

### New Files

**`src/gobby/servers/api_chat_session.py`** (~450 lines)

`APIChatSession` — implements `ChatSessionProtocol` via LiteLLM streaming:
- Parameterized by provider name, model, auth mode, api_base
- Manages `_messages: list[dict]` in-memory (OpenAI message format)
- Agentic loop: stream response → detect tool calls → execute via MCP → loop
- Supports function-calling models (tool bridge) and chat-only models (no tools)

**`src/gobby/servers/api_chat_session_permissions.py`** (~250 lines)

Shared with or forked from Gemini permissions mixin. Same dict-based decisions.

**`src/gobby/servers/api_chat_session_tools.py`** (~200 lines)

MCP tool bridge for API-backed sessions:
- `load_mcp_tools()` → fetch schemas from MCP proxy HTTP API
- `execute_mcp_tool()` → call tool via proxy
- `convert_to_openai_tools()` → reuse extracted `_convert_tools_to_openai_format()` from `litellm_executor.py`

### Modified Files

**`src/gobby/servers/websocket/chat/_session.py`** (~10 more lines)

Add API fallback branch:

```python
elif agent_body and agent_body.provider in ("openai", "ollama", "lmstudio", "litellm"):
    from gobby.servers.api_chat_session import APIChatSession
    session = APIChatSession(
        conversation_id=conversation_id,
        _provider=agent_body.provider,
        _api_base=provider_config.api_base,
    )
```

Also: Gemini without CLI falls through to APIChatSession.

**`src/gobby/llm/litellm_executor.py`** (~10 lines)

Extract `_convert_tools_to_openai_format()` to module-level function for reuse.

**`src/gobby/config/llm_providers.py`** (~30 lines)

Add local LLM provider configs:

```yaml
llm_providers:
  ollama:
    models: "llama3,codellama,deepseek-coder"
    auth_mode: "none"
    api_base: "http://localhost:11434/v1"
  lmstudio:
    models: "local-model"
    auth_mode: "none"
    api_base: "http://localhost:1234/v1"
```

New `auth_mode: "none"` for local providers (no API key needed).

**`src/gobby/storage/migrations.py`**

Add `chat_messages` table for API-backed session history persistence:

```sql
CREATE TABLE IF NOT EXISTS chat_messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    turn_index INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT,
    tool_calls TEXT,
    tool_call_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(session_id, turn_index)
);
```

### Data Flow (API-direct)

```
User message → WebSocket → APIChatSession.send_message()
  1. Append user message to _messages
  2. Agentic loop:
     a. litellm.acompletion(stream=True, messages=_messages, tools=_tools, api_base=...)
     b. Text deltas → yield TextChunk
     c. Tool call deltas → accumulate
     d. If tool_calls: execute via MCP proxy, append results, loop
     e. If no tool_calls: append assistant text, break
  3. yield DoneEvent
  4. Persist _messages to chat_messages table
```

### Local LLM Considerations

- **No auth**: `auth_mode: "none"`, no API key resolution needed
- **Tool calling**: Many local models don't support function calling. `APIChatSession` detects this (LiteLLM raises `UnsupportedParamsError`) and falls back to chat-only mode — no tools passed
- **Context windows**: Smaller than cloud models. Aggressive history truncation needed. Use model's reported `max_tokens` or config override
- **Streaming**: All local providers (Ollama, LM Studio, llama.cpp) support OpenAI-compatible streaming

## Resume Semantics

| Provider | Resume mechanism |
|----------|-----------------|
| Claude SDK | Native `resume_session_id` (already works) |
| Codex | Thread ID resume (already works) |
| Gemini ACP | `--resume <session-id>` flag on subprocess restart |
| API providers | Load `_messages` from `chat_messages` table |

## Provider Selection UX

Two mechanisms — Settings for the default, agent definitions for specialized configs.

### Settings Panel (primary, for most users)

Currently `web/src/components/Settings.tsx` hardcodes `MODEL_OPTIONS` to Claude (Opus/Sonnet/Haiku) in `web/src/hooks/useSettings.ts`. This needs to become dynamic:

**Backend: new `/api/providers` endpoint** (`src/gobby/servers/routes/`)
- Returns all configured providers with their available models:
  ```json
  {
    "providers": [
      {"name": "claude", "models": ["opus", "sonnet", "haiku"], "default": true},
      {"name": "gemini", "models": ["gemini-2.5-pro", "gemini-2.0-flash"]},
      {"name": "ollama", "models": ["llama3", "codellama"], "api_base": "http://localhost:11434/v1"},
      {"name": "openai", "models": ["gpt-4o", "gpt-4o-mini"]}
    ]
  }
  ```
- Reads from `config.llm_providers` (already has per-provider model lists)
- Filters to providers with valid auth (has API key, or auth_mode=none for local)

**Frontend: Settings.tsx changes**
- Replace hardcoded `MODEL_OPTIONS` with fetched provider/model list
- Two dropdowns: **Provider** (Claude, Gemini, Ollama, etc.) → **Model** (filtered by provider)
- Or: single unified dropdown grouped by provider ("Claude Opus", "Claude Sonnet", "Gemini 2.5 Pro", "Ollama llama3")
- Selected provider+model stored in settings, sent with `new_chat` WebSocket message
- `useSettings.ts`: `Settings` type gains `provider: string` field alongside `model: string`

**Backend: `_create_chat_session()` routing update**
- When no agent is selected (default chat), use `settings.provider` + `settings.model` to determine session type
- This replaces the current "always Claude" default

### Agent Definitions (power users, specialized configs)

Agent definitions still work as override — when user picks an agent from AgentPickerDropdown, its `provider` field takes precedence over settings. Examples:

```yaml
# Gemini CLI agent (uses ACP)
name: gemini-web-chat
provider: gemini
model: gemini-2.5-pro

# Local Ollama agent
name: local-llama
provider: ollama
model: llama3
api_base: http://localhost:11434/v1

# OpenAI API agent
name: gpt-web-chat
provider: openai
model: gpt-4o
```

## Phased Delivery Summary

| Phase | Scope | Key Deliverable |
|-------|-------|-----------------|
| **1** | Gemini ACP | `GeminiACPClient` + `GeminiChatSession` — CLI-subprocess web chat for Gemini |
| **2** | API-direct | `APIChatSession` — LiteLLM-backed web chat for local LLMs + cloud APIs |
| **3** | Settings UX | Dynamic provider/model picker in Settings, `/api/providers` endpoint, provider field in settings |
| **4** | Resume + history | `chat_messages` persistence, history reload, context window truncation |
| **5** | Polish | Thinking tokens, cost tracking, model switching, shared permissions base class |

## Risks

1. **Gemini ACP stability** — ACP is relatively new. Protocol may change. Mitigate: version-check on init, fallback to API-direct if ACP unavailable.
2. **Local LLM tool calling** — Many models don't support function calling. Mitigate: graceful degradation to chat-only mode.
3. **Context window exhaustion** (API tier) — Full history sent each request. Mitigate: truncation in Phase 3.
4. **Permissions duplication** — Three permission mixins (Claude SDK, Codex/Gemini dict-based, API). Mitigate: extract shared `DictPermissionsMixin` in Phase 4.

## Verification

### Phase 1 (Gemini ACP)
1. Ensure `gemini` CLI installed: `which gemini`
2. Create agent definition: `provider: gemini`, `model: gemini-2.5-pro`
3. Open web chat, select Gemini agent → verify streaming text, tool use, interrupt
4. `uv run pytest tests/servers/test_gemini_chat_session.py -v`
5. `uv run pytest tests/adapters/test_gemini_acp_client.py -v`

### Phase 2 (API-direct)
1. Start Ollama: `ollama serve` + `ollama pull llama3`
2. Create agent: `provider: ollama`, `model: llama3`, `api_base: http://localhost:11434/v1`
3. Open web chat → verify streaming, chat-only mode (no tools for small models)
4. Test with OpenAI: `provider: openai`, `model: gpt-4o` → verify tool calling works
5. `uv run pytest tests/servers/test_api_chat_session.py -v`

## Key Reference Files

| File | Role |
|------|------|
| `src/gobby/servers/chat_session_base.py` | Protocol to implement |
| `src/gobby/servers/codex_chat_session.py` | Structural template for GeminiChatSession |
| `src/gobby/adapters/codex_impl/client.py` | Structural template for GeminiACPClient |
| `src/gobby/adapters/codex_impl/types.py` | Structural template for ACP types |
| `src/gobby/servers/codex_chat_session_permissions.py` | Permissions pattern to fork |
| `src/gobby/servers/websocket/chat/_session.py` | Provider routing to extend |
| `src/gobby/agents/gemini_session.py` | Existing Gemini session ID capture (reusable) |
| `src/gobby/llm/litellm_executor.py:235` | `_convert_tools_to_openai_format()` to extract |
| `src/gobby/config/llm_providers.py` | Provider config to extend with local LLM support |
| `src/gobby/workflows/definitions.py:250` | `AgentDefinitionBody.provider` field |
