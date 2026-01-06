# Hook Manager Decomposition Analysis

**File:** `src/gobby/hooks/hook_manager.py`
**Lines:** 1,681
**Methods:** 29 (including 15 event handlers)
**Task:** gt-93dbea
**Parent:** gt-a474d1 (Decompose hook_manager.py)

## Current Structure Summary

The HookManager class serves as the central coordinator for Claude Code hooks. Despite the docstring claiming it's "~300-line routing layer", it has grown to 1,681 lines with multiple responsibilities.

## Event Types (15 total)

| # | Event Type | Handler Method | Lines | Description |
|---|------------|----------------|-------|-------------|
| 1 | SESSION_START | _handle_event_session_start | 899-1027 | Register session, execute handoff workflow |
| 2 | SESSION_END | _handle_event_session_end | 1029-1133 | Generate summary, mark handoff_ready |
| 3 | BEFORE_AGENT | _handle_event_before_agent | 1238-1303 | User prompt submit, title synthesis |
| 4 | AFTER_AGENT | _handle_event_after_agent | 1305-1347 | Agent stop, status update |
| 5 | BEFORE_TOOL | _handle_event_before_tool | 1385-1430 | Pre-tool-use evaluation |
| 6 | AFTER_TOOL | _handle_event_after_tool | 1432-1479 | Post-tool processing |
| 7 | PRE_COMPACT | _handle_event_pre_compact | 1481-1512 | Context compaction |
| 8 | SUBAGENT_START | _handle_event_subagent_start | 1514-1541 | Subagent spawn |
| 9 | SUBAGENT_STOP | _handle_event_subagent_stop | 1543-1562 | Subagent termination |
| 10 | NOTIFICATION | _handle_event_notification | 1564-1594 | Notification handling |
| 11 | BEFORE_TOOL_SELECTION | _handle_event_before_tool_selection | 1620-1639 | Gemini only |
| 12 | BEFORE_MODEL | _handle_event_before_model | 1641-1660 | Gemini only |
| 13 | AFTER_MODEL | _handle_event_after_model | 1662-1681 | Gemini only |
| 14 | PERMISSION_REQUEST | _handle_event_permission_request | 1596-1618 | Claude Code only |
| 15 | STOP | _handle_event_stop | 1349-1383 | Claude Code stop hook |

## Method Inventory

| Method | Lines | Responsibility Area | Notes |
|--------|-------|---------------------|-------|
| __init__ | 85-375 | Initialization | Creates all subsystems |
| _setup_logging | 377-412 | Logging | Configures log rotation |
| _reregister_active_sessions | 414-448 | Session Coordinator | Re-register on daemon restart |
| _start_health_check_monitoring | 450-489 | Health Monitor | Background daemon check |
| _get_cached_daemon_status | 491-504 | Health Monitor | Get cached status |
| handle | 506-714 | Core Routing | Main entry point |
| _get_event_handler | 716-726 | Core Routing | Handler lookup |
| _dispatch_webhooks_sync | 728-779 | Webhook Dispatcher | Blocking webhooks |
| _dispatch_webhooks_async | 781-822 | Webhook Dispatcher | Fire-and-forget webhooks |
| shutdown | 824-850 | Lifecycle | Cleanup resources |
| get_machine_id | 854-859 | Helper | Get machine identifier |
| _resolve_project_id | 861-894 | Helper | Resolve project from cwd |
| _handle_event_session_start | 899-1027 | Event Handler | SESSION_START |
| _handle_event_session_end | 1029-1133 | Event Handler | SESSION_END |
| _complete_agent_run | 1135-1201 | Session Coordinator | Complete terminal agent |
| _release_session_worktrees | 1209-1236 | Session Coordinator | Release worktrees |
| _handle_event_before_agent | 1238-1303 | Event Handler | BEFORE_AGENT |
| _handle_event_after_agent | 1305-1347 | Event Handler | AFTER_AGENT |
| _handle_event_stop | 1349-1383 | Event Handler | STOP |
| _handle_event_before_tool | 1385-1430 | Event Handler | BEFORE_TOOL |
| _handle_event_after_tool | 1432-1479 | Event Handler | AFTER_TOOL |
| _handle_event_pre_compact | 1481-1512 | Event Handler | PRE_COMPACT |
| _handle_event_subagent_start | 1514-1541 | Event Handler | SUBAGENT_START |
| _handle_event_subagent_stop | 1543-1562 | Event Handler | SUBAGENT_STOP |
| _handle_event_notification | 1564-1594 | Event Handler | NOTIFICATION |
| _handle_event_permission_request | 1596-1618 | Event Handler | PERMISSION_REQUEST |
| _handle_event_before_tool_selection | 1620-1639 | Event Handler | BEFORE_TOOL_SELECTION |
| _handle_event_before_model | 1641-1660 | Event Handler | BEFORE_MODEL |
| _handle_event_after_model | 1662-1681 | Event Handler | AFTER_MODEL |

## Internal State/Attributes

### Core Dependencies (injected/created)
- `_llm_service`: LLM service for AI features
- `_config`: DaemonConfig instance
- `_database`: LocalDatabase
- `_daemon_client`: DaemonClient for HTTP communication
- `_transcript_processor`: TranscriptProcessor for JSONL parsing

### Storage Managers
- `_session_storage`: LocalSessionManager
- `_session_task_manager`: SessionTaskManager
- `_memory_storage`: LocalMemoryManager
- `_skill_storage`: LocalSkillManager
- `_message_manager`: LocalSessionMessageManager
- `_task_manager`: LocalTaskManager
- `_agent_run_manager`: LocalAgentRunManager
- `_worktree_manager`: LocalWorktreeManager

### Business Logic
- `_memory_manager`: MemoryManager
- `_skill_learner`: SkillLearner (optional)
- `_session_manager`: SessionManager
- `_workflow_engine`: WorkflowEngine
- `_workflow_handler`: WorkflowHookHandler
- `_summary_file_generator`: SummaryFileGenerator
- `_webhook_dispatcher`: WebhookDispatcher
- `_plugin_loader`: PluginLoader (optional)

### Health Monitoring State
- `_cached_daemon_is_ready`: bool
- `_cached_daemon_message`: str | None
- `_cached_daemon_status`: str
- `_cached_daemon_error`: str | None
- `_health_check_interval`: float
- `_health_check_timer`: threading.Timer | None
- `_health_check_lock`: threading.Lock
- `_is_shutdown`: bool

### Session Tracking State
- `_registered_sessions`: set[str]
- `_registered_sessions_lock`: threading.Lock
- `_title_synthesized_sessions`: set[str]
- `_title_synthesized_lock`: threading.Lock
- `_agent_message_cache`: dict[str, tuple[str, float]]
- `_cache_lock`: threading.Lock
- `_lookup_lock`: threading.Lock

### Event Routing
- `_event_handler_map`: dict[HookEventType, Callable]
- `_loop`: asyncio.AbstractEventLoop | None (for thread-safe async)
- `broadcaster`: Optional broadcaster for WebSocket events

## Proposed Extraction Modules

### Module 1: `hooks/health_monitor.py` (~80 lines)
**Daemon health check monitoring**

Methods to move:
- `_start_health_check_monitoring()` (450-489)
- `_get_cached_daemon_status()` (491-504)

State to move:
- `_cached_daemon_is_ready`
- `_cached_daemon_message`
- `_cached_daemon_status`
- `_cached_daemon_error`
- `_health_check_interval`
- `_health_check_timer`
- `_health_check_lock`
- `_is_shutdown`

Dependencies:
- DaemonClient

### Module 2: `hooks/webhook_dispatcher.py` (~100 lines)
**Already exists at `src/gobby/hooks/webhooks.py`**

The WebhookDispatcher class is already extracted. The wrapper methods in HookManager:
- `_dispatch_webhooks_sync()` (728-779)
- `_dispatch_webhooks_async()` (781-822)

These are thin wrappers that could be inlined or kept as convenience methods.

### Module 3: `hooks/session_coordinator.py` (~200 lines)
**Session lifecycle coordination**

Methods to move:
- `_reregister_active_sessions()` (414-448)
- `_complete_agent_run()` (1135-1201)
- `_release_session_worktrees()` (1209-1236)

State to move:
- `_registered_sessions`
- `_registered_sessions_lock`
- `_title_synthesized_sessions`
- `_title_synthesized_lock`
- `_agent_message_cache`
- `_cache_lock`
- `_lookup_lock`

Dependencies:
- SessionManager
- AgentRunManager
- WorktreeManager
- MessageProcessor

### Module 4: `hooks/event_handlers.py` (~800 lines)
**Individual event handler implementations**

Methods to move (all 15 event handlers):
- `_handle_event_session_start()`
- `_handle_event_session_end()`
- `_handle_event_before_agent()`
- `_handle_event_after_agent()`
- `_handle_event_stop()`
- `_handle_event_before_tool()`
- `_handle_event_after_tool()`
- `_handle_event_pre_compact()`
- `_handle_event_subagent_start()`
- `_handle_event_subagent_stop()`
- `_handle_event_notification()`
- `_handle_event_permission_request()`
- `_handle_event_before_tool_selection()`
- `_handle_event_before_model()`
- `_handle_event_after_model()`

Dependencies:
- SessionManager, WorkflowHandler
- SummaryFileGenerator
- TaskManager (for auto-link commits)

### Module 5: `hooks/hook_manager.py` (after extraction, ~500 lines)
**Core coordinator with routing**

Remaining responsibilities:
- `__init__()` - Initialize all subsystems
- `_setup_logging()` - Configure logging
- `handle()` - Main entry point with routing
- `_get_event_handler()` - Handler lookup
- `shutdown()` - Cleanup
- `get_machine_id()` - Helper
- `_resolve_project_id()` - Helper

## Dependency Graph

```
HookManager (coordinator)
├── HealthMonitor
│   └── DaemonClient
├── WebhookDispatcher (already extracted)
├── SessionCoordinator
│   ├── SessionManager
│   ├── AgentRunManager
│   └── WorktreeManager
├── EventHandlers
│   ├── WorkflowHandler
│   ├── SummaryFileGenerator
│   └── TaskManager
└── Core subsystems (stay in HookManager)
    ├── WorkflowEngine
    ├── PluginLoader
    └── Broadcaster
```

## Extraction Order

1. **hooks/health_monitor.py** - Independent, no deps on other new modules
2. **hooks/session_coordinator.py** - Session tracking logic
3. **hooks/event_handlers.py** - All event handlers (largest extraction)
4. **Update hook_manager.py** - Wire extracted modules

## Risk Assessment

**Low Risk:**
- HealthMonitor extraction - self-contained
- WebhookDispatcher already extracted

**Medium Risk:**
- EventHandlers - many methods, need to maintain event routing
- SessionCoordinator - state management across threads

**High Risk:**
- Large __init__ method creates many dependencies - may need to refactor initialization pattern

## Notes

- The file grew from the claimed "~300 lines" to 1,681 lines
- Some methods like `_dispatch_webhooks_*` are thin wrappers around already-extracted WebhookDispatcher
- Event handlers follow a consistent pattern: get session_id, log, execute workflows, return response
- Thread-safe state (locks) must be carefully moved to avoid race conditions
- The `_event_handler_map` will need to reference the extracted EventHandlers class
