# Fix UI Bugs: Project Selector, Branch Selector, Chat Deletion

## Summary

Three related UI bugs in the web frontend, ranging from cosmetic (z-index) to data-integrity (chat deletion). All live in the `web/src/` directory.

---

## Bug 1: Project Selector Dropdown Behind Chat Selector (#9165 → #9168)

**Root Cause:** `ProjectSelector.tsx` line 73 uses Tailwind `z-10` for the dropdown. The `ConversationPicker` sidebar establishes a stacking context that renders above it.

**Fix:**
- **File:** `web/src/components/ProjectSelector.tsx`
- **Change:** Replace `z-10` with `z-50` on the dropdown container (line 73)
- **Why z-50:** Clears sidebar (z-10 range) while staying well below modals (z-100+)

**Verification:**
1. Open project selector → dropdown renders above chat sidebar
2. Open a modal → modal still renders above dropdown
3. Test with sidebar both collapsed and expanded

---

## Bug 2: Branch Selector Visible on Personal Project (#9166 → #9169)

**Root Cause:** The git branch selector renders unconditionally regardless of the active project context. Personal projects have no git repo, so the branch selector is meaningless.

**Fix:**
- **File:** `web/src/App.tsx` (where BranchSelector is rendered)
- **Change:** Wrap the branch selector render in a conditional:
  ```tsx
  {selectedProject && selectedProject.slug !== '_personal' && (
    <BranchSelector ... />
  )}
  ```
- **Alternative:** Check if the project has a `path` / `repo_path` property rather than string-matching `_personal`

**Verification:**
1. Switch to personal project → branch selector disappears
2. Switch to git-backed project → branch selector appears
3. Fresh page load with personal project → no branch selector
4. No layout shift or flicker

---

## Bug 3: Chat Deletion Doesn't Persist (#9167 → #9170, #9171)

**Root Cause:** `handleDeleteConversation` in `App.tsx:315` does two things in parallel:
1. Sends `delete_chat` via WebSocket → backend soft-deletes in DB
2. Calls `removeSession()` → removes from React state immediately

The local removal **always succeeds**, masking any WebSocket failure. If the WS send fails (disconnected, race condition, stale external_id), the session disappears from the UI but lives on in the DB. On the next 30-second poll, it reappears — a zombie session.

**Fix (two phases):**

### Phase 1: Audit (#9170 - research)
- Verify `external_id` is always populated on sessions loaded from the DB
- Check if WebSocket readyState guard in `useChat.ts:951` silently swallows failures
- Trace the full path: `deleteConversation()` → WS message → `session_control.py:479` → DB update
- Confirm `chat_deleted` ACK message is sent back and handled on the frontend

### Phase 2: Fix (#9171 - code, depends on #9170)
- **File:** `web/src/App.tsx` — `handleDeleteConversation` callback
- **File:** `web/src/hooks/useChat.ts` — `deleteConversation` function
- **File:** `web/src/hooks/useSessions.ts` — add pending state support
- **Changes:**
  1. Don't call `removeSession()` immediately — mark session as "deleting" (CSS dim + spinner)
  2. Listen for `chat_deleted` WebSocket message before removing from state
  3. If no ACK within 5 seconds, restore session and show error toast
  4. Filter `status: 'deleted'` sessions from the poll response in `useSessions.ts` as a safety net

**Verification:**
1. Delete chat with good connection → pending state → removed
2. Delete chat with no WS → session stays, error shown
3. Deleted sessions don't reappear on 30s poll refresh
4. Delete active conversation → resets to new chat correctly

---

## Implementation Order

1. **#9168** — z-index fix (1 line change, instant win)
2. **#9169** — branch selector conditional (small, isolated)
3. **#9170** — audit chat deletion flow (research, informs fix)
4. **#9171** — implement confirmed deletion pattern (depends on #9170)

## Files Touched

| File | Bugs |
|------|------|
| `web/src/components/ProjectSelector.tsx` | #9168 |
| `web/src/App.tsx` | #9169, #9171 |
| `web/src/hooks/useChat.ts` | #9171 |
| `web/src/hooks/useSessions.ts` | #9171 |
| `web/src/styles/index.css` | #9171 (pending state styles) |
