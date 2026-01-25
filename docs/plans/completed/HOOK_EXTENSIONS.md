# Hook Extensions Plan

## Vision

Transform Gobby's hook system from passive observation into an **extensible platform** where developers can customize behavior through WebSocket subscriptions, webhook callbacks, and Python plugins.

Key insight: **Hooks are already the nervous system of Gobby** - every CLI interaction flows through them. By exposing these events to external consumers and allowing custom handlers, we enable infinite customization without modifying core code.

Inspired by:
- [Claude Code Hooks](https://docs.anthropic.com/en/docs/claude-code/hooks) - Event-driven customization
- [Zapier Webhooks](https://zapier.com/help/doc/how-get-started-webhooks-zapier) - External service integration
- [pytest plugins](https://docs.pytest.org/en/stable/how-to/writing_plugins.html) - Python plugin architecture

## Current State

Gobby's hook system currently provides:
- **Unified event model**: `HookEvent` dataclass with 14 event types across 3 CLIs
- **Response control**: `HookResponse` with `allow/deny/ask` decisions and context injection
- **Session tracking**: Auto-registration, status updates, summary generation
- **WebSocket infrastructure**: `broadcast()` method exists but unused by hooks

What's missing:
- No way for external services to subscribe to hook events
- No webhook callouts to external URLs
- No plugin system for custom Python handlers

## Proposed Extensions

### 1. WebSocket Event Broadcasting
Real-time event streaming to connected WebSocket clients.

### 2. Config-Driven Webhooks
HTTP callouts to external services on hook events.

### 3. Python Plugin System
Dynamically loaded Python modules that can intercept and modify hook behavior.

---

## Core Design Principles

1. **Fail-open** - Extensions never block hook execution on failure
2. **Async-first** - All extensions run asynchronously to avoid latency
3. **Config-driven** - Enable/disable via `~/.gobby/config.yaml`
4. **Progressive disclosure** - Simple use cases first, advanced later
5. **Security-conscious** - Plugins require explicit enablement

---

## Architecture

### Enhanced Hook Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                      CLI Invocation                              │
│              (Claude Code / Gemini / Codex)                      │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Hook Dispatcher                                │
│              POST /hooks/execute                                 │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                     HookManager.handle()                         │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │  Pre-Plugins    │  │  Core Handler   │  │  Post-Plugins   │  │
│  │  (can block)    │→ │  (existing)     │→ │  (observe only) │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
└─────────────────────────┬───────────────────────────────────────┘
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
┌─────────────────┐ ┌───────────────┐ ┌─────────────────┐
│   WebSocket     │ │   Webhooks    │ │   CLI Response  │
│   Broadcast     │ │   (async)     │ │                 │
└─────────────────┘ └───────────────┘ └─────────────────┘
```

### New Components

| Component | Location | Purpose |
|-----------|----------|---------|
| `HookEventBroadcaster` | `src/hooks/broadcaster.py` | WebSocket event streaming |
| `WebhookDispatcher` | `src/hooks/webhooks.py` | HTTP callouts to external URLs |
| `PluginLoader` | `src/hooks/plugins.py` | Dynamic Python plugin loading |
| `PluginRegistry` | `src/hooks/plugins.py` | Plugin lifecycle management |

### Configuration Schema

```yaml
# ~/.gobby/config.yaml

hook_extensions:
  # WebSocket broadcasting
  websocket:
    enabled: true
    broadcast_events:
      - session_start
      - session_end
      - before_tool
      - after_tool
    include_payload: true  # Include event.data in broadcast

  # Webhook callouts
  webhooks:
    enabled: false
    endpoints:
      - url: "https://example.com/hook"
        events: ["session_start", "session_end"]
        headers:
          Authorization: "Bearer ${WEBHOOK_TOKEN}"
        timeout: 5
        retry_count: 2
        can_block: false  # If true, webhook can return deny decision

  # Python plugins
  plugins:
    enabled: false
    plugin_dirs:
      - "~/.gobby/plugins"
      - ".gobby/plugins"  # Project-specific
    auto_discover: true
    plugins:
      my_plugin:
        enabled: true
        config:
          custom_key: "value"
```

---

## Feature Details

### 1. WebSocket Event Broadcasting

**Problem**: External tools (dashboards, IDEs, monitoring) can't observe hook events in real-time.

**Solution**: Broadcast hook events to all connected WebSocket clients.

**Event Format**:
```json
{
  "type": "hook_event",
  "event_type": "before_tool",
  "session_id": "sess-abc123",
  "source": "claude",
  "timestamp": "2025-01-15T10:30:00Z",
  "data": {
    "tool_name": "Edit",
    "tool_input": {"file_path": "/src/main.py", "...": "..."}
  },
  "response": {
    "decision": "allow"
  }
}
```

**Integration**:
- `GobbyRunner` passes WebSocket server reference to HTTP server
- `execute_hook` endpoint broadcasts after handler returns
- Configurable event filtering via `broadcast_events` list

**Client Subscription Example**:
```javascript
const ws = new WebSocket('ws://localhost:60335');
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.type === 'hook_event') {
    console.log(`[${data.event_type}] ${data.session_id}`);
  }
};
```

---

### 2. Config-Driven Webhooks

**Problem**: No way to notify external services (Slack, PagerDuty, custom APIs) of hook events.

**Solution**: HTTP POST to configured URLs on specified events.

**Webhook Payload**:
```json
{
  "event": "before_tool",
  "timestamp": "2025-01-15T10:30:00Z",
  "session_id": "sess-abc123",
  "source": "claude",
  "project_id": "proj-xyz",
  "machine_id": "mac-123",
  "data": {
    "tool_name": "Bash",
    "tool_input": {"command": "rm -rf /tmp/test"}
  }
}
```

**Blocking Webhooks** (optional):
```json
// Webhook response that blocks the action
{
  "decision": "deny",
  "reason": "Destructive command blocked by policy server"
}
```

**Retry Logic**:
- Exponential backoff: 1s, 2s, 4s
- Max retries configurable per endpoint
- Failures logged but never block hook execution (unless `can_block: true`)

**Workflow Integration**:
Webhooks become a workflow action type:
```yaml
# In workflow YAML
on_enter:
  - action: webhook
    url: "{{ config.policy_server }}"
    event: "phase_entered"
    can_block: true
```

---

### 3. Python Plugin System

**Problem**: Some customizations require code logic that can't be expressed in config.

**Solution**: Dynamically load Python modules that register hook handlers.

**Plugin Interface**:
```python
# ~/.gobby/plugins/my_policy.py
from gobby.hooks.plugins import HookPlugin, hook_handler
from gobby.hooks.events import HookEvent, HookResponse, HookEventType

class MyPolicyPlugin(HookPlugin):
    """Custom policy enforcement plugin."""

    name = "my_policy"
    version = "1.0.0"

    def on_load(self, config: dict) -> None:
        """Called when plugin is loaded."""
        self.blocked_commands = config.get("blocked_commands", [])

    @hook_handler(HookEventType.BEFORE_TOOL, priority=10)
    def check_bash_command(self, event: HookEvent) -> HookResponse | None:
        """Block dangerous bash commands."""
        if event.data.get("tool_name") != "Bash":
            return None  # Continue to next handler

        command = event.data.get("tool_input", {}).get("command", "")
        for blocked in self.blocked_commands:
            if blocked in command:
                return HookResponse(
                    decision="deny",
                    reason=f"Command contains blocked pattern: {blocked}"
                )
        return None  # Allow

    @hook_handler(HookEventType.SESSION_START)
    def log_session_start(self, event: HookEvent) -> None:
        """Observe-only handler (no return = allow)."""
        self.logger.info(f"Session started: {event.session_id}")
```

**Plugin Discovery**:
1. Scan `plugin_dirs` for `.py` files
2. Import modules and find `HookPlugin` subclasses
3. Instantiate and call `on_load()` with plugin config
4. Register handlers by event type and priority

**Handler Priorities**:
- Lower number = earlier execution
- Priority 0-49: Pre-handlers (can block)
- Priority 50: Core handler (existing HookManager)
- Priority 51-100: Post-handlers (observe only)

**Security Model**:
- Plugins disabled by default (`plugins.enabled: false`)
- Each plugin must be explicitly enabled in config
- Plugin errors logged but don't crash daemon
- Sandboxing: Future enhancement (restricted imports)

---

## Storage Schema

### Webhook Delivery Log (Optional)

```sql
CREATE TABLE webhook_deliveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    endpoint_url TEXT NOT NULL,
    event_type TEXT NOT NULL,
    session_id TEXT,
    payload TEXT NOT NULL,          -- JSON
    status_code INTEGER,
    response_body TEXT,
    delivered_at TIMESTAMP,
    retry_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_webhook_deliveries_endpoint ON webhook_deliveries(endpoint_url);
CREATE INDEX idx_webhook_deliveries_event ON webhook_deliveries(event_type);
```

---

## Implementation Checklist

### Phase 1: WebSocket Event Broadcasting ✅ COMPLETE

#### Infrastructure Setup
- [x] Add `websocket_server` reference to HTTPServer class (`src/servers/http.py`)
- [x] Modify `GobbyRunner` to pass WebSocket server to HTTP server after init
- [x] Create `src/hooks/broadcaster.py` module

#### Broadcaster Implementation
- [x] Create `HookEventBroadcaster` class
- [x] Implement `broadcast_hook_event(event: HookEvent, response: HookResponse)` method
- [x] Implement event filtering based on config `broadcast_events` list
- [x] Implement payload sanitization (remove sensitive data option)
- [x] Add `include_payload` config option

#### Client Subscription (Decision 3)
- [x] Define subscription message format: `{"type": "subscribe", "events": ["session_start", ...]}`
- [x] Add `subscriptions` dict to WebSocket connection state
- [x] Filter broadcasts based on client subscriptions (default: all events)
- [x] Add `{"type": "unsubscribe", "events": [...]}` support
- [x] Document subscription protocol in WebSocket event schema docs

#### Configuration
- [x] Add `HookExtensionsConfig` to `src/config/app.py`
- [x] Add `WebSocketBroadcastConfig` sub-config
- [x] Add default config values

#### Integration
- [x] Call broadcaster in `/hooks/execute` endpoint after handler returns
- [x] Add broadcast to `HookManager.handle()` for direct calls
- [x] Handle broadcast errors gracefully (log, don't fail)

#### Testing
- [x] Unit tests for `HookEventBroadcaster` (tests/hooks/test_broadcaster.py)
- [x] Integration test: WebSocket client receives hook events
- [x] Test event filtering
- [x] Test error handling when no clients connected

---

### Phase 2: Config-Driven Webhooks ✅ COMPLETE

#### Core Implementation
- [x] Create `src/hooks/webhooks.py` module
- [x] Create `WebhookDispatcher` class
- [x] Implement `trigger(event_type, event, response)` async method
- [x] Implement endpoint matching by event type
- [x] Implement HTTP POST with configurable headers

#### Retry Logic
- [x] Implement exponential backoff retry
- [x] Add `timeout` per endpoint
- [x] Add `retry_count` per endpoint
- [x] Log failures with context

#### Blocking Webhooks
- [x] Implement `can_block` option
- [x] Parse webhook response for `decision` field
- [x] Return `HookResponse` from blocking webhook
- [x] Add timeout protection for blocking webhooks

#### Configuration
- [x] Add `WebhooksConfig` to `src/config/app.py`
- [x] Add `WebhookEndpointConfig` for endpoint definitions
- [x] Support environment variable substitution in headers (`${VAR}`)
- [x] Validate webhook URLs on config load

#### Integration
- [x] Initialize `WebhookDispatcher` in HTTP server lifespan
- [x] Call dispatcher in `/hooks/execute` endpoint
- [x] Add webhook delivery logging (optional, if table created)

#### Fire-and-Forget Delivery (Decision 4)
- [x] Implement async webhook dispatch (no blocking on response)
- [x] Add `log_deliveries: true/false` config option (default: false)
- [x] Document that webhook reliability is the endpoint's responsibility

#### Testing
- [x] Unit tests for `WebhookDispatcher` (tests/hooks/test_webhooks.py)
- [x] Integration test with mock webhook server
- [x] Test retry logic
- [x] Test blocking webhook flow
- [x] Test environment variable substitution

---

### Phase 3: Python Plugin System ✅ COMPLETE

#### Plugin Infrastructure
- [x] Create `src/hooks/plugins.py` module
- [x] Define `HookPlugin` base class with `name`, `version`, `on_load()`, `on_unload()`
- [x] Define `@hook_handler` decorator with `event_type` and `priority` params
- [x] Create `PluginLoader` class for discovery and loading
- [x] Create `PluginRegistry` for handler registration

#### Plugin Discovery
- [x] Implement `discover_plugins(dirs: list[str])` method
- [x] Scan directories for `.py` files
- [x] Import modules dynamically
- [x] Find `HookPlugin` subclasses
- [x] Handle import errors gracefully

#### Plugin Lifecycle
- [x] Implement `load_plugin(path, config)` method
- [x] Call `on_load()` with plugin-specific config
- [x] Register handlers by event type
- [x] Implement `unload_plugin(name)` method
- [x] Call `on_unload()` on daemon shutdown

#### Handler Execution
- [x] Implement `execute_handlers(event_type, event)` method
- [x] Sort handlers by priority
- [x] Execute pre-handlers (priority < 50) before core handler
- [x] Execute post-handlers (priority >= 50) after core handler
- [x] Short-circuit on `deny` response from pre-handler
- [x] Pass handler errors to logger, don't fail

#### Configuration
- [x] Add `PluginsConfig` to `src/config/app.py`
- [x] Add `plugin_dirs` list
- [x] Add `plugins` dict for per-plugin config and enablement
- [x] Add `auto_discover` boolean

#### Integration
- [x] Initialize `PluginLoader` in HTTP server lifespan
- [x] Inject `PluginRegistry` into `HookManager`
- [x] Modify `HookManager.handle()` to call plugin handlers
- [x] Add plugin status to `/admin/status` endpoint

#### Testing
- [x] Unit tests for `PluginLoader` (tests/hooks/test_plugins.py)
- [x] Unit tests for `PluginRegistry`
- [x] Integration test with sample plugin
- [x] Test priority ordering
- [x] Test deny short-circuit
- [x] Test plugin error isolation

---

### Phase 4: Workflow Integration ✅ COMPLETE

#### Webhook as Workflow Action
- [x] Add `webhook` action type to workflow engine
- [x] Implement `WebhookAction` class in `src/workflows/webhook.py`
- [x] Support `url`, `event`, `can_block`, `headers` params
- [x] Integrate with existing webhook infrastructure

#### Plugin-Defined Actions
- [x] Allow plugins to register custom workflow actions
- [x] Add `register_action(name, handler)` to plugin interface
- [x] Expose registered actions to workflow engine

#### Plugin-Defined Conditions
- [x] Allow plugins to register custom condition evaluators
- [x] Add `register_condition(name, evaluator)` to plugin interface
- [x] Expose registered conditions for workflow `when` clauses

#### Documentation
- [x] Document webhook action YAML syntax (docs/guides/webhooks-and-plugins.md)
- [x] Document plugin action registration
- [x] Add examples to workflow templates

---

### Phase 5: CLI & Monitoring ✅ COMPLETE

#### CLI Commands
- [x] Add `gobby hooks` command group (src/gobby/cli/extensions.py)
- [x] Implement `gobby hooks list` - show registered handlers
- [x] Implement `gobby hooks test <event>` - trigger test event
- [x] Implement `gobby plugins list` - show loaded plugins
- [x] Implement `gobby plugins reload [plugin_name]` - reload all or specific plugin
- [x] Implement `gobby webhooks list` - show configured webhooks
- [x] Implement `gobby webhooks test <endpoint>` - test webhook delivery

#### Stateless Plugin Reload (Decision 5)
- [x] Call `on_unload()` on existing plugin instances before reload
- [x] Re-import modules and re-instantiate plugins
- [x] Clear and re-register all handlers from reloaded plugins
- [x] Document that reload clears plugin state (pytest model)

#### MCP Tools
- [x] Add `list_hook_handlers()` MCP tool (src/gobby/mcp_proxy/server.py:301)
- [x] Add `test_hook_event(event_type, data)` MCP tool (server.py:355)
- [x] Add `list_plugins()` MCP tool (server.py:434)
- [x] Add `reload_plugin()` MCP tool (server.py:473)

#### Observability
- [x] Add hook event metrics (count by type) - src/gobby/utils/metrics.py
- [x] Add webhook delivery metrics (success/failure rate)
- [x] Add plugin handler metrics (execution time)
- [x] Expose metrics via `/admin/metrics` endpoint

---

### Phase 6: Documentation ✅ COMPLETE

- [x] Update CLAUDE.md with hook extension configuration (minimal reference at line 193)
- [x] Create `docs/guides/webhooks-and-plugins.md` user guide (725 lines)
- [x] Document WebSocket event schema (including subscription protocol)
- [x] Document webhook payload format
- [x] Document plugin interface

#### Plugin Security Model (Decision 2)
- [x] Add "Security Model" section explaining trust model
- [x] Document: "Plugins run with full daemon privileges. Only enable plugins you trust."
- [x] Add warning message when enabling plugins via config
- [x] Consider `--i-trust-this-plugin` flag for explicit acknowledgment (deferred - documented in guide)

#### Examples
- [x] Add example plugins to `examples/plugins/`
- [x] Add example webhook integration (Slack notification in webhooks-and-plugins.md)
- [x] Add "Code Guardian" example plugin (`examples/plugins/code_guardian.py`) demonstrating:
  - Hook handlers for `PRE_TOOL_CALL` and `POST_TOOL_CALL`
  - Event blocking and content modification
  - Context injection for reporting
  - `register_action()` for workflow actions (`run_linter`, `format_code`)
  - `register_condition()` for workflow conditions (`passes_lint`, `has_type_errors`)
  - Per-plugin configuration (`checks`, `block_on_error`, `auto_fix`)

---

## Decisions

| # | Question | Decision | Rationale |
|---|----------|----------|-----------|
| 1 | **Webhook authentication** | Header-based auth only for v1 | Covers 90% of use cases (Slack, Discord, PagerDuty). Add OAuth/signed payloads later if needed. |
| 2 | **Plugin sandboxing** | Defer - use trust model via documentation | Plugins disabled by default, require explicit enablement. Document: "Plugins run with full daemon privileges. Only enable plugins you trust." |
| 3 | **WebSocket client filtering** | Yes - add client-side subscription | Low-cost, high-value. Clients send `{"subscribe": ["session_start", "tool_call"]}` after connection. |
| 4 | **Webhook delivery guarantees** | Fire-and-forget with optional logging | Delivery logging table already planned. For guaranteed delivery, users can put a queue behind their endpoint. |
| 5 | **Plugin hot-reload** | Yes, stateless reload via CLI | Allow `gobby plugins reload` but document that plugin state is lost. This is the pytest model. |

---

## Future Enhancements

- **Plugin marketplace** - Share plugins via registry
- **Webhook templates** - Pre-built integrations (Slack, Discord, PagerDuty)
- **Event replay** - Replay historical events through webhooks
- **Plugin dependencies** - Plugins that depend on other plugins
- **Conditional broadcasting** - WebSocket clients specify event filters
- **Webhook batching** - Aggregate events into periodic batch calls
- **Plugin metrics dashboard** - Visualize plugin performance
