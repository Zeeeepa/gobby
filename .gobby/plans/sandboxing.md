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

<!-- Updated after task creation -->
| Plan Item | Task Ref | Status |
|-----------|----------|--------|
| Create SandboxConfig model | | |
| Create ResolvedSandboxPaths model | | |
| Add sandbox field to AgentDefinition | | |
| Create SandboxResolver base class | | |
| Implement ClaudeSandboxResolver | | |
| Implement CodexSandboxResolver | | |
| Implement GeminiSandboxResolver | | |
| Create get_sandbox_resolver factory | | |
| Create compute_sandbox_paths helper | | |
| Add sandbox_args to build_cli_command | | |
| Add sandbox fields to SpawnRequest | | |
| Add sandbox params to spawn_agent MCP | | |
| Update TerminalSpawner | | |
| Update EmbeddedSpawner | | |
| Update HeadlessSpawner | | |
| Update generic.yaml | | |
| Create sandboxed.yaml | | |
| Unit tests for SandboxConfig | | |
| Unit tests for sandbox resolvers | | |
| Integration tests for spawn | | |
| Update docs/guides | | |

## Sources

- [Claude Code Sandboxing](https://code.claude.com/docs/en/sandboxing)
- [Gemini CLI Sandbox](https://geminicli.com/docs/cli/sandbox/)
- [Codex Security](https://developers.openai.com/codex/security/)
