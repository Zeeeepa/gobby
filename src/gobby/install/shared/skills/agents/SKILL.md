---
name: agents
description: Manage subagent spawning - spawn, cancel, list, and check results of autonomous agents.
triggers: spawn agent, list agents
category: core
---

# /gobby agents - Agent Management Skill

This skill manages subagent spawning via the gobby-agents MCP server. Parse the user's input to determine which subcommand to execute.

## Session Context

**IMPORTANT**: Use the `session_id` from your SessionStart hook context for agent calls.

Look for `Gobby Session Ref:` or `Gobby Session ID:` in your system context:
```
Gobby Session Ref: #5
Gobby Session ID: <uuid>
```

**Note**: All `session_id` and `parent_session_id` parameters accept #N, N, UUID, or prefix formats.

## Tool Schema Reminder

**First time calling a tool this session?** Use `get_tool_schema(server_name, tool_name)` before `call_tool` to get correct parameters. Schemas are cached per session—no need to refetch.

## Shorthand: Named Agent with Task

When the first argument matches a known agent name (e.g., "meeseeks-gemini", "meeseeks-claude"), this is a **named agent spawn**. Named agents have preconfigured workflows, providers, and terminals - do NOT write a custom prompt or override their defaults.

**Pattern:** `/gobby agents <agent-name> session_task=#N`

**Action:** Call `spawn_agent` with ONLY these parameters:
- `agent`: The agent name
- `task_id`: The `session_task` value (maps to the workflow's `session_task` variable)
- `parent_session_id`: Your session ID
- `prompt`: A minimal one-liner like "Execute task #N" (required by schema but the workflow overrides it)

Do NOT set `mode`, `workflow`, `isolation`, `terminal`, `provider`, or write a detailed prompt. The agent definition controls all of these. The agent's `default_workflow` activates automatically.

Example: `/gobby agents meeseeks-claude session_task=#6878`
→ `spawn_agent(prompt="Execute task #6878", agent="meeseeks-claude", task_id="#6878", parent_session_id="#934")`

Example: `/gobby agents meeseeks-gemini session_task=#5000`
→ `spawn_agent(prompt="Execute task #5000", agent="meeseeks-gemini", task_id="#5000", parent_session_id="#934")`

## Subcommands

### `/gobby agents spawn <prompt>` - Spawn a new agent (manual)
Use this for ad-hoc spawns WITHOUT a named agent definition.

Call `spawn_agent` with:
- `prompt`: (required) Task description for the agent
- `agent`: Named agent definition (e.g., "meeseeks-gemini", "meeseeks-claude")
- `workflow`: Workflow to activate. Note: some workflows are marked `internal` and can only be spawned by the orchestrator (e.g., "worker" in meeseeks agents)
- `task_id`: Task ID to associate with the agent
- `isolation`: Isolation mode - "current" (default), "worktree", or "clone"
- `branch_name`: Custom branch name for worktree/clone
- `base_branch`: Base branch to branch from
- `mode`: Execution mode - "terminal" (default), "headless", or "embedded"
- `initial_step`: Starting step for workflow
- `terminal`: Terminal type (ghostty, tmux, iterm, etc.)
- `provider`: LLM provider (claude, gemini)
- `model`: Model override (provider-specific identifier, e.g., `claude-3-opus` for Claude, `gemini-2.0-flash` for Gemini). Must be compatible with the selected `--provider`. Omitting `--provider` uses the default provider for the current CLI.
- `timeout`: Max runtime in seconds
- `max_turns`: Max conversation turns
- `sandbox`: Enable sandboxing (true/false)
- `parent_session_id`: Parent session for tracking

**Isolation modes:**
- `current` - Work in current directory (default)
- `worktree` - Create git worktree for isolated branch
- `clone` - Create shallow clone for full isolation

Example: `/gobby agents spawn Implement the login feature`
→ `spawn_agent(prompt="Implement the login feature")`

Example: `/gobby agents spawn --isolation worktree Fix auth bug`
→ `spawn_agent(prompt="Fix auth bug", isolation="worktree")`

Example: `/gobby agents spawn --agent meeseeks-gemini Fix the tests`
→ `spawn_agent(prompt="Fix the tests", agent="meeseeks-gemini")`

### `/gobby agents result <run-id>` - Get agent result
Call `get_agent_result` with:
- `run_id`: (required) The agent run ID

Returns the result of a completed agent run.

Example: `/gobby agents result run-abc123` → `get_agent_result(run_id="run-abc123")`

### `/gobby agents stop <run-id>` - Stop a running agent
Call `stop_agent` with:
- `run_id`: (required) The agent run ID to stop

Marks the agent as cancelled in the database (does not kill the process).

Example: `/gobby agents stop run-abc123` → `stop_agent(run_id="run-abc123")`

### `/gobby agents kill <run-id|session-id>` - Kill agent process
Call `kill_agent` with:
- `run_id`: Agent run ID (parent kills child)
- `session_id`: Session ID (agent kills itself)

Kills the process and closes the terminal.

Example: `/gobby agents kill run-abc123` → `kill_agent(run_id="run-abc123")`
Example: `/gobby agents kill #5` → `kill_agent(session_id="#5")`

### `/gobby agents list` - List agent runs for a session
Call `list_agents` with:
- `session_id`: (required) Session ID to list agents for
- `status`: Optional filter (running, completed, cancelled)
- `limit`: Max results

Returns agents with run ID, status, prompt summary, and runtime.

Example: `/gobby agents list` → `list_agents(session_id="<session_id>")`
Example: `/gobby agents list running` → `list_agents(session_id="<session_id>", status="running")`

### `/gobby agents running` - List currently running agents
Call `list_running_agents` with:
- `session_id`: Optional filter by session
- `mode`: Optional filter by mode

Returns in-memory process state for running agents.

Example: `/gobby agents running` → `list_running_agents()`

### `/gobby agents can-spawn` - Check if agent can be spawned
Call `can_spawn_agent` with:
- `session_id`: (required) Session ID to check

Checks agent depth limit to prevent infinite spawning.

Example: `/gobby agents can-spawn` → `can_spawn_agent(session_id="<session_id>")`

### `/gobby agents stats` - Get running agent statistics
Call `running_agent_stats` to get statistics about running agents.

Example: `/gobby agents stats` → `running_agent_stats()`

### `/gobby agents evaluate <agent>` - Dry-run spawn evaluation
Call `evaluate_spawn` to validate a spawn configuration without executing. Checks agent definition, workflow resolution, isolation config, orchestrator enforcement, and runtime environment.

Parameters:
- `agent`: Agent name to evaluate
- `workflow`: Optional workflow override
- `task_id`: Optional task ID
- `isolation`: Optional isolation mode
- `mode`: Optional execution mode
- `parent_session_id`: Optional parent session for depth/orchestrator checks

Returns a `SpawnEvaluation` with `can_spawn` (bool), `items` (list of findings with level/code/message), and resolved effective values.

Key evaluation codes:
- `AGENT_NOT_FOUND` — agent definition missing
- `WORKFLOW_KEY_MISMATCH` — default_workflow not in workflows map
- `ORCHESTRATOR_MISMATCH` — non-default workflow without orchestrator active
- `INTERNAL_WORKFLOW_BLOCKED` — internal workflow without orchestrator
- `SPAWN_DEPTH_EXCEEDED` — max agent depth reached

Example: `/gobby agents evaluate meeseeks-gemini`
→ `evaluate_spawn(agent="meeseeks-gemini", parent_session_id="<session_id>")`

Example: `/gobby agents evaluate meeseeks-gemini --workflow worker`
→ `evaluate_spawn(agent="meeseeks-gemini", workflow="worker", parent_session_id="<session_id>")`

## Messaging Between Agents

### `/gobby agents send-to-parent <message>` - Send message to parent
Call `send_to_parent` with:
- `session_id`: (required) Your session ID
- `content`: (required) Message content

Workers use this to report completion to orchestrator.

Example: `/gobby agents send-to-parent Task completed`
→ `send_to_parent(session_id="<session_id>", content="Task completed")`

### `/gobby agents send-to-child <child-id> <message>` - Send message to child
Call `send_to_child` with:
- `session_id`: (required) Your session ID
- `child_session_id`: (required) Child's session ID
- `content`: (required) Message content

Example: `/gobby agents send-to-child #10 Please fix the tests`
→ `send_to_child(session_id="<session_id>", child_session_id="#10", content="Please fix the tests")`

### `/gobby agents poll` - Poll for messages
Call `poll_messages` with:
- `session_id`: (required) Your session ID

Returns unread messages sent to this session.

Example: `/gobby agents poll` → `poll_messages(session_id="<session_id>")`

### `/gobby agents broadcast <message>` - Broadcast to all children
Call `broadcast_to_children` with:
- `session_id`: (required) Your session ID
- `content`: (required) Message content

Sends message to all active child sessions.

Example: `/gobby agents broadcast Stop working`
→ `broadcast_to_children(session_id="<session_id>", content="Stop working")`

## Named Agent Definitions

Agent definitions in `.gobby/agents/` provide preconfigured settings:

### Meeseeks Pattern
The meeseeks agent supports orchestrator/worker workflows for any supported coding CLI. Agent definitions in `.gobby/agents/` configure which CLI, provider, and terminal to use.

Example: `spawn_agent(agent="meeseeks-gemini", task_id="#123", parent_session_id="...")`

**Workflows:**
- `box` - Interactive orchestrator (runs in your session via `mode: self`)
- `worker` - Task executor (runs in isolated clone/worktree) — **internal**, only spawnable by the box orchestrator

**Orchestrator flow (meeseeks-box):**
1. `find_work` - Call `suggest_next_task()` to get ready subtasks; falls back to `session_task` directly for leaf tasks (no children) or parents with all children done
2. `spawn_worker` - Spawn worker agent in isolated environment
3. `wait_for_worker` - Wait for task completion
4. `code_review` - Review worker's changes
5. `merge_worktree` - Merge approved changes
6. `push_changes` - Push to remote
7. `cleanup_worktree` - Delete worktree, loop back

**Leaf task support:** You can spawn a meeseeks agent with either a parent task (workers handle subtasks) or a single leaf task (assigned directly to a worker).

**Worker flow (meeseeks worker):**
1. `claim_task` - Claim assigned task
2. `work` - Implement with full tool access
3. `report_to_parent` - Send completion message
4. `shutdown` - Call `kill_agent` to terminate

## Response Format

After executing the appropriate MCP tool, present the results clearly:
- For spawn: Show run ID, mode, and initial status
- For result: Show agent output and completion status
- For stop/kill: Confirm agent stopped
- For list: Table with run ID, status, prompt, duration
- For running: Show active processes
- For can-spawn: Show yes/no with depth info
- For stats: Show running agent statistics
- For messaging: Confirm sent/received

## Agent Safety

- Agent depth is limited (default 3) to prevent infinite spawning
- Each workflow step restricts available tools
- Parent session context is injected automatically
- Workers cannot push - orchestrator handles merge/push
- Internal workflows (e.g., `worker`) cannot be spawned directly — the orchestrator must be active first
- Use `can_spawn_agent` to check before spawning

## Error Handling

If the subcommand is not recognized, show available subcommands:
- spawn, result, stop, kill, list, running, can-spawn, stats, evaluate
- send-to-parent, send-to-child, poll, broadcast
