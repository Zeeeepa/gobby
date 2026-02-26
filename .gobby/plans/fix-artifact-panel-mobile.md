# Plan: Fix Artifact Panel on Mobile

## Problems

1. **Artifact panel overflows on mobile** — Panel uses a fixed pixel `width` (480px default) with `shrink-0`, but mobile viewports are ~375px. Text and code blocks get clipped on the right edge.
2. **Context pie bleeds through** — The `ContextUsageIndicator` SVG ring in `ChatInput` is visible behind/through the artifact panel because the chat column isn't hidden when the artifact panel is open on mobile.

Both stem from the same root cause: **no mobile-specific layout for the artifact panel**.

## Approach: Full-Width Overlay on Mobile

On screens below `md` (768px), the artifact panel should:
- Take **full width** (`w-full`) instead of a fixed pixel width
- **Hide the chat column** underneath (or overlay with proper z-index)
- **Hide the resize handle** (no room to resize on mobile)
- Show a more prominent close button for navigation back

## Files to Modify

### 1. `web/src/components/chat/ChatPage.tsx`

In the inner flex layout (line 122), conditionally render based on screen size:

```tsx
{/* Artifact or Canvas panel */}
{canvas.isPanelOpen && canvas.activeCanvas ? (
  <CanvasPanel ... />
) : isPanelOpen && activeArtifact ? (
  <>
    {/* Hide resize handle on mobile */}
    <div className="hidden md:block">
      <ResizeHandle onResize={setPanelWidth} panelWidth={panelWidth} />
    </div>
    <ArtifactPanel
      artifact={activeArtifact}
      width={panelWidth}
      onClose={closePanel}
      ...
    />
  </>
) : null}
```

And conditionally hide the chat column on mobile when artifact is open:

```tsx
{/* Chat column — hidden on mobile when artifact panel is open */}
<div className={cn(
  "flex flex-col flex-1 min-w-0",
  isPanelOpen && activeArtifact && "hidden md:flex"
)}>
```

### 2. `web/src/components/chat/artifacts/ArtifactPanel.tsx`

Make the panel responsive. On mobile, ignore the `width` prop and go full-width:

```tsx
<div
  className="flex flex-col h-full border-l border-border bg-background
             w-full md:shrink-0"
  style={{ width: undefined }}  // handled via className on mobile
>
```

More precisely — use a media query approach:
- Mobile (`< md`): `w-full` (ignore `width` prop)
- Desktop (`>= md`): `shrink-0` with `style={{ width }}`

Implementation: use a wrapper approach or a CSS class that overrides the inline style on mobile:

```tsx
<div
  className={cn(
    "flex flex-col h-full border-l border-border bg-background",
    "w-full md:w-auto md:shrink-0"
  )}
  style={{ '--panel-width': `${width}px` } as React.CSSProperties}
>
```

With a corresponding CSS rule:
```css
@media (min-width: 768px) {
  [style*='--panel-width'] {
    width: var(--panel-width) !important;
  }
}
```

**Or simpler**: just pass the width conditionally using a `useMediaQuery` hook or `window.innerWidth` check. Given Tailwind's approach, the cleanest option is:

- Remove `shrink-0` from the panel
- Add responsive classes: `w-full md:w-auto md:shrink-0 md:basis-auto`
- Only apply `style={{ width }}` on `md+` screens via a simple hook

### 3. Add a `useIsMobile` hook (if not already present)

```ts
// web/src/hooks/useIsMobile.ts
import { useState, useEffect } from 'react'

export function useIsMobile(breakpoint = 768) {
  const [isMobile, setIsMobile] = useState(
    typeof window !== 'undefined' ? window.innerWidth < breakpoint : false
  )
  useEffect(() => {
    const mq = window.matchMedia(`(max-width: ${breakpoint - 1}px)`)
    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches)
    mq.addEventListener('change', handler)
    setIsMobile(mq.matches)
    return () => mq.removeEventListener('change', handler)
  }, [breakpoint])
  return isMobile
}
```

### 4. Wire it together in `ChatPage.tsx`

```tsx
const isMobile = useIsMobile()

// In the artifact panel section:
<ArtifactPanel
  artifact={activeArtifact}
  width={isMobile ? undefined : panelWidth}  // full-width on mobile
  onClose={closePanel}
  ...
/>
```

And in `ArtifactPanel.tsx`, make `width` optional:

```tsx
interface ArtifactPanelProps {
  width?: number  // undefined = full width
  ...
}

// In the render:
<div
  className="flex flex-col h-full border-l border-border bg-background"
  style={width ? { width, flexShrink: 0 } : { width: '100%' }}
>
```

## Implementation Order

1. Create `useIsMobile` hook
2. Update `ArtifactPanel` — make `width` optional, full-width when undefined
3. Update `ChatPage` — hide chat column on mobile when artifact open, hide resize handle, pass `undefined` width on mobile
4. Test on mobile viewport sizes

## Verification

- Open dev tools, toggle mobile viewport (375px, 390px, 414px)
- Open an artifact/plan — should be full width, no horizontal overflow
- Context pie should NOT be visible behind the artifact
- Code blocks should wrap or scroll horizontally within the panel
- Close button should return to chat view
- On desktop (>768px), behavior should be unchanged (fixed width + resize handle)
