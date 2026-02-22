# A2UI Canvas Platform

## Context

The current plan at `docs/plans/a2ui-canvas.md` uses raw HTML with `data-action`/`data-payload` conventions. Two problems:

1. **Agents don't know how to use it** — no skill, no instructions teaching the convention
2. **HTML sanitization is complex and fragile** — dual sanitization, CSS blocklists, URI filters

We're replacing this with a full canvas platform inspired by OpenClaw's approach, built on Google's A2UI v0.8 protocol (Apache 2.0, github.com/google/A2UI). Two modes:

- **Inline A2UI surfaces** — declarative JSON components rendered in chat (forms, approvals, status cards)
- **Canvas panel** — sandboxed iframe panel for arbitrary HTML content, JS evaluation, screenshots

---

## Phase 1: Inline A2UI Surfaces + Canvas Panel Skeleton

### 1A. Backend: `gobby-canvas` Tool Registry

**New: `src/gobby/mcp_proxy/tools/canvas.py`**

Factory: `create_canvas_registry() -> InternalToolRegistry`
Pattern: `create_memory_registry()` from `src/gobby/mcp_proxy/tools/memory.py`

**State:**
```python
@dataclass
class CanvasState:
    canvas_id: str
    mode: str                     # "a2ui" or "html"
    surface: dict[str, Any]       # component map {id: component_def} (a2ui mode)
    data_model: dict[str, Any]    # bound data (a2ui mode)
    root_component_id: str | None
    html_url: str | None          # URL for html mode
    conversation_id: str
    pending_event: asyncio.Event | None
    interaction_result: dict | None
    created_at: datetime
    expires_at: datetime
    completed: bool = False
```

**Bounds:** `MAX_CANVASES_PER_CONVERSATION=50`, `MAX_TOTAL_CANVASES=1000`, `MAX_COMPONENT_COUNT=200`, `MAX_DATA_MODEL_SIZE=64KB`, `MAX_RENDER_RATE=10/min/conversation`

**Phase 1 Tools:**

| Tool | Purpose |
|------|---------|
| `render_surface(components, root_id, canvas_id, data_model, blocking, timeout, conversation_id)` | A2UI mode: validate types against catalog, store, broadcast, optionally block |
| `update_surface(canvas_id, components, data_model)` | Merge A2UI updates, broadcast |
| `delete_surface(canvas_id)` | Remove + broadcast |
| `wait_for_interaction(canvas_id, timeout)` | Block on non-blocking surface |
| `canvas_present(target, canvas_id, title, width, height, conversation_id)` | HTML mode: open canvas panel with URL/path |
| `canvas_hide(canvas_id)` | Hide/close canvas panel |

**Registry API (for WebSocket handler):** `get_canvas()`, `resolve_interaction()` (per-canvas lock), `cancel_conversation_canvases()`, `sweep_expired()`

**A2UI catalog (validated server-side):** `Text`, `Button`, `TextField`, `CheckBox`, `Row`, `Column`, `Card`, `List`, `Image`, `Icon`, `Badge`

### 1B. Canvas Host Route

**Modify: `src/gobby/servers/http.py`**

Add static file serving route for canvas content, following existing `StaticFiles` pattern (line 604):

```python
# Serve canvas files from configurable directory
# Default: ~/.gobby/canvas/ (global) or .gobby/canvas/ (project)
app.mount("/__gobby__/canvas", StaticFiles(directory=canvas_root), name="canvas-files")
```

Agents write HTML files, then call `canvas_present(target="/__gobby__/canvas/my-app.html")` to show them.

### 1C. Backend Wiring

| File | Line | Change |
|------|------|--------|
| `src/gobby/mcp_proxy/registries.py` | after 383 | Add canvas registry |
| `src/gobby/servers/websocket/server.py` | 233 | Add `"canvas_interaction"` to dispatch |
| `src/gobby/servers/websocket/chat.py` | new method | `_handle_canvas_interaction` (pattern: `_handle_ask_user_response` at line 757) |
| `src/gobby/servers/websocket/broadcast.py` | line 41 | Add `"canvas_event"` to high-volume set + `broadcast_canvas_event()` |
| `src/gobby/servers/http.py` | lifespan + routes | Wire broadcast, start sweeper, add canvas host route |

### 1D. WebSocket Protocol

**Server → Client:**
```json
{"type": "canvas_event", "event": "surface_update|begin_rendering|data_model_update|delete_surface|interaction_confirmed|panel_present|panel_hide", "canvas_id": "...", "conversation_id": "...", "payload": {}}
```

**Client → Server:**
```json
{"type": "canvas_interaction", "canvas_id": "...", "action": {"name": "approve", "sourceComponentId": "approve-btn", "timestamp": "...", "context": {}}}
```

### 1E. Frontend: React A2UI Renderer

**New: `web/src/components/canvas/`**

```
canvas/
  index.ts                          # barrel export
  types.ts                          # BoundValue, Action, ChildrenSpec, A2UISurfaceState, UserAction
  A2UIRenderer.tsx                  # resolve component tree, handle actions, dim on completed
  A2UIComponentRegistry.tsx         # type name -> React component map + RenderComponent
  hooks/
    useA2UIDataModel.ts             # data model state + BoundValue resolution (JSON pointer)
    useCanvasPanel.ts               # panel state: open/width/activeCanvas (localStorage)
  components/
    A2UIText.tsx                    # -> <p>/<h1>-<h3> via usageHint
    A2UIButton.tsx                  # -> Button (CVA from ui/Button.tsx)
    A2UITextField.tsx               # -> <input> with label
    A2UICheckBox.tsx                # -> <input type="checkbox">
    A2UIRow.tsx                     # -> div.flex.flex-row
    A2UIColumn.tsx                  # -> div.flex.flex-col
    A2UICard.tsx                    # -> div.rounded-lg.border.border-border
    A2UIList.tsx                    # -> <ul>
    A2UIImage.tsx                   # -> <img> (src validated: https/data:image only)
    A2UIIcon.tsx                    # -> SVG icon
    A2UIBadge.tsx                   # -> Badge (CVA from ui/Badge.tsx)
  CanvasPanel.tsx                   # Right-side panel with sandboxed iframe
  CanvasPanelHeader.tsx             # Title, badges, close button (pattern: ArtifactPanel)
```

**A2UI types:**
- `BoundValue`: `{literalString?: string, path?: string}`
- `Action`: `{name: string, context?: Record<string, BoundValue>}`
- `ChildrenSpec`: `{explicitList?: string[]}`

### 1F. Canvas Panel (iframe)

**New: `web/src/components/canvas/CanvasPanel.tsx`**

Follows `ArtifactPanel` pattern from `web/src/components/chat/artifacts/ArtifactPanel.tsx`:
- Right-side collapsible panel with `ResizeHandle` (reuse `web/src/components/chat/artifacts/ResizeHandle.tsx`)
- Panel state via `useCanvasPanel` hook (localStorage persistence, same pattern as `useArtifacts`)
- Contains sandboxed iframe: `<iframe sandbox="allow-scripts" src={canvasUrl} />`
- postMessage bridge for bidirectional communication (eval results, snapshot requests, user actions)

**Modify: `web/src/components/chat/ChatPage.tsx`**

Add CanvasPanel alongside ArtifactPanel in the layout. When canvas is active, it takes the right panel slot (same position as artifacts).

### 1G. Frontend Integration

| File | Change |
|------|--------|
| `web/src/components/chat/ToolCallCard.tsx` (line 225) | Add `isCanvasRender()` detection + `CanvasSurfaceCard` |
| `web/src/hooks/useChat.ts` | Subscribe to `canvas_event`, add surface state, `respondToCanvas`, handle `panel_present`/`panel_hide` |
| `web/src/components/chat/ChatPage.tsx` | Add `CanvasPanel` to layout (right panel slot) |

### 1H. Skill Source Filtering (prerequisite)

The canvas skill must auto-inject for web UI sessions but stay hidden from CLI agents. The skill injection system needs a `sources` filter.

**Modify: `src/gobby/skills/parser.py`** — Add `sources` to `SkillAudienceConfig` (line ~52):
```python
sources: list[str] | None = None  # Session sources, e.g. ["claude_sdk_web_chat"]
```

**Modify: `src/gobby/skills/injector.py`** — Add source check in `_matches_audience()` (line ~210):
```python
# Source check (web UI vs CLI)
if config.sources is not None:
    if context.source not in config.sources:
        return False
```

This uses existing infrastructure:
- `AgentContext.source` already populated from session (`src/gobby/agents/context.py:36`)
- `SessionSource.CLAUDE_SDK_WEB_CHAT` identifies web sessions (`src/gobby/hooks/events.py:63`)
- Web chat sets `source="claude_sdk_web_chat"` at creation (`src/gobby/servers/websocket/chat.py:191`)

### 1I. Agent Skill

**New: `src/gobby/install/shared/skills/canvas/SKILL.md`**

```yaml
---
name: canvas
description: Render interactive A2UI surfaces and present HTML content in the canvas panel
category: core
alwaysApply: true
metadata:
  gobby:
    audience: all
    sources: ["claude_sdk_web_chat"]
---
```

`alwaysApply: true` + `sources: ["claude_sdk_web_chat"]` = auto-injects for web UI sessions, invisible to CLI agents.

Skill body teaches:
1. **Two modes**: inline A2UI surfaces (forms, approvals) vs canvas panel (full HTML apps, visualizations)
2. **A2UI component catalog** — all 11 types with properties and JSON examples
3. **Data binding** — BoundValue literals vs paths
4. **Actions** — definition and interaction result format
5. **Copy-paste patterns** — approval form, input form, status card, selection list
6. **Canvas panel workflow** — write HTML file → `canvas_present` → user interacts → `canvas_hide`
7. **When to use what** — AskUserQuestion for simple choices, inline A2UI for rich forms, canvas panel for full apps

### 1I. Security

**A2UI inline surfaces** — security by construction:
- Agents produce JSON, client renders only trusted React components
- Backend rejects unknown component types
- No `dangerouslySetInnerHTML` — BoundValue rendered as text content
- Image src validated

**Canvas panel** — iframe sandbox:
- `sandbox="allow-scripts"` — JS runs but no same-origin access to parent
- Content served from `/__gobby__/canvas/` route (not same origin as app)
- postMessage bridge validates message origin
- File serving validates paths to prevent directory traversal

---

## Phase 2: Rich Canvas (eval, snapshot, navigate)

| Tool | Purpose |
|------|---------|
| `canvas_eval(canvas_id, js)` | Execute JS in sandboxed iframe via postMessage, return result |
| `canvas_snapshot(canvas_id, format)` | Capture iframe content (html2canvas injected via postMessage bridge) |
| `canvas_navigate(canvas_id, url)` | Change iframe URL |

**postMessage bridge protocol** (injected into iframe):
```javascript
// Parent → iframe
{type: "gobby_eval", id: "req-1", code: "document.title"}
{type: "gobby_snapshot", id: "req-2", format: "jpeg"}

// iframe → parent
{type: "gobby_eval_result", id: "req-1", result: "My Page"}
{type: "gobby_snapshot_result", id: "req-2", data: "data:image/jpeg;base64,..."}
{type: "gobby_user_action", action: {name: "...", context: {}}}
```

**Live reload**: WebSocket listener in iframe reloads on file change events (same pattern as OpenClaw's chokidar-based approach, but using Gobby's existing WebSocket infrastructure).

**A2UI in panel**: Render A2UI surfaces in the canvas panel (not just inline) for multi-surface layouts.

## Phase 3: Persistence + Templates

- SQLite `canvas_surfaces` table
- REST endpoints `/api/canvas/{conversation_id}`
- Template library: `render_surface(template="approval_form", variables={...})`

---

## Files Summary

### New (Phase 1): 18
| File | Purpose |
|------|---------|
| `src/gobby/mcp_proxy/tools/canvas.py` | Tool registry + state |
| `src/gobby/install/shared/skills/canvas/SKILL.md` | Agent skill |
| `web/src/components/canvas/types.ts` | TypeScript types |
| `web/src/components/canvas/A2UIRenderer.tsx` | Top-level A2UI renderer |
| `web/src/components/canvas/A2UIComponentRegistry.tsx` | Catalog map |
| `web/src/components/canvas/hooks/useA2UIDataModel.ts` | Data model + BoundValue |
| `web/src/components/canvas/hooks/useCanvasPanel.ts` | Panel state (localStorage) |
| `web/src/components/canvas/components/A2UIText.tsx` | Text |
| `web/src/components/canvas/components/A2UIButton.tsx` | Button |
| `web/src/components/canvas/components/A2UITextField.tsx` | TextField |
| `web/src/components/canvas/components/A2UICheckBox.tsx` | CheckBox |
| `web/src/components/canvas/components/A2UIRow.tsx` | Row |
| `web/src/components/canvas/components/A2UIColumn.tsx` | Column |
| `web/src/components/canvas/components/A2UICard.tsx` | Card |
| `web/src/components/canvas/CanvasPanel.tsx` | Right-side iframe panel |
| `web/src/components/canvas/CanvasPanelHeader.tsx` | Panel header (title, close) |
| `web/src/components/canvas/index.ts` | Barrel export |
| `tests/mcp_proxy/tools/test_canvas.py` | Backend tests |

### Modified (Phase 1): 10
| File | Change |
|------|--------|
| `src/gobby/skills/parser.py` (line ~52) | Add `sources` field to `SkillAudienceConfig` |
| `src/gobby/skills/injector.py` (line ~210) | Add source check in `_matches_audience()` |
| `src/gobby/mcp_proxy/registries.py` (after line 383) | Add canvas registry |
| `src/gobby/servers/websocket/server.py` (line 233) | Add dispatch entry |
| `src/gobby/servers/websocket/chat.py` | Add handler |
| `src/gobby/servers/websocket/broadcast.py` (line 41) | Add event type |
| `src/gobby/servers/http.py` | Canvas host route + wiring |
| `web/src/components/chat/ToolCallCard.tsx` (line 225) | Add A2UI detection |
| `web/src/hooks/useChat.ts` | Canvas state + events + callback |
| `web/src/components/chat/ChatPage.tsx` | Add CanvasPanel to layout |

### Replaced
| `docs/plans/a2ui-canvas.md` | Replace with this plan |

---

## Verification

1. **Backend tests** (`uv run pytest tests/mcp_proxy/tools/test_canvas.py -v`): render creates state, blocking unblocks, timeout error, unknown types rejected, rate limiting, first-wins lock, disconnect cancellation, sweeper, canvas_present creates panel state

2. **Frontend tests** (Vitest): A2UI renderer builds tree, BoundValue resolution, unknown type error, action callbacks, panel open/close/resize

3. **A2UI E2E**: agent calls `render_surface` with approval form → renders inline → click Approve → agent gets result → surface dims

4. **Canvas panel E2E**: agent writes HTML file → calls `canvas_present` → panel opens with iframe → user sees content → `canvas_hide` closes panel

5. **Cross-CLI**: terminal Claude Code calls tools via MCP → web UI renders inline surfaces and opens panel

6. **Security**: unknown A2UI types rejected, BoundValue never renders as HTML, iframe sandboxed, canvas host validates paths

7. **Skill source filtering**: verify canvas skill injected for `source="claude_sdk_web_chat"` sessions, NOT injected for `source="claude"` / `source="gemini"` CLI sessions
