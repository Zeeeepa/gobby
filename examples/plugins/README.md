# Gobby Plugin Examples

This directory contains example plugins demonstrating the Gobby plugin system.

## Available Examples

### Code Guardian (`code_guardian.py`)

A code quality enforcement plugin that runs linters on file modifications.

**Features:**
- Pre-hook handlers to intercept Edit/Write tools
- Runs ruff and mypy checks on Python files
- Blocks writes that fail linting (configurable)
- Auto-fix with ruff (configurable)
- Workflow actions for manual linting
- Workflow conditions for quality gates

**Installation:**

1. Copy to your plugins directory:
   ```bash
   cp code_guardian.py ~/.gobby/plugins/
   ```

2. Enable in `~/.gobby/config.yaml`:
   ```yaml
   hook_extensions:
     plugins:
       enabled: true
       plugins:
         code-guardian:
           enabled: true
           config:
             checks: [ruff, mypy]
             block_on_error: true
             auto_fix: true
   ```

3. Restart the daemon:
   ```bash
   gobby stop && gobby start
   ```

## Creating Your Own Plugin

### Basic Structure

```python
from gobby.hooks.plugins import HookPlugin, hook_handler
from gobby.hooks.events import HookEvent, HookEventType, HookResponse

class MyPlugin(HookPlugin):
    name = "my-plugin"  # Required: unique identifier
    version = "1.0.0"
    description = "What my plugin does"

    def on_load(self, config: dict) -> None:
        """Initialize with config from YAML."""
        self.my_setting = config.get("my_setting", "default")

    def on_unload(self) -> None:
        """Cleanup resources."""
        pass

    @hook_handler(HookEventType.BEFORE_TOOL, priority=10)
    def check_tool(self, event: HookEvent) -> HookResponse | None:
        """Pre-handler: return HookResponse to block, None to allow."""
        if self._should_block(event):
            return HookResponse(decision="deny", reason="Blocked by MyPlugin")
        return None

    @hook_handler(HookEventType.AFTER_TOOL, priority=60)
    def observe_tool(self, event: HookEvent, core_response: HookResponse | None) -> None:
        """Post-handler: observe only, cannot block."""
        self.logger.info(f"Tool completed: {event.data.get('tool_name')}")
```

### Handler Priorities

- **Priority < 50**: Pre-handlers (run before core, can block)
- **Priority >= 50**: Post-handlers (run after core, observe only)

Lower priority values run first.

### Workflow Integration

Register actions and conditions in `on_load()`:

```python
def on_load(self, config: dict) -> None:
    # Actions are async functions
    self.register_action("my_action", self._action_handler)

    # Conditions are sync functions returning bool
    self.register_condition("is_ready", self._condition_checker)

async def _action_handler(self, context: dict, **kwargs) -> dict:
    """Called from workflow YAML: plugin:my-plugin:my_action"""
    return {"success": True}

def _condition_checker(self) -> bool:
    """Used in 'when' clauses: plugin_my_plugin_is_ready()"""
    return True
```

### Configuration

Plugin config goes in `~/.gobby/config.yaml`:

```yaml
hook_extensions:
  plugins:
    enabled: true
    plugin_dirs:
      - ~/.gobby/plugins
      - .gobby/plugins
    plugins:
      my-plugin:
        enabled: true
        config:
          my_setting: value
          another: 42
```

### Event Types

Available `HookEventType` values:
- `SESSION_START`, `SESSION_END`
- `BEFORE_AGENT`, `AFTER_AGENT`
- `BEFORE_TOOL`, `AFTER_TOOL`
- `BEFORE_TOOL_SELECTION` (Gemini only)

### Best Practices

1. **Fail-open**: Handle errors gracefully, don't crash the daemon
2. **Log sparingly**: Use `self.logger` with appropriate levels
3. **Respect timeouts**: Long operations should have timeouts
4. **Track state**: Use instance variables for cross-event state
5. **Validate config**: Check configuration in `on_load()`
