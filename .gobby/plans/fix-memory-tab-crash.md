# Fix: Memory Tab Crash → Returns to Chat

## Root Cause

The Memory tab crashes because of a **two-layer failure**:

### Layer 1: The KnowledgeGraph (3D/WebGL) component crashes
- Neo4j is configured (`configured: true`), so `viewMode` auto-switches to `'knowledge'`
- The knowledge graph endpoint returns **955 entities + 2,238 relationships**
- `ForceGraph3D` (Three.js) creates 955 `SpriteText` objects — each one generates a hidden canvas + WebGL texture
- This can fail in several ways: WebGL context lost, texture memory exhaustion, context creation failure
- The crash happens **asynchronously** (in Three.js's `requestAnimationFrame` loop), which means React's `KnowledgeGraphErrorBoundary` **cannot catch it** — error boundaries only catch synchronous render/lifecycle errors

### Layer 2: No App-level error boundary
- When an unhandled error propagates, React 18 unmounts the entire root tree
- `App` re-mounts with `useState<string>('chat')` as the default → user lands on Chat
- This is the "goes black and returns to Chat" behavior

## Fix Plan

### 1. Add global ErrorBoundary in `App.tsx` (prevents the "return to chat" symptom)

Wrap the tab content area with a top-level error boundary that:
- Catches any render error from any tab
- Shows a "Something went wrong" UI with a "Return to Chat" button
- Includes a "Try Again" button that re-mounts the failed component
- Logs the error to console for debugging

### 2. Harden `KnowledgeGraph.tsx` against async Three.js crashes

- Add `window.addEventListener('error', ...)` inside the component to catch uncaught Three.js errors during the WebGL render loop
- Add `window.addEventListener('unhandledrejection', ...)` for promise-based failures
- On WebGL error: set an error state, show fallback UI ("3D graph unavailable"), offer to switch to 2D view
- Add a `canvas.addEventListener('webglcontextlost', ...)` handler on the ForceGraph3D canvas element
- Wrap the `nodeThreeObject` callback in try-catch (each SpriteText allocation)

### 3. Lower default knowledge graph limit

- Change `DEFAULT_KNOWLEDGE_GRAPH_LIMIT` from `5000` → `500` in `MemoryPage.tsx`
- 955 entities creating 955 Three.js sprites is excessive — start with 500, user can increase via the slider
- This reduces the WebGL texture pressure that likely triggers the crash

### 4. Add `KnowledgeGraph` graceful degradation

- If the 3D graph fails, automatically fall back to 2D `MemoryGraph` view
- Store the failure state so it doesn't keep retrying 3D on subsequent visits

## Files to Modify

| File | Changes |
|------|---------|
| `web/src/App.tsx` | Add `AppErrorBoundary` class component wrapping tab content |
| `web/src/components/KnowledgeGraph.tsx` | Add async error handlers, WebGL context-lost handler, try-catch in nodeThreeObject |
| `web/src/components/MemoryPage.tsx` | Change `DEFAULT_KNOWLEDGE_GRAPH_LIMIT` from 5000→500, add `onError` callback to auto-switch view mode on 3D failure |

## Implementation Order

1. `App.tsx` — Add global error boundary (immediate crash-to-chat prevention)
2. `MemoryPage.tsx` — Lower default limit + add onError view mode fallback
3. `KnowledgeGraph.tsx` — Add async error handling + WebGL context lost + SpriteText try-catch

## Verification

1. Navigate to Memory tab — should load without crashing
2. If 3D graph still fails, should show error UI (not crash to Chat)
3. Error boundary "Try Again" button should re-mount the failed tab
4. Lower limit (500) should reduce sprite count and memory pressure
5. WebGL context lost simulation: `canvas.getContext('webgl2').getExtension('WEBGL_lose_context').loseContext()` should trigger graceful fallback
