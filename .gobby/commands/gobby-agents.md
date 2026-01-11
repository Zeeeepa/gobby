---
description: This skill should be used when the user asks to "/agents", "spawn agent", "start agent", "list agents". Manage subagent spawning - start, stop, list, and check status of autonomous agents.
---

# /agents - Agent Management Skill

This skill manages subagent spawning via the gobby-agents MCP server. Parse the user's input to determine which subcommand to execute.

## Subcommands

### `/agents start <prompt>` - Start a new agent
Call `gobby-agents.start_agent` with:
- `prompt`: Task description for the agent
- `mode`: Execution mode (terminal, headless, embedded)
- `workflow`: Optional workflow to activate (plan-execute, test-driven, etc.)
- `context_sources`: Optional context injection sources

Modes:
- `terminal` - Opens in new terminal window (default)
- `headless` - Runs in background, no UI
- `embedded` - Runs in current process

Example: `/agents start Implement the login feature`
→ `start_agent(prompt="Implement the login feature", mode="terminal")`

Example: `/agents start --headless Fix all type errors`
→ `start_agent(prompt="Fix all type errors", mode="headless")`

### `/agents stop <agent-id>` - Stop a running agent
Call `gobby-agents.stop_agent` with:
- `agent_id`: The agent ID to stop

Example: `/agents stop agent-abc123` → `stop_agent(agent_id="agent-abc123")`

### `/agents list` - List all agents
Call `gobby-agents.list_agents` with:
- `status`: Optional filter (running, stopped, completed)

Returns agents with ID, status, prompt summary, and runtime.

Example: `/agents list` → `list_agents()`
Example: `/agents list running` → `list_agents(status="running")`

### `/agents status <agent-id>` - Check agent status
Call `gobby-agents.get_agent_status` with:
- `agent_id`: The agent ID to check

Returns detailed status including progress, current task, and output.

Example: `/agents status agent-abc123` → `get_agent_status(agent_id="agent-abc123")`

## Response Format

After executing the appropriate MCP tool, present the results clearly:
- For start: Show agent ID, mode, and initial status
- For stop: Confirm agent stopped
- For list: Table with agent ID, status, prompt, duration
- For status: Detailed progress report

## Agent Safety

- Agent depth is limited (default 3) to prevent infinite spawning
- Each workflow step restricts available tools
- Parent session context is injected automatically

## Error Handling

If the subcommand is not recognized, show available subcommands:
- start, stop, list, status
