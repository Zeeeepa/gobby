# Unified `spawn_agent` API Design

**Status**: Draft
**Date**: 2026-01-25
**Task**: #6079

## Overview

Consolidate three separate agent spawning tools into one unified `spawn_agent` API with an `isolation` parameter.

### Current State (Problems)

| Tool | Location | Issues |
|------|----------|--------|
| `start_agent` | `agents.py` | Naming inconsistent (`start` vs `spawn`) |
| `spawn_agent_in_worktree` | `worktrees.py` | ~200 lines duplicated spawner logic |
| `spawn_agent_in_clone` | `clones.py` | ~150 lines duplicated spawner logic |

### Target State

One tool: `spawn_agent(agent, isolation="current"|"worktree"|"clone", ...)`

---

## API Design

### Tool Signature

```python
async def spawn_agent(
    prompt: str,                   # Required - what the agent should do
    agent: str = "generic",        # Agent definition (defaults to generic)
    task_id: str | None = None,    # Link to task (supports N, #N, UUID)

    # Isolation
    isolation: Literal["current", "worktree", "clone"] | None = None,
    branch_name: str | None = None,  # Auto-generated from task title if not provided
    base_branch: str | None = None,

    # Execution
    workflow: str | None = None,
    mode: Literal["terminal", "embedded", "headless", "in_process"] | None = None,
    terminal: str = "auto",
    provider: str | None = None,
    model: str | None = None,

    # Limits
    timeout: float | None = None,
    max_turns: int | None = None,

    # Context
    parent_session_id: str | None = None,
    project_path: str | None = None,
) -> dict[str, Any]:
```

### Key Principles

1. **`prompt` is required** - describes what the agent should do
2. **`agent` defaults to `"generic"`** - uses `generic-agent.yaml` with `generic-workflow.yaml`
3. **All params override the agent definition** - tool params take precedence over YAML config
4. **Isolation options**:
   - `current` - work in current directory (main worktree)
   - `worktree` - create/reuse git worktree
   - `clone` - create full repository clone
5. **Branch auto-generation** - when `branch_name` not provided for worktree/clone, generate from task title (e.g., `task-6079-design-spawn-agent`)

---

## Agent Definition Schema

### Updated YAML Format

```yaml
# .gobby/agents/feature-developer.yaml
name: feature-developer
description: Agent that implements features in isolated worktrees

# Execution
model: claude-sonnet-4-20250514
mode: terminal
provider: claude

# Isolation (NEW)
isolation: worktree
branch_prefix: "feat/"
base_branch: main

# Workflow
workflow: tdd-workflow

# Variables
lifecycle_variables:
  can_spawn_children: false
default_variables:
  focus_mode: true

# Limits
timeout: 300.0
max_turns: 20
```

### Updated Model

```python
# src/gobby/agents/definitions.py

class AgentDefinition(BaseModel):
    name: str
    description: str | None = None

    # Execution
    model: str | None = None
    mode: str = "headless"
    provider: str = "claude"

    # Isolation (NEW)
    isolation: Literal["current", "worktree", "clone"] | None = None
    branch_prefix: str | None = None
    base_branch: str = "main"

    # Workflow
    workflow: str | None = None

    # Variables
    lifecycle_variables: dict[str, Any] = Field(default_factory=dict)
    default_variables: dict[str, Any] = Field(default_factory=dict)

    # Limits
    timeout: float = 120.0
    max_turns: int = 10
```

---

## Implementation Architecture

### New Modules

```
src/gobby/
├── agents/
│   ├── isolation.py          # NEW - Isolation handlers
│   └── spawn_executor.py     # NEW - Shared spawn logic
└── mcp_proxy/tools/
    └── spawn_agent.py        # NEW - Unified tool
```

### Isolation Handlers

```python
# src/gobby/agents/isolation.py

class IsolationHandler(ABC):
    @abstractmethod
    async def prepare_environment(self, config: SpawnConfig) -> IsolationContext:
        """Prepare isolated environment."""
        pass

    @abstractmethod
    def build_context_prompt(self, config: SpawnConfig, ctx: IsolationContext) -> str:
        """Build environment-aware prompt."""
        pass


class CurrentIsolationHandler(IsolationHandler):
    """No isolation - work in current directory."""
    pass


class WorktreeIsolationHandler(IsolationHandler):
    """Create/reuse git worktree."""
    # Extract from spawn_agent_in_worktree (worktrees.py:932-1268)
    pass


class CloneIsolationHandler(IsolationHandler):
    """Create shallow clone."""
    # Extract from spawn_agent_in_clone (clones.py:522-901)
    pass
```

### Spawn Executor

```python
# src/gobby/agents/spawn_executor.py

async def execute_spawn(
    runner: AgentRunner,
    config: AgentConfig,
    mode: str,
    terminal: str,
    cwd: str,
    enhanced_prompt: str,
    running_registry: RunningAgentRegistry,
) -> dict[str, Any]:
    """
    Execute agent spawn - consolidates duplicated logic from
    agents.py, worktrees.py, and clones.py.
    """
    pass
```

### Unified Tool Flow

```python
# src/gobby/mcp_proxy/tools/spawn_agent.py

async def spawn_agent(prompt: str, agent: str = "generic", ...) -> dict[str, Any]:
    # 1. Load agent definition (defaults to "generic")
    agent_def = agent_loader.load(agent)
    if not agent_def:
        return {"success": False, "error": f"Agent '{agent}' not found"}

    # 2. Merge config: agent_def defaults < tool params
    config = _merge_config(agent_def, tool_params)

    # 3. Resolve task_id if provided (supports N, #N, UUID)
    if task_id:
        config.task_id = resolve_task_id_for_mcp(task_manager, task_id)

    # 4. Auto-generate branch_name from task if needed
    if config.isolation in ("worktree", "clone") and not branch_name:
        if config.task_id:
            task = task_manager.get_task(config.task_id)
            config.branch_name = slugify(f"task-{task.seq_num}-{task.title}")
        else:
            config.branch_name = f"{config.branch_prefix or 'agent/'}{timestamp()}"

    # 5. Get isolation handler
    handler = get_isolation_handler(config.isolation or "current")

    # 6. Prepare environment
    context = await handler.prepare_environment(config)

    # 7. Build enhanced prompt
    enhanced_prompt = handler.build_context_prompt(prompt, context)

    # 8. Execute spawn
    return await execute_spawn(runner, config, context.cwd, enhanced_prompt)
```

---

## Migration Strategy

### Phase 1: Add Unified Tool (Non-Breaking)

1. Create `spawn_agent` tool
2. Add `isolation` field to `AgentDefinition`
3. Extract shared logic into isolation handlers
4. Register alongside existing tools

### Phase 2: Deprecation Notices

1. Add deprecation warnings to old tools
2. Update documentation
3. Update workflow examples

### Phase 3: Remove Deprecated Tools

1. Remove `start_agent`, `spawn_agent_in_worktree`, `spawn_agent_in_clone`
2. Update all internal references

---

## Files to Modify

| File | Change |
|------|--------|
| `src/gobby/agents/definitions.py` | Add `isolation`, `branch_prefix`, `base_branch`, `provider` |
| `src/gobby/agents/isolation.py` | **NEW** - Isolation handlers |
| `src/gobby/agents/spawn_executor.py` | **NEW** - Shared spawn logic |
| `src/gobby/mcp_proxy/tools/spawn_agent.py` | **NEW** - Unified tool |
| `src/gobby/mcp_proxy/tools/agents.py` | Deprecation warning |
| `src/gobby/mcp_proxy/tools/worktrees.py` | Deprecation warning |
| `src/gobby/mcp_proxy/tools/clones.py` | Deprecation warning |
| `src/gobby/mcp_proxy/server.py` | Register new tool |
| `src/gobby/install/shared/agents/generic.yaml` | **NEW** - Default agent definition |
| `src/gobby/install/shared/workflows/generic.yaml` | **NEW** - Default workflow |

---

## Test Requirements

### Unit Tests

`tests/mcp_proxy/tools/test_spawn_agent.py`:
- Default agent loading (`agent="generic"`)
- Config merging (agent defaults vs tool params)
- Isolation mode dispatch
- task_id resolution (N, #N, UUID formats)
- Branch auto-generation from task title
- Branch fallback to prefix + timestamp when no task

### Isolation Handler Tests

`tests/agents/test_isolation.py`:
- `CurrentIsolationHandler` - no-op prep
- `WorktreeIsolationHandler` - worktree creation, hooks
- `CloneIsolationHandler` - shallow clone
- Context prompt building

### Integration Tests

`tests/integration/test_spawn_agent_unified.py`:
- Full spawn flow per isolation mode
- Real git operations
- Workflow activation

---

## Verification

1. **Unit tests pass**: `uv run pytest tests/agents/test_isolation.py tests/mcp_proxy/tools/test_spawn_agent.py -v`
2. **Manual test**: Create agent definition, spawn with each isolation mode
3. **Deprecation works**: Old tools emit warnings but still function
4. **Task ID resolution**: Test with `#N`, `N`, and UUID formats

---

## Design Decisions

1. **Anonymous spawning**: ✅ Supported - `agent` defaults to `"generic"`, which uses `generic-agent.yaml` + `generic-workflow.yaml`
2. **Branch auto-generation**: ✅ From task title - e.g., `task-6079-design-spawn-agent` (falls back to `branch_prefix + timestamp` if no task)
3. **`in_process` mode for isolation**: TBD - currently only in `start_agent`, may add later if needed
