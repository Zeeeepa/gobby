# Gobby Workflows

Workflows transform Gobby from a passive session tracker into an **enforcement layer** for AI agent behavior. Instead of relying on prompts to guide behavior, Gobby uses **rules** to enforce tool restrictions, inject context, and manage state -- all declaratively in YAML.

**Key insight**: The LLM doesn't need to remember constraints -- the rule engine evaluates every event and enforces behavior through tool blocks, injected context, and state mutations. The LLM naturally follows because it sees blocked tools and guidance text.

## Architecture

Gobby's workflow system has three layers:

| Layer | Purpose | Model |
|-------|---------|-------|
| **Rules** | Always-on declarative enforcement | Event → condition → effect |
| **On-Demand Workflows** | Step-based state machines | Steps with tool restrictions and transitions |
| **Pipelines** | Deterministic sequential execution | Typed data flow with approval gates |

Rules are the primary enforcement mechanism. On-demand workflows and pipelines build on top for structured multi-step processes.

---

## Rules

Rules are the core building block. Each rule responds to a session event, checks an optional condition, and fires a single effect. Rules are defined in YAML files, stored in the database, and evaluated by the `RuleEngine` on every hook event.

### Rule YAML Format

Rules are organized in YAML files by **group**:

```yaml
# src/gobby/install/shared/rules/worker-safety.yaml

group: worker-safety
tags: [enforcement, safety]

rules:
  no-push:
    description: "Block git push - let the parent session handle pushing."
    event: before_tool
    effect:
      type: block
      tools: [Bash]
      command_pattern: "git\\s+push"
      reason: "Do not push to remote. Let the parent session handle pushing."

  require-task:
    description: "Block file edits without a claimed task."
    event: before_tool
    when: "not task_claimed and not plan_mode"
    effect:
      type: block
      tools: [Edit, Write, NotebookEdit]
      reason: "Claim a task before editing files. Use claim_task() on gobby-tasks."
```

### Rule Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `description` | string | No | -- | Human-readable description |
| `event` | RuleEvent | Yes | -- | Event that triggers this rule |
| `priority` | integer | No | 100 | Evaluation order (lower = first) |
| `when` | string | No | -- | Condition expression (skip if false) |
| `effect` | RuleEffect | Yes | -- | What happens when the rule fires |
| `agent_scope` | list[string] | No | -- | Only active for these agent types |

### File-Level Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `group` | string | Yes | Group name for organization and filtering |
| `tags` | list[string] | No | Tags for discovery and categorization |

---

## RuleEvent Types

Rules respond to 7 event types that map to hooks in the session lifecycle:

| Event | When It Fires | Common Effects |
|-------|--------------|----------------|
| `before_tool` | Before any tool call (native or MCP) | block, set_variable |
| `after_tool` | After a tool call completes | set_variable |
| `before_agent` | Before each agent turn/prompt | inject_context, mcp_call |
| `session_start` | When a session begins (new, clear, compact, resume) | set_variable, mcp_call |
| `session_end` | When a session ends | mcp_call |
| `stop` | When the agent attempts to stop | block, set_variable |
| `pre_compact` | Before context compaction | mcp_call, set_variable |

### Event Data

Each event provides data accessible in `when` conditions:

```yaml
# before_tool / after_tool
event.data.tool_name       # "Edit", "Bash", "mcp__gobby__call_tool"
event.data.tool_input      # Tool arguments dict

# session_start
event.data.source          # "new", "clear", "compact", "resume"

# stop
event.data                 # Stop context
```

---

## RuleEffect Types

Rules fire one of four primitive effects. See [Rule Effects Reference](./workflow-actions.md) for the complete field reference with examples.

| Effect | Purpose | Stops Evaluation? |
|--------|---------|-------------------|
| **block** | Prevent a tool call or action | Yes (first block wins) |
| **set_variable** | Update session state | No |
| **inject_context** | Add text to system message | No (accumulates) |
| **mcp_call** | Trigger an MCP tool call | No |

### Quick Examples

```yaml
# block -- prevent an action
effect:
  type: block
  tools: [Bash]
  command_pattern: "git\\s+push"
  reason: "Do not push to remote."

# set_variable -- update state
effect:
  type: set_variable
  variable: stop_attempts
  value: "variables.get('stop_attempts', 0) + 1"

# inject_context -- add system message text
effect:
  type: inject_context
  template: |
    You are working on task {{ task_ref }}.

# mcp_call -- trigger MCP tool
effect:
  type: mcp_call
  server: gobby-memory
  tool: recall_with_synthesis
  arguments:
    limit: 5
```

---

## Evaluation Flow

When a hook event fires, the `RuleEngine` evaluates all matching rules:

```
Hook event received (e.g., before_tool)
  │
  ├─ 1. Load enabled rules matching this event type
  │     (SQL query on workflow_definitions, workflow_type='rule')
  │
  ├─ 2. Load session overrides (rule_overrides table)
  │     Apply per-session enable/disable toggles
  │
  ├─ 3. Filter by agent_scope (if applicable)
  │     Skip rules not matching the current agent type
  │
  ├─ 4. Sort by priority ascending (10 → 20 → 100)
  │
  └─ 5. Evaluate each rule in order:
        ├─ Check `when` condition → skip if false
        ├─ Apply effect:
        │   ├─ block: check tool matching → if match, STOP (first block wins)
        │   ├─ set_variable: mutate variable immediately
        │   ├─ inject_context: append to context list
        │   └─ mcp_call: record for dispatch
        └─ Continue to next rule (unless blocked)
```

### Key Design Principles

- **First block wins**: Evaluation stops at the first matching `block` effect. No further rules are checked.
- **Variables mutate in-place**: `set_variable` effects are visible to later rules in the same evaluation pass.
- **Context accumulates**: Multiple `inject_context` effects combine (separated by `\n\n`).
- **MCP calls collect**: All `mcp_call` effects are recorded and dispatched after evaluation completes.
- **Conditions skip, not stop**: A `when: false` condition skips the rule but evaluation continues.

### Priority Ordering

Rules evaluate in priority order (lowest number first). Default priority is 100.

```yaml
rules:
  first-rule:
    priority: 10    # Runs first
    ...
  second-rule:
    priority: 20    # Runs second
    ...
  default-rule:     # priority: 100 (default)
    ...
```

Typical priority layout:

| Range | Purpose |
|-------|---------|
| 5-10 | State initialization (reset counters, clear flags) |
| 10-30 | Blocking gates (stop gates, tool restrictions) |
| 30-50 | Secondary gates (memory review, error triage) |
| 50+ | Context injection and MCP calls |

---

## Session Overrides

Rules can be toggled per-session without modifying the rule definition:

```sql
-- Stored in rule_overrides table
(session_id, rule_name, enabled)
```

- **Default**: If no override exists, the rule is enabled.
- **Session-scoped**: Only affects the specified session.
- **Independent**: Different sessions can override the same rule differently.

### Managing Overrides

```bash
# CLI
gobby rules enable <rule-name>
gobby rules disable <rule-name>

# MCP (via gobby-workflows)
# toggle_rule(name, enabled)
```

---

## Condition Expressions

The `when` field uses `SafeExpressionEvaluator` (AST-based, no `eval()`).

### Available Context

| Variable | Description |
|----------|-------------|
| `variables` | Session variables dict (supports `.get('key', default)`) |
| `event` | Hook event object (`event.data`, `event.source`) |
| `tool_input` | Tool input parameters (before_tool/after_tool only) |
| `source` | Event source string |
| Top-level vars | All session variables flattened (e.g., `task_claimed` directly) |

### Supported Operations

```yaml
# Boolean logic
when: "not task_claimed and not plan_mode"
when: "task_claimed or plan_mode"

# Comparisons
when: "variables.get('stop_attempts', 0) < 3"
when: "variables.get('mode_level', 2) >= 1"

# Membership
when: "event.data.get('source') in ['clear', 'compact']"

# Functions
when: "len(variables.get('pending_messages', [])) > 0"
when: "bool(variables.get('task_ref'))"

# Nested access
when: "event.data.get('tool_name') == 'claim_task'"
```

---

## Bundled Rule Groups

Gobby ships with 11 rule groups that are synced to the database on startup:

| Group | Rules | Purpose |
|-------|-------|---------|
| `worker-safety` | 4 | Block git push, force push, destructive git, require task before edit |
| `tool-hygiene` | 2 | Require `uv` for Python, track pending memory review |
| `progressive-discovery` | 9 | Enforce MCP tool discovery order (list_servers → list_tools → get_schema → call_tool) |
| `task-enforcement` | 8 | Block native task tools, require task before edit, commits before close |
| `stop-gates` | 10 | Count stop attempts, block premature stops, reset on new prompt |
| `plan-mode` | 5 | Detect enter/exit plan mode, manage mode_level |
| `memory-lifecycle` | 10 | Memory sync import/export, recall, digest, extraction |
| `context-handoff` | 9 | Session context injection, handoff generation, task sync |
| `auto-task` | 3 | Autonomous task execution context, block premature stops |
| `messaging` | 5 | P2P agent messaging, command activation, tool restrictions |
| `session-defaults` | -- | Variable initialization (not rules, just default values) |

Rule files live in `src/gobby/install/shared/rules/`. Custom rules can be imported via `gobby rules import <file.yaml>`.

---

## Session Variables

Variables are mutable state that persists across the session. Rules read and write variables to coordinate behavior.

### Initialization

Variables are initialized from `session-defaults.yaml` at session start:

```yaml
session_variables:
  chat_mode: "bypass"
  mode_level: 2
  stop_attempts: 0
  task_claimed: false
  plan_mode: false
  require_task_before_edit: true
  require_uv: true
  max_stop_attempts: 3
```

### How Variables Flow

1. **Session starts** → defaults loaded from `session-defaults.yaml`
2. **Rules fire** → `set_variable` effects update state
3. **Rules check** → `when` conditions read current state
4. **Blocks reference** → `reason` templates render variable values (`{{ task_ref }}`)

### Key Variables

| Variable | Type | Purpose |
|----------|------|---------|
| `task_claimed` | bool | Whether a task is claimed in this session |
| `task_ref` | string | Current task reference (e.g., `#1234`) |
| `plan_mode` | bool | Whether the agent is in plan mode |
| `mode_level` | int | Autonomy level (0=plan, 1=accept_edits, 2=normal) |
| `stop_attempts` | int | Consecutive stop attempts (for escape hatch) |
| `max_stop_attempts` | int | Threshold before escape hatch allows stop |
| `require_task_before_edit` | bool | Enforce task-before-edit gate |
| `require_uv` | bool | Enforce `uv` for Python operations |
| `_tool_block_pending` | bool | A tool was just blocked (stop gate uses this) |

---

## On-Demand Workflows

On-demand workflows are step-based state machines for structured multi-step processes. They are activated explicitly and enforce tool restrictions per step.

### Characteristics

- `enabled: false` -- must be activated via CLI or MCP tool
- Has `steps` section with allowed/blocked tools
- Has `transitions` and `exit_conditions`
- Only one on-demand workflow active per session at a time
- Coexists with always-on rules

### Use Cases

- Plan-and-Execute development
- TDD (Test-Driven Development)
- Code Review
- Structured coordination

### Built-in On-Demand Workflows

| Workflow | Description |
|----------|-------------|
| `developer` | Plan → implement → test → review → commit |
| `code-review` | Review → fix → verify → commit |
| `coordinator` | Deterministic agent orchestration loop |
| `merge` | Merge approved branches with cleanup |
| `qa-reviewer` | Review → fix → verify → approve → shutdown |

### Activating

```bash
gobby workflows set developer --session <ID>
```

---

## Pipeline Workflows

Pipelines are sequential execution workflows with typed data flow between steps, approval gates, and deterministic execution.

See [Pipelines Guide](./pipelines.md) for complete documentation.

---

## CLI Commands

### Rules CLI

```bash
# List rules with filters
gobby rules list [--event EVENT] [--group GROUP] [--enabled] [--disabled] [--json]

# Show rule details
gobby rules show <name> [--json]

# Enable/disable a rule
gobby rules enable <name>
gobby rules disable <name>

# Import rules from YAML file
gobby rules import <file.yaml>

# Export rules as YAML
gobby rules export [--group GROUP]

# View rule audit log
gobby rules audit [--session ID] [--limit N] [--json]
```

### Workflows CLI

```bash
# List workflows
gobby workflows list [--all] [--global] [--json]

# Show workflow details
gobby workflows show <name> [--json]

# Activate on-demand workflow
gobby workflows set <name> [--session ID] [--step STEP]

# Check workflow status
gobby workflows status [--session ID] [--json]

# Clear/deactivate workflow
gobby workflows clear [--session ID] [--force]

# Manual step transition (escape hatch)
gobby workflows step <step-name> [--session ID] [--force]

# Reset workflow to initial step
gobby workflows reset [--session ID] [--force]

# Disable/enable workflow enforcement
gobby workflows disable [--session ID] [--reason TEXT]
gobby workflows enable [--session ID]

# Validate workflow definition
gobby workflows check <name> [--json]

# View audit log
gobby workflows audit [--session ID] [--type TYPE] [--result RESULT] [--limit N] [--verbose] [--json]

# Set variable
gobby workflows set-var <name> <value> [--session ID] [--json]
```

---

## MCP Tools

### Rule Tools (gobby-workflows)

| Tool | Description |
|------|-------------|
| `list_rules` | List rules with optional event/group filter |
| `list_rule_groups` | List available rule groups |
| `get_rule_detail` | Get full rule definition |
| `toggle_rule` | Enable/disable a rule for the session |

### Workflow Tools (gobby-workflows)

| Tool | Description |
|------|-------------|
| `get_workflow_status` | Current workflow state |
| `activate_workflow` | Activate an on-demand workflow |
| `deactivate_workflow` | Clear active workflow |
| `force_transition` | Manual step transition |
| `set_variable` | Set a session variable |
| `get_variable` | Get a session variable value |
| `list_variables` | List all session variables |

---

## Troubleshooting

### Tool Unexpectedly Blocked

```bash
# Check which rules are active
gobby rules list --enabled

# Check audit log for the block
gobby rules audit --session <ID> --limit 10

# Temporarily disable a rule
gobby rules disable <rule-name>
```

### Agent Can't Stop

The stop-gates rule group controls stop behavior. The escape hatch allows stopping after `max_stop_attempts` (default: 3) consecutive attempts.

```bash
# Check stop_attempts variable
gobby workflows set-var stop_attempts 0 --session <ID>

# Or disable the stop gate
gobby rules disable require-task-close
```

### Variables Not Taking Effect

```bash
# Check current variable values
gobby workflows status --session <ID> --json

# Override a variable
gobby workflows set-var <name> <value> --session <ID>
```

### Rule Not Firing

1. Check the rule is enabled: `gobby rules show <name>`
2. Check the event matches: rule `event` must match the hook event type
3. Check the `when` condition: test with simpler conditions first
4. Check priority: a higher-priority block may be stopping evaluation before your rule

---

## File Locations

| Path | Purpose |
|------|---------|
| `src/gobby/install/shared/rules/*.yaml` | Bundled rule definitions |
| `src/gobby/workflows/rule_engine.py` | Rule evaluation engine |
| `src/gobby/workflows/definitions.py` | Rule models (RuleEvent, RuleEffect, RuleDefinitionBody) |
| `src/gobby/workflows/safe_evaluator.py` | Safe expression evaluator |
| `src/gobby/cli/rules.py` | Rules CLI commands |
| `src/gobby/servers/routes/rules.py` | Rules HTTP API |
| `~/.gobby/gobby-hub.db` | SQLite database (rules stored in workflow_definitions) |
