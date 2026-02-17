# Workflow Actions Reference

This document provides a comprehensive reference for all available actions in the Gobby Workflow Engine. Actions are the building blocks of workflows, executed in response to hooks (start, end, tool calls, etc.) or within steps.

## Conditional Execution

All actions support an optional `when` field for conditional execution. When present, the condition is evaluated before the action runs. If the condition is false, the action is skipped entirely.

```yaml
- action: call_mcp_tool
  when: "not variables.get('current_task_id') and variables.get('session_task')"
  server_name: gobby-tasks
  tool_name: get_task
  arguments:
    task_id: "{{ variables.session_task }}"
  output_as: _task_info
```

The `when` expression has access to:
- `variables` — Workflow variables as a `DotDict` (supports both `variables.key` and `variables.get('key')`)
- All workflow variables flattened to top level (e.g., `session_task` instead of `variables.session_task`)
- Built-in functions: `len()`, `bool()`, `str()`, `int()`

Actions without a `when` field always execute (backward compatible).

## State Management

### `load_workflow_state`

Loads the persisted workflow state for the current session.
**Usage:** `on_session_start`

```yaml
- action: load_workflow_state
```

### `save_workflow_state`

Persists the current workflow state to the database.
**Usage:** `on_session_end`, `on_transition`

```yaml
- action: save_workflow_state
```

### `set_variable`

Sets a key-value pair in the workflow variables.
**Usage:** Any trigger

```yaml
- action: set_variable
  name: current_task_index
  value: 0
```

### `increment_variable`

Increments a numeric workflow variable.
**Usage:** Loop iterations

```yaml
- action: increment_variable
  name: retry_count
  amount: 1
```

### `mark_loop_complete`

Marks a workflow loop iteration as complete.
**Usage:** End of loop cycles

```yaml
- action: mark_loop_complete
```

### `end_workflow`

Ends/terminates the active workflow.
**Usage:** Workflow completion or forced termination

```yaml
- action: end_workflow
  reason: "All tasks completed"
```

## Context Injection

### `inject_context`

Injects text content into the next prompt sent to the agent.
**Usage:** `on_enter`, `on_session_start`, `on_before_agent`

```yaml
- action: inject_context
  source: previous_session_summary
  template: |
    ## Previous Session
    {{ summary }}
```

**Sources:**

| Source | Description | Parameters |
|--------|-------------|------------|
| `previous_session_summary` | Summary from parent session handoff | `require: true` to block if missing |
| `compact_handoff` | Context from pre-compact handoff | `require: true` to block if missing |
| `skills` | Inject skill list with descriptions | `filter: always_apply` for alwaysApply skills only |
| `task_context` | Active task details if session has claimed task | — |
| `memories` | Relevant memories for current context | `limit`, `min_importance` |
| (none) | Use inline `template` with Jinja2 syntax | — |

### `inject_message`

Injects a direct message visible to the agent (system or user channel depending on implementation).
**Usage:** To give instructions

```yaml
- action: inject_message
  content: "You are now in PLANNING mode."
```

### `extract_handoff_context`

Extracts structured context before compaction for handoff to the next session.
**Usage:** `on_pre_compact`

```yaml
- action: extract_handoff_context
```

## Detection

### `detect_plan_mode_from_context`

Detects if the agent is in plan mode by analyzing context signals.
**Usage:** `on_session_start`, `on_before_agent`

```yaml
- action: detect_plan_mode_from_context
```

## Session Lifecycle

### `start_new_session`

Starts a new session for handoff or spawning.
**Usage:** Session handoff workflows

```yaml
- action: start_new_session
```

### `mark_session_status`

Updates the status of the current or parent session.
**Usage:** `on_session_start` (expire parent), `on_session_end` (ready handoff)

```yaml
- action: mark_session_status
  target: parent  # or 'current_session'
  status: expired
```

### `switch_mode`

Signals that the agent should switch its behavioral mode.
**Usage:** `on_enter`

```yaml
- action: switch_mode
  mode: plan
```

## Summary

### `synthesize_title`

Generates a short title for the session based on the transcript.
**Usage:** `on_before_agent` (typically once)

```yaml
- action: synthesize_title
  when: "session.title == null"
```

### `generate_summary`

Generates a markdown summary of the session using an LLM and saves it to the session record.
**Usage:** `on_session_end`, or on-demand

```yaml
- action: generate_summary
  template: "Summarize this session..." # Optional custom prompt
```

### `generate_handoff`

Generates a summary AND marks the session as `handoff_ready`.
**Usage:** `on_session_end`

```yaml
- action: generate_handoff
```

## Memory

### `memory_save`

Saves a memory entry to the memory system.
**Usage:** Any trigger

```yaml
- action: memory_save
  content: "{{ variables.key_finding }}"
  importance: 0.8
```

### `memory_recall_relevant`

Recalls relevant memories for the current context and injects them.
**Usage:** `on_before_agent`

```yaml
- action: memory_recall_relevant
  limit: 10
  min_importance: 0.3
```

### `memory_sync_import`

Imports memories from `.gobby/memories.jsonl` into the database.
**Usage:** `on_session_start`

```yaml
- action: memory_sync_import
```

### `memory_sync_export`

Exports memories from the database to `.gobby/memories.jsonl`.
**Usage:** `on_session_end`, `on_pre_compact`

```yaml
- action: memory_sync_export
```

### `memory_extraction_gate`

Gate that checks conditions before allowing memory extraction.
**Usage:** `on_session_end`

```yaml
- action: memory_extraction_gate
```

### `memory_review_gate`

Gate that checks conditions before allowing memory review.
**Usage:** `on_session_end`

```yaml
- action: memory_review_gate
```

### `memory_extract_from_session`

Extracts memories from the session transcript using LLM analysis.
**Usage:** `on_session_end`

```yaml
- action: memory_extract_from_session
```

### `memory_inject_project_context`

Injects project-level context from the memory system.
**Usage:** `on_session_start`

```yaml
- action: memory_inject_project_context
```

### `reset_memory_injection_tracking`

Resets tracking of which memories have been injected in this session.
**Usage:** `on_session_start` (on clear/compact events)

```yaml
- action: reset_memory_injection_tracking
```

## Task Sync

### `task_sync_import`

Imports tasks from `.gobby/tasks.jsonl` into the database.
**Usage:** `on_session_start`

```yaml
- action: task_sync_import
```

### `task_sync_export`

Exports tasks from the database to `.gobby/tasks.jsonl`.
**Usage:** `on_session_end`, `on_pre_compact`

```yaml
- action: task_sync_export
```

### `persist_tasks`

Persists a list of tasks (dictionaries) to the Gobby Task System.
**Usage:** Plan decomposition

```yaml
- action: persist_tasks
  source: task_list.tasks  # variable containing list of dicts
```

### `get_workflow_tasks`

Gets tasks associated with the current workflow.
**Usage:** Any trigger

```yaml
- action: get_workflow_tasks
  output_as: workflow_tasks
```

### `update_workflow_task`

Updates a workflow task's fields.
**Usage:** Task management

```yaml
- action: update_workflow_task
  task_id: "{{ variables.current_task_id }}"
  status: completed
```

## Task Enforcement

### `block_tools`

Evaluates blocking rules against tool calls. Supports `tools:` (upstream tool names) and `mcp_tools:` (server:tool targets) matching patterns.
**Usage:** `on_before_tool`

```yaml
- action: block_tools
  rules:
    - tools: [Edit, Write, NotebookEdit]
      when: "not task_claimed"
      reason: "Claim a task first"

    - mcp_tools: ["gobby-tasks:close_task"]
      when: "not task_has_commits"
      reason: "Commit your changes first"

    - tools: [Bash]
      command_pattern: "(?:^|[;&|])\\s*(?:sudo\\s+)?python\\b"
      command_not_pattern: "(?:^|[;&|])\\s*uv\\s+"
      reason: "Use uv run python instead"
```

### `block_stop`

Blocks the agent from stopping the session.
**Usage:** `on_stop`

```yaml
- action: block_stop
  message: "Cannot stop while task is in progress"
```

### `require_active_task`

Blocks Edit/Write tools unless a task is claimed and `in_progress`.
**Usage:** `on_before_tool`

```yaml
- action: require_active_task
```

### `require_task_complete`

Checks task completion requirements before allowing transitions.
**Usage:** `on_exit`, exit conditions

```yaml
- action: require_task_complete
```

### `require_commit_before_stop`

Blocks session stop if the claimed task has uncommitted changes.
**Usage:** `on_stop`

```yaml
- action: require_commit_before_stop
```

### `require_task_review_or_close_before_stop`

Blocks session stop if a task is still `in_progress` (must be closed or marked `needs_review` first).
**Usage:** `on_stop`

```yaml
- action: require_task_review_or_close_before_stop
```

### `validate_session_task_scope`

Validates that the session is working within the scope of its assigned task.
**Usage:** `on_before_tool`

```yaml
- action: validate_session_task_scope
```

### `capture_baseline_dirty_files`

Records uncommitted files at session start for later commit detection.
**Usage:** `on_session_start`

```yaml
- action: capture_baseline_dirty_files
```

### `track_schema_lookup`

Tracks `get_tool_schema` calls for progressive disclosure enforcement.
**Usage:** `on_after_tool`

```yaml
- action: track_schema_lookup
```

### `track_discovery_step`

Tracks MCP discovery steps (list_mcp_servers, list_tools, etc.).
**Usage:** `on_after_tool`

```yaml
- action: track_discovery_step
```

## Todo

### `write_todos`

Writes a list of todo strings to a file (default `TODO.md`).
**Usage:** UI mirroring

```yaml
- action: write_todos
  filename: "TODO.md"
```

### `mark_todo_complete`

Marks a todo item as complete in a markdown file.
**Usage:** Task completion

```yaml
- action: mark_todo_complete
  todo_text: "Implement feature X"
```

## Shell

### `shell` / `run` / `bash`

Executes a shell command. All three names are aliases for the same handler.
**Usage:** Any trigger

```yaml
- action: shell
  command: "uv run pytest tests/ -v"
  timeout: 60
```

## LLM

### `call_llm`

Calls an LLM with a prompt and stores the result in a variable.
**Usage:** Decomposition, analysis

```yaml
- action: call_llm
  prompt: "Analyze this code: {{ code }}"
  output_as: analysis_result
```

## MCP

### `call_mcp_tool`

Invokes a tool on a connected MCP server.
**Usage:** External integrations

```yaml
- action: call_mcp_tool
  server_name: "github"
  tool_name: "create_issue"
  arguments:
    title: "Bug fix"
  output_as: issue_result
```

## Stop Signals

### `check_stop_signal`

Checks if a stop has been signaled for the session.
**Usage:** Step transitions, periodic checks

```yaml
- action: check_stop_signal
  acknowledge: true
```

### `request_stop`

Signals that the session should stop gracefully.
**Usage:** Workflow completion, error handling

```yaml
- action: request_stop
  source: workflow
  reason: "All tasks completed"
```

### `clear_stop_signal`

Clears any pending stop signal for the session.
**Usage:** Session recovery

```yaml
- action: clear_stop_signal
```

## Progress Tracking

### `start_progress_tracking`

Begins tracking agent progress for autonomous execution.
**Usage:** `on_enter` (autonomous steps)

```yaml
- action: start_progress_tracking
```

### `stop_progress_tracking`

Stops progress tracking.
**Usage:** `on_exit` (autonomous steps)

```yaml
- action: stop_progress_tracking
  keep_data: false
```

### `record_progress`

Records a progress event.
**Usage:** `on_after_tool`

```yaml
- action: record_progress
  progress_type: tool_call
  tool_name: "{{ tool_name }}"
```

### `detect_task_loop`

Detects if the agent is stuck in a repetitive loop.
**Usage:** Periodic checks during autonomous execution

```yaml
- action: detect_task_loop
```

### `detect_stuck`

Detects if the agent appears stuck (no meaningful progress).
**Usage:** Periodic checks during autonomous execution

```yaml
- action: detect_stuck
```

### `record_task_selection`

Records which task was selected for tracking and loop detection.
**Usage:** Task selection events

```yaml
- action: record_task_selection
  task_id: "{{ variables.current_task_id }}"
```

### `get_progress_summary`

Gets a summary of agent progress during autonomous execution.
**Usage:** On-demand, reflection steps

```yaml
- action: get_progress_summary
  output_as: progress
```

## Pipeline

### `run_pipeline`

Executes a pipeline by name from within a workflow.
**Usage:** Any trigger

```yaml
- action: run_pipeline
  name: deploy
  inputs:
    env: "{{ variables.target_env }}"
  await_completion: true
  result_variable: deploy_result
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | string | — | Pipeline name (required) |
| `inputs` | dict | `{}` | Input parameters (supports template rendering) |
| `await_completion` | bool | `false` | Store pending pipeline in state if waiting for approval |
| `result_variable` | string | `null` | Variable name to store the execution result |

## External Integrations

### `webhook`

Sends an HTTP request to an external service.
**Usage:** Any trigger, especially `on_session_end`, `on_error`

```yaml
- action: webhook
  url: "https://hooks.slack.com/services/xxx"
  method: POST
  headers:
    Authorization: "Bearer ${secrets.API_TOKEN}"
  payload:
    text: "Session ${session_id} completed"
  timeout: 30
  retry:
    max_attempts: 3
    backoff_seconds: 2
  capture_response:
    status_var: "webhook_status"
    body_var: "webhook_body"
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `url` | string | — | Target URL (required unless using `webhook_id`) |
| `webhook_id` | string | — | Reference to registered webhook in config |
| `method` | enum | `POST` | HTTP method: GET, POST, PUT, PATCH, DELETE |
| `headers` | dict | `{}` | Request headers (supports `${secrets.VAR}`) |
| `payload` | dict/string | `null` | Request body |
| `timeout` | int | `30` | Timeout in seconds (1-300) |
| `retry` | object | `null` | Retry config with max_attempts, backoff_seconds |
| `capture_response` | object | `null` | Variables to capture response into |
| `on_success` | string | `null` | Action to run on 2xx response |
| `on_failure` | string | `null` | Action to run after retries fail |

See [Webhooks and Plugins Guide](./webhooks-and-plugins.md) for examples.

## Plugin Actions

### `plugin:<name>:<action>`

Executes a custom action from a plugin. Plugin actions support optional schema validation.
**Usage:** Any trigger

```yaml
# Format: plugin:<plugin-name>:<action-name>
- action: plugin:code-guardian:run_linter
  files: ["src/main.py"]

- action: plugin:example-notify:http_notify
  url: "https://api.example.com"
  method: POST
  payload:
    message: "Hello"
```

Plugin actions are registered via Python plugins in `~/.gobby/plugins/`. See [Webhooks and Plugins Guide](./webhooks-and-plugins.md) for development instructions.
