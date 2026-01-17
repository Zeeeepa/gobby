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

**Dependency Notation:**
- Use `(depends: Task 1)` or `(depends: Phase N)` in markdown
- Dependencies are resolved when tasks are created via `create_task` with `parent_task_id`

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

Ensure each task has a valid category:
- `code` - Implementation tasks (gets TDD triplets)
- `config` - Configuration changes (gets TDD triplets)
- `docs` - Documentation tasks (no TDD)
- `test` - Test infrastructure (no TDD)
- `research` - Investigation tasks (no TDD)
- `planning` - Architecture/design (no TDD)
- `manual` - Manual verification (no TDD)

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

**IMPORTANT**: `expand_task` creates FLAT children only - it does not create nested hierarchies.
To get a proper Epic → Phases → Tasks structure, you must create the hierarchy manually.

**Required: session_id** - All `create_task` calls require a `session_id` parameter. Find your session ID in the SessionStart hook context (look for `session_id: <uuid>` in the startup system reminder).

### 6a. Create the Root Epic

```python
epic = call_tool("gobby-tasks", "create_task", {
    "title": "{Epic Title}",
    "task_type": "epic",
    "description": "See .gobby/plans/{name}.md",
    "session_id": "<your_session_id>"
})
# Returns: {"ref": "#42", ...}
```

### 6b. Create Phase Epics Manually

For EACH phase in your plan, create a child epic. Include the phase's task list in the description
so `expand_task` knows what leaf tasks to create:

```python
# Phase 1
phase1 = call_tool("gobby-tasks", "create_task", {
    "title": "Phase 1: {Phase Name}",
    "task_type": "epic",
    "parent_task_id": "#42",  # Root epic ref
    "description": "{Phase goal}\n\nTasks:\n- Task 1 title (category: code)\n- Task 2 title (category: code)\n- Task 3 title (category: config)",
    "session_id": "<your_session_id>"
})
# Returns: {"ref": "#43", ...}

# Phase 2
phase2 = call_tool("gobby-tasks", "create_task", {
    "title": "Phase 2: {Phase Name}",
    "task_type": "epic",
    "parent_task_id": "#42",
    "description": "{Phase goal}\n\nTasks:\n- Task 4 title (category: code)\n- Task 5 title (category: document)",
    "session_id": "<your_session_id>"
})
# ... repeat for each phase in the plan
```

### 6c. Expand Each Phase Epic

Now expand each phase to generate leaf tasks + TDD sandwich:

```python
# Expand Phase 1 - LLM creates leaf tasks from the description
call_tool("gobby-tasks", "expand_task", {
    "task_id": "#43",
    "session_id": "<your_session_id>"
})

# Expand Phase 2
call_tool("gobby-tasks", "expand_task", {
    "task_id": "#44",
    "session_id": "<your_session_id>"
})

# ... repeat for each phase
```

**What expand_task does per phase:**
- LLM reads the phase title + description
- Creates feature tasks as children of the phase epic
- Each feature task (category: code/config) gets TDD triplets: [TDD] → [IMPL] → [REF]
- Sets `is_expanded=True` on the phase

### 6d. Update Plan Doc with Task Refs

After all expansions complete:

```python
# Get the full task tree
call_tool("gobby-tasks", "list_tasks", {
    "parent_task_id": "#42",
    "session_id": "<your_session_id>"
})
```

- Fill in Task Mapping table with created task refs
- Use Edit tool to update `.gobby/plans/{name}.md`

## Step 7: Task Verification

After creating all tasks:
1. Show the created task tree (call `list_tasks` with `parent_task_id`)
2. Confirm task count matches plan items
3. Show the updated plan doc with task refs

## Task Granularity Guidelines

Each task should be:
- **Atomic**: Completable in one AI session 
- **Testable**: Has clear pass/fail criteria
- **Verb-led**: Starts with action verb (Add, Create, Implement, Update, Remove)
- **Scoped**: References specific files/functions when possible

Good: "Add TaskEnricher class to src/gobby/tasks/enrich.py"
Bad: "Implement enrichment" (too vague)

## TDD Compatibility (IMPORTANT)

The /gobby-plan skill creates **feature tasks** knowing that `expand_task` will apply TDD triplets to each one.

### TDD Triplet Pattern

Each feature task (category: code) gets expanded into three children:
- **[TDD]** - Write failing tests first
- **[IMPL]** - Make tests pass
- **[REF]** - Refactor while keeping tests green

```
Feature Task
├── [TDD] Write failing tests for feature
├── [IMPL] Implement feature
└── [REF] Clean up, verify tests pass
```

### Task Categories

Valid categories (from `src/gobby/storage/tasks.py`):
- `code` - Implementation tasks (gets TDD triplets)
- `config` - Configuration changes (gets TDD triplets)
- `docs` - Documentation tasks (no TDD)
- `test` - Test infrastructure tasks (no TDD)
- `research` - Investigation tasks (no TDD)
- `planning` - Architecture/design tasks (no TDD)
- `manual` - Manual verification tasks (no TDD)

### What You Create vs What expand_task Produces

**DO NOT manually create:**
- `[TDD]`, `[IMPL]`, `[REF]` prefixed tasks
- "Write tests for: ..." tasks
- "Ensure tests pass" tasks
- Separate test tasks alongside implementation

**DO create:**
- Feature tasks with `category: "code"` or `category: "config"`
- Documentation tasks with `category: "docs"`

**Example - What the skill creates (plan):**

```
Phase 1: Backend Setup
├── Create protocol.py with type definitions (category: code)
├── Create backends/__init__.py with factory (category: code)
├── Add config schema for backend selection (category: config)
```

**After expand_task, this becomes:**

```
○ #100  Phase 1: Backend Setup [epic]
○ #101  ├── Create protocol.py with type definitions
○ #102  │   ├── [TDD] Write failing tests for protocol.py types
○ #103  │   ├── [IMPL] Implement MemoryCapability, MemoryQuery, MemoryRecord
○ #104  │   └── [REF] Clean up protocol.py, verify tests pass
○ #105  ├── Create backends/__init__.py with factory
○ #106  │   ├── [TDD] Write failing tests for backend factory
○ #107  │   ├── [IMPL] Implement get_backend() factory function
○ #108  │   └── [REF] Clean up factory, verify tests pass
○ #109  └── Add config schema for backend selection
○ #110      ├── [TDD] Write failing tests for config loading
○ #111      ├── [IMPL] Add memory.backend config option
○ #112      └── [REF] Clean up, verify tests pass
```

### Hierarchy

```
Root Epic
└── Phase Epic
    └── Feature Task (category: code)
        ├── [TDD] Write failing tests
        ├── [IMPL] Implementation
        └── [REF] Refactor/cleanup
```

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
