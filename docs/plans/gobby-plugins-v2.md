# gobby-plugins Internal MCP Server

## Overview

Create a `gobby-plugins` internal MCP server to expose plugin management functionality to agents. Plugins are runtime components that affect agent behavior (e.g., code-guardian blocks Edit/Write on lint failures), so agents need visibility and control.

## Motivation

### Current State
- Plugin tools (`list_plugins`, `reload_plugin`, `list_hook_handlers`, `test_hook_event`) are in top-level HTTP MCP server
- Not exposed via stdio (parity gap)
- Treated as "admin/debug" tools, but plugins are actually runtime

### Why Plugins Are Runtime
The `code-guardian` plugin demonstrates this:
- **BEFORE_TOOL hook**: Blocks Edit/Write if code fails linting
- **AFTER_TOOL hook**: Auto-fixes code after edits
- **Workflow actions**: `plugin:code-guardian:run_linter`
- **Workflow conditions**: `plugin_code_guardian_passes_lint()`

Agents need to:
1. Know what plugins are active (explains blocked tools)
2. Hot-reload plugins during sessions
3. Call plugin actions directly (not just via workflows)
4. Check plugin state/stats

## Proposed Tools

### Core Tools

| Tool | Description | Arguments |
|------|-------------|-----------|
| `list_plugins` | List loaded plugins with status/config | `enabled_only?: bool` |
| `get_plugin` | Get detailed plugin info | `name: str` |
| `reload_plugin` | Hot-reload a plugin | `name: str` |
| `enable_plugin` | Enable a disabled plugin | `name: str` |
| `disable_plugin` | Disable a plugin | `name: str` |

### Plugin Interaction Tools

| Tool | Description | Arguments |
|------|-------------|-----------|
| `call_plugin_action` | Call a registered plugin action | `plugin: str, action: str, args?: dict` |
| `list_plugin_actions` | List actions a plugin provides | `plugin: str` |
| `list_plugin_conditions` | List conditions a plugin provides | `plugin: str` |
| `get_plugin_stats` | Get plugin runtime stats | `plugin: str` |

### Hook Inspection Tools

| Tool | Description | Arguments |
|------|-------------|-----------|
| `list_hook_handlers` | List registered handlers by event type | `event_type?: str` |
| `test_hook_event` | Test hook event routing (debug) | `event_type: str, source?: str, data?: dict` |

## Architecture

### File Structure
```
src/gobby/mcp_proxy/tools/plugins/
├── __init__.py          # create_plugins_registry(), exports
├── core.py              # list_plugins, get_plugin, reload_plugin
├── interaction.py       # call_plugin_action, list_plugin_actions
└── hooks.py             # list_hook_handlers, test_hook_event
```

### Dependency Resolution

**Problem**: `hook_manager` is created after registries in HTTP server startup.

**Solution**: Lazy loading via callable resolver.

```python
def create_plugins_registry(
    hook_manager_resolver: Callable[[], HookManager | None] | None = None,
) -> InternalToolRegistry:
    """
    Create plugins registry with lazy hook_manager access.

    Args:
        hook_manager_resolver: Callable that returns HookManager when invoked.
                               Allows deferring hook_manager access until tool execution.
    """
    registry = InternalToolRegistry("gobby-plugins")

    def get_hook_manager() -> HookManager | None:
        if hook_manager_resolver:
            return hook_manager_resolver()
        return None

    # Register tools with get_hook_manager callback
    registry.register(list_plugins(get_hook_manager))
    # ...
```

### Registration in setup_internal_registries

```python
# In registries.py
def setup_internal_registries(
    config: DaemonConfig,
    session_manager: LocalSessionManager | None = None,
    memory_manager: MemoryManager | None = None,
    hook_manager_resolver: Callable[[], HookManager | None] | None = None,  # NEW
) -> InternalRegistryManager:
    # ...
    plugins_registry = create_plugins_registry(
        hook_manager_resolver=hook_manager_resolver,
    )
    manager.register(plugins_registry)
```

### HTTP Server Integration

```python
# In http.py, after hook_manager is created in lifespan
def _get_hook_manager() -> HookManager | None:
    return self._hook_manager

# Pass resolver to setup_internal_registries
self.services.internal_manager = setup_internal_registries(
    config=self.services.config,
    session_manager=self.services.session_manager,
    memory_manager=self.services.memory_manager,
    hook_manager_resolver=_get_hook_manager,
)
```

## Implementation Plan

### Phase 1: Core Registry Structure
1. Create `src/gobby/mcp_proxy/tools/plugins/` directory
2. Implement `create_plugins_registry()` with lazy loading
3. Move `list_plugins` and `reload_plugin` from server.py
4. Register in `setup_internal_registries()`

### Phase 2: Plugin Interaction Tools
1. Implement `call_plugin_action` - calls registered plugin actions
2. Implement `list_plugin_actions` - lists what a plugin provides
3. Implement `list_plugin_conditions` - lists workflow conditions
4. Implement `get_plugin_stats` - runtime statistics

### Phase 3: Hook Tools Migration
1. Move `list_hook_handlers` from server.py
2. Move `test_hook_event` from server.py
3. Update tests

### Phase 4: Cleanup
1. Remove tools from top-level server.py
2. Update documentation
3. Update instructions.py with gobby-plugins discovery

## Tool Specifications

### list_plugins

```python
async def list_plugins(enabled_only: bool = False) -> dict[str, Any]:
    """
    List loaded plugins with their status and configuration.

    Args:
        enabled_only: If true, only return enabled plugins

    Returns:
        {
            "success": true,
            "plugins": [
                {
                    "name": "code-guardian",
                    "version": "1.0.0",
                    "description": "Code quality guardian",
                    "enabled": true,
                    "actions": ["run_linter", "format_code"],
                    "conditions": ["passes_lint", "has_type_errors"],
                    "handlers": {
                        "BEFORE_TOOL": 1,
                        "AFTER_TOOL": 1
                    }
                }
            ],
            "total": 1,
            "enabled": 1
        }
    """
```

### call_plugin_action

```python
async def call_plugin_action(
    plugin: str,
    action: str,
    args: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Call a registered plugin action.

    This allows agents to invoke plugin functionality directly,
    without going through workflow YAML.

    Args:
        plugin: Plugin name (e.g., "code-guardian")
        action: Action name (e.g., "run_linter")
        args: Action arguments (e.g., {"files": ["src/main.py"]})
        context: Optional workflow-like context

    Returns:
        Action result dict (varies by action)

    Example:
        call_plugin_action("code-guardian", "run_linter", {"files": ["src/"]})
        # Returns: {"passed": true, "errors": [], "files_checked": 5}
    """
```

### get_plugin_stats

```python
async def get_plugin_stats(plugin: str) -> dict[str, Any]:
    """
    Get runtime statistics for a plugin.

    Useful for understanding plugin behavior during a session.

    Args:
        plugin: Plugin name

    Returns:
        {
            "success": true,
            "plugin": "code-guardian",
            "stats": {
                "files_checked": 42,
                "files_blocked": 3,
                "last_check_results": {...}
            }
        }
    """
```

## Testing Strategy

### Unit Tests
- `tests/mcp_proxy/tools/test_plugins.py`
- Mock `hook_manager` and `plugin_loader`
- Test each tool in isolation

### Integration Tests
- `tests/integration/test_plugins_registry.py`
- Test with real plugin loading
- Test lazy loading resolver pattern

### Migration Tests
- Verify existing tests in `test_server_coverage.py` still pass
- Tools should work identically, just from different location

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Lazy loading adds complexity | Well-documented resolver pattern |
| Breaking existing tool calls | Tools have same signatures |
| Plugin state access from tools | Plugins already expose stats via instance vars |
| Performance of lazy resolver | Resolver is O(1), just returns reference |

## Success Criteria

1. All plugin tools accessible via `call_tool("gobby-plugins", ...)`
2. Works via both HTTP and stdio (auto-proxied)
3. Lazy loading resolves circular dependency
4. Existing tests pass with minimal changes
5. Agents can discover and interact with plugins

## Related Tasks

- **#6900**: Move hook/plugin debug tools to CLI (SUPERSEDED by this plan)
- **#6899**: Migrate skills CLI sync operations (separate concern)
- **#6901**: Investigate stdio MCP parity (partially addressed)

## Timeline Estimate

| Phase | Effort |
|-------|--------|
| Phase 1: Core Registry | 2-3 hours |
| Phase 2: Interaction Tools | 2-3 hours |
| Phase 3: Hook Migration | 1-2 hours |
| Phase 4: Cleanup | 1 hour |
| **Total** | **6-9 hours** |
