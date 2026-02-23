# Progressive Disclosure Rules Migration Plan

## Context

The `session-lifecycle` step-based workflow is still doing all enforcement — it's alive in the DB (`source=bundled, enabled=1`) even though the YAML file was deleted. The YAML rules (in `progressive-disclosure.yaml`) are the intended replacement, but most are `enabled=0` in the DB.

The bug: progressive disclosure was blocking `get_tool_schema` calls. This was the **session-lifecycle workflow's `on_before_tool` block_tools rules**, not the YAML rules.

## Problem Summary

1. **Zombie workflow**: `session-lifecycle` and `claude-sdk-lifecycle` are in `workflow_definitions` with `enabled=1, source=bundled` but no YAML on disk. They keep running because `sync_bundled_workflows` only adds/updates — it doesn't clean up orphans.
2. **Duplicate enforcement**: Both the step-based workflow AND YAML rules define the same progressive disclosure blocking. When both are active, tracking happens in different places (`workflow_states.variables` vs `session_variables`), causing desync.
3. **Session defaults not wired**: `load_session_defaults()` exists but is never called. When the step-based workflow goes away, new sessions won't have `enforce_tool_schema_check`, `listed_servers`, etc. initialized.
4. **YAML tracking rules write to wrong store**: The YAML `set_variable` effects write to `session_variables`, but the blocking rules read merged state from `workflow_states + session_variables`. Without a `workflow_states` row, the merge path in `_evaluate_rules()` starts from an empty dict — which is fine, IF session defaults are properly initialized.

## Plan (Incremental, One Rule at a Time)

### Phase 0: Cleanup — Disable Zombie Workflows

**Files:**
- `src/gobby/workflows/sync.py` — Add orphan cleanup to `sync_bundled_workflows`

**Changes:**
- After syncing, query for `source='bundled'` workflow definitions whose `name` doesn't match any YAML file on disk
- Soft-delete orphans (set `deleted_at`) rather than hard-deleting — reversible
- This kills `session-lifecycle` and `claude-sdk-lifecycle` in the DB on next sync

**Alternative (safer for testing):** Just disable them via SQL: `UPDATE workflow_definitions SET enabled=0 WHERE name IN ('session-lifecycle', 'claude-sdk-lifecycle')`

### Phase 1: Wire Session Variable Defaults

**Files:**
- `src/gobby/workflows/hooks.py` — `_evaluate_rules()` method

**Changes:**
- When loading variables for a session and both `workflow_states` and `session_variables` return empty, call `load_session_defaults()` and seed `session_variables` with the defaults
- This ensures `enforce_tool_schema_check=true`, `listed_servers=[]`, `servers_listed=false`, etc. are available even without a step-based workflow

**Alternative:** Add a `session_start` rule (YAML) with `set_variable` effects for defaults. But `load_session_defaults()` already has the data and is cleaner — single source of truth in `session-defaults.yaml`.

### Phase 2: Enable Tracking Rules First

Enable **one at a time**, test each:

1. **`track-servers-listed`** (priority 21) — After `list_mcp_servers`, sets `servers_listed=true`
   - Test: Call `list_mcp_servers`, verify `session_variables` gets `servers_listed: true`

2. **`track-listed-servers`** (priority 22) — After `list_tools(server)`, appends to `listed_servers`
   - Test: Call `list_tools(server_name="gobby-tasks")`, verify `listed_servers` includes `"gobby-tasks"`

3. **`track-schema-lookup`** (priority 20) — After `get_tool_schema`, appends to `unlocked_tools`
   - Test: Call `get_tool_schema(...)`, verify `unlocked_tools` includes the `server:tool` key

### Phase 3: Enable Blocking Rules (After Tracking Verified)

Enable **one at a time**, test each:

1. **`require-servers-listed`** (priority 20) — Blocks `list_tools` without prior `list_mcp_servers`
   - Test: Fresh session, call `list_tools` → should be blocked. Call `list_mcp_servers` first → `list_tools` should pass.

2. **`require-server-listed-for-schema`** (priority 21) — Blocks `get_tool_schema` without prior `list_tools`
   - Test: Call `get_tool_schema(server_name="gobby-tasks", ...)` without `list_tools("gobby-tasks")` → blocked. After `list_tools` → passes.

3. **`require-schema-before-call`** (priority 22) — Blocks `call_tool` without prior `get_tool_schema`
   - Test: Call `call_tool(server_name="gobby-tasks", tool_name="create_task", arguments={...})` → blocked. After `get_tool_schema` → passes.

### Phase 4: Enable Remaining Rules (from session-lifecycle)

The session-lifecycle workflow had many more `on_before_tool` blocking rules that need equivalent YAML rules. These should be audited against the existing YAML rule files and enabled/created as needed:

- `require-task-before-edit`
- `require-commit-before-close`
- `require-uv`
- Stop-attempt escalation rules
- etc.

Each follows the same pattern: enable in DB, test in isolation.

## Verification Steps

For each rule enablement:
1. Disable the step-based workflow enforcement for that specific behavior
2. Enable the YAML rule
3. Test the happy path (rule allows when conditions met)
4. Test the block path (rule blocks when conditions not met)
5. Test the tracking persistence (variables survive across hook events)
6. Check `session_variables` table directly to verify persistence

## Open Questions

1. **Session-lifecycle disable strategy**: Disable the whole workflow at once, or surgically remove individual `on_before_tool` rules from it as YAML equivalents are enabled?
2. **Reset rules (lines 70-98)**: The `session_start` reset rules clear tracking state on compact/clear. Should these be enabled alongside the tracking rules, or are they already handled by the step-based workflow?
3. **Duplicate DB rows**: There are duplicate rule names in `workflow_definitions` (some `enabled=0`, some `enabled=1`). These need cleanup — probably the `enabled=0` ones are stale from an earlier sync.
