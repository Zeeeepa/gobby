---
name: tasks
description: This skill should be used when the user asks to "/gobby tasks", "task management", "create task", "list tasks", "close task". Manage gobby tasks - create, list, close, expand, validate, and dependencies.
version: "2.0.0"
category: core
triggers: create task, list tasks, close task, task management
metadata:
  gobby:
    audience: all
    format_overrides:
      autonomous: full
---

# /gobby tasks - Task Management Skill

This skill manages tasks via the gobby-tasks MCP server. Parse the user's input to determine which subcommand to execute.

## Session Context

**IMPORTANT**: Pass your `session_id` from SessionStart context when creating or closing tasks for tracking.

Look for `Gobby Session Ref:` or `Gobby Session ID:` in your system context:
```
Gobby Session Ref: #5
Gobby Session ID: <uuid>
```

**Note**: All `session_id` parameters accept #N, N, UUID, or prefix formats.

## Tool Schema Reminder

**First time calling a tool this session?** Use `get_tool_schema(server_name, tool_name)` before `call_tool` to get correct parameters. Schemas are cached per session—no need to refetch.

## Task ID Formats

Tasks can be referenced by:
- `#N` - Short number (e.g., `#1`, `#47`)
- `path` - Hierarchical path (e.g., `1.2.3`)
- `UUID` - Full task ID

## Core Subcommands

### `/gobby tasks create <title>` - Create a new task
Call `create_task` with:
- `title`: (required) The task title
- `session_id`: (required) Your session ID from SessionStart context
- `description`: Detailed description
- `task_type`: "task" (default), "bug", "feature", or "epic"
- `priority`: 1=High, 2=Medium (default), 3=Low
- `parent_task_id`: Optional parent task
- `blocks`: List of task IDs this task blocks
- `depends_on`: List of task IDs this task depends on (must complete first)
- `labels`: List of labels
- `category`: "code", "config", "docs", "refactor", "test", "research", "planning", or "manual"
- `validation_criteria`: Acceptance criteria

**Auto-claim**: When both `session_id` AND `claim=true` are provided, the task is automatically claimed (status set to `in_progress`, assignee set to your session). Default: `claim=false`.

Example: `/gobby tasks create Fix login button` → `create_task(title="Fix login button", session_id="<your_session_id>")`
Example: `/gobby tasks create Add OAuth support --type=feature` → `create_task(title="Add OAuth support", task_type="feature", session_id="<your_session_id>")`
Example: `/gobby tasks create Integrate API --depends-on=#1,#2` → `create_task(title="Integrate API", depends_on=["#1", "#2"], session_id="<your_session_id>")`

### `/gobby tasks show <task-id>` - Show task details
Call `get_task` with:
- `task_id`: (required) Task reference

Displays full task details including description, status, validation criteria, dependencies.

Example: `/gobby tasks show #1` → `get_task(task_id="#1")`

### `/gobby tasks update <task-id>` - Update task fields
Call `update_task` with:
- `task_id`: (required) Task reference
- `title`, `description`, `status`, `priority`, `assignee`, `labels`, `validation_criteria`, `category`, etc.

Example: `/gobby tasks update #1 status=in_progress` → `update_task(task_id="#1", status="in_progress")`

### `/gobby tasks claim <task-id>` - Claim a task for your session
Call `claim_task` with:
- `task_id`: (required) Task reference
- `session_id`: (required) Your session ID from SessionStart context
- `force`: Override existing claim by another session (default: false)

Atomically sets assignee to your session_id and status to `in_progress`. Detects conflicts if already claimed by another session.

**Conflict behavior**:
- If task is unclaimed: claims successfully
- If claimed by same session: succeeds (idempotent)
- If claimed by another session: returns error unless `force=true`

Example: `/gobby tasks claim #1` → `claim_task(task_id="#1", session_id="<your_session_id>")`
Example: `/gobby tasks claim #1 --force` → `claim_task(task_id="#1", session_id="<your_session_id>", force=true)`

### `/gobby tasks list [status]` - List tasks
Call `list_tasks` with:
- `status`: Filter (open, in_progress, needs_review, closed, or comma-separated)
- `priority`: Filter by priority
- `task_type`: Filter by type
- `assignee`: Filter by assignee
- `label`: Filter by label
- `parent_task_id`: Filter by parent
- `title_like`: Fuzzy title match
- `limit`: Max results (default 50)
- `all_projects`: List from all projects

Example: `/gobby tasks list` → `list_tasks(status="open")`
Example: `/gobby tasks list in_progress` → `list_tasks(status="in_progress")`

### `/gobby tasks close <task-id>` - Close a task
Call `close_task` with:
- `task_id`: (required) Task reference
- `reason`: "completed" (default), "duplicate", "already_implemented", "wont_fix", "obsolete", "out_of_repo"
- `changes_summary`: (required) Summary of what was changed and why. For no-work closes, explain why no changes were needed.
- `commit_sha`: Git commit SHA to link
- `skip_validation`: Skip LLM validation (requires justification)
- `override_justification`: Why skipping validation
- `session_id`: Your session ID for tracking

**IMPORTANT**: Commit changes first, then close with commit SHA.

**Edge cases (no work done):** Use `reason` to close without a commit:
- `reason="already_implemented"` - Task was already done
- `reason="obsolete"` - Task is no longer needed
- `reason="duplicate"` - Task duplicates another
- `reason="wont_fix"` - Decided not to do it
- `reason="out_of_repo"` - Changes outside repo (e.g., ~/.gobby/config.yaml)

**Review routing**: Tasks may route to `review` status instead of `closed` when:
- Task has `requires_user_review=true`, OR
- `skip_validation=true` with `override_justification`

Returns `routed_to_review: true` if task was sent to review instead of closed.

Example: `/gobby tasks close #1` → First commit, then `close_task(task_id="#1", commit_sha="<sha>")`

### `/gobby tasks reopen <task-id>` - Reopen a closed or review task
Call `reopen_task` with:
- `task_id`: (required) Task reference
- `append_description`: Additional context for reopening

Works on both `closed` and `review` status tasks. Resets `accepted_by_user` to false.

Example: `/gobby tasks reopen #1` → `reopen_task(task_id="#1")`

### `/gobby tasks delete <task-id>` - Delete a task
Call `delete_task` with:
- `task_id`: (required) Task reference
- `cascade`: If true, delete subtasks AND dependent tasks (default: true)
- `unlink`: If true, remove dependency links but preserve dependent tasks
  - **Note**: `unlink` only takes effect when `cascade=false`. If `cascade=true` (default), `unlink` is ignored.

By default, deletes the task and all subtasks/dependents. If the task has dependents and neither
`cascade` nor `unlink` is set, returns an error with suggestions.

Example: `/gobby tasks delete #1` → `delete_task(task_id="#1")` (cascade delete, default)
Example: `/gobby tasks delete #1 --no-cascade --unlink` → `delete_task(task_id="#1", cascade=false, unlink=true)` (preserve dependents)

## Expansion & Planning

### `/gobby tasks expand <task-id>` - Expand into subtasks
Call `expand_task` with:
- `task_id`: (required) Task to expand
- `context`: Additional context for expansion
- `enable_web_research`: Use web for research
- `enable_code_context`: Include code context
- `generate_validation`: Generate criteria for subtasks
- `iterative`: Set to `true` for epics to cascade through all phases
- `session_id`: Your session ID

**For epics with multiple phases**, use iterative mode and loop until complete:
```python
while True:
    result = call_tool("gobby-tasks", "expand_task", {
        "task_id": "#100",
        "iterative": True,
        "session_id": "<session_id>"
    })
    # Report progress
    print(f"Expanded {result['expanded_ref']}, {result['unexpanded_epics']} remaining")
    if result.get("complete"):
        break
```

Response includes:
- `expanded_ref`: The task that was actually expanded (may differ from input in iterative mode)
- `unexpanded_epics`: Count of remaining unexpanded epics
- `complete`: True when all epics in tree are expanded

Example: `/gobby tasks expand #1` → `expand_task(task_id="#1")`
Example (epic cascade): `/gobby tasks expand #1 --cascade` → loops with `iterative=True`

**When user runs `/gobby tasks expand` on an epic:**
1. Check if the task has `task_type=epic`
2. If epic, recommend cascade: "This epic has phases. Would you like me to expand them all (cascade), or just this one?"
3. For cascade, use iterative mode and report progress after each phase
4. Report progress: "Expanded Phase 1 (#4015), 6 phases remaining..."
5. Continue until `complete=True`

### `/gobby tasks suggest` - Suggest next task
Call `suggest_next_task` with:
- `session_id`: **Required** - your session ID (from system context)
- `task_type`: Optional type filter
- `prefer_subtasks`: Prefer leaf tasks (default true)
- `parent_id`: Scope to specific epic/feature hierarchy

Returns the highest-priority ready task, auto-scoped via workflow's session_task variable.

Example: `/gobby tasks suggest` → `suggest_next_task(session_id="<your_session_id>")`

### `/gobby tasks ready` - List ready tasks
Call `list_ready_tasks` with:
- `priority`, `task_type`, `assignee`, `parent_task_id`, `limit`

Lists tasks with no blocking dependencies.

Example: `/gobby tasks ready` → `list_ready_tasks()`

### `/gobby tasks blocked` - List blocked tasks
Call `list_blocked_tasks` to see tasks waiting on dependencies.

## Dependencies

### `/gobby tasks depend <task> <blocker>` - Add dependency
Call `add_dependency` with:
- `task_id`: (required) The dependent task
- `depends_on`: (required) The blocker task
- `dep_type`: "blocks" (default), "discovered-from", or "related"

Example: `/gobby tasks depend #2 #1` → `add_dependency(task_id="#2", depends_on="#1")`

### `/gobby tasks undepend <task> <blocker>` - Remove dependency
Call `remove_dependency`

### `/gobby tasks deps <task-id>` - Show dependency tree
Call `get_dependency_tree`

### `/gobby tasks check-cycles` - Detect circular dependencies
Call `check_dependency_cycles`

## Validation

### `/gobby tasks validate <task-id>` - Validate completion
Call `validate_task` with:
- `task_id`: (required) Task to validate
- `changes_summary`: Summary of changes
- `context_files`: Relevant files to check

Auto-gathers context from commits if not provided.

Example: `/gobby tasks validate #1` → `validate_task(task_id="#1")`

### `/gobby tasks validation-status <task-id>` - Get validation details
Call `get_validation_status`

### `/gobby tasks validation-history <task-id>` - Get validation history
Call `get_validation_history`

### `/gobby tasks generate-criteria <task-id>` - Generate validation criteria
Call `generate_validation_criteria`

### `/gobby tasks fix <task-id>` - Run fix attempt
Call `run_fix_attempt` to spawn a fix agent for validation issues.

### `/gobby tasks validate-fix <task-id>` - Validate with auto-fix
Call `validate_and_fix` for validation loop with automatic fixes.

## Labels

### `/gobby tasks label <task-id> <label>` - Add label
Call `add_label`

### `/gobby tasks unlabel <task-id> <label>` - Remove label
Call `remove_label`

## Git Integration

### `/gobby tasks link-commit <task-id> <sha>` - Link commit
Call `link_commit`

### `/gobby tasks unlink-commit <task-id> <sha>` - Unlink commit
Call `unlink_commit`

### `/gobby tasks auto-link` - Auto-link commits
Call `auto_link_commits` to find commits mentioning task IDs.

### `/gobby tasks diff <task-id>` - Get task diff
Call `get_task_diff`

## Orchestration

Orchestration tools have moved to the `gobby-orchestration` server.

### `/gobby tasks orchestrate <parent-id>` - Spawn agents for ready tasks
Call `orchestrate_ready_tasks` on `gobby-orchestration`

### `/gobby tasks orchestration-status <parent-id>` - Get orchestration status
Call `get_orchestration_status` on `gobby-orchestration`

### `/gobby tasks poll-agents` - Poll agent status
Call `poll_agent_status` on `gobby-orchestration`

## Sync

### `/gobby tasks sync` - Trigger sync
Call `sync_tasks`

### `/gobby tasks sync-status` - Get sync status
Call `get_sync_status`

## Response Format

After executing the appropriate MCP tool, present the results clearly:
- For create: Show the new task ID and title
- For list: Table with ID, title, status, priority
- For show: All task fields in readable format
- For close: Confirm closure with task ID
- For expand: List created subtasks
- For suggest: Show suggested task with reasoning
- For validate: Validation result (pass/fail) with feedback

## Error Handling

If the subcommand is not recognized, show available subcommands:
- create, show, update, claim, list, close, reopen, delete
- expand, suggest, ready, blocked
- depend, undepend, deps, check-cycles
- validate, validation-status, validation-history, generate-criteria, fix, validate-fix
- label, unlabel
- link-commit, unlink-commit, auto-link, diff
- orchestrate, orchestration-status, poll-agents (via `gobby-orchestration`)
- sync, sync-status
