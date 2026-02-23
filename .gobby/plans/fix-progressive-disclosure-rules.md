# Fix Progressive Disclosure Rules — `mcp_tool` Not Set for Native MCP Tools

## Root Cause

The Claude Code adapter (`src/gobby/adapters/claude_code.py`, line 142-147) only enriches `event.data` with `mcp_tool`/`mcp_server` for `call_tool` and `mcp__gobby__call_tool`. When CC calls native MCP tools like `mcp__gobby__list_tools` or `mcp__gobby__get_tool_schema`, the adapter does NOT parse the `mcp__` prefix to extract these fields.

**Result:** All three progressive disclosure tracking rules fail silently:

| Rule | `when` condition | Why it fails |
|------|-----------------|--------------|
| `track-servers-listed` | `event.data.get('mcp_tool') == 'list_mcp_servers'` | `mcp_tool` is `None` |
| `track-listed-servers` | `event.data.get('mcp_tool') == 'list_tools'` | `mcp_tool` is `None` |
| `track-schema-lookup` | `event.data.get('mcp_tool') == 'get_tool_schema'` | `mcp_tool` is `None` |

Since tracking never fires, the blocking rules (`require-servers-listed`, `require-server-listed-for-schema`, `require-schema-before-call`) always see empty state and block everything — creating an infinite loop.

## Fix

### Option A: Fix the adapter (recommended)

**File:** `src/gobby/adapters/claude_code.py` — `_enrich_tool_data` method

Add parsing of `mcp__<server>__<tool>` prefixed tool names to extract `mcp_server` and `mcp_tool` for ALL native MCP calls, not just `call_tool`:

```python
def _enrich_tool_data(self, input_data: dict[str, Any]) -> dict[str, Any]:
    data = dict(input_data)
    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {}) or {}

    # Parse mcp__<server>__<tool> format for ALL native MCP calls
    if tool_name.startswith("mcp__") and "mcp_tool" not in data:
        parts = tool_name.split("__", 2)  # ["mcp", "server", "tool"]
        if len(parts) == 3:
            data.setdefault("mcp_server", parts[1])
            data.setdefault("mcp_tool", parts[2])

    # Also handle call_tool where mcp info is in tool_input
    if tool_name in ("call_tool", "mcp__gobby__call_tool"):
        if "mcp_server" not in data:
            data["mcp_server"] = tool_input.get("server_name")
        if "mcp_tool" not in data:
            data["mcp_tool"] = tool_input.get("tool_name")

    # Normalize tool_result → tool_output
    if "tool_result" in data and "tool_output" not in data:
        data["tool_output"] = data["tool_result"]

    return data
```

**Also apply to:** `src/gobby/adapters/cursor.py` (same pattern at line 206-211).

Check other adapters too:
- `src/gobby/adapters/` — grep for similar `_enrich_tool_data` or MCP normalization

### Option B: Fix the YAML rules (alternative/belt-and-suspenders)

Change the `when` conditions to also match on `tool_name`:

```yaml
track-servers-listed:
  when: "event.data.get('mcp_tool') == 'list_mcp_servers' or event.data.get('tool_name') == 'mcp__gobby__list_mcp_servers'"

track-listed-servers:
  when: "event.data.get('mcp_tool') == 'list_tools' or event.data.get('tool_name') == 'mcp__gobby__list_tools'"

track-schema-lookup:
  when: "event.data.get('mcp_tool') == 'get_tool_schema' or event.data.get('tool_name') == 'mcp__gobby__get_tool_schema'"
```

### Recommendation

**Do both.** Option A fixes the root cause at the adapter level so ALL rules/workflows that check `mcp_tool` work correctly for native MCP tools. Option B is a safety net specific to progressive disclosure.

## Files to Modify

1. **`src/gobby/adapters/claude_code.py`** — Add `mcp__` prefix parsing to `_enrich_tool_data`
2. **`src/gobby/adapters/cursor.py`** — Same fix
3. **`src/gobby/install/shared/rules/progressive-disclosure.yaml`** — Add fallback `tool_name` checks to `when` conditions
4. Check all other adapters in `src/gobby/adapters/` for the same gap

## Implementation Order

1. Fix `claude_code.py` adapter (primary fix)
2. Fix `cursor.py` adapter (same fix)
3. Check/fix other adapters
4. Update YAML rules as belt-and-suspenders
5. Add test: verify `_enrich_tool_data` correctly parses `mcp__gobby__list_tools` → `mcp_server="gobby"`, `mcp_tool="list_tools"`
6. Re-enable rules via `toggle_rule` and verify the full flow

## Verification

1. Enable progressive disclosure rules
2. Call `mcp__gobby__list_mcp_servers` — verify `track-servers-listed` fires
3. Call `mcp__gobby__list_tools(server_name="gobby-tasks")` — verify `track-listed-servers` fires
4. Call `mcp__gobby__get_tool_schema(...)` — verify `track-schema-lookup` fires
5. Call `mcp__gobby__call_tool(...)` — verify it's not blocked (tool is unlocked)
6. Run existing tests: `uv run pytest tests/workflows/test_progressive_disclosure_rules.py`
