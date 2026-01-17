---
name: gobby-plan
description: This skill should be used when the user asks to "/gobby-plan", "create plan", "plan feature", "write specification". Guide users through structured specification planning and task creation.
version: "1.0"
---

# /gobby-plan - Implementation Planning Skill

Guide users through structured requirements gathering, specification writing, and task creation.

## Workflow Overview

1. **Requirements Gathering** - Ask questions to understand the feature
2. **Draft Plan** - Write structured plan document
3. **Plan Verification** - Check for TDD anti-patterns and dependency issues
4. **User Approval** - Present plan for review
5. **Task Creation** - Create tasks from approved plan
6. **Task Verification** - Update plan with task refs

## Step 0: **REQUIRED** ENTER PLAN MODE

Before creating any plan, you must enter Claude Code's plan mode to explore the codebase
and design the implementation approach.

**How to enter**: Use the `EnterPlanMode` tool or respond with a planning-focused message
that triggers plan mode. Plan mode allows you to read files and design without making edits.

**Why required**: Plan creation requires understanding existing code patterns, architecture
constraints, and dependencies before proposing new work.

## Step 1: Requirements Gathering

Ask the user:
1. "What is the name/title for this feature or project?"
2. "What is the high-level goal? (1-2 sentences)"
3. "Are there any constraints or requirements I should know about?"
4. "What are the unknowns or risks?"

## Step 2: Draft Plan Structure

Create a plan with:
- **Epic title**: The overall feature name
- **Phases**: Logical groupings of work (e.g., "Foundation", "Core Implementation", "Polish")
- **Tasks**: Atomic units of work under each phase
- **Dependencies**: Which tasks block which (use notation: `depends: #N` or `depends: Phase N`)

## Step 3: Write Plan Document

Write to `.gobby/plans/{kebab-name}.md`:

```markdown
# {Epic Title}

## Overview
{Goal and context from Step 1}

## Constraints
{Constraints from Step 1}

## Phase 1: {Phase Name}

**Goal**: {One sentence outcome}

**Tasks:**
- [ ] Task 1 title
- [ ] Task 2 title (depends: Task 1)
- [ ] Task 3 title (parallel)

## Phase 2: {Phase Name}

**Goal**: {One sentence outcome}

**Tasks:**
- [ ] Task 4 (depends: Phase 1)
- [ ] Task 5 (parallel with Task 4)

## Task Mapping

<!-- Updated after task creation -->
| Plan Item | Task Ref | Status |
|-----------|----------|--------|
```

**Dependency Notation Mapping:**
- In markdown plan: `(depends: Task 1)` or `(depends: Phase N)`
- In JSON for build_task_tree: `"depends_on": ["Task 1"]` or `"depends_on": ["Phase N: Name"]`

The skill converts human-readable notation to JSON format when calling `build_task_tree`.

## Step 4: Plan Verification (REQUIRED)

Before presenting to the user, verify the plan does NOT contain TDD anti-patterns:

### Check 1: No Explicit Test Tasks

Scan for tasks that should NOT exist (TDD sandwich creates these automatically):

**FORBIDDEN patterns - remove these if found:**
- `"Write tests for..."` or `"Add tests for..."`
- `"Test..."` as task title prefix
- `"[TEST]..."` or `"[IMPL]..."` or `"[REFACTOR]..."`
- `"Ensure tests pass"` or `"Run tests"`
- `"Add unit tests"` or `"Add integration tests"`
- Any task with `test` as the primary verb

**ALLOWED (these are fine):**
- `"Add TestClient fixture"` (not a test task, but test infrastructure)
- `"Configure pytest settings"` (configuration, not test writing)

### Check 2: Dependency Tree Validation

Verify the dependency structure is valid:

1. **No circular dependencies**: Task A → B → A is invalid
2. **No missing dependencies**: If Task B depends on Task A, Task A must exist
3. **Phase dependencies are valid**: `depends: Phase N` must reference an existing phase
4. **Leaf tasks are implementation work**: Bottom-level tasks should be concrete work, not meta-tasks

### Check 3: Task Categorization

Ensure each task has the right category:
- `category: "code"` - Implementation tasks (will get TDD treatment)
- `category: "document"` - Documentation tasks (no TDD)
- `category: "config"` - Configuration changes (gets TDD)

### Verification Output

After verification, report:
```
Plan Verification:
✓ No explicit test tasks found
✓ Dependency tree is valid (no cycles, all refs exist)
✓ Categories assigned correctly

Ready for user approval.
```

Or if issues found:
```
Plan Verification:
✗ Found 2 explicit test tasks (removed):
  - "Add tests for user authentication" → REMOVED
  - "Ensure all tests pass" → REMOVED
✓ Dependency tree is valid
✓ Categories assigned correctly

Plan updated. Ready for user approval.
```

## Step 5: User Approval

Present the plan to the user:
- Show the full plan document
- Show verification results
- Ask: "Does this plan look correct? Would you like any changes before I create tasks?"
- Make changes if requested
- Once approved, proceed to task creation

## Step 6: Task Creation

Build a JSON tree from the plan structure and call `build_task_tree`:

```python
call_tool("gobby-tasks", "build_task_tree", {
    "tree": {
        "title": "{Epic Title}",
        "task_type": "epic",
        "description": "See plan: .gobby/plans/{name}.md",
        "children": [
            {
                "title": "Phase 1: {Phase Name}",
                "children": [
                    {"title": "Task 1", "category": "code"},
                    {"title": "Task 2", "category": "code", "depends_on": ["Task 1"]}
                ]
            },
            {
                "title": "Phase 2: {Phase Name}",
                "children": [
                    {"title": "Task 3", "category": "code", "depends_on": ["Phase 1: {Phase Name}"]},
                    {"title": "Task 4", "category": "document"}
                ]
            }
        ]
    },
    "session_id": "<your_session_id>"
})
```

**Note on session_id**:
- Required parameter provided by the runtime environment
- Available in the `SessionStart` hook context at conversation start
- Look for `session_id: <uuid>` in the startup system reminder
- If not found, omit the parameter and the system will use the current session
- Invalid session_id returns an error; the task is not created

The tool returns:
- `task_refs`: All created task refs (["#42", "#43", ...])
- `epic_ref`: The root epic ref ("#42")
- `tasks_created`: Total count

**Update plan doc** with task refs:
- Fill in Task Mapping table with created task refs (#N)
- Use Edit tool to update `.gobby/plans/{name}.md`

## Step 7: Task Verification

After creating all tasks:
1. Show the created task tree (call `list_tasks` with `parent_task_id`)
2. Confirm task count matches plan items
3. Show the updated plan doc with task refs

## Task Granularity Guidelines

Each task should be:
- **Atomic**: Completable in one session (< 2 hours work)
- **Testable**: Has clear pass/fail criteria
- **Verb-led**: Starts with action verb (Add, Create, Implement, Update, Remove)
- **Scoped**: References specific files/functions when possible

Good: "Add TaskEnricher class to src/gobby/tasks/enrich.py"
Bad: "Implement enrichment" (too vague)

## TDD Compatibility (IMPORTANT)

The /gobby-plan skill creates **coarse-grained tasks** knowing that:
1. `expand_task` decomposes them into subtasks
2. TDD sandwich pattern is applied at the parent/epic level

### TDD Sandwich Pattern

The TDD sandwich wraps a parent task's implementation children:
- **ONE [TEST] task at the START** - Write tests for the entire feature
- **Multiple [IMPL] tasks in the MIDDLE** - Implementation subtasks
- **ONE [REFACTOR] task at the END** - Refactor after all impls pass

```
Parent Task
├── [TEST] Write tests for feature (first)
├── [IMPL] Subtask 1
├── [IMPL] Subtask 2
├── [IMPL] Subtask 3
└── [REFACTOR] Refactor feature code (last)
```

**DO NOT manually create:**
- "Write tests for: ..."
- "[TEST] ..." tasks
- "[IMPL] ..." tasks
- "[REFACTOR] ..." tasks
- Separate test tasks alongside implementation tasks

These are automatically generated by `expand_task` when TDD mode is enabled.

**DO create:**
- High-level feature tasks (e.g., "Add user authentication")
- Set `category: "code"` for tasks that will get TDD treatment
- Set `category: "document"` for docs (skips TDD)
- Set `category: "config"` for config changes (gets TDD)

**Example - What the skill creates:**
```json
{"title": "Add database schema", "category": "code"}
{"title": "Create API endpoint", "category": "code", "depends_on": ["Add database schema"]}
{"title": "Write API documentation", "category": "document"}
```

**After expand_task with TDD sandwich, this becomes:**
- Add database schema (parent)
  - [TEST] Write tests for database schema
  - [IMPL] Add database schema
  - [REFACTOR] Refactor database schema code
- Create API endpoint (parent)
  - [TEST] Write tests for API endpoint
  - [IMPL] Create API endpoint
  - [REFACTOR] Refactor API endpoint code
- Write API documentation (no TDD - it's a document)

## Example Usage

User: `/gobby-plan`
Agent: "What feature would you like to plan?"
User: "Add dark mode support to the app"
Agent: [Asks clarifying questions]
Agent: [Writes plan to .gobby/plans/dark-mode.md]
Agent: [Runs verification - removes any test tasks found]
Agent: "Here's the plan. Does this look correct?"
User: "Yes, create the tasks"
Agent: [Creates epic + phases + tasks]
Agent: "Created 12 tasks under epic #47. The plan has been updated with task refs."
