# Plan: Fix Canvas Skill Auto-Injection for Web UI Sessions

**Task**: #9115
**Date**: 2026-02-24

## Problem

The canvas skill (`skl-4a7c57a3`) is installed and enabled but never injected into web chat sessions. The LLM doesn't know it can render A2UI surfaces. Canvas rendering works end-to-end (MCP tools broadcast WebSocket events, frontend renders them), but the LLM is never told it has this capability.

### Root Cause Chain

1. **`_db_skill_to_parsed()`** in `hooks/skill_manager.py` doesn't extract `audience_config` from `metadata.gobby` — only extracts triggers. Canvas gets `audience_config=None`.
2. **Canvas SKILL.md** uses `conditions:` frontmatter (Jinja2 templates) which nothing in the codebase evaluates — should use `metadata.gobby.sources` instead.
3. **`SkillInjector._should_include()`** checks `audience_config` (None) → falls back to `always_apply` (False) → canvas silently excluded.
4. **`_inject_context_aware_skills()`** in `context_actions.py` returns empty string — dead function with a comment saying discovery handles it.
5. **`inject-skills-on-start` rule** is `enabled: false`.
6. **`SESSION_START`** is fire-and-forget in web chat (`chat.py` line 280: `asyncio.create_task(...)`) — response is discarded, so even an enabled rule wouldn't reach the LLM through that event.

## Changes

### 1. Fix `_db_skill_to_parsed()` — extract `audience_config` from metadata

**File**: `src/gobby/hooks/skill_manager.py`

The filesystem parser (`skills/parser.py:parse_skill()`) already extracts `audience_config` from `metadata.gobby.*` fields at lines 326-394. But `_db_skill_to_parsed()` skips this entirely — it only pulls triggers.

**Change**: Mirror the `audience_config` extraction logic from `parse_skill()`:
- Check `metadata.gobby` for keys: `audience`, `depth`, `steps`, `task_categories`, `sources`, `format_overrides`, `priority`
- Build `SkillAudienceConfig` when any are present
- Pass to `ParsedSkill(..., audience_config=audience_config)`

### 2. Convert canvas SKILL.md frontmatter

**File**: `src/gobby/install/shared/skills/canvas/SKILL.md`

Replace dead `conditions:` with structured audience_config fields:

**Before**:
```yaml
conditions:
  - "{{ session.source in ['claude_sdk_web_chat', 'gemini_sdk_web_chat'] }}"
```

**After**:
```yaml
always_apply: true
injection_format: content
gobby:
  sources:
    - claude_sdk_web_chat
    - gemini_sdk_web_chat
  audience: all
```

- `always_apply: true` — makes it a candidate for auto-injection
- `injection_format: content` — injects full skill body, not a summary line
- `gobby.sources` — restricts to web UI sessions only (SkillInjector already supports this at `injector.py` lines 215-217)

### 3. Revive `_inject_context_aware_skills()` with SkillInjector

**File**: `src/gobby/workflows/context_actions.py`

Currently returns `""`. Change it to:
- Build an `AgentContext` from the session (including `source` field)
- Use `SkillInjector.select_skills()` to filter skills by audience_config
- Format selected skills with `_format_skills_with_formats()`

This makes the `filter: context_aware` option in rules actually work.

### 4. Enable skill injection rule on `before_agent`

**File**: `src/gobby/install/shared/rules/context-handoff/inject-skills-on-start.yaml`

**Before**:
```yaml
event: session_start
enabled: false
```

**After**:
```yaml
event: before_agent
enabled: true
when: "not variables.get('_skills_injected')"
filter: context_aware
```

Uses `before_agent` (UserPromptSubmit) because that's the reliable injection point for web chat — the response feeds into `additionalContext`. The `_skills_injected` guard ensures it only fires once per session.

## Files to Modify

| File | Change |
|------|--------|
| `src/gobby/hooks/skill_manager.py` | Extract `audience_config` in `_db_skill_to_parsed()` |
| `src/gobby/install/shared/skills/canvas/SKILL.md` | Replace `conditions:` with `gobby.sources` + `always_apply: true` |
| `src/gobby/workflows/context_actions.py` | Revive `_inject_context_aware_skills()` with `SkillInjector` |
| `src/gobby/install/shared/rules/context-handoff/inject-skills-on-start.yaml` | Enable, change event to `before_agent`, add `context_aware` filter |

## Implementation Order

1. `_db_skill_to_parsed()` fix (unblocks everything else)
2. Canvas SKILL.md frontmatter update
3. `_inject_context_aware_skills()` revival
4. Rule enablement
5. Re-sync skills to DB (`install_all_templates()`)

## Verification

1. Start a web chat session → canvas skill content appears in LLM context
2. Start a CLI session → canvas skill is NOT injected (source filtering works)
3. LLM can call `render_surface` and produce working A2UI in web chat
4. Existing always-apply skills (discovery, claiming-tasks, etc.) still inject correctly
5. All existing tests pass
