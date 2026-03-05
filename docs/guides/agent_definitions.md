> **DEPRECATED**: This document is superseded by [Agents](./agents.md). This file is retained for reference only.

# Agent Definitions Guide

Agent Definitions (Agents V3) represent a configuration-driven identity and orchestration model for Gobby agents. They provide a unified schema for spawning agents and establishing persona/context across interactive sessions.

## Agent Definition Schema

Agent Definitions are stored in the database as `workflow_definitions` where `workflow_type = 'agent'`. Below is an overview of the schema structure:

```yaml
name: "worker"
description: "A generalized worker agent"
extends: "default"

# Prompt fields
role: "You are an autonomous AI coding assistant."
goal: "Complete the task specified by the user."
personality: "Helpful, concise, technical."
instructions: "Always verify your code against tests before finishing."

# Execution details
provider: "inherit"
model: "inherit"
mode: "self"
isolation: "worktree"
base_branch: "inherit"
timeout: 120.0
max_turns: 15

# Orchestration context
workflows:
  pipeline: null
  rules: []
  rule_selectors:
    include: ["tag:gobby"]
    exclude: ["name:dangerous-rule"]
  skill_selectors:
    include: ["*"]
    exclude: []
  variable_selectors:
    include: ["*"]
  skill_format: "tools"
  variables:
    chat_mode: false
```

### The `inherit` Sentinel
For `provider`, `model`, and `base_branch`, the sentinel value `"inherit"` means the agent will adopt its configuration from its parent session (if spawned) or from the system-level global defaults (if at the root level).

### Execution Modes
- **`mode: self` (Persona)**: Identifies an agent running inline in the current interactive session (e.g., your interactive terminal or chat session). No subprocess is spawned; the definition manages your preamble, injected rules, skills, and variables.
- **`mode: terminal`, `headless`, `embedded` (Process)**: Used when spawning autonomous subagents that run in isolated, background, or embedded environments.

## The `extends` Inheritance Model

You can compose agents hierarchically using the `extends` field. When an agent definition specifies an `extends: "parent-agent"` field, the resolving engine will deep-merge properties.

**Merge Behavior**:
- **Scalars** (like `provider` or `timeout`): Child values override the parent ones, unless the child value is explicitly `None` (or not defined).
- **Prompt Lists** (`role`, `goal`, `personality`, `instructions`): These strings are appended to build a unified preamble.
- **Workflow Selections**: `rules` arrays are merged. `AgentSelectors` (`rule_selectors`, `skill_selectors`, `variable_selectors`) are merged such that `include` and `exclude` lists accumulate from parent to child. 

*(Note: Inheritance chains are restricted to a maximum cycle depth of 10 to prevent infinite recursion).*

## Selectors Engine

Agents determine active rules, skills, and variables using an advanced inclusion/exclusion selector engine. By default, selectors are permissive (`["*"]`). 

**Syntax Options**:
- `*`: Matches everything.
- `<name>` (bare string): Exact name match.
- `tag:<tag_name>`: Matches entities featuring the specified tag.
- `group:<group_name>`: Matches entities belonging to the specified group.
- `source:<source_name>`: Matches origins (`bundled`, `installed`, `template`, `user`).
- `category:<category>`: Matches specific skill or entity categories.

**Resolution Priority**: `exclude` always takes precedence over `include`. For example, `include: ["tag:safety"]` but `exclude: ["name:strict-safety"]` will block `strict-safety` even if it has the `safety` tag.

## Skill Configuration
Agent Definitions control skill injections directly:
- **`skill_selectors`**: Dictates which skills are available to the agent via `include`/`exclude`. Passing `null` acts as a permissive `["*"]` default, opening up the entire registry.
- **`skill_format`**: Controls how skills are injected (e.g., `tools` for MCP tool stubs or `prompt` for raw text). If omitted, falls back to the system default format configured in `injector.py`.

## Variable Definitions

Variables define pre-seeded session data defaults. In Agents V3, `VariableDefinitionBody` models have replaced `init-*` startup rules for setting simple constants.

```yaml
# Shared YAML for a Variable
variable: "enforce_tool_schema_check"
value: true
description: "Controls whether strict MCP schema checks are enforced."
```

When an agent loads, its `variable_selectors` determines which `VariableDefinitions` are synced into the active `session_variables` directory upon startup. If `variable_selectors` is `null`, it loads all enabled variables in the system DB. This removes the legacy dependency on one-off rules spanning hundreds of lines.

## Default Agent Activation (`default_agent`)

When a new interactive session or root session begins, `_session.py` invokes `_activate_default_agent()`. 
1. It queries the daemon config `default_agent` (usually "default").
2. It resolves the full `default` Agent Definition chain.
3. It passes `rule_selectors`, `skill_selectors`, and `variable_selectors` through the resolution engine against the database.
4. The approved subset of rules, skills, and variables are merged and updated into `session_variables` (e.g., `_active_rule_names`, `_active_skill_names`).

## Examples

### 1. The Baseline Agent (Persona)
```yaml
name: "default"
description: "Standard Interactive User Agent"
mode: "self"
provider: "inherit"
model: "inherit"
workflows:
  rule_selectors:
    include: ["*"]
  skill_selectors:
    include: ["*"]
```

### 2. Derived Worker (Skill Narrowing)
```yaml
name: "worker"
extends: "default"
mode: "headless"
workflows:
  skill_selectors:
    include: ["tag:core", "name:git-tools"] # Only core skills + git
```

### 3. Reviewer Agent (Rule Overrides)
```yaml
name: "strict-reviewer"
extends: "default"
role: "You only perform code reviews."
workflows:
  rule_selectors:
    include: ["tag:gobby"]
    exclude: ["group:modify-code"]  # Prevent this agent from changing state
```
