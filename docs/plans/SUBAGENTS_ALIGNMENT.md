# Phase 1.5: Subagent Alignment & Context Injection

## Goal

Align the current `start_agent` implementation with the `SUBAGENTS.md` design vision. This "Phase 1.5" bridges the gap between the initial "in-process only" implementation and the future "terminal/worktree" capabilities by:

1. Updating the `start_agent` MCP tool signature to match the planned API.
2. Implementing the `session_context` injection logic (`summary_markdown`, `transcript:N`, `file:path`).
3. Refactoring `AgentRunner` to support distinct "spawn" (setup) and "execute" (run) phases, enabling future non-blocking modes.

## User Review Required

- **Context Injection**: Is reading arbitrary files via `file:path` allowed for subagents? (Assuming yes, as agents run with user permissions).
- **Breaking Change**: This updates the internal `start_agent` signature. Downstream tools (if any exist yet) would need updates. (None exist yet).

## Proposed Changes

### Agents Package

#### [NEW] [context.py](file:///Users/josh/Projects/gobby/src/gobby/agents/context.py)

- Implement `ContextResolver` class.
- Logic to parse `session_context` strings:
  - `summary_markdown` (default): Get from parent session.
  - `session_id:<id>`: Get summary from specific session.
  - `transcript:<n>`: Get last N messages from `LocalSessionMessageManager`.
  - `file:<path>`: Read file content.

#### [runner.py](file:///Users/josh/Projects/gobby/src/gobby/agents/runner.py)

- Refactor `run()` method into:
  - `prepare_run(config) -> AgentRunContext`: Creates session, database record, workflow state.
  - `execute_run(context, config) -> AgentResult`: Runs the executor loop.
  - `run(config)`: Helper that calls `prepare_run` then `execute_run` (preserving current behavior).
- Add `resolve_context` integration in `prepare_run` (or just before).

### MCP Tools

#### [agents.py](file:///Users/josh/Projects/gobby/src/gobby/mcp_proxy/tools/agents.py)

- Update `start_agent` signature:

    ```python
    async def start_agent(
        # ... existing ...
        mode: str = "in_process",
        session_context: str = "summary_markdown",
        worktree_id: str | None = None,
        # ...
    )
    ```

- Use `ContextResolver` to fetch context string.
- Prepend context to `prompt` before creating `AgentConfig`.
- Validate `mode` (raise NotImplementedError for 'terminal'/'embedded'/'headless' for now).

## Verification Plan

### Automated Tests

- **New Test File**: `tests/agents/test_context_resolver.py`
  - Test parsing of all context types.
  - Mock session/message storage to verify data retrieval.
- **Update Existing**: `tests/mcp_proxy/test_agent_tools.py` (if exists) or create it.
  - Verify `start_agent` accepts new parameters.
  - Verify error on unsupported modes.

### User Verification

- Since we don't have a UI yet, I will use `call_tool` to `start_agent` with different `session_context` values and verify the `messages` or `prompt` sent to the executor (via mocking or debug logs).
