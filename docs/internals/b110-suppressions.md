# Instances of `pass  # nosec B110` in Gobby

This document lists all current instances of explicitly suppressed Bandit B110 (try-except-pass) warnings in the Gobby codebase, along with their justifications.

## Context
Bandit B110 flags `try`/`except` blocks that catch `Exception` (or a broad exception type) and do nothing (`pass`). In Gobby, this is strictly controlled and always requires an inline justification explaining *why* it's safe to ignore the error.

## Instances Found

### Server & Routes
- **`src/gobby/servers/routes/sessions.py:819`**
  ```python
  pass  # nosec B110 - empty body is fine
  ```
  _Used during a fallback state check where failure is expected and safely ignored._

### MCP Proxy Tools
#### Sessions Tool
- **`src/gobby/mcp_proxy/tools/sessions/_handoff.py:258`**
  ```python
  pass  # nosec B110 - git status is optional, ignore failures
  ```
- **`src/gobby/mcp_proxy/tools/sessions/_handoff.py:278`**
  ```python
  pass  # nosec B110 - git log is optional, ignore failures
  ```
  _Git context gathering for session handoff is strictly best-effort._

#### Tasks Tool (`_lifecycle.py`)
- **Line 147**: `pass  # nosec B110 - best-effort session edit check`
- **Line 219**: `pass  # nosec B110 - best-effort linking`
- **Line 248**: `pass  # nosec B110 - best-effort linking, don't fail the close`
- **Line 266**: `pass  # nosec B110 - ref stays raw, comparison below handles it`
- **Line 304**: `pass  # nosec B110 - best-effort reset`
- **Line 322**: `pass  # nosec B110 - best-effort worktree update, don't fail the close`
- **Line 408**: `pass  # nosec B110 - best-effort worktree update`
- **Line 625**: `pass  # nosec B110 - best-effort linking`
- **Line 645**: `pass  # nosec B110 - best-effort variable setting`
- **Line 723**: `pass  # nosec B110 - best-effort linking`
- **Line 813**: `pass  # nosec B110 - best-effort linking`
- **Line 897**: `pass  # nosec B110 - best-effort linking`
  _Task lifecycle actions frequently tie into optional external state (worktrees, active sessions) where failure should not block core state transitions._

#### Tasks Tool (`_crud.py`)
- **Line 158**: `pass  # nosec B110 - best-effort linking`
- **Line 178**: `pass  # nosec B110 - best-effort state update`

### Sync & Storage
#### Memories Sync
- **`src/gobby/sync/memories.py:135`**
  ```python
  pass  # nosec B110 - fall back to cwd if project context unavailable
  ```
- **`src/gobby/sync/memories.py:325`**
  ```python
  pass  # nosec B110 - best-effort sanitization
  ```

#### Storage Database
- **`src/gobby/storage/database.py:317`**
  ```python
  pass  # nosec B110 - connection may already be closed
  ```
- **`src/gobby/storage/database.py:333`**
  ```python
  pass  # nosec B110 - ignore errors during shutdown
  ```
- **`src/gobby/storage/database.py:345`**
  ```python
  pass  # nosec B110 - ignore errors during gc
  ```
  _Connection lifecycle and resource cleanup must not bubble errors that could cause dirty shutdowns or panic loops._

### CLI & Worktrees
#### Worktree Manager
- **`src/gobby/worktrees/git.py:695`**
  ```python
  pass  # nosec B110 - method 1 failed, try next method
  ```
  _Fallback logic for git operations._

#### CLI Subcommands
- **`src/gobby/cli/installers/codex.py:152`**
  ```python
  pass  # nosec B110 - best-effort cleanup, directory removal is non-critical
  ```
- **`src/gobby/cli/installers/gemini.py:282`**
  ```python
  pass  # nosec B110 - best-effort cleanup
  ```
- **`src/gobby/cli/sessions.py:475`**
  ```python
  pass  # nosec B110 - git status is optional
  ```
- **`src/gobby/cli/sessions.py:495`**
  ```python
  pass  # nosec B110 - git log is optional
  ```

### Agents
#### Headless Spawner
- **`src/gobby/agents/spawners/headless.py:150`**
  ```python
  pass  # nosec B110 - Best-effort process cleanup
  ```

## Summary
The pattern `pass  # nosec B110` is used heavily in the codebase to denote **best-effort operations** (like updating metadata or linking objects during a broader transaction) and **cleanup routines** (like closing database connections or removing temporary files) where raising an exception would interrupt critical path operations.
