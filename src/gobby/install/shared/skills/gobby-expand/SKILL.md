---
name: gobby-expand
description: "Use when user asks to '/gobby-expand', 'expand task', 'break down task', 'decompose task'. Expand a task into subtasks using codebase analysis and visible LLM reasoning. Survives session compaction."
---

# /gobby-expand - Task Expansion Skill

Expand a task into atomic subtasks. YOU do the analysis and reasoning (visible in conversation).
Survives session compaction - spec is saved before execution.

## Input Formats

- `#N` - Task reference (e.g., `/gobby-expand #42`)
- `path.md` - Plan file (creates root task first, e.g., `/gobby-expand docs/plan.md`)

## Session Context

**IMPORTANT**: Use the `session_id` from your SessionStart hook context:
```
session_id: fd59c8fc-...
```

## Workflow

### Phase 0: Check for Resume

First, check if there's a pending expansion to resume:

```python
result = call_tool("gobby-tasks", "get_expansion_spec", {"task_id": "<ref>"})
if result.get("pending"):
    # Skip directly to Phase 4 with saved spec
    print(f"Resuming expansion with {result['subtask_count']} subtasks")
    # Jump to Phase 4
```

If `pending=True`, skip to **Phase 4** immediately.

### Phase 1: Prepare

1. **Parse input**: Task ref (`#N`) or file path (`plan.md`)

2. **If file path**: Read file content, create root task:
   ```python
   content = Read(file_path)
   # Extract first heading as title
   result = call_tool("gobby-tasks", "create_task", {
       "title": "<first_heading>",
       "description": content,
       "task_type": "epic",
       "session_id": "<session_id>"
   })
   task_id = result["task"]["id"]
   ```

3. **Get task details**:
   ```python
   task = call_tool("gobby-tasks", "get_task", {"task_id": "<ref>"})
   ```

4. **Check for existing children** and delete them (clean slate):
   ```python
   children = call_tool("gobby-tasks", "list_tasks", {"parent_task_id": task_id})
   if children["tasks"]:
       # Delete parent cascades to children
       call_tool("gobby-tasks", "delete_task", {"task_id": task_id, "cascade": True})
       # Re-create the parent task
       result = call_tool("gobby-tasks", "create_task", {
           "title": task["title"],
           "description": task["description"],
           "task_type": task["type"],
           "session_id": "<session_id>"
       })
       task_id = result["task"]["id"]
   ```

### Phase 2: Analyze Codebase (VISIBLE)

Use YOUR tools to understand the codebase context. This analysis is visible in the conversation.

**Required analysis**:
- `Glob`: Find relevant source files matching the task domain
- `Grep`: Search for patterns, function names, classes
- `Read`: Examine key files for structure and patterns

**Optional tools**:
- `context7`: Library documentation lookup
- `WebSearch`: External API/library research

Example analysis approach:
```
1. Search for related code: Glob("**/auth*.py"), Glob("**/user*.py")
2. Find existing patterns: Grep("class.*Handler", type="py")
3. Read key files: Read("/src/api/routes.py")
4. Note dependencies, test patterns, validation approaches
```

### Phase 3: Generate & Save Spec

Think through the decomposition with these requirements:

**Requirements**:
1. **TDD Mandate**: All code changes require tests. Include "Tests pass" in validation criteria.
2. **Atomicity**: Each task should be completable in 10-30 minutes
3. **Categories**: Use `code`, `config`, `docs`, `research`, `planning`, `manual`
4. **No separate test tasks**: TDD is a workflow constraint, not separate tasks
5. **Dependencies**: Use indices (0-based) to reference earlier subtasks

**Spec format**:
```python
spec = {
    "subtasks": [
        {
            "title": "Add User model with password hashing",
            "category": "code",
            "depends_on": [],
            "validation": "Tests pass. User model exists with hash_password method.",
            "description": "Create User model in models/user.py",
            "priority": 2
        },
        {
            "title": "Implement login endpoint",
            "category": "code",
            "depends_on": [0],  # Depends on User model
            "validation": "Tests pass. POST /login returns JWT on valid credentials.",
            "description": "Add login route to api/auth.py"
        },
        {
            "title": "Add logout endpoint",
            "category": "code",
            "depends_on": [1],  # Depends on login
            "validation": "Tests pass. POST /logout invalidates session."
        }
    ]
}
```

**Save the spec BEFORE creating tasks** (this enables resume):
```python
result = call_tool("gobby-tasks", "save_expansion_spec", {
    "task_id": "<ref>",
    "spec": spec
})
# Returns: {"saved": True, "task_id": "...", "subtask_count": N}
```

### Phase 4: Execute (ATOMIC)

Execute the saved spec atomically:
```python
result = call_tool("gobby-tasks", "execute_expansion", {
    "task_id": "<ref>",
    "session_id": "<session_id>"
})
# Returns: {"created": ["#43", "#44", "#45"], "count": 3}
```

This creates all subtasks and wires dependencies in one transaction.

### Phase 5: Report

Show the created task tree with refs and dependencies:

```
Created 3 subtasks for #42 "Implement user authentication":

#43 [code] Add User model with password hashing
    └─ validation: Tests pass. User model exists with hash_password method.

#44 [code] Implement login endpoint (depends on #43)
    └─ validation: Tests pass. POST /login returns JWT on valid credentials.

#45 [code] Add logout endpoint (depends on #44)
    └─ validation: Tests pass. POST /logout invalidates session.

Use `suggest_next_task` to get the first ready task.
```

## Subtask Categories

| Category | When to Use |
|----------|-------------|
| `code` | Implementation tasks (includes tests per TDD) |
| `config` | Configuration file changes |
| `docs` | Documentation updates |
| `research` | Investigation/exploration tasks |
| `planning` | Design/architecture tasks |
| `manual` | Manual testing/verification |

## TDD Approach

TDD is a **constraint**, not separate tasks:
- Every `code` category task's validation criteria should include "Tests pass"
- The agent is expected to write tests alongside implementation
- No separate `[TEST]`, `[IMPL]`, `[REFACTOR]` task patterns

## Error Handling

**Task not found**:
```
Error: Task #42 not found. Verify the task reference exists.
```

**Invalid spec**:
```
Error: Spec must contain 'subtasks' array with at least one subtask.
Each subtask requires a 'title' field.
```

**Session compaction recovery**:
If expansion was interrupted after Phase 3, the skill will detect the pending spec
and resume from Phase 4 automatically.

## Examples

### Basic Expansion
```
User: /gobby-expand #42

Agent: Checking for pending expansion...
No pending spec found. Starting fresh expansion.

Phase 1: Getting task #42...
Task: "Implement user authentication" (feature)

Phase 2: Analyzing codebase...
[Glob, Grep, Read calls visible here]

Phase 3: Generating subtasks...
[Agent reasoning visible here]
Saving expansion spec with 4 subtasks...

Phase 4: Executing expansion...
Created 4 subtasks.

Phase 5: Task tree created:
#43 [code] Add User model...
#44 [code] Implement login...
...
```

### Resume After Interruption
```
User: /gobby-expand #42

Agent: Checking for pending expansion...
Found pending spec with 4 subtasks. Resuming from Phase 4.

Phase 4: Executing expansion...
Created 4 subtasks.

Phase 5: Task tree created:
#43 [code] Add User model...
...
```

### From Plan File
```
User: /gobby-expand docs/auth-plan.md

Agent: Reading plan file...
Creating root epic from plan...
Created epic #50 "User Authentication System"

Phase 2: Analyzing codebase...
...
```
