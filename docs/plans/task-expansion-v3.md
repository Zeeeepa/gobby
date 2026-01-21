# Plan: Simplified Task Expansion via Skills

## Branch

**Feature branch**: `feature/skill-based-expansion`

Clean break - delete old code entirely, no v2 naming needed.

## Problem Statement

The current task expansion system is ~4,100 lines of complex code that:
- Makes opaque LLM calls inside MCP tools (agent can't see what's happening)
- Creates duplicate tasks when expanding epics with existing children
- Has 12-step processes that over-engineer a fundamentally creative task
- Cannot survive session compaction or resume

## Solution

Replace the expansion MCP tool with a transparent `/gobby-expand` skill where:
- The agent does the LLM reasoning (visible in conversation)
- Spec is persisted before execution (survives compaction/resume)
- Task creation is atomic (via MCP tool)
- Clean slate approach: cascade delete existing children before expanding

## Design

### Skill Workflow (Resumable)

```
/gobby-expand #N or plan.md
    |
    v
[Check for pending expansion: get_expansion_spec(task_id)]
    |
    +---> If spec exists: skip to Phase 4 (Execute)
    |
    v
[Phase 1: Prepare]
  - If plan.md: create root task
  - Get task details
  - Cascade delete existing children
    |
    v
[Phase 2: Analyze (VISIBLE)]
  - Agent uses Glob, Grep, Read
  - Optional: context7, gitingest
    |
    v
[Phase 3: Generate & Save Spec]
  - Agent reasons through decomposition
  - Agent validates against original
  - Call save_expansion_spec(task_id, spec)
    |
    v
[Phase 4: Execute (ATOMIC)]
  - Call execute_expansion(task_id)
  - MCP tool reads spec, creates all tasks
    |
    v
[Phase 5: Report]
  - Show created task tree
```

### Session Safety

- **Spec persisted in task.expansion_context** before creation
- **On resume**: Skill calls `get_expansion_spec(task_id)`
  - If pending spec exists → resume from Phase 4
  - If no spec → start from Phase 1
- **Creation atomic**: `execute_expansion` creates all tasks or none

### TDD Approach

TDD is a **constraint**, not separate tasks:
- Each code task's validation criteria includes "tests pass"
- Agent is instructed: "All code must have matching tests"
- No separate `[TDD]`, `[IMPL]`, `[REF]` tasks

### Key Simplifications

| Before | After |
|--------|-------|
| ~4,100 lines across 8 files | ~400 line SKILL.md |
| LLM calls hidden in daemon | Agent reasoning visible |
| Complex context gathering | Agent uses Glob/Grep/Read |
| TDD sandwich (3x tasks) | TDD as validation criteria |
| Enhance vs replace logic | Always cascade delete (clean slate) |

## Files to Create

### 1. `/gobby-expand` Skill
**Path**: `src/gobby/install/shared/skills/gobby-expand/SKILL.md`

```markdown
---
name: gobby-expand
description: "Use when user asks to '/gobby-expand', 'expand task', 'break down task'. Expand a task into subtasks using codebase analysis and LLM reasoning."
version: "1.0"
---

# /gobby-expand - Task Expansion Skill

## Overview
Expand a task into atomic subtasks. YOU do the analysis and reasoning (visible).
Survives session compaction - spec is saved before execution.

## Input Formats
- `#N` - Task reference (e.g., `#42`)
- `path.md` - Plan file (creates root task first)

## Workflow

### Phase 0: Check for Resume
First, check if there's a pending expansion to resume:
```python
result = call_tool("gobby-tasks", "get_expansion_spec", {"task_id": "<ref>"})
if result["pending"]:
    # Skip to Phase 4 with saved spec
    print(f"Resuming expansion with {len(result['spec']['subtasks'])} subtasks")
```

### Phase 1: Prepare
1. Parse input (task ref or file path)
2. If file: Read content, `create_task(title=<first_heading>, description=<content>, task_type="epic")`
3. Get task: `get_task(task_id="<ref>")`
4. Check children: `children = list_tasks(parent_task_id="<task_id>")`
5. If children exist: Delete each child individually:
   ```python
   for child in children["tasks"]:
       delete_task(task_id=child["id"])
   ```

### Phase 2: Analyze Codebase (VISIBLE)
Use YOUR tools to understand context:
- `Glob`: Find relevant source files
- `Grep`: Search for patterns, function names
- `Read`: Examine key files
- Optional: `context7` for library docs

### Phase 3: Generate & Save Spec
Think through decomposition with these requirements:
1. **TDD Mandate**: All code changes require tests. Include "tests pass" in validation criteria.
2. **Atomicity**: Each task completable in 10-30 minutes
3. **Categories**: code, config, docs, research, planning, manual
4. **No separate test tasks**: TDD is a workflow constraint

After generating, SAVE the spec before creating tasks:
```python
spec = {
    "subtasks": [
        {"title": "...", "category": "code", "depends_on": [], "validation": "Tests pass. ..."},
        {"title": "...", "category": "code", "depends_on": [0], "validation": "Tests pass. ..."},
    ]
}
call_tool("gobby-tasks", "save_expansion_spec", {"task_id": "<ref>", "spec": spec})
```

### Phase 4: Execute (ATOMIC)
Execute the saved spec atomically:
```python
result = call_tool("gobby-tasks", "execute_expansion", {
    "task_id": "<ref>",
    "session_id": "<your_session_id>"
})
# Returns: {"created": ["#43", "#44", ...], "count": N}
```

### Phase 5: Report
Show created task tree with refs and dependency arrows.
```
```

## New MCP Tools

**Path**: `src/gobby/mcp_proxy/tools/tasks/_expansion.py` (replaces old file)

### `save_expansion_spec`
```python
async def save_expansion_spec(
    task_id: str,
    spec: dict,  # {subtasks: [{title, category, depends_on, validation, ...}]}
) -> dict:
    """Save expansion spec to task.expansion_context for later execution."""
    task = manager.get_task(task_id)
    task.expansion_context = json.dumps(spec)
    task.expansion_status = "pending"
    manager.update_task(task)
    return {"saved": True, "task_id": task_id, "subtask_count": len(spec["subtasks"])}
```

### `execute_expansion`
```python
async def execute_expansion(
    task_id: str,
    session_id: str,
) -> dict:
    """Execute a saved expansion spec atomically."""
    task = manager.get_task(task_id)
    spec = json.loads(task.expansion_context)

    created = []
    for subtask in spec["subtasks"]:
        new_task = manager.create_task(
            title=subtask["title"],
            parent_task_id=task_id,
            category=subtask.get("category"),
            validation_criteria=subtask.get("validation"),
            session_id=session_id,
        )
        created.append(new_task)

    # Wire dependencies
    for i, subtask in enumerate(spec["subtasks"]):
        for dep_idx in subtask.get("depends_on", []):
            manager.add_dependency(created[i].id, created[dep_idx].id)

    task.is_expanded = True
    task.expansion_status = "completed"
    manager.update_task(task)
    return {"created": [t.ref for t in created], "count": len(created)}
```

### `get_expansion_spec`
```python
async def get_expansion_spec(task_id: str) -> dict:
    """Check for pending expansion spec (for resume)."""
    task = manager.get_task(task_id)
    if task.expansion_status == "pending" and task.expansion_context:
        return {"pending": True, "spec": json.loads(task.expansion_context)}
    return {"pending": False}
```

## Files to Delete (FIRST - clean break)

Delete these files on the feature branch:
- `src/gobby/tasks/expansion.py` (626 lines)
- `src/gobby/tasks/context.py` (747 lines)
- `src/gobby/tasks/research.py` (421 lines)
- `src/gobby/tasks/criteria.py` (342 lines)
- `src/gobby/tasks/prompts/expand.py` (328 lines)
- `src/gobby/mcp_proxy/tools/task_expansion.py` (592 lines)
- Tests for deleted code in `tests/`

Keep:
- `src/gobby/tasks/tdd.py` (may be useful elsewhere)
- `src/gobby/tasks/validation.py` (used for task closure)

## Files to Modify

### Add `expansion_status` Field to Task Model
**Path**: `src/gobby/storage/tasks/_models.py`

```python
expansion_status: Literal["none", "pending", "completed"] = "none"
```

### Ensure `delete_task` Supports Cascade
**Path**: `src/gobby/mcp_proxy/tools/tasks/_lifecycle.py`

Verify `delete_task` MCP tool exposes `cascade` parameter.

## Implementation Phases

### Phase 1: Create Feature Branch & Delete Old Code
```bash
git checkout -b feature/skill-based-expansion
```
1. Delete old expansion files (~3,000 lines)
2. Delete tests for old expansion code
3. Fix any imports that break
4. Commit: "remove legacy task expansion system"

### Phase 2: Add New MCP Tools
1. Add `expansion_status` field to Task model + migration
2. Create `src/gobby/mcp_proxy/tools/tasks/_expansion.py` with:
   - `save_expansion_spec(task_id, spec)`
   - `execute_expansion(task_id, session_id)`
   - `get_expansion_spec(task_id)`
3. Register tools in task registry
4. Write tests for new tools
5. Commit: "add skill-based expansion MCP tools"

### Phase 3: Create Skill
1. Create `src/gobby/install/shared/skills/gobby-expand/SKILL.md`
2. Update `/gobby-tasks` skill to remove `expand` subcommand reference
3. Commit: "add /gobby-expand skill"

### Phase 4: Test & PR
1. Manual testing with sample tasks
2. Test resume flow
3. Open PR to main

## Verification

### Unit Tests
```bash
# Test new MCP tools
pytest tests/mcp_proxy/tools/tasks/test_expansion.py -v

# Test cases:
# - save_expansion_spec stores spec in task.expansion_context
# - execute_expansion creates tasks atomically
# - execute_expansion wires dependencies correctly
# - get_expansion_spec returns pending spec
# - get_expansion_spec returns {"pending": false} when no spec
```

### Manual Testing
```bash
# 1. Create a test task
gobby tasks create "Implement user authentication" --type=feature

# 2. Run the skill
# In Claude Code: /gobby-expand #<task_id>

# 3. Verify:
# - Existing children deleted (if any)
# - Agent shows codebase analysis (Glob, Grep, Read calls visible)
# - Agent shows reasoning for task tree
# - Spec saved before task creation
# - Tasks created atomically
# - Validation criteria include "tests pass"

# 4. Check task tree
gobby tasks tree #<task_id>
```

### Resume Flow Testing
```bash
# 1. Start expansion, interrupt after Phase 3 (spec saved)
# In Claude Code: /gobby-expand #<task_id>
# Agent saves spec, then simulate interruption (Ctrl+C or /compact)

# 2. Resume in new session
# In Claude Code: /gobby-expand #<task_id>
# Agent should detect pending spec and skip to Phase 4

# 3. Verify tasks created from saved spec
gobby tasks tree #<task_id>
```

### Test with Plan File
```bash
# Create a test plan
echo "# Test Epic\n\nImplement login and logout with JWT." > /tmp/test-plan.md

# Run skill
# In Claude Code: /gobby-expand /tmp/test-plan.md

# Verify root epic created with plan as description
```

## Success Criteria

1. `/gobby-expand #N` produces good quality task decomposition
2. Agent's reasoning is visible in conversation
3. TDD requirement is explicit in task validation criteria
4. Cascade delete prevents duplicate tasks
5. **Resume works**: Interrupted expansion can continue from saved spec
6. **~3,000 lines of code deleted** (old expansion system removed)
7. All existing tests pass (excluding deleted expansion tests)
