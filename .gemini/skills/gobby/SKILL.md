---
name: gobby
description: "Unified router for Gobby skills and MCP servers. Usage: /gobby <skill> [args] or /gobby mcp <server> [args]"
version: "1.0.0"
category: core
---

# /gobby - Unified Skill & MCP Router

Route to Gobby skills or MCP servers via a single entry point.

## Usage

```text
/gobby                     # Show help
/gobby help                # Show help
/gobby <skill> [args]      # Load and execute a skill
/gobby mcp <server> [args] # Route to an MCP server
```

## Routing Logic

Parse the user's input after `/gobby`:

### 1. No args or "help" → Show Help

Display available skills and usage:

```text
/gobby - Unified Gobby Router

Usage:
  /gobby <skill> [args]      Execute a Gobby skill
  /gobby mcp <server> [args] Route to MCP server

Quick-create tasks:
  /gobby bug <title>         Create bug task
  /gobby feat <title>        Create feature task
  /gobby chore <title>       Create chore task
  /gobby epic <title>        Create epic
  /gobby nit <title>         Create nitpick task
  /gobby ref <title>         Create refactor task

Core skills:
  /gobby tasks [cmd]         Task management
  /gobby plan                Specification planning
  /gobby expand <task>       Expand task into subtasks
  /gobby sessions            Session management
  /gobby memory [cmd]        Persistent memory
  /gobby workflows           Workflow management
  /gobby agents              Agent spawning
  /gobby worktrees           Git worktree management
  /gobby clones              Git clone management
  /gobby merge               AI merge conflict resolution
  /gobby metrics             Tool usage metrics
  /gobby diagnostic          Run systems check

MCP routing:
  /gobby mcp <server> <query>  Route to MCP server
  /gobby mcp context7 react    Query context7 for React docs

Aliases: /g is shorthand for /gobby
```

### 2. First arg is "mcp" → Route to MCP Server

When user provides `/gobby mcp <server> [args]`:

1. Extract server name (second arg)
2. Extract remaining args as query
3. Use `list_mcp_servers()` to verify server exists
4. Use `list_tools(server)` to find appropriate tool
5. Call the tool with the query

Example: `/gobby mcp context7 react hooks`
```python
# 1. Verify server exists
list_mcp_servers()
# 2. Get available tools on that server
list_tools(server="context7")
# 3. Call appropriate tool (e.g., resolve-library-id, query-docs)
call_tool(server_name="context7", tool_name="resolve-library-id", arguments={"libraryName": "react", "query": "hooks"})
```

### 3. First arg matches a skill → Load Skill

When user provides `/gobby <skill> [args]`:

1. Call `get_skill(name="<skill>")` to load the skill
2. If skill not found, suggest similar skills or show help
3. If skill found, follow the skill's instructions with remaining args

Example: `/gobby tasks list`
```python
# Load the skill
get_skill(name="tasks")
# Follow skill instructions with args: "list"
```

**Skill name resolution order:**
1. Exact match: `get_skill(name="tasks")` — matches skill with `name: tasks`
2. Prefixed fallback: `get_skill(name="gobby-tasks")` — tried if exact match fails
3. This allows both `/gobby tasks` and `/gobby gobby-tasks` to resolve to the same skill

## Quick-Create Skills

These skills create tasks directly:

| Command | Skill | Task Type |
|---------|-------|-----------|
| `/gobby bug <title>` | bug | bug (priority 1) |
| `/gobby feat <title>` | feat | feature |
| `/gobby chore <title>` | chore | task |
| `/gobby epic <title>` | epic | epic |
| `/gobby nit <title>` | nit | task |
| `/gobby ref <title>` | ref | task |
| `/gobby eval` | eval | - (guidance skill) |

## Core Skills (gobby-* prefix optional)

| Command | Skill | Description |
|---------|-------|-------------|
| `/gobby tasks` | gobby-tasks | Task management |
| `/gobby plan` | gobby-plan | Specification planning |
| `/gobby expand` | gobby-expand | Expand tasks |
| `/gobby sessions` | gobby-sessions | Session management |
| `/gobby memory` | gobby-memory | Persistent memory |
| `/gobby workflows` | gobby-workflows | Workflow management |
| `/gobby agents` | gobby-agents | Agent spawning |
| `/gobby worktrees` | gobby-worktrees | Git worktrees |
| `/gobby clones` | gobby-clones | Git clones |
| `/gobby merge` | gobby-merge | AI merge |
| `/gobby metrics` | gobby-metrics | Tool metrics |
| `/gobby diagnostic` | gobby-diagnostic | Systems check |
| `/gobby mcp-guide` | gobby-mcp | MCP tool discovery |

## Error Handling

### Skill Not Found

If `get_skill` fails or returns no content:

```text
Skill '<name>' not found.

Did you mean one of these?
  - tasks (task management)
  - plan (specification planning)
  - memory (persistent memory)

Run /gobby help to see all available skills.
```

### MCP Server Not Found

If server doesn't exist:

```text
MCP server '<name>' not found.

Available servers:
  - context7 (documentation lookup)
  - gobby-tasks (task management)
  - gobby-sessions (session management)
  ...

Run list_mcp_servers() for full list.
```

## Implementation Notes

1. **Skill loading**: Always use `get_skill(name=...)` - the name parameter works for both skill names and IDs.

2. **Fallback resolution**: If exact name fails, try with `gobby-` prefix for core skills.

3. **Args passthrough**: Pass remaining args to the loaded skill as context.

4. **Session context**: Skills may need `session_id` — look for `Gobby Session ID:` in your system context and pass it to MCP tool calls that require it.
