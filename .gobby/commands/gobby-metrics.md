---
description: This skill should be used when the user asks to "/gobby-metrics", "tool metrics", "usage stats", "performance report". View tool usage metrics, performance statistics, and server health.
---

# /gobby-metrics - Metrics and Statistics Skill

This skill retrieves usage metrics via the gobby-metrics MCP server. Parse the user's input to determine which subcommand to execute.

## Subcommands

### `/gobby-metrics report` - Generate usage report
Call `gobby-metrics.get_report` with:
- `period`: Time period (day, week, month, all)
- `format`: Output format (summary, detailed)

Returns comprehensive usage statistics.

Example: `/gobby-metrics report` → `get_report(period="week")`
Example: `/gobby-metrics report month detailed` → `get_report(period="month", format="detailed")`

### `/gobby-metrics tools` - Tool usage statistics
Call `gobby-metrics.get_tool_metrics` with:
- `server`: Optional filter by server name
- `limit`: Max tools to show (default 20)

Returns per-tool statistics:
- Call count
- Average response time
- Error rate
- Last used

Example: `/gobby-metrics tools` → `get_tool_metrics()`
Example: `/gobby-metrics tools gobby-tasks` → `get_tool_metrics(server="gobby-tasks")`

### `/gobby-metrics servers` - Server health status
Call `gobby-metrics.get_server_metrics` to check:
- Connection status for each MCP server
- Response times
- Error counts
- Uptime

Example: `/gobby-metrics servers` → `get_server_metrics()`

### `/gobby-metrics sessions` - Session statistics
Call `gobby-metrics.get_session_metrics` with:
- `period`: Time period (day, week, month)

Returns session statistics:
- Total sessions
- Average duration
- Tool calls per session
- Sessions by source (claude/gemini/codex)

Example: `/gobby-metrics sessions` → `get_session_metrics(period="week")`

## Response Format

After executing the appropriate MCP tool, present the results clearly:
- For report: Summary with key metrics highlighted
- For tools: Table sorted by usage count
- For servers: Health status with indicators
- For sessions: Statistics with trends

## Metrics Concepts

- **Tool metrics**: Per-tool usage and performance
- **Server metrics**: MCP server connection health
- **Session metrics**: Agent session statistics

## Error Handling

If the subcommand is not recognized, show available subcommands:
- report, tools, servers, sessions
