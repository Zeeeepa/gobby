# Artifact Panel: Auto-Display Plans + Opt-In for Code Files

## Context

When the agent writes a plan file during plan mode, the plan is only visible as inline markdown in chat. The artifact sidepanel (markdown preview, code highlighting, versioning) is never used automatically. The `PlanApprovalBar` says "Review it above" but there's no way to re-open the plan after scrolling past or closing the panel. After rejecting a plan and requesting changes, the approval bar disappears entirely — no way to view the plan during revision.

For code files, the agent often writes multiple files rapidly (scaffolding). Auto-opening the artifact panel for each would be disruptive. Instead, users should opt-in by clicking an "Open in Panel" button on the inline Write tool preview.

## Approach

**Two-tier artifact display:**
1. **Plan files** (`.gobby/plans/*.md`, `.claude/plans/*.md`): Auto-display in artifact panel
2. **All other Write calls**: Opt-in via "Open in Panel" button on ToolCallCard

**Supporting features:**
- PlanApprovalBar "waiting" state after rejection with persistent View Plan button
- `/artifacts` slash command to toggle panel
- Mobile fullscreen overlay for artifact panel
- Agent system prompt explaining artifact behavior

## Phase 1: Foundation

**Goal**: Extract shared utility for language detection

### 1.1 Extract getLanguageFromPath to shared util [category: refactor]

Target: `web/src/utils/languages.ts` (new), `web/src/components/chat/ToolCallCard.tsx`

Extract `EXT_TO_LANGUAGE` (lines 31-37) and `getLanguageFromPath` (lines 62-65) from `ToolCallCard.tsx` into a shared utility module.

**Create `web/src/utils/languages.ts`:**

```typescript
export const EXT_TO_LANGUAGE: Record<string, string> = {
  py: 'python', tsx: 'tsx', ts: 'typescript', jsx: 'jsx', js: 'javascript',
  json: 'json', yaml: 'yaml', yml: 'yaml', md: 'markdown', css: 'css',
  html: 'html', sh: 'bash', bash: 'bash', zsh: 'bash', sql: 'sql',
  rs: 'rust', go: 'go', rb: 'ruby', java: 'java', c: 'c', cpp: 'cpp',
  h: 'c', hpp: 'cpp', toml: 'toml', xml: 'xml', svg: 'xml',
}

export function getLanguageFromPath(filePath: string): string {
  const ext = filePath.split('.').pop()?.toLowerCase() || ''
  return EXT_TO_LANGUAGE[ext] || 'text'
}
```

**Update `ToolCallCard.tsx`:** Remove local `EXT_TO_LANGUAGE` and `getLanguageFromPath`, import from `../../utils/languages`. All usages at lines 88, 108, 174 are unchanged.

## Phase 2: Plan File Auto-Display

**Goal**: Plan file writes auto-open in artifact panel

### 2.1 Detect plan file writes and create artifacts [category: code] (depends: 1.1)

Target: `web/src/hooks/useChat.ts`, `web/src/types/chat.ts`, `web/src/App.tsx`, `web/src/components/chat/ChatPage.tsx`

**Detection in useChat** — when `handleToolStatus` processes a Write to a plan file, store in state:

In `web/src/types/chat.ts`:
```typescript
// Add before ChatState
export interface PlanWriteInfo {
  toolCallId: string
  filePath: string
  content: string
}

// Add to ChatState (after line 75)
latestPlanWrite: PlanWriteInfo | null
conversationId?: string
```

In `web/src/hooks/useChat.ts`:
```typescript
// Module-level constant (after imports)
const PLAN_FILE_PATTERN = /[/\\]\.(?:claude|gobby)[/\\]plans[/\\].*\.md$/

// State (after planPendingApproval, line 187)
const [latestPlanWrite, setLatestPlanWrite] = useState<PlanWriteInfo | null>(null)

// Detection in handleToolStatus (after setIsThinking, line 436, before setMessages line 439)
if (status.status === 'calling' && status.tool_name === 'Write' && status.arguments) {
  const filePath = (status.arguments.file_path as string) || ''
  const content = (status.arguments.content as string) || ''
  if (filePath && content && PLAN_FILE_PATTERN.test(filePath)) {
    setLatestPlanWrite({ toolCallId: status.tool_call_id, filePath, content })
  }
}

// Return (after planPendingApproval, line 1042)
latestPlanWrite,
```

In `web/src/App.tsx` — destructure `latestPlanWrite` from useChat (line 33), pass through ChatState (line 392):
```typescript
latestPlanWrite,
conversationId,
```

**Artifact creation in ChatPage** — react to plan writes:

In `web/src/components/chat/ChatPage.tsx`:
```typescript
// Update import: add useRef, useEffect, useState
import { useCallback, useEffect, useRef, useState } from 'react'

// Add openArtifact to useArtifacts destructure (line 28-37)

// After openCodeAsArtifact (line 41):
const planArtifactMapRef = useRef<Map<string, string>>(new Map())
const lastPlanToolCallIdRef = useRef<string | null>(null)
const [planArtifactId, setPlanArtifactId] = useState<string | null>(null)

useEffect(() => {
  const pw = chat.latestPlanWrite
  if (!pw || pw.toolCallId === lastPlanToolCallIdRef.current) return
  lastPlanToolCallIdRef.current = pw.toolCallId

  const fileName = pw.filePath.split(/[/\\]/).pop() || 'plan'
  const title = fileName.replace(/\.md$/i, '').replace(/[-_]/g, ' ')

  const existingId = planArtifactMapRef.current.get(pw.filePath)
  if (existingId) {
    updateArtifact(existingId, pw.content)
    openArtifact(existingId)
    setPlanArtifactId(existingId)
  } else {
    const id = createArtifact('text', pw.content, undefined, title)
    planArtifactMapRef.current.set(pw.filePath, id)
    setPlanArtifactId(id)
  }
}, [chat.latestPlanWrite, createArtifact, updateArtifact, openArtifact])

// Reset on conversation switch
useEffect(() => {
  planArtifactMapRef.current = new Map()
  lastPlanToolCallIdRef.current = null
  setPlanArtifactId(null)
}, [chat.conversationId])
```

## Phase 3: PlanApprovalBar Enhancements

**Goal**: View Plan button + waiting state after rejection

### 3.1 Add PlanApprovalBar waiting state and View Plan button [category: code] (depends: 2.1)

Target: `web/src/hooks/useChat.ts`, `web/src/types/chat.ts`, `web/src/components/chat/PlanApprovalBar.tsx`, `web/src/components/chat/MessageList.tsx`, `web/src/components/chat/ChatPage.tsx`, `web/src/App.tsx`

**Problem**: After clicking "Request Changes", `planPendingApproval` becomes false and PlanApprovalBar disappears. User can't view the plan during revision.

**Fix**: Add `planFeedbackSent` state. After rejection, keep `planPendingApproval = true` and set `planFeedbackSent = true`. PlanApprovalBar shows a "waiting for revision" variant with View Plan button. When the agent's next stream completes in plan mode, reset `planFeedbackSent = false`.

In `web/src/hooks/useChat.ts`:
```typescript
// State (after planPendingApproval)
const [planFeedbackSent, setPlanFeedbackSent] = useState(false)

// Change requestPlanChanges (currently sets planPendingApproval=false):
const requestPlanChanges = useCallback((feedback: string) => {
  // ... existing WebSocket send ...
  setPlanFeedbackSent(true)  // Keep bar visible in waiting state
  // REMOVE: setPlanPendingApproval(false)
}, [])

// In handleChatStream, when chunk.done in plan mode (line 375-377):
if (currentModeRef.current === 'plan') {
  setPlanPendingApproval(true)
  setPlanFeedbackSent(false)  // Agent finished revising
}

// Return: add planFeedbackSent
```

In `web/src/types/chat.ts` — add to ChatState:
```typescript
planFeedbackSent: boolean
```

In `web/src/App.tsx` — destructure and pass `planFeedbackSent`.

In `PlanApprovalBar.tsx`:
```typescript
interface PlanApprovalBarProps {
  onApprove: () => void
  onRequestChanges: (feedback: string) => void
  onViewPlan?: () => void
  feedbackSent?: boolean
}

// Render three variants:
// 1. feedbackSent=true: "Revision in progress. Review the current plan while waiting."
//    + View Plan button only
// 2. onViewPlan present: "Review it in the side panel, then approve or request changes."
//    + View Plan + Approve + Request Changes
// 3. Default: "Review it above, then approve or request changes."
//    + Approve + Request Changes
```

In `MessageList.tsx` — add `onViewPlan` and `feedbackSent` props, pass to PlanApprovalBar.

In `ChatPage.tsx`:
```typescript
const handleViewPlan = useCallback(() => {
  if (planArtifactId) openArtifact(planArtifactId)
}, [planArtifactId, openArtifact])

// Pass to MessageList:
onViewPlan={planArtifactId ? handleViewPlan : undefined}
feedbackSent={chat.planFeedbackSent}
```

## Phase 4: Write Tool "Open in Panel"

**Goal**: Users can opt-in to view any Write tool output in the artifact panel

### 4.1 Add "Open in Panel" button to ToolCallCard [category: code] (depends: 1.1)

Target: `web/src/components/chat/artifacts/ArtifactContext.tsx`, `web/src/components/chat/ChatPage.tsx`, `web/src/components/chat/ToolCallCard.tsx`

**Extend ArtifactContext** — add `openFileAsArtifact` alongside existing `openCodeAsArtifact`:

In `ArtifactContext.tsx`:
```typescript
interface ArtifactContextValue {
  openCodeAsArtifact: (language: string, content: string, title?: string) => void
  openFileAsArtifact: (filePath: string, content: string) => void  // NEW
}
```

In `ChatPage.tsx` — create `openFileAsArtifact` callback:
```typescript
import { getLanguageFromPath } from '../../utils/languages'

const openFileAsArtifact = useCallback((filePath: string, content: string) => {
  const fileName = filePath.split(/[/\\]/).pop() || 'file'
  const isMarkdown = /\.md$/i.test(filePath)
  if (isMarkdown) {
    createArtifact('text', content, undefined, fileName)
  } else {
    const language = getLanguageFromPath(filePath)
    createArtifact('code', content, language, fileName)
  }
}, [createArtifact])

// Update ArtifactContext.Provider value:
<ArtifactContext.Provider value={{ openCodeAsArtifact, openFileAsArtifact }}>
```

In `ToolCallCard.tsx` — add "Open in Panel" button on Write tool argument display:

```typescript
// In ToolArgumentsContent, inside the Write pattern block (lines 87-103):
import { useArtifactContext } from './artifacts/ArtifactContext'

// Inside the component:
const { openFileAsArtifact } = useArtifactContext()

// After the SyntaxHighlighter (before closing </div>), add a button row:
<div className="flex justify-end mt-1">
  <button
    className="text-xs text-muted-foreground hover:text-foreground transition-colors"
    onClick={() => openFileAsArtifact(filePath, args.content as string)}
  >
    Open in panel
  </button>
</div>
```

This follows the same pattern as the existing "Open in panel" button on `CodeBlock.tsx` (line 62-64).

## Phase 5: /artifacts Command

**Goal**: Users can toggle artifact panel via slash command

### 5.1 Add /artifacts local slash command [category: code]

Target: `web/src/hooks/useSlashCommands.ts`, `web/src/App.tsx`, `web/src/components/chat/ChatPage.tsx`

**Register command** in `useSlashCommands.ts`:
```typescript
// Add to LOCAL_COMMANDS array:
{ name: 'artifacts', description: 'Toggle artifact panel', action: 'toggle_artifacts' },
```

**Handle in App.tsx** — dispatch custom event:
```typescript
// In handleSendMessage, local command handler (around line 196-219):
else if (cmd.tool === 'toggle_artifacts') {
  window.dispatchEvent(new CustomEvent('gobby:toggle-artifacts'))
}
```

**Listen in ChatPage.tsx** — toggle panel:
```typescript
useEffect(() => {
  const handler = () => {
    if (isPanelOpen) {
      closePanel()
    } else {
      // Re-open last artifact, or the plan artifact
      const lastId = planArtifactId
        || Array.from(fileArtifactMapRef?.current?.values() ?? []).pop()
      if (lastId) openArtifact(lastId)
    }
  }
  window.addEventListener('gobby:toggle-artifacts', handler)
  return () => window.removeEventListener('gobby:toggle-artifacts', handler)
}, [isPanelOpen, closePanel, openArtifact, planArtifactId])
```

## Phase 6: Mobile Support

**Goal**: Artifact panel works on mobile (<768px) as fullscreen overlay

### 6.1 Add mobile-responsive artifact panel styles [category: code]

Target: `web/src/components/chat/artifacts/ArtifactPanel.tsx`, `web/src/styles/index.css`

**In `ArtifactPanel.tsx`** — add `artifact-panel` class to root div (line 69):
```typescript
className="artifact-panel flex flex-col h-full border-l border-border bg-background shrink-0"
```

**In `web/src/styles/index.css`** — add media query (alongside existing 768px breakpoints):
```css
/* Artifact panel: fullscreen overlay on mobile */
@media (max-width: 768px) {
  [role="separator"][aria-label="Resize panel"] {
    display: none !important;
  }

  .artifact-panel {
    position: fixed !important;
    inset: 0 !important;
    width: 100% !important;
    z-index: 30;
    border-left: none !important;
  }
}
```

ResizeHandle targeted by its existing ARIA attributes — no changes needed to `ResizeHandle.tsx`.

## Phase 7: Agent Instructions

**Goal**: Agent knows about artifact panel behavior

### 7.1 Update system prompt for artifact behavior [category: config]

Target: `src/gobby/install/shared/prompts/chat/system.md`

Add a new section to the chat system prompt (after "## Using Tools" or "## How to Be") explaining artifact panel behavior:

```markdown
## Artifact Panel
The web UI has an artifact panel that displays file content with syntax highlighting (code) or markdown preview (text).

- **Plan files** (`.gobby/plans/*.md`, `.claude/plans/*.md`): Automatically displayed in the artifact panel when you Write them. Use Write (not Edit) for plan files so the full content appears in the panel. When revising a plan after user feedback, Write the full file again — the artifact updates with a new version.
- **Other files**: The user can click "Open in Panel" on any Write tool call to view it in the artifact panel. This is opt-in — files are not auto-displayed.
- **`/artifacts` command**: The user can type `/artifacts` to toggle the panel open/closed.
```

## Task Mapping

| Plan Item | Task Ref | Status |
|-----------|----------|--------|
| 1.1 Extract getLanguageFromPath to shared util | | |
| 2.1 Detect plan file writes and create artifacts | | |
| 3.1 Add PlanApprovalBar waiting state and View Plan button | | |
| 4.1 Add "Open in Panel" button to ToolCallCard | | |
| 5.1 Add /artifacts local slash command | | |
| 6.1 Add mobile-responsive artifact panel styles | | |
| 7.1 Update system prompt for artifact behavior | | |

## Verification

1. **Plan auto-display**: Enter plan mode, write a plan file — artifact panel opens with markdown preview
2. **Plan rewrite**: Request changes, agent rewrites plan — artifact updates (Version 2 of 2)
3. **Plan rejection UX**: Click "Request Changes" — bar shows "Revision in progress" with View Plan button
4. **Plan re-view**: Close panel during revision — View Plan button re-opens it
5. **Code opt-in**: Agent writes a `.ts` file — "Open in panel" button appears on inline preview — click opens artifact panel with syntax highlighting
6. **Rapid writes**: Agent writes 5 files quickly — no auto-open disruption, each has "Open in panel" button
7. **Non-plan .md**: Agent writes a README.md — "Open in panel" button shows, click opens markdown preview
8. **/artifacts command**: Type `/artifacts` — panel toggles open/closed
9. **Edit tool**: Verify Edit tool calls do NOT trigger auto-display or show "Open in panel"
10. **Conversation switch**: Switch conversations — plan artifact state resets
11. **Mobile overlay**: Resize to <768px — artifact panel is fullscreen, resize handle hidden
12. **Mobile close**: Tap Close — returns to chat
