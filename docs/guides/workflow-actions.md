> **DEPRECATED**: This document is superseded by [Rules](./rules.md) which includes the complete effects reference. This file is retained for reference only.

# Rule Effects Reference

Rules in Gobby use four primitive effect types to control agent behavior. Each rule fires a single effect when its conditions are met. This document is the complete reference for all effect types.

## Overview

| Effect Type | Purpose | Stops Evaluation? |
|-------------|---------|-------------------|
| `block` | Prevent a tool call or action | Yes (first block wins) |
| `set_variable` | Update session state | No (continues to next rule) |
| `inject_context` | Add text to system message | No (accumulates) |
| `mcp_call` | Trigger an MCP tool call | No (recorded for dispatch) |

Effects are defined in the `effect` field of a rule:

```yaml
rules:
  my-rule:
    event: before_tool
    when: "optional_condition"
    effect:
      type: block | set_variable | inject_context | mcp_call
      # ... type-specific fields
```

## Conditional Execution

All rules support an optional `when` field. The condition is evaluated before the effect fires. If false, the rule is skipped (evaluation continues to the next rule).

```yaml
when: "not task_claimed and not plan_mode"
```

The `when` expression has access to:

- `variables` -- Session variables as a dict (supports `variables.get('key', default)`)
- All session variables flattened to top level (e.g., `task_claimed` instead of `variables['task_claimed']`)
- `event` -- The hook event object (`event.data`, `event.source`)
- `tool_input` -- Tool input parameters (for `before_tool` / `after_tool` events)
- `source` -- Event source string (e.g., `"new"`, `"clear"`, `"compact"`)
- Built-in functions: `len()`, `str()`, `int()`, `bool()`, `isinstance()`

Expressions are evaluated by `SafeExpressionEvaluator` (AST-based, no `eval()`).

---

## `block` -- Prevent an Action

Blocks a tool call, stop attempt, or other action. The first matching block rule stops evaluation -- no further rules are checked.

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | `"block"` | Yes | Effect type |
| `reason` | `string` | Yes | Message shown to the agent explaining why the action was blocked |
| `tools` | `list[string]` | No | Native tools to match (e.g., `["Edit", "Write", "Bash"]`) |
| `mcp_tools` | `list[string]` | No | MCP tools to match (e.g., `["gobby-tasks:close_task", "server:*"]`) |
| `command_pattern` | `string` | No | Regex pattern to match Bash command content |
| `command_not_pattern` | `string` | No | Negative regex -- exclude commands matching this pattern |

### Tool Matching

- If `tools` is specified, only those native tools are blocked.
- If `mcp_tools` is specified, only those MCP tools are blocked. Supports wildcards (`"server:*"` blocks all tools on a server).
- If neither is specified, the block applies to all tools for the event.
- `command_pattern` and `command_not_pattern` apply only to the `Bash` tool.

### Examples

**Block file edits without a claimed task:**

```yaml
require-task:
  event: before_tool
  when: "not task_claimed and not plan_mode"
  effect:
    type: block
    tools: [Edit, Write, NotebookEdit]
    reason: "Claim a task before editing files. Use claim_task() on gobby-tasks."
```

**Block git push:**

```yaml
no-push:
  event: before_tool
  effect:
    type: block
    tools: [Bash]
    command_pattern: "git\\s+push"
    reason: "Do not push to remote. Let the parent session handle pushing."
```

**Block destructive git operations:**

```yaml
no-destructive-git:
  event: before_tool
  effect:
    type: block
    tools: [Bash]
    command_pattern: "git\\s+(reset\\s+--hard|clean\\s+-f|checkout\\s+(--\\s+)?\\.)"
    reason: "Destructive git operations are not allowed without explicit approval."
```

**Block stop when a tool was just blocked:**

```yaml
block-stop-after-tool-block:
  event: stop
  priority: 20
  when: "variables.get('_tool_block_pending') and variables.get('stop_attempts', 0) < 3"
  effect:
    type: block
    reason: "Do not stop. A tool was blocked -- follow the instructions in the error message."
```

**Block stop with template variables in reason:**

```yaml
require-task-close:
  event: stop
  priority: 50
  when: "task_claimed and variables.get('stop_attempts', 0) < 3"
  effect:
    type: block
    reason: |
      Task {{ task_ref }} is still in_progress. Commit and close_task().
```

---

## `set_variable` -- Update Session State

Mutates a session variable in-place. Later rules in the evaluation order see the updated value immediately.

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | `"set_variable"` | Yes | Effect type |
| `variable` | `string` | Yes | Variable name to set |
| `value` | `any` | Yes | Value to assign -- literal or expression |

### Value Expressions

Values can be **literals** or **expressions**:

- **Literals**: `true`, `false`, `42`, `"hello"`, `[]`, `{}`
- **Expressions**: Strings containing operators or function calls are evaluated by `SafeExpressionEvaluator`

Expression indicators (if any of these appear in a string value, it's treated as an expression):
- `variables.`, `event.`, `tool_input.`
- `len(`, `str(`, `int(`, `bool(`
- `+`, `-`, `*`, `/`, `and`, `or`, `not`
- `==`, `!=`, `<`, `>`, `<=`, `>=`

### Examples

**Increment a counter:**

```yaml
increment-stop-attempts:
  event: stop
  priority: 10
  effect:
    type: set_variable
    variable: stop_attempts
    value: "variables.get('stop_attempts', 0) + 1"
```

**Set a boolean flag:**

```yaml
clear-pending-reset:
  event: session_start
  when: "variables.get('pending_context_reset')"
  effect:
    type: set_variable
    variable: pending_context_reset
    value: false
```

**Reset a list:**

```yaml
reset-memory-tracking:
  event: session_start
  priority: 5
  when: "event.data.get('source') in ['clear', 'compact']"
  effect:
    type: set_variable
    variable: _injected_memory_ids
    value: []
```

**Track state based on tool usage:**

```yaml
mark-task-claimed:
  event: after_tool
  when: "event.data.get('tool_name') == 'claim_task'"
  effect:
    type: set_variable
    variable: task_claimed
    value: true
```

---

## `inject_context` -- Add Text to System Message

Appends text to the hook response's context field, which is injected into the agent's system message. Multiple `inject_context` effects accumulate (separated by `\n\n`).

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | `"inject_context"` | Yes | Effect type |
| `template` | `string` | Yes | Text to inject. Supports `{{ variable }}` template substitution. |

### Template Variables

Templates use Jinja2-style `{{ }}` syntax. Available variables include all session variables and special context variables.

### Examples

**Inject previous session summary on context clear:**

```yaml
inject-previous-session-summary:
  event: session_start
  priority: 10
  when: "event.data.get('source') == 'clear'"
  effect:
    type: inject_context
    template: |
      ## Previous Session Context
      *Injected by Gobby session handoff*

      {{ summary }}
```

**Inject task context:**

```yaml
inject-task-context:
  event: before_agent
  when: "task_claimed"
  effect:
    type: inject_context
    template: |
      You are working on task {{ task_ref }}: {{ task_title }}
      Validation criteria: {{ validation_criteria }}
```

---

## `mcp_call` -- Trigger MCP Tool Execution

Records an MCP tool call for the dispatcher to execute. Can run synchronously (blocking) or in the background (async).

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | `"mcp_call"` | Yes | Effect type |
| `server` | `string` | Yes | MCP server name (e.g., `"gobby-memory"`, `"gobby-tasks"`) |
| `tool` | `string` | Yes | Tool name on the server |
| `arguments` | `dict` | No | Arguments to pass to the tool |
| `background` | `boolean` | No | If `true`, run async with zero latency (default: `false`) |

### Examples

**Import memories on session start:**

```yaml
memory-sync-import:
  event: session_start
  priority: 30
  effect:
    type: mcp_call
    server: gobby-memory
    tool: sync_import
```

**Recall relevant memories before each prompt:**

```yaml
memory-recall-on-prompt:
  event: before_agent
  priority: 10
  effect:
    type: mcp_call
    server: gobby-memory
    tool: recall_with_synthesis
    arguments:
      limit: 5
    background: false
```

**Background digest (zero latency):**

```yaml
memory-background-digest:
  event: before_agent
  priority: 11
  effect:
    type: mcp_call
    server: gobby-memory
    tool: update_session_digest
    background: true
```

**Capture baseline dirty files:**

```yaml
capture-baseline-on-start:
  event: session_start
  priority: 8
  effect:
    type: mcp_call
    server: gobby-sessions
    tool: capture_baseline_dirty_files
```

---

## Evaluation Order and Interactions

### Priority

Rules evaluate in **priority order** (lowest number first). Default priority is 100.

```yaml
rules:
  first:
    priority: 10   # Evaluates first
    ...
  second:
    priority: 20   # Evaluates second
    ...
  last:
    priority: 100  # Evaluates last (default)
    ...
```

### Effect Interactions

1. **`set_variable` is immediate**: Later rules see updated values in their `when` conditions.
2. **`inject_context` accumulates**: Multiple inject effects combine into one context block.
3. **`mcp_call` records**: All MCP calls are collected and dispatched after evaluation.
4. **`block` terminates**: The first matching block stops evaluation. No further rules run.

### Typical Priority Layout

| Priority | Purpose | Example |
|----------|---------|---------|
| 5-10 | State initialization | Reset counters, clear flags |
| 10-20 | Blocking gates | Stop gates, tool restrictions |
| 20-40 | Secondary gates | Memory review, error triage |
| 50+ | Context injection | Memory recall, task context |
| 100 | Default | Most rules |
