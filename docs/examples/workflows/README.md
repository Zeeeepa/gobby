# Agent Workflow Examples

This directory contains example workflow YAML files demonstrating agent-related patterns.

## Workflows

### agent-delegation.yaml
A workflow for delegating subtasks to subagents while the parent coordinates and reviews results.

**Use case**: Complex tasks that can be broken into independent subtasks.

**Phases**:
1. **plan** - Research and identify subtasks (read-only)
2. **delegate** - Spawn agents for each subtask
3. **review** - Review results and integrate
4. **complete** - Final state

### parallel-worktree-agents.yaml
A workflow for spawning multiple agents in isolated git worktrees for parallel development.

**Use case**: Multiple features that can be developed simultaneously without conflicts.

**Phases**:
1. **analyze** - Identify parallelizable features
2. **spawn_worktrees** - Create worktrees and spawn agents
3. **monitor** - Track agent progress
4. **integrate** - Merge branches and cleanup
5. **complete** - Final state

### agent-tdd.yaml
A test-driven development workflow for agents implementing features.

**Use case**: When spawning an agent to implement a specific feature with TDD.

**Phases**:
1. **understand** - Research requirements (read-only)
2. **write_tests** - Write failing tests first
3. **implement** - Minimal implementation to pass tests
4. **refactor** - Improve code quality
5. **complete** - Final state

## Installation

Copy workflow files to one of:
- `~/.gobby/workflows/` - Available globally
- `.gobby/workflows/` - Available in specific project

## Usage

### Activate workflow for a session

```bash
# Using CLI
gobby workflows set agent-tdd

# Or check status
gobby workflows status
```

### Spawn agent with workflow

```python
# Spawn an agent that runs this workflow
call_tool(server_name="gobby-agents", tool_name="start_agent", arguments={
    "prompt": "Implement user authentication with proper tests",
    "workflow": "agent-tdd",
    "parent_session_id": current_session_id,
    "mode": "terminal",
    "terminal": "ghostty",
})
```

### Workflow variables

Workflows can have variables that customize behavior:

```yaml
variables:
  test_command: "uv run pytest -v"
  max_parallel_agents: 3
  base_branch: main
```

Access variables in templates: `{{ variable_name }}`

## Creating Custom Workflows

See the [Workflow Engine documentation](../../guides/workflows.md) for:
- Complete YAML schema
- Available actions
- Transition conditions
- Exit conditions

Key concepts:
- **Steps** define phases with tool restrictions
- **Transitions** move between steps based on conditions
- **Actions** execute on step enter/exit (inject context, capture artifacts)
- **Variables** customize workflow behavior
