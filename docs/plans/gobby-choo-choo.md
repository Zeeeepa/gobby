# Plan: Task Commands, Gobby the Task Goblin, Inter-Agent Communication, and OpenTelemetry

## Summary

Four features requested:
1. **Task Type Commands** - Quick slash commands for creating tasks by type
2. **Gobby the Task Goblin** - Persistent LLM loop for task orchestration and monitoring
3. **Inter-Agent Communication** - Messaging between parent/child agents in worktrees
4. **OpenTelemetry Integration** - Distributed tracing, metrics, and observability

---

## Feature 1: Task Type Commands

### Goal
Create slash commands in `.claude/commands/` for quickly creating tasks of specific types.

### Commands to Create
| Command | Task Type | Notes |
|---------|-----------|-------|
| `/bug` | bug | Bug/defect task |
| `/feat` | feature | New feature task |
| `/nit` | chore | Nitpick with label |
| `/ref` | chore | Refactoring with label |
| `/epic` | epic | Parent container task |
| `/chore` | chore | Maintenance/cleanup |

### File Structure
```
.claude/commands/
├── bug.md       # /bug <title> [description]
├── feat.md      # /feat <title> [description]
├── nit.md       # /nit <title> [description] (type=chore, label=nitpick)
├── ref.md       # /ref <title> [description] (type=chore, label=refactor)
├── epic.md      # /epic <title> [description]
└── chore.md     # /chore <title> [description]
```

### Implementation
Each command file calls `gobby-tasks.create_task` with appropriate `task_type` and labels.

---

## Feature 2: Gobby the Task Goblin

### Concept
A persistent Python LLM loop that monitors tasks, checks agent health, tracks tokens, and speaks in haiku. A friendly daemon that keeps the task system tidy.

### Architecture

```
                    ┌─────────────────────────────────┐
                    │     Gobby the Task Goblin       │
                    │     (Persistent LLM Loop)       │
                    └─────────────────────────────────┘
                                   │
        ┌──────────────────────────┼──────────────────────────┐
        │                          │                          │
        ▼                          ▼                          ▼
┌───────────────┐      ┌───────────────────┐      ┌───────────────────┐
│ Task Monitor  │      │  Agent Watcher    │      │  Token Tracker    │
│ • Stale tasks │      │ • Stuck agents    │      │ • Usage per sess  │
│ • Orphans     │      │ • Depth limits    │      │ • Budget alerts   │
│ • Blockers    │      │ • Health checks   │      │ • Cost estimates  │
└───────────────┘      └───────────────────┘      └───────────────────┘
        │                          │                          │
        └──────────────────────────┼──────────────────────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    │        Alert System         │
                    │ • Log to goblin.log         │
                    │ • Desktop notifications     │
                    │ • callme → USER (you!)      │
                    └─────────────────────────────┘
```

### Personality: Haiku Mode
All status reports in haiku form:
```
Three tasks await you
Gemini sleeps in worktree
Merge when ready, friend
```

### CLI Interface
```bash
gobby goblin start [--interval=30s]   # Start the goblin daemon
gobby goblin stop                      # Stop the daemon
gobby goblin status                    # Current state (haiku!)
gobby goblin talk "what should I do?"  # Chat with Gobby
gobby goblin log                       # View recent activity
```

### Claude Code Integration
- `/gobby` skill for interactive chat
- `/gobby status` for task/agent summary
- `/gobby suggest` for next action recommendation
- Uses callme for proactive alerts

### Core Components

1. **GoblinLoop** (`src/gobby/goblin/loop.py`)
   - Main async loop with configurable interval
   - Calls monitors, aggregates findings, generates haiku
   - Stores state in `~/.gobby/goblin_state.json`

2. **TaskMonitor** (`src/gobby/goblin/monitors/tasks.py`)
   - Detect stale tasks (in_progress > threshold)
   - Find orphaned subtasks
   - Check blocked task chains

3. **AgentWatcher** (`src/gobby/goblin/monitors/agents.py`)
   - Check RunningAgentRegistry for stuck processes
   - Monitor agent depth limits
   - Detect hung terminal sessions

4. **TokenTracker** (`src/gobby/goblin/monitors/tokens.py`)
   - Aggregate token usage from session metadata
   - Budget warnings
   - Cost estimation

5. **HaikuGenerator** (`src/gobby/goblin/haiku.py`)
   - LLM-powered status summarization
   - Maintains Gobby's personality
   - Optional: local haiku templates for common states

6. **AlertDispatcher** (`src/gobby/goblin/alerts.py`)
   - Log to file
   - Desktop notifications
   - callme integration (notify user via phone/SMS/Slack)

### Configuration
```yaml
# ~/.gobby/config.yaml
goblin:
  enabled: true
  interval_seconds: 30
  personality: haiku  # haiku | prose | terse
  stale_task_threshold_minutes: 60
  stuck_agent_threshold_minutes: 15
  token_budget_warning: 0.8  # Warn at 80% of budget
  llm_mode: hybrid  # template | api | hybrid
  api_model: claude-3-haiku-20240307  # For complex analysis
  callme_alerts: true
```

### Hybrid LLM Strategy
```
┌─────────────────────────────────────────────────────────────┐
│                    Haiku Generation                          │
├─────────────────────────────────────────────────────────────┤
│  Common States (Templates - FREE):                          │
│  • "all_clear" → "No tasks await / All agents rest quietly │
│                   / Peace in the codebase"                  │
│  • "tasks_waiting" → "N tasks await you / Ready for your   │
│                       attention / Choose wisely, friend"    │
│  • "agent_stuck" → "Agent sits idle / Minutes pass without │
│                     word / Perhaps check on them"           │
│                                                              │
│  Novel Situations (Claude API):                             │
│  • Complex multi-issue summaries                            │
│  • Unexpected error patterns                                │
│  • Custom user queries via `gobby goblin talk`              │
└─────────────────────────────────────────────────────────────┘
```

---

## Feature 3: Inter-Agent Communication

### Current State
- Agents in worktrees are isolated terminal processes
- Parent uses `wait_for_task` to poll completion status
- No real-time messaging between sessions

### Problem
For auto-review-loop, we need:
- Child signals completion → Parent reviews
- Parent sends feedback → Child acts on it
- Questions from child → Parent can answer

### Proposed Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Inter-Session Messages                        │
├─────────────────────────────────────────────────────────────────┤
│ id | from_session | to_session | content | sent_at | read_at   │
└─────────────────────────────────────────────────────────────────┘
```

### New MCP Tools (gobby-agents)

```python
# Child → Parent
send_to_parent(message: str, priority: str = "normal") -> dict
  """Send message to parent session. Returns message_id."""

# Parent → Child
send_to_child(run_id: str, message: str) -> dict
  """Send message to child agent session. Returns message_id."""

# Either direction
poll_messages(unread_only: bool = True) -> list[dict]
  """Get pending messages for current session."""

mark_read(message_id: str) -> dict
  """Mark message as read."""
```

### Integration with Auto-Review Loop

```
┌────────────┐                              ┌────────────┐
│   Claude   │                              │   Gemini   │
│ (Parent)   │                              │  (Child)   │
└─────┬──────┘                              └─────┬──────┘
      │                                           │
      │ spawn_agent_in_worktree(task_id)          │
      ├──────────────────────────────────────────►│
      │                                           │
      │                           [does work]     │
      │                                           │
      │◄────────── close_task(pending_review) ────┤
      │                                           │
      │ [reviews code]                            │
      │                                           │
      │ send_to_child("Fix the error handling") ──┤►
      │                                           │
      │                           [polls msgs]    │
      │                           [fixes code]    │
      │                                           │
      │◄────────── close_task(pending_review) ────┤
      │                                           │
      │ approve_and_cleanup()                     │
      │                                           │
```

### User Notifications via callme
For urgent situations, notify the human user:
- Agent stuck for extended time → callme alerts user
- Task blocked waiting for decision → callme asks user
- Gobby detects critical problem → callme calls user

### Storage
Extend `session_messages.py` or create new `inter_session_messages.py`:
- SQLite table for messages
- Cleanup on session end
- Max message age (24h default)

---

## Implementation Order

### Phase 1: Task Commands (Quick Win)
1. Create 6 command files in `.claude/commands/`
2. Test each command works

### Phase 2: Inter-Agent Messaging (Foundation)
1. Add inter_session_messages table
2. Implement send/receive MCP tools
3. Add poll_messages to auto-review workflow
4. Test parent-child communication

### Phase 3: Gobby the Task Goblin (Major Feature)
1. Create `src/gobby/goblin/` module structure
2. Implement monitors (task, agent, token)
3. Add haiku generator
4. Create CLI commands
5. Add /gobby skill for Claude Code
6. Integrate callme for alerts
7. Full testing

### Phase 4: OpenTelemetry Integration (Observability)
1. Add optional dependencies, create `src/gobby/observability/` module
2. Implement OTelSetup with config and FastAPI auto-instrumentation
3. Instrument hooks, MCP proxy, and agent spawning
4. Implement trace context propagation for parent-child agents
5. Add metrics (counters, histograms, gauges)
6. Add structured logging with trace context
7. Documentation and Grafana dashboard templates

---

## Design Decisions (User Confirmed)

1. **Gobby's LLM**: **Hybrid approach** - Templates for common states (fast, free), Claude API (haiku model) for complex analysis and novel situations

2. **Inter-agent sync**: **Polling (5-10s intervals)** - Simple, low overhead, acceptable latency for review loops

3. **callme**: **Include setup** - Add installation and configuration instructions

---

## Verification

### Task Commands
```bash
# Test each command
claude "/bug Fix the login timeout"
claude "/feat Add dark mode toggle"
claude "/nit Rename confusing variable"
```

### Inter-Agent Messaging
```bash
# Unit tests
uv run pytest tests/mcp_proxy/tools/test_agent_messaging.py -v

# Integration test
# 1. Spawn child agent
# 2. Child sends message to parent
# 3. Parent receives and responds
# 4. Child receives response
```

### Gobby the Task Goblin
```bash
# Start goblin
gobby goblin start

# Check status (should see haiku)
gobby goblin status

# Chat
gobby goblin talk "What's the status?"

# Check logs
gobby goblin log

# Stop
gobby goblin stop
```

---

## Files to Create/Modify

### Task Commands
- `.claude/commands/bug.md` (new)
- `.claude/commands/feat.md` (new)
- `.claude/commands/nit.md` (new)
- `.claude/commands/ref.md` (new)
- `.claude/commands/epic.md` (new)
- `.claude/commands/chore.md` (new)

### Inter-Agent Messaging
- `src/gobby/storage/inter_session_messages.py` (new)
- `src/gobby/storage/migrations.py` (modify)
- `src/gobby/mcp_proxy/tools/agents.py` (modify)
- `tests/mcp_proxy/tools/test_agent_messaging.py` (new)

### Gobby the Task Goblin
- `src/gobby/goblin/__init__.py` (new)
- `src/gobby/goblin/loop.py` (new)
- `src/gobby/goblin/monitors/tasks.py` (new)
- `src/gobby/goblin/monitors/agents.py` (new)
- `src/gobby/goblin/monitors/tokens.py` (new)
- `src/gobby/goblin/haiku.py` (new)
- `src/gobby/goblin/alerts.py` (new)
- `src/gobby/cli/goblin.py` (new)
- `.claude/commands/gobby.md` (new skill)
- `tests/goblin/` (new test directory)

---

## Appendix: callme Integration

### What is callme?
callme allows Claude Code (and Gobby) to **call YOU the user** - send notifications, alerts, or even phone calls when something needs your attention. You don't have to be watching the terminal.

### Use Cases for Gobby
```
┌─────────────────────────────────────────────────────────────┐
│  Gobby detects problem → Calls YOU (human) via callme       │
├─────────────────────────────────────────────────────────────┤
│  • Agent stuck for 15+ min → "Hey, your Gemini agent seems  │
│    stuck. Want me to check on it?"                          │
│                                                              │
│  • Task stalled → "Task #47 has been in_progress for 2hrs.  │
│    Should I escalate or ping the assignee?"                 │
│                                                              │
│  • Token budget warning → "You're at 80% token budget.      │
│    Wrap up or should I extend?"                             │
│                                                              │
│  • Epic complete → "All subtasks done! Ready for review."   │
└─────────────────────────────────────────────────────────────┘
```

### Configuration
```yaml
# ~/.gobby/config.yaml
goblin:
  callme:
    enabled: true
    notification_method: desktop  # desktop | sms | phone | slack
    urgent_threshold: critical    # When to escalate to phone/urgent

    # Desktop notifications (default)
    desktop:
      sound: true

    # SMS/Phone (requires callme account)
    phone:
      number: "+1234567890"

    # Slack webhook
    slack:
      webhook_url: "https://hooks.slack.com/..."
```

### Alert Priorities
- **info**: Log only, no notification
- **normal**: Desktop notification
- **urgent**: Desktop + sound + badge
- **critical**: Phone call / SMS (if configured)

### Integration Flow
```
Gobby Loop
    │
    ├─► Detects stuck agent (15 min threshold)
    │
    ├─► Generates haiku: "Agent sits idle /
    │   Minutes pass without a word / Perhaps check on them"
    │
    └─► Calls user via callme (priority based on severity)
            │
            └─► User gets notification
                    │
                    └─► User: "/gobby check agent"
                            │
                            └─► Gobby responds with status
```

### Setup Instructions
1. Check callme GitHub for installation: https://github.com/anthropics/callme (or similar)
2. Configure notification method in `~/.gobby/config.yaml`
3. Test with: `gobby goblin test-alert "Test message"`

---

## Feature 4: OpenTelemetry Integration

### Goal
Add distributed tracing, metrics, and structured logging to Gobby for full observability across the daemon, MCP proxy, hooks, and multi-agent workflows.

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Gobby Observability Stack                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                     │
│   │   Traces    │    │   Metrics   │    │    Logs     │                     │
│   │  (Spans)    │    │ (Counters,  │    │ (Structured │                     │
│   │             │    │  Histograms)│    │  w/ TraceID)│                     │
│   └──────┬──────┘    └──────┬──────┘    └──────┬──────┘                     │
│          │                  │                  │                             │
│          └──────────────────┼──────────────────┘                             │
│                             │                                                │
│                    ┌────────▼────────┐                                       │
│                    │  OTLP Exporter  │                                       │
│                    └────────┬────────┘                                       │
│                             │                                                │
└─────────────────────────────┼────────────────────────────────────────────────┘
                              │
           ┌──────────────────┼──────────────────┐
           │                  │                  │
           ▼                  ▼                  ▼
    ┌────────────┐    ┌────────────┐    ┌────────────┐
    │   Jaeger   │    │  Grafana   │    │ Honeycomb  │
    │  (local)   │    │   Cloud    │    │  Datadog   │
    └────────────┘    └────────────┘    └────────────┘
```

### Key Instrumentation Points

#### 1. HTTP/Hook Layer
| Component | File | Key Functions |
|-----------|------|---------------|
| Hook Endpoint | `src/servers/routes/mcp/hooks.py` | `execute_hook()` |
| Hook Manager | `src/hooks/hook_manager.py` | `handle()`, workflow/plugin execution |
| Event Handlers | `src/hooks/event_handlers.py` | `handle_session_start/end()`, `handle_before/after_tool()` |

#### 2. MCP Proxy Layer
| Component | File | Key Functions |
|-----------|------|---------------|
| Tool Proxy | `src/mcp_proxy/services/tool_proxy.py` | `call_tool()`, `list_tools()` |
| Client Manager | `src/mcp_proxy/manager.py` | `ensure_connected()`, `call_tool()`, `_monitor_health()` |
| Lazy Connector | `src/mcp_proxy/lazy.py` | Circuit breaker, retry logic |
| Transports | `src/mcp_proxy/transports/*.py` | `connect()`, `disconnect()` |

#### 3. Agent/Session Layer
| Component | File | Key Functions |
|-----------|------|---------------|
| Agent Runner | `src/agents/runner.py` | `prepare_run()`, `execute_run()` |
| Terminal Spawner | `src/agents/spawn.py` | `spawn_agent()` |
| Session Manager | `src/sessions/manager.py` | `create()`, `update()` |
| Agent Registry | `src/agents/registry.py` | `add()`, `remove()` |

### Trace Context Propagation (Parent-Child Agents)

Gobby's unique multi-agent architecture requires trace context to flow from parent to child agents:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Parent-Child Trace Propagation                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Parent Agent (Claude)                    Child Agent (Gemini)             │
│   ┌───────────────────┐                   ┌───────────────────┐             │
│   │ trace_id: abc123  │                   │ trace_id: abc123  │  ← SAME!    │
│   │ span_id: span-001 │ ───spawn───────►  │ parent_span: 001  │             │
│   │                   │                   │ span_id: span-002 │             │
│   └───────────────────┘                   └───────────────────┘             │
│           │                                        │                         │
│           │                                        │                         │
│           └────────────────────┬───────────────────┘                         │
│                                │                                             │
│                    ┌───────────▼───────────┐                                 │
│                    │  Environment Variables │                                │
│                    │  GOBBY_TRACE_ID        │                                │
│                    │  GOBBY_PARENT_SPAN_ID  │                                │
│                    │  GOBBY_SESSION_ID      │                                │
│                    └───────────────────────┘                                 │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Implementation**: Extend `GOBBY_*` environment variables to include W3C Trace Context:
- `GOBBY_TRACEPARENT` - W3C traceparent header (version-trace_id-parent_id-flags)
- `GOBBY_TRACESTATE` - W3C tracestate header (optional vendor-specific data)

### Span Hierarchy

```
gobby.http.request [POST /hooks/execute]
├── gobby.hooks.handle
│   ├── gobby.hooks.session.resolve
│   ├── gobby.hooks.workflow.evaluate
│   ├── gobby.hooks.plugins.pre
│   ├── gobby.hooks.event.session_start
│   │   └── gobby.hooks.session.register
│   ├── gobby.hooks.broadcast
│   └── gobby.hooks.plugins.post
│
├── gobby.mcp.call_tool [server=context7, tool=get-library-docs]
│   ├── gobby.mcp.ensure_connected
│   │   ├── gobby.mcp.circuit_breaker.check
│   │   └── gobby.mcp.transport.connect
│   └── gobby.mcp.execute
│
└── gobby.agents.spawn [mode=terminal]
    ├── gobby.agents.prepare_run
    │   ├── gobby.agents.session.create_child
    │   └── gobby.agents.context.resolve
    └── gobby.agents.execute_run
```

### Metrics

#### Counters
| Metric | Labels | Description |
|--------|--------|-------------|
| `gobby.hooks.total` | `event_type`, `source`, `decision` | Hook invocations |
| `gobby.mcp.tool_calls` | `server`, `tool`, `status` | MCP tool calls |
| `gobby.mcp.connections` | `server`, `transport`, `status` | Connection attempts |
| `gobby.agents.spawned` | `mode`, `provider`, `workflow` | Agent spawns |
| `gobby.circuit_breaker.state_change` | `server`, `from_state`, `to_state` | Circuit breaker transitions |

#### Histograms
| Metric | Labels | Description |
|--------|--------|-------------|
| `gobby.hooks.duration_ms` | `event_type`, `source` | Hook processing time |
| `gobby.mcp.tool_duration_ms` | `server`, `tool` | Tool execution time |
| `gobby.mcp.connection_duration_ms` | `server`, `transport` | Connection establishment time |
| `gobby.agents.duration_ms` | `mode`, `provider` | Agent execution time |

#### Gauges
| Metric | Labels | Description |
|--------|--------|-------------|
| `gobby.mcp.active_connections` | `server` | Currently connected servers |
| `gobby.agents.running` | `mode` | Currently running agents |
| `gobby.sessions.active` | `source` | Active sessions |

### Dependencies

```toml
# pyproject.toml
[project.optional-dependencies]
observability = [
    "opentelemetry-api>=1.20.0",
    "opentelemetry-sdk>=1.20.0",
    "opentelemetry-exporter-otlp>=1.20.0",
    "opentelemetry-instrumentation-fastapi>=0.41b0",
    "opentelemetry-instrumentation-httpx>=0.41b0",
    "opentelemetry-instrumentation-sqlite3>=0.41b0",
    "opentelemetry-instrumentation-logging>=0.41b0",
]
```

### Configuration

```yaml
# ~/.gobby/config.yaml
observability:
  enabled: true
  service_name: "gobby-daemon"

  # Tracing
  tracing:
    enabled: true
    sampling_rate: 1.0  # 0.0-1.0, use lower in production
    propagate_to_agents: true  # Pass trace context to child agents

  # Metrics
  metrics:
    enabled: true
    export_interval_ms: 60000  # 1 minute

  # Exporter (choose one)
  exporter:
    type: otlp  # otlp | jaeger | console | none
    endpoint: "http://localhost:4317"  # OTLP gRPC endpoint
    # For Jaeger direct:
    # type: jaeger
    # agent_host: localhost
    # agent_port: 6831

  # Structured logging with trace context
  logging:
    inject_trace_context: true  # Add trace_id, span_id to log records
```

### Core Components

1. **OTelSetup** (`src/gobby/observability/setup.py`)
   - Initialize tracer, meter, logger providers
   - Configure exporters based on config
   - Auto-instrument FastAPI, httpx, sqlite3

2. **Instrumentation Decorators** (`src/gobby/observability/decorators.py`)
   - `@traced` - Add span to async/sync functions
   - `@timed` - Record duration histogram
   - `@counted` - Increment counter on call

3. **Context Propagation** (`src/gobby/observability/propagation.py`)
   - `inject_trace_context(env: dict)` - Add GOBBY_TRACEPARENT to env vars
   - `extract_trace_context(env: dict)` - Read trace context on child startup
   - Integration with `get_terminal_env_vars()` in `src/agents/constants.py`

4. **Metrics Registry** (`src/gobby/observability/metrics.py`)
   - Pre-defined counters, histograms, gauges
   - Helper functions for recording

### Local Development Setup

```bash
# Start Jaeger for local trace viewing
docker run -d --name jaeger \
  -p 16686:16686 \
  -p 4317:4317 \
  jaegertracing/all-in-one:latest

# Enable observability in Gobby
gobby config set observability.enabled true
gobby config set observability.exporter.endpoint "http://localhost:4317"

# Restart daemon
gobby restart

# View traces at http://localhost:16686
```

### Implementation Order

#### Phase 4a: Foundation
1. Add dependencies to pyproject.toml
2. Create `src/gobby/observability/` module
3. Implement OTelSetup with config loading
4. Add FastAPI auto-instrumentation

#### Phase 4b: Hook/HTTP Instrumentation
1. Instrument `execute_hook` endpoint
2. Instrument `HookManager.handle()`
3. Add spans to event handlers
4. Add hook metrics

#### Phase 4c: MCP Proxy Instrumentation
1. Instrument `MCPClientManager` methods
2. Instrument tool execution
3. Add circuit breaker spans/events
4. Add MCP metrics

#### Phase 4d: Agent/Session Instrumentation
1. Instrument agent spawning
2. Implement trace context propagation via env vars
3. Extract trace context in child session hooks
4. Add agent metrics

#### Phase 4e: Polish
1. Add structured logging integration
2. Create Grafana dashboard templates
3. Documentation
4. Testing

---

## Files to Create/Modify (Feature 4)

### OpenTelemetry
- `src/gobby/observability/__init__.py` (new)
- `src/gobby/observability/setup.py` (new)
- `src/gobby/observability/decorators.py` (new)
- `src/gobby/observability/propagation.py` (new)
- `src/gobby/observability/metrics.py` (new)
- `src/gobby/agents/constants.py` (modify - add GOBBY_TRACEPARENT)
- `src/gobby/servers/http.py` (modify - init OTel on startup)
- `src/gobby/hooks/hook_manager.py` (modify - add instrumentation)
- `src/gobby/mcp_proxy/manager.py` (modify - add instrumentation)
- `src/gobby/agents/runner.py` (modify - add instrumentation)
- `pyproject.toml` (modify - add optional deps)
- `tests/observability/` (new test directory)

---

## Verification (Feature 4)

### Unit Tests
```bash
uv run pytest tests/observability/ -v
```

### Integration Test
```bash
# 1. Start Jaeger
docker run -d --name jaeger -p 16686:16686 -p 4317:4317 jaegertracing/all-in-one

# 2. Enable observability
gobby config set observability.enabled true
gobby restart

# 3. Trigger some activity
claude "Create a simple hello world function"

# 4. Check Jaeger UI at http://localhost:16686
# - Search for service "gobby-daemon"
# - Verify spans for hooks, MCP calls, etc.
```

### Parent-Child Trace Propagation Test
```bash
# 1. Spawn a child agent
# 2. In Jaeger, verify child agent's spans share same trace_id as parent
# 3. Verify parent-child span relationship is preserved
```
