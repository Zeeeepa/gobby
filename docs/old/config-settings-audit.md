# Config Settings Audit: Behavior vs Infrastructure

This document categorizes all settings in Gobby's configuration files as either:
- **INFRASTRUCTURE**: Require daemon restart to take effect
- **BEHAVIOR**: Can be changed at runtime (candidates for workflow variables)

## Files Reviewed

1. `src/gobby/install/shared/config/config.yaml` - Main daemon configuration
2. `.bmad/core/config.yaml` - BMAD tool config (not Gobby-related, minimal settings)

---

## INFRASTRUCTURE Settings (require daemon restart)

These settings affect process startup, port binding, or service initialization.

### Daemon Core

| Setting | Location | Description |
|---------|----------|-------------|
| `daemon_port` | config.yaml | HTTP server port binding |
| `daemon_health_check_interval` | config.yaml | Background health check interval |

### WebSocket Server

| Setting | Location | Description |
|---------|----------|-------------|
| `websocket.enabled` | config.yaml | Enable/disable WebSocket server |
| `websocket.port` | config.yaml | WebSocket port binding |
| `websocket.ping_interval` | config.yaml | Keep-alive ping interval |
| `websocket.ping_timeout` | config.yaml | Ping response timeout |

### Logging

| Setting | Location | Description |
|---------|----------|-------------|
| `logging.level` | config.yaml | Log level (debug/info/warn/error) |
| `logging.format` | config.yaml | Log format (text/json) |
| `logging.client` | config.yaml | Client log file path |
| `logging.client_error` | config.yaml | Error log file path |
| `logging.hook_manager` | config.yaml | Hook manager log path |
| `logging.mcp_server` | config.yaml | MCP server log path |
| `logging.mcp_client` | config.yaml | MCP client log path |
| `logging.max_size_mb` | config.yaml | Log rotation size |
| `logging.backup_count` | config.yaml | Number of log backups |

### MCP Client Proxy

| Setting | Location | Description |
|---------|----------|-------------|
| `mcp_client_proxy.enabled` | config.yaml | Enable MCP proxy |
| `mcp_client_proxy.connect_timeout` | config.yaml | Connection timeout |
| `mcp_client_proxy.proxy_timeout` | config.yaml | Proxy request timeout |
| `mcp_client_proxy.tool_timeout` | config.yaml | Default tool timeout |
| `mcp_client_proxy.tool_timeouts.*` | config.yaml | Per-tool timeout overrides |

### LLM Providers

| Setting | Location | Description |
|---------|----------|-------------|
| `llm_providers.*.models` | config.yaml | Available models per provider |
| `llm_providers.*.auth_mode` | config.yaml | Authentication method |

### Hook Extensions

| Setting | Location | Description |
|---------|----------|-------------|
| `hook_extensions.websocket.enabled` | config.yaml | WebSocket broadcast |
| `hook_extensions.websocket.broadcast_events` | config.yaml | Events to broadcast |
| `hook_extensions.plugins.enabled` | config.yaml | Plugin system enable |
| `hook_extensions.plugins.plugin_dirs` | config.yaml | Plugin search paths |
| `hook_extensions.plugins.auto_discover` | config.yaml | Auto-discover plugins |

### Background Services

| Setting | Location | Description |
|---------|----------|-------------|
| `message_tracking.enabled` | config.yaml | Message tracking service |
| `message_tracking.poll_interval` | config.yaml | Polling interval |
| `message_tracking.debounce_delay` | config.yaml | Debounce for updates |
| `session_lifecycle.active_session_pause_minutes` | config.yaml | Session pause timeout |
| `session_lifecycle.stale_session_timeout_hours` | config.yaml | Stale session cleanup |
| `session_lifecycle.expire_check_interval_minutes` | config.yaml | Cleanup check interval |

### Import MCP Server

| Setting | Location | Description |
|---------|----------|-------------|
| `import_mcp_server.enabled` | config.yaml | Enable MCP import |
| `import_mcp_server.provider` | config.yaml | LLM provider for import |
| `import_mcp_server.model` | config.yaml | Model for import |

### BMAD Config (.bmad/core/config.yaml)

| Setting | Location | Description |
|---------|----------|-------------|
| `user_name` | .bmad/core/config.yaml | User display name |
| `communication_language` | .bmad/core/config.yaml | Language setting |
| `document_output_language` | .bmad/core/config.yaml | Output language |
| `agent_sidecar_folder` | .bmad/core/config.yaml | BMAD memory folder |
| `output_folder` | .bmad/core/config.yaml | BMAD output folder |
| `install_user_docs` | .bmad/core/config.yaml | Install docs flag |

---

## BEHAVIOR Settings (runtime-changeable)

These settings control per-request or per-session behavior and are candidates for workflow variables.

### Task Expansion

| Setting | Current Location | Proposed Location | Description |
|---------|-----------------|-------------------|-------------|
| `gobby-tasks.expansion.enabled` | config.yaml | Workflow variable | Enable task expansion |
| `gobby-tasks.expansion.tdd_mode` | config.yaml | **Workflow variable** | Enable TDD test-implementation pairs |
| `gobby-tasks.expansion.max_subtasks` | config.yaml | Workflow variable | Max subtasks per expansion |
| `gobby-tasks.expansion.codebase_research_enabled` | config.yaml | Workflow variable | Enable codebase research |
| `gobby-tasks.expansion.web_research_enabled` | config.yaml | Workflow variable | Enable web research |
| `gobby-tasks.expansion.provider` | config.yaml | Keep in config | LLM provider |
| `gobby-tasks.expansion.model` | config.yaml | Keep in config | LLM model |

### Task Validation

| Setting | Current Location | Proposed Location | Description |
|---------|-----------------|-------------------|-------------|
| `gobby-tasks.validation.enabled` | config.yaml | Workflow variable | Enable validation |
| `gobby-tasks.validation.run_build_first` | config.yaml | Workflow variable | Run build before LLM validation |
| `gobby-tasks.validation.max_iterations` | config.yaml | Keep in config | Max validation attempts |
| `gobby-tasks.validation.max_consecutive_errors` | config.yaml | Keep in config | Max errors before stop |
| `gobby-tasks.validation.escalation_enabled` | config.yaml | Workflow variable | Enable escalation |
| `gobby-tasks.validation.use_external_validator` | config.yaml | Workflow variable | Use different LLM |
| `gobby-tasks.validation.provider` | config.yaml | Keep in config | LLM provider |
| `gobby-tasks.validation.model` | config.yaml | Keep in config | LLM model |

### Workflow

| Setting | Current Location | Proposed Location | Description |
|---------|-----------------|-------------------|-------------|
| `workflow.enabled` | config.yaml | Keep in config | Enable workflow engine |
| `workflow.timeout` | config.yaml | Keep in config | Execution timeout |
| `workflow.require_task_before_edit` | WorkflowConfig | **Workflow variable** | Require active task for edits |
| `workflow.protected_tools` | WorkflowConfig | Keep in config | Tools requiring active task |

### Session Features

| Setting | Current Location | Proposed Location | Description |
|---------|-----------------|-------------------|-------------|
| `compact_handoff.enabled` | config.yaml | Workflow variable | Enable compact handoff |
| `session_summary.enabled` | config.yaml | Workflow variable | Enable session summaries |
| `title_synthesis.enabled` | config.yaml | Keep in config | Enable title synthesis |
| `code_execution.enabled` | config.yaml | Keep in config | Enable code execution |
| `recommend_tools.enabled` | config.yaml | Keep in config | Enable tool recommendations |
| `tool_summarizer.enabled` | config.yaml | Keep in config | Enable tool summarization |
| `skills.enabled` | config.yaml | Keep in config | Enable skills system |

### Memory (from MemoryConfig in src/gobby/config/persistence.py)

| Setting | Current Location | Proposed Location | Description |
|---------|-----------------|-------------------|-------------|
| `memory.injection_limit` | MemoryConfig:34 | **Workflow variable** | Max memories to inject |
| `memory.importance_threshold` | MemoryConfig | Workflow variable | Min importance for injection |
| `memory.auto_extract` | MemoryConfig | Workflow variable | Auto-extract memories |

---

## Settings Specifically Required by Task

| Setting | Found | Location | Category |
|---------|-------|----------|----------|
| `require_task_before_edit` | Yes | `src/gobby/config/tasks.py:305` | BEHAVIOR |
| `tdd_mode` | Yes | `src/gobby/config/tasks.py:139` | BEHAVIOR |
| `memory_injection_enabled` | No* | N/A | N/A |
| `memory_injection_limit` | Yes | `src/gobby/config/persistence.py:34` | BEHAVIOR |

*Note: `memory_injection_enabled` does not exist as a named setting. Memory injection is controlled by the presence/absence of the `memory_inject` action in workflow YAML files (e.g., session-lifecycle.yaml).

---

## Recommendations

### Priority 1: Move to Workflow Variables

These settings should support workflow variable override (following the `auto_decompose` pattern):

1. **`tdd_mode`** - Allow disabling TDD pairs per session
2. **`require_task_before_edit`** - Per-session task enforcement
3. **`memory.injection_limit`** - Tune memory injection per context

### Priority 2: Consider for Workflow Variables

1. `validation.enabled` - Disable validation for research sessions
2. `compact_handoff.enabled` - Toggle handoff per session
3. `expansion.enabled` - Disable expansion temporarily

### Implementation Pattern

Follow the `auto_decompose` implementation in `src/gobby/storage/tasks.py`:

```python
# Priority: explicit parameter > workflow variable > config default
if auto_decompose is not None:
    effective_auto_decompose = auto_decompose
elif workflow_state and workflow_state.variables.get("auto_decompose") is not None:
    effective_auto_decompose = bool(workflow_state.variables.get("auto_decompose"))
else:
    effective_auto_decompose = True  # config default
```

---

## Summary

| Category | Count |
|----------|-------|
| Infrastructure settings | 35+ |
| Behavior settings | 15+ |
| Key workflow variable candidates | 3 (tdd_mode, require_task_before_edit, memory.injection_limit) |
