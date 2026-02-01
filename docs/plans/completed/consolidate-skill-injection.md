# Consolidate Skill Injection into Workflows

## Overview

Move skill injection from hooks to workflows for a single source of truth. Currently hooks inject skills (alwaysApply) while workflows inject handoff context, memory recall, and plan mode prompts. This consolidation reduces token waste and simplifies the architecture.

**Goal:** Reduce startup context from ~180 to ~80 tokens by removing redundant MCP instructions and moving skill injection to workflows.

## Constraints

- CLI-agnostic: No adapter modifications
- Session ID injection stays in hooks (registration responsibility)
- `_injected_sessions` set stays in memory (timing/performance)
- Codex context limitation is pre-existing, not in scope

## Phase 1: Foundation

**Goal:** Wire skill_manager and task_manager to ActionContext

**Tasks:**
- [ ] Add skill_manager field to ActionContext dataclass (category: code)
- [ ] Add task_manager field to ActionContext dataclass (category: code)
- [ ] Pass skill_manager to ActionExecutor in hook_manager.py (category: code)

## Phase 2: Context Sources

**Goal:** Extend inject_context with new sources: skills, task_context, memories

**Tasks:**
- [ ] Add "skills" source to inject_context in context_actions.py (category: code)
- [ ] Add "task_context" source to inject_context (category: code)
- [ ] Add "memories" source wrapping memory_recall_relevant logic (category: code)
- [ ] Support array syntax for multi-source: `source: [skills, task_context]` (category: code)
- [ ] Add helper functions: _format_skills, _restore_skills_from_parent (category: code)

## Phase 3: Workflow Integration

**Goal:** Update session-lifecycle.yaml to use new inject_context sources

**Tasks:**
- [ ] Add inject_context with source: skills to on_session_start (category: config)
- [ ] Add inject_context with source: task_context to on_session_start (category: config)
- [ ] Remove progressive disclosure from plan mode prompt (redundant) (category: config)
- [ ] Update .gobby/workflows/lifecycle/session-lifecycle.yaml (category: config)

## Phase 4: Cleanup

**Goal:** Remove hook-based skill injection and update skills

**Tasks:**
- [ ] Remove _build_skill_injection_context() from _session.py (category: code)
- [ ] Remove _restore_skills_from_parent() from _session.py (category: code)
- [ ] Remove skill injection calls from handle_session_start() (category: code)
- [ ] Set discovering-tools skill to alwaysApply: false (category: config)

## Phase 5: MCP Instructions

**Goal:** Simplify MCP instructions (~180 → ~80 tokens)

**Tasks:**
- [ ] Rewrite build_gobby_instructions() with minimal content (category: code)
- [ ] Remove redundant startup calls (list_mcp_servers, list_skills) (category: code)
- [ ] Keep progressive disclosure hint and critical rule only (category: code)

## Phase 6: Documentation

**Goal:** Update documentation to reflect new architecture

**Tasks:**
- [ ] Update docs/guides/workflows.md with skill/task injection via workflows (category: docs)
- [ ] Update docs/guides/hook-schemas.md noting skills moved to workflows (category: docs)
- [ ] Update docs/guides/mcp-tools.md clarifying progressive disclosure is on-demand (category: docs)
- [ ] Update comments in src/gobby/config/skills.py (category: docs)

## Files to Modify

| File | Changes |
|------|---------|
| `src/gobby/workflows/actions.py` | Add skill_manager, task_manager to ActionContext |
| `src/gobby/hooks/hook_manager.py` | Pass skill_manager to ActionExecutor |
| `src/gobby/workflows/context_actions.py` | Add sources: skills, task_context, memories |
| `src/gobby/mcp_proxy/instructions.py` | Simplify (~180 → ~80 tokens) |
| `src/gobby/hooks/event_handlers/_session.py` | Remove skill injection methods |
| `src/gobby/install/shared/workflows/lifecycle/session-lifecycle.yaml` | Add inject_context calls |
| `.gobby/workflows/lifecycle/session-lifecycle.yaml` | Same |
| `src/gobby/install/shared/skills/discovering-tools/SKILL.md` | Set alwaysApply: false |
| `docs/guides/workflows.md` | Document new sources |
| `docs/guides/hook-schemas.md` | Note migration |
| `docs/guides/mcp-tools.md` | Clarify progressive disclosure |

## Verification

1. **Debug echo test:** Enable `debug_echo_context: true` in session-lifecycle.yaml, start new session, verify skills appear via workflow injection
2. **Unit tests:** `pytest tests/workflows/ tests/hooks/ -v`
3. **Manual test:** Start Claude Code session, verify skill list appears in context
4. **Token count:** Measure MCP instruction tokens before/after (target: 55% reduction)

## Task Mapping

| Plan Item | Task Ref | Status |
|-----------|----------|--------|
| Add skill_manager to ActionContext | | |
| Add task_manager to ActionContext | | |
| Pass skill_manager to ActionExecutor | | |
| Add "skills" source | | |
| Add "task_context" source | | |
| Add "memories" source | | |
| Support array syntax | | |
| Update session-lifecycle.yaml (shared) | | |
| Update session-lifecycle.yaml (local) | | |
| Remove hook skill injection | | |
| Set discovering-tools alwaysApply: false | | |
| Simplify MCP instructions | | |
| Update workflows.md | | |
| Update hook-schemas.md | | |
| Update mcp-tools.md | | |
