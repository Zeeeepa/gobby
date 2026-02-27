# Rule Authoring Guide

Practical guidance for writing Gobby rules. For the full reference (events, effects, fields), see [workflows.md](./workflows.md).

---

## Variable Safety in `when` Conditions

Rule `when` conditions are evaluated by `SafeExpressionEvaluator`, which operates on session variables. How you reference a variable determines what happens when it doesn't exist yet.

### The Problem

```yaml
# DANGEROUS in a block rule
when: "task_claimed and some_other_condition"
```

If `task_claimed` was never set (e.g., a Q&A session where no task was created), the evaluator raises `NameError`. For `block` effects, **unhandled errors fail closed** -- the rule always blocks, even when it shouldn't.

### Safe Patterns

**Use `variables.get()` with a default:**

```yaml
# Safe -- returns False if task_claimed was never set
when: "variables.get('task_claimed', False) and some_other_condition"
```

**Or create an init rule in `session-defaults/`:**

```yaml
# src/gobby/install/shared/rules/session-defaults/init-task-claimed.yaml
tags: [session-defaults, initialization]

rules:
  init-task-claimed:
    description: "Default task_claimed to false"
    event: session_start
    enabled: false
    priority: 1
    when: "variables.get('task_claimed') is None"
    effect:
      type: set_variable
      variable: task_claimed
      value: false
```

With an init rule, the variable always exists by the time other rules reference it, so bare `task_claimed` is safe.

### Which Approach to Use

| Approach | When to use |
|----------|-------------|
| `variables.get('var', default)` | One-off references; quick and self-contained |
| Init rule in `session-defaults/` | Variable used by multiple rules; systemic default needed |
| Both | Belt and suspenders for critical `block` rules |

### Rule of Thumb

**Never use bare variable names in `block` rules without either a default or an init rule.** Other effect types (`set_variable`, `inject_context`, `mcp_call`) are less dangerous since a NameError there doesn't block the agent, but it's still good practice to be defensive.

---

## Hardcoded Engine Behaviors

The rule engine has several behaviors baked into `RuleEngine.evaluate()` that fire **before** any user-defined rules are evaluated. These are universal safety mechanisms — not configurable via YAML.

### Consecutive Tool Block Counter

When a rule blocks a `BEFORE_TOOL` event, the engine sets `tool_block_pending = True` and records which tool was blocked in `_last_blocked_tool`. On the next `BEFORE_TOOL`:

- **Same tool retried**: The `consecutive_tool_blocks` counter increments. At count >= 2 (i.e., 3rd attempt), a hardcoded block fires with an escalating message telling the agent to try a different approach.
- **Different tool attempted**: The counter resets to 0 and the event proceeds to normal rule evaluation. This allows the agent to recover by using other tools (Read, Bash, etc.) even after a tool is blocked.

The counter and `_last_blocked_tool` are cleared on:
- `BEFORE_AGENT` (new user turn)
- Successful `AFTER_TOOL` (tool succeeded, crisis over)

**Session variables involved:**

| Variable | Type | Purpose |
|----------|------|---------|
| `tool_block_pending` | bool | Set when any tool is blocked (rule or hardcoded) |
| `_last_blocked_tool` | str | Name of the most recently blocked tool |
| `consecutive_tool_blocks` | int | How many times `_last_blocked_tool` was retried |

### Tool Block Stop Gate

When a stop event fires while `tool_block_pending` is true, the engine blocks the stop with "A tool just failed. Read the error and recover — do not stop." This is **self-clearing**: `tool_block_pending` is set to false after the block, so the next stop attempt proceeds to normal rule evaluation.

### Force Allow Stop (Catastrophic Failure Bypass)

When a tool failure contains catastrophic patterns (out of usage, rate limit, quota exceeded, billing, account suspended), the engine sets `force_allow_stop = True`. The next stop event bypasses all stop gates unconditionally. Self-clearing after one use.

### Awaiting Tool Use

Set to `True` on `BEFORE_AGENT`, cleared on successful `AFTER_TOOL`. Used by the `block-stop-awaiting-tool-use` rule to prevent premature stops before the agent has used any tools.
