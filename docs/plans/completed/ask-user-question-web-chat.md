# Plan: AskUserQuestion Response Mechanism for Web Chat UI

## Overview

The web chat UI renders AskUserQuestion tool calls as interactive cards, but users can't respond — options are display-only. The Claude Agent SDK's `can_use_tool` callback is the mechanism for intercepting AskUserQuestion and providing user answers. Currently, ChatSession uses `permission_mode="bypassPermissions"` which auto-approves all tools without the callback.

Replace `permission_mode="bypassPermissions"` with a `can_use_tool` callback on ChatSession. When AskUserQuestion is intercepted, the callback blocks (via `asyncio.Event`) until the web UI sends the user's answers through a new `ask_user_response` WebSocket message. All other tools are auto-approved.

## Constraints

- No new WebSocket message type needed for showing questions — the existing `tool_status` with `status: "calling"` already delivers AskUserQuestion to the frontend
- One pending question per session — Claude processes sequentially, so only one AskUserQuestion can be pending at a time per ChatSession (no queue needed)
- `asyncio.Event` works because anyio on asyncio wraps asyncio tasks; `provide_answer()` called from asyncio WebSocket handler crosses tasks safely via `event.set()`
- Removing `permission_mode="bypassPermissions"` means all tool calls go through `can_use_tool` — the auto-approve path is instant, so overhead is negligible
- Session-lifecycle failover (SDK sessions not firing SessionStart hooks) is a separate concern — tracked independently, not part of this plan

## Timeouts and Validation

- **Timeout**: User response should timeout after 300 seconds (configurable) to prevent blocking the agent indefinitely. On timeout, `_can_use_tool` should return a rejection or default value.
- **Validation**: `answers` payload from WebSocket must be validated against the `options` provided in the tool call. Reject invalid or extra keys.
- **Disconnect**: If client disconnects while question is pending, pause the timer. Resume on reconnect? Or reject immediately? Policy: Reject immediately to free up the agent.

## Phase 1: Backend — ChatSession can_use_tool callback

- [ ] Add `_can_use_tool()` async callback, pending question state fields, and `provide_answer()` method to ChatSession (category: code)
  - Remove `permission_mode="bypassPermissions"`, add `can_use_tool=self._can_use_tool` to `ClaudeAgentOptions`
  - Add fields: `_pending_question: dict | None`, `_pending_answer_event: asyncio.Event | None`, `_pending_answers: dict | None`
  - `_can_use_tool()`: if `tool_name == "AskUserQuestion"` → store question, create Event, await it, return `PermissionResultAllow(updated_input=...)` with answers; otherwise → return `PermissionResultAllow(updated_input=input_data)` (auto-approve)
  - `provide_answer(answers)`: sets `_pending_answers`, fires `_pending_answer_event`
  - `has_pending_question` property
  - File: `src/gobby/servers/chat_session.py`

## Phase 2: Backend — WebSocket handler

- [ ] Add `ask_user_response` message handler to WebSocket server (category: code, depends: Phase 1)
  - Register `"ask_user_response": self._handle_ask_user_response` in message dispatch
  - Extract `conversation_id` and `answers` from message data
  - Look up ChatSession from `self._chat_sessions[conversation_id]`, call `session.provide_answer(answers)`
  - If no session or no pending question, log warning and ignore
  - File: `src/gobby/servers/websocket/chat.py` (ChatMixin)

## Phase 3: Frontend — Interactive AskUserQuestion UI

- [ ] Add selection state and submit logic to AskUserQuestionDisplay (category: code, depends: Phase 2)
  - Add state: `selectedOptions: Record<number, string[]>`, `otherTexts: Record<number, string>`, `submitted: boolean`
  - Make option divs clickable: single-select (radio), multi-select (checkbox), "Other" shows text input
  - Selected options get `ask-user-option-selected` class
  - Add Submit button (visible when `isWaiting && !submitted`): builds answers map `{ "question text": "selected label" }`, calls `onRespond(call.id, answers)`, sets `submitted = true`
  - After submit: show selected answers as confirmed text, disable all options
  - Add `onRespond` prop: `(toolCallId: string, answers: Record<string, string>) => void`
  - File: `web/src/components/ToolCallDisplay.tsx`

- [ ] Add `respondToQuestion` callback to useChat hook (category: code, depends: Phase 2)
  - Sends `ask_user_response` WebSocket message with `conversation_id`, `tool_call_id`, `answers`
  - Add to returned object from hook
  - File: `web/src/hooks/useChat.ts`

- [ ] Thread `onRespondToQuestion` prop through Message and ChatMessages (category: code, depends: Phase 3 task 1, Phase 3 task 2)
  - Add `onRespondToQuestion` to `MessageProps`, pass to `ToolCallDisplay` as `onRespond`
  - Add `onRespondToQuestion` to `ChatMessagesProps`, pass to each `<Message>`
  - Files: `web/src/components/Message.tsx`, `web/src/components/ChatMessages.tsx`

- [ ] Wire `respondToQuestion` from useChat to ChatMessages in App.tsx (category: code, depends: Phase 3 task 3)
  - Destructure `respondToQuestion` from `useChat()`
  - Pass as `onRespondToQuestion` prop to `<ChatMessages>`
  - File: `web/src/App.tsx`

- [ ] Add CSS classes for selected/submitted states (category: code)
  - `.ask-user-option-selected` — highlighted border/background for selected options
  - `.ask-user-submitted` — disabled/muted appearance after submission
  - File: `web/src/styles/index.css`

## Implementation Details

### Event Flow

```
1. Claude generates AskUserQuestion ToolUseBlock
2. CLI sends AssistantMessage (frontend sees tool_status "calling")
3. CLI sends can_use_tool control request to SDK
4. SDK calls ChatSession._can_use_tool() callback
5. Callback stores pending question, creates asyncio.Event, awaits it
6. Frontend renders interactive question UI (from existing tool_status message)
7. User selects options and clicks Submit
8. Frontend sends ask_user_response WebSocket message
9. WebSocket handler calls session.provide_answer(answers)
10. asyncio.Event fires -> callback returns PermissionResultAllow with answers
11. CLI processes tool result -> UserMessage with ToolResultBlock arrives
12. Frontend shows completed state
```

### Prop Chain

```
App.tsx (useChat -> respondToQuestion)
  -> ChatMessages (onRespondToQuestion prop)
    -> Message (onRespondToQuestion prop)
      -> ToolCallDisplay (onRespond prop)
        -> AskUserQuestionDisplay (onRespond prop, manages selection state)
```

### `src/gobby/servers/chat_session.py`

- Import `PermissionResultAllow` from `claude_agent_sdk`
- `_can_use_tool()` returns `PermissionResultAllow(updated_input={"questions": input_data["questions"], "answers": self._pending_answers})` for AskUserQuestion
- Auto-approve path: `return PermissionResultAllow(updated_input=input_data)`

### `web/src/hooks/useChat.ts`

```ts
const respondToQuestion = useCallback((toolCallId: string, answers: Record<string, string>) => {
  if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
  wsRef.current.send(JSON.stringify({
    type: 'ask_user_response',
    conversation_id: conversationIdRef.current,
    tool_call_id: toolCallId,
    answers,
  }))
}, [])
```

## Task Mapping

| Phase | Task | Gobby Ref |
|-------|------|-----------|
| 1 | ChatSession can_use_tool callback | |
| 2 | WebSocket ask_user_response handler | |
| 3.1 | AskUserQuestionDisplay interactive UI | |
| 3.2 | useChat respondToQuestion callback | |
| 3.3 | Thread onRespondToQuestion prop | |
| 3.4 | Wire respondToQuestion in App.tsx | |
| 3.5 | CSS selected/submitted classes | |
