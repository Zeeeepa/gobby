# Agent Definition System Design

## Problem

Validation delegation creates infinite loops because spawned agents inherit the same lifecycle variables (`validation_model: haiku`), causing them to also get blocked and spawn more agents.

## Root Cause

`start_agent` doesn't allow specifying lifecycle variables. The child agent gets the same hooks with the same behavior.

## Solution: Named Agent Definitions

Agents are workflow configurations with names. An agent definition bundles:
- Model to use
- Lifecycle workflow and/or variables
- Step workflow (optional)
- Default variables

### Agent Definition Format

```yaml
# .gobby/agents/agents/validation-runner.yaml
name: validation-runner
description: Runs validation commands (pytest, ruff, mypy) and reports results

model: haiku
mode: headless

# Lifecycle variables - override parent's lifecycle settings
lifecycle_variables:
  validation_model: null  # Disable delegation for this agent
  require_task_before_edit: false  # No task needed

# Optional step workflow
workflow: null  # Just execute prompt, no steps

# Execution limits
timeout: 1800
max_turns: 10
```

### Spawning Named Agents

```python
# Current (doesn't work - inherits parent lifecycle)
start_agent(prompt="run pytest", mode="headless", model="haiku")

# New - load agent definition
start_agent(agent="validation-runner", prompt="run pytest tests/")
```

### Where Definitions Live

Priority order (later overrides earlier):
1. Built-in: `src/gobby/install/shared/agents/`
2. User-level: `~/.gobby/agents/`
3. Project-level: `.gobby/agents/`

### How It Works

1. `start_agent(agent="validation-runner", prompt="...")` is called
2. Agent definition loaded from YAML
3. Child session created with `lifecycle_variables` merged in
4. Child runs with its own lifecycle behavior (no validation blocking)
5. Reports result back to parent

## Files to Create/Modify

### New Files
- `src/gobby/agents/definitions.py` - AgentDefinition dataclass, loader
- `src/gobby/install/shared/agents/validation-runner.yaml` - Built-in validation agent

### Modify
- `src/gobby/mcp_proxy/tools/agents.py` - Add `agent` param to `start_agent`
- `src/gobby/agents/runner.py` - Accept lifecycle_variables, merge into child session
- `src/gobby/workflows/state_manager.py` - Apply lifecycle_variables when creating state

### Remove/Update
- `require_validation_delegation` from `task_enforcement_actions.py` - Move to YAML hook config
- `session-lifecycle.yaml` - Hook spawns `validation-runner` agent directly

## Validation Hook (YAML-based)

After this, the session-lifecycle hook becomes:

```yaml
on_before_tool:
  - when: tool_name == "Bash" and ("pytest" in command or "ruff" in command or "mypy" in command)
    spawn_agent:
      agent: validation-runner
      prompt: "Run and report: {{ tool_input.command }}"
```

No Python action needed - just YAML configuration.

## Open Questions

1. Should `lifecycle_variables` completely replace parent's, or merge?
2. How to handle the hook response - does spawning block the original tool call?
3. Should there be a `lifecycle_workflow` field to use a completely different lifecycle?
4. Can the workflow engine execute `spawn_agent` directly, or does it need a new action type?

## Verification

1. Create `validation-runner.yaml` agent definition
2. Update `start_agent` to accept `agent` param and load definition
3. Spawn validation-runner, verify it can run pytest without being blocked
4. Update session-lifecycle hook to use spawn_agent
5. Test end-to-end: parent runs pytest → spawns validation-runner → gets result
