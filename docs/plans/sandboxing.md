# Sandbox Configuration Injection for Spawned Agents

## Summary

Add sandbox configuration injection to Gobby's agent spawning system, enabling spawned agents to run with each CLI's **built-in sandbox** enabled. Gobby just passes the right flags - the CLIs handle all sandbox setup themselves.

## Background

All three CLIs have **built-in sandboxing** (we just enable it via flags):

| CLI | Flag | Underlying Tech |
|-----|------|-----------------|
| **Claude Code** | `--sandbox` | Seatbelt (macOS) / bubblewrap (Linux) |
| **Codex** | `--sandbox workspace-write` | Seatbelt (macOS) / Landlock+seccomp (Linux) |
| **Gemini** | `--sandbox` or `GEMINI_SANDBOX=true` | Seatbelt (macOS) / Docker (Linux, auto-managed) |

**Key insight**: We don't create containers or manage sandboxes - the CLIs do that. We just pass flags and ensure:
1. Network access to `localhost:60887` (Gobby daemon) isn't blocked
2. Worktree paths are accessible for writes

This is **opt-in** - no sandbox by default (preserves current behavior).

## Implementation

### Phase 1: Data Models

**New file: `src/gobby/agents/sandbox.py`**

```python
class SandboxConfig(BaseModel):
    enabled: bool = False
    mode: Literal["permissive", "restrictive"] = "permissive"
    allow_network: bool = True
    extra_read_paths: list[str] = []
    extra_write_paths: list[str] = []

class ResolvedSandboxPaths(BaseModel):
    workspace_path: str
    gobby_daemon_port: int = 60887  # Default Gobby HTTP port
    read_paths: list[str]
    write_paths: list[str]
    allow_external_network: bool
```

**Update: `src/gobby/agents/definitions.py`**
- Add `sandbox: SandboxConfig | None = None` to `AgentDefinition`

### Phase 2: CLI-Specific Resolvers

**New file: `src/gobby/agents/sandbox_resolvers.py`**

| CLI | Args | Env Vars |
|-----|------|----------|
| Claude | `--sandbox`, `--allowed-path <path>` | - |
| Codex | `--sandbox workspace-write` | - |
| Gemini | `--sandbox` | `SEATBELT_PROFILE`, `SANDBOX_FLAGS` |

```python
def get_sandbox_resolver(provider: str) -> SandboxResolver
def compute_sandbox_paths(workspace_path, daemon_port, config) -> ResolvedSandboxPaths
```

### Phase 3: Spawn Integration

**Update: `src/gobby/agents/spawn.py`**
- Add `sandbox_args: list[str]` param to `build_cli_command()`

**Update: `src/gobby/agents/spawn_executor.py`**
- Add `sandbox_config`, `sandbox_args`, `sandbox_env` to `SpawnRequest`

**Update: `src/gobby/mcp_proxy/tools/spawn_agent.py`**
```python
async def spawn_agent(
    prompt: str,
    # ... existing params ...
    sandbox: bool = False,
    sandbox_mode: Literal["permissive", "restrictive"] = "permissive",
    sandbox_allow_network: bool = True,
    sandbox_extra_paths: list[str] | None = None,
) -> dict[str, Any]:
```

### Phase 4: Spawner Updates

Update each spawner to:
1. Accept `sandbox_config` parameter
2. Resolve sandbox paths using `compute_sandbox_paths()`
3. Get CLI-specific args/env from resolver
4. Pass to command builder and environment

Files:
- `src/gobby/agents/spawners/terminal.py`
- `src/gobby/agents/spawners/embedded.py`
- `src/gobby/agents/spawners/headless.py`

### Phase 5: Agent Definition Support

**Update: `src/gobby/install/shared/agents/generic.yaml`**
```yaml
sandbox: null  # disabled by default
```

**New: `src/gobby/install/shared/agents/sandboxed.yaml`**
```yaml
name: sandboxed
description: Agent that runs in an OS-level sandbox
sandbox:
  enabled: true
  mode: permissive
  allow_network: true
```

## File Changes

| File | Type | Description |
|------|------|-------------|
| `src/gobby/agents/sandbox.py` | NEW | SandboxConfig model |
| `src/gobby/agents/sandbox_resolvers.py` | NEW | CLI-specific resolvers |
| `src/gobby/agents/definitions.py` | MODIFY | Add sandbox field |
| `src/gobby/agents/spawn.py` | MODIFY | Add sandbox_args param |
| `src/gobby/agents/spawn_executor.py` | MODIFY | Add sandbox to SpawnRequest |
| `src/gobby/agents/spawners/*.py` | MODIFY | Handle sandbox config |
| `src/gobby/mcp_proxy/tools/spawn_agent.py` | MODIFY | Add sandbox params |
| `src/gobby/install/shared/agents/sandboxed.yaml` | NEW | Example agent |
| `tests/agents/test_sandbox*.py` | NEW | Unit tests |

## Usage Examples

### Via MCP tool
```python
spawn_agent(
    prompt="Fix the bug",
    sandbox=True,
    sandbox_mode="permissive"
)
```

### Via agent definition
```yaml
# .gobby/agents/secure-worker.yaml
name: secure-worker
sandbox:
  enabled: true
  mode: permissive
  allow_network: true
```

### Via workflow
```yaml
steps:
  - name: sandboxed_work
    on_enter:
      - action: spawn_agent
        agent: sandboxed
        prompt: "Complete the task"
```

## Verification

1. **Unit tests**: Test each resolver in isolation
2. **Integration tests**: Verify `build_cli_command` with sandbox args
3. **Manual E2E test**:
   ```bash
   # Spawn sandboxed agent
   gobby agent spawn --sandbox --prompt "echo test"

   # Verify:
   # - Agent can reach Gobby daemon at localhost:60887 (MCP calls work)
   # - Agent can write to workspace/worktree
   # - Agent cannot write to /etc (restrictive mode)
   ```

4. **Per-CLI verification**:
   - Claude Code: Check `/sandbox` command shows enabled
   - Codex: Verify `--sandbox workspace-write` in process args
   - Gemini: Verify `GEMINI_SANDBOX` env or Docker container running

## Sources

- [Claude Code Sandboxing](https://code.claude.com/docs/en/sandboxing)
- [Gemini CLI Sandbox](https://geminicli.com/docs/cli/sandbox/)
- [Codex Security](https://developers.openai.com/codex/security/)
