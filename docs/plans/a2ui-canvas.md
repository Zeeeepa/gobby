# A2UI (Agent-to-UI) Implementation Plan

## Context

OpenClaw's Canvas/A2UI lets agents generate interactive HTML — buttons, forms, cards — that render in a visual workspace. User clicks on those elements become tool calls back to the agent, closing the loop without typing. Gobby's web UI is rich but developer-designed at build time. A2UI lets **agents design UI at runtime** for the current task.

Gobby already has the foundational pattern: `AskUserQuestion` blocks the agent, renders interactive options in the web UI, collects user input, and returns it as a tool result. A2UI generalizes this to arbitrary HTML content.

## Design Decisions

**Where does it render?** Inline in chat messages (same spot as AskUserQuestion), with a "pop out" button for complex canvases. Keeps the mental model simple — the agent "says" something interactive.

**How does it work across CLIs?** As an MCP tool (`gobby-canvas` registry). Any CLI agent calls `render_canvas` → content broadcasts to web UI via WebSocket → user interacts → result returns to agent. Works whether the agent is Claude Code in a terminal or the web chat.

**Blocking model?** Same `asyncio.Event` pattern as `AskUserQuestion` (`chat_session.py:387-424`) and pipeline approvals. Tool blocks until user interacts or timeout expires.

**Security?** DOMPurify with strict allowlist. No `<script>`, no `on*` handlers, no `javascript:` URIs.

## Data Flow

```
Agent (any CLI) ──call_tool("gobby-canvas", "render_canvas", {content, blocking})──▶ MCP Proxy
    │
    ▼
Canvas Registry (canvas.py)
    │ stores CanvasState, creates asyncio.Event, broadcasts via callback
    ▼
WebSocket Server ──broadcast canvas_event──▶ Web UI (useChat.ts)
    │                                            │
    │                                            ▼
    │                                       ToolCallDisplay.tsx detects render_canvas
    │                                       CanvasRenderer.tsx sanitizes + renders HTML
    │                                            │
    │                                       User clicks [data-action="approve"]
    │                                            │
    │  ◀──canvas_interaction ws message──────────┘
    ▼
WebSocket handler (_handle_canvas_interaction)
    │ looks up CanvasState, sets asyncio.Event
    ▼
Canvas Registry unblocks, returns {action, payload} to agent
```

## Implementation

### Phase 1: Core Loop (MVP)

**7 new files, 5 modified files**

#### Backend

**New: `src/gobby/mcp_proxy/tools/canvas.py`** — Canvas tool registry

```python
# Pattern: follows create_memory_registry() in tools/memory.py
def create_canvas_registry(
    broadcast_callback: Callable | None = None,
) -> InternalToolRegistry:
```

Three tools:
- `render_canvas(content: str, canvas_id: str = "", title: str = "", blocking: bool = True)` — Sanitize HTML server-side (optional), store `CanvasState`, broadcast `canvas_event` with `event: "rendered"`, if blocking wait on `asyncio.Event` (600s timeout), return `{canvas_id, interaction: {action, payload, form_data}}` or `{canvas_id, status: "rendered"}` for non-blocking
- `update_canvas(canvas_id: str, content: str, mode: str = "replace")` — Update stored content, broadcast `canvas_event` with `event: "updated"`, return immediately
- `clear_canvas(canvas_id: str)` — Remove canvas state, broadcast `event: "cleared"`

In-memory state:
```python
@dataclass
class CanvasState:
    canvas_id: str
    content: str
    title: str
    conversation_id: str  # for routing interactions
    pending_event: asyncio.Event | None  # for blocking mode
    interaction_result: dict | None
    created_at: datetime
    expires_at: datetime  # created_at + timeout; for automatic cleanup
    completed: bool = False  # True after interaction received or timeout
```

Key: `_pending_canvases: dict[str, CanvasState]` shared between the tool functions and the resolve function that the WebSocket handler calls.

Rate limiting and resource bounds:
```python
MAX_CANVASES_PER_CONVERSATION = 50  # prevent runaway agents
MAX_CANVAS_SIZE = 64 * 1024  # 64KB HTML content limit
MAX_RENDER_RATE = 10  # renders per minute per conversation
```

Enforce in `render_canvas`: reject with error if conversation exceeds `MAX_CANVASES_PER_CONVERSATION`, content exceeds `MAX_CANVAS_SIZE`, or rate limit hit. Periodic cleanup: a background task (or lazy sweep on next `render_canvas`) removes expired canvases where `completed=True` or `datetime.now() > expires_at`.

Expose a `resolve_interaction(canvas_id, action, payload, form_data)` method on the registry that the WebSocket handler can call to unblock.

**Modify: `src/gobby/mcp_proxy/registries.py`** (line ~374, after pipelines registry)

```python
from gobby.mcp_proxy.tools.canvas import create_canvas_registry

canvas_registry = create_canvas_registry()
manager.add_registry(canvas_registry)
```

Store a reference to the registry so the WebSocket server can call `resolve_interaction`. Pattern: same as how `pipeline_executor` is passed around — add `canvas_registry` to `setup_internal_registries` return or expose it on the manager.

**Modify: `src/gobby/servers/websocket/server.py`** (line 209-229, dispatch table)

Add entry:
```python
"canvas_interaction": self._handle_canvas_interaction,
```

**Modify: `src/gobby/servers/websocket/chat.py`** — Add handler

```python
async def _handle_canvas_interaction(self, websocket: Any, data: dict[str, Any]) -> None:
    canvas_id = data.get("canvas_id")
    action = data.get("action", "")
    payload = data.get("payload", {})
    form_data = data.get("form_data", {})

    # Validate required fields
    if not canvas_id or not isinstance(canvas_id, str):
        await self._send_error(websocket, "canvas_interaction requires a valid canvas_id")
        return
    if not action or not isinstance(action, str):
        await self._send_error(websocket, "canvas_interaction requires a valid action")
        return
    if not isinstance(payload, dict) or not isinstance(form_data, dict):
        await self._send_error(websocket, "payload and form_data must be objects")
        return

    canvas_registry = getattr(self, "_canvas_registry", None)
    if not canvas_registry:
        await self._send_error(websocket, "Canvas system not available")
        return

    try:
        canvas_registry.resolve_interaction(canvas_id, action, payload, form_data)
    except KeyError:
        await self._send_error(websocket, f"Canvas {canvas_id} not found or already completed")
    except Exception as e:
        logger.error(f"Canvas interaction failed for {canvas_id}: {e}", exc_info=True)
        await self._send_error(websocket, "Internal error processing canvas interaction")
```

Wire `_canvas_registry` on WebSocketServer during HTTP server lifespan (same pattern as `workflow_handler`).

**Modify: `src/gobby/servers/websocket/broadcast.py`** — Add `canvas_event` to high-volume subscription list

#### Frontend

**New: `web/src/utils/sanitizeHtml.ts`** — DOMPurify config

```typescript
import DOMPurify from 'dompurify'

const ALLOWED_TAGS = [
  'div', 'span', 'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  'button', 'input', 'select', 'option', 'textarea', 'form', 'label',
  'table', 'tr', 'td', 'th', 'thead', 'tbody', 'ul', 'ol', 'li',
  'a', 'img', 'br', 'hr', 'strong', 'em', 'code', 'pre',
  'details', 'summary',
]

const ALLOWED_ATTRS = [
  'class', 'id', 'style', 'type', 'name', 'value', 'placeholder',
  'disabled', 'checked', 'selected', 'href', 'src', 'alt', 'title',
  'data-action', 'data-payload', 'data-element-id',
  'aria-label', 'aria-describedby', 'role',
  'rows', 'cols', 'min', 'max', 'step', 'pattern', 'required',
]

export function sanitizeCanvasHtml(html: string): string { ... }
```

**New: `web/src/components/CanvasRenderer.tsx`** — Renders sanitized HTML with event delegation

```typescript
interface CanvasRendererProps {
  canvasId: string
  content: string
  title?: string
  status: 'active' | 'completed'
  onInteraction: (canvasId: string, action: string, payload: Record<string, unknown>, formData: Record<string, string>) => void
}
```

Key behaviors:
- `dangerouslySetInnerHTML` with DOMPurify-sanitized content
- Delegated click handler on container: walk up DOM from `e.target` to find closest `[data-action]`, with max traversal depth (20 levels) to prevent pathological DOM structures from hanging the handler
- Null-check `e.target` and verify it's within the container before traversal
- For `<form data-action="...">`: intercept submit, gather all named inputs
- For `<select data-action="...">`: intercept change events
- Parse `data-payload` with try/catch around `JSON.parse` — reject malformed JSON and log a warning rather than crashing the handler
- When `status === 'completed'`: dim the canvas, show interaction result
- Scoped CSS: `.canvas-container`, `.canvas-content`, themed buttons/inputs using existing CSS variables

**New: `web/src/components/CanvasRenderer.css`** — Styles following existing patterns (CSS variables, BEM-like naming)

**Modify: `web/src/components/ToolCallDisplay.tsx`** — Detect canvas tools and render inline

Add detection (follows `isAskUserQuestion` pattern at line 21):
```typescript
function isCanvasRender(call: ToolCall): boolean {
  // Direct tool name or routed through call_tool
  return call.tool_name === 'render_canvas' ||
    (call.tool_name === 'mcp__gobby__call_tool' &&
     call.arguments?.tool_name === 'render_canvas')
}
```

Add `CanvasDisplay` component (parallel to `AskUserQuestionDisplay`), rendered in `ToolCallItem` at line 158.

Thread `onCanvasInteraction` prop through `ToolCallDisplay` → `ToolCallItem` → `CanvasDisplay` → `CanvasRenderer` (same as `onRespond` for AskUserQuestion).

**Modify: `web/src/hooks/useChat.ts`** — Add canvas interaction callback

```typescript
const respondToCanvas = useCallback((
  canvasId: string, action: string,
  payload: Record<string, unknown>, formData: Record<string, string>
) => {
  const ws = wsRef.current
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    console.warn('Canvas interaction dropped: WebSocket not connected')
    return
  }
  // Optimistic UI: immediately mark canvas as completed locally
  updateCanvasStatus(canvasId, 'completed')
  try {
    ws.send(JSON.stringify({
      type: 'canvas_interaction',
      conversation_id: conversationIdRef.current,
      canvas_id: canvasId, action, payload, form_data: formData,
    }))
  } catch (e) {
    // Revert optimistic update on send failure
    updateCanvasStatus(canvasId, 'active')
    console.error('Failed to send canvas interaction:', e)
  }
}, [])
```

Handle `canvas_event` messages for live updates to existing canvases.

**New dependency: `dompurify` + `@types/dompurify`** in `web/package.json`

### Phase 2: Live Updates + Side Panel

- `update_canvas` broadcasts partial updates; frontend patches DOM by `canvas_id`
- Non-blocking canvases: interactions injected as synthetic user messages instead of unblocking events
- `CanvasPanel.tsx` — collapsible side panel (follows `TerminalPanel` pattern in `ChatPage.tsx`) for expanded/multi-canvas view

### Phase 3: Persistence + Templates

- SQLite `canvas_states` table for surviving session restarts
- REST endpoints (`/canvas/{conversation_id}`) following `create_*_router()` pattern
- Canvas templates: agent calls `render_canvas(template="approval_form", variables={...})`

## Data Attribute Convention

```html
<button data-action="approve" data-payload='{"id":"123"}'>Approve</button>
<form data-action="submit_config">
  <input name="threshold" type="number" value="80" />
  <button type="submit">Save</button>
</form>
```

- `data-action` — declares this element triggers an interaction
- `data-payload` — JSON string sent with the action. **Must be valid JSON.** The frontend parses with `JSON.parse` inside a try/catch; malformed values are ignored with a console warning. Agents should use `JSON.stringify()` to produce this value, never string concatenation, to prevent injection via crafted payloads
- `data-element-id` — for targeted updates via `update_canvas`

## Files Summary

### New files (Phase 1)
| File | Purpose |
|------|---------|
| `src/gobby/mcp_proxy/tools/canvas.py` | Canvas tool registry |
| `web/src/components/CanvasRenderer.tsx` | HTML renderer with event delegation |
| `web/src/components/CanvasRenderer.css` | Canvas styles |
| `web/src/utils/sanitizeHtml.ts` | DOMPurify config |
| `tests/tools/test_canvas.py` | Backend unit tests |
| `tests/websocket/test_canvas_interaction.py` | WebSocket integration tests |

### Modified files (Phase 1)
| File | Change |
|------|--------|
| `src/gobby/mcp_proxy/registries.py` | Add canvas registry (~374) |
| `src/gobby/servers/websocket/server.py` | Add `canvas_interaction` to dispatch (line 209) |
| `src/gobby/servers/websocket/chat.py` | Add `_handle_canvas_interaction` handler |
| `src/gobby/servers/websocket/broadcast.py` | Add `canvas_event` to high-volume types |
| `web/src/components/ToolCallDisplay.tsx` | Add `isCanvasRender` + `CanvasDisplay` |
| `web/src/hooks/useChat.ts` | Add `respondToCanvas` + `canvas_event` handler |
| `web/package.json` | Add `dompurify` dependency |

## Verification

1. **Unit tests**: `tests/tools/test_canvas.py` — test render_canvas creates state, resolve_interaction unblocks, timeout returns error, clear_canvas cleans up
2. **Integration test**: `tests/websocket/test_canvas_interaction.py` — test full WebSocket round-trip: render → broadcast → interact → unblock
3. **Manual E2E**: Start daemon, open web UI, start a chat. Agent calls `render_canvas` with a simple button. Verify:
   - Canvas renders inline in chat
   - Button is clickable
   - Click sends `canvas_interaction` via WebSocket
   - Agent receives interaction result and continues
4. **Security**: Verify `<script>alert(1)</script>` is stripped, `onclick` handlers are stripped, `javascript:` URIs are stripped
5. **Cross-CLI**: From a terminal Claude Code session, call `render_canvas` via MCP. Verify web UI shows the canvas and interaction flows back
