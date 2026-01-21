# Task Expansion System Analysis

## Executive Summary

The task expansion system has solid foundations but suffers from three critical issues:
1. **Extreme linear dependency chains** (72% of tasks have exactly 1 dep)
2. **Inconsistent TDD application** (phase-level vs feature-level)
3. **Context overload** leading to LLM hallucination

This analysis identifies root causes and proposes structural improvements to make expansion more deterministic.

---

## Current State: What's Working

- **JSON schema output** - LLM reliably produces structured JSON
- **Test task filtering** - Catches most duplicate test tasks via regex
- **Context gathering** - Rich context from codebase, tests, verification commands
- **TDD sandwich pattern** - Correct RED/GREEN/BLUE structure
- **Graceful degradation** - Timeouts and errors don't crash the system

---

## Critical Issues Found

### 1. Extreme Linear Coupling (THE BIG ONE)

From the Task System V2 expansion (40 subtasks):
- **72.5% have exactly 1 dependency** - creates serial execution
- **Max dependency chain: 15 levels deep**
- **Only 5 root tasks** - everything else is blocked

**Example of the problem:**
```
Task 37 (CLI) → 36 → 35 → 34 → 28 → 23 → 21 → 4 → 3 (migration tests)
```

One slow task at position 3 blocks 34 downstream tasks.

**Root cause**: The prompt says "Order your array logically - dependencies should come before dependents" but doesn't incentivize parallelization. The LLM defaults to serial ordering.

### 2. TDD Applied at Wrong Level

The system applies TDD sandwich at the PHASE level:
```
Phase 1 Epic
├── [TEST] Write tests for Phase 1...  ← ONE test task for entire phase
├── Feature A
├── Feature B
├── Feature C
└── [REF] Refactor Phase 1...         ← ONE refactor for entire phase
```

**Should be** per-feature:
```
Phase 1 Epic
├── Feature A
│   ├── [TDD] Write failing tests for A
│   ├── [IMPL] Implement A
│   └── [REF] Refactor A
├── Feature B
│   ├── [TDD] Write failing tests for B
│   ...
```

Note: Task `#4422` addressed this - need to verify it's working.

### 3. Prompt Contradictions

| Issue | Location | Problem |
|-------|----------|---------|
| Category optional vs required | Line 49 vs 111 | "Yes*" then "MUST have" |
| "test" category mentioned | Line 27 schema | Listed but forbidden |
| No parallelization guidance | Rules section | No incentive for parallel work |
| Atomicity: "10-30 mins" | Line 108 | Subjective, unenforceable |

---

## What in Plan Files Could Throw Off the LLM

### 1. Checkbox Format Confusion
```markdown
- [ ] Create Skill dataclass with all spec fields (category: code)
- [ ] Create `validate_skill_name()` per spec (category: code)
```

The `- [ ]` checkbox format may cause the LLM to:
- Generate checkbox-style output instead of JSON
- Copy the format into task descriptions
- Interpret checkboxes as optional items

### 2. Too Much Implementation Detail

The plan includes full code examples:
```python
@dataclass
class Skill:
    id: str
    name: str
    description: str
    ...
```

This causes the LLM to copy code into task descriptions rather than decompose.

### 3. Comparison Tables

Tables mapping Feature A → Feature B may cause:
- Tasks framed as "implement X equivalent" vs concrete actions
- Confusion between source and target

### 4. Mixed Categories in Single Phase

Phases that include:
- `code` tasks (dataclass, validation functions)
- `config` tasks (migration)
- Implicit `test` tasks (acceptance criteria)

The LLM may generate all categories mixed together without proper separation.

### 5. External URLs and Sources

```markdown
## Sources
- [External GitHub](https://github.com/example/repo)
- [Specification](https://example.io/spec)
```

May trigger "research" mode or web-fetch attempts instead of implementation.

---

## Recommendations: Making Expansion More Deterministic

### A. Structural Changes (High Impact)

#### 1. Add Parallelization Score to Output Schema
```json
{
  "subtasks": [...],
  "parallelization_score": 0.65,  // 0-1, higher = more parallel
  "max_chain_depth": 4,           // Maximum dependency chain
  "root_task_count": 5            // Tasks with no dependencies
}
```

Add to prompt:
> "Aim for parallelization_score >= 0.5 and max_chain_depth <= 5.
> Independent tasks (tests, docs, migrations) should have `depends_on: []`."

#### 2. Two-Phase Expansion

**Phase A: Structure** (fast, deterministic)
- Task titles only
- Dependencies graph
- Categories
- No descriptions

**Phase B: Details** (can be deferred)
- Rich descriptions
- Validation criteria
- Implementation notes

Benefits:
- Faster iteration on structure
- Descriptions can be generated on-demand
- Easier to review/correct

#### 3. Template-Based Generation for Common Patterns

Instead of LLM generation for known patterns:

```python
PATTERN_TEMPLATES = {
    "migration": [
        {"title": "Write tests for {name} migration", "category": "code", "deps": []},
        {"title": "Implement {name} migration", "category": "config", "deps": [0]},
    ],
    "crud_manager": [
        {"title": "Define {name} dataclass", "category": "code", "deps": []},
        {"title": "Implement {name}Manager CRUD", "category": "code", "deps": [0]},
        {"title": "Add {name} CLI commands", "category": "code", "deps": [1]},
    ],
    "mcp_tool": [
        {"title": "Implement {name} MCP tool", "category": "code", "deps": []},
        {"title": "Register {name} in MCP registry", "category": "config", "deps": [0]},
    ],
}
```

Benefits:
- 100% deterministic for known patterns
- Consistent naming and structure
- LLM only handles novel decomposition

#### 4. Dependency Graph Validation

Post-expansion validation:
```python
def validate_dependency_graph(subtasks: list[Subtask]) -> list[str]:
    issues = []

    # Check parallelization
    root_tasks = [t for t in subtasks if not t.depends_on]
    if len(root_tasks) < len(subtasks) * 0.2:
        issues.append(f"Only {len(root_tasks)} root tasks - low parallelization")

    # Check chain depth
    max_depth = calculate_max_depth(subtasks)
    if max_depth > 5:
        issues.append(f"Dependency chain too deep: {max_depth}")

    # Check for artificial serialization
    single_dep_tasks = [t for t in subtasks if len(t.depends_on) == 1]
    if len(single_dep_tasks) > len(subtasks) * 0.5:
        issues.append("Too many single-dependency tasks - likely artificial serialization")

    return issues
```

#### 5. LLM Self-Critique Pass

After initial expansion, run a critique pass:
```
Given this task graph, identify:
1. Tasks that could be parallelized but aren't
2. Artificial dependencies that should be removed
3. Missing dependencies that would cause issues

Suggest a revised dependency graph.
```

### B. Prompt Improvements (Medium Impact)

#### 1. Add Parallelization Rules
```markdown
## Dependency Rules

1. **Maximize parallelization**: Tasks that don't share code should have NO dependencies
2. **Independent tests**: Test tasks for different modules should run in parallel
3. **Migrations before code**: But multiple migrations can run in parallel
4. **Docs are always parallel**: Documentation never blocks code

### Dependency Anti-Patterns (AVOID)
- Linear chains: A → B → C → D → E (bad)
- Single root: Everything depends on one task (bad)
- Serial tests: Test A → Test B → Test C (bad)

### Good Patterns
- Diamond: A → [B, C] → D (good - B and C parallel)
- Forest: [A, B, C] (good - independent roots)
- Fan-out: A → [B, C, D, E] (good - parallel after setup)
```

#### 2. Fix Category Schema
Remove "test" from schema entirely. Current:
```json
"category": "code|config|docs|research|planning|manual (NOT test)"
```

Change to:
```json
"category": "code|config|docs|refactor|research|planning|manual"
```

#### 3. Add Concrete Examples of Parallel Tasks
```markdown
## Example: Database Feature

```json
{
  "subtasks": [
    {"title": "Add users migration", "category": "config", "depends_on": []},
    {"title": "Add sessions migration", "category": "config", "depends_on": []},
    {"title": "Implement UserManager", "category": "code", "depends_on": [0]},
    {"title": "Implement SessionManager", "category": "code", "depends_on": [1]},
    {"title": "Add users CLI", "category": "code", "depends_on": [2]},
    {"title": "Add sessions CLI", "category": "code", "depends_on": [3]},
    {"title": "Update docs", "category": "docs", "depends_on": []}
  ]
}
```

Note: Migrations 0,1 are parallel. CLI tasks 4,5 are parallel. Docs task 6 is independent.
```

### C. Plan File Improvements

#### 1. Use Structured Task Blocks Instead of Checkboxes
```markdown
## Phase 1 Tasks

### Task: Skill Dataclass
- **Category**: code
- **Files**: src/gobby/storage/skills.py
- **Depends**: None (root task)
- **Acceptance**: Skill dataclass importable, has all fields from spec

### Task: validate_skill_name()
- **Category**: code
- **Files**: src/gobby/skills/validator.py
- **Depends**: None (parallel with dataclass)
- **Acceptance**: Rejects uppercase, consecutive hyphens, >64 chars
```

#### 2. Remove Code Examples from Plan
Instead of:
```python
@dataclass
class Skill:
    id: str
    name: str
```

Use:
```markdown
Skill dataclass fields: id, name, description, version, license,
compatibility, allowed_tools, metadata, content, source_path,
source_type, source_ref, enabled, project_id, created_at, updated_at
```

#### 3. Separate External References
Move sources to a separate `## References` section at the end, clearly marked as "for human reference only, not for LLM context."

---

## Comparison: Gobby vs Beads vs Task Master AI

| Feature | Gobby | Beads | Task Master |
|---------|-------|-------|-------------|
| JSON output | Yes | Yes | Yes |
| Dependency graphs | Yes (needs work) | Basic | Advanced |
| TDD integration | Yes (sandwich) | No | Optional |
| Codebase context | Rich | Limited | Medium |
| Parallelization | Weak | N/A | Better |
| Template patterns | No | No | Yes |
| Self-critique | No | No | Yes |
| Validation | Basic | None | Strong |

**Key differentiators Gobby should add:**
1. Template-based expansion for common patterns
2. Parallelization scoring and validation
3. Two-phase expansion (structure → details)
4. Self-critique pass for dependency optimization

---

## Unified Expansion Workflow: `gobby tasks expand-plan`

### Core Concept

The plan file IS the task description. When you run `expand_task` on a task whose description contains a structured plan, the expansion should produce the same results whether it's:
- A single feature task with inline spec
- An epic with a full plan file loaded as description

### Proposed Command

```bash
gobby tasks expand-plan <plan-file> [--epic-title "..."] [--dry-run]
```

Or via MCP:
```python
call_tool("gobby-tasks", "expand_plan", {
    "plan_path": "docs/plans/gobby-skills.md",
    "epic_title": "gobby-skills: SkillPort-compatible Skill Management"
})
```

### Workflow Steps (12 Steps - 4 Key Differentiators Integrated)

```
┌─────────────────────────────────────────────────────────────────┐
│  1. LOAD: Read plan file, extract structured content            │
└─────────────────────────────────┬───────────────────────────────┘
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│  2. NORMALIZE: Convert to canonical format                      │
│     - Strip markdown artifacts (checkboxes, code blocks)        │
│     - Extract phases, tasks, acceptance criteria                │
│     - Validate structure (required fields present)              │
└─────────────────────────────────┬───────────────────────────────┘
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│  3. FILTER TEST TASKS (PRE): Strip before any processing        │
│     - Remove "Write tests for X" tasks from plan text           │
│     - Remove tasks with category: test                          │
│     - Preserve acceptance criteria (different from test tasks)  │
└─────────────────────────────────┬───────────────────────────────┘
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│  4. CREATE ROOT: Create epic task with normalized plan as desc  │
│     - Title from plan frontmatter or --epic-title               │
│     - Description = full normalized plan                        │
│     - task_type = "epic"                                        │
└─────────────────────────────────┬───────────────────────────────┘
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│  5. PHASE A - STRUCTURE: Extract skeleton (fast, deterministic) │  ← TWO-PHASE
│     - Parse phase sections → phase epics                        │     EXPANSION
│     - Parse features → feature tasks (titles + categories only) │
│     - Wire inter-phase dependencies (Phase 2 → Phase 1)         │
│     - Wire intra-phase dependencies from explicit Depends: field│
│     - NO descriptions yet, NO LLM involved                      │
└─────────────────────────────────┬───────────────────────────────┘
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│  6. TEMPLATE MATCHING: Apply templates for known patterns       │  ← TEMPLATE-BASED
│     - Detect: migration, crud_manager, mcp_tool, cli_command    │     EXPANSION
│     - For matches: expand using PATTERN_TEMPLATES (100% determ) │
│     - For non-matches: mark for LLM enrichment                  │
│     - Templates define: subtasks, categories, dependencies      │
└─────────────────────────────────┬───────────────────────────────┘
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│  7. PHASE B - DETAILS: LLM enrichment for non-template tasks    │  ← TWO-PHASE
│     - Only for features NOT matched by templates                │     EXPANSION
│     - Only for features lacking acceptance criteria             │
│     - LLM adds: descriptions, validation criteria               │
│     - Strict: NO new subtasks, NO scope creep                   │
│     - Skip with --no-enrich for pure deterministic mode         │
└─────────────────────────────────┬───────────────────────────────┘
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│  8. TDD SANDWICH: Apply to code/config features                 │
│     - Create [TDD] task per feature (not per phase!)            │
│     - Mark implementation tasks as [IMPL]                       │
│     - Create [REF] task per feature                             │
│     - Wire: [TDD] → [IMPL]* → [REF]                             │
└─────────────────────────────────┬───────────────────────────────┘
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│  9. FILTER TEST TASKS (POST): Remove any LLM-generated tests    │
│     - Remove test tasks LLM may have generated in step 7        │
│     - ONLY TDD sandwich test tasks survive                      │
│     - Log filtered tasks for debugging                          │
└─────────────────────────────────┬───────────────────────────────┘
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│  10. VALIDATE GRAPH: Check dependency structure                 │  ← PARALLELIZATION
│      - Calculate parallelization_score (root_tasks / total)     │     SCORING &
│      - Calculate max_chain_depth (longest dependency path)      │     VALIDATION
│      - Detect circular dependencies                             │
│      - Detect orphaned tasks (no path to root)                  │
│      - Thresholds: chain_depth ≤ 5, parallelization ≥ 0.4      │
└─────────────────────────────────┬───────────────────────────────┘
                                  ▼
                         ┌───────┴───────┐
                         │ Validation OK? │
                         └───────┬───────┘
                    Yes ─────────┼───────── No
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│  11. SELF-CRITIQUE & AUTO-FIX: LLM optimizes dependencies       │  ← SELF-CRITIQUE
│      - LLM analyzes the task graph                              │     PASS
│      - Identifies: artificial serialization, missing parallels  │
│      - Proposes: dependency removals, restructuring             │
│      - Shows diff to user (or auto-applies with --auto-fix)     │
│      - Re-validates after fixes                                 │
└─────────────────────────────────┬───────────────────────────────┘
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│  12. OUTPUT: Return task tree ready for execution               │
│      - root_task_id, phase_count, feature_count, total_tasks    │
│      - parallelization_score, max_chain_depth                   │
│      - graph_fixes_applied (if any)                             │
│      - warnings (if any)                                        │
│      - task_tree (if --dry-run)                                 │
└─────────────────────────────────────────────────────────────────┘
```

### The 4 Key Differentiators - Where They Appear

| Differentiator | Step | Description |
|----------------|------|-------------|
| **1. Template-based expansion** | Step 6 | Known patterns (migration, CRUD, MCP) use deterministic templates |
| **2. Parallelization scoring** | Step 10 | Graph validation calculates scores, enforces thresholds |
| **3. Two-phase expansion** | Steps 5+7 | Structure first (fast), details later (can be skipped) |
| **4. Self-critique pass** | Step 11 | LLM reviews graph, suggests/applies dependency optimizations |

### Plan File Format (Canonical)

To make expansion deterministic, plan files should follow this structure:

```markdown
---
title: Feature Name
phases: 7
---

## Phase 1: Storage Layer

### Dependencies
- None (root phase)

### Features

#### Feature: Skill Dataclass
- **Category**: code
- **Files**: src/gobby/storage/skills.py
- **Acceptance**:
  - Skill dataclass importable from gobby.storage.skills
  - Has fields: id, name, description, version, ...
  - Passes mypy type checking

#### Feature: validate_skill_name()
- **Category**: code
- **Files**: src/gobby/skills/validator.py
- **Depends**: None (parallel with Skill Dataclass)
- **Acceptance**:
  - Rejects names with uppercase letters
  - Rejects names with consecutive hyphens
  - Rejects names longer than 64 characters
  - Returns True for valid names

#### Feature: Skills Migration v67
- **Category**: config
- **Files**: src/gobby/storage/migrations.py
- **Acceptance**:
  - Migration creates skills table
  - Table has all required columns
  - Migration is idempotent

## Phase 2: Search Integration

### Dependencies
- Phase 1

### Features
...
```

### Key Differences from Current System

| Current | Proposed |
|---------|----------|
| LLM generates task structure | Plan file defines structure, LLM enriches details |
| Checkboxes in plan | Both formats supported (normalizer converts) |
| Implicit dependencies | Explicit `Depends:` field (or inferred from bullets) |
| TDD at phase level | TDD at feature level |
| Test tasks filtered post-hoc | Test tasks stripped pre AND post processing |
| No validation of graph | Graph validation with LLM auto-fix |

### Design Decisions

1. **Plan Format**: Support BOTH checkbox and canonical formats
   - Normalizer auto-converts `- [ ] Task` to feature blocks
   - Existing plans work without modification
   - Canonical format recommended for new plans

2. **LLM Enrichment**: Enabled by default, opt-out with `--no-enrich`
   - LLM adds implementation details to underspecified features
   - Strict scope: no new features, only details
   - `--no-enrich` for pure deterministic mode

3. **Graph Validation Failure**: LLM auto-fix with approval
   - When chain depth > 5 or parallelization < 0.4
   - LLM suggests dependency restructuring
   - Shows diff, applies if user approves (or `--auto-fix`)

### Implementation Components

1. **PlanParser** (`src/gobby/tasks/plan_parser.py`)
   - Parse markdown plan files
   - Extract frontmatter, phases, features
   - Normalize to canonical structure

2. **PlanNormalizer** (`src/gobby/tasks/plan_normalizer.py`)
   - Strip checkboxes, code blocks
   - Convert bullet lists to feature blocks
   - Validate required fields

3. **TestTaskFilter** (`src/gobby/tasks/test_filter.py`)
   - Pre-processing: strip test tasks from plan text (step 3)
   - Post-processing: remove test tasks from expansion output (step 9)
   - Whitelist: only TDD sandwich tests survive

4. **TaskTreeBuilder** (`src/gobby/tasks/tree_builder.py`)
   - Create task hierarchy from normalized plan
   - Wire dependencies from explicit `Depends:` fields
   - Assign categories
   - **Two-phase**: Structure only in first pass (step 5)

5. **PatternTemplates** (`src/gobby/tasks/templates.py`) ← **KEY DIFFERENTIATOR #1**
   - Template definitions for common patterns:
     ```python
     PATTERN_TEMPLATES = {
         "migration": [...],      # DB migration pattern
         "crud_manager": [...],   # Manager class pattern
         "mcp_tool": [...],       # MCP tool pattern
         "cli_command": [...],    # CLI command pattern
         "dataclass": [...],      # Dataclass + validation pattern
     }
     ```
   - Pattern detection from feature titles/descriptions
   - 100% deterministic expansion for matched patterns

6. **LLMEnricher** (`src/gobby/tasks/enricher.py`) ← **KEY DIFFERENTIATOR #3 (Phase B)**
   - Add descriptions to skeleton tasks
   - Generate validation criteria
   - Strict scope: NO new subtasks allowed
   - Skipped with `--no-enrich`

7. **GraphValidator** (`src/gobby/tasks/graph_validator.py`) ← **KEY DIFFERENTIATOR #2**
   - Calculate `parallelization_score = root_tasks / total_tasks`
   - Calculate `max_chain_depth` via BFS/DFS
   - Detect circular dependencies
   - Detect orphaned tasks
   - Return structured validation result

8. **GraphOptimizer** (`src/gobby/tasks/graph_optimizer.py`) ← **KEY DIFFERENTIATOR #4**
   - LLM self-critique prompt:
     ```
     Given this task dependency graph, identify:
     1. Artificial serialization (tasks that could run in parallel)
     2. Unnecessary dependencies (A→B where B doesn't need A)
     3. Missing dependencies (would cause runtime issues)

     Output a list of changes: {action: "remove"|"add", from: X, to: Y}
     ```
   - Generate diff showing proposed changes
   - Apply fixes if user approves or `--auto-fix`
   - Re-validate after fixes

### MCP Tool Schema

```python
@tool
async def expand_plan(
    plan_path: str,                    # Path to plan file
    epic_title: str | None = None,     # Override title from frontmatter
    dry_run: bool = False,             # Preview without creating tasks
    no_enrich: bool = False,           # Skip LLM enrichment (deterministic only)
    skip_tdd: bool = False,            # Skip TDD sandwich
    auto_fix: bool = False,            # Auto-apply LLM graph fixes without prompt
    session_id: str | None = None,     # For task creation
) -> dict:
    """
    Expand a plan file into a complete task tree.

    Returns:
        {
            "root_task_id": "...",
            "phase_count": 7,
            "feature_count": 42,
            "total_tasks": 126,  # Including TDD tasks
            "parallelization_score": 0.65,
            "max_chain_depth": 4,
            "graph_fixes_applied": [...],  # If auto-fix or user approved
            "warnings": [...],
            "task_tree": {...}  # If dry_run=True
        }
    """
```

### CLI Command

```bash
# Full expansion from plan file (LLM enrichment ON by default)
gobby tasks expand-plan docs/plans/gobby-skills.md

# Preview without creating tasks
gobby tasks expand-plan docs/plans/gobby-skills.md --dry-run

# Pure deterministic mode (no LLM involvement)
gobby tasks expand-plan docs/plans/gobby-skills.md --no-enrich

# Skip TDD (for non-code plans)
gobby tasks expand-plan docs/plans/architecture.md --skip-tdd

# Auto-fix graph issues without prompting
gobby tasks expand-plan docs/plans/gobby-skills.md --auto-fix

# Override title
gobby tasks expand-plan docs/plans/gobby-skills.md --title "Skills System v2"

# Combine flags
gobby tasks expand-plan docs/plans/gobby-skills.md --dry-run --no-enrich
```

---

## Proposed Implementation Priority

### Phase 1: Foundation (Steps 1-5)
1. **PlanParser** - Parse markdown, extract frontmatter, phases, features
2. **PlanNormalizer** - Strip checkboxes, convert formats
3. **TestTaskFilter** - Pre-strip test tasks before processing
4. **TaskTreeBuilder** - Structure-only pass (titles, categories, deps)

### Phase 2: Templates (Step 6) ← **DIFFERENTIATOR #1**
5. **PatternTemplates** - Define templates for migration, CRUD, MCP, CLI patterns
6. **PatternMatcher** - Detect patterns from feature titles/descriptions
7. **TemplateExpander** - Apply templates deterministically

### Phase 3: Enrichment (Step 7) ← **DIFFERENTIATOR #3 (Phase B)**
8. **LLMEnricher** - Add descriptions, validation criteria
9. **ScopeGuard** - Reject any new subtasks from LLM

### Phase 4: TDD + Filtering (Steps 8-9)
10. **TDD integration** - Per-feature sandwich (existing `tdd.py`)
11. **TestTaskFilter (post)** - Remove LLM-generated test tasks

### Phase 5: Validation + Optimization (Steps 10-11) ← **DIFFERENTIATORS #2, #4**
12. **GraphValidator** - Parallelization scoring, chain depth, cycles
13. **GraphOptimizer** - LLM self-critique, dependency restructuring
14. **FixApplier** - Apply approved changes, re-validate

### Phase 6: Interface (Step 12)
15. **MCP tool** - `expand_plan` in `mcp_proxy/tools/`
16. **CLI command** - `gobby tasks expand-plan`
17. **Dry-run support** - Preview without creating tasks
18. **Integration** - Route `expand_task` to plan parser when detected

---

## Verification

After implementing changes, verify with:

1. **Expand Phase 1 of a test plan**
   - Check: Root tasks >= 3
   - Check: Max chain depth <= 5
   - Check: No artificial serialization

2. **Compare parallelization scores**
   - Before: ~0.28 (only 5 root tasks out of 40)
   - Target: >= 0.50

3. **Time to first actionable task**
   - Before: Immediate (but blocked by chain)
   - Target: 3+ parallel starting points

---

## Backward Compatibility: expand_task with Plan Content

When `expand_task` is called on a task whose description contains structured plan content, it should:

1. **Detect plan format** - Check for phase headers, feature blocks, or YAML frontmatter
2. **Route to plan expansion** - If detected, use PlanParser instead of raw LLM expansion
3. **Fall back to LLM** - If not a plan, use current LLM-based expansion

```python
async def expand_task(task_id: str, ...) -> dict:
    task = manager.get_task(task_id)

    # Detect if description contains structured plan
    if _is_plan_content(task.description):
        # Use deterministic plan expansion
        return await _expand_from_plan(task, ...)
    else:
        # Use LLM-based expansion (current behavior)
        return await _expand_with_llm(task, ...)

def _is_plan_content(description: str) -> bool:
    """Detect if description is a structured plan."""
    indicators = [
        r"^## Phase \d+:",           # Phase headers
        r"^### Feature:",            # Feature blocks
        r"^---\n.*title:",           # YAML frontmatter
        r"^\*\*Category\*\*:",       # Feature metadata
        r"^\*\*Acceptance\*\*:",     # Acceptance criteria
    ]
    return any(re.search(p, description, re.MULTILINE) for p in indicators)
```

This means:
- Loading a plan into a task description, then running `expand_task` = same as `expand_plan`
- Existing tasks without plan format continue to use LLM expansion
- Gradual migration path

---

## Files to Modify

### New Files

| File | Purpose | Differentiator |
|------|---------|----------------|
| `src/gobby/tasks/plan_parser.py` | Parse markdown plan files | Foundation |
| `src/gobby/tasks/plan_normalizer.py` | Normalize to canonical format | Foundation |
| `src/gobby/tasks/tree_builder.py` | Build task tree (structure only) | **#3 Two-phase** |
| `src/gobby/tasks/test_filter.py` | Pre/post filter test tasks | Cleanup |
| `src/gobby/tasks/templates.py` | Pattern templates (migration, CRUD, etc.) | **#1 Templates** |
| `src/gobby/tasks/enricher.py` | LLM enrichment (Phase B - details) | **#3 Two-phase** |
| `src/gobby/tasks/graph_validator.py` | Parallelization scoring, validation | **#2 Scoring** |
| `src/gobby/tasks/graph_optimizer.py` | LLM self-critique, dependency fixes | **#4 Self-critique** |
| `src/gobby/cli/tasks/expand_plan.py` | CLI command | Interface |
| `src/gobby/mcp_proxy/tools/expand_plan.py` | MCP tool | Interface |

### Modified Files

| File | Change |
|------|--------|
| `src/gobby/tasks/expansion.py` | Add plan detection, route to parser |
| `src/gobby/tasks/tdd.py` | Ensure per-feature application (not per-phase) |
| `src/gobby/tasks/prompts/expand.py` | Add parallelization rules (for LLM fallback) |
| `src/gobby/mcp_proxy/tools/task_expansion.py` | Integrate expand_plan, add detection |
| `src/gobby/cli/tasks/__init__.py` | Register expand-plan command |

---

## Verification Plan

### Unit Tests

1. **PlanParser**
   - Parses YAML frontmatter correctly
   - Extracts phases with dependencies
   - Extracts features with all metadata
   - Handles malformed input gracefully

2. **PlanNormalizer**
   - Strips checkboxes: `- [ ] Task` → `Task`
   - Converts bullets to feature blocks
   - Preserves acceptance criteria
   - Removes code examples from plan text

3. **TestTaskFilter**
   - Pre-filter removes "Write tests for X" from plan
   - Post-filter removes test tasks from expansion
   - TDD sandwich tasks are preserved
   - Regex patterns catch all variants

4. **GraphValidator**
   - Rejects chain depth > 5
   - Calculates parallelization score correctly
   - Detects circular dependencies
   - Reports all issues

### Integration Tests

1. **Full Pipeline**
   - `expand_plan` on test plan produces valid tree
   - All phases have correct dependencies
   - TDD applied per-feature, not per-phase
   - No duplicate test tasks

2. **Backward Compatibility**
   - `expand_task` on task with plan description works
   - `expand_task` on regular task uses LLM
   - `--cascade` still works for non-plan epics

### Manual Verification

```bash
# 1. Dry-run on a plan file
gobby tasks expand-plan docs/plans/example.md --dry-run
# Check: parallelization score, chain depth, test task count

# 2. Create real tasks
gobby tasks expand-plan docs/plans/example.md
# Verify: task tree in gobby tasks tree

# 3. Verify TDD structure
gobby tasks show #<feature-task>
# Check: [TDD], [IMPL], [REF] children
```

---

## Summary: What This Achieves

### Before (Current State)
- LLM generates task structure unpredictably
- 72% linear dependencies, 15-level chains
- TDD applied at phase level (wrong)
- CLI and MCP behave differently
- Test tasks leak through, require cleanup

### After (This Plan)
- Plan file defines structure deterministically
- LLM only enriches details (opt-out available)
- TDD applied per-feature (correct)
- Single `expand_plan` command for both CLI and MCP
- Test tasks filtered pre AND post, only TDD sandwich survives
- Graph validation with LLM auto-fix for bad structures

### Key Insight
The plan file content IS the task description. Whether you:
1. Run `gobby tasks expand-plan docs/plans/foo.md`
2. Create a task with plan content as description, then `expand_task`

...you get the same deterministic result. This unifies the workflow and makes expansion predictable.
