# Conductor — Deferred Items

Phase 4 landed the persistent conductor and cron broadcast infrastructure.
These items are deferred to future phases.

## Notification Channels

The conductor currently operates silently — it checks tasks and dispatches agents,
but only logs its decisions. Future work:

- **WebSocket broadcast** (free): Broadcast conductor decisions to active sessions
  via the existing `broadcast_cron_event` infrastructure. Clients can subscribe to
  `conductor_tick` events.
- **External notifications**: Email, Telegram, Slack via MCP server integrations.
  Suggest a `notify` MCP tool with configurable backends (similar to how `spawn_agent`
  abstracts provider differences).
- **Implementation**: Add a `notify` step type to pipelines, or a `notify` handler
  in the conductor system prompt that calls an MCP notification server.

## Observability UI

Data already exists in the database — needs web UI components:

- **Pipeline timeline**: Visual execution timeline showing step durations, wait gates,
  and agent dispatch. Data source: `pipeline_executions` + `step_executions` tables.
- **Conductor conversation viewer**: Read-only view of the conductor's ChatSession
  transcript. Data source: session messages for `source=conductor`.
- **Cron run history**: Dashboard showing job execution history, success/failure rates,
  and timing. Data source: `cron_jobs` + `cron_runs` tables.

## Pipeline Tool Cleanup (Phase 6)

Once the conductor is proven stable, ~600 lines of event-driven continuation
machinery become dead code:

- `register_pipeline_continuation` — Pipeline completion continuation registration
- `_pending_dead_end_retries` — Dead-end retry logic for stalled continuations
- `_auto_subscribe_lineage` — Automatic lineage subscription for event routing
- `pipeline_continuations` table — DB table for continuation state
- Related code in `runner.py` (`_rerun_pipeline`), `pipeline_executor.py`
  (continuation hooks), and `completion_registry.py`

**Strategy**: Strangler fig pattern. The conductor runs in parallel with the existing
event-driven system. Once conductor handles all dispatch scenarios reliably, disable
continuations and remove the dead code.

## Multi-Project Conductor

Current implementation is single-project (one conductor per GobbyRunner). Options:

- **One conductor per project**: Each project with `conductor.enabled=true` gets its
  own ChatSession and cron job. Simple but resource-heavy.
- **Iterate over projects**: Single conductor iterates over projects with active tasks.
  More efficient but requires cross-project task queries.
- **Hub-level conductor**: Operates at the hub database level, dispatching across
  all projects. Most capable but most complex.

## Agent Definition Loading

Current: ConductorManager builds its system prompt inline (`CONDUCTOR_SYSTEM_PROMPT`
constant). Future: load from the installed `conductor` agent definition YAML, allowing
users to customize the conductor's behavior without code changes.

Implementation: In `_ensure_session()`, call `resolve_agent("conductor", db)` and use
`agent_body.build_prompt_preamble()` if found, falling back to the hardcoded prompt.
