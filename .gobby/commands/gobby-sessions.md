---
description: This skill should be used when the user asks to "/gobby-sessions", "list sessions", "session handoff", "pickup session". Manage agent sessions - list, show details, handoff context, and resume previous work.
---

# /gobby-sessions - Session Management Skill

This skill manages agent sessions via the gobby-sessions MCP server. Parse the user's input to determine which subcommand to execute.

## Subcommands

### `/gobby-sessions list` - List all sessions
Call `gobby-sessions.list_sessions` with:
- `limit`: Optional max results (default 20)
- `status`: Optional status filter (active, ended)

Returns recent sessions with ID, source (claude/gemini/codex), start time, and status.

Example: `/gobby-sessions list` → `list_sessions(limit=20)`
Example: `/gobby-sessions list active` → `list_sessions(status="active")`

### `/gobby-sessions show <session-id>` - Show session details
Call `gobby-sessions.get_session` with:
- `session_id`: The session ID to retrieve

Returns full session details including:
- Session metadata (source, times, duration)
- Tool calls made
- Tasks worked on
- Summary if available

Example: `/gobby-sessions show sess-abc123` → `get_session(session_id="sess-abc123")`

### `/gobby-sessions handoff` - Prepare session handoff summary
Call `gobby-sessions.prepare_handoff` to generate a continuation context containing:
- Current git state (branch, uncommitted changes)
- Recent tool calls
- Active tasks and their status
- Todo list state

This context is automatically injected on the next session start.

Example: `/gobby-sessions handoff` → `prepare_handoff()`

### `/gobby-sessions pickup [session-id]` - Resume a previous session
Call `gobby-sessions.pickup` with:
- `session_id`: Optional specific session ID (defaults to most recent)

Retrieves the handoff context from a previous session and injects it into the current context.

Example: `/gobby-sessions pickup` → `pickup()` (resumes most recent)
Example: `/gobby-sessions pickup sess-abc123` → `pickup(session_id="sess-abc123")`

## Response Format

After executing the appropriate MCP tool, present the results clearly:
- For list: Table with session ID, source, start time, duration, status
- For show: Full session details in readable format
- For handoff: Confirm handoff context was prepared, show summary
- For pickup: Show injected context, highlight key continuation points

## Session Concepts

- **Session**: A single agent conversation (Claude Code, Gemini CLI, or Codex)
- **Handoff**: Context preservation across sessions via /compact
- **Pickup**: Resuming work from a previous session's context
- **Source**: Which CLI tool created the session

## Error Handling

If the subcommand is not recognized, show available subcommands:
- list, show, handoff, pickup
