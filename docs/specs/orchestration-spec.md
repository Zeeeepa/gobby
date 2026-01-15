# Orchestration System Specification

## Overview

This spec defines the Gobby Conductor orchestration system for coordinating multi-agent workflows, task monitoring, and autonomous operation with token budget awareness.

**Key capabilities:**
- Inter-agent messaging (parent ↔ child)
- Blocking wait tools for task synchronization
- `pending_review` status for review gates
- Token aggregation, pricing, and budget throttling
- Conductor daemon with TARS-style haiku personality
- Phone alerts via callme integration

## Phase A: Inter-Agent Messaging Foundation

Enable parent ↔ child message passing during agent execution.

### Storage Layer

- [ ] Create `inter_session_messages` table migration
  - [ ] Add columns: id, from_session, to_session, content, priority, sent_at, read_at
- [ ] Create `src/gobby/storage/inter_session_messages.py`
  - [ ] Implement `create_message(from_session, to_session, content, priority)`
  - [ ] Implement `get_messages(session_id, unread_only)`
  - [ ] Implement `mark_read(message_id)`

### MCP Tools

- [ ] Add `send_to_parent` tool to gobby-agents
  - [ ] Validate current session has parent
  - [ ] Create message record
  - [ ] Broadcast via WebSocket
- [ ] Add `send_to_child` tool to gobby-agents
  - [ ] Accept run_id parameter
  - [ ] Lookup child session from agent_runs
  - [ ] Create message record
- [ ] Add `poll_messages` tool to gobby-agents
  - [ ] Filter by current session
  - [ ] Support unread_only parameter
- [ ] Add `mark_read` tool to gobby-agents

## Phase B: Task Status Extensions

Support review workflow with `pending_review` status and blocking wait tools.

### Database Changes

- [ ] Add `pending_review` to task status enum
- [ ] Add `pending_review_at` timestamp column to tasks table
- [ ] Update JSONL sync to handle `pending_review` status

### Modified `close_task` Behavior

- [ ] Detect agent context via `session.agent_depth`
- [ ] Transition to `pending_review` when agent_depth > 0
- [ ] Transition to `completed` when called by orchestrator
- [ ] Add `force_complete` parameter for override

### Blocking Wait Tools

- [ ] Add `wait_for_task` tool to gobby-tasks
  - [ ] Poll task status at configurable interval
  - [ ] Return when status leaves `in_progress`
  - [ ] Support timeout parameter
- [ ] Add `wait_for_any_task` tool to gobby-tasks
  - [ ] Accept list of task_ids
  - [ ] Return first completed task
- [ ] Add `wait_for_all_tasks` tool to gobby-tasks
  - [ ] Accept list of task_ids
  - [ ] Return dict of task statuses
- [ ] Add `reopen_task` tool to gobby-tasks
  - [ ] Transition `pending_review` back to `in_progress`
  - [ ] Clear commit_sha
  - [ ] Log reopen reason
- [ ] Add `approve_and_cleanup` tool to gobby-tasks
  - [ ] Mark task completed
  - [ ] Delete worktree if specified

## Phase C: Interactive Orchestration Workflows

Enable human-driven sequential and parallel review loops.

### Worktree Agent Workflow

- [ ] Create `worktree-agent.yaml` workflow definition
  - [ ] Define tool allowlist (get_task, update_task, close_task, memory tools)
  - [ ] Block task navigation tools (list_tasks, suggest_next_task, create_task)
  - [ ] Block agent/worktree management tools
- [ ] Modify `spawn_agent_in_worktree` to auto-activate workflow
- [ ] Pass task_id to spawned agent via prompt injection

### Sequential Orchestrator Workflow

- [ ] Create `sequential-orchestrator.yaml` workflow definition
  - [ ] Define step: select_task (suggest_next_task, get_task)
  - [ ] Define step: spawn_agent (create_worktree, spawn_agent_in_worktree)
  - [ ] Define step: wait (wait_for_task)
  - [ ] Define step: review (read, glob, grep)
  - [ ] Define step: decide (merge_worktree, approve_and_cleanup, reopen_task)
  - [ ] Define step: loop with transitions

### Parallel Orchestrator Workflow

- [ ] Create `parallel-orchestrator.yaml` workflow definition
  - [ ] Add config for max_parallel_worktrees
  - [ ] Define step: select_batch
  - [ ] Define step: spawn_batch
  - [ ] Define step: wait_any (wait_for_any_task)
  - [ ] Define step: review_completed
  - [ ] Define step: process_completed
  - [ ] Define loop transitions

### Skill Documentation

- [ ] Create gobby-merge skill in `src/gobby/install/claude/skills/gobby-merge/SKILL.md`

## Phase D: Token Budget & Throttling

Enable resource-aware operation with accurate cost tracking.

### Schema Changes

- [ ] Add `model` column to sessions table
- [ ] Create migration for model column
- [ ] Extract model from Claude JSONL transcripts
- [ ] Extract model from Gemini transcripts

### Pricing Module

- [ ] Create `src/gobby/conductor/pricing.py`
  - [ ] Define Anthropic model pricing (input, output, cache_write, cache_read)
  - [ ] Define Google model pricing
  - [ ] Add helper to calculate cost from token counts

### Token Tracker

- [ ] Create `src/gobby/conductor/token_tracker.py`
- [ ] Implement `get_usage_summary(days)` aggregation query
  - [ ] Sum tokens by model within time window
  - [ ] Calculate costs using pricing data
  - [ ] Return UsageSummary dataclass
- [ ] Implement `get_budget_status()` budget check
  - [ ] Compare usage against configured limit
  - [ ] Return percentage and can_spawn flag
- [ ] Implement `can_spawn_agent()` throttle check

### Configuration

- [ ] Add `token_budget` section to config schema
  - [ ] weekly_limit (nullable float)
  - [ ] warning_threshold (float, default 0.8)
  - [ ] throttle_threshold (float, default 0.9)
  - [ ] tracking_window_days (int, default 7)

### MCP Tools

- [ ] Add `get_usage_report` tool to gobby-metrics
- [ ] Add `get_budget_status` tool to gobby-metrics

## Phase E: Conductor Daemon

Persistent daemon that monitors and acts on task backlog.

### Core Conductor Module

- [ ] Create `src/gobby/conductor/__init__.py`
- [ ] Create `src/gobby/conductor/loop.py`
  - [ ] Implement `ConductorLoop` class
  - [ ] Implement `start()` method
  - [ ] Implement `stop()` method
  - [ ] Implement `tick()` monitoring cycle
  - [ ] Integrate token budget check
  - [ ] Integrate task monitor
  - [ ] Integrate agent watcher
  - [ ] Support autonomous mode flag

### Monitors

- [ ] Create `src/gobby/conductor/monitors/__init__.py`
- [ ] Create `src/gobby/conductor/monitors/tasks.py`
  - [ ] Detect stale tasks (in_progress > threshold)
  - [ ] Find orphaned subtasks
  - [ ] Check blocked task chains
- [ ] Create `src/gobby/conductor/monitors/agents.py`
  - [ ] Check RunningAgentRegistry for stuck processes
  - [ ] Monitor agent depth limits
  - [ ] Detect hung terminal sessions

### Haiku Generator

- [ ] Create `src/gobby/conductor/haiku.py`
- [ ] Define template haikus for common states
  - [ ] all_clear template
  - [ ] tasks_waiting template
  - [ ] agent_stuck template
  - [ ] budget_warning template
- [ ] Implement template matching logic
- [ ] Implement LLM fallback for novel situations
- [ ] Add TARS-style humor setting (default 0.15)

### Alert Dispatcher

- [ ] Create `src/gobby/conductor/alerts.py`
- [ ] Implement priority levels (info, normal, urgent, critical)
- [ ] Implement log output for all levels
- [ ] Implement WebSocket broadcast for urgent+
- [ ] Implement callme integration for critical
  - [ ] Call `initiate_call` with alert message
  - [ ] Handle call response

### CLI Commands

- [ ] Create `src/gobby/cli/conductor.py`
- [ ] Implement `gobby conductor start` command
  - [ ] Support --interval option
  - [ ] Support --autonomous flag
- [ ] Implement `gobby conductor stop` command
- [ ] Implement `gobby conductor restart` command
- [ ] Implement `gobby conductor status` command
  - [ ] Show haiku status
  - [ ] Show active agents
  - [ ] Show pending tasks
  - [ ] Show token usage
- [ ] Implement `gobby conductor chat` command
  - [ ] Support message argument
  - [ ] Support interactive dashboard mode
- [ ] Register conductor group in main CLI

### Runner Integration

- [ ] Modify `src/gobby/runner.py` to start ConductorLoop
- [ ] Add conductor enabled check
- [ ] Handle conductor shutdown on daemon stop

### Configuration

- [ ] Add conductor section to config schema
  - [ ] enabled (bool)
  - [ ] interval_seconds (int, default 30)
  - [ ] autonomous_mode (bool)
  - [ ] personality settings
  - [ ] threshold settings
  - [ ] llm_mode (template/api/hybrid)

## Phase F: Documentation & Testing

Validate the system end-to-end and update documentation.

### Documentation Updates

- [ ] Document worktree agent mode in GEMINI.md
  - [ ] Explain scope limitations
  - [ ] List available tools
  - [ ] Describe workflow
- [ ] Document orchestrator patterns in CLAUDE.md
  - [ ] Sequential pattern instructions
  - [ ] Parallel pattern instructions

### Unit Tests

- [ ] Test close_task transitions to pending_review for agents
- [ ] Test wait_for_task returns on status change
- [ ] Test wait_for_task timeout behavior
- [ ] Test wait_for_any_task returns first completed
- [ ] Test wait_for_all_tasks returns all statuses
- [ ] Test reopen_task transitions status back
- [ ] Test token aggregation calculates costs correctly
- [ ] Test budget throttling respects thresholds
- [ ] Test haiku templates render correctly
- [ ] Test message creation and retrieval

gobby - call_tool (MCP)(server_name: "gobby-tasks", tool_name: "orchestrate_ready_tasks", arguments: {"parent_task_id":"53879476-21b3-473e-b202-5cd0f00060df"})

# 4. Agent Manager returns that orchestrator has started
gobby -> (System) Orchestrator started for parent task 53879476-21b3-473e-b202-5cd0f00060df

# 5. User checks status
gobby - call_tool (MCP)(server_name: "gobby-tasks", tool_name: "get_orchestration_status", arguments: {"parent_task_id":"53879476-21b3-473e-b202-5cd0f00060df"})

### E2E Tests

- [ ] Create `tests/e2e/test_inter_agent_messages.py`
  - [ ] Test send_to_parent / poll_messages flow
  - [ ] Test send_to_child / poll_messages flow
- [ ] Create `tests/e2e/test_sequential_review_loop.py`
  - [ ] Test full sequential orchestration cycle
- [ ] Create `tests/e2e/test_token_budget.py`
  - [ ] Test usage report aggregation
  - [ ] Test throttle behavior
- [ ] Create `tests/e2e/test_autonomous_mode.py`
  - [ ] Test auto-spawn on ready tasks
  - [ ] Test stuck agent alert
- [ ] Create `tests/e2e/test_worktree_merge_live.py`
  - [ ] Validate existing merge system

## Notes

- All worktree branches merge to `dev`, not main
- Worktrees auto-deleted after successful merge
- callme configured separately as Claude Code plugin
- Budget tracking in USD, calculated from token counts internally
- CLI flags take precedence over config file settings
