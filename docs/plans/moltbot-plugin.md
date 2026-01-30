# Plan: Gobby as MCP Server for Moltbot

**Session**: #640
**Status**: Approved
**Date**: 2026-01-29

## Summary

Create a Moltbot plugin that exposes Gobby's MCP tools to the Pi agent. The plugin connects to Gobby's HTTP endpoint (`http://localhost:60887/mcp`) and registers a meta-tool that provides access to all Gobby capabilities.

## Architecture

```
Moltbot Pi Agent
       ↓
   gobby plugin (meta-tool)
       ↓
   GobbyClient (HTTP)
       ↓
   Gobby Daemon @ :60887/mcp
       ↓
   50+ tools (tasks, sessions, workflows, memory, agents)
```

## Implementation

### File Structure

```
~/Projects/moltbot/extensions/gobby/
├── index.ts              # Plugin registration
├── src/
│   ├── gobby-client.ts   # HTTP client for Gobby MCP
│   └── gobby-tool.ts     # Meta-tool implementation
```

### 1. Plugin Entry Point (`index.ts`)

Follow the lobster plugin pattern:
- Register tool factory with `optional: true`
- Disable in sandboxed mode
- Pass plugin API to tool creator

### 2. Gobby Client (`src/gobby-client.ts`)

HTTP client wrapping Gobby's MCP endpoint:
- `status()` - Check daemon availability
- `listServers()` - List MCP servers
- `listTools(server)` - List tools with brief metadata
- `getToolSchema(server, tool)` - Get full schema
- `callTool(server, tool, args)` - Execute tool

Uses `fetch` to POST to `http://localhost:60887/mcp` with MCP JSON-RPC format.

### 3. Meta-Tool (`src/gobby-tool.ts`)

Single tool with action dispatch:

```typescript
{
  name: "gobby",
  description: "Access Gobby daemon tools...",
  parameters: Type.Object({
    action: Type.Unsafe<"status" | "list_servers" | "list_tools" | "get_schema" | "call">({
      type: "string",
      enum: ["status", "list_servers", "list_tools", "get_schema", "call"]
    }),
    server: Type.Optional(Type.String()),
    tool: Type.Optional(Type.String()),
    args: Type.Optional(Type.Record(Type.String(), Type.Unknown())),
  }),
  execute: async (_id, params) => { ... }
}
```

Returns `{ content: [...], details: ... }` format matching Pi agent expectations.

### Error Handling

- Return helpful error when daemon unavailable: `"hint": "Start with: gobby start"`
- Don't throw on connection errors - return structured error response

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Integration type | Plugin (not system extension) | Follows existing patterns, no core changes |
| Tool registration | Single meta-tool | Avoids 50+ tool bloat, matches Gobby's progressive disclosure |
| Transport | HTTP fetch | Simpler than stdio, Gobby already exposes HTTP |
| Schema handling | Pass-through via `Type.Unsafe()` | TypeBox accepts raw JSON Schema |

## Files to Create

1. **`~/Projects/moltbot/extensions/gobby/index.ts`**
   - Plugin entry, registers gobby tool

2. **`~/Projects/moltbot/extensions/gobby/src/gobby-client.ts`**
   - HTTP client for MCP endpoint

3. **`~/Projects/moltbot/extensions/gobby/src/gobby-tool.ts`**
   - Meta-tool with action dispatch

## Reference Files

- `~/Projects/moltbot/extensions/lobster/index.ts` - Plugin pattern
- `~/Projects/moltbot/extensions/lobster/src/lobster-tool.ts` - Tool structure
- `~/Projects/moltbot/src/plugins/types.ts` - API types
- `~/Projects/gobby/src/gobby/mcp_proxy/server.py` - MCP interface

## Verification

1. Start Gobby daemon: `cd ~/Projects/gobby && uv run gobby start`
2. Build plugin: `cd ~/Projects/moltbot && bun run build`
3. Test via Moltbot gateway:
   ```
   gobby action=status
   gobby action=list_servers
   gobby action=list_tools server=gobby
   gobby action=call server=gobby tool=list_mcp_servers
   ```
4. Verify error handling with daemon stopped

## Future Enhancements (Out of Scope)

- Direct tool wrappers for high-frequency tools
- Session correlation between Moltbot and Gobby
- Bidirectional integration (Moltbot channels in Gobby)
