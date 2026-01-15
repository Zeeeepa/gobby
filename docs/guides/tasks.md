# Task Management Guide

Gobby includes a native task tracking system designed for AI-assisted development. Tasks are persistent across sessions, support dependencies, and sync with git.

## Core Concepts

- **Task**: A unit of work with title, description, priority, and status
- **Epic**: A parent task that groups subtasks
- **Dependencies**: Tasks can block other tasks (A must complete before B starts)
- **Ready Work**: Tasks with no unresolved blocking dependencies
- **Sync**: Tasks export to `.gobby/tasks.jsonl` for git versioning

## Quick Start

### MCP Tools (for AI Agents)

```python
# Check what's ready to work on
call_tool(server_name="gobby-tasks", tool_name="list_ready_tasks", arguments={})

# Create a task
call_tool(server_name="gobby-tasks", tool_name="create_task", arguments={
    "title": "Fix authentication bug",
    "priority": 1,
    "task_type": "bug",
    "session_id": "<your_session_id>"  # Required
})

# Claim and work on it
call_tool(server_name="gobby-tasks", tool_name="update_task", arguments={
    "task_id": "gt-abc123",
    "status": "in_progress"
})

# Complete it
call_tool(server_name="gobby-tasks", tool_name="close_task", arguments={
    "task_id": "gt-abc123",
    "reason": "completed"
})
```

### CLI Commands

```bash
# List ready work
gobby tasks list --ready

# Create a task
gobby tasks create "Fix login bug" -p 1 -t bug

# Update status
gobby tasks update gt-abc123 --status in_progress

# Close task
gobby tasks close gt-abc123 --reason "Fixed"

# Sync with git
gobby tasks sync
```

## Task Lifecycle

```text
open → in_progress → closed
   ↘                ↘ failed (validation failures)
    needs_decomposition → open (when subtasks added)
```

- **open**: Ready or blocked, not started
- **in_progress**: Currently being worked on
- **closed**: Completed with reason
- **failed**: Exceeded validation retry limit
- **needs_decomposition**: Multi-step task awaiting breakdown into subtasks

## Task Types

| Type | Use For |
|------|---------|
| `task` | General work items (default) |
| `bug` | Something broken |
| `feature` | New functionality |
| `epic` | Large feature with subtasks |
| `chore` | Maintenance, dependencies, tooling |

## Priority Levels

| Priority | Meaning |
|----------|---------|
| 1 | High (critical bugs, major features) |
| 2 | Medium (default) |
| 3 | Low (polish, optimization) |

## Dependencies

Tasks can block other tasks. A blocked task won't appear in `list_ready_tasks` until its blockers are closed.

```python
# Task A blocks Task B (B depends on A completing first)
call_tool(server_name="gobby-tasks", tool_name="add_dependency", arguments={
    "task_id": "gt-taskB",      # The dependent task
    "depends_on": "gt-taskA",   # The blocker
    "dep_type": "blocks"
})

# Create task with dependencies in one call
call_tool(server_name="gobby-tasks", tool_name="create_task", arguments={
    "title": "Implement feature",
    "blocks": ["gt-parent-epic"],  # This task blocks the parent
    "session_id": "<your_session_id>"  # Required
})
```

### Dependency Types

| Type | Behavior |
|------|----------|
| `blocks` | Hard dependency - prevents task from being "ready" |
| `related` | Soft link - informational only |
| `discovered-from` | Task found while working on another |

## Auto-Decomposition

When creating tasks with multi-step descriptions (numbered lists, bullet points with action verbs), the system automatically breaks them into subtasks.

### How It Works

```python
# Multi-step descriptions are preserved but NOT auto-decomposed (use expand_task instead)
call_tool(server_name="gobby-tasks", tool_name="create_task", arguments={
    "title": "Implement auth",
    "description": """1. Create user model
2. Add login endpoint
3. Generate JWT tokens""",
    "session_id": "<your_session_id>"  # Required
})
+# Result: single task with multi-step description preserved
+# Use expand_task(task_id) to break down into subtasks if needed
```

### Detection Patterns

Multi-step content is detected when:
- **Numbered lists** with 3+ items (e.g., `1. First`, `2. Second`, `3. Third`)
- **Bullet lists** with 3+ action verbs (`- Create`, `- Add`, `- Implement`)
- **Phase headers** (`## Phase 1`, `## Phase 2`)
- **Sequence words** (`first`, `then`, `finally`, `next`)

**False positives avoided:**
- Bug reproduction steps (`Steps to Reproduce: 1. Click...`)
- Acceptance criteria
- Requirements lists
- Options/approaches

### Opting Out

```python
# Create a complex task (auto-decomposition is disabled by default)
call_tool(server_name="gobby-tasks", tool_name="create_task", arguments={
    "title": "Complex task",
    "description": "1. Step one\n2. Step two\n3. Step three",
    "session_id": "<your_session_id>"  # Required
})
# Note: auto_decompose parameter is deprecated. Use expand_task() to decompose tasks

# Disable for entire session via workflow variable
call_tool(server_name="gobby-workflows", tool_name="set_variable", arguments={
    "name": "auto_decompose",
    "value": False
})
```

### The `needs_decomposition` Status

When `auto_decompose=False` on a multi-step description:
- Task is created with `status: needs_decomposition`
- Task **cannot** be claimed (`in_progress`) until decomposed
- Task **cannot** have validation criteria set until decomposed
- Adding subtasks automatically transitions status to `open`

```python
# Check if task needs decomposition
task = call_tool(server_name="gobby-tasks", tool_name="get_task", arguments={"task_id": "gt-xxx"})
if task["status"] == "needs_decomposition":
    # Add subtasks manually
    call_tool(server_name="gobby-tasks", tool_name="create_task", arguments={
        "title": "Subtask 1",
        "parent_task_id": task["id"],
        "session_id": "<your_session_id>"  # Required
    })
    # Parent automatically transitions to 'open'
```

## Task Decomposition Workflow

Gobby provides a phased approach to breaking down complex work into actionable tasks:

```text
parse_spec → enrich → expand → apply_tdd
     ↓          ↓        ↓          ↓
  (fast)    (context) (subtasks)  (tests)
```

### Phase 1: Parse Spec (Fast)

Create tasks from a specification document with checkboxes:

```bash
# CLI: Parse spec into tasks
gobby tasks parse-spec docs/plans/feature.md

# With parent task
gobby tasks parse-spec docs/plans/feature.md --parent #42
```

```python
# MCP: Parse checkboxes from spec content
call_tool(server_name="gobby-tasks", tool_name="parse_spec", arguments={
    "spec_content": "## Phase 1\n- [ ] Task 1\n- [ ] Task 2",
    "parent_task_id": "gt-abc123"
})
```

### Phase 2: Enrich Tasks (LLM Context)

Add context, complexity scores, and validation criteria:

```bash
# CLI: Enrich a task
gobby tasks enrich #42

# Enrich with subtasks
gobby tasks enrich #42 --cascade

# Enable web research
gobby tasks enrich #42 --web-research --mcp-tools
```

```python
# MCP: Enrich task with AI analysis
call_tool(server_name="gobby-tasks", tool_name="enrich_task", arguments={
    "task_id": "gt-abc123",
    "enable_web_research": False,
    "enable_mcp_tools": False
})
```

Enrichment adds:
- **Category**: Type classification (feature, bug, refactor)
- **Complexity score**: 1-10 difficulty rating
- **Validation criteria**: Pass/fail conditions
- **Relevant files**: Codebase files to modify

### Phase 3: Expand Tasks (Subtask Generation)

Break down complex tasks into smaller subtasks:

```bash
# CLI: Expand a task
gobby tasks expand #42

# Expand multiple tasks
gobby tasks expand #42,#43,#44

# Expand with cascade (include subtasks)
gobby tasks expand #42 --cascade

# Skip enrichment step
gobby tasks expand #42 --no-enrich
```

```python
# MCP: Expand task into subtasks
call_tool(server_name="gobby-tasks", tool_name="expand_task", arguments={
    "task_id": "gt-abc123",
    "enable_code_context": True,
    "enable_web_research": False
})
```

### Phase 4: Apply TDD (Test/Implementation Pairs)

Transform tasks into test-driven development triplets:

```bash
# CLI: Apply TDD to a task
gobby tasks apply-tdd #42

# Apply TDD to multiple tasks
gobby tasks apply-tdd #42,#43

# Apply TDD to task tree
gobby tasks apply-tdd #42 --cascade
```

```python
# MCP: Create TDD triplet
call_tool(server_name="gobby-tasks", tool_name="apply_tdd", arguments={
    "task_id": "gt-abc123"
})
```

TDD creates three subtasks for each task:
1. **[TEST]** Write tests for: *original title*
2. **[IMPL]** Implement: *original title* (blocked by TEST)
3. **[REFACTOR]** Refactor: *original title* (blocked by IMPL)

### Complete Workflow Example

```bash
# 1. Parse spec into tasks
gobby tasks parse-spec docs/plans/auth-feature.md

# 2. Enrich all tasks with AI analysis
gobby tasks enrich #42 --cascade

# 3. Expand complex tasks into subtasks
gobby tasks expand #42 --cascade

# 4. Apply TDD to implementation tasks
gobby tasks apply-tdd #42 --cascade

# 5. View the task tree
gobby tasks show #42 --tree
```

## LLM-Powered Expansion

Break down complex tasks into subtasks using AI:

```python
# Expand a task into subtasks
call_tool(server_name="gobby-tasks", tool_name="expand_task", arguments={
    "task_id": "gt-abc123",
    "enable_code_context": True
})

# Get complexity analysis
call_tool(server_name="gobby-tasks", tool_name="analyze_complexity", arguments={
    "task_id": "gt-abc123"
})

# Get AI suggestion for next task
call_tool(server_name="gobby-tasks", tool_name="suggest_next_task", arguments={})

# Create tasks from a PRD or spec
call_tool(server_name="gobby-tasks", tool_name="expand_from_spec", arguments={
    "spec_content": "# Feature: User Authentication\n..."
})
```

## Task Validation

Validate task completion with AI assistance. Validation uses actual git diffs to verify real code changes.

### Automatic Validation on Close

When closing a task with `validation_criteria`, the system automatically:
1. Fetches uncommitted git changes (staged + unstaged)
2. Passes the actual diff to the validation LLM
3. Blocks the close if validation fails

```python
# Close task - validation happens automatically if task has validation_criteria
call_tool(server_name="gobby-tasks", tool_name="close_task", arguments={
    "task_id": "gt-abc123",
    "reason": "completed"
})
# If validation fails, returns: {"error": "validation_failed", "message": "...", "validation_status": "invalid"}

# Skip validation if needed
call_tool(server_name="gobby-tasks", tool_name="close_task", arguments={
    "task_id": "gt-abc123",
    "reason": "completed",
    "skip_validation": True
})
```

### Generate Validation Criteria

Tasks need `validation_criteria` for validation to run:

```python
# Generate criteria for a single task
call_tool(server_name="gobby-tasks", tool_name="generate_validation_criteria", arguments={
    "task_id": "gt-abc123"
})

# Or set criteria manually when creating/updating
call_tool(server_name="gobby-tasks", tool_name="create_task", arguments={
    "title": "Add logout button",
    "validation_criteria": "- Logout button visible in header\n- Clicking logs user out\n- Redirects to login page",
    "session_id": "<your_session_id>"  # Required
})
```

### Manual Validation

```python
# Validate a task explicitly (with optional changes_summary)
call_tool(server_name="gobby-tasks", tool_name="validate_task", arguments={
    "task_id": "gt-abc123",
    "changes_summary": "Added login form with validation"  # Optional - uses git diff if not provided
})

# Check validation status
call_tool(server_name="gobby-tasks", tool_name="get_validation_status", arguments={
    "task_id": "gt-abc123"
})

# Reset validation count for retry
call_tool(server_name="gobby-tasks", tool_name="reset_validation_count", arguments={
    "task_id": "gt-abc123"
})
```

### CLI Validation Commands

```bash
# Generate validation criteria
gobby tasks generate-criteria gt-abc123

# Generate criteria for all open tasks missing it
gobby tasks generate-criteria --all

# Validate a task
gobby tasks validate gt-abc123

# Reset validation failure count
gobby tasks reset-validation gt-abc123
```

## Git Sync

Tasks automatically sync to `.gobby/tasks.jsonl`:

- **Export**: After task changes (5s debounce)
- **Import**: On daemon start
- **Manual**: `gobby tasks sync`

### Git Hook Auto-Sync

Install git hooks for automatic task sync on commits and branch changes:

```bash
gobby install
```

**Hooks installed:**
| Hook | Trigger | Action |
|------|---------|--------|
| `pre-commit` | Before each commit | Export tasks to JSONL |
| `post-merge` | After pull/merge | Import tasks from JSONL |
| `post-checkout` | On branch switch | Import tasks from JSONL |

The installer chains with existing hooks (preserving pre-commit framework if present) and creates backups before modification.

This ensures tasks stay in sync with your git branches without manual intervention.

### Stealth Mode

Keep tasks out of git (store in `~/.gobby/` instead):

```bash
gobby tasks config --stealth on
```

## Complete MCP Tool Reference

### Task CRUD

| Tool | Description |
|------|-------------|
| `create_task` | Create a new task |
| `get_task` | Get task details with dependencies |
| `update_task` | Update task fields |
| `close_task` | Close a task with reason |
| `delete_task` | Delete a task (cascade optional) |
| `list_tasks` | List tasks with filters |
| `add_label` | Add a label to a task |
| `remove_label` | Remove a label from a task |

### Dependencies

| Tool | Description |
|------|-------------|
| `add_dependency` | Create dependency between tasks |
| `remove_dependency` | Remove a dependency |
| `get_dependency_tree` | Get blockers/blocking tree |
| `check_dependency_cycles` | Detect circular dependencies |

### Ready Work

| Tool | Description |
|------|-------------|
| `list_ready_tasks` | Tasks with no unresolved blockers |
| `list_blocked_tasks` | Tasks waiting on others |

### Progressive Disclosure

List operations return **brief format** (8 fields) to minimize token usage:

```json
{"id", "title", "status", "priority", "type", "parent_task_id", "created_at", "updated_at"}
```

Use `get_task` to retrieve full details (description, validation criteria, commits, etc.):

```python
# Step 1: Discover tasks
tasks = call_tool(server_name="gobby-tasks", tool_name="list_ready_tasks", arguments={})

# Step 2: Get full details for specific task
task = call_tool(server_name="gobby-tasks", tool_name="get_task", arguments={"task_id": "gt-abc"})
```

### Session Integration

| Tool | Description |
|------|-------------|
| `link_task_to_session` | Associate task with session |
| `get_session_tasks` | Tasks linked to a session |
| `get_task_sessions` | Sessions that touched a task |

### Git Sync

| Tool | Description |
|------|-------------|
| `sync_tasks` | Trigger import/export |
| `get_sync_status` | Get sync status |

### Task Decomposition

| Tool | Description |
|------|-------------|
| `parse_spec` | Parse checkboxes from spec content (fast, no LLM) |
| `enrich_task` | Add context, complexity, validation criteria |
| `expand_task` | Break task into subtasks with AI |
| `apply_tdd` | Create test/implement/refactor triplet |
| `analyze_complexity` | Get complexity score |
| `expand_all` | Expand all unexpanded tasks |
| `expand_from_spec` | Create tasks from PRD/spec |
| `suggest_next_task` | AI suggests next task to work on |

### Validation

| Tool | Description |
|------|-------------|
| `validate_task` | Validate task completion (uses git diff automatically) |
| `get_validation_status` | Get validation details |
| `reset_validation_count` | Reset failure count for retry |
| `generate_validation_criteria` | Generate validation criteria using LLM |

## CLI Command Reference

```bash
# Task management
gobby tasks list [--status S] [--priority N] [--ready] [--blocked] [--json]
gobby tasks show TASK_ID
gobby tasks create "Title" [-d DESC] [-p PRIORITY] [-t TYPE]
gobby tasks update TASK_ID [--status S] [--priority P]
gobby tasks close TASK_ID --reason "Done"
gobby tasks delete TASK_ID [--cascade]

# Dependencies
gobby tasks dep add TASK BLOCKER
gobby tasks dep remove TASK BLOCKER
gobby tasks dep tree TASK
gobby tasks dep cycles

# Labels
gobby tasks label add TASK LABEL
gobby tasks label remove TASK LABEL

# Ready work
gobby tasks ready [--limit N]
gobby tasks blocked

# Sync
gobby tasks sync [--import] [--export]

# Task Decomposition
gobby tasks parse-spec SPEC_PATH [--parent TASK] [--project NAME]
gobby tasks enrich TASKS... [--cascade] [--web-research] [--mcp-tools] [--force]
gobby tasks expand TASKS... [--cascade] [--no-enrich] [--force]
gobby tasks apply-tdd TASKS... [--cascade] [--force]
gobby tasks complexity TASK_ID [--all]
gobby tasks suggest

# Validation
gobby tasks generate-criteria TASK_ID   # Generate criteria for one task
gobby tasks generate-criteria --all     # Generate for all open tasks
gobby tasks validate TASK_ID            # Run validation
gobby tasks reset-validation TASK_ID    # Reset failure count

# Stats
gobby tasks stats
```

## Data Storage

- **Database**: `~/.gobby/gobby-hub.db` (SQLite)
- **Git sync**: `.gobby/tasks.jsonl` (or `~/.gobby/tasks/{project}.jsonl` in stealth mode)
- **Metadata**: `.gobby/tasks_meta.json`

## Task ID Format

- Generated: `gt-{6 hex chars}` (e.g., `gt-a1b2c3`)
- Hierarchical: `gt-a1b2c3.1`, `gt-a1b2c3.2` (subtasks)
- Prefix matching supported: `gt-a1b` matches `gt-a1b2c3`
