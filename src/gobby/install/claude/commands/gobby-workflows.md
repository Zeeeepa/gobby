---
description: This skill should be used when the user asks to "/gobby-workflows", "activate workflow", "workflow status". Manage step-based workflows - activate, deactivate, check status, transitions, and variables.
version: "2.0"
---

# /gobby-workflows - Workflow Management Skill

This skill manages step-based workflows via the gobby-workflows MCP server. Parse the user's input to determine which subcommand to execute.

## Session Context

**IMPORTANT**: Use the `session_id` from your SessionStart hook context for workflow calls:
```
session_id: fd59c8fc-...
```

Do NOT call `list_sessions` to look it up - you already have it.

## Subcommands

### `/gobby-workflows list` - List available workflows
Call `gobby-workflows.list_workflows` with:
- `project_path`: Optional project path
- `workflow_type`: Filter by type
- `global_only`: Only show global workflows

Returns:
- Built-in workflows (global)
- Project-specific workflows (.gobby/workflows/)
- Workflow descriptions and step counts

Example: `/gobby-workflows list` → `list_workflows()`

### `/gobby-workflows show <name>` - Show workflow details
Call `gobby-workflows.get_workflow` with:
- `name`: (required) Workflow name
- `project_path`: Optional project path

Returns full workflow definition including steps, transitions, and allowed tools.

Example: `/gobby-workflows show plan-execute` → `get_workflow(name="plan-execute")`

### `/gobby-workflows activate <name>` - Activate a workflow
Call `gobby-workflows.activate_workflow` with:
- `name`: (required) Workflow name to activate
- `session_id`: Session ID (from context)
- `initial_step`: Optional starting step (defaults to first)
- `variables`: Initial variables as object (e.g., `{"session_task": "gt-abc123"}`)
- `project_path`: Optional project path

Available workflows:
- `auto-task` - Task execution with session_task variable
- `plan-execute` - Planning then execution phases
- `test-driven` - TDD: Red → Green → Refactor
- `plan-act-reflect` - Structured development cycle
- `react` - Reason-Act continuous loop

Example: `/gobby-workflows activate plan-execute`
→ `activate_workflow(name="plan-execute")`

Example: `/gobby-workflows activate auto-task session_task=#1`
→ `activate_workflow(name="auto-task", variables={"session_task": "#1"})`

### `/gobby-workflows deactivate` - End current workflow
Call `gobby-workflows.end_workflow` with:
- `session_id`: Session ID (from context)
- `reason`: Optional reason for ending

Example: `/gobby-workflows deactivate` → `end_workflow()`

### `/gobby-workflows status` - Show current workflow status
Call `gobby-workflows.get_workflow_status` with:
- `session_id`: Session ID (from context)

Returns:
- Active workflow name (if any)
- Current step
- Available transitions
- Session variables

Example: `/gobby-workflows status` → `get_workflow_status()`

### `/gobby-workflows transition <step>` - Request step transition
Call `gobby-workflows.request_step_transition` with:
- `to_step`: (required) Target step name
- `reason`: Optional reason for transition
- `session_id`: Session ID (from context)
- `force`: Force transition even if conditions not met
- `project_path`: Optional project path

Example: `/gobby-workflows transition execute` → `request_step_transition(to_step="execute")`

### `/gobby-workflows artifact <name>` - Mark artifact complete
Call `gobby-workflows.mark_artifact_complete` with:
- Artifact name (plan, spec, etc.)

Registers an artifact as complete for workflow progression.

Example: `/gobby-workflows artifact plan` → `mark_artifact_complete(...)`

### `/gobby-workflows set <name> <value>` - Set session variable
Call `gobby-workflows.set_variable` with:
- `name`: (required) Variable name
- `value`: (required) Variable value
- `session_id`: Session ID (from context)

Session-scoped, not persisted to YAML.

Common variables:
- `session_task` - Link session to a task (enforced by stop hook)
- `auto_decompose` - Enable/disable auto-decomposition

Example: `/gobby-workflows set session_task #1`
→ `set_variable(name="session_task", value="#1")`

### `/gobby-workflows get [name]` - Get session variable(s)
Call `gobby-workflows.get_variable` with:
- `name`: Optional variable name (omit for all)
- `session_id`: Session ID (from context)

Example: `/gobby-workflows get session_task` → `get_variable(name="session_task")`
Example: `/gobby-workflows get` → `get_variable()` (returns all)

### `/gobby-workflows import <path>` - Import a workflow
Call `gobby-workflows.import_workflow` to import a workflow from a file path into the project or global directory.

Example: `/gobby-workflows import ./my-workflow.yaml`

## Response Format

After executing the appropriate MCP tool, present the results clearly:
- For list: Display workflows with name, description, and type
- For show: Full workflow definition with steps
- For activate: Confirm activation with workflow name and starting step
- For deactivate: Confirm deactivation
- For status: Show current state, step, and available actions
- For transition: Confirm transition or show why it failed
- For set/get: Show variable value(s)
- For import: Confirm import with location

## Workflow Concepts

- **Steps**: Named states with allowed tools and transitions
- **Variables**: Session-scoped key-value storage
- **Transitions**: Move between steps based on conditions
- **Tool filtering**: Each step restricts which tools are available
- **Artifacts**: Completed work products (plans, specs, etc.)

## Error Handling

If the subcommand is not recognized, show available subcommands:
- list, show, activate, deactivate, status, transition, artifact, set, get, import
