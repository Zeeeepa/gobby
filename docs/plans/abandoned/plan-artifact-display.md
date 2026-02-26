# Plan: Auto-Display Plans in Artifact Sidepanel

## Problem
When the agent is in plan mode and finishes streaming, the `PlanApprovalBar` says "Review it above" — but the plan is just inline markdown in the chat. There's no artifact panel showing the plan in a dedicated, readable view. The user has to scroll through chat to find and read the plan.

## Root Cause
There's no connection between plan mode and the artifact system. The pieces exist independently:
- **Artifact system**: `useArtifacts` hook creates artifacts → opens `ArtifactPanel` sidepanel. Supports `text` type with markdown rendering via `ArtifactTextView`.
- **Plan mode**: Backend detects `ExitPlanMode` tool → broadcasts `mode_changed` → frontend sets `planPendingApproval=true` → shows `PlanApprovalBar`.
- **Plan file writes**: Backend allows Write/Edit to `.gobby/plans/*.md` and `~/.claude/plans/*.md` during plan mode (regex: `_PLAN_FILE_PATTERN`).
- **Tool status events**: Every Write tool call emits `tool_status` with `status: "calling"` (includes `arguments.file_path` and `arguments.content`) and `status: "completed"`.

**The gap**: Nothing watches for Write tool calls to plan files and auto-creates an artifact from the content.

## Solution

### Approach: Detect plan file writes in tool_status handler, auto-create artifact

When a `tool_status` event arrives with `status: "calling"` for a Write tool targeting a plan file path, extract the content and create/update a text artifact in the sidepanel.

### Files to Modify

#### 1. `web/src/hooks/useChat.ts` — Detect plan file writes
In `handleToolStatus`, when we see a Write tool call to a `.gobby/plans/` or `.claude/plans/` path:
- Extract `file_path` and `content` from `status.arguments`
- Call a new callback (e.g. `onPlanFileWritten(title, content)`) passed from ChatPage

**Changes:**
- Add `onPlanFileWritten` callback ref to the hook
- In `handleToolStatus`, when `status.status === 'calling'` and tool_name matches `Write` and file_path matches plan pattern → invoke callback

#### 2. `web/src/components/chat/ChatPage.tsx` — Wire artifact creation
- When `onPlanFileWritten` fires, call `createArtifact('text', content, undefined, title)` to open the plan in the artifact panel
- If the plan artifact already exists (same file path), call `updateArtifact` to add a new version instead

**Changes:**
- Add `onPlanFileWritten` callback that creates/updates an artifact
- Track plan artifact ID by file path (Map or ref)
- Wire callback into useChat

#### 3. `web/src/components/chat/PlanApprovalBar.tsx` — Minor UX improvement
- Update the message from "Review it above" to "Review the plan in the side panel" when an artifact is open
- (Optional) Add a button to re-open the artifact panel if the user closed it

### Alternative Considered: Backend emits a `plan_file_written` WebSocket event
More explicit but requires backend changes. The frontend-only approach is simpler since the data is already in tool_status events — the Write tool's `arguments` contain both `file_path` and `content`.

## Implementation Order

1. **`useChat.ts`** — Add plan file detection in `handleToolStatus`
2. **`ChatPage.tsx`** — Wire `onPlanFileWritten` → `createArtifact`
3. **`PlanApprovalBar.tsx`** — Update copy to reference side panel
4. **Test** — Enter plan mode, write a plan file, verify artifact panel opens with markdown preview

## Detection Logic (Frontend)

```typescript
const PLAN_FILE_PATTERN = /[/\\]\.(?:claude|gobby)[/\\]plans[/\\].*\.md$/

function isPlanFileWrite(toolStatus: ToolStatusMessage): boolean {
  if (toolStatus.status !== 'calling') return false
  const toolName = toolStatus.tool_name || ''
  // Native Write tool or Claude Code's file write
  if (toolName !== 'Write') return false
  const filePath = (toolStatus.arguments?.file_path as string) || ''
  return PLAN_FILE_PATTERN.test(filePath)
}
```

## Verification Steps

1. Start a web chat session in plan mode
2. Ask the agent to plan a feature → agent writes `.gobby/plans/some-plan.md`
3. Verify artifact panel opens automatically with the plan content rendered as markdown
4. Verify `PlanApprovalBar` text references the side panel
5. Close the panel, verify a "View Plan" button re-opens it
6. Request changes → agent rewrites plan → verify artifact updates (new version)
7. Verify non-plan Write tool calls do NOT trigger artifact creation
