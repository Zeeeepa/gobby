---
name: workflows
description: This skill should be used when the user asks to "/gobby workflows", "activate workflow", "workflow status", "list rules", "enable/disable rule". Manage rules and step-based workflows - list rules, toggle rules, activate workflows, check status, and list available workflows.
category: core
metadata:
  gobby:
    audience: interactive
    depth: 0
---

# /gobby workflows - Rules and Workflow Management Skill

This skill manages declarative rules and step-based workflows via the gobby-workflows MCP server. Rules are always-on enforcement (block, set_variable, inject_context, mcp_call). Workflows are on-demand state machines activated for structured processes. Parse the user's input to determine which subcommand to execute.

## Session Context

**IMPORTANT**: Use the `session_id` from your SessionStart hook context (injected at session start) for all workflow calls.

Look for `Gobby Session Ref:` or `Gobby Session ID:` in your system context:
```
Gobby Session Ref: #5
Gobby Session ID: <uuid>
```

**Note**: All `session_id` parameters accept #N, N, UUID, or prefix formats.

Do NOT call `list_sessions` to look it up - you already have it.

## Tool Schema Reminder

**First time calling a tool this session?** Use `get_tool_schema(server_name, tool_name)` before `call_tool` to get correct parameters. Schemas are cached per session—no need to refetch.

## Subcommands

### `/gobby workflows rules` - List active rules
Call `list_rules` to see all rules with optional filters:
- `event`: Filter by event type (before_tool, after_tool, before_agent, session_start, session_end, stop, pre_compact)
- `group`: Filter by rule group (e.g., "worker-safety", "stop-gates")

Example: `/gobby workflows rules` → `list_rules()`
Example: `/gobby workflows rules --group worker-safety` → `list_rules(group="worker-safety")`

### `/gobby workflows rule <name>` - Show rule details
Call `get_rule_detail` with:
- `name`: (required) Rule name

Returns the full rule definition including event, when condition, and effect.

Example: `/gobby workflows rule no-push` → `get_rule_detail(name="no-push")`

### `/gobby workflows enable <rule-name>` - Enable a rule
Call `toggle_rule` with:
- `name`: (required) Rule name
- `enabled`: true

Example: `/gobby workflows enable require-task` → `toggle_rule(name="require-task", enabled=true)`

### `/gobby workflows disable <rule-name>` - Disable a rule
Call `toggle_rule` with:
- `name`: (required) Rule name
- `enabled`: false

Example: `/gobby workflows disable require-task` → `toggle_rule(name="require-task", enabled=false)`

### `/gobby workflows activate <workflow-name>` - Activate a workflow
Call `activate_workflow` with:
- `session_id`: **Required** - from your SessionStart context
- `name`: The workflow name to activate
- `variables`: Optional initial variables (e.g., `session_task` for auto-task)
- `initial_step`: Optional starting step (defaults to first step)

Available workflows:
- `auto-task` - Task execution with session_task variable
- `plan-execute` - Planning then execution phases
- `test-driven` - TDD: Red → Green → Refactor
- `plan-act-reflect` - Structured development cycle
- `react` - Reason-Act continuous loop

Example: `/gobby workflows activate plan-execute`
→ `activate_workflow(session_id="<from context>", name="plan-execute")`

Example: `/gobby workflows activate auto-task session_task=gt-abc123`
→ `activate_workflow(session_id="<from context>", name="auto-task", variables={"session_task": "gt-abc123"})`

### `/gobby workflows deactivate` - Deactivate current workflow
Call `end_workflow` with:
- `session_id`: **Required** - from your SessionStart context

Example: `/gobby workflows deactivate`
→ `end_workflow(session_id="<from context>")`

### `/gobby workflows status` - Show current workflow status
Call `get_workflow_status` with:
- `session_id`: **Required** - from your SessionStart context

Returns:
- Active workflow name (if any)
- Current step
- Available transitions
- Session variables

Example: `/gobby workflows status`
→ `get_workflow_status(session_id="<from context>")`

### `/gobby workflows list` - List available workflows
Call `list_workflows` to see all available workflows:
- Built-in workflows (global)
- Project-specific workflows (.gobby/workflows/)
- Workflow descriptions and step counts

Example: `/gobby workflows list` → `list_workflows()`

### `/gobby workflows evaluate <workflow-name>` - Dry-run workflow validation
Call `evaluate_workflow` to validate a workflow definition without executing. Checks structure, step reachability, transitions, and tool references.

Parameters:
- `name`: (required) Workflow name to evaluate
- `project_path`: Optional project path for lookup

Returns a `WorkflowEvaluation` with `valid` (bool), `items` (list of findings), and `step_trace` (reachability analysis).

Example: `/gobby workflows evaluate auto-task`
→ `evaluate_workflow(name="auto-task")`

## Response Format

After executing the appropriate MCP tool, present the results clearly:
- For activate: Confirm activation with workflow name and starting step
- For deactivate: Confirm deactivation
- For status: Show current state, step, and available actions
- For list: Display workflows with name, description, and type (step/stepped)

## Concepts

### Rules (always-on)
- **Events**: 7 event types trigger rule evaluation (before_tool, after_tool, before_agent, session_start, session_end, stop, pre_compact)
- **Effects**: 4 primitives — block (prevent action), set_variable (update state), inject_context (add system text), mcp_call (trigger MCP tool)
- **Conditions**: `when` expressions evaluated by SafeExpressionEvaluator
- **Groups**: 11 bundled groups (worker-safety, stop-gates, task-enforcement, etc.)

### Workflows (on-demand)
- **Steps**: Named states with allowed tools and transitions
- **Variables**: Session-scoped key-value storage (e.g., `session_task`)
- **Transitions**: Move between steps based on conditions
- **Tool filtering**: Each step restricts which tools are available

## Step Transitions

Transitions between steps can be automatic or manual:

### Automatic Transitions
Most workflows use condition-based transitions that fire automatically:
- `step_action_count >= N` - after N tool calls in the step
- `task_tree_complete(...)` - when tasks are done
- Variable comparisons - when workflow state changes

**You don't need to manually transition** - just perform the required actions and the workflow engine handles the rest.

### Manual Transitions
If you need to force a transition, use `request_step_transition`:
```python
call_tool("gobby-workflows", "request_step_transition", {
    "session_id": "<from context>",
    "to_step": "work",
    "reason": "Research complete, ready to implement"
})
```

Only use manual transitions when automatic conditions aren't met and you have justification.

**Common mistake**: Guessing tool names like `transition_step` or `step_transition`. The actual tool is `request_step_transition`.

## Error Handling

If the subcommand is not recognized, show available subcommands:
- rules, rule, enable, disable (rule management)
- activate, deactivate, status, list, evaluate (workflow management)
