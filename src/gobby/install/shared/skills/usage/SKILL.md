---
name: usage
description: This skill should be used when the user asks to "/gobby usage", "show usage", "token usage", "cost report", "budget status". Display token usage, costs, and budget status from the gobby-metrics MCP server.
category: core
---

# /gobby usage - Token Usage and Cost Reporting

This skill displays token usage, costs, and budget status by querying the gobby-metrics MCP server.

## Subcommands

> **Note**: All tool calls below are executed against `server_name="gobby-metrics"`.

### `/gobby usage` - Show help
Display available options and current budget status.

### `/gobby usage --today` - Today's usage summary
Show token usage and costs for today only.

```python
await call_tool(server_name="gobby-metrics", tool_name="get_usage_report", arguments={"days": 1})
```

### `/gobby usage --week` - Weekly usage summary
Show token usage and costs for the last 7 days.

```python
await call_tool(server_name="gobby-metrics", tool_name="get_usage_report", arguments={"days": 7})
```

### `/gobby usage --budget` - Budget status only
Show current daily budget status without usage breakdown.

```python
await call_tool(server_name="gobby-metrics", tool_name="get_budget_status", arguments={})
```

## Output Format

Present the results in a clear, readable format:

### Usage Report
```
Token Usage (last N days):
  Input tokens:  XXX,XXX
  Output tokens: XXX,XXX
  Cache read:    XXX,XXX
  Cache create:  XXX,XXX
  Total tokens:  XXX,XXX

Estimated Cost: $X.XX
```

### Budget Status
```
Daily Budget Status:
  Budget:    $X.XX
  Used:      $X.XX
  Remaining: $X.XX (XX%)
```

## Tool Calls Reference

### get_usage_report
```python
await call_tool(server_name="gobby-metrics", tool_name="get_usage_report", arguments={"days": N})
```
Returns token counts and cost estimates for the specified period.

Parameters:
- `days` (int, optional): Number of days to include. Default is 1.

### get_budget_status
```python
await call_tool(server_name="gobby-metrics", tool_name="get_budget_status", arguments={})
```
Returns current daily budget configuration and usage.

Returns:
- Budget limit
- Amount used today
- Remaining budget
- Percentage used

## Error Handling

If no usage data is found, display a friendly message:
```
No usage data found for the specified period.
```

If budget is not configured, note this in the output:
```
Daily budget not configured. Set GOBBY_DAILY_BUDGET_USD to enable budget tracking.
```
