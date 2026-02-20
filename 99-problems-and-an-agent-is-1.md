# 99 Problems and an Agent is 1

## Investigation: Why Spawned Claude Agents Sit Idle (0 Turns)

**Date:** 2026-02-19
**Session:** #196
**Task:** #8665
**Pipeline tested:** `weather-kamikaze`

---

## The Problem

The `weather-kamikaze` pipeline spawns a Claude agent to fetch a 7-day weather forecast for Little Rock, AR, waits for the result, then kills the agent. The pipeline mechanics work perfectly -- all 4 steps execute in order, template interpolation works, kill works. But the spawned agent sits idle: **0 API turns, 0 tool calls, no result**, despite the process being alive and consuming ~500MB RAM.

## Root Causes Found

### 1. Missing `--session-id` flag (spawn_executor.py)

**File:** `src/gobby/agents/spawn_executor.py`, lines 152-159

`_spawn_claude_terminal()` calls `build_cli_command()` without passing `session_id`:

```python
# BEFORE (broken)
cmd = build_cli_command(
    cli="claude",
    prompt=request.prompt,
    auto_approve=True,
    mode="terminal",
    model=request.model,
    # session_id is MISSING
)
```

The `gobby_session_id` is available (line 150) but never passed. Without `--session-id`, Claude generates its own random session ID, and the **pre-created session is never matched** by the `SessionStart` hook.

**Why this matters:** The `SessionStart` hook has a "pre-created session" path (line 130-151 of `_session.py`) that matches Claude's external_id to the pre-created Gobby session. This is how the workflow name, parent linkage, and step variables get picked up. Without `--session-id`, this path is never hit, so the workflow is never activated.

**Fix applied:**

```python
# AFTER (fixed)
cmd = build_cli_command(
    cli="claude",
    prompt=request.prompt,
    session_id=gobby_session_id,  # <-- added
    auto_approve=True,
    mode="terminal",
    model=request.model,
)
```

**Status:** Code changed but daemon not restarted, so the fix hasn't been tested yet.

### 2. Prompt delivery is broken in terminal mode (command_builder.py)

**File:** `src/gobby/agents/spawners/command_builder.py`, lines 67-79

For Claude in terminal mode, `-p` is intentionally skipped (to allow multi-turn interaction). The prompt is appended as a **bare positional argument**:

```python
elif cli in ("claude", "windsurf", "copilot"):
    if session_id:
        command.extend(["--session-id", session_id])
    if auto_approve:
        command.append("--dangerously-skip-permissions")
    # For headless mode, use -p (print mode) for single-turn execution
    # For terminal mode, don't use -p to allow multi-turn interaction
    if prompt and mode != "terminal":
        command.append("-p")

# ...
if prompt:
    command.append(prompt)  # bare positional arg
```

The resulting command is:
```
claude --dangerously-skip-permissions "## Role\nWeb researcher..."
```

Claude CLI **does** accept a positional `prompt` argument (confirmed via `claude --help`), so this should work. However, combined with the missing `--session-id`, the agent starts a fresh session with no Gobby linkage, no workflow activation, and no `on_enter` injection.

### 3. `GOBBY_PROMPT` env var is set but never consumed

**File:** `src/gobby/agents/constants.py` (definition), `src/gobby/agents/spawners/prompt_manager.py` (reader)

`prepare_terminal_spawn()` correctly sets `GOBBY_PROMPT` (or `GOBBY_PROMPT_FILE` for long prompts) in the spawned process's environment. A `read_prompt_from_env()` function exists in `prompt_manager.py` -- but **nothing calls it**. It's dead code. No hook reads the env var and injects it into Claude's context.

The intended architecture was:
1. `GOBBY_PROMPT` set in env
2. Some hook reads it on session start
3. Prompt injected into first turn

Step 2 was never implemented.

### 4. Generic agent's workflow is `enabled: false`

**File:** `src/gobby/install/shared/workflows/generic.yaml`

The generic agent definition references `default_workflow: generic`, but the generic workflow YAML has `enabled: false`. Even if the session matching worked, the workflow wouldn't activate. And even if it did, the generic workflow has **no `on_enter: inject_message`** action, so the prompt would never be injected.

### 5. tmux sessions are on an isolated socket

tmux sessions created by Gobby use `-L gobby` (a separate tmux server socket). Running `tmux ls` from a normal terminal shows nothing. Use `tmux -L gobby ls` to see agent sessions. This is by design (`src/gobby/config/tmux.py`) but caused confusion during debugging.

### 6. `wait_for_agent` MCP transport timeout

The `wait_for_agent` tool blocks server-side until the agent completes or times out. But the MCP HTTP client has its own read timeout (~25-30s) that fires first, returning a `ReadTimeout` error. This makes `wait_for_agent` unusable via MCP for any agent that takes more than ~25 seconds.

**Options:**
- Increase the MCP HTTP client timeout
- Make `wait_for_agent` non-blocking with a polling pattern
- Use `get_pipeline_status` / `get_agent_result` for polling instead

## What Was Done

### Created: `researcher` agent definition

**File:** `src/gobby/install/shared/agents/researcher.yaml`

A proper agent with:
- Role/personality for web research
- Inline `research` workflow with `on_enter: inject_message` for prompt delivery
- `WebSearch`, `WebFetch`, and Gobby MCP tools in allowed tools
- `send_to_parent` integration with variable tracking (`parent_notified`)
- Shutdown step with `kill_agent` self-termination
- `on_mcp_error` handler for `send_to_parent` failures (parent may be gone)
- Synced to DB via `sync_bundled_agents()`

### Updated: `weather-kamikaze` pipeline (v1.1)

- Changed `agent: researcher` (was using default `generic`)
- Added `agent` parameter to `spawn_agent` step
- Bumped `max_turns` from 5 to 15
- Updated prompt to mention `send_to_parent`

### Fixed: `spawn_executor.py`

- Added `session_id=gobby_session_id` to `build_cli_command()` call in `_spawn_claude_terminal()`

## What Hasn't Been Tested

The `spawn_executor.py` fix requires a **daemon restart** to take effect. The daemon (PID 57075, `python -m gobby.runner`) is running old code. The fix was applied to disk but the running process doesn't see it.

After daemon restart, the expected flow is:
1. Pipeline spawns researcher agent with `--session-id <gobby_uuid>`
2. Claude process starts, `SessionStart` hook fires
3. Hook matches pre-created session by `external_id == gobby_session_id`
4. `_handle_pre_created_session` auto-activates the `researcher:research` workflow
5. Workflow `on_enter: inject_message` fires, injecting "RESEARCH TASK: ..." into context
6. Claude also has the full prompt as a positional arg (belt AND suspenders)
7. Agent searches web, sends results to parent via `send_to_parent`
8. Workflow transitions to `shutdown` step, agent self-terminates

## Open Questions

1. **Does Claude CLI actually process the positional `prompt` arg in interactive/terminal mode?** The `claude --help` says it accepts it, but the 0-turns behavior suggests it might not work as expected when combined with `--dangerously-skip-permissions` and project hooks loading. Needs testing after the `--session-id` fix.

2. **Is the `on_enter: inject_message` content sufficient?** The current message is generic ("Execute the task described below"). The actual task prompt comes via the CLI positional arg. If Claude processes the positional arg, the inject_message is supplementary context. If Claude ignores the positional arg, we need to pass the prompt as a workflow variable and template it into the inject_message content.

3. **Startup time:** The first two test runs showed 0 turns after 120s. Claude CLI in this project loads 20+ MCP servers, project hooks, and CLAUDE.md. Startup could be 30-60+ seconds. The 120s timeout may be too aggressive for the first turn.

4. **`GOBBY_PROMPT` cleanup:** The `read_prompt_from_env()` function in `prompt_manager.py` is dead code. Either wire it into a hook or remove it. Currently it's misleading -- the env var is set but never read.

## Test Runs

| Run | Execution ID | Agent Status | Turns | Issue |
|-----|-------------|-------------|-------|-------|
| 1 | `pe-d52a79fd` | Timed out (120s) | 0 | No `--session-id`, generic agent, prompt ignored |
| 2 | `pe-ab90c36f` | Timed out (120s) | 0 | Same as above |
| 3 | `pe-39f14e87` | Failed at spawn | 0 | `Agent 'researcher' not found` (not synced to DB yet) |
| 4 | `pe-0f4889fa` | Running (killed) | 0 | Researcher agent synced, but daemon running old code (no `--session-id` fix) |

## Architecture Diagram

```
Pipeline: weather-kamikaze
  |
  v
spawn_agent(agent="researcher", prompt="...", parent_session_id=...)
  |
  v
spawn_agent_impl()
  |-- Loads researcher agent definition (DB)
  |-- Prepends role/goal/personality preamble to prompt
  |-- Resolves default_workflow -> "researcher:research"
  |
  v
_spawn_claude_terminal()
  |-- prepare_terminal_spawn() -> creates child session, sets env vars
  |     |-- GOBBY_SESSION_ID, GOBBY_PROMPT, GOBBY_WORKFLOW_NAME, etc.
  |
  |-- build_cli_command() -> constructs CLI command
  |     |-- claude --session-id <uuid> --dangerously-skip-permissions <prompt>
  |     |                    ^^^^^^^^^
  |     |                    THIS WAS MISSING (now fixed)
  |
  |-- TmuxSpawner.spawn() -> launches in tmux -L gobby
  |
  v
Claude CLI starts (PID in tmux)
  |
  v
SessionStart hook fires
  |-- Matches pre-created session by external_id == session_id  <-- REQUIRES --session-id fix
  |-- _handle_pre_created_session()
  |     |-- Auto-activates "researcher:research" workflow
  |     |-- on_enter: inject_message fires
  |
  v
Agent works (WebSearch, WebFetch, etc.)
  |
  v
send_to_parent(session_id, content="findings...")
  |-- parent_notified = true
  |-- Workflow transitions to "shutdown" step
  |
  v
kill_agent(session_id=self) -> clean exit
```

## Files Modified

| File | Change |
|------|--------|
| `src/gobby/agents/spawn_executor.py` | Added `session_id=gobby_session_id` to `build_cli_command()` call |
| `src/gobby/install/shared/agents/researcher.yaml` | **New file** -- researcher agent definition with inline research workflow |
| Pipeline `weather-kamikaze` (DB) | Updated to v1.1 -- uses `agent: researcher`, bumped `max_turns` to 15 |
