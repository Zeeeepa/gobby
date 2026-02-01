# Plan: Consolidate Skill Injection into Workflows

## Current Startup Context (Baseline)

What I received at session start:

### From SessionStart Hook (`additionalContext`)
```
SessionStart:startup hook success: Success
```

### From UserPromptSubmit Hook (`additionalContext`)
```
The following skills are available for use with the Skill tool:

- keybindings-help: Use when the user wants to customize keyboard shortcuts...
- g: Shorthand alias for /gobby...
- gobby: Unified router for Gobby skills and MCP servers...
- frontend-design:frontend-design: Create distinctive, production-grade frontend interfaces...
```

```
<project-memory>
## Project Context
...
## Patterns
...
## Facts
...
</project-memory>

Gobby Session ID: #687 (or 70cd9d8b-3583-4667-8b34-ea439a6c59ff)
CLI-Specific Session ID (external_id): fd5c6ce9-acb3-4737-8478-a8438327db0d
```

### From MCP Server Instructions
```xml
<gobby_system>
<startup>
At the start of EVERY session:
1. `list_mcp_servers()` — Discover available servers
2. `list_skills()` — Discover available skills
3. Session ID: Look for `Gobby Session Ref:` or `Gobby Session ID:` in your context.
   If missing, call: get_current_session(...)
</startup>
...
</gobby_system>
```

### Observations
1. **Skills injected via UserPromptSubmit**, not SessionStart
2. **Session ID injected** with both formats (#687 and full UUID)
3. **MCP instructions redundant** - tell agent to call list_skills() but skills already injected
4. **Memory injected** via `<project-memory>` block

## Context

Hook handlers predate the workflow system. Currently:
- **Hooks** inject: session ID, active task, **skills (alwaysApply)**
- **Workflows** inject: handoff context, memory recall, plan mode prompt

We're consolidating skill injection into workflows for a single source of truth.

## Changes Overview

1. **Simplify MCP instructions** - Remove redundant startup calls
2. **Create `inject_skills` workflow action** - Move skill logic from hooks to workflows
3. **Wire skill_manager to ActionContext** - Enable workflows to access skills
4. **Update session-lifecycle.yaml** - Add inject_skills action
5. **Remove hook-based skill injection** - Clean up _session.py

## Detailed Changes

### 1. Simplify MCP Instructions (Target: ~80 tokens)

**File:** `src/gobby/mcp_proxy/instructions.py`

Current: ~180 tokens, tells agents to call list_skills() even though skills are injected.

New minimal version:

```python
def build_gobby_instructions() -> str:
    return """<gobby>

Session ID is injected automatically. References use #N format.

Tool discovery (progressive):
  list_tools(server) → get_tool_schema(server, tool) → call_tool(server, tool, args)

Skill guidance:
  get_skill(name) or search_skills(query)

Rules:
  - Create/claim task before Edit/Write/NotebookEdit
  - Pass session_id to task operations

</gobby>"""
```

**Token savings**: ~180 → ~80 tokens (55% reduction)

### 2. Add skill_manager to ActionContext

**File:** `src/gobby/workflows/actions.py`

```python
@dataclass
class ActionContext:
    # ... existing fields ...
    skill_manager: Any | None = None  # ADD THIS
```

**File:** `src/gobby/hooks/hook_manager.py` (line ~264)

```python
self._action_executor = ActionExecutor(
    # ... existing args ...
    skill_manager=self._skill_manager,  # ADD THIS
)
```

### 3. Extend inject_context with New Sources

**File:** `src/gobby/workflows/context_actions.py`

Instead of creating separate actions, extend the existing `inject_context` dispatch pattern:

```python
# Add to inject_context function after existing sources:

elif source == "skills":
    # Get skill manager from context (need to pass via kwargs or action context)
    skill_manager = kwargs.get("_skill_manager")
    skills_config = kwargs.get("_skills_config")

    if not skill_manager:
        return None

    # Check if injection enabled
    if skills_config and not skills_config.inject_core_skills:
        return None

    # Get injection format
    injection_format = kwargs.get("format") or (
        skills_config.injection_format if skills_config else "summary"
    )
    if injection_format == "none":
        return None

    # Discover and format skills
    core_skills = skill_manager.discover_core_skills()
    always_apply = [s for s in core_skills if s.always_apply]

    # Restore from parent (if applicable)
    parent_skills = _restore_skills_from_parent(session_manager, session_id)

    # Format output
    content = _format_skills(always_apply, parent_skills, injection_format)

elif source == "task_context":
    # Get current task from session
    current_session = session_manager.get(session_id)
    if current_session and current_session.current_task_id:
        task = task_manager.get(current_session.current_task_id)
        if task:
            content = f"## Active Task\nYou are working on: {task.title} (#{task.seq_num})"
```

**Usage in YAML:**
```yaml
on_session_start:
  - action: inject_context
    source: skills
    format: summary

  - action: inject_context
    source: task_context
```

### 4. Update session-lifecycle.yaml

**Files:**
- `src/gobby/install/shared/workflows/lifecycle/session-lifecycle.yaml`
- `.gobby/workflows/lifecycle/session-lifecycle.yaml`

```yaml
on_session_start:
  # ... existing actions ...

  # Inject core skills (moved from hooks)
  - action: inject_context
    source: skills
    format: summary

  # Inject task context (moved from hooks)
  - action: inject_context
    source: task_context
```

### 5. Remove Hook-based Skill Injection

**File:** `src/gobby/hooks/event_handlers/_session.py`

Remove:
- `_build_skill_injection_context()` method (lines 458-536)
- `_restore_skills_from_parent()` method (lines 538-573)
- Calls to these methods in `handle_session_start()` (lines 152-154)

## Files Summary

### Core Changes
| File | Action |
|------|--------|
| `src/gobby/mcp_proxy/instructions.py` | Simplify (~180 → ~80 tokens) |
| `src/gobby/workflows/actions.py` | Add skill_manager, task_manager to ActionContext |
| `src/gobby/hooks/hook_manager.py` | Pass skill_manager to ActionExecutor |
| `src/gobby/workflows/context_actions.py` | Add sources: `skills`, `task_context`, `memories` |
| `src/gobby/workflows/memory_actions.py` | Deprecate `memory_recall_relevant`, keep as internal |
| `src/gobby/install/shared/workflows/lifecycle/session-lifecycle.yaml` | Update to use `inject_context` for all |
| `.gobby/workflows/lifecycle/session-lifecycle.yaml` | Same |
| `src/gobby/hooks/event_handlers/_session.py` | Remove skill + task injection methods |

### Skills to Update
| File | Action |
|------|--------|
| `src/gobby/install/shared/skills/discovering-tools/SKILL.md` | Set `alwaysApply: false` - keep for on-demand reference |
| `src/gobby/install/shared/skills/claiming-tasks/SKILL.md` | Keep as-is (task blocking still relevant) |
| `src/gobby/install/shared/skills/doctor/SKILL.md` | Keep - diagnostic calls still valid |
| `src/gobby/install/shared/skills/gobby/SKILL.md` | Keep - MCP router still needed |

### Redundancy Elimination
Progressive disclosure is currently taught in THREE places (~630 tokens total):
1. MCP instructions `<tool_discovery>` (~50 tokens) - **KEEP as source of truth**
2. session-lifecycle.yaml plan mode prompt (lines 101-106, ~80 tokens) - **REMOVE**
3. discovering-tools skill (~500+ tokens) - **Set alwaysApply: false**

**Net savings**: ~580 tokens per session

### Documentation to Update
| File | Action |
|------|--------|
| `docs/guides/workflows.md` | Add skill/task injection via workflows |
| `docs/guides/hook-schemas.md` | Note skills moved from hooks to workflows |
| `docs/guides/mcp-tools.md` | Clarify progressive disclosure is on-demand |

### Config to Review
| File | Action |
|------|--------|
| `src/gobby/config/skills.py` | Update comments (workflow-based, not hook-based) |

## Minimal Agent Context Design

Based on investigation, the ideal startup context is **50-100 tokens**:

| Component | Tokens | Purpose |
|-----------|--------|---------|
| Session ID | 10-20 | Required for all task operations |
| Progressive disclosure hint | 20-30 | Teaches efficient tool discovery |
| One critical rule | 10-15 | "Create/claim task before editing" |
| Skill pointer | 10-15 | Where to get deeper guidance |

**Everything else is on-demand:**
- `list_mcp_servers()` → ~50 tokens when called
- `list_skills()` → ~100 tokens when called
- `get_skill(name)` → 300-500 tokens per skill
- `get_tool_schema()` → 200-400 tokens per tool

**Current waste**: MCP instructions tell agents to call `list_skills()` at startup, but skills are already injected via hooks. Agents don't need both.

## CLI Compatibility

Changes are **CLI-agnostic** - no adapter modifications needed.

| CLI | Context Injection | Notes |
|-----|-------------------|-------|
| Claude Code | `additionalContext` in `hookSpecificOutput` | Full support |
| Gemini | `additionalContext` in `hookSpecificOutput` | Full support |
| Codex | None | Pre-existing limitation (approval-only) |
| Antigravity | Uses Claude Code format | Full support |

**Unified flow:**
```
Workflow inject_context → HookResponse.context → Adapter translates to CLI format
```

**Only CLI-specific condition in session-lifecycle.yaml:**
- Gemini compact trigger (lines 197-221) - skips auto-compaction, only manual

## What We're NOT Changing

- **`_injected_sessions` in-memory set** - Timing issues, performance, ephemeral by design
- **Session ID injection** - Stays in hooks (session registration is hook responsibility)
- **Adapter code** - No modifications needed, unified context flow
- **Codex context support** - Pre-existing limitation, not in scope

## Verification

### Debug Echo (Primary Method)
Use `debug_echo_context: true` in session-lifecycle.yaml (already enabled) to see all context injection in terminal:
```yaml
# .gobby/workflows/lifecycle/session-lifecycle.yaml
variables:
  debug_echo_context: true
```

This echoes `additionalContext` to `<system-message>` in terminal output. After changes:
- Skills should appear via workflow `inject_context(source="skills")`
- Task context should appear via workflow `inject_context(source="task_context")`
- Progressive disclosure should NOT appear in plan mode prompt (removed as redundant)

### Automated Tests
```bash
pytest tests/workflows/ tests/hooks/ -v
pytest tests/mcp_proxy/test_instructions.py -v  # if exists
```

### Database Verification
Query workflow_states to confirm skill injection is tracked:
```sql
SELECT session_id, variables FROM workflow_states
WHERE variables LIKE '%skill%' ORDER BY updated_at DESC LIMIT 5;
```

### Transcript Verification
Check session transcript for skill injection:
```bash
# Find recent session transcripts
ls -la ~/.gobby/transcripts/ | tail -5

# Grep for skill injection in transcript
grep -l "Available Skills" ~/.gobby/transcripts/*.json | head -3
```

### MCP Tool Verification
```python
# Via gobby MCP
call_tool("gobby-sessions", "get_current_session", {"external_id": "...", "source": "claude"})
# Check response includes session with workflow state
```

## Deliverables

1. Code changes as described above
2. Report documenting findings: `./reports/feat-hooks-workflows.md`

### Report Contents (`./reports/feat-hooks-workflows.md`)

```markdown
# Feature: Consolidate Skill Injection into Workflows

## Background
- Hook handlers built before workflows existed
- Skills were injected via `_build_skill_injection_context()` in hooks
- Other context (handoff, memory) injected via workflow `inject_context`

## Minimal Context Design

### Target: 50-100 tokens at startup

| Component | Tokens | Source |
|-----------|--------|--------|
| Session ID | 10-20 | Hook injection |
| Progressive disclosure | 20-30 | MCP instructions |
| Critical rule | 10-15 | MCP instructions |
| Skill pointer | 10-15 | MCP instructions |

### On-demand (not at startup)
- Server list: `list_mcp_servers()` → ~50 tokens
- Skill list: `list_skills()` → ~100 tokens
- Skill content: `get_skill(name)` → 300-500 tokens
- Tool schema: `get_tool_schema()` → 200-400 tokens

## Changes Made
- Extended `inject_context` with `source="skills"` and `source="task_context"`
- Wired `skill_manager` and `task_manager` to ActionContext
- Added inject_context sources to session-lifecycle.yaml
- Removed hook-based skill + task injection from _session.py
- Simplified MCP instructions (~180 → ~80 tokens)

## Architecture
Single omnibus action for all context injection (UX simplification for workflow authors):

| Source | Purpose | Status |
|--------|---------|--------|
| `previous_session_summary` | Parent session handoff | Exists |
| `compact_handoff` | Compact continuation | Exists |
| `artifacts` | Captured artifacts | Exists |
| `workflow_state` | Current state dump | Exists |
| `memories` | Semantic recall + inject | **NEW** (wraps `memory_recall_relevant`) |
| `skills` | AlwaysApply skills | **NEW** (replaces hook injection) |
| `task_context` | Current task info | **NEW** (replaces hook injection) |
| `skill_suggestion` | Suggest skills for task | **NEW** (optional, future) |

**Usage - Multi-source in single action:**
```yaml
on_session_start:
  - action: inject_context
    source: skills, task_context, handoff
    format: summary  # applies to skills

on_before_agent:
  - action: inject_context
    source: memories, skill_suggestion
    limit: 5           # applies to memories
    min_importance: 0.7
```

Or as explicit list:
```yaml
- action: inject_context
  source:
    - skills
    - memories
    - task_context
```

**Benefits:**
- One action, multiple activations
- Less YAML, easier to scan
- Order determines injection order
- Can still call individually when needed
- Source-specific params (limit, format) apply to relevant source

**Keep separate (different purpose):**
- Task CRUD: MCP tools (`create_task`, `claim_task`, `close_task`)
- Memory save/extract: Separate actions (not injection)

## Startup Context (Before)
~180 token MCP instructions + skill injection via hooks

## Startup Context (After)
~80 token MCP instructions + skill injection via workflows

## Verification Results
- [ ] Skills appear in additionalContext
- [ ] Parent skills restored on handoff
- [ ] injection_format: "none" disables injection
- [ ] All tests pass
- [ ] MCP instructions simplified
- [ ] Database shows workflow_states with skill tracking
- [ ] Transcript grep confirms skill injection

## Architecture Decision
Single source of truth: All context injection via workflows.
Hooks handle: session registration, task state, session ID.
```
