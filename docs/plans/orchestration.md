# Gobby Conductor: Unified Orchestration System

## 1. Overview

### 1.1 What is the Conductor?

The Conductor is Gobby's persistent orchestration daemon that monitors tasks, coordinates agents, tracks resources, and speaks in haiku. Think of it as a friendly daemon that keeps the task system tidy while occasionally offering dry, TARS-style wit.

**Key responsibilities:**
- Monitor task backlog for stale/blocked work
- Watch agent health and detect stuck processes
- Track token usage and enforce budgets
- Coordinate worktree agents and review loops
- Alert humans via callme when intervention needed

### 1.2 Two Operational Modes

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        GOBBY ORCHESTRATION LAYER                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   ┌─────────────────────┐    ┌─────────────────────────────────────┐   │
│   │   INTERACTIVE MODE  │    │         AUTONOMOUS MODE             │   │
│   │                     │    │                                     │   │
│   │ - Human triggers    │    │ - ConductorLoop daemon              │   │
│   │   workflows         │    │ - Token budget throttling           │   │
│   │ - Reviews at gates  │    │ - Auto-spawn on ready tasks         │   │
│   │ - /gobby commands   │    │ - Alerts via callme                 │   │
│   │                     │    │ - TARS personality (15% humor)      │   │
│   └─────────────────────┘    └─────────────────────────────────────┘   │
│                                                                         │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │                    SHARED INFRASTRUCTURE                        │   │
│   │                                                                 │   │
│   │  Inter-Agent Messaging    Task Status Extensions   Token Track  │   │
│   │  - send_to_parent         - pending_review         - Usage API  │   │
│   │  - send_to_child          - wait_for_task          - Budget %   │   │
│   │  - poll_messages          - reopen_task            - Throttle   │   │
│   │  - mark_read              - approve_and_cleanup                 │   │
│   │                                                                 │   │
│   │  WebSocket Broadcasting   Workflow System          Merge System │   │
│   │  - Agent events           - worktree-agent         - Already    │   │
│   │  - Message notifications  - sequential-orch        - complete   │   │
│   │  - Task updates           - parallel-orch          - Live test  │   │
│   └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

**Interactive Mode**: Human developer monitors agent outputs, deliberately triggers workflows, reviews at gates. Best for learning the system, complex decisions, and when you want control.

**Autonomous Mode**: Conductor farms out work based on task backlog with resource throttling. Auto-spawns agents on ready tasks, alerts via callme when stuck. Best for batch processing independent tasks overnight.

### 1.3 Key Capabilities Summary

| Capability | Description |
|------------|-------------|
| Inter-agent messaging | Parent↔child message passing during execution |
| Blocking wait tools | Synchronous wait for task completion |
| `pending_review` status | Review gates in task flow |
| Token aggregation/pricing | Sum across sessions + cost calculation |
| Conductor daemon loop | Persistent monitoring + TARS personality |

---

## 2. Architecture

### 2.1 System Diagram

```
                    ┌─────────────────────────────────────┐
                    │        Gobby the Conductor          │
                    │       (Persistent LLM Loop)         │
                    └─────────────────────────────────────┘
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
                    │ • Log to conductor.log      │
                    │ • Desktop notifications     │
                    │ • callme → USER (you!)      │
                    └─────────────────────────────┘
```

### 2.2 Core Components

| Component | File | Purpose |
|-----------|------|---------|
| **ConductorLoop** | `src/gobby/conductor/loop.py` | Main async loop with configurable interval (default 30s). Calls monitors, aggregates findings, generates haiku. |
| **TaskMonitor** | `src/gobby/conductor/monitors/tasks.py` | Detect stale tasks (in_progress > threshold), find orphaned subtasks, check blocked task chains. |
| **AgentWatcher** | `src/gobby/conductor/monitors/agents.py` | Check RunningAgentRegistry for stuck processes, monitor agent depth limits, detect hung terminal sessions. |
| **TokenTracker** | `src/gobby/conductor/monitors/tokens.py` | Aggregate token usage from session metadata, budget warnings, cost estimation. |
| **HaikuGenerator** | `src/gobby/conductor/haiku.py` | LLM-powered status summarization with TARS-style personality. Uses Claude Haiku model for API calls. |
| **AlertDispatcher** | `src/gobby/conductor/alerts.py` | Log to file, desktop notifications, callme integration for urgent alerts. |

### 2.3 Existing Infrastructure (DO NOT Implement)

The following already exist and should be leveraged:
- WebSocket server with broadcasting (`src/gobby/servers/websocket.py`)
- Agent event broadcasting via `RunningAgentRegistry`
- Merge system (gobby-merge) - needs live testing only
- Per-session token capture from JSONL (but no aggregation/pricing)
- Task type commands (`/bug`, `/feat`, etc.) - committed in `9d5d73f`

---

## 3. CLI Commands

### 3.1 `gobby conductor start`

Start the conductor daemon loop.

```bash
gobby conductor start [--interval=30s] [--autonomous]
```

**Options:**
- `--interval`: Monitoring frequency (default: 30s)
- `--autonomous`: Enable auto-spawning of agents on ready tasks

**Example:**
```bash
# Start conductor in interactive mode (monitoring only)
gobby conductor start

# Start in autonomous mode with 60s interval
gobby conductor start --autonomous --interval=60s
```

### 3.2 `gobby conductor stop`

Stop the conductor daemon.

```bash
gobby conductor stop
```

### 3.3 `gobby conductor restart`

Restart the conductor (stop + start with same options).

```bash
gobby conductor restart
```

### 3.4 `gobby conductor status`

Show current state with haiku, active agents, pending tasks, token usage.

```bash
gobby conductor status
```

**Example output:**
```
🎭 Conductor Status

Three tasks await you
Code review blocks the feature
Dependencies clear

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Active Agents: 2
  • gemini-abc123 (feature/auth) - 12m running
  • claude-def456 (fix/bug-42) - 3m running

Pending Tasks: 5
  • #2130 (ready) - Add user avatar upload
  • #2128 (blocked by #2127) - Integrate S3 storage
  • #2125 (pending_review) - Auth middleware refactor

Token Usage (7d): $12.45 / $50.00 (24.9%)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### 3.5 `gobby conductor chat`

Interactive dashboard showing current tasks, agents/workflows in use, progress, token usage. Without a message argument, enters live dashboard mode.

```bash
gobby conductor chat [message]
```

**Examples:**
```bash
# Ask a question
gobby conductor chat "What should I work on next?"

# Enter interactive dashboard mode
gobby conductor chat
```

**Interactive mode features:**
- Real-time task/agent status updates
- Token usage graph
- Recent haiku history
- Command input for queries

---

## 4. Conductor Personality: TARS Mode (15% Humor)

### 4.1 Haiku Communication

The Conductor speaks in haiku with dry, deadpan wit. Think TARS from Interstellar - helpful, competent, occasionally catches you off guard with subtle sass.

### 4.2 Example Haikus by Situation

**Normal status:**
```
Three tasks await you
Code review blocks the feature
Dependencies clear
```

**When you've ignored a task for 3 days (sass on stale):**
```
Task forty-seven
Has waited three days for you
It's starting to judge
```

**When an agent is stuck:**
```
Gemini sits still
Perhaps it found enlightenment
Or perhaps it crashed
```

**After you close 5 tasks in a row (productivity praise):**
```
Five tasks completed
Your productivity frightens
Even the machines
```

**Budget warning:**
```
Tokens flow like rain
Eighty percent of budget
Consider a pause
```

**All clear:**
```
No tasks await you
All agents rest quietly
Peace in the codebase
```

### 4.3 Configuration

```yaml
# ~/.gobby/config.yaml
conductor:
  enabled: true
  interval_seconds: 30
  autonomous_mode: false

  personality:
    mode: haiku           # haiku | prose | terse
    humor_setting: 0.15   # TARS-style dry wit (0.0-1.0)
    sass_on_stale_tasks: true
    sass_threshold_hours: 24

  thresholds:
    stale_task_minutes: 60
    stuck_agent_minutes: 15

  llm_mode: hybrid        # template | api | hybrid
  api_model: claude-3-haiku-20240307
```

### 4.4 Hybrid LLM Strategy

```
┌─────────────────────────────────────────────────────────────────┐
│                    Haiku Generation                              │
├─────────────────────────────────────────────────────────────────┤
│  Common States (Templates - FREE):                               │
│  • "all_clear" → "No tasks await / All agents rest quietly      │
│                   / Peace in the codebase"                       │
│  • "tasks_waiting" → "N tasks await you / Ready for your        │
│                       attention / Choose wisely, friend"         │
│  • "agent_stuck" → "Agent sits idle / Minutes pass without      │
│                     word / Perhaps check on them"                │
│                                                                  │
│  Novel Situations (Claude API):                                  │
│  • Complex multi-issue summaries                                 │
│  • Unexpected error patterns                                     │
│  • Custom user queries via `gobby conductor chat`                │
└─────────────────────────────────────────────────────────────────┘
```

**Implementation:**
```python
class HaikuGenerator:
    TEMPLATES = {
        "all_clear": "No tasks await you\nAll agents rest quietly\nPeace in the codebase",
        "tasks_waiting": "{n} tasks await you\nReady for your attention\nChoose wisely, friend",
        "agent_stuck": "Agent sits idle\nMinutes pass without a word\nPerhaps check on them",
        # ... more templates
    }

    async def generate(self, context: ConductorContext) -> str:
        # Try template first
        if template := self._match_template(context):
            return template.format(**context.to_dict())

        # Fall back to API for novel situations
        return await self._generate_via_api(context)
```

---

## 5. Task Status Flow & Review Gates

### 5.1 Status Flow Diagram

```
pending → in_progress → pending_review → completed
                 ↑              │
                 └──────────────┘  (reopen if review fails)
```

**Flow explanation:**
1. Task starts as `pending`
2. Agent picks up task → `in_progress`
3. Agent completes work → `pending_review` (awaiting orchestrator review)
4. Orchestrator approves → `completed`
5. Orchestrator finds issues → `reopen` back to `in_progress`, fix, close again

### 5.2 `pending_review` Status

When `close_task` is called by an agent (session.agent_depth > 0), it transitions to `pending_review` instead of `completed`. This creates a review gate where the orchestrator must approve the work.

**Schema change:**
```sql
-- Add pending_review_at timestamp
ALTER TABLE tasks ADD COLUMN pending_review_at TIMESTAMP;
```

**Logic in close_task:**
```python
def close_task(task_id: str, commit_sha: str, force_complete: bool = False):
    session = get_current_session()

    if session.agent_depth > 0 and not force_complete:
        # Agent closes to pending_review
        task.status = "pending_review"
        task.pending_review_at = datetime.utcnow()
    else:
        # Orchestrator closes to completed
        task.status = "completed"
        task.completed_at = datetime.utcnow()
```

### 5.3 Blocking Wait Tools

**`wait_for_task(task_id, timeout_seconds=300, poll_interval=5)`**

Polls task status until it leaves `in_progress`. Returns when task becomes `pending_review` or `completed`.

```python
wait_for_task(task_id: str, timeout_seconds: int = 300) -> TaskStatus
# Returns: task data with status, commit_sha, worktree_path
# Timeout: returns with current state + timed_out=True
```

**`wait_for_any_task(task_ids, timeout_seconds=300)`**

Polls multiple tasks, returns when ANY task leaves `in_progress`.

```python
wait_for_any_task(task_ids: List[str], timeout_seconds: int) -> (task_id, status)
# Returns: first completed task data + remaining task_ids still in progress
```

**`wait_for_all_tasks(task_ids, timeout_seconds=600)`**

Polls multiple tasks, returns when ALL tasks leave `in_progress` (or timeout).

```python
wait_for_all_tasks(task_ids: List[str], timeout_seconds: int) -> Dict[str, status]
# Returns: dict of task_id -> task data with their statuses
```

### 5.4 Task Reopen Capability

**`reopen_task(task_id, reason=None)`**

Transitions from `pending_review` → `in_progress`. Used when orchestrator finds issues during review.

```python
reopen_task(task_id: str, reason: str = None) -> Task
# - Transitions status back to in_progress
# - Clears commit_sha (new work incoming)
# - Logs reopen reason for debugging
# - Allows orchestrator to fix and re-close
```

---

## 6. Worktree Agent Restrictions

### 6.1 Design Principle (Agent Sandboxing)

**Critical design principle**: Agents spawned in worktrees are sandboxed to ONE task. They cannot navigate the task tree, spawn agents, or manage worktrees. This prevents runaway agent chains and keeps orchestration authority with the parent.

### 6.2 ALLOWED Tools (Complete List)

```
# Task tools (minimal set)
gobby-tasks.get_task          # See assigned task details
gobby-tasks.update_task       # Set status to in_progress
gobby-tasks.close_task        # Signal completion with commit_sha

# Memory (optional)
gobby-memory.remember         # Store learnings
gobby-memory.recall           # Retrieve context
gobby-memory.forget           # Remove memories

# All upstream MCP tools (context7, etc.)
# All native file/code tools (read, write, edit, bash, glob, grep)
```

### 6.3 BLOCKED Tools (Complete List)

```
# Task navigation (orchestrator's job)
gobby-tasks.list_tasks
gobby-tasks.list_ready_tasks
gobby-tasks.suggest_next_task
gobby-tasks.create_task
gobby-tasks.expand_task
gobby-tasks.expand_from_spec
gobby-tasks.validate_task_tree

# Agent/worktree management (orchestrator's job)
gobby-agents.*                # No spawning subagents
gobby-worktrees.*             # No managing worktrees
gobby-workflows.set_*         # No changing workflows

# Wait tools (orchestrator only)
gobby-tasks.wait_for_task
gobby-tasks.wait_for_any_task
gobby-tasks.wait_for_all_tasks
```

### 6.4 Worktree Agent Workflow YAML

```yaml
# src/gobby/workflows/definitions/worktree-agent.yaml
name: worktree-agent
description: Restricted workflow for agents working in worktrees
auto_activate_on: worktree_spawn

tool_allowlist:
  gobby-tasks:
    - get_task
    - update_task
    - close_task
  gobby-memory:
    - remember
    - recall
    - forget
  # All other gobby-* servers blocked by default

# Allow all upstream MCP servers
upstream_servers: allow_all

steps:
  - name: work
    description: Execute the assigned task
    # No step transitions - single continuous work phase
```

**Auto-activation**: When `spawn_agent_in_worktree` is called, the worktree-agent workflow auto-activates on the spawned session. The workflow tool filtering enforces the restrictions.

---

## 7. Inter-Agent Messaging

### 7.1 Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    Inter-Session Messages                        │
├─────────────────────────────────────────────────────────────────┤
│ id | from_session | to_session | content | sent_at | read_at    │
└─────────────────────────────────────────────────────────────────┘
```

**Storage**: SQLite table `inter_session_messages` with:
- `id` (UUID)
- `from_session` (session_id of sender)
- `to_session` (session_id of recipient)
- `content` (message text)
- `priority` (normal, urgent)
- `sent_at` (timestamp)
- `read_at` (timestamp, nullable)

### 7.2 Message Tools

**`send_to_parent(message, priority="normal")`**

Child agent sends message to parent session.

```python
send_to_parent(message: str, priority: str = "normal") -> dict
# Returns: {"message_id": "...", "sent_at": "..."}
```

**`send_to_child(run_id, message)`**

Parent sends message to child agent session.

```python
send_to_child(run_id: str, message: str) -> dict
# Returns: {"message_id": "...", "sent_at": "..."}
```

**`poll_messages(unread_only=True)`**

Get pending messages for current session.

```python
poll_messages(unread_only: bool = True) -> list[dict]
# Returns: [{"id": "...", "from": "...", "content": "...", "sent_at": "...", "priority": "..."}]
```

**`mark_read(message_id)`**

Mark message as read.

```python
mark_read(message_id: str) -> dict
# Returns: {"success": true, "read_at": "..."}
```

### 7.3 Integration with Review Loop (Sequence Diagram)

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

**WebSocket Integration**: Messages broadcast `message_sent` events on WebSocket for real-time notification. Polling fallback for CLI agents that don't maintain WS connection.

---

## 8. Orchestration Workflows

### 8.1 Sequential Orchestrator Pattern

**When to use**: Dependent tasks, limited resources, simpler review, learning the system.

**Step-by-step workflow**:
1. Set `session_task` to epic ID, activate `sequential-orchestrator` workflow
2. Loop:
   a. `suggest_next_task()` → get ready subtask
   b. `create_worktree(branch=f"feature/{task_id}")`
   c. `spawn_agent_in_worktree(task_id, provider="gemini")`
   d. `wait_for_task(task_id, timeout=600)`
   e. Review code at worktree_path
   f. If good: `merge_worktree()` → `approve_and_cleanup()`
   g. If bad: `reopen_task()`, fix in worktree, `close_task()`
3. Repeat until no ready tasks

**YAML Definition**:
```yaml
# src/gobby/workflows/definitions/sequential-orchestrator.yaml
name: sequential-orchestrator
description: Process epic subtasks one at a time with worktree agents

steps:
  - name: select_task
    allowed_tools: [list_ready_tasks, suggest_next_task, get_task]

  - name: spawn_agent
    allowed_tools: [create_worktree, spawn_agent_in_worktree]

  - name: wait
    allowed_tools: [wait_for_task]

  - name: review
    allowed_tools: [read, glob, grep, get_worktree_status]

  - name: decide
    allowed_tools: [merge_worktree, approve_and_cleanup, reopen_task, close_task]

  - name: loop
    transitions:
      - condition: "has_ready_tasks"
        next: select_task
      - condition: "no_ready_tasks"
        next: complete
```

### 8.2 Parallel Orchestrator Pattern

**When to use**: Independent tasks, faster throughput, available resources, overnight batch processing.

**Workflow with max_parallel**:
1. Set `session_task` to epic ID, activate `parallel-orchestrator` workflow
2. Spawn phase:
   a. `list_ready_tasks()` → get up to N independent tasks
   b. For each: `create_worktree()` + `spawn_agent_in_worktree()`
   c. Track: {task_id: worktree_id} mapping
3. Wait phase:
   a. `wait_for_any_task(task_ids)` → returns first completed
   b. Review completed task's worktree
   c. Merge/approve or reopen/fix
   d. If agents still running: goto 3a
4. Refill phase:
   a. If ready tasks remain and slots available: spawn more
   b. Goto wait phase
5. Complete when all tasks done

**YAML Definition**:
```yaml
# src/gobby/workflows/definitions/parallel-orchestrator.yaml
name: parallel-orchestrator
description: Process multiple subtasks in parallel worktrees

config:
  max_parallel_worktrees: 3

steps:
  - name: select_batch
    allowed_tools: [list_ready_tasks, get_task]

  - name: spawn_batch
    allowed_tools: [create_worktree, spawn_agent_in_worktree]
    # Called N times for N tasks

  - name: wait_any
    allowed_tools: [wait_for_any_task, wait_for_all_tasks]

  - name: review_completed
    allowed_tools: [read, glob, grep, get_worktree_status]

  - name: process_completed
    allowed_tools: [merge_worktree, approve_and_cleanup, reopen_task]

  - name: loop
    transitions:
      - condition: "agents_still_running"
        next: wait_any
      - condition: "has_ready_tasks"
        next: select_batch
      - condition: "all_done"
        next: complete
```

### 8.3 Target Workflow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│  Claude (Orchestrator) - auto-task mode with session_task=epic │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
    ┌─────────────────┐
    │ 1. Create       │
    │    worktree     │
    └────────┬────────┘
             │
         ▼
    ┌─────────────────┐
    │ 2. Spawn Agent  │
    │    on task      │
    └────────┬────────┘
             │
         ▼
    ┌─────────────────┐
    │ 3. Wait for     │  ← BLOCKING WAIT (wait_for_task)
    │    completion   │
    └────────┬────────┘
             │
         ▼
    ┌─────────────────┐
    │ 4. Review code  │  ← Read files from worktree path
    │    in worktree  │
    └────────┬────────┘
             │
         ▼
    ┌──────────────────────────────────────┐
    │ 5. Quality check                     │
    │    ├─ GOOD → merge to dev, close     │
    │    └─ BAD → reopen, fix, close       │
    └────────┬─────────────────────────────┘
             │
         ▼
    ┌─────────────────┐
    │ 6. Delete       │
    │    worktree     │
    └────────┬────────┘
             │
         ▼
    ┌─────────────────┐
    │ 7. Next task    │  ← Loop until epic exhausted
    │    in epic      │
    └─────────────────┘
```

---

## 9. Token Budget & Throttling

### 9.1 Token Tracking

We already capture per-session tokens in the `sessions` table via `SessionLifecycleManager`. Need to add:
1. Model tracking (for pricing)
2. Aggregation queries
3. Pricing calculation
4. Budget enforcement

**Schema change**:
```sql
ALTER TABLE sessions ADD COLUMN model TEXT;  -- e.g., "claude-opus-4-5-20251101"
```

### 9.2 Pricing Data

```python
# src/gobby/conductor/pricing.py
ANTHROPIC_PRICING = {
    # Per 1M tokens (from Anthropic pricing page)
    "claude-opus-4-5-20251101": {
        "input": 15.00,
        "output": 75.00,
        "cache_write": 18.75,
        "cache_read": 1.50
    },
    "claude-sonnet-4-20250514": {
        "input": 3.00,
        "output": 15.00,
        "cache_write": 3.75,
        "cache_read": 0.30
    },
    "claude-3-5-haiku-20241022": {
        "input": 0.80,
        "output": 4.00,
        "cache_write": 1.00,
        "cache_read": 0.08
    },
}

GOOGLE_PRICING = {
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00},
    "gemini-2.5-flash": {"input": 0.075, "output": 0.30},
}
```

### 9.3 Budget Configuration

```yaml
# ~/.gobby/config.yaml
conductor:
  token_budget:
    weekly_limit: null       # null = no limit, or dollar amount (e.g., 50.00)
    warning_threshold: 0.8   # alert at 80%
    throttle_threshold: 0.9  # pause spawning at 90%
    tracking_window_days: 7
```

### 9.4 Throttling Logic

```python
# src/gobby/conductor/token_tracker.py
class TokenTracker:
    def get_usage_summary(self, days: int = 7) -> UsageSummary:
        """Aggregate token usage across sessions in time window."""
        query = """
        SELECT
            model,
            SUM(usage_input_tokens) as input_tokens,
            SUM(usage_output_tokens) as output_tokens,
            SUM(usage_cache_creation_tokens) as cache_write,
            SUM(usage_cache_read_tokens) as cache_read
        FROM sessions
        WHERE created_at > datetime('now', ?)
        GROUP BY model
        """
        # Calculate costs using pricing data

    def get_budget_status(self) -> BudgetStatus:
        """Get current budget utilization."""
        usage = self.get_usage_summary()
        limit = self.config.token_budget.weekly_limit

        if limit is None:
            return BudgetStatus(used=usage.total_cost_usd, limit=None, percentage=0.0, can_spawn=True)

        percentage = usage.total_cost_usd / limit
        can_spawn = percentage < self.config.token_budget.throttle_threshold

        return BudgetStatus(used=usage.total_cost_usd, limit=limit, percentage=percentage, can_spawn=can_spawn)

    def can_spawn_agent(self) -> bool:
        """Check if we're under throttle threshold."""
        return self.get_budget_status().can_spawn
```

### 9.5 API & MCP Tools

```python
@dataclass
class UsageSummary:
    input_tokens: int
    output_tokens: int
    cache_write_tokens: int
    cache_read_tokens: int
    total_cost_usd: float
    by_model: dict[str, ModelUsage]
    window_days: int

# MCP Tool (gobby-metrics server)
def get_usage_report(days: int = 7) -> UsageSummary:
    """Get token usage report for the specified time window."""
    return token_tracker.get_usage_summary(days)

def get_budget_status() -> BudgetStatus:
    """Get current budget utilization status."""
    return token_tracker.get_budget_status()
```

---

## 10. Alert System & callme Integration

### 10.1 What is callme?

[callme](https://github.com/ZeframLou/call-me) is a Claude Code plugin that enables Claude to initiate **phone calls** to notify you about task completion, blockers, or when decisions are needed. It supports multi-turn voice conversations during task execution.

**Key capability:** "Start a task, walk away. Your phone/watch rings when Claude is done, stuck, or needs a decision."

### 10.2 Alert Priorities

| Priority | Behavior |
|----------|----------|
| `info` | Log only, no notification |
| `normal` | Log + optional terminal bell |
| `urgent` | Log + WebSocket broadcast (for dashboards) |
| `critical` | **Phone call via callme** (if configured) |

### 10.3 callme Installation

```bash
# Install the callme plugin
/plugin marketplace add ZeframLou/call-me
/plugin install callme@callme
# Restart Claude Code after installation
```

### 10.4 callme Configuration

**Required accounts:**
- **Phone Provider**: Telnyx (recommended, ~$0.007/min) or Twilio (~$0.014/min)
- **OpenAI API Key**: For speech-to-text and text-to-speech (~$0.03/min)
- **ngrok Account**: Free tier for webhook tunneling

**Environment variables** (store in `~/.claude/settings.json`):

| Variable | Purpose |
|----------|---------|
| `CALLME_PHONE_PROVIDER` | `"telnyx"` or `"twilio"` |
| `CALLME_PHONE_ACCOUNT_SID` | Provider account identifier |
| `CALLME_PHONE_AUTH_TOKEN` | Provider authentication credential |
| `CALLME_PHONE_NUMBER` | Claude's outbound phone number (E.164 format) |
| `CALLME_USER_PHONE_NUMBER` | Your receiving phone number |
| `CALLME_OPENAI_API_KEY` | OpenAI credentials for voice processing |
| `CALLME_NGROK_AUTHTOKEN` | ngrok tunnel authentication |

**Optional variables:**
- `CALLME_TTS_VOICE`: Voice selection (default: `"onyx"`)
- `CALLME_PORT`: Server port (default: `3333`)
- `CALLME_TRANSCRIPT_TIMEOUT_MS`: Speech timeout (default: `180000`ms)

### 10.5 callme Tools

The conductor uses these MCP tools from the callme plugin:

```python
# Start a phone call with initial message
initiate_call(message: str) -> {call_id: str, response: str}

# Continue conversation on active call
continue_call(call_id: str, message: str) -> str

# One-way message (Claude proceeds without waiting)
speak_to_user(message: str) -> None

# End the call gracefully
end_call(call_id: str) -> None
```

### 10.6 Integration Flow Diagram

```
Conductor Loop
    │
    ├─► Detects stuck agent (15 min threshold)
    │
    ├─► Priority = critical? Yes →
    │                              │
    │                              ▼
    │                    ┌─────────────────────┐
    │                    │  initiate_call()    │
    │                    │  "Hey! Your Gemini  │
    │                    │  agent seems stuck. │
    │                    │  Want me to check?" │
    │                    └─────────┬───────────┘
    │                              │
    │                              ▼
    │                    ┌─────────────────────┐
    │                    │  User responds      │
    │                    │  via phone          │
    │                    └─────────┬───────────┘
    │                              │
    │                              ▼
    │                    ┌─────────────────────┐
    │                    │  continue_call()    │
    │                    │  with follow-up     │
    │                    └─────────────────────┘
    │
    └─► Priority < critical → Log + WebSocket broadcast
```

### 10.7 Use Cases

```
┌─────────────────────────────────────────────────────────────────┐
│  Conductor detects problem → CALLS YOU (phone) via callme        │
├─────────────────────────────────────────────────────────────────┤
│  • Agent stuck for 15+ min → "Hey! Your Gemini agent seems       │
│    stuck on task forty-seven. Should I restart it or wait?"      │
│                                                                  │
│  • Task blocked → "Task forty-seven needs a decision. The auth   │
│    system could use OAuth or JWT. Which do you prefer?"          │
│                                                                  │
│  • Token budget critical → "You're at ninety percent of your     │
│    weekly budget. Should I pause spawning new agents?"           │
│                                                                  │
│  • Epic complete → "Great news! All five subtasks in the auth    │
│    epic are done and merged. Ready for you to review."           │
└─────────────────────────────────────────────────────────────────┘
```

### 10.8 Cost Estimates

| Service | Cost |
|---------|------|
| Telnyx outbound | ~$0.007/min |
| Twilio outbound | ~$0.014/min |
| Monthly phone number | ~$1.00-1.15 |
| OpenAI transcription | ~$0.006/min |
| OpenAI synthesis | ~$0.02/min |
| **Total per call** | **~$0.03-0.04/min** |

A typical alert call (30 seconds) costs approximately $0.02.

---

## 11. Documentation Updates

### 11.1 GEMINI.md (Worktree Agent Mode)

Add this section to GEMINI.md:

```markdown
## Worktree Agent Mode

When spawned in a worktree by an orchestrator (Claude):

**Your scope is LIMITED to one task.** You cannot create tasks, expand epics,
spawn agents, or manage worktrees. Focus on the assigned task only.

### Available Tools
- `get_task(task_id)` - View your assigned task details
- `update_task(task_id, status="in_progress")` - Mark task active
- `close_task(task_id, commit_sha)` - Signal completion
- All file/code tools and upstream MCP servers

### Workflow
1. `get_task(<your-task-id>)` - understand the requirement
2. `update_task(status="in_progress")` - BEFORE any edits
3. Do the work, commit with `[task-id]` prefix
4. `close_task(commit_sha="<sha>")` - signals orchestrator you're done
5. Session ends, orchestrator reviews your work

### You CANNOT
- Create, expand, or navigate tasks
- Spawn subagents or manage worktrees
- Pick your next task (orchestrator decides)
```

### 11.2 CLAUDE.md (Orchestrator Patterns)

Add this section to CLAUDE.md:

```markdown
## Autonomous Task Orchestration

### Sequential Pattern (One at a time)

Best for: dependent tasks, limited resources, simpler review

1. Set `session_task` to epic ID, activate `sequential-orchestrator` workflow
2. Loop:
   a. `suggest_next_task()` → get ready subtask
   b. `create_worktree(branch=f"feature/{task_id}")`
   c. `spawn_agent_in_worktree(task_id, provider="gemini")`
   d. `wait_for_task(task_id, timeout=600)`
   e. Review code at worktree_path
   f. If good: `merge_worktree()` → `approve_and_cleanup()`
   g. If bad: `reopen_task()`, fix in worktree, `close_task()`
3. Repeat until no ready tasks

### Parallel Pattern (Multiple simultaneous)

Best for: independent tasks, faster throughput, available resources

1. Set `session_task` to epic ID, activate `parallel-orchestrator` workflow
2. Spawn phase:
   a. `list_ready_tasks()` → get up to N independent tasks
   b. For each: `create_worktree()` + `spawn_agent_in_worktree()`
   c. Track: {task_id: worktree_id} mapping
3. Wait phase:
   a. `wait_for_any_task(task_ids)` → returns first completed
   b. Review completed task's worktree
   c. Merge/approve or reopen/fix
   d. If agents still running: goto 3a
4. Refill phase:
   a. If ready tasks remain and slots available: spawn more
   b. Goto wait phase
5. Complete when all tasks done
```

### 11.3 gobby-merge Skill

Add skill file `src/gobby/install/claude/skills/gobby-merge/SKILL.md`:

```markdown
---
description: This skill should be used when the user asks to "/gobby-merge",
"merge worktree", "resolve conflicts", "merge to dev". Manage AI-powered
merge conflict resolution - start merges, resolve conflicts, apply resolutions.
version: "1.0"
---

# /gobby-merge - Merge Conflict Resolution Skill

## Core Subcommands

### `/gobby-merge start <worktree-id>` - Start merge operation
Call `gobby-merge.merge_start` with:
- `worktree_id`: (required) Worktree to merge
- `source_branch`: Branch being merged (auto-detected from worktree)
- `target_branch`: Target branch (default: "dev")
- `strategy`: "auto", "conflict_only", "full_file", "manual"

### `/gobby-merge status <resolution-id>` - Get merge status
Call `gobby-merge.merge_status` with:
- `resolution_id`: (required) Resolution ID from merge_start

### `/gobby-merge resolve <conflict-id>` - Resolve conflict
Call `gobby-merge.merge_resolve` with:
- `conflict_id`: (required) Conflict to resolve
- `resolved_content`: Manual resolution (skips AI)
- `use_ai`: Use AI resolution (default: true)

### `/gobby-merge apply <resolution-id>` - Apply and complete
Call `gobby-merge.merge_apply` with:
- `resolution_id`: (required) Resolution to apply

### `/gobby-merge abort <resolution-id>` - Abort merge
Call `gobby-merge.merge_abort` with:
- `resolution_id`: (required) Resolution to abort

## Resolution Tiers
1. **git_auto** - Git handles it (no conflicts)
2. **conflict_only_ai** - Send only conflict hunks to LLM
3. **full_file_ai** - Send full file for complex conflicts
4. **human_review** - Escalate to human

## Workflow Example
1. `merge_start(worktree_id)` - Start merge, get resolution_id
2. If conflicts: `merge_status(resolution_id)` - See conflicts
3. For each conflict: `merge_resolve(conflict_id)` - AI or manual
4. `merge_apply(resolution_id)` - Complete merge
```

---

## 12. Implementation Phases

### Phase A: Inter-Agent Messaging Foundation

**Goal**: Enable parent↔child message passing during agent execution

**Files to create/modify**:
- `src/gobby/storage/inter_session_messages.py` - Message storage with `from_session`, `to_session`, `content`, `sent_at`, `read_at`
- `src/gobby/storage/migrations.py` - Add `inter_session_messages` table
- `src/gobby/mcp_proxy/tools/agents.py` - Add messaging tools

**New MCP Tools**:
```python
send_to_parent(message: str, priority: str = "normal") -> message_id
send_to_child(run_id: str, message: str) -> message_id
poll_messages(unread_only: bool = True) -> List[Message]
mark_read(message_id: str) -> bool
```

**WebSocket Integration**:
- Broadcast `message_sent` events on WebSocket for real-time notification
- Polling fallback for CLI agents that don't maintain WS connection

**Live Test Deliverable**: Terminal split demo
- Left pane: Claude (parent) session
- Right pane: Gemini (child) agent spawned in worktree
- Demo flow:
  1. Claude spawns Gemini via `spawn_agent_in_worktree`
  2. Claude sends message: `send_to_child(run_id, "Please confirm you received this")`
  3. Gemini polls: `poll_messages()` → sees message
  4. Gemini responds: `send_to_parent("Message received, starting work")`
  5. Claude polls: `poll_messages()` → sees response

### Phase B: Task Status Extensions

**Goal**: Support review workflow with `pending_review` status

**Files to modify**:
- `src/gobby/storage/tasks.py` - Add `pending_review` status + `pending_review_at` timestamp
- `src/gobby/mcp_proxy/tools/tasks.py` - Modify `close_task` behavior based on agent context
- `src/gobby/mcp_proxy/tools/task_sync.py` - Handle `pending_review` in JSONL

**Logic Change**:
- When `close_task` called by agent (session.agent_depth > 0) → transitions to `pending_review`
- When called by orchestrator → transitions to `completed`

**New MCP Tools**:
```python
wait_for_task(task_id: str, timeout_seconds: int = 300) -> TaskStatus
wait_for_any_task(task_ids: List[str], timeout_seconds: int) -> (task_id, status)
wait_for_all_tasks(task_ids: List[str], timeout_seconds: int) -> Dict[str, status]
reopen_task(task_id: str, reason: str) -> Task
approve_and_cleanup(task_id: str, worktree_id: str) -> bool
```

### Phase C: Interactive Orchestration Workflows

**Goal**: Enable human-driven sequential and parallel review loops

**Files to create**:
- `src/gobby/workflows/definitions/worktree-agent.yaml` - Tool restrictions for spawned agents
- `src/gobby/workflows/definitions/sequential-orchestrator.yaml` - Step-by-step orchestration
- `src/gobby/workflows/definitions/parallel-orchestrator.yaml` - Multi-agent orchestration

**Changes to spawn_agent_in_worktree**:
- Auto-set `workflow="worktree-agent"` if not specified
- Pass task_id via environment or prompt injection
- Workflow activates on session start hook

### Phase D: Token Budget & Throttling

**Goal**: Enable resource-aware autonomous operation with accurate cost tracking

**Files to create/modify**:
- `src/gobby/storage/sessions.py` - Add `model` column, aggregation queries
- `src/gobby/storage/migrations.py` - Migration for model column
- `src/gobby/sessions/transcripts/claude.py` - Extract model from JSONL
- `src/gobby/conductor/token_tracker.py` - Aggregation + pricing + budget API
- `src/gobby/conductor/pricing.py` - Model pricing data
- `src/gobby/config/app.py` - Budget configuration

### Phase E: Conductor Daemon (Autonomous Mode)

**Goal**: Persistent daemon that monitors and acts on task backlog

**Files to create**:
- `src/gobby/conductor/__init__.py` - Module init
- `src/gobby/conductor/loop.py` - Main ConductorLoop class
- `src/gobby/conductor/monitors/tasks.py` - Stale task detection
- `src/gobby/conductor/monitors/agents.py` - Stuck agent detection
- `src/gobby/conductor/haiku.py` - TARS personality generator
- `src/gobby/conductor/alerts.py` - callme integration
- `src/gobby/cli/conductor.py` - CLI commands

**ConductorLoop Behavior**:
```python
class ConductorLoop:
    """Runs as part of gobby daemon, checks every 30s"""

    async def tick(self):
        # 1. Check token budget
        if not self.token_tracker.can_spawn_agent():
            return  # Throttled

        # 2. Check for stuck agents
        for agent in self.registry.get_stuck_agents(threshold_minutes=15):
            await self.alert("agent_stuck", agent, priority="urgent")

        # 3. Check for ready tasks (no blockers)
        ready_tasks = await self.task_manager.list_ready_tasks()

        # 4. Auto-spawn if autonomous mode enabled
        if self.config.autonomous_mode and ready_tasks:
            await self.spawn_next_agent(ready_tasks[0])

        # 5. Generate status haiku
        status = await self.generate_status_haiku()
        await self.broadcast_status(status)
```

### Phase F: Live Integration Testing

**Goal**: Validate the new system end-to-end

**Test Scenarios** (all require new test files in `tests/e2e/`):

1. **WebSocket Message Test** (Phase A validation):
   - Start gobby daemon
   - Spawn agent in terminal (terminal split: left=Claude, right=Gemini)
   - Send message from parent to child via `send_to_child`
   - Verify child receives via `poll_messages`
   - Child responds via `send_to_parent`
   - Verify parent receives

2. **Sequential Review Loop** (Phases B+C validation):
   - Create epic with 2 subtasks
   - Activate `sequential-orchestrator` workflow
   - Watch Claude spawn Gemini on task 1
   - Verify task transitions: `in_progress` → `pending_review`
   - Claude reviews, approves
   - Verify merge and task completion
   - Repeat for task 2

3. **Autonomous Mode** (Phases D+E validation):
   - Seed task backlog with ready tasks
   - Enable autonomous mode in config
   - Start daemon with ConductorLoop
   - Verify auto-spawning respects token budget
   - Trigger alert by making agent "stuck"
   - Verify callme notification

4. **Merge System Live Test** (validate existing gobby-merge - no new code):
   - Create worktree, make conflicting changes
   - Run merge workflow via MCP tools
   - Verify AI conflict resolution works

5. **Token Budget Test** (Phase D validation):
   - Run `get_usage_report(days=7)` via MCP
   - Verify aggregation across recent sessions
   - Verify cost calculation matches expected
   - Test throttling by setting low budget limit

---

## 13. File Summary

### 13.1 New Files to Create

| File | Phase | Purpose |
|------|-------|---------|
| `src/gobby/storage/inter_session_messages.py` | A | Message storage layer |
| `src/gobby/conductor/__init__.py` | D | Conductor module init |
| `src/gobby/conductor/loop.py` | E | Main ConductorLoop daemon |
| `src/gobby/conductor/token_tracker.py` | D | Token aggregation + pricing |
| `src/gobby/conductor/pricing.py` | D | Model pricing data |
| `src/gobby/conductor/haiku.py` | E | TARS personality generator |
| `src/gobby/conductor/alerts.py` | E | callme integration |
| `src/gobby/conductor/monitors/__init__.py` | E | Monitors module init |
| `src/gobby/conductor/monitors/tasks.py` | E | Stale task detection |
| `src/gobby/conductor/monitors/agents.py` | E | Stuck agent detection |
| `src/gobby/cli/conductor.py` | E | CLI commands |
| `src/gobby/workflows/definitions/worktree-agent.yaml` | C | Agent tool restrictions |
| `src/gobby/workflows/definitions/sequential-orchestrator.yaml` | C | Sequential workflow |
| `src/gobby/workflows/definitions/parallel-orchestrator.yaml` | C | Parallel workflow |
| `src/gobby/install/claude/skills/gobby-merge/SKILL.md` | C | Merge skill |

### 13.2 Files to Modify

| File | Changes |
|------|---------|
| `src/gobby/storage/migrations.py` | Add `inter_session_messages` table, `model` column |
| `src/gobby/storage/sessions.py` | Add model column, aggregation queries |
| `src/gobby/storage/tasks.py` | Add `pending_review` status |
| `src/gobby/sessions/transcripts/claude.py` | Extract model from JSONL |
| `src/gobby/mcp_proxy/tools/agents.py` | Add messaging tools |
| `src/gobby/mcp_proxy/tools/tasks.py` | Add wait/reopen tools |
| `src/gobby/mcp_proxy/tools/task_sync.py` | Handle pending_review in JSONL |
| `src/gobby/mcp_proxy/tools/worktrees.py` | Auto-activate worktree-agent workflow |
| `src/gobby/config/app.py` | Add conductor config section |
| `src/gobby/runner.py` | Start ConductorLoop |
| `src/gobby/cli/__init__.py` | Register conductor commands |
| `GEMINI.md` | Add worktree agent instructions |
| `CLAUDE.md` | Add orchestrator workflow docs |

### 13.3 Test Files

| File | Validates |
|------|-----------|
| `tests/e2e/test_inter_agent_messages.py` | Phase A - messaging |
| `tests/e2e/test_sequential_review_loop.py` | Phases B+C |
| `tests/e2e/test_token_budget.py` | Phase D |
| `tests/e2e/test_autonomous_mode.py` | Phase E |
| `tests/e2e/test_worktree_merge_live.py` | Existing merge (validation only) |
| `tests/conductor/test_haiku.py` | TARS personality |
| `tests/conductor/test_token_tracker.py` | Token aggregation |
| `tests/conductor/test_loop.py` | ConductorLoop behavior |

---

## 14. Verification & Testing

### 14.1 Unit Test Requirements

- `close_task` → `pending_review` when session.agent_depth > 0
- `wait_for_task` returns on status change or timeout
- `wait_for_any_task` returns when first task completes
- `wait_for_all_tasks` returns when all tasks complete
- `merge_worktree` performs git merge correctly
- `reopen_task` transitions status back
- SESSION_END handler updates agent_runs
- Token aggregation calculates costs correctly
- Budget throttling respects thresholds
- Haiku templates render correctly

### 14.2 Integration Tests

**Sequential Workflow**:
```bash
# 1. Create epic with subtasks
gobby tasks create "Epic" --type=epic
gobby tasks expand <epic-id>

# 2. Activate sequential workflow
gobby workflows set sequential-orchestrator

# 3. Run orchestration loop manually
gobby tasks suggest-next
gobby worktrees create feature/task-1
gobby worktrees spawn feature/task-1 --task=<task-id> --provider=gemini

# 4. Wait for Gemini to complete, then verify
gobby tasks list --status=pending_review

# 5. Merge using gobby-merge
# Via MCP: merge_start(worktree_id, source_branch, target_branch="dev")

# 6. Approve and cleanup
# Via MCP: approve_and_cleanup(task_id, worktree_id)
```

**Parallel Workflow**:
```bash
# 1. Create epic with 3 independent subtasks
gobby tasks create "Parallel Epic" --type=epic
# ... add subtasks

# 2. Spawn multiple agents
gobby worktrees spawn feature/task-1 --task=<task-1> --provider=gemini
gobby worktrees spawn feature/task-2 --task=<task-2> --provider=gemini

# 3. Wait for any to complete
# (via MCP tool: wait_for_any_task)

# 4. Process completed, spawn more if ready tasks remain
```

### 14.3 End-to-End Tests

**Full Sequential Loop**:
1. Create epic with 2 subtasks
2. Claude activates `sequential-orchestrator` workflow
3. Spawns Gemini for subtask 1, waits, reviews, merges
4. Spawns Gemini for subtask 2, waits, reviews, merges
5. Epic marked complete when all subtasks done

**Full Parallel Loop**:
1. Create epic with 4 independent subtasks
2. Claude activates `parallel-orchestrator` workflow
3. Spawns Gemini in 2 worktrees (max_parallel=2)
4. As each completes: review, merge, spawn next
5. All 4 tasks processed with max 2 concurrent agents

**Autonomous Mode**:
1. Seed task backlog
2. Enable autonomous mode
3. Start conductor: `gobby conductor start --autonomous`
4. Observe auto-spawning
5. Trigger stuck agent alert
6. Verify callme notification

---

## 15. Configuration Reference

### 15.1 Complete YAML Example

```yaml
# ~/.gobby/config.yaml
conductor:
  # Core settings
  enabled: true
  interval_seconds: 30
  autonomous_mode: false

  # Personality
  personality:
    mode: haiku           # haiku | prose | terse
    humor_setting: 0.15   # TARS-style dry wit
    sass_on_stale_tasks: true
    sass_threshold_hours: 24

  # Monitoring thresholds
  thresholds:
    stale_task_minutes: 60
    stuck_agent_minutes: 15

  # LLM settings
  llm_mode: hybrid        # template | api | hybrid
  api_model: claude-3-haiku-20240307

  # Token budget
  token_budget:
    weekly_limit: 50.00   # null = no limit
    warning_threshold: 0.8
    throttle_threshold: 0.9
    tracking_window_days: 7

  # Alerts (callme is configured separately as a Claude Code plugin)
  alerts:
    critical_threshold_minutes: 15  # When to escalate to phone call
    use_callme: true                # Enable phone calls for critical alerts
```

### 15.2 Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `GOBBY_CONDUCTOR_ENABLED` | Enable conductor | `false` |
| `GOBBY_CONDUCTOR_AUTONOMOUS` | Enable auto-spawn | `false` |
| `GOBBY_TOKEN_BUDGET` | Weekly limit in USD | `null` |

**callme environment variables** (see Section 10.4 for full list):

| Variable | Purpose |
|----------|---------|
| `CALLME_PHONE_PROVIDER` | `"telnyx"` or `"twilio"` |
| `CALLME_USER_PHONE_NUMBER` | Your phone number (E.164 format) |
| `CALLME_OPENAI_API_KEY` | OpenAI for voice processing |

---

## Appendix A: Design Decisions

### Confirmed Decisions

1. **Token tracking**: Use existing session-level data + add aggregation/pricing layer (not ccusage dependency)
2. **E2E test location**: `tests/e2e/` directory
3. **WebSocket live test format**: Terminal split - two panes showing Claude parent and Gemini child exchanging messages
4. **Message delivery guarantee**: Persist to database + WebSocket broadcast for real-time + polling fallback
5. **Merge target**: All worktree branches merge to `dev` (not main). Main branch updated via normal PR flow.
6. **Auto-cleanup**: Worktrees auto-deleted after successful merge

### Open Questions

1. **Autonomous mode activation**: CLI flag (`gobby conductor start --autonomous`) AND config file (conductor.autonomous_mode). CLI takes precedence.
2. **Budget units**: Track by dollar amount for user-friendliness, calculate from token counts internally.

---

## Appendix B: Deliverables Summary

| Phase | Key Output | Validates |
|-------|-----------|-----------|
| A | Inter-agent messaging MCP tools | WebSocket + message passing |
| B | `pending_review` status + wait tools | Review gates |
| C | Orchestration workflow definitions | Interactive mode |
| D | Token tracking + throttling | Budget awareness |
| E | ConductorLoop + TARS haikus | Autonomous mode |
| F | Live integration tests | End-to-end system |

---

## Appendix C: Verification Commands

After implementation:

```bash
# 1. Start daemon with verbose logging
gobby start --verbose

# 2. Start conductor
gobby conductor start

# 3. Check conductor status
gobby conductor status

# 4. Run E2E tests
uv run pytest tests/e2e/ -v

# 5. Test autonomous mode
gobby conductor start --autonomous
# Observe auto-spawning behavior

# 6. Chat with conductor
gobby conductor chat "What's the status?"
```
