# Unified Workflow Architecture

## Context

Gobby currently has three separate execution models that share infrastructure but can't compose:

| Model | Execution | Activation | Composability |
|-------|-----------|------------|---------------|
| **Lifecycle workflow** | Event-driven triggers | Always on | None |
| **Step workflow** | State machine | Manual `activate_workflow` | None |
| **Pipeline** | Sequential/deterministic | Manual `run_pipeline` | `invoke_pipeline` only |

This creates friction:
- Lifecycle and step workflows use different code paths in `engine.py` despite sharing variables, conditions, and actions
- Step workflows are artificially limited to one-per-session
- Pipelines can't invoke workflows; workflows can't invoke pipelines
- The "type" distinction (lifecycle vs step) confuses users — they're the same concept with different capabilities enabled

**Goal:** Unify lifecycle + step into a single workflow type with optional capabilities, and enable bidirectional composability between workflows and pipelines.

---

## Part 1: Unified Workflow Type

### Design

Every workflow is a single type. No `type` field. Capabilities are determined by what's declared:

```yaml
name: my-workflow
priority: 20           # Execution ordering (lower = first)
enabled: true          # true = always-on, false = activate via set_variable
sources: [claude]      # Optional CLI filter

variables: { ... }          # Workflow-scoped variables
session_variables: { ... }  # Session-scoped shared variables
observers: [ ... ]          # Event watchers that set variables

# Reactive capabilities (event-driven)
triggers:
  on_before_tool: [ ... ]
  on_stop: [ ... ]

# Proactive capabilities (state machine)
steps:
  - name: work
    on_enter: [ ... ]
    transitions: [ ... ]

# Tool enforcement
tool_rules: [ ... ]

# Step extras (only meaningful when steps exist)
exit_condition: "..."
on_premature_stop: { ... }
```

### Key rules

1. **`enabled: true`** (default) = workflow evaluates on every hook event.
2. **`enabled: false`** = workflow is dormant. Activate by calling `set_variable(name="enabled", value=true, workflow="my-workflow")`.
3. **Triggers are always evaluated** when enabled, regardless of whether steps exist or which step is current.
4. **Steps are optional.** A triggers-only workflow is valid. A steps-only workflow is valid. Both together is the new capability.
5. **Multiple workflows active simultaneously.** No one-step-workflow limit. Priority ordering resolves conflicts. First block wins.
6. **Steps can reference triggers.** Trigger conditions can include `variables._current_step == "red"` to scope behavior to a step.

### Concrete examples

**session-lifecycle (triggers only, always on):**
```yaml
name: session-lifecycle
priority: 10
enabled: true
session_variables:
  unlocked_tools: []
  task_claimed: false
  servers_listed: false
  plan_mode: false
observers:
  - name: task_tracking
    behavior: task_claim_tracking
triggers:
  on_session_start:
    - action: inject_context
      filter: context_aware
  on_before_tool:
    - when: "not session.task_claimed"
      action: block_tools
      rules: [{ tool: Edit, decision: block }]
```

**auto-task (triggers only, activatable):**
```yaml
name: auto-task
priority: 25
enabled: false
variables:
  assigned_task_id: null
  context_injected: false
triggers:
  on_before_agent:
    - when: "not variables.context_injected"
      action: inject_message
      content: "Autonomous mode. Task: {{ variables.assigned_task_id }}"
    - when: "not variables.context_injected"
      action: set_variable
      name: context_injected
      value: true
  on_stop:
    - when: "not task_tree_complete(variables.assigned_task_id)"
      action: block
      message: "Task incomplete. Keep working."
```

**developer (steps + triggers, activatable):**
```yaml
name: developer
priority: 20
enabled: false
variables:
  assigned_task_id: null
  tests_written: false
  tests_passing: false

steps:
  - name: red
    on_enter:
      - action: inject_message
        content: "Write failing tests first."
    allowed_tools: [Read, Grep, Glob, Write, Edit]
    rules:
      - name: test_files_only
        when: "not is_test_file(tool_input.file_path)"
        tool: [Write, Edit]
        decision: block
    transitions:
      - to: green
        when: "variables.tests_written"

  - name: green
    on_enter:
      - action: inject_message
        content: "Make the tests pass."
    transitions:
      - to: blue
        when: "variables.tests_passing"

  # ... more steps

triggers:
  on_stop:
    - when: "not variables.exit_condition_met"
      action: block
      message: "Finish your TDD cycle."

exit_condition: "variables.task_complete"
```

### Activation API

```python
# Activate — convenience tool that sets enabled=true + merges variables
activate_workflow(name="developer", session_id="#123", variables={"assigned_task_id": "#456"})

# Deactivate — sets enabled=false + clears step state + clears workflow variables
end_workflow(workflow="developer", session_id="#123")

# Direct variable control
set_variable(name="enabled", value=True, workflow="developer", session_id="#123")
```

### Engine: single evaluation loop

```
# Build index once on workflow load/change (not per-event)
workflows_by_trigger: dict[str, list[Workflow]]  # event_type → sorted workflows

# Per-event evaluation
for each workflow in workflows_by_trigger[event_type]:
    if not workflow.enabled: skip
    evaluate triggers (event-driven) → accumulate context/messages
    if workflow.has_steps:
        evaluate step state (tool restrictions, transitions, on_enter/on_exit)
    if decision == block: stop evaluation, return block
    # Otherwise continue to next workflow (accumulate context)
```

**Accumulate context, first block stops.** All enabled workflows get a chance to inject context (messages, variables). But the first workflow that returns a `block` decision halts evaluation — no further workflows run for that event. This means a priority-10 "security" workflow can block before a priority-20 "logger" workflow runs, but a priority-10 "context injector" won't prevent a priority-20 "enforcer" from blocking.

**Performance:** Workflows are indexed by trigger type at load time. On a `before_tool` event, only workflows with `on_before_tool` triggers (or steps with tool rules) are evaluated — not all enabled workflows. This prevents latency on high-frequency events.

Triggers and steps are layers, not alternatives. Triggers fire on events. Steps provide structure and tool restrictions. A workflow can use either or both.

### State model

- One state entry per workflow, keyed by workflow name
- `step` field is null when workflow has no steps, or the current step name
- `enabled` field on the state
- Workflow variables stored per-workflow

---

## Part 2: Variable Scoping

### Two namespaces

**Workflow variables** — isolated per-workflow:
```yaml
variables:
  tests_written: false      # only this workflow reads/writes
  tests_passing: false
```

**Session variables** — shared namespace visible to all workflows:
```yaml
session_variables:
  unlocked_tools: []        # any workflow can read/write
  task_claimed: false
```

### Access

| Operation | Syntax | Scope |
|-----------|--------|-------|
| Read own variable | `variables.tests_written` | Workflow |
| Write own variable | `set_variable(name, value, workflow)` | Workflow |
| Read session variable | `session.task_claimed` | Session (shared) |
| Write session variable | `set_session_variable(name, value)` | Session (shared) |
| Read another workflow's variable | Not allowed | — |

### MCP tools

```python
# Workflow-scoped
set_variable(name="tests_written", value=True, workflow="developer", session_id="#123")
get_variable(name="tests_written", workflow="developer", session_id="#123")

# Session-scoped
set_session_variable(name="task_claimed", value=True, session_id="#123")
get_session_variable(name="task_claimed", session_id="#123")
```

### Lifecycle & isolation

- `session_variables` declared in any workflow YAML. First workflow to declare a session variable sets its default.
- Session variables persist for the entire session lifetime, regardless of which workflows are enabled/disabled.
- Workflow variables are created when enabled, cleared when disabled.
- **Storage isolation:** Workflow variables and session variables are stored in separate dicts in the state model — not merged into a single namespace. The `variables.*` and `session.*` prefixes in condition expressions resolve to different backing stores. Writing to `variables.foo` can never leak into `session.foo`.

### Condition context

Both namespaces available in `when` expressions and templates:
```yaml
triggers:
  on_before_tool:
    - when: "not session.task_claimed"
      action: block_tools

steps:
  - name: red
    transitions:
      - to: green
        when: "variables.tests_written"
```

---

## Part 3: Pipeline/Workflow Composability

### Pipeline inside workflow

New action type `run_pipeline` available in triggers and step on_enter/on_exit:

```yaml
steps:
  - name: validate
    on_enter:
      - action: run_pipeline
        pipeline: ci-checks
        inputs:
          task_id: "{{ variables.assigned_task_id }}"
          commit_sha: "{{ variables.last_commit }}"
        result_variable: validation
    transitions:
      - to: commit
        when: "variables.validation.all_passed"
      - to: fix
        when: "not variables.validation.all_passed"
```

**Semantics:**
- Pipeline executes synchronously within the workflow action
- Pipeline outputs stored in the specified workflow variable
- If pipeline hits an approval gate, the workflow action pauses (hook returns, agent continues, pipeline resumes when approved)
- Pipeline failure sets `result_variable` to `{error: "...", failed: true}`

### Workflow inside pipeline (orchestrator pattern)

New pipeline step type `spawn_session`:

```yaml
steps:
  - id: implement
    spawn_session:
      agent: claude
      workflow: developer
      variables:
        assigned_task_id: "${{ steps.find_task.output.task_id }}"
      wait_for: exit_condition
      timeout: 3600
    # output = workflow's final variables

  - id: review
    prompt: "Review changes from ${{ steps.implement.output.last_commit }}"
```

**Semantics:**
- Pipeline executor spawns a new terminal/session via existing spawner infrastructure
- Activates the specified workflow on that session
- If `wait_for: exit_condition`, pipeline blocks until workflow signals completion
- Workflow's final variables become the step's output
- Timeout prevents infinite waits

### Workflow inside pipeline (inline pattern)

New pipeline step type `activate_workflow`:

```yaml
steps:
  - id: setup
    activate_workflow:
      name: auto-task
      variables:
        assigned_task_id: "${{ steps.find_task.output.task_id }}"
    # Non-blocking — pipeline continues, workflow runs alongside

  - id: wait_for_completion
    activate_workflow:
      name: auto-task
      wait_for: exit_condition
      timeout: 1800
    # Blocking — pipeline waits for workflow to finish
```

**Semantics:**
- Activates workflow on the pipeline's session (sets `enabled=true` + variables)
- Non-blocking by default, optional `wait_for` to block
- Useful for "configure the agent's behavior then let it work"

### Pipeline inside pipeline (existing)

Already works via `invoke_pipeline`. No changes needed.

---

## Part 4: Directory Structure

```
.gobby/workflows/
  session-lifecycle.yaml    # All workflows in one flat directory
  developer.yaml
  auto-task.yaml
  ci-pipeline.yaml          # Pipelines coexist (type: pipeline)
```

No `lifecycle/` subdirectory. No `type` field on workflows. Pipelines keep `type: pipeline` — they're a fundamentally different execution model (deterministic/sequential vs reactive/event-driven). Composability bridges them without merging them.

---

## Summary

| Concept | Design |
|---------|--------|
| **Workflow type** | One unified type. `triggers:` for reactive, `steps:` for state machine, both optional. |
| **Activation** | `enabled: true/false`. `activate_workflow` / `end_workflow` as convenience sugar. |
| **Concurrency** | Multiple workflows active simultaneously. Priority ordering. First block wins. |
| **Workflow variables** | Isolated per-workflow via `variables:`. Accessed as `variables.*`. |
| **Session variables** | Shared namespace via `session_variables:`. Accessed as `session.*`. |
| **Pipeline → Workflow** | `run_pipeline` action in triggers/steps. Synchronous execution. |
| **Workflow → Pipeline (orchestrator)** | `spawn_session` pipeline step. Spawns agent with workflow, waits for completion. |
| **Workflow → Pipeline (inline)** | `activate_workflow` pipeline step. Activates on current session. |
| **Pipeline type** | Unchanged. `type: pipeline` remains a distinct execution model. |
