# Plan: AskUserQuestion Response Mechanism for Web Chat UI

## Context

The web chat UI renders AskUserQuestion tool calls as interactive cards, but users can't respond - options are display-only. The Claude Agent SDK's official `can_use_tool` callback (documented at platform.claude.com/docs/en/agent-sdk/user-input) is the mechanism for intercepting AskUserQuestion and providing user answers. Currently, ChatSession uses `permission_mode="bypassPermissions"` which auto-approves all tools without the callback.

## Approach

Replace `permission_mode="bypassPermissions"` with a `can_use_tool` callback on ChatSession. When AskUserQuestion is intercepted, the callback blocks (via `asyncio.Event`) until the web UI sends the user's answers through a new `ask_user_response` WebSocket message. All other tools are auto-approved.

### Event Flow

```
1. Claude generates AskUserQuestion ToolUseBlock
2. CLI sends AssistantMessage (→ frontend sees tool_status "calling")
3. CLI sends can_use_tool control request to SDK
4. SDK calls ChatSession._can_use_tool() callback
5. Callback stores pending question, creates asyncio.Event, awaits it
6. Frontend renders interactive question UI (from existing tool_status message)
7. User selects options and clicks Submit
8. Frontend sends ask_user_response WebSocket message
9. WebSocket handler calls session.provide_answer(answers)
10. asyncio.Event fires → callback returns PermissionResultAllow with answers
11. CLI processes tool result → UserMessage with ToolResultBlock arrives
12. Frontend shows completed state
```

## Changes

### 1. `src/gobby/servers/chat_session.py` — Intercept AskUserQuestion

- Add imports: `PermissionResultAllow` from `claude_agent_sdk`
- Add fields to ChatSession dataclass:
  - `_pending_question: dict | None` — stores the AskUserQuestion input_data
  - `_pending_answer_event: asyncio.Event | None` — blocks callback until answer arrives
  - `_pending_answers: dict | None` — stores the user's answers
- Add `_can_use_tool()` async method:
  - If `tool_name == "AskUserQuestion"`: store question, create Event, await it, return `PermissionResultAllow(updated_input={"questions": input_data["questions"], "answers": self._pending_answers})`
  - Otherwise: return `PermissionResultAllow(updated_input=input_data)` (auto-approve)
- Add `provide_answer(answers: dict)` method:
  - Sets `_pending_answers = answers`
  - Sets `_pending_answer_event` to unblock the callback
- Add `has_pending_question` property: returns whether a question is pending
- In `start()`:
  - Remove `permission_mode="bypassPermissions"`
  - Add `can_use_tool=self._can_use_tool` to `ClaudeAgentOptions`

### 2. `src/gobby/servers/websocket.py` — Handle ask_user_response

- Register new handler in message dispatch (around line 285 where other handlers are registered):
  ```python
  "ask_user_response": self._handle_ask_user_response
  ```
- Add `_handle_ask_user_response()` method:
  - Extract `conversation_id` and `answers` from the message data
  - Look up ChatSession from `self._chat_sessions[conversation_id]`
  - Call `session.provide_answer(answers)`
  - If no session or no pending question, log warning and ignore

### 3. `web/src/components/ToolCallDisplay.tsx` — Interactive options

- Add `onRespond` prop to `ToolCallDisplayProps` and `AskUserQuestionDisplay`:
  ```ts
  onRespond?: (toolCallId: string, answers: Record<string, string>) => void
  ```
- Add local state to `AskUserQuestionDisplay`:
  - `selectedOptions: Record<number, string[]>` — tracks selected option labels per question index
  - `otherTexts: Record<number, string>` — tracks "Other" text input per question
  - `submitted: boolean` — disables UI after submit
- Make option divs clickable:
  - Single-select (radio behavior): clicking an option sets it as the only selection for that question
  - Multi-select (checkbox behavior): clicking toggles the option
  - "Other" option: when selected, shows a text input field
  - Visual feedback: selected options get a highlighted class (`ask-user-option-selected`)
- Add Submit button below options (visible when `isWaiting && !submitted`):
  - On click: build answers map `{ "question text": "selected label" }`, call `onRespond(call.id, answers)`, set `submitted = true`
- After submit: show selected answers as confirmed text, disable all options

### 4. `web/src/hooks/useChat.ts` — respondToQuestion function

- Add `respondToQuestion` callback:
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
- Add `respondToQuestion` to the returned object

### 5. `web/src/components/Message.tsx` — Pass callback through

- Add `onRespondToQuestion` to `MessageProps`:
  ```ts
  onRespondToQuestion?: (toolCallId: string, answers: Record<string, string>) => void
  ```
- Pass it to `ToolCallDisplay`:
  ```tsx
  <ToolCallDisplay toolCalls={message.toolCalls} onRespond={onRespondToQuestion} />
  ```

### 6. `web/src/components/ChatMessages.tsx` — Thread callback through

- Add `onRespondToQuestion` to `ChatMessagesProps`
- Pass it to each `<Message>` component

### 7. `web/src/App.tsx` — Wire `respondToQuestion` from useChat

- Destructure `respondToQuestion` from `useChat()` (line ~50)
- Pass as `onRespondToQuestion` prop to `<ChatMessages>` (line ~74)

### Prop chain

```
App.tsx (useChat → respondToQuestion)
  → ChatMessages (onRespondToQuestion prop)
    → Message (onRespondToQuestion prop)
      → ToolCallDisplay (onRespond prop)
        → AskUserQuestionDisplay (onRespond prop, manages selection state)
```

## Files Modified

| File | Change |
|------|--------|
| `src/gobby/servers/chat_session.py` | Add `can_use_tool` callback, pending question state, `provide_answer()` |
| `src/gobby/servers/websocket.py` | Add `ask_user_response` handler at line ~283 in `_handle_message()` |
| `src/gobby/install/shared/workflows/lifecycle/session-lifecycle.yaml` | Add `session_initialized` flag to `on_session_start`; add failover bootstrap to `on_before_agent` |
| `web/src/components/ToolCallDisplay.tsx` | Interactive options, selection state, submit button |
| `web/src/hooks/useChat.ts` | Add `respondToQuestion()` function |
| `web/src/components/Message.tsx` | Add + pass `onRespondToQuestion` prop |
| `web/src/components/ChatMessages.tsx` | Add + pass `onRespondToQuestion` prop |
| `web/src/App.tsx` | Wire `respondToQuestion` → `ChatMessages` |

## Key Considerations

- **No new WebSocket message type for showing questions**: The existing `tool_status` with `status: "calling"` already delivers AskUserQuestion to the frontend. The `can_use_tool` callback just blocks until answered.
- **One pending question per session**: Since Claude processes sequentially, only one AskUserQuestion can be pending at a time per ChatSession. No need for a queue.
- **asyncio.Event compatibility**: The `can_use_tool` callback runs in an anyio task (backed by asyncio). `asyncio.Event` works because anyio on asyncio wraps asyncio tasks. `provide_answer()` is called from asyncio WebSocket handler — `event.set()` works across tasks.
- **No bypassPermissions**: Removing `permission_mode="bypassPermissions"` means all tool calls go through `can_use_tool`. The auto-approve path (`return PermissionResultAllow(updated_input=input_data)`) is instant, so overhead is negligible.

### Hook Interaction: SessionStart Failover

The CLI subprocess loads project hooks from `.claude/settings.json`, so session-lifecycle hooks DO fire for web chat sessions. However, the SDK doesn't fire `SessionStart` (documented limitation), meaning session-lifecycle variables (`enforce_tool_schema_check`, `unlocked_tools`, etc.) are never initialized. The `on_before_tool` enforcement is effectively bypassed.

**Fix: Add `on_before_agent` failover in session-lifecycle.yaml** that runs the full `on_session_start` bootstrap on the first `UserPromptSubmit` when `session_initialized` is not set.

#### `session-lifecycle.yaml` changes

**Add to end of `on_session_start` (after all existing actions):**
```yaml
# Mark session as initialized (prevents on_before_agent failover from re-running)
- action: set_variable
  name: session_initialized
  value: true
```

**Add to BEGINNING of `on_before_agent` (before existing `stop_attempts` reset):**
```yaml
# === SDK SessionStart failover ===
# The Claude Agent SDK doesn't fire SessionStart hooks. On the first
# UserPromptSubmit, run the same bootstrap that on_session_start provides.

- action: set_variable
  when: "not variables.get('session_initialized')"
  name: plan_mode
  value: false

- action: set_variable
  when: "not variables.get('session_initialized')"
  name: unlocked_tools
  value: []

- action: set_variable
  when: "not variables.get('session_initialized')"
  name: servers_listed
  value: false

- action: set_variable
  when: "not variables.get('session_initialized')"
  name: listed_servers
  value: []

- action: reset_memory_injection_tracking
  when: "not variables.get('session_initialized')"

- action: capture_baseline_dirty_files
  when: "not variables.get('session_initialized')"

- action: memory_sync_import
  when: "not variables.get('session_initialized')"

- action: task_sync_import
  when: "not variables.get('session_initialized')"

- action: inject_context
  when: "not variables.get('session_initialized')"
  source: skills
  filter: always_apply
  template: |
    {{ skills_list }}

- action: inject_context
  when: "not variables.get('session_initialized')"
  source: task_context
  template: |
    {{ task_context }}

- action: inject_context
  when: "not variables.get('session_initialized')"
  template: |
    ## Pre-Existing Error/Warning/Failure Policy
    ... (same text as on_session_start)

- action: set_variable
  when: "not variables.get('session_initialized')"
  name: session_initialized
  value: true

# === End SDK failover ===
```

**Skipped from on_session_start** (not applicable for SDK sessions):
- Context handoff injection (`previous_session_summary`, `compact_handoff`) — SDK sessions have no previous Gobby session to hand off from
- Plan mode recommendation prompt — web chat has its own UX for this
- `pending_context_reset` flag handling — Gemini-specific

**How it works:**
- CLI sessions: `on_session_start` runs → sets `session_initialized: true` → failover in `on_before_agent` skips
- SDK sessions: `on_session_start` never fires → first `UserPromptSubmit` → `session_initialized` is None (falsy) → failover runs full bootstrap → sets `session_initialized: true` → subsequent prompts skip

## Verification

1. **Start daemon**: `uv run gobby restart --verbose`
2. **Open web UI**: Navigate to the chat interface
3. **Trigger AskUserQuestion**: Send a prompt that requires clarification (e.g., "Help me add authentication to this project" — Claude should ask which method)
4. **Verify interactive UI**: Question should render with clickable options, submit button visible
5. **Submit response**: Select an option, click Submit, verify:
   - Options become disabled / show selected state
   - Claude continues with the selected answer
   - Tool status transitions from "calling" to "completed"
6. **Test "Other"**: Trigger another question, select "Other", type custom text, submit
7. **Test multi-select**: If a question has `multiSelect: true`, verify multiple options can be toggled
8. **Test regular tools**: Verify other MCP tool calls still work normally (auto-approved via callback)
