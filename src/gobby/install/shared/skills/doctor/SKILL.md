---
name: doctor
description: This skill should be used when the user asks to "/gobby doctor", "run doctor", "security audit", "health check", "systems check", "run diagnostics". Run comprehensive systems check and security audit verifying CLI and MCP tools work correctly.
category: core
---

# /gobby doctor - System Health and Security Skill

This skill runs a comprehensive systems check and security audit to verify Gobby's CLI commands and MCP tools are functioning correctly. All tests use the `__diag__` prefix for automatic cleanup.

## Subcommands

### `/gobby doctor` - Show help
Display available options and a brief description of each check type.

### `/gobby doctor --functional` - Functional tests (phases 1-3)
Run prerequisite checks, read-only tests, and write+cleanup tests. Does not include worktree/clone tests or security audit.

### `/gobby doctor --security` - Security audit (phase 5 only)
Run security-focused checks: file permissions, plaintext secrets scan, HTTP binding check, webhook HTTPS validation, debug log level warning, plugin security, MCP server URLs, and permissive skills.

### `/gobby doctor --all` - Full check (all phases)
Run everything: functional tests (phases 1-4 including worktree/clone) plus security audit (phase 5).

### `/gobby doctor --cleanup` - Cleanup only
Scan for and remove stale `__diag__` artifacts from previous failed runs.

## Execution Protocol

Execute phases sequentially. Track all created resource IDs for cleanup. Report PASS/FAIL per test.

---

## Phase 1: Prerequisites

Run these first. If any fail, stop and report - other tests won't be reliable.

### 1.1 Daemon Status
```bash
gobby status
```
Expected: Daemon is running.

### 1.2 MCP Server Connectivity
Call `gobby.list_mcp_servers()`

Expected: Returns list of servers. Check that core servers are connected:
- `gobby-tasks`
- `gobby-memory`
- `gobby-sessions`

### 1.3 Database Connectivity
Call `gobby-sessions.list_sessions(limit=1)`

Expected: Returns without error (empty list is OK).

Report summary: "Prerequisites: X/3 PASS"

---

## Phase 2: Read-Only Tests

These tests only read data - no cleanup needed.

### 2.1 CLI List Commands
Run each command and verify no errors:

| Command | Expected |
|---------|----------|
| `gobby sessions list --limit 1` | Returns without error |
| `gobby tasks list --limit 1` | Returns without error |
| `gobby memory list --limit 1` | Returns without error |
| `gobby skills list --limit 1` | Returns without error |
| `gobby workflows list` | Returns without error |
| `gobby worktrees list` | Returns without error |
| `gobby clones list` | Returns without error |
| `gobby agents list` | Returns without error |

### 2.2 MCP List Tools
Call each tool and verify response:

| Server | Tool | Expected |
|--------|------|----------|
| `gobby-sessions` | `list_sessions` | Returns list/empty |
| `gobby-sessions` | `session_stats` | Returns stats object |
| `gobby-tasks` | `list_tasks` | Returns list/empty |
| `gobby-memory` | `list_memories` | Returns list/empty |
| `gobby-memory` | `memory_stats` | Returns stats object |
| `gobby-metrics` | `get_tool_metrics` | Returns metrics object |
| `gobby-metrics` | `get_top_tools` | Returns list |
| `gobby-workflows` | `list_workflows` | Returns list/empty |
| `gobby-worktrees` | `list_worktrees` | Returns list/empty |
| `gobby-clones` | `list_clones` | Returns list/empty |
| `gobby-agents` | `list_agents` | Returns list/empty |

### 2.3 MCP Get/Search Tools
Call tools that retrieve or search data:

| Server | Tool | Args | Expected |
|--------|------|------|----------|
| `gobby` | `search_tools` | `query="test"` | Returns results |
| `gobby` | `recommend_tools` | `task_description="list items"` | Returns recommendations |
| `gobby-memory` | `search_memories` | `query="__nonexistent__"` | Returns empty (no error) |

Report summary: "Read-Only: X/Y PASS"

---

## Phase 3: Write + Cleanup Tests

Create test resources, verify, then delete. Track all IDs for cleanup.

**CRITICAL**: Initialize cleanup tracker before starting:
```
cleanup_tracker = {
    "memories": [],
    "tasks": [],
    "worktrees": [],
    "clones": []
}
```

### 3.1 Memory Create/Delete Cycle

**Create:**
```
gobby-memory.create_memory(
    content="__diag__ diagnostic test memory - safe to delete",
    tags="__diag__,test",
    importance=0.1
)
```
Store returned `memory_id` in `cleanup_tracker["memories"]`.

**Verify:** Call `gobby-memory.get_memory(memory_id=<id>)` - should return the memory.

**Delete:** Call `gobby-memory.delete_memory(memory_id=<id>)`

**Verify deletion:** Call `gobby-memory.get_memory(memory_id=<id>)` - should return error/not found.

### 3.2 Task Create/Close Cycle

**Get session ID first:**
Call `gobby-sessions.get_current_session()` to retrieve the current session object.
Use the returned `id` field as the `session_id` parameter below.

**Create:**
```
gobby-tasks.create_task(
    title="__diag__ diagnostic test task",
    description="Diagnostic test task - safe to delete",
    task_type="chore",
    session_id=<id from gobby-sessions.get_current_session()>
)
```
Store returned `task_id` in `cleanup_tracker["tasks"]`.

**Verify:** Call `gobby-tasks.get_task(task_id=<id>)` - should return the task.

**Update:** Call `gobby-tasks.update_task(task_id=<id>, status="completed")`

**Verify update:** Call `gobby-tasks.get_task(task_id=<id>)` - status should be "completed".

**Close:** Call `gobby-tasks.close_task(task_id=<id>, reason="completed")`

### 3.3 Workflow Variable Cycle (session-scoped, auto-cleaned on session termination)

**Note:** Workflow variables are session-scoped and automatically cleaned up when the session ends. No `__diag__` prefix needed since they don't persist beyond the session.

**Set:**
```
gobby-workflows.set_variable(
    name="diag_test_var",
    value="diagnostic_value"
)
```

**Get:** Call `gobby-workflows.get_variable(name="diag_test_var")` - should return "diagnostic_value".

Report summary: "Write+Cleanup: X/3 PASS"

---

## Phase 4: Resource-Heavy Tests (--full only)

Only run with `--full` flag. These create filesystem resources.

### 4.1 Worktree Cycle

**Check spawn capability:**
```
gobby-worktrees.can_spawn_worktree()
```
If false, skip with note "Worktree spawn not available".

**Create:**
```
gobby-worktrees.create_worktree(
    branch="__diag__/test-branch",
    base_branch="HEAD"
)
```
Store returned `worktree_id`.

**Verify:** Call `gobby-worktrees.get_worktree(worktree_id=<id>)` - should return worktree.

**Delete:** Call `gobby-worktrees.delete_worktree(worktree_id=<id>, force=true)`

**Verify deletion:** Call `gobby-worktrees.get_worktree(worktree_id=<id>)` - should return error/not found.

### 4.2 Clone Cycle

**Check spawn capability:**
```
gobby-clones.can_spawn_clone()
```
If false, skip with note "Clone spawn not available".

**Create:**
```
gobby-clones.create_clone(
    name="__diag__-test-clone"
)
```
Store returned `clone_id`.

**Verify:** Call `gobby-clones.get_clone(clone_id=<id>)` - should return clone.

**Delete:** Call `gobby-clones.delete_clone(clone_id=<id>, force=true)`

**Verify deletion:** Call `gobby-clones.get_clone(clone_id=<id>)` - should return error/not found.

### 4.3 Agent Spawn Check (read-only)

**Check capability:**
```
gobby-agents.can_spawn_agent()
```
Report result (PASS if returns true/false without error, capability status is informational).

Report summary: "Resource-Heavy: X/3 PASS"

---

## Phase 5: Security Audit

Read-only security checks that scan configuration and runtime state for potential security issues. These checks are non-destructive and only report findings.

### 5.1 File Permissions

Check that sensitive files have restrictive permissions (0o600 or stricter):

| File | Location | Expected |
|------|----------|----------|
| `config.yaml` | `~/.gobby/config.yaml` | 0o600 |
| `.mcp.json` | `~/.mcp.json` | 0o600 |
| `gobby-hub.db` | `~/.gobby/gobby-hub.db` | 0o600 |

Report: WARN if permissions are more permissive than expected.

### 5.2 Plaintext Secrets Scan

Scan configuration files for potential plaintext secrets:

```bash
# Check for API keys, tokens, passwords in config files
grep -iE "(api_key|api-key|apikey|secret|token|password|auth)" ~/.gobby/config.yaml
```

Patterns to flag:
- `api_key: sk-...`
- `password: ...` (if not using env var reference)
- Any value that looks like a token (long alphanumeric strings)

Report: WARN if potential plaintext secrets found. Recommend using environment variables.

### 5.3 HTTP Binding Check

Check if the daemon is bound to a non-localhost address:

```python
# In config.yaml, check server binding
server:
  host: "127.0.0.1"  # OK
  host: "0.0.0.0"    # WARN - exposed to network
```

Report: WARN if server is bound to `0.0.0.0` or a public IP address.

### 5.4 Webhook HTTPS Validation

Check that any configured webhooks use HTTPS:

```python
# In config.yaml
webhooks:
  - url: "https://example.com/hook"  # OK
  - url: "http://example.com/hook"   # WARN - unencrypted
```

Report: WARN for each webhook using HTTP instead of HTTPS.

### 5.5 Debug Log Level Warning

Check if debug logging is enabled in production:

```python
# In config.yaml
logging:
  level: "DEBUG"  # WARN in production
  level: "INFO"   # OK
```

Report: WARN if log level is DEBUG (may expose sensitive information).

### 5.6 Plugin Security Warning

List any third-party or non-bundled skills/plugins:

```python
# Check for skills not in the bundled skills directory
gobby-skills.list_skills()
```

Report: INFO listing non-bundled skills. Note: These have access to MCP tools and should be reviewed.

### 5.7 MCP Server URL Validation

Check that MCP server URLs are valid and use HTTPS where appropriate:

```python
gobby.list_mcp_servers()
```

For each server:
- HTTP servers: WARN if not localhost
- Stdio servers: OK (local process)
- WebSocket servers: WARN if not using wss://

Report: WARN for any MCP server communicating over unencrypted channels to non-localhost.

### 5.8 Permissive Skills Listing

Check for skills with overly permissive tool access:

```python
# Check skills that allow all tools or sensitive tool categories
gobby-skills.list_skills()
```

Flag skills where:
- `allowed_tools` is empty/null (allows all tools)
- `allowed_tools` includes sensitive tools (file write, shell execute)

Report: INFO listing skills with broad tool access.

---

Report summary: "Security Audit: X/8 PASS, Y WARN"

---

## Cleanup Protocol

Run cleanup in this order (reverse dependency):

### Step 1: Clean Clones
Search for clones with `__diag__` prefix:
```
gobby-clones.list_clones()
```
For each clone with name starting with `__diag__`:
```
gobby-clones.delete_clone(clone_id=<id>, force=true)
```

### Step 2: Clean Worktrees
Search for worktrees with `__diag__` prefix:
```
gobby-worktrees.list_worktrees()
```
For each worktree with branch starting with `__diag__`:
```
gobby-worktrees.delete_worktree(worktree_id=<id>, force=true)
```

### Step 3: Clean Tasks
Search for tasks with `__diag__` prefix:
```
gobby-tasks.list_tasks()
```
For each task with title starting with `__diag__`:
```
gobby-tasks.close_task(task_id=<id>, reason="obsolete")
```

### Step 4: Clean Memories
Search for memories with `__diag__` tag:
```
gobby-memory.list_memories(tags_any="__diag__")
```
For each memory:
```
gobby-memory.delete_memory(memory_id=<id>)
```

---

## Stale Artifact Detection

Before running tests, check for orphaned `__diag__` artifacts:

1. Call `gobby-memory.list_memories(tags_any="__diag__")`
2. Call `gobby-tasks.list_tasks()` and filter for `__diag__` prefix
3. Call `gobby-worktrees.list_worktrees()` and filter for `__diag__` prefix
4. Call `gobby-clones.list_clones()` and filter for `__diag__` prefix

If any found, report:
```
WARNING: Found X stale diagnostic artifacts from previous run.
Run `/gobby doctor --cleanup` to remove them, or they will be cleaned after this run.
```

---

## Output Format

### Progress Reporting
For each test, report:
```
[PASS] <Test Name>
[FAIL] <Test Name>: <Error Message>
[SKIP] <Test Name>: <Reason>
```

### Summary
At the end, report:
```
=== Doctor Summary ===
Phase 1 (Prerequisites):  X/3 PASS
Phase 2 (Read-Only):      X/Y PASS
Phase 3 (Write+Cleanup):  X/3 PASS
Phase 4 (Resource-Heavy): X/3 PASS (or "Skipped - use --all")
Phase 5 (Security Audit): X/8 PASS, Y WARN (or "Skipped - use --security or --all")

Overall: X/Y tests passed, Z warnings
Cleanup: All __diag__ artifacts removed
```

### Failure Report
If any tests fail, include a failure summary:
```
=== Failures ===
1. [Phase 2] list_memories: Connection timeout after 10s
2. [Phase 3] create_task: Permission denied
```

---

## Timeouts

| Operation Type | Timeout |
|----------------|---------|
| Read operations | 10 seconds |
| Write operations | 30 seconds |
| Resource-heavy (worktree/clone) | 120 seconds |

If a timeout occurs, log the failure and continue to the next test.

---

## Error Handling

1. **Prerequisite failures**: Stop immediately - report which prerequisite failed
2. **Test failures**: Log failure, continue to next test, ensure cleanup still runs
3. **Cleanup failures**: Log warning but don't fail the diagnostic
4. **Timeout**: Treat as failure, continue to next test

---

## Examples

### Show help
User: `/gobby doctor`
Display available options and descriptions.

### Functional health check
User: `/gobby doctor --functional`
Run phases 1-3 (prerequisites, read-only, write+cleanup tests).

### Security audit
User: `/gobby doctor --security`
Run phase 5 security checks only.

### Full system test
User: `/gobby doctor --all`
Run all phases including worktree/clone tests and security audit.

### Cleanup stale artifacts
User: `/gobby doctor --cleanup`
Only run cleanup protocol, report what was removed.
