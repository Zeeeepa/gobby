# Unified Transcript Rendering — JSONL as Single Source of Truth

## Overview

The web UI renders chat messages via two paths that diverge after page refresh:
1. **Live**: WebSocket broadcasts flat `ParsedMessage` rows → frontend reassembles via `transcriptAdapter.ts`
2. **Historical**: `/api/sessions/{id}/messages` queries `session_messages` DB table → frontend reassembles via same adapter

The DB is a lossy derivative of JSONL — `_expand_line()` splits multi-block assistant turns into separate rows. Worse, the Claude parser uses `str()` on unrecognized content block types (tool_reference, image, document, mcp_tool_use, etc.), producing Python repr text that gets stored as corrupted data. The JSONL has everything in proper JSON.

**Fix**: New `TranscriptRenderer` that reads JSONL directly and outputs turn-grouped `RenderedMessage` objects with typed tool calls. Both delivery paths (WebSocket live, HTTP historical) emit the same shape. Drop `session_messages` table.

## Constraints

- Existing `/messages` endpoint path stays — swap implementation, don't create new endpoint
- Existing `/transcript` endpoint stays as raw JSONL download
- Frontend `ToolCallCard.tsx` (1100+ lines) already has rich renderers for Read, Edit, Bash, Grep, Glob, Write — deliver clean data, don't rebuild renderers
- Hybrid upsert for live WebSocket: broadcast full `RenderedMessage` eagerly, re-broadcast same ID when tool_result arrives
- `search_messages` reimplementation deferred to separate task
- Parser error logging to `~/.gobby/logs/{cli}-parser-error.log`

## Phase 1: Core Renderer

**Goal**: Build the TranscriptRenderer that converts flat ParsedMessage streams into grouped RenderedMessage objects with typed tool calls.

### 1.1 Create TranscriptRenderer data models [category: code]

Target: `src/gobby/sessions/transcript_renderer.py` (CREATE)

Create the core data models and grouping logic. This is the heart of the system — it takes a stream of flat `ParsedMessage` objects (from any CLI parser) and groups them into turn-based `RenderedMessage` objects.

**Data models to create:**

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable

@dataclass
class RenderedToolCall:
    id: str
    tool_name: str
    server_name: str | None          # extracted from mcp__server__tool naming
    tool_type: str                    # "bash", "read", "write", "edit", "grep", "glob", "mcp", "unknown"
    arguments: dict[str, Any] | None  # always valid JSON-serializable dict, NEVER str()
    result: ToolResult | None
    status: str                       # "completed", "error", "pending"
    error: str | None

@dataclass
class ToolResult:
    """Typed tool result — preserves structure for frontend rendering."""
    content: Any                      # the actual result content (string, list, or dict from JSONL)
    content_type: str                 # "text", "json", "image", "error"
    truncated: bool                   # whether result was truncated
    metadata: dict[str, Any] | None   # tool-specific metadata (exit_code for Bash, line_count for Read, etc.)

@dataclass
class ContentBlock:
    type: str                         # "text", "thinking", "tool_chain", "tool_reference", "image", "unknown"
    content: str | None               # for text/thinking blocks
    tool_calls: list[RenderedToolCall] | None  # for tool_chain blocks
    raw: dict | None                  # for unknown blocks — always JSON, never str()
    source_line: int | None           # JSONL line number for debugging

@dataclass
class RenderedMessage:
    id: str
    role: str                         # "user", "assistant", "system"
    content: str                      # plain text summary (for search, preview)
    timestamp: datetime
    content_blocks: list[ContentBlock]
    model: str | None
    usage: dict | None                # {input_tokens, output_tokens, ...}

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-safe dict for API/WebSocket."""
        ...
```

**Block type handling table — NO `str()` fallbacks:**

| JSONL Block Type | ContentBlock Output |
|---|---|
| `text` | `{type: "text", content: "..."}` |
| `thinking` | `{type: "thinking", content: "..."}` |
| `tool_use` | Grouped into `{type: "tool_chain", tool_calls: [...]}` |
| `tool_result` | Paired to matching tool_use by `tool_use_id` → fills `RenderedToolCall.result` |
| `tool_reference` | `{type: "tool_reference", tool_name: "...", server_name: "..."}` |
| `image` | `{type: "image", source: {...}}` — pass through for frontend |
| `document` | `{type: "document", source: {...}}` — pass through |
| `mcp_tool_use` / `mcp_tool_result` | Fold into `tool_chain` like regular tool_use/result |
| `web_search_tool_result` | `{type: "web_search_result", content: {...}}` |
| **Any unknown** | `{type: "unknown", block_type: "original_type", raw: {...}, source_line: N}` — always valid JSON via `json.dumps()` |

**Grouping logic for `render_transcript()`:**
- Assistant text + thinking + tool_use blocks from same JSONL line → single `RenderedMessage` with ordered `content_blocks`
- Consecutive tool_result messages → matched to preceding tool_use by `tool_use_id`, merged into `RenderedToolCall.result`
- Content deduplication: Claude Code writes duplicate JSONL lines during streaming — deduplicate by content value (pattern from claude-replay's `collectAssistantBlocks()`)
- User messages → single `RenderedMessage`, strip hook context / system reminders
- Hook feedback messages (prefixes: "Stop hook feedback:", "PreToolUse hook", "PostToolUse hook", "UserPromptSubmit hook") → classified as role `"system"` (not user)

**Two entry points:**

```python
def render_transcript(
    parsed_messages: Iterable[ParsedMessage],
    session_id: str | None = None,
) -> list[RenderedMessage]:
    """Full transcript render — for historical reads."""

def render_incremental(
    new_messages: list[ParsedMessage],
    pending_state: RenderState,
) -> tuple[list[RenderedMessage], RenderState]:
    """Incremental render — for live WebSocket. Returns completed/updated turns + new state."""
```

`RenderState` holds the in-progress assistant turn (accumulating blocks until turn boundary — next real user message or end of stream).

### 1.2 Create typed tool classification system [category: code] (depends: 1.1)

Target: `src/gobby/sessions/transcript_renderer.py` (same file, separate concern)

Add tool type classification and result metadata extraction. The frontend's `ToolCallCard.tsx` already has rich renderers keyed on tool name — this system provides structured metadata so the frontend doesn't need to parse strings.

```python
TOOL_TYPE_MAP = {
    "Bash": "bash", "Read": "read", "Write": "write", "Edit": "edit",
    "MultiEdit": "edit", "Grep": "grep", "Glob": "glob",
    "WebSearch": "web_search", "WebFetch": "web_fetch",
    "AskUserQuestion": "ask_user", "Agent": "agent", "NotebookEdit": "notebook",
}
# Tools not in map → "mcp" if name contains __ (MCP naming), "unknown" otherwise

def classify_tool(tool_name: str) -> tuple[str, str | None]:
    """Returns (tool_type, server_name). Extracts server from mcp__server__tool naming."""
    ...

def extract_result_metadata(tool_type: str, result_content: Any) -> dict[str, Any]:
    """Extract tool-specific metadata from result for rich frontend rendering."""
    match tool_type:
        case "bash":
            # Parse exit code from result, count stdout/stderr lines
            return {"exit_code": ..., "stdout_lines": ..., "stderr_lines": ...}
        case "read":
            # Extract file path from arguments, count lines in result
            return {"file_path": ..., "line_count": ..., "language": ...}
        case "edit":
            return {"file_path": ..., "lines_changed": ...}
        case "grep":
            return {"files_matched": ..., "total_matches": ...}
        case "glob":
            return {"files_found": ...}
        case _:
            return {}
```

**Key guarantee**: `arguments` is always the raw dict from JSONL `tool_use.input`. `result.content` is always the parsed content from `tool_result` block. No `str()` anywhere.

### 1.3 Add parser error logging [category: code] (depends: 1.1)

Target: `src/gobby/sessions/transcripts/base.py` (MODIFY), `src/gobby/sessions/transcript_renderer.py` (MODIFY)

Create `TranscriptParserErrorLog` class and wire into both the CLI parsers and the renderer.

```python
class TranscriptParserErrorLog:
    """Logs unrecognized JSONL content to ~/.gobby/logs/{cli}-parser-error.log"""

    def __init__(self, cli_name: str):
        self.log_path = Path.home() / ".gobby" / "logs" / f"{cli_name}-parser-error.log"

    def log_unknown_block(self, line_num: int, session_id: str | None, block_type: str, raw: dict) -> None:
        """Log format: [ISO timestamp] line:{N} session:{id} — Unknown block type: {type}\n{json}"""
        ...

    def log_malformed_line(self, line_num: int, session_id: str | None, raw_text: str, error: str) -> None:
        ...
```

- Rotates at 10MB
- Called by renderer when encountering unknown block types
- Called by CLI parsers when encountering malformed JSONL lines (replace current silent skip)
- Wire into `BaseTranscriptParser` so all CLI parsers inherit error logging

## Phase 2: Wire Into Data Paths

**Goal**: Connect the renderer to both historical (HTTP) and live (WebSocket) message delivery.

### 2.1 Add rendered message support to TranscriptReader [category: code] (depends: 1.1)

Target: `src/gobby/sessions/transcript_reader.py` (MODIFY)

Add `get_rendered_messages()` method that returns `list[RenderedMessage]`:

- Reads JSONL (live file or gzip archive) through CLI-specific parser
- Pipes `ParsedMessage` stream through `TranscriptRenderer.render_transcript()`
- Supports `limit`/`offset` pagination on the rendered (grouped) messages
- Fallback chain: live JSONL → gzip archive (skip DB — it has corrupted data)
- Handle truncated gzip archives gracefully (skip malformed lines, log, continue)

Existing `get_messages()` stays temporarily for backwards compatibility until Phase 4 completes.

### 2.2 Swap /messages endpoint to renderer [category: code] (depends: 2.1)

Target: `src/gobby/servers/routes/sessions.py` (MODIFY)

Swap `GET /api/sessions/{id}/messages` implementation:
- Currently: `message_manager.get_messages()` (DB query returning flat rows)
- New: `transcript_reader.get_rendered_messages()` (JSONL parse returning grouped turns)
- Add `?format=rendered` query param during transition (default to `rendered`)
- `?format=legacy` returns old flat format for any consumers not yet migrated
- Response includes `content_blocks` array on each message

### 2.3 Wire renderer into processor for live WebSocket [category: code] (depends: 1.1, 1.2)

Target: `src/gobby/sessions/processor.py` (MODIFY)

The processor currently:
1. Detects new JSONL lines via byte offset polling (2s interval)
2. Parses through CLI parser → flat `ParsedMessage` list
3. Stores in DB via `store_messages()`
4. Broadcasts flat messages via WebSocket

Change step 4 to:
- Maintain per-session `RenderState` dict on the processor
- Pipe new `ParsedMessage` list through `render_incremental()`
- Broadcast `RenderedMessage`-shaped payloads via WebSocket
- Keep DB writes (step 3) for now — removed in Phase 3

**Hybrid upsert broadcast:**
- Broadcast full `RenderedMessage` eagerly (not patches)
- First broadcast: tool_calls have `status: "pending"`, `result: null`
- When tool_result arrives: re-broadcast **same message ID** with result filled, status "completed"
- Frontend upserts by message ID — find by ID → replace, else append

```python
# Both initial and update use same shape:
{"type": "session_message", "session_id": "...", "message": {
    "id": "turn-001",  # stable across updates
    "role": "assistant",
    "content_blocks": [
        {"type": "text", "content": "Let me check that file."},
        {"type": "tool_chain", "tool_calls": [
            {"id": "abc", "tool_name": "Read", "tool_type": "read", "status": "pending", "result": null},
        ]}
    ]
}}
```

Edge cases:
- Session crash mid-turn: `RenderState` has pending tool_use with no result → flush with status "pending"
- Processor restart: `RenderState` lost, next poll starts fresh from byte offset
- Rapid tool chains in same poll cycle: batch into single broadcast with all pairs matched

## Phase 3: Frontend

**Goal**: Update frontend to consume the unified RenderedMessage shape from both paths.

### 3.1 Update TypeScript types for RenderedMessage [category: code] (depends: 1.1)

Target: `web/src/types/chat.ts` (MODIFY)

Update/add types to match backend `RenderedMessage` shape:

```typescript
export interface ContentBlock {
  type: 'text' | 'thinking' | 'tool_chain' | 'tool_reference' | 'image' | 'document' | 'web_search_result' | 'unknown';
  content?: string;
  tool_calls?: ToolCall[];
  raw?: Record<string, unknown>;
  source_line?: number;
  block_type?: string;  // original type for unknown blocks
}

export interface ToolCall {
  id: string;
  tool_name: string;
  server_name: string;
  tool_type: string;    // NEW: "bash", "read", "edit", etc.
  status: 'calling' | 'completed' | 'error' | 'pending' | 'pending_approval';
  arguments?: Record<string, unknown>;
  result?: ToolResult;  // NEW: typed result
  error?: string;
}

export interface ToolResult {
  content: unknown;
  content_type: string;  // "text", "json", "image", "error"
  truncated: boolean;
  metadata?: Record<string, unknown>;  // tool-specific: exit_code, line_count, etc.
}
```

### 3.2 Update useSessionDetail for upsert + rendered shape [category: code] (depends: 2.2, 2.3, 3.1)

Target: `web/src/hooks/useSessionDetail.ts` (MODIFY)

- WebSocket handler: receive `RenderedMessage`-shaped events with `content_blocks`
- Implement upsert logic:
  ```typescript
  setMessages(prev => {
    const idx = prev.findIndex(m => m.id === incoming.id);
    if (idx >= 0) { prev[idx] = incoming; return [...prev]; }
    return [...prev, incoming];
  });
  ```
- Historical load: fetch from `/messages` endpoint (now returns rendered shape)
- Map `RenderedMessage` → `ChatMessage` (field mapping, `tool_chain` blocks → `ToolCall[]`)

### 3.3 Update useChat for historical load via renderer [category: code] (depends: 2.2, 3.1)

Target: `web/src/hooks/useChat.ts` (MODIFY)

- Page refresh / reconnect: load history from `/messages` endpoint (now returns `RenderedMessage` shape)
- Live streaming path (SDK WebSocket handlers): unchanged
- Reconciliation: when historical load completes, deduplicate against any WebSocket messages received during loading

### 3.4 Update ToolCallCard to consume tool_type and metadata [category: code] (depends: 3.1)

Target: `web/src/components/chat/ToolCallCard.tsx` (MODIFY)

- Use `tool_type` field for tool classification instead of string-matching on `tool_name`
- Use `result.metadata` for tool-specific rendering hints where available (exit_code, line_count, etc.)
- Existing renderers (Read file viewer, Edit diff viewer, Bash terminal, Grep results, etc.) stay as-is
- Add fallback for new `tool_type` values the frontend doesn't know about yet

### 3.5 Create Unknown block renderer [category: code] (depends: 3.1)

Target: `web/src/components/chat/UnknownBlockCard.tsx` (CREATE)

Small component (~30 lines) that renders `ContentBlock` with `type: "unknown"`:
- Shows: "Unrecognized content block" header
- Shows: `block_type` value (the original type from JSONL)
- Shows: `source_line` number
- Collapsible raw JSON viewer
- Serves as visible signal when a CLI ships a new format we haven't handled

### 3.6 Delete transcriptAdapter [category: refactor] (depends: 3.2, 3.3)

Target: `web/src/components/sessions/transcriptAdapter.ts` (DELETE)

- Grouping logic has moved to backend `TranscriptRenderer`
- Check if `extractServerName()` is used elsewhere — if so, move to a util before deleting
- Remove associated test file if it exists

## Phase 4: Migration & Cleanup

**Goal**: Relocate stats to sessions table, stop DB message writes, drop session_messages.

### 4.1 Add stats columns to sessions table [category: code]

Target: `src/gobby/storage/migrations.py` (MODIFY)

New migration adding columns:
```sql
ALTER TABLE sessions ADD COLUMN message_count INTEGER DEFAULT 0;
ALTER TABLE sessions ADD COLUMN turn_count INTEGER DEFAULT 0;
ALTER TABLE sessions ADD COLUMN tool_call_count INTEGER DEFAULT 0;
ALTER TABLE sessions ADD COLUMN last_assistant_content TEXT;
```

Include one-time backfill: compute stats from existing `session_messages` rows. Run backfill BEFORE any table drop.

### 4.2 Update processor to compute stats and stop DB writes [category: code] (depends: 2.3, 4.1)

Target: `src/gobby/sessions/processor.py` (MODIFY)

- Stop calling `message_manager.store_messages()` — no more DB writes for messages
- Compute stats (message_count, turn_count, tool_call_count, last_assistant_content) during incremental parsing
- Update sessions table with computed stats
- Continue broadcasting via WebSocket (already using renderer from 2.3)

### 4.3 Update session_coordinator for stats from sessions table [category: code] (depends: 4.1)

Target: `src/gobby/hooks/session_coordinator.py` (MODIFY)

- Agent completion: read `last_assistant_content` from sessions table instead of querying session_messages
- Stats validation: read `tool_call_count` and `turn_count` from sessions table

### 4.4 Update MCP get_session_messages to use renderer [category: code] (depends: 2.1)

Target: `src/gobby/mcp_proxy/tools/sessions/_messages.py` (MODIFY)

- `get_session_messages`: swap from `message_manager.get_messages()` to `transcript_reader.get_rendered_messages()`
- `search_messages`: add deprecation note, defer reimplementation to separate task

### 4.5 Drop session_messages table and delete storage module [category: code] (depends: 4.2, 4.3, 4.4)

Target: `src/gobby/storage/migrations.py` (MODIFY), `src/gobby/storage/session_messages.py` (DELETE)

New migration (separate from 4.1 — runs after all consumers are migrated):
```sql
DROP TABLE IF EXISTS session_messages;
```

Delete `src/gobby/storage/session_messages.py` (entire `LocalSessionMessageManager` class).

Also clean up remaining consumers:
- `src/gobby/servers/routes/sessions.py`: remove legacy format fallback from `/messages`
- `src/gobby/servers/websocket/chat/_messaging.py`: remove `store_messages()` calls
- `src/gobby/cli/sessions.py`: use `message_count` from sessions table

## Task Mapping

<!-- Updated after task creation -->
| Plan Item | Task Ref | Status |
|-----------|----------|--------|
