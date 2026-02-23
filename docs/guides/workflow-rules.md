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
