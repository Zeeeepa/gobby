# Fix: Web Chat Title Synthesis Race Condition

## Root Cause

The title synthesis in `App.tsx` fires when `isStreaming` transitions `true → false`. It looks up the current session in `sessionsRef.current` (the in-memory sessions list from `useSessions`) to get the DB session ID, then calls `POST /sessions/{id}/synthesize-title`.

**For new chats, this lookup always fails** because of two compounding timing issues:

### Issue 1: Stale sessions list
The sessions list polls every 30 seconds (`useSessions.ts:44`). When the first response completes:
1. The session was JUST registered in the DB during `_create_chat_session()` (chat.py:222)
2. The sessions list hasn't polled since registration
3. `sessionsRef.current.find()` returns `undefined` → no synthesis

### Issue 2: external_id swap
Even if the list were fresh, the `external_id` changes mid-response:
1. Session registers with `external_id = frontendUUID` (chat.py:224)
2. Done chunk updates DB `external_id` to `sdk_session_id` (chat.py:773)
3. Frontend `conversationId` also changes to `sdk_session_id` (useChat.ts:479-480)
4. The stale list (if it had the session) would have the OLD `external_id`

### Why some chats DO get titles
After a 30s poll refreshes the list, the session appears with the updated `external_id`. The `needsTitle` check (`!currentSession.title`) is true, so the NEXT streaming completion triggers synthesis. Chats that have multiple exchanges spanning >30s eventually get titles.

## Fix

**Send `db_session_id` from the backend to the frontend**, so title synthesis can call the API directly without needing the sessions list lookup.

### 1. Backend: `src/gobby/servers/websocket/chat.py`

**Add `db_session_id` to `session_info` message** (~line 558):
```python
session_info_msg = _base_msg(
    type="session_info",
    conversation_id=conversation_id,
)
# Include DB session ID so frontend can call session API directly
db_sid = getattr(session, "db_session_id", None)
if db_sid:
    session_info_msg["db_session_id"] = db_sid
```

### 2. Frontend: `web/src/hooks/useChat.ts`

**Track `dbSessionId` from `session_info` message**:
- Add `dbSessionId` state (alongside `sessionRef`, `currentBranch`, etc.)
- Extract from `session_info` WS message
- Reset on conversation switch / new chat
- Expose in return value

### 3. Frontend: `web/src/App.tsx`

**Rewrite title synthesis to use `dbSessionId` directly**:
```typescript
// Get dbSessionId from useChat (set by backend session_info message)
const { dbSessionId, ... } = useChat()

useEffect(() => {
  if (wasStreamingRef.current && !isStreaming) {
    titleSynthesisCountRef.current += 1

    if (dbSessionId) {
      // Check existing sessions list for current title (if available)
      const currentSession = sessionsRef.current.find(
        (s) => s.id === dbSessionId
      )
      const needsTitle = !currentSession?.title
      const periodicUpdate = titleSynthesisCountRef.current >= 4

      if (needsTitle || periodicUpdate) {
        titleSynthesisCountRef.current = 0
        const baseUrl = import.meta.env.VITE_API_BASE_URL || ''
        fetch(`${baseUrl}/sessions/${dbSessionId}/synthesize-title`, { method: 'POST' })
          .then((res) => res.ok ? res.json() : null)
          .then((data) => {
            if (data?.title) refreshSessionsRef.current()
          })
          .catch(() => {})
      }
    }
  }
  wasStreamingRef.current = isStreaming
}, [isStreaming, conversationId, dbSessionId])
```

Key changes:
- Uses `dbSessionId` directly → no dependence on stale sessions list
- Looks up session by `s.id === dbSessionId` (stable PK) instead of `s.external_id` (which changes)
- `needsTitle` falls back to true when session isn't in list (new chat case)
- Calls `refreshSessionsRef.current()` after successful synthesis to update sidebar

## Implementation Order

1. Backend: add `db_session_id` to `session_info` message
2. Frontend: track `dbSessionId` in `useChat.ts`, expose it
3. Frontend: rewrite title synthesis in `App.tsx` to use it
4. Test: new chat → first response should synthesize title

## Verification

1. Start new web chat, send one message → title should appear in sidebar within seconds
2. Existing chats should continue to get periodic title updates
3. Check daemon logs: `POST /sessions/{id}/synthesize-title` should return 200
4. Check that `session_info` WS message includes `db_session_id`
