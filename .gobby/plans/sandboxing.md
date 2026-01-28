# Sandbox Configuration Injection for Spawned Agents

## Overview

Add sandbox configuration injection to Gobby's agent spawning system, enabling spawned agents to run with each CLI's **built-in sandbox** enabled. Gobby just passes the right flags - the CLIs handle all sandbox setup themselves.

**Key insight**: We don't create containers or manage sandboxes - the CLIs do that. We just pass flags and ensure:
1. Network access to `localhost:60887` (Gobby daemon) isn't blocked
2. Worktree paths are accessible for writes

This is **opt-in** - no sandbox by default (preserves current behavior).

## Constraints

- Must work with all three CLIs: Claude Code, Codex, Gemini
- Must not break existing spawn behavior (opt-in only)
- Must allow MCP communication to Gobby daemon
- Must allow filesystem access to worktree/workspace paths

## Phase 1: Data Models

**Goal**: Create Pydantic models for sandbox configuration

**Tasks:**
- [ ] Create SandboxConfig model in sandbox.py (category: code)
- [ ] Create ResolvedSandboxPaths model in sandbox.py (category: code)
- [ ] Add sandbox field to AgentDefinition (category: code, depends: Create SandboxConfig model)

## Phase 2: CLI-Specific Resolvers

**Goal**: Implement per-CLI sandbox flag/env resolution

**Tasks:**
- [ ] Create SandboxResolver base class (category: code)
- [ ] Implement ClaudeSandboxResolver (category: code, depends: Create SandboxResolver base class)
- [ ] Implement CodexSandboxResolver (category: code, depends: Create SandboxResolver base class)
- [ ] Implement GeminiSandboxResolver (category: code, depends: Create SandboxResolver base class)
- [ ] Create get_sandbox_resolver factory function (category: code, depends: Implement ClaudeSandboxResolver)
- [ ] Create compute_sandbox_paths helper (category: code)

## Phase 3: Spawn Integration

**Goal**: Wire sandbox config through the spawn pipeline

**Tasks:**
- [ ] Add sandbox_args param to build_cli_command (category: code, depends: Phase 2)
- [ ] Add sandbox fields to SpawnRequest dataclass (category: code, depends: Phase 2)
- [ ] Add sandbox params to spawn_agent MCP tool (category: code, depends: Add sandbox fields to SpawnRequest)
- [ ] Update TerminalSpawner to handle sandbox (category: code, depends: Add sandbox_args param to build_cli_command)
- [ ] Update EmbeddedSpawner to handle sandbox (category: code, depends: Add sandbox_args param to build_cli_command)
- [ ] Update HeadlessSpawner to handle sandbox (category: code, depends: Add sandbox_args param to build_cli_command)

## Phase 4: Agent Definition Support

**Goal**: Enable sandbox config in agent YAML definitions

**Tasks:**
- [ ] Update generic.yaml with sandbox: null (category: config, depends: Phase 1)
- [ ] Create sandboxed.yaml example agent (category: config, depends: Phase 1)

## Phase 5: Documentation & Testing

**Goal**: Ensure quality and document usage

**Tasks:**
- [ ] Add unit tests for SandboxConfig (category: test, depends: Phase 1)
- [ ] Add unit tests for sandbox resolvers (category: test, depends: Phase 2)
- [ ] Add integration tests for spawn with sandbox (category: test, depends: Phase 3)
- [ ] Update docs/guides with sandbox usage (category: docs, depends: Phase 4)

## Task Mapping

| Plan Item | Task Ref | Status |
|-----------|----------|--------|
| **Root Epic** | #6198 | open |
| **Phase 1: Data Models** | #6199 | open |
| Create SandboxConfig model | #6209 | open |
| Create ResolvedSandboxPaths model | #6210 | open |
| Add sandbox field to AgentDefinition | #6211 | open |
| **Phase 2: CLI-Specific Resolvers** | #6200 | open |
| Create SandboxResolver base class | #6216 | open |
| Implement ClaudeSandboxResolver | #6217 | open |
| Implement CodexSandboxResolver | #6218 | open |
| Implement GeminiSandboxResolver | #6219 | open |
| Create get_sandbox_resolver factory | #6220 | open |
| Create compute_sandbox_paths helper | #6221 | open |
| **Phase 3: Spawn Integration** | #6201 | open |
| Add sandbox_args to build_cli_command | #6227 | open |
| Add sandbox fields to SpawnRequest | #6228 | open |
| Add sandbox params to spawn_agent MCP | #6229 | open |
| Update TerminalSpawner | #6230 | open |
| Update EmbeddedSpawner | #6231 | open |
| Update HeadlessSpawner | #6232 | open |
| **Phase 4: Agent Definition Support** | #6202 | open |
| Update generic.yaml | #6236 | open |
| Create sandboxed.yaml | #6238 | open |
| **Phase 5: Documentation & Testing** | #6203 | open |
| Unit tests for SandboxConfig | #6244 | open |
| Unit tests for sandbox resolvers | #6245 | open |
| Integration tests for spawn | #6246 | open |
| Update docs/guides | #6247 | open |

## Sources

- [Claude Code Sandboxing](https://code.claude.com/docs/en/sandboxing)
- [Gemini CLI Sandbox](https://geminicli.com/docs/cli/sandbox/)
- [Codex Security](https://developers.openai.com/codex/security/)
