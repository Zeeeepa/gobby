# Replace require-read-mail block with inject_context

## Summary

Replace the `require-read-mail` rule (which blocks all tool use until the agent reads mail) with a softer `notify-unread-mail` rule that uses `inject_context` to nudge the agent about pending messages. The agent still gets told to read its mail, but isn't hard-blocked from doing other work.

## Why

Blocking is heavy-handed. The agent can't do *anything* — not even read a file — until it calls `deliver_pending_messages`. An inject_context approach gives the agent the same information ("you have unread mail, go read it") but lets it exercise judgment about when to do so. In practice, agents always comply with context nudges anyway.

## Changes

### 1. Replace the rule YAML

**File**: `src/gobby/install/shared/rules/messaging/require-read-mail.yaml`

Rename to `notify-unread-mail.yaml` and change from `block` to `inject_context`:

```yaml
tags: [messaging, p2p, context]

rules:
  notify-unread-mail:
    description: "Notify agent of pending inter-session messages via context injection"
    event: before_tool
    enabled: false
    priority: 8
    agent_scope: ["*"]
    when: >-
      has_pending_messages(event.metadata.get('_platform_session_id', ''))
      and not is_message_delivery_tool(event.data.get('mcp_tool'))
    effect:
      type: inject_context
      template: |
        ⚠️ You have {{ pending_message_count(event.metadata.get('_platform_session_id', '')) }} undelivered inter-session message(s).
        Please read them soon by calling: deliver_pending_messages(session_id="{{ event.metadata.get('_platform_session_id', '') }}")
```

Key differences from the old rule:
- **Effect type**: `block` → `inject_context`
- **No discovery tool exemption needed**: inject_context doesn't block anything, so `is_discovery_tool` check is removed from `when` (not needed — discovery tools don't need special treatment if nothing is blocked)
- **Tag**: `enforcement` → `context` (it's no longer enforcing)
- **Rule name**: `require-read-mail` → `notify-unread-mail`

### 2. Update blocking.py — remove `is_message_delivery_tool` (or keep for compat)

**File**: `src/gobby/workflows/enforcement/blocking.py`

`MESSAGE_DELIVERY_TOOLS` and `is_message_delivery_tool` are still referenced in the `when` clause (to avoid re-notifying when the agent is *already* calling deliver). Keep them — they serve a useful purpose even with inject_context (no point injecting "read your mail" context on the very call that reads mail).

**No changes needed here.**

### 3. Update tests

**File**: `tests/workflows/test_messaging_rules.py`

- Rename `TestRequireReadMail` → `TestNotifyUnreadMail`
- Change all `assert response.decision == "block"` to `assert response.decision == "allow"` with `assert response.context` containing the nudge text
- Remove the discovery-tool exemption test (no longer relevant — inject_context doesn't block)
- Keep the "allows when no messages" and "allows when already delivered" tests (they now verify no context is injected)
- Update `_require_read_mail_body()` → `_notify_unread_mail_body()` with the new effect
- Keep the Jinja2 helper test (`test_helpers_available_in_inject_context`) — it already tests the inject_context path and passes today
- Update `test_block_reason_renders_message_count` → verify the count renders in `response.context` instead of `response.reason`

### 4. Delete old rule file, add new one

- Delete: `src/gobby/install/shared/rules/messaging/require-read-mail.yaml`
- Create: `src/gobby/install/shared/rules/messaging/notify-unread-mail.yaml`

No migration needed — rules are synced from YAML templates via `sync_bundled_content_to_db()`. The old rule name will be orphaned (soft-deleted) on next sync.

## Implementation order

1. Create `notify-unread-mail.yaml` with the new rule
2. Delete `require-read-mail.yaml`
3. Update tests in `test_messaging_rules.py`
4. Run tests: `pytest tests/workflows/test_messaging_rules.py -x`

## Verification

- `pytest tests/workflows/test_messaging_rules.py -x` — all messaging rule tests pass
- `pytest tests/workflows/ -x` — no regressions in other workflow tests
- Grep for any remaining references to `require-read-mail` to ensure nothing is missed
