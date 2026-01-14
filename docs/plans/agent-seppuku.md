# Agent Termination: kill_agent + Seppuku

This plan covers two approaches to terminating spawned agents:

1. **External Kill** (SIGTERM-based) - Immediate implementation
2. **Agent Seppuku** (MCP-based self-termination) - Future enhancement

---

# Part 1: External Kill Strategy

## Overview

Add process termination for spawned agents. Currently `cancel_agent` only updates DB status - processes continue running. This adds real process killing with mode-aware strategies.

## Problem Analysis

| Mode | PID Captured | Can Kill? | Strategy |
|------|-------------|-----------|----------|
| **headless** | Actual CLI PID | Yes | Direct SIGTERM |
| **terminal** (macOS) | `open` PID (useless!) | No | Use session DB or pgrep |
| **terminal** (Linux) | Actual terminal PID | Partial | SIGTERM terminal OR pgrep inner |
| **in_process** | None (asyncio.Task) | Yes | Task.cancel() |

## PID Capture by Provider

| Provider | Hook System | PID Source |
|----------|-------------|------------|
| **Claude** | Shell hooks (`hook_dispatcher.py`) | `session.terminal_context["parent_pid"]` |
| **Codex** | JSON-RPC events (internal) | Use pgrep fallback |
| **Gemini** | None yet (coming soon) | Use pgrep fallback |

**Strategy by provider:**

1. **Claude**: Session hook captures `os.getppid()` → stored in DB → use directly
2. **Codex/Gemini**: Fall back to `pgrep -f "Your Gobby session_id is: {id}"`

## Platform Considerations

| Platform | Signal | Process Finder | Notes |
|----------|--------|----------------|-------|
| **macOS** | `os.kill(SIGTERM)` | `pgrep -f` | `open` exits immediately |
| **Linux** | `os.kill(SIGTERM)` | `pgrep -f` | Terminal PID may be usable |
| **Windows** | `subprocess.terminate()` | `tasklist /FI` | Uses `TerminateProcess` |

**Windows implementation:**

```python
if platform.system() == "Windows":
    # No os.kill with signals on Windows
    import subprocess
    subprocess.run(["taskkill", "/F", "/PID", str(target_pid)], check=True)
else:
    os.kill(target_pid, signal.SIGTERM)
```

**Windows pgrep equivalent:**

```python
# Find process by command line pattern
result = subprocess.run(
    ["wmic", "process", "where",
     f"CommandLine like '%Your Gobby session_id is: {session_id}%'",
     "get", "ProcessId"],
    capture_output=True, text=True
)
```

## Implementation

### Files to Modify

| File | Changes |
|------|---------|
| `src/gobby/agents/registry.py` | Add `kill()` method with mode-aware strategies |
| `src/gobby/mcp_proxy/tools/agents.py` | Add `kill_agent` MCP tool |
| `src/gobby/cli/agents.py` | Add `gobby agents kill` CLI command |

### 1. Registry Method (`registry.py`)

Add to `RunningAgentRegistry` class:

```python
def kill(
    self,
    run_id: str,
    signal_name: str = "TERM",
    timeout: float = 5.0,
) -> dict[str, Any]:
    """
    Kill a running agent process.

    Strategy varies by mode:
    - headless: Direct signal to tracked PID
    - terminal: pgrep by session_id to find inner CLI process
    - in_process: Cancel asyncio task

    Args:
        run_id: Agent run ID
        signal_name: Signal without SIG prefix (TERM, KILL, INT)
        timeout: Seconds before escalating TERM → KILL

    Returns:
        Dict with success status and details
    """
    import os
    import signal
    import subprocess

    agent = self.get(run_id)
    if not agent:
        return {"success": False, "error": "Agent not found in registry"}

    # Handle in_process mode (asyncio.Task)
    if agent.mode == "in_process" and agent.task:
        agent.task.cancel()
        self.remove(run_id, status="cancelled")
        return {"success": True, "message": "Cancelled in-process task"}

    # For terminal mode, find PID via multiple strategies
    target_pid = agent.pid
    if agent.mode == "terminal" and agent.session_id:
        # Strategy 1: Check session's terminal_context (Claude captures PID via hooks)
        from gobby.storage.sessions import LocalSessionManager
        from gobby.storage.database import LocalDatabase
        try:
            db = LocalDatabase()
            session_mgr = LocalSessionManager(db)
            session = session_mgr.get_session(agent.session_id)
            if session and session.terminal_context:
                ctx_pid = session.terminal_context.get("parent_pid")
                if ctx_pid:
                    target_pid = int(ctx_pid)
                    self._logger.info(f"Found PID from session terminal_context: {target_pid}")
        except Exception as e:
            self._logger.debug(f"terminal_context lookup failed: {e}")

        # Strategy 2: pgrep fallback (for Codex/Gemini without hooks)
        if target_pid == agent.pid or not target_pid:
            try:
                result = subprocess.run(
                    ["pgrep", "-f", f"Your Gobby session_id is: {agent.session_id}"],
                    capture_output=True,
                    text=True,
                    timeout=5.0,
                )
                if result.returncode == 0 and result.stdout.strip():
                    pids = result.stdout.strip().split("\n")
                    target_pid = int(pids[0])
                    self._logger.info(f"Found PID via pgrep: {target_pid}")
            except Exception as e:
                self._logger.warning(f"pgrep fallback failed: {e}")

    if not target_pid:
        return {"success": False, "error": "No target PID found"}

    # Check if process is alive
    try:
        os.kill(target_pid, 0)
    except ProcessLookupError:
        self.remove(run_id, status="completed")
        return {"success": True, "message": f"Process {target_pid} already dead", "already_dead": True}
    except PermissionError:
        return {"success": False, "error": f"No permission to signal PID {target_pid}"}

    # Close PTY if embedded mode
    if agent.master_fd is not None:
        try:
            os.close(agent.master_fd)
        except OSError:
            pass

    # Send signal
    sig = getattr(signal, f"SIG{signal_name}", signal.SIGTERM)
    try:
        os.kill(target_pid, sig)
    except ProcessLookupError:
        self.remove(run_id, status="completed")
        return {"success": True, "message": "Process died during signal", "already_dead": True}

    # Wait for termination with optional SIGKILL escalation
    if signal_name == "TERM" and timeout > 0:
        import time
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                os.kill(target_pid, 0)
                time.sleep(0.1)
            except ProcessLookupError:
                break
        else:
            # Still alive - escalate to SIGKILL
            try:
                os.kill(target_pid, signal.SIGKILL)
                self._logger.info(f"Escalated to SIGKILL for PID {target_pid}")
            except ProcessLookupError:
                pass

    self.remove(run_id, status="killed")
    return {
        "success": True,
        "message": f"Sent SIG{signal_name} to PID {target_pid}",
        "pid": target_pid,
        "signal": signal_name,
        "found_via": "pgrep" if target_pid != agent.pid else "registry",
    }
```

### 2. MCP Tool (`agents.py` ~line 900)

```python
@registry.tool(
    name="kill_agent",
    description="Kill a running agent process by sending a signal (SIGTERM/SIGKILL).",
)
async def kill_agent(
    run_id: str,
    signal: str = "TERM",
    force: bool = False,
) -> dict[str, Any]:
    """
    Kill a running agent process.

    Args:
        run_id: The agent run ID to kill.
        signal: Signal to send (TERM, KILL, INT). Default: TERM.
        force: If True, use SIGKILL immediately.

    Returns:
        Dict with success status and kill details.
    """
    if force:
        signal = "KILL"

    result = agent_registry.kill(run_id, signal_name=signal)

    if result.get("success"):
        runner.cancel_run(run_id)  # Update database

    return result
```

### 3. CLI Command (`cli/agents.py` ~line 380)

```python
@agents.command("kill")
@click.argument("run_ref")
@click.option("--signal", "-s", default="TERM", help="Signal to send (TERM, KILL, INT)")
@click.option("--force", "-f", is_flag=True, help="Use SIGKILL immediately")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def kill_agent_cmd(run_ref: str, signal: str, force: bool, yes: bool) -> None:
    """Kill a running agent process (UUID or prefix).

    Sends SIGTERM by default. For terminal agents, finds the inner CLI
    process via pgrep and kills it.

    Examples:
        gobby agents kill abc123
        gobby agents kill abc123 --force
        gobby agents kill abc123 -s KILL
    """
    run_id = resolve_agent_run_id(run_ref)

    if not yes:
        click.confirm(f"Kill agent {run_id}?", abort=True)

    daemon_url = get_daemon_url()

    try:
        response = httpx.post(
            f"{daemon_url}/mcp/gobby-agents/tools/kill_agent",
            json={"run_id": run_id, "signal": signal, "force": force},
            timeout=15.0,
        )
        response.raise_for_status()
        result = response.json()
    except httpx.ConnectError:
        click.echo("Error: Cannot connect to Gobby daemon", err=True)
        return
    except httpx.HTTPStatusError as e:
        click.echo(f"Error: {e.response.status_code}", err=True)
        return

    if result.get("success"):
        click.echo(result.get("message", f"Killed agent {run_id}"))
        if result.get("found_via") == "pgrep":
            click.echo(f"  (found via pgrep, PID {result.get('pid')})")
        if result.get("already_dead"):
            click.echo("  (process was already terminated)")
    else:
        click.echo(f"Failed: {result.get('error')}", err=True)
```

## Behavior Summary

| Mode | Kill Strategy |
|------|---------------|
| `headless` | Direct SIGTERM to tracked PID → SIGKILL if needed |
| `terminal` | pgrep for session_id in command → kill inner process |
| `in_process` | asyncio.Task.cancel() |
| `embedded` | Close PTY fd + signal |

## Terminal Close Behavior

When the inner process (claude/gemini/codex) is killed:

- Terminal may close automatically (if configured)
- Terminal may show "[Process exited]" and stay open
- Terminal will NOT prompt "Are you sure?" because WE initiated the kill

## Verification

```bash
# 1. Start a terminal agent
gobby agents start "wait for 60 seconds" -s $(gobby sessions list --json | jq -r '.[0].id')

# 2. List to get run_id
gobby agents list --status running

# 3. Kill it
gobby agents kill <run-id> -y

# 4. Verify
gobby agents show <run-id>  # Status: killed
pgrep -f "wait for 60"      # Should return nothing
```

---

# Part 2: Agent Seppuku (MCP-Based Self-Termination)

## Overview

Instead of external SIGTERM/SIGKILL signals to terminate spawned agents, ask the agent to terminate itself via MCP. This provides a cross-platform, graceful shutdown mechanism.

## Problem Statement

The external kill approach has limitations:

| Issue | Description |
|-------|-------------|
| **macOS terminal PID** | `open` command exits immediately, stored PID is useless |
| **Cross-platform signals** | SIGTERM on Unix vs `taskkill` on Windows |
| **PID tracking complexity** | Different strategies needed per mode/provider |
| **No graceful shutdown** | Agent can't save state or clean up |

## Proposed Solution

### Concept

1. Gobby marks session for termination in database
2. On next MCP tool call from agent, return termination instruction
3. Agent receives instruction and self-terminates
4. Agent can clean up gracefully before exiting

### Benefits

| Benefit | Description |
|---------|-------------|
| **Cross-platform** | No SIGTERM/taskkill differences |
| **Graceful shutdown** | Agent can save state before exit |
| **Terminal control** | Agent can close terminal window if desired |
| **No PID tracking** | Works regardless of how agent was spawned |
| **Provider-agnostic** | Works with Claude, Gemini, Codex |

## Technical Investigation

### MCP Notification Limitations

**Question**: Can Gobby send unsolicited messages to agents via MCP?

**Answer**: No, stdio transport doesn't support server-initiated messages.

From MCP spec research:

- Notifications require client to be listening
- stdio transport is request/response based
- Server can't push messages to client unprompted

### Alternative: Tool Response Injection

Instead of notifications, inject termination instruction in next tool response:

```python
# In any MCP tool handler
async def some_tool(session_id: str, ...) -> dict:
    # Check if session is marked for termination
    session = session_manager.get_session(session_id)
    if session and session.terminate_requested:
        return {
            "action": "terminate",
            "reason": "User requested termination",
            "instructions": "Please exit gracefully using 'exit 0'"
        }

    # Normal tool execution
    return {"result": "..."}
```

### Agent-Side Implementation

How would agents handle the termination instruction?

**Option 1: Bash exit**

```bash
exit 0
```

**Option 2: Kill terminal (macOS)**

```bash
osascript -e 'tell application "Ghostty" to close front window'
osascript -e 'tell application "Terminal" to close front window'
osascript -e 'tell application "iTerm" to close current session of current window'
```

**Option 3: Kill process group**

```bash
kill -9 0  # Kills entire process group
```

**Option 4: Platform-specific**

```python
import sys
sys.exit(0)
```

## Open Questions

### 1. CLI Behavior on Unexpected Responses

How do Claude Code, Gemini CLI, and Codex handle unexpected tool responses?

- Do they display the response to the user?
- Do they attempt to parse/execute instructions?
- Do they error out?

**Research needed**: Test each CLI's behavior when MCP tool returns `{"action": "terminate", ...}`

### 2. Instruction Honoring

Will AI agents actually execute termination instructions?

- Claude Code: Likely yes, follows instructions well
- Gemini CLI: Unknown
- Codex: Unknown

**Research needed**: Test with each provider

### 3. Termination Check Injection Point

Where should we inject the termination check?

**Option A: Every tool call** (high overhead)

```python
# In every MCP tool
if check_termination(session_id):
    return terminate_response()
```

**Option B: Middleware/decorator** (cleaner)

```python
@check_termination
async def my_tool(...):
    ...
```

**Option C: Dedicated tool** (agent must call it)

```python
@registry.tool(name="check_status")
async def check_status(session_id: str) -> dict:
    """Agent should call this periodically."""
    if should_terminate(session_id):
        return {"action": "terminate", ...}
    return {"status": "continue"}
```

### 4. Race Conditions

What if agent is mid-execution when termination is requested?

- Should we wait for current tool to complete?
- Should we interrupt immediately?
- How do we handle long-running operations?

### 5. Confirmation UX

Should the agent confirm termination to user before exiting?

```text
Gobby: Termination requested. Exiting gracefully...
[Agent saves state]
[Agent exits]
```

## Implementation Sketch

### Database Schema

```sql
ALTER TABLE sessions ADD COLUMN terminate_requested BOOLEAN DEFAULT FALSE;
ALTER TABLE sessions ADD COLUMN terminate_reason TEXT;
ALTER TABLE sessions ADD COLUMN terminate_requested_at TIMESTAMP;
```

### MCP Tool: Request Termination

```python
@registry.tool(name="request_termination")
async def request_termination(
    session_id: str,
    reason: str = "User requested"
) -> dict:
    """Mark a session for graceful termination."""
    session_manager.mark_for_termination(session_id, reason)
    return {
        "success": True,
        "message": "Session marked for termination. Agent will exit on next tool call."
    }
```

### Termination Check Middleware

```python
def with_termination_check(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        session_id = kwargs.get("session_id") or extract_session_id(args)
        if session_id:
            session = session_manager.get_session(session_id)
            if session and session.terminate_requested:
                return {
                    "action": "terminate",
                    "reason": session.terminate_reason,
                    "instructions": """
Please exit this session gracefully:
1. Save any work in progress
2. Run: exit 0

Thank you for your work!
"""
                }
        return await func(*args, **kwargs)
    return wrapper
```

### CLI Command

```bash
gobby agents seppuku <run-id>  # Request graceful termination
gobby agents kill <run-id>     # Fallback to SIGTERM if seppuku fails
```

## Comparison: SIGTERM vs Seppuku

| Aspect | SIGTERM | Seppuku |
|--------|---------|---------|
| Cross-platform | Requires platform-specific code | Universal |
| PID tracking | Required | Not needed |
| Graceful shutdown | No | Yes |
| State preservation | No | Possible |
| Terminal cleanup | Process dies, terminal may stay | Agent can close terminal |
| Latency | Immediate | Waits for next tool call |
| Reliability | High (OS-level) | Depends on agent cooperation |

## Recommended Approach

1. **Implement SIGTERM-based `kill_agent` first** (reliable, immediate)
2. **Add seppuku as optional graceful mode** (cross-platform, graceful)
3. **Fallback chain**: seppuku → timeout → SIGTERM → SIGKILL

```python
async def terminate_agent(run_id: str, graceful: bool = True, timeout: float = 10.0):
    if graceful:
        # Try seppuku first
        request_termination(run_id)

        # Wait for agent to self-terminate
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not agent_still_running(run_id):
                return {"success": True, "method": "seppuku"}
            await asyncio.sleep(0.5)

    # Fallback to SIGTERM
    result = kill_agent(run_id, signal="TERM")
    if result["success"]:
        return {"success": True, "method": "sigterm"}

    # Last resort: SIGKILL
    return kill_agent(run_id, signal="KILL")
```

## Next Steps

1. [ ] Test CLI behavior with unexpected tool responses (Claude, Gemini, Codex)
2. [ ] Test if agents honor termination instructions
3. [ ] Design termination check injection strategy
4. [ ] Implement database schema changes
5. [ ] Implement `request_termination` MCP tool
6. [ ] Implement termination check middleware
7. [ ] Add `gobby agents seppuku` CLI command
8. [ ] Integration testing with all providers

---

## Related

- Task: #3363 (Add kill_agent functionality)
- Task: #3364 (Fix task_claimed reset bug)
