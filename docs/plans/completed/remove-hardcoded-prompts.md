# Extract Hardcoded Enforcement Prompts into Workflow YAML

## Context

Workflow enforcement messages (stop-hook blocks, task policy blocks) are hardcoded as f-strings in Python. Changing agent-facing wording requires code changes + daemon restart. The workflow YAML already supports configurable `reason:` fields on `block_stop` actions — we extend this pattern to all enforcement actions so messages live in the workflow definition alongside the logic they belong to.

## Approach

Add a `messages:` dict to enforcement actions in the workflow YAML. The handlers pass these through to policy functions, which use them as Jinja2 templates (rendered via the existing `TemplateEngine`). Hardcoded strings become fallback defaults when `messages` is not provided.

### Example (workflow YAML)

```yaml
- action: require_task_review_or_close_before_stop
  when: "..."
  messages:
    task_still_in_progress: |
      Task {{ task_ref }} is still in_progress. Commit your changes and close it with close_task().
      Do NOT use mark_task_needs_review as a shortcut — only use needs_review when there is
      something genuinely critical the user must verify before closing.
```

## Files to Modify

### 1. `src/gobby/install/shared/workflows/session-lifecycle.yaml`
Add `messages:` dict to each enforcement action with the current hardcoded text as the default value. Actions to update:
- `require_task_review_or_close_before_stop` (1 message key: `task_still_in_progress`)
- `require_commit_before_stop` (called implicitly — add as new action entry with messages, or add messages to the commit policy handler; need to check how it's triggered)
- `block_tools` rules already have `reason:` — no change needed
- `require_task_complete` — not in YAML currently, need to add if used

**Also**: check where `require_commit_before_stop` and `require_task_complete` are triggered. If they're called from Python (not YAML), we need a different approach for those.

### 2. `src/gobby/workflows/enforcement/handlers.py`
Update handler signatures to accept `messages: dict[str, str] | None = None` kwarg and pass it through to the underlying policy functions:
- `handle_require_task_review_or_close_before_stop` → passes messages to `require_task_review_or_close_before_stop`
- `handle_require_commit_before_stop` → passes messages to `require_commit_before_stop`
- `handle_require_task_complete` → passes messages to `require_task_complete`
- `handle_validate_session_task_scope` → passes messages to `validate_session_task_scope`

### 3. `src/gobby/workflows/enforcement/commit_policy.py`
- `require_commit_before_stop()`: Accept `messages: dict | None = None`, use `messages.get("uncommitted_changes", DEFAULT)` for the block reason. Render with `TemplateEngine` if message contains `{{`.
- `require_task_review_or_close_before_stop()`: Same pattern with key `task_still_in_progress`.

### 4. `src/gobby/workflows/enforcement/task_policy.py`
- `require_task_complete()`: Accept `messages: dict | None = None`. Message keys:
  - `task_ready_to_close`
  - `task_incomplete_no_claim`
  - `task_claimed_incomplete`
  - `task_redirect_to_parent`
  - `task_generic_incomplete`
- `validate_session_task_scope()`: Accept `messages: dict | None = None`. Key: `scope_out_of_scope_claim`

### 5. `src/gobby/workflows/enforcement/blocking.py`
The generic tool block fallback (`Tool '{tool_name}' is blocked.`) — add `default_reason` to the `block_tools` action config in YAML. The `handle_block_tools` handler already receives kwargs from YAML.

### 6. `src/gobby/mcp_proxy/instructions.py`
Move the full `build_gobby_instructions()` text into `src/gobby/install/shared/prompts/mcp/progressive-disclosure.md` and load it via `PromptLoader`. This one makes more sense as a bundled prompt since it's not tied to a workflow action — it's static MCP server configuration.

### 7. `src/gobby/hooks/event_handlers/_agent.py`
Move agent event handler messages (`skill-hint`, `help-content`, `skill-not-found`) into `src/gobby/install/shared/prompts/agent/`. Same reasoning — these aren't workflow actions.

## Rendering Strategy

For workflow-based messages: use the existing `TemplateEngine` (`src/gobby/workflows/templates.py`) which is already available in enforcement handlers via the `template_engine` parameter. Simple approach:
1. Policy function checks if message contains `{{`
2. If yes, render with TemplateEngine passing the variable context
3. If no, return as-is (for simple static messages)

Alternatively, just always render — Jinja2 is a no-op on strings without template syntax.

## Prompt Files to Create (3 only — for non-workflow messages)

| File | Source |
|------|--------|
| `src/gobby/install/shared/prompts/mcp/progressive-disclosure.md` | `instructions.py` |
| `src/gobby/install/shared/prompts/agent/skill-hint.md` | `_agent.py:133` |
| `src/gobby/install/shared/prompts/agent/help-content.md` | `_agent.py:144` |
| `src/gobby/install/shared/prompts/agent/skill-not-found.md` | `_agent.py:184` |

These use the existing `PromptLoader` with a thin `render_prompt()` helper (see original plan). Only 4 files instead of 13.

## Verification

1. Edit a message in `session-lifecycle.yaml`, restart daemon, trigger the enforcement, verify new wording appears
2. `uv run pytest tests/workflows/ -v -k enforcement` — existing tests pass
3. `uv run ruff check src/ && uv run mypy src/gobby/workflows/enforcement/` — clean

## Summary

- **9 enforcement messages** → workflow YAML `messages:` dict (editable without code changes)
- **4 non-workflow messages** → bundled prompt `.md` files (editable via DB overrides)
- **0 new frameworks** — extends existing patterns (`block_stop` reason kwarg, `PromptLoader`)
