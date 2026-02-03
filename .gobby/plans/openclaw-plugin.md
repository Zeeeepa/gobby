# OpenClaw Gobby Plugin

## Overview

Create an OpenClaw plugin that exposes Gobby's MCP tools to the Pi agent via HTTP.

## Constraints

- Follow lobster plugin pattern (optional: true, sandbox-aware)
- Single meta-tool design (avoid 50+ tool bloat)
- HTTP transport to localhost:60887/mcp

## Phase 1: Plugin Setup

**Goal**: Create plugin structure and manifest.

**Tasks:**
- [ ] Create extensions/gobby directory structure (category: config)
- [ ] Create openclaw.plugin.json manifest (category: config)
- [ ] Create package.json with @openclaw/gobby name (category: config)

## Phase 2: HTTP Client

**Goal**: Implement Gobby MCP HTTP client.

**Tasks:**
- [ ] Create src/gobby-client.ts with GobbyClient class (category: code)
- [ ] Implement status() method for daemon health check (category: code)
- [ ] Implement listServers() method (category: code)
- [ ] Implement listTools(server) method (category: code)
- [ ] Implement getToolSchema(server, tool) method (category: code)
- [ ] Implement callTool(server, tool, args) method (category: code)

## Phase 3: Meta-Tool Implementation

**Goal**: Create the gobby meta-tool with action dispatch.

**Tasks:**
- [ ] Create src/gobby-tool.ts with tool definition (category: code)
- [ ] Implement action parameter with TypeBox union (category: code)
- [ ] Implement execute function with action dispatch (category: code)
- [ ] Add error handling for daemon unavailable (category: code)
- [ ] Add input sanitization for args keys (category: code)

## Phase 4: Plugin Registration

**Goal**: Register the plugin following OpenClaw patterns.

**Tasks:**
- [ ] Create index.ts with register function (category: code)
- [ ] Add sandbox check (disable in sandboxed mode) (category: code)
- [ ] Register gobby tool with optional: true (category: code)

## Phase 5: Documentation & Testing

**Goal**: Document and verify the plugin.

**Tasks:**
- [ ] Create README.md with usage instructions (category: docs)
- [ ] Test plugin via OpenClaw gateway (category: manual)
- [ ] Verify error handling with daemon stopped (category: manual)

## Task Mapping

<!-- Updated after task creation via /g expand -->
| Plan Item | Task Ref | Status |
|-----------|----------|--------|
