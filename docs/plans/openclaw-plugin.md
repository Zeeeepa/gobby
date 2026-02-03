# Plan: Gobby as MCP Server for OpenClaw

**Session**: #640
**Status**: Approved
**Date**: 2026-01-29

## Summary

Create an OpenClaw plugin that exposes Gobby's MCP tools to the Pi agent. The plugin connects to Gobby's HTTP endpoint (`http://localhost:60887/mcp`) and registers a meta-tool that provides access to all Gobby capabilities.

## Architecture

```
OpenClaw Pi Agent
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
~/Projects/openclaw/extensions/gobby/
├── openclaw.plugin.json  # Plugin manifest
├── index.ts              # Plugin registration
├── src/
│   ├── gobby-client.ts   # HTTP client for Gobby MCP
│   └── gobby-tool.ts     # Meta-tool implementation
```

### 1. Plugin Manifest (`openclaw.plugin.json`)

```json
{
  "name": "@openclaw/gobby",
  "version": "0.1.0",
  "description": "Gobby MCP integration for OpenClaw",
  "main": "index.ts",
  "optional": true,
  "sandbox": false
}
```

### 2. Plugin Entry Point (`index.ts`)

Follow the lobster plugin pattern:
- Register tool factory with `optional: true`
- Disable in sandboxed mode
- Pass plugin API (`OpenClawPluginApi`) to tool creator

### 3. Gobby Client (`src/gobby-client.ts`)

HTTP client wrapping Gobby's MCP endpoint:
- `status()` - Check daemon availability
- `listServers()` - List MCP servers
- `listTools(server)` - List tools with brief metadata
- `getToolSchema(server, tool)` - Get full schema
- `callTool(server, tool, args)` - Execute tool

Uses `fetch` to POST to `http://localhost:60887/mcp` with MCP JSON-RPC format.

### 4. Meta-Tool (`src/gobby-tool.ts`)

Single tool with action dispatch:

```typescript
{
  name: "gobby",
  description: "Access Gobby daemon tools...",
  parameters: Type.Object({
    action: Type.Union([
      Type.Literal("status"),
      Type.Literal("list_servers"),
      Type.Literal("list_tools"),
      Type.Literal("get_schema"),
      Type.Literal("call")
    ]),
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
| Security model | Trusted localhost | Daemon on localhost:60887 is a trusted local service |
| Schema validation | Lightweight at boundaries | Validate action enum; sanitize args keys before callTool |

## Security Considerations

### Trust Model

The Gobby daemon at `localhost:60887/mcp` is treated as a **trusted local service**:

- **Assumption**: Only the local user can access the daemon (no network exposure)
- **Risk**: If the daemon is compromised, an attacker gains full access to all Gobby tools (tasks, sessions, memory, workflows)
- **Mitigation**: The daemon binds to localhost only; no authentication is required for local-only access

### Schema Pass-Through

Using `Type.Unsafe()` for dynamic schema pass-through bypasses TypeBox validation:

- **Trade-off**: Flexibility vs. type safety—allows Gobby tools to define their own schemas without plugin updates
- **Recommendation**: Add lightweight validation at plugin boundaries:
  1. Validate `action` parameter against the known enum before dispatch
  2. Validate `server` and `tool` are non-empty strings when required
  3. Sanitize `args` keys (reject or escape special characters) before passing to `callTool`

### Input Sanitization

Arguments passed to `callTool` should be sanitized:

- **Keys**: Validate arg keys are alphanumeric with underscores (reject `__proto__`, `constructor`, etc.)
- **Values**: Pass values as-is to Gobby (Gobby's MCP tools handle their own validation)
- **Errors**: Return structured error responses; never expose internal stack traces

## Files to Create

1. **`~/Projects/openclaw/extensions/gobby/openclaw.plugin.json`**
   - Plugin manifest

2. **`~/Projects/openclaw/extensions/gobby/index.ts`**
   - Plugin entry, registers gobby tool

3. **`~/Projects/openclaw/extensions/gobby/src/gobby-client.ts`**
   - HTTP client for MCP endpoint

4. **`~/Projects/openclaw/extensions/gobby/src/gobby-tool.ts`**
   - Meta-tool with action dispatch

## Reference Files

- `~/Projects/openclaw/extensions/lobster/index.ts` - Plugin pattern
- `~/Projects/openclaw/extensions/lobster/src/lobster-tool.ts` - Tool structure
- `~/Projects/openclaw/src/plugins/types.ts` - OpenClawPluginApi types
- `~/Projects/gobby/src/gobby/mcp_proxy/server.py` - MCP interface

## Verification

1. Start Gobby daemon: `cd ~/Projects/gobby && uv run gobby start`
2. Build plugin: `cd ~/Projects/openclaw && bun run build`
3. Test via OpenClaw gateway:
   ```
   gobby action=status
   gobby action=list_servers
   gobby action=list_tools server=gobby
   gobby action=call server=gobby tool=list_mcp_servers
   ```
4. Verify error handling with daemon stopped

## Future Enhancements (Out of Scope)

- Direct tool wrappers for high-frequency tools
- Session correlation between OpenClaw and Gobby
- Bidirectional integration (OpenClaw channels in Gobby)
