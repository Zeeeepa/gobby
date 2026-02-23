# Fix: Progressive Disclosure Tracking Rules Never Fire

## Root Cause

**Two bugs working together:**

### Bug 1: Custom copies have truncated `when` conditions

The custom tracking rules in the DB have truncated `when` conditions that only check `event.data.get('mcp_tool')` — a field set by CLI hook adapters but **NOT** by the web chat SDK bridge.

| Rule | DB `when` (broken) | YAML `when` (correct) |
|------|-------------------|----------------------|
| `track-listed-servers` | `event.data.get('mcp_tool') == 'list_tools'` | `...== 'list_tools' or event.data.get('tool_name') in ('list_tools', 'mcp__gobby__list_tools')` |
| `track-servers-listed` | `event.data.get('mcp_tool') == 'list_mcp_servers'` | Same pattern — includes `tool_name` fallback |
| `track-schema-lookup` | `event.data.get('mcp_tool') == 'get_tool_schema'` | Same pattern — includes `tool_name` fallback |

For web chat sessions, `event.data` has `tool_name: "mcp__gobby__list_tools"` but NOT `mcp_tool`. So the tracking `when` never evaluates to True, variables never get set, and the blocking rules always see empty state → permanent block.

### Bug 2: `_sync_single_rule` can't update bundled rules when custom copies exist

In `sync.py:_sync_single_rule`, the sync process:
1. Calls `manager.get_by_name(rule_name)` — which **prefers custom over bundled** (line 170-172 in `workflow_definitions.py`)
2. Gets the custom copy back
3. Checks `if existing.source == "bundled":` → **False** (it's "custom")
4. Falls through to `else: result["skipped"] += 1` — **skips entirely**

So even though the YAML has the correct full `when` condition, the sync never reaches the bundled DB row to update it. The custom copy shadows it.

## Fix Plan

### File 1: `src/gobby/workflows/sync.py` — Fix sync to handle custom shadows

In `_sync_single_rule`, when `get_by_name` returns a custom copy, we should still look for and update the bundled row directly:

```python
# After get_by_name returns a custom row:
if existing is not None and existing.source != "bundled":
    # Custom copy shadows bundled — look up the bundled row directly
    bundled_row = db.fetchone(
        "SELECT * FROM workflow_definitions WHERE name = ? AND source = 'bundled' AND deleted_at IS NULL",
        (rule_name,),
    )
    if bundled_row:
        existing_bundled = WorkflowDefinitionRow.from_row(bundled_row)
        if existing_bundled.definition_json != definition_json:
            manager.update(existing_bundled.id, definition_json=definition_json, ...)
            result["updated"] += 1
        else:
            result["skipped"] += 1
    # Skip the custom row — don't touch it
    return
```

### File 2: Data fix — Update the 6 broken DB rows

Both the bundled and custom copies need their `when` conditions corrected. Run SQL to update:

For each of the 3 tracking rules × 2 copies (bundled + custom):
- Parse the current `definition_json`
- Replace the truncated `when` with the full condition from YAML
- Update the row

### File 3: Add integration test

Add a test to `tests/workflows/test_progressive_disclosure_rules.py` that exercises the **full round-trip**: fire `after_tool` for `list_tools` → verify `listed_servers` gets populated → fire `before_tool` for `get_tool_schema` → verify it's allowed.

The existing `test_full_disclosure_flow` test **manually sets variables** (line 480-481: "Python handler sets this") instead of having the rule engine do it. The new test should let the rule engine's `set_variable` effect do the tracking.

## Implementation Order

1. Fix `_sync_single_rule` to handle custom shadows (prevents future recurrence)
2. Fix the DB rows (immediate fix)
3. Add the integration test
4. Re-enable progressive disclosure rules via `toggle_rule`
5. Test end-to-end in this session

## Verification

1. Call `list_tools(server_name="gobby-workflows")`
2. Call `get_tool_schema("gobby-workflows", "list_rules")` → should succeed
3. Call `call_tool("gobby-workflows", "list_rules", {})` after schema → should succeed
4. Check `session_variables` table → should show `listed_servers: ["gobby-workflows"]`
