---
name: task-creation
description: "How to create tasks effectively via gobby-tasks MCP. Covers task types, priorities, when to use each, and writing effective validation criteria."
category: core
metadata:
  gobby:
    audience: all
---

# Task Creation

Create and manage tasks via gobby-tasks MCP. Use progressive discovery for tool schemas.

> **Note:** Claude Code's native task system (TodoWrite/TodoRead) is disabled by Gobby rules.
> All task operations go through **gobby-tasks** MCP. Do not use native Claude task tools — they will be blocked.

---

## Task Types — When to Use Each

| Type | When | Priority | Example |
|------|------|----------|---------|
| `bug` | Something is broken | 1 (high) | "Fix null pointer in session cleanup" |
| `feature` | New capability | 2 (medium) | "Add webhook support for pipeline completion" |
| `epic` | Large feature needing subtasks | 2 (medium) | "Implement knowledge graph integration" |
| `chore` | Maintenance, cleanup | 3 (low) | "Update dependencies to latest versions" |
| `refactor` | Restructure without behavior change | 3 (low) | "Extract validation logic from pipeline executor" |
| `task` | General work that doesn't fit above | 2 (medium) | "Investigate memory leak in long sessions" |

**Nitpicks** — minor cleanup, typos, style fixes — use type `chore` with priority 4 (backlog) and label `["nitpick"]`.

### Priority Scale

| Priority | Meaning | Typical types |
|----------|---------|---------------|
| 1 | High — fix now | Bugs, blockers |
| 2 | Medium — next up | Features, epics |
| 3 | Low — when convenient | Chores, refactors |
| 4 | Backlog — someday | Nitpicks, nice-to-haves |

## Required Fields

| Field | When | Notes |
|-------|------|-------|
| `title` | Always | Imperative form: "Fix X", "Add Y" |
| `category` | Always | Determines validation behavior |
| `validation_criteria` | `category=code` | Creation fails without it |

> **Note:** `session_id` is read automatically from session context — you do not need to pass it to task tools.

### Categories

| Category | Use for |
|----------|---------|
| `code` | Implementation — requires `validation_criteria` |
| `config` | Configuration file changes |
| `docs` | Documentation |
| `test` | Test writing |
| `research` | Investigation, no code output expected |
| `planning` | Design, architecture |
| `manual` | Requires manual verification |

## Writing Effective Validation Criteria

Validation criteria are checked against the diff when closing a task. Write them so an independent reviewer can verify completion.

**Good:** "The `close_task` tests in `test_tasks_coverage.py` pass. `LocalSessionManager` is patched at the correct import path in both tests."

**Bad:** "Tests pass." / "It works." / "Bug is fixed."

Criteria should be:
- **Observable** — can be verified by reading code or running tests
- **Specific** — names files, functions, or behaviors
- **Complete** — covers all acceptance conditions, not just the happy path

## Labels

Use labels for cross-cutting concerns:

| Label | When |
|-------|------|
| `nitpick` | Minor cleanup, typos, style |
| `refactor` | Code restructuring |
| `security` | Security-related work |
| `performance` | Performance improvements |

## Plan Mode

Do **not** create tasks during plan mode unless the user explicitly asks you to. Plan mode is for designing an approach, not organizing work into tasks. Only use task tools in plan mode if the user requests it.

## Claiming

Claim a task before editing files — this sets it to `in_progress` and assigns it to your session. You can auto-claim at creation time with `claim: true`, or claim an existing task separately.

## Error Triage

When you encounter bugs or issues unrelated to your current task, create a bug task for them immediately and continue with your current work. Every error is your error, even if you didn't cause it.
