# Implementation Plan: Cursor, Windsurf, Copilot CLI Adapters

## Summary

Add 3 new CLI adapters to Gobby following the existing adapter pattern. All events map to existing `HookEventType` values - no new event types needed.

---

## Research Background

Researched 10 AI coding tools for hooks system compatibility with Gobby. Found **4 tools with robust hooks systems** that Gobby could support, plus several that rely primarily on MCP for extensibility.

---

## Tools WITH Hooks Systems (Good Candidates)

### 1. Cursor (Best Match)
**Hooks System:** Most comprehensive, very similar to Claude Code

| Feature | Details |
|---------|---------|
| Config Location | `.cursor/hooks.json` |
| Hook Count | 15+ lifecycle events |
| Format | JSON with version field |
| Blocking | Exit code 2 to block actions |
| Context | JSON via stdin |

**Hook Events:**
- `sessionStart` / `sessionEnd`
- `preToolUse` / `postToolUse` / `postToolUseFailure`
- `subagentStart` / `subagentStop`
- `beforeShellExecution` / `afterShellExecution`
- `beforeMCPExecution` / `afterMCPExecution`
- `beforeReadFile` / `afterFileEdit`
- `beforeSubmitPrompt`
- `preCompact`, `stop`, `afterAgentResponse`, `afterAgentThought`

**Docs:** https://cursor.com/docs/agent/hooks

---

### 2. Windsurf (Cascade)
**Hooks System:** Enterprise-grade, very similar architecture

| Feature | Details |
|---------|---------|
| Config Location | System/user/workspace JSON files |
| Hook Count | 11 events |
| Format | JSON with `hooks` object |
| Blocking | Exit code 2 for pre-hooks |
| Context | JSON via stdin |

**Hook Events:**
- `pre_read_code` / `post_read_code`
- `pre_write_code` / `post_write_code`
- `pre_run_command` / `post_run_command`
- `pre_mcp_tool_use` / `post_mcp_tool_use`
- `pre_user_prompt`
- `post_cascade_response`
- `post_setup_worktree`

**Docs:** https://docs.windsurf.com/windsurf/cascade/hooks

---

### 3. GitHub Copilot CLI
**Hooks System:** Solid foundation, major market presence

| Feature | Details |
|---------|---------|
| Config Location | `.copilot/hooks.json` (local CLI) or `.github/hooks/hooks.json` (Coding Agent) |
| Hook Count | 6 events |
| Format | JSON with bash/powershell commands |
| Context | JSON via stdin |

**Hook Events:**
- `sessionStart` / `sessionEnd`
- `userPromptSubmitted`
- `preToolUse` / `postToolUse`
- `errorOccurred`

**Docs:** https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent/use-hooks

---

### 4. OpenCode (Lower Priority)
**Hooks System:** Plugin-based (TypeScript/JavaScript)

| Feature | Details |
|---------|---------|
| Config Location | `.opencode/plugin/` directory |
| Hook Count | 3+ event types |
| Format | TypeScript/JavaScript modules |
| Context | Function parameters |

**Hook Events:**
- `tool.execute.before` / `tool.execute.after`
- `event` (session lifecycle like `session.idle`)

**Docs:** https://opencode.ai/docs/

---

## Tools WITHOUT Traditional Hooks (MCP-Only)

### Continue.dev
- **Extensibility:** MCP servers, pre-commit hooks integration
- **No agent hooks system** - relies on MCP for tool extensibility

### Cline / RooCode
- **Extensibility:** MCP only
- **No hooks system** - human-in-the-loop approval model

### Aider
- **Extensibility:** Git pre-commit hooks only (`--git-commit-verify`)
- **No agent hooks system**

### Amazon Q Developer
- **Extensibility:** Agent hooks (in agent configs), MCP
- **Context hooks deprecated** - moving to agent-based approach

---

## Gobby Adapter Pattern

Gobby uses individual adapters extending `BaseAdapter` (see `src/gobby/adapters/`). Each adapter:

1. Has a `source` attribute (`SessionSource` enum value)
2. Implements `translate_to_hook_event()` - CLI format → unified `HookEvent`
3. Implements `translate_from_hook_response()` - `HookResponse` → CLI format
4. Has an `EVENT_MAP` dict for event name translation

### Existing Unified Event Types (`HookEventType`)

```
SESSION_START, SESSION_END     # All CLIs
BEFORE_AGENT, AFTER_AGENT      # Prompt lifecycle
STOP                           # Agent exit
BEFORE_TOOL, AFTER_TOOL        # Tool lifecycle
PRE_COMPACT                    # Context compaction
SUBAGENT_START, SUBAGENT_STOP  # Subagent lifecycle
PERMISSION_REQUEST, NOTIFICATION
```

---

# Implementation Plan

## Files to Create

| File | Purpose |
|------|---------|
| `src/gobby/adapters/cursor.py` | CursorAdapter (~280 lines) |
| `src/gobby/adapters/windsurf.py` | WindsurfAdapter (~250 lines) |
| `src/gobby/adapters/copilot.py` | CopilotAdapter (~200 lines) |
| `tests/adapters/test_cursor.py` | Cursor tests |
| `tests/adapters/test_windsurf.py` | Windsurf tests |
| `tests/adapters/test_copilot.py` | Copilot tests |

## Files to Modify

| File | Changes |
|------|---------|
| `src/gobby/hooks/events.py` | Add `CURSOR`, `WINDSURF`, `COPILOT` to SessionSource |
| `src/gobby/adapters/__init__.py` | Export new adapters |
| `src/gobby/servers/routes/mcp/hooks.py` | Add adapter selection for new sources |

---

## Event Mappings

### Cursor (15 events → camelCase)

```python
EVENT_MAP = {
    "sessionStart": SESSION_START,
    "sessionEnd": SESSION_END,
    "beforeSubmitPrompt": BEFORE_AGENT,
    "preToolUse": BEFORE_TOOL,
    "postToolUse": AFTER_TOOL,
    "beforeShellExecution": BEFORE_TOOL,  # tool_type: Bash
    "afterShellExecution": AFTER_TOOL,
    "beforeReadFile": BEFORE_TOOL,        # tool_type: Read
    "afterFileEdit": AFTER_TOOL,          # tool_type: Edit
    "beforeMCPExecution": BEFORE_TOOL,    # MCP tool
    "afterMCPExecution": AFTER_TOOL,
    "preCompact": PRE_COMPACT,
    "stop": STOP,
    "subagentStart": SUBAGENT_START,
    "subagentStop": SUBAGENT_STOP,
}
```

### Windsurf (11 events → snake_case)

**Note:** Windsurf has no explicit session start/end hooks. The adapter will:
- Treat first `pre_user_prompt` as SESSION_START (creates session)
- Use `pre_user_prompt` for BEFORE_AGENT on subsequent calls
- No SESSION_END equivalent (session times out or inferred from inactivity)

```python
EVENT_MAP = {
    "pre_read_code": BEFORE_TOOL,     # tool_type: Read
    "post_read_code": AFTER_TOOL,
    "pre_write_code": BEFORE_TOOL,    # tool_type: Write
    "post_write_code": AFTER_TOOL,
    "pre_run_command": BEFORE_TOOL,   # tool_type: Bash
    "post_run_command": AFTER_TOOL,
    "pre_mcp_tool_use": BEFORE_TOOL,  # MCP tool
    "post_mcp_tool_use": AFTER_TOOL,
    "pre_user_prompt": BEFORE_AGENT,  # Also triggers SESSION_START on first call
    "post_cascade_response": AFTER_AGENT,
    "post_setup_worktree": NOTIFICATION,
}

# WindsurfAdapter needs state tracking:
# - Check if session exists for this external_id
# - If not, emit SESSION_START before BEFORE_AGENT
```

### Copilot CLI (6 events → camelCase)

```python
EVENT_MAP = {
    "sessionStart": SESSION_START,
    "sessionEnd": SESSION_END,
    "userPromptSubmitted": BEFORE_AGENT,
    "preToolUse": BEFORE_TOOL,
    "postToolUse": AFTER_TOOL,
    "errorOccurred": NOTIFICATION,
}
```

---

## Response Formats

All three use exit code 2 to block actions.

**Cursor** (same as Claude Code):
```json
{"continue": true, "decision": "approve", "hookSpecificOutput": {...}}
```

**Windsurf**:
```json
{"decision": "allow", "reason": "...", "hookSpecificOutput": {...}}
```

**Copilot CLI**:
```json
{"continue": true, "decision": "allow", "reason": "...", "context": "..."}
```

---

## Implementation Order

1. **SessionSource enum** - Add 3 new values
2. **CursorAdapter** - Most similar to Claude Code (reference impl)
3. **WindsurfAdapter** - Different naming convention (snake_case)
4. **CopilotAdapter** - Simplest (6 events)
5. **Hooks router update** - Add adapter selection
6. **Tests** - Following test_gemini.py pattern

---

## Verification

1. **Unit tests**: Event mapping, response translation for each adapter
2. **Integration test**: Hook round-trip with mock HookManager
3. **Manual test**: Configure each CLI to call Gobby's hook endpoint

```bash
# Run tests
uv run pytest tests/adapters/test_cursor.py -v
uv run pytest tests/adapters/test_windsurf.py -v
uv run pytest tests/adapters/test_copilot.py -v

# Type check
uv run mypy src/gobby/adapters/cursor.py src/gobby/adapters/windsurf.py src/gobby/adapters/copilot.py
```

---

## Sources

- [Cursor Hooks Docs](https://cursor.com/docs/agent/hooks)
- [Windsurf Cascade Hooks](https://docs.windsurf.com/windsurf/cascade/hooks)
- [GitHub Copilot Hooks](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent/use-hooks)
- [OpenCode Extensibility Guide](https://dev.to/einarcesar/does-opencode-support-hooks-a-complete-guide-to-extensibility-k3p)
- [Cursor Hooks Deep Dive](https://blog.gitbutler.com/cursor-hooks-deep-dive)
