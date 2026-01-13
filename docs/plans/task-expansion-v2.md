# TDD Expansion Restructure Plan

## Overview

Restructure task expansion from a monolithic auto-decomposition system into a phased workflow with clear separation of concerns.

## Design Decisions

| Decision | Choice |
| :--- | :--- |
| Auto-decomposition | Remove from `create_task` entirely |
| Validation criteria | Move from `create_task` to `enrich_task` (was 6+ sec) |
| Expansion scope | Single-level in MCP tools; CLI handles cascade with progress UX |
| Research storage | Persist in `expansion_context` field on tasks |
| Task descriptions | Smart context extraction (Option C) |
| TDD transformation | Deterministic (no LLM needed) |
| Spec templates | Both: template file + documentation |
| Prompt storage | `~/.gobby/prompts/*.md` - not hardcoded in Python |
| Validation scope | Checks work completion only, not dependencies |
| Dependency interface | Accept seq_nums at API; storage stays UUID (non-breaking) |

## Schema Changes

### Rename: `test_strategy` -> `category`

Categories: `code`, `document`, `research`, `config`, `test`, `manual`

**Default**: `NULL` (uncategorized). Tasks without a category are not processed by `apply_tdd`.

### New field: `agent_name`

Optional field specifying which subagent file to use for this task.

- If set, the agent's default workflow applies
- `workflow_name` becomes an override of the agent's workflow

### Field requirements by context

| Field | MCP | CLI |
| :--- | :--- | :--- |
| `created_in_session_id` | **Required** (agents always have sessions) | Optional |
| `project_id` | From context or required | Optional (`--project/-p` flag) |

### CLI `--project/-p` flag

Accepts project **name** or **ID** (not just UUID - humans can't type those).

Needed because:

- Gobby can be installed globally, run outside project directories
- Personal tasks don't need project context ("pickup laundry", "lunch with Meghan")
- **Auto-detect**: Check if cwd is under a project path in `projects` table
- **Fallback**: Create task with `project_id=NULL` if can't determine and flag not set

### New field: `reference_doc`

Optional field to attach a spec/doc reference to a task.

- Path to the source document (e.g., `docs/plans/memory-v3.md`)
- Enables traceability from tasks back to requirements

### New fields: `is_enriched`, `is_expanded`, `is_tdd_applied`

Boolean flags for idempotent batch operations and recovery:

- `is_enriched: bool = False` - Set True after successful `enrich_task`
- `is_expanded: bool = False` - Set True after successful `expand_task`
- `is_tdd_applied: bool = False` - Set True after successful `apply_tdd`

Batch operations skip tasks where the relevant flag is already True.
Failed operations leave flag as False for retry.

### Category vs Labels

| Field | Purpose | Values |
| :--- | :--- | :--- |
| `category` | **Drives behavior** (TDD for code, skip for doc) | Single: code/document/research/config/test/manual |
| `labels` | **Filtering/grouping** (user-defined metadata) | Multiple, free-form |

Both are needed - category is functional, labels are organizational.

## Implementation Approach: Strangler Fig

Maintain functionality while refactoring:

1. **Deprecate first**: Add deprecation warnings to `auto_decompose`, `tdd_mode` in workflows
2. **Build new**: Implement new tools (`parse_spec`, `enrich_task`, `apply_tdd`)
3. **Migrate**: Update agents/docs to use new workflow
4. **Remove last**: Delete deprecated code in final cleanup phase

## Code Guidelines

- **Python files < 1000 lines** - decompose if larger
- Add to CLAUDE.md and memory

## Prompt Files

Two categories of prompts with different locations:

### System Prompts (`~/.gobby/prompts/`)

Internal prompts used by gobby's Python code. Agents don't interact with these directly.

| File | Purpose | Used By |
| :--- | :--- | :--- |
| `enrich-task.md` | Research and categorization | `enrich_task` tool |
| `expand-task.md` | Subtask generation | `expand_task` tool |
| `validate-criteria.md` | Validation criteria generation | `enrich_task` tool |

**Loading pattern:**

```python
def load_prompt(name: str) -> str:
    """Load prompt from ~/.gobby/prompts/{name}.md"""
    prompt_path = Path.home() / ".gobby" / "prompts" / f"{name}.md"
    if not prompt_path.exists():
        # Fall back to bundled default
        prompt_path = Path(__file__).parent / "prompts" / f"{name}.md"
    return prompt_path.read_text()
```

### Project Guides (`.gobby/docs/`)

Skill prompts and guides accessible to agents. Installed per-project from `src/gobby/install/shared/docs/`.

| File               | Purpose                       |
| ------------------ | ----------------------------- |
| `spec-planning.md` | Spec writing guide for agents |

**Install source:** `src/gobby/install/shared/docs/` → `.gobby/docs/`

**Installer update required:** Ensure `gobby install` copies `shared/docs/` to `.gobby/docs/`.

**Note:** This separation keeps system internals (`~/.gobby/`) out of agents' way.
Agents only interact with project-level resources (`.gobby/`).

## MCP Input Limits & Timeouts

### Input Character Limits

Check input size **before processing**. If too large, return immediately with CLI suggestion.

| Field | Limit | Rationale |
| :--- | :--- | :--- |
| `task.title` | 200 chars | Titles should be concise |
| `task.description` | 10,000 chars | Reasonable spec section |
| `task.expansion_context` | 50,000 chars | Research findings can be large |
| Combined input to LLM | 100,000 chars | Prevent context overflow |

**Enforcement in MCP tools:**

```python
async def enrich_task(task_id: str, ...):
    task = get_task(task_id)

    # Check input size before LLM call
    input_size = len(task.title or "") + len(task.description or "")
    if input_size > 10_000:
        return {
            "error": "task_too_large",
            "message": f"Task content ({input_size:,} chars) exceeds MCP limit",
            "suggestion": "Use CLI for large tasks",
            "cli_command": f"gobby tasks enrich #{task.seq_num} --timeout 30m"
        }

    # Proceed with LLM call...
```

### Timeouts

- **MCP tools**: 2 minute default (matches Claude Code Bash default)
- **CLI commands**: 10 minute default, `--timeout` flag for override
- **Subagent delegation**: 30 minute timeout for complex expansions

## New Workflow

```text
+-------------------+     +-------------------+     +-------------------+     +-------------------+
|   parse_spec      |---->|   enrich_task     |---->|   expand_task     |---->|    apply_tdd      |
|                   |     |                   |     |                   |     |                   |
| - Parse markdown  |     | - Research        |     | - Generate        |     | - Transform       |
| - Create epic     |     | - Categorize      |     |   subtasks        |     |   code tasks      |
| - Create phases   |     | - Store context   |     | - Use stored      |     |   into triplets   |
| - Create tasks    |     |                   |     |   context         |     |                   |
| - Smart context   |     |                   |     |                   |     | - Deterministic   |
|                   |     |                   |     |                   |     |   (no LLM)        |
+-------------------+     +-------------------+     +-------------------+     +-------------------+
     No LLM                  LLM                      LLM                    No LLM
```

## Implementation Plan

### Phase 1: Remove Auto-Decomposition and Validation from create_task

**File:** `src/gobby/mcp_proxy/tools/tasks.py`

1. Remove lines 326-395 (TDD expansion and fallback logic)
2. Remove `detect_multi_step` import and usage
3. Remove validation criteria auto-generation (lines 427-447)
4. Keep `create_task_with_decomposition` but with `auto_decompose=False` always
5. Remove/deprecate `auto_decompose` workflow variable
6. Make `session_id` required parameter in MCP tool
7. Update docstring to clarify create_task only creates ONE task, fast

**Before:**

```python
is_multi_step = detect_multi_step(description)
tdd_enabled = resolve_tdd_mode(session_id)
use_tdd_expansion = (...)
if use_tdd_expansion:
    # expensive LLM call

# Also remove:
should_generate = (...)
if should_generate and task_validator:
    criteria = await task_validator.generate_criteria(...)  # 6+ seconds!
```

**After:**

```python
# create_task just creates one task, no auto-expansion, no validation gen
task = task_manager.create_task(...)
```

### Phase 2: Smart Context Extraction in Spec Parser

**File:** `src/gobby/tasks/spec_parser.py`

1. Modify `TaskHierarchyBuilder._process_checkbox()` to build smart descriptions
2. Add method `_build_smart_description(checkbox, heading, spec_content)`:
   - Extract goal from parent heading
   - Extract related files/tasks mentioned
   - Format as focused context for this task

**New method:**

```python
def _build_smart_description(
    self,
    checkbox: CheckboxItem,
    heading: HeadingNode,
    all_checkboxes: list[CheckboxItem],
) -> str:
    """Build focused description with context from spec."""
    parts = []

    # Parent context
    if heading:
        parts.append(f"Part of: {heading.text}")

        # Extract goal if present
        goal_match = re.search(r'\*\*Goal\*\*:?\s*(.+?)(?:\n\n|\*\*)', heading.content)
        if goal_match:
            parts.append(f"Goal: {goal_match.group(1).strip()}")

    # Related tasks (siblings)
    siblings = [cb for cb in all_checkboxes
                if cb.parent_heading == heading.text and cb != checkbox]
    if siblings:
        parts.append(f"Related tasks: {', '.join(cb.text[:40] for cb in siblings[:3])}")

    return "\n\n".join(parts)
```

1. Update `_create_task` calls to use smart descriptions

### Phase 3: Database Migration

**New migration in:** `src/gobby/storage/migrations.py`

1. Rename column `test_strategy` -> `category`
2. Add new column `agent_name` (TEXT, nullable)
3. Update existing data: map old test_strategy values to categories
   - "manual" -> "manual"
   - "automated" -> "code"
   - `NULL` -> remains `NULL`

4. Add new column `reference_doc` (TEXT, nullable) - path to source spec
5. Add new columns `is_enriched`, `is_expanded` (BOOLEAN, default FALSE)

```sql
-- Rename test_strategy to category
ALTER TABLE tasks RENAME COLUMN test_strategy TO category;

-- Add agent_name column
ALTER TABLE tasks ADD COLUMN agent_name TEXT;

-- Add reference_doc column
ALTER TABLE tasks ADD COLUMN reference_doc TEXT;

-- Add expansion state flags
ALTER TABLE tasks ADD COLUMN is_enriched BOOLEAN DEFAULT FALSE;
ALTER TABLE tasks ADD COLUMN is_expanded BOOLEAN DEFAULT FALSE;
ALTER TABLE tasks ADD COLUMN is_tdd_applied BOOLEAN DEFAULT FALSE;
```

### Phase 4: Add enrich_task MCP Tool

**New file:** `src/gobby/tasks/enrich.py`

```python
@dataclass
class EnrichmentResult:
    task_id: str
    category: Literal["document", "research", "code", "config", "test", "manual"]
    complexity_score: int  # 1-5
    research_findings: str
    suggested_subtask_count: int
    validation_criteria: str  # Generated here, not in create_task
    mcp_tools_used: list[str]
```

**File:** `src/gobby/mcp_proxy/tools/task_expansion.py`

Add new tool:

**MCP Tool: `enrich_task`**

```text
Description:
    Research task(s) and store findings for later expansion.

    Gathers context from codebase, web, and MCP tools. Categorizes task,
    generates validation criteria, and stores findings in expansion_context.
    Sets is_enriched=True on successful completion.

    Batch operations skip tasks where is_enriched=True unless force=True.

Parameters:
    task_id: str (optional)
        Single task reference (e.g., "#42", "42", UUID)
        Mutually exclusive with task_ids

    task_ids: list[str] (optional)
        Multiple task references for batch parallel execution
        Mutually exclusive with task_id

    enable_code_research: bool = True
        Search codebase for relevant files, patterns, signatures

    enable_web_research: bool = False
        Search web for documentation, examples, best practices

    enable_mcp_tools: list[str] | None = None
        MCP servers to query (e.g., ["context7", "supabase"])

    generate_validation: bool = True
        Generate validation_criteria field (moved from create_task)

    force: bool = False
        Re-enrich even if is_enriched=True

    session_id: str (required)
        Current session ID for context

Returns:
    {
      "success": true,
      "enriched_count": 3,
      "skipped_count": 1,
      "results": [
        {
          "task_id": "uuid",
          "task_ref": "#42",
          "category": "code",
          "complexity_score": 3,
          "validation_criteria": "## Deliverable\n- [ ] ...",
          "findings": {
            "relevant_files": ["src/gobby/tasks/expansion.py"],
            "existing_patterns": "Uses TaskExpander class...",
            "dependencies": [],
            "suggested_approach": "Modify existing method...",
            "estimated_subtasks": 3
          }
        }
      ]
    }

Errors:
    - "task_id or task_ids required" - Neither parameter provided
    - "Cannot specify both task_id and task_ids" - Both provided
    - "Task not found: #42" - Invalid task reference
    - "Response too large" - Suggests CLI command with timeout
```

### Phase 5: Restructure expand_task

**File:** `src/gobby/mcp_proxy/tools/task_expansion.py`

1. Simplify to single-level expansion only
2. Use stored `expansion_context` if available
3. If no context, optionally call `enrich_task` first
4. Support batch parallel: `expand_task(task_ids=["#1", "#2", "#3"])`
5. Sets `is_expanded=True` on successful completion
6. Parent's `validation_criteria` updated to "All child tasks completed" (parent becomes container)

**MCP Tool: `expand_task`**

```text
Description:
    Expand task(s) into subtasks using LLM.

    Uses stored expansion_context from enrich_task if available.
    Single-level expansion only - does not recursively expand children.
    Sets is_expanded=True on successful completion.
    Parent's validation_criteria updated to "All child tasks completed".

    Batch operations skip tasks where is_expanded=True unless force=True.

Parameters:
    task_id: str (optional)
        Single task reference (e.g., "#42", "42", UUID)
        Mutually exclusive with task_ids

    task_ids: list[str] (optional)
        Multiple task references for batch parallel execution
        Mutually exclusive with task_id

    use_stored_context: bool = True
        Use expansion_context from prior enrich_task call

    enrich_if_missing: bool = True
        Auto-run enrich_task if expansion_context is empty

    force: bool = False
        Re-expand even if is_expanded=True (creates duplicate subtasks!)

    session_id: str (required)
        Current session ID for context

Returns:
    {
      "success": true,
      "expanded_count": 2,
      "skipped_count": 1,
      "results": [
        {
          "task_id": "uuid",
          "task_ref": "#42",
          "subtasks_created": 4,
          "subtasks": [
            {
              "task_id": "uuid",
              "task_ref": "#43",
              "title": "Create database schema",
              "category": "code",
              "depends_on": []
            },
            {
              "task_id": "uuid",
              "task_ref": "#44",
              "title": "Implement repository layer",
              "category": "code",
              "depends_on": [43]  // seq_num (API returns seq_nums, storage uses UUIDs)
            }
          ]
        }
      ]
    }

Errors:
    - "task_id or task_ids required" - Neither parameter provided
    - "Cannot specify both task_id and task_ids" - Both provided
    - "Task not found: #42" - Invalid task reference
    - "Task already has children" - Use force=True to expand anyway
    - "Response too large" - Suggests CLI command with timeout
```

### Phase 6: Add apply_tdd Tool

**New file:** `src/gobby/tasks/tdd_transform.py`

Deterministic transformation (no LLM):

```python
# Templated validation criteria for TDD phases
TDD_CRITERIA_RED = """## Deliverable
- [ ] Tests written that define expected behavior
- [ ] Tests fail when run (no implementation yet)
- [ ] Test coverage addresses acceptance criteria from parent task
"""

TDD_CRITERIA_BLUE = """## Deliverable
- [ ] All tests continue to pass
- [ ] Code refactored for clarity and maintainability
- [ ] No new functionality added (refactor only)
- [ ] Unrelated bugs discovered during refactor logged as new bug tasks

**Note:** If you discover bugs outside your scope during refactoring, create bug tasks
for them rather than fixing them now. Example: "I noticed 5 errors from outside my
scope, creating bug tasks for later agents..."
"""

PARENT_CRITERIA = """## Deliverable
- [ ] All child tasks completed
"""

TDD_SKIP_PATTERNS = [
    r"^Write tests for:",       # Already a TDD red task
    r"^Implement:",              # Already a TDD green task
    r"^Refactor:",               # Already a TDD blue task
    r"\b(delete|remove|deprecate|cleanup)\b",  # Deletion tasks have nothing to test
    r"(?i)\bupdate\b.*\.(md|yaml|yml|toml|json)\b",   # Doc/config file updates
]

def should_skip_tdd(task: Task) -> tuple[bool, str | None]:
    """Check if task should be skipped for TDD transformation.

    Returns (should_skip, reason) tuple.
    """
    # Skip non-code categories
    if task.category not in ("code", "config"):
        return True, f"category is '{task.category}'"

    # Skip already-processed tasks
    if task.is_tdd_applied:
        return True, "is_tdd_applied=True"

    # Skip tasks matching exclusion patterns
    title_lower = task.title.lower()
    for pattern in TDD_SKIP_PATTERNS:
        if re.search(pattern, task.title, re.IGNORECASE):
            return True, f"title matches skip pattern: {pattern}"

    return False, None

def transform_to_tdd_triplet(task: Task) -> list[Task]:
    """Transform a code/config task into Test->Implement->Refactor triplet."""
    # Check skip conditions
    should_skip, reason = should_skip_tdd(task)
    if should_skip:
        return []  # Caller should log the skip reason

    # Save parent's original criteria for the implement task
    original_criteria = task.validation_criteria

    test_task = create_task(
        title=f"Write tests for: {task.title}",
        description=task.description,
        validation_criteria=TDD_CRITERIA_RED,  # Templated
        parent_task_id=task.id,
    )

    impl_task = create_task(
        title=f"Implement: {task.title}",
        description=task.description,
        validation_criteria=original_criteria,  # Inherited from parent
        parent_task_id=task.id,
        depends_on=[test_task.id],
    )

    refactor_task = create_task(
        title=f"Refactor: {task.title}",
        description=task.description,
        validation_criteria=TDD_CRITERIA_BLUE,  # Templated
        parent_task_id=task.id,
        depends_on=[impl_task.id],
    )

    # Parent becomes container - update its criteria
    task.validation_criteria = PARENT_CRITERIA
    task.is_tdd_applied = True

    return [test_task, impl_task, refactor_task]
```

**File:** `src/gobby/mcp_proxy/tools/task_expansion.py`

**MCP Tool: `apply_tdd`**

```text
Description:
    Transform tasks into TDD triplets (Test->Implement->Refactor).

    Deterministic transformation - no LLM needed.
    Sets is_tdd_applied=True on successful transformation.

    **Skip conditions** (task is not transformed):
    - Category not in ("code", "config") - document/research/manual tasks skip
    - is_tdd_applied=True - already processed
    - Title starts with "Write tests for:", "Implement:", "Refactor:" - already TDD
    - Title contains "delete", "remove", "deprecate", "cleanup" - deletion tasks
    - Title matches "update *.md/yaml/json" pattern - doc/config updates

    Validation criteria:
    - Parent task: Set to "All child tasks completed" (parent is now a container)
    - Red (test): Templated TDD criteria for writing failing tests
    - Green (implement): Inherits parent's original validation_criteria
    - Blue (refactor): Templated TDD criteria for code cleanup

Parameters:
    task_id: str (optional)
        Single task reference (e.g., "#42", "42", UUID)
        Mutually exclusive with task_ids

    task_ids: list[str] (optional)
        Multiple task references for batch parallel execution
        Mutually exclusive with task_id

    force: bool = False
        Apply TDD even if task already has children (dangerous!)

    session_id: str (required)
        Current session ID for context

Returns:
    {
      "success": true,
      "transformed_count": 2,
      "skipped_count": 3,
      "skipped_reasons": {
        "#45": "category is 'document'",
        "#46": "is_tdd_applied=True",
        "#47": "title starts with 'Write tests for:'"
      },
      "results": [
        {
          "original_task_ref": "#42",
          "triplet": [
            {"task_ref": "#48", "title": "Write tests for: User auth"},
            {"task_ref": "#49", "title": "Implement: User auth"},
            {"task_ref": "#50", "title": "Refactor: User auth"}
          ]
        }
      ]
    }

Errors:
    - "task_id or task_ids required" - Neither parameter provided
    - "Cannot specify both task_id and task_ids" - Both provided
    - "Task not found: #42" - Invalid task reference
```

### Phase 7: Restructure parse_spec

**File:** `src/gobby/mcp_proxy/tools/task_expansion.py`

Rename current `expand_from_spec` to `parse_spec` with simplified behavior:

- Parse markdown structure
- Create epic + phases + tasks with smart descriptions
- NO research, NO subtask generation, NO TDD transformation
- Fast and deterministic

```python
@registry.tool(name="parse_spec")
async def parse_spec(
    spec_path: str,
    parent_task_id: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """
    Parse a specification file and create tasks from its structure.

    Creates tasks from headings and checkboxes with smart context extraction.

    Does NOT research or generate subtasks - use enrich_task and expand_task
    for that.
    """
```

Keep `expand_from_spec` as an alias that calls the full workflow:

```python
@registry.tool(name="expand_from_spec")  # Backwards compat
async def expand_from_spec(...):
    """Full workflow: parse -> enrich -> expand -> apply_tdd"""
    result = await parse_spec(...)
    # Then optionally chain other steps based on flags
```

### Phase 8: CLI Improvements

**Files:** `src/gobby/cli/tasks/crud.py`, `src/gobby/cli/tasks/expand.py`, `src/gobby/cli/tasks/utils.py`

#### 8a. Flexible task ref parsing

All CLI commands accepting task refs should support:

- `42` - plain number
- `#42` - hash prefix
- `#42,#43,#44` - comma-separated list
- `42 43 44` - space-separated (shell args)

Add helper function in `src/gobby/cli/tasks/utils.py`:

```python
def parse_task_refs(refs: tuple[str, ...]) -> list[str]:
    """Parse flexible task reference formats into normalized list."""
    result = []
    for ref in refs:
        # Handle comma-separated
        for part in ref.split(","):
            part = part.strip()
            # Normalize: remove # prefix, validate numeric
            if part.startswith("#"):
                part = part[1:]
            if part:
                result.append(part)
    return result
```

#### 8b. CLI Command: `gobby tasks enrich`

```text
$ gobby tasks enrich --help

Usage: gobby tasks enrich [OPTIONS] TASK_REFS...

  Research tasks and store findings for expansion.

  Gathers context from codebase, web, and MCP tools. Categorizes tasks,
  generates validation criteria, and stores findings in expansion_context.

Arguments:
  TASK_REFS...  Task references (e.g., 42, #42, #42,#43,#44)

Options:
  -c, --cascade           Recursively enrich all descendants
  -p, --project TEXT      Project name or ID (auto-detects from cwd)
  --no-code-research      Skip codebase research
  --web-research          Enable web research (disabled by default)
  --mcp-tools TEXT        Comma-separated MCP servers to query
  --no-validation         Skip validation criteria generation
  --force                 Re-enrich even if already enriched
  --timeout TEXT          Timeout duration (default: 10m, e.g., 30m, 1h)
  -v, --verbose           Show detailed progress
  --help                  Show this message and exit.

Examples:
  gobby tasks enrich #42
  gobby tasks enrich #42,#43,#44 --cascade
  gobby tasks enrich 42 43 44 --web-research --mcp-tools context7
```

#### 8c. CLI Command: `gobby tasks expand`

```text
$ gobby tasks expand --help

Usage: gobby tasks expand [OPTIONS] TASK_REFS...

  Expand tasks into subtasks using LLM.

  Uses stored expansion_context from enrich if available.
  Single-level by default; use --cascade for recursive expansion.

Arguments:
  TASK_REFS...  Task references (e.g., 42, #42, #42,#43,#44)

Options:
  -c, --cascade           Recursively expand all descendants
  -p, --project TEXT      Project name or ID (auto-detects from cwd)
  --no-enrich             Don't auto-enrich if context missing
  --force                 Re-expand even if already expanded
  --timeout TEXT          Timeout duration (default: 10m, e.g., 30m, 1h)
  -v, --verbose           Show detailed progress
  --help                  Show this message and exit.

Examples:
  gobby tasks expand #42
  gobby tasks expand #42 --cascade -v
  gobby tasks expand 42,43,44 --force --timeout 30m
```

#### 8d. CLI Command: `gobby tasks apply-tdd`

```text
$ gobby tasks apply-tdd --help

Usage: gobby tasks apply-tdd [OPTIONS] TASK_REFS...

  Transform code/config tasks into TDD triplets.

  Creates Test->Implement->Refactor subtasks for each task with
  category in ('code', 'config'). Deterministic - no LLM needed.

Arguments:
  TASK_REFS...  Task references (e.g., 42, #42, #42,#43,#44)

Options:
  -c, --cascade           Recursively apply to all descendants
  -p, --project TEXT      Project name or ID (auto-detects from cwd)
  --force                 Apply even if task already has children
  -v, --verbose           Show detailed progress
  --help                  Show this message and exit.

Examples:
  gobby tasks apply-tdd #42
  gobby tasks apply-tdd #42 --cascade
  gobby tasks apply-tdd 42,43,44 --force
```

#### 8e. CLI Command: `gobby tasks parse-spec`

```text
$ gobby tasks parse-spec --help

Usage: gobby tasks parse-spec [OPTIONS] SPEC_PATH

  Parse a spec file and create tasks from its structure.

  Creates epic + phases + tasks with smart context extraction.
  Fast and deterministic - no LLM calls.

Arguments:
  SPEC_PATH  Path to markdown spec file

Options:
  -p, --project TEXT      Project name or ID (auto-detects from cwd)
  --parent TEXT           Parent task reference for created tasks
  -v, --verbose           Show created task tree
  --help                  Show this message and exit.

Examples:

  gobby tasks parse-spec docs/plans/memory-v3.md
  gobby tasks parse-spec spec.md --parent #42
  gobby tasks parse-spec spec.md -p my-project -v
```

#### 8f. Add `--project/-p` flag to existing commands

Update `gobby tasks create`, `gobby tasks list`, etc. with:

```python

@click.option("-p", "--project", help="Project name or ID (auto-detects from cwd)")

```

Auto-detection logic:

1. If `--project` provided: look up by name or ID
2. Else check if cwd is under a project path in `projects` table
3. Else create task with `project_id=NULL` (personal task)

#### 8g. Progress bar implementation

For `--cascade` operations:

```python
def run_cascade_operation(task_refs, operation_fn, label):
    """Run operation on task tree with progress bar."""
    tasks = list(walk_tree_bfs(task_refs))

    with click.progressbar(
        tasks,
        label=label,
        item_show_func=lambda t: f"#{t.seq_num}: {t.title[:30]}" if t else ""
    ) as bar:
        for task in bar:
            try:
                operation_fn(task)
            except KeyboardInterrupt:
                click.echo("\nCancelled by user. Progress preserved.")
                break
            except Exception as e:
                click.echo(f"\nError on #{task.seq_num}: {e}")
                if not click.confirm("Continue?"):
                    break
```

Progress bar format: `Expanding [####----] 4/10 #42: Task title truncated...`

### Phase 9: Spec Template & Documentation

#### 9a. Spec Template for Users

**New file:** `docs/templates/spec-template.md`

```markdown
# [Project/Feature Name]

## Overview
Brief description of what this spec covers.

## Architecture
[Optional diagrams, component descriptions]

## Phase 1: [Phase Name]

**Goal**: One sentence describing the outcome.

**Files:**
- `path/to/new/file.py` - Description
- `path/to/modify.py` - What changes

**Tasks:**

- [ ] First task with clear action
- [ ] Second task (depends: #1)
- [ ] Third task (depends: #2)
- [ ] Documentation task (parallel - no deps)

## Phase 2: [Phase Name]

**Tasks:**

- [ ] Task A (depends: Phase 1)
- [ ] Task B (parallel with A)
- [ ] Task C (depends: #5, #6)

---

## Task Mapping

<!-- Updated by parse_spec, maintained by agents -->

| Task # | Checkbox | Status |
| :--- | :--- | :--- |
| #1 | Phase 1: First task | pending |
| #2 | Phase 1: Second task | pending |
| ... | ... | ... |

## Completion Instructions

When completing a task:
1. Make all code changes
2. Commit with task reference: `git commit -m "[#N] description"`
3. Close the task: `gobby tasks close #N --commit-sha <sha>`
4. Update the checkbox above to `[x]`

Never close a task without committing first unless it's a non-code task.
```

#### 9b. Spec Writing Guide

**File:** `.gobby/docs/spec-planning.md` (installed from `src/gobby/install/shared/docs/`)

A template/guide for agents writing specification documents. Agents can reference this
when creating specs that work well with `parse_spec`.

**Future:** May become a `/gobby:spec` skill and part of `architect.yaml` workflow.

```markdown
# Spec Writing Guide

This guide helps you create structured specification documents that can be
parsed into Gobby tasks using `parse_spec`.

## Output Location

Write the spec to: `docs/plans/{feature-name}.md`

## Required Sections

### 1. Title and Overview

```markdown
# [Feature Name]

## Overview
[2-3 sentences: What problem does this solve? Why now?]
```

### 2. Architecture (if applicable)

```markdown
## Architecture

[Component diagram, data flow, or key abstractions]
[Reference existing patterns in the codebase]
```

### 3. Phased Implementation

Break work into phases. Each phase should be independently shippable or testable.

```markdown
## Phase 1: [Phase Name]

**Goal**: [One sentence outcome]

**Files:**
- `path/to/new/file.py` - [What it does]
- `path/to/modify.py` - [What changes]

**Tasks:**
- [ ] First task with clear action verb
- [ ] Second task (depends: #1)
- [ ] Third task (depends: #2)
- [ ] Documentation task (parallel - no deps)
```

### 4. Dependencies

Use explicit dependency notation:

- `(depends: #N)` - blocked by task N
- `(depends: #N, #M)` - blocked by tasks N and M
- `(depends: Phase N)` - blocked by all tasks in Phase N
- `(parallel)` or no annotation - can run alongside others

### 5. Parallel Work Tracks

Group independent work that can happen simultaneously:

```markdown
**Track A: Backend**
- [ ] API endpoint
- [ ] Database layer

**Track B: Frontend (parallel with Track A)**
- [ ] UI component
- [ ] State management
```

### 6. Task Mapping (leave empty)

```markdown
## Task Mapping

<!-- Populated by parse_spec -->
| Task # | Checkbox | Status |
| :--- | :--- | :--- |
```

### 7. Completion Instructions

```markdown
## Completion Instructions

When completing a task:
1. Make all code changes
2. Run tests: `uv run pytest path/to/tests -v`
3. Commit with task reference: `git commit -m "[#N] description"`
4. Close the task: `gobby tasks close #N --commit-sha <sha>`
5. Update the checkbox above to `[x]`

Never close a task without committing first unless it's a non-code task.
```

## Task Granularity Guidelines

Each checkbox should be:

- **Atomic**: Completable in one session (< 2 hours)
- **Testable**: Has clear pass/fail criteria
- **Verb-led**: Starts with action verb (Add, Create, Implement, Update, Remove)
- **Scoped**: References specific files/functions when possible

Good: `- [ ] Add TaskEnricher class to src/gobby/tasks/enrich.py`
B  `- [ ] Implement enrichment` (too vague)

## After Writing Your Spec

1. Review the spec for completeness
2. Run `gobby tasks parse-spec docs/plans/{feature}.md` to create tasks
3. Verify task structure with `gobby tasks list --tree`

```python

#### 9c. Spec Writing Guide

**New file:** `docs/guides/spec-writing.md`

Documentation explaining:
-   Heading levels and their meaning
-   Checkbox format best practices
-   How context flows into task descriptions
-   Dependency notation syntax
-   Parallel work track conventions
-   Task mapping maintenance
-   Example specs

### Phase 10: Cleanup (Final)

**Strangler Fig final phase** - remove deprecated code after new system is validated.

**Auto-decomposition cleanup:**

1.  `.gobby/workflows/lifecycle/session-lifecycle.yaml`
    -   Remove `auto_decompose: false` variable (no longer used)
    -   Keep `tdd_mode: true` OR remove if apply_tdd is explicit-only

2.  `src/gobby/config/tasks.py`
    -   Remove `auto_decompose` from `WorkflowVariablesConfig`
    -   Decide on `tdd_mode` retention

3.  `src/gobby/tasks/auto_decompose.py`
    -   Delete file entirely (no longer used)

4.  `src/gobby/mcp_proxy/tools/tasks.py`
    -   Remove any remaining imports/references to auto_decompose

5.  Clean up any `auto*.yaml` workflow files if they exist

**Stealth mode removal:**

6.  `src/gobby/cli/tasks/main.py`
    -   Remove `stealth_cmd` command (lines 216-274)

7.  `src/gobby/cli/tasks/_utils.py`
    -   Remove stealth mode check in `get_sync_manager()` (lines 53-64)

8.  `src/gobby/sync/tasks.py`
    -   Remove stealth mode comment (line 73)

9.  `src/gobby/config/persistence.py`
    -   Remove stealth references from `MemorySyncConfig`

10. `tests/cli/test_stealth.py`
    -   Delete entire test file

11. `src/gobby/cli/tasks/__init__.py`
    -   Remove stealth mention from docstring

**Deprecated gt- format removal:**

12. `src/gobby/storage/tasks.py`
    -   Remove gt- deprecation error (lines 693-697)

13. `src/gobby/mcp_proxy/tools/tasks.py`
    -   Remove gt- deprecation check (lines 161-165)

**Documentation updates:**

14. `docs/guides/tasks.md`
    -   Update expansion workflow documentation
    -   Document new tools: `parse_spec`, `enrich_task`, `expand_task`, `apply_tdd`
    -   Remove auto-decomposition references

15. `CLAUDE.md`
    -   Update task workflow section
    -   Document new phased approach

16. `GEMINI.md` (if exists)
    -   Update task expansion references

17. `AGENTS.md` (if exists)
    -   Update task expansion references

18. `skills/*.toml` and `SKILL.md` files
    -   Search: `rg -l "expand.*task|task.*expan" skills/ docs/skills/`
    -   Update any task expansion references

**Verification before cleanup:**
-   All tests pass with new workflow
-   Integration test with memory-v3.md succeeds
-   No references to deprecated functions in code/docs

---

## Files to Modify

| File | Changes |
| :--- | :--- |
| `src/gobby/mcp_proxy/tools/tasks.py` | Remove auto-decomposition, require session_id in MCP |
| `src/gobby/mcp_proxy/tools/task_expansion.py` | Restructure tools, add enrich_task, apply_tdd, parse_spec |
| `src/gobby/tasks/spec_parser.py` | Smart context extraction for descriptions |
| `src/gobby/tasks/expansion.py` | Simplify, work with stored context |
| `src/gobby/tasks/prompts/expand.py` | JSON schemas for each phase |
| `src/gobby/config/tasks.py` | Remove/deprecate auto_decompose variable |
| `src/gobby/cli/tasks/crud.py` | Fix output format, add --project flag |
| `src/gobby/cli/tasks/expand.py` | Add expand command with cascade |
| `src/gobby/storage/migrations.py` | Add migration: rename test_strategy->category, add agent_name |
| `src/gobby/storage/tasks.py` | Update Task dataclass: category, agent_name, reference_doc |
| `.gobby/workflows/lifecycle/session-lifecycle.yaml` | Remove deprecated variables (Phase 10) |
| `src/gobby/tasks/auto_decompose.py` | Delete file (Phase 10) |

## New Files

| File | Purpose |
| :--- | :--- |
| `src/gobby/tasks/enrich.py` | Enrichment/research logic |
| `src/gobby/tasks/tdd_transform.py` | Deterministic TDD transformation |
| `src/gobby/cli/tasks/utils.py` | Helper functions (parse_task_refs) |
| `src/gobby/tasks/prompts.py` | Prompt loading utilities |
| `docs/templates/spec-template.md` | Spec template for users |
| `docs/guides/spec-writing.md` | Documentation for spec format |
| `src/gobby/install/shared/docs/spec-planning.md` | Spec writing guide (installed to `.gobby/docs/`) |
| `~/.gobby/prompts/enrich-task.md` | Task enrichment prompt |
| `~/.gobby/prompts/expand-task.md` | Task expansion prompt |
| `~/.gobby/prompts/validate-criteria.md` | Validation criteria prompt |

---

## Verification Plan

### 1. Unit Tests

**New test files:**
- `tests/mcp_proxy/tools/test_parse_spec.py`
- `tests/mcp_proxy/tools/test_enrich_task.py`
- `tests/mcp_proxy/tools/test_apply_tdd.py`
- `tests/tasks/test_tdd_transform.py`
- `tests/tasks/test_enrich.py`
- `tests/cli/test_cli_tasks_expand.py`

**Specific test commands:**
```bash
# Run all task-related tests
uv run pytest tests/mcp_proxy/tools/test_task*.py tests/tasks/ -v

# Run new tool tests specifically
uv run pytest tests/mcp_proxy/tools/test_parse_spec.py -v
uv run pytest tests/mcp_proxy/tools/test_enrich_task.py -v
uv run pytest tests/mcp_proxy/tools/test_apply_tdd.py -v

# Run CLI tests
uv run pytest tests/cli/test_cli_tasks*.py -v
```

### 2. Integration Test with memory-v3.md

**Goal:** Verify the complete workflow from spec parsing to TDD triplet creation.

**Test file:** `tests/integration/test_spec_to_tdd_workflow.py`

**Test steps:**

```python
async def test_full_spec_to_tdd_workflow():
    """
    Integration test: parse spec -> enrich -> expand -> apply TDD.
    Uses docs/plans/memory-v3.md as reference spec.
    """
    # Step 1: Parse spec (no LLM, should be fast)
    result = await parse_spec("docs/plans/memory-v3.md")

    # Verify: Epic created with reference_doc set
    assert result["epic"]["reference_doc"] == "docs/plans/memory-v3.md"

    # Verify: Phase tasks created with parent relationships
    phases = result["phases"]
    assert len(phases) >= 3  # memory-v3.md has multiple phases

    # Verify: Leaf tasks have smart descriptions (not just checkbox text)
    leaf_tasks = [t for t in result["tasks"] if not t.get("children")]
    for task in leaf_tasks:
        assert task["description"] is not None
        assert "Part of:" in task["description"]  # Smart context

    # Step 2: Enrich tasks (LLM call)
    task_ids = [t["task_id"] for t in leaf_tasks[:3]]  # Sample 3
    enrich_result = await enrich_task(task_ids=task_ids)

    # Verify: is_enriched flag set
    for r in enrich_result["results"]:
        task = get_task(r["task_id"])
        assert task.is_enriched == True
        assert task.category in ("code", "document", "research", "config", "test", "manual")
        assert task.expansion_context is not None

    # Step 3: Expand tasks (LLM call)
    expand_result = await expand_task(task_ids=task_ids)

    # Verify: is_expanded flag set, subtasks created
    for r in expand_result["results"]:
        task = get_task(r["task_id"])
        assert task.is_expanded == True
        assert r["subtasks_created"] > 0

    # Step 4: Apply TDD (no LLM, deterministic)
    # Get code tasks from expanded subtasks
    code_tasks = [t for t in get_all_tasks() if t.category == "code"]
    tdd_result = await apply_tdd(task_ids=[t.id for t in code_tasks[:2]])

    # Verify: TDD triplets created with correct structure
    for r in tdd_result["results"]:
        triplet = r["triplet"]
        assert len(triplet) == 3
        assert triplet[0]["title"].startswith("Write tests for:")
        assert triplet[1]["title"].startswith("Implement:")
        assert triplet[2]["title"].startswith("Refactor:")

        # Verify dependencies: test -> impl -> refactor
        test_task = get_task(triplet[0]["task_ref"])
        impl_task = get_task(triplet[1]["task_ref"])
        refactor_task = get_task(triplet[2]["task_ref"])

        assert impl_task.depends_on == [test_task.id]
        assert refactor_task.depends_on == [impl_task.id]
```

**Expected outputs from memory-v3.md:**

- 1 epic task with `reference_doc="docs/plans/memory-v3.md"`
- 4-6 phase tasks (Phase 1: Foundation, Phase 2: Enhanced Search, etc.)
- 15-25 leaf tasks with smart descriptions containing "Part of: ``<phase name>``"
- Each enriched task has `category` assigned (likely mix of "code" and "document")
- Each expanded task has subtasks with `depends_on` relationships
- Each code task transformed into 3 TDD subtasks with blocking dependencies

**CLI verification:**

```bash
# Parse spec
gobby tasks parse-spec docs/plans/memory-v3.md -v

# Expected output:
# Created epic gobby-#100: Memory System V3
#   Created phase gobby-#101: Phase 1 - Foundation
#     Created task gobby-#102: Implement memory schema
#     Created task gobby-#103: Add storage layer
#   Created phase gobby-#104: Phase 2 - Enhanced Search
#     ...

# List tree to verify structure
gobby tasks list --tree --project gobby

# Enrich a task
gobby tasks enrich #102 -v

# Expected output:
# Enriching #102: Implement memory schema
#   Category: code
#   Complexity: 3
#   Found 5 relevant files
#   Generated validation criteria
# Done. Task enriched.

# Expand the enriched task
gobby tasks expand #102 -v

# Expected output:
# Expanding #102: Implement memory schema
#   Created subtask #105: Create Memory dataclass
#   Created subtask #106: Add database migration
#   Created subtask #107: Implement CRUD methods
# Done. Created 3 subtasks.

# Apply TDD
gobby tasks apply-tdd #105,#106,#107

# Expected output:
# Applying TDD to #105: Create Memory dataclass

#   Created: #108 Write tests for: Create Memory dataclass
#   Created: #109 Implement: Create Memory dataclass
#   Created: #110 Refactor: Create Memory dataclass
# ...
# Done. Transformed 3 tasks into 9 TDD subtasks.
```

### 3. Regression Tests

**Existing tests that must pass:**

```bash
# TDD ordering test (critical)
uv run pytest tests/integration/test_tdd_ordering_e2e.py -v

# Task expansion tests
uv run pytest tests/mcp_proxy/tools/test_task_expansion.py -v

# Task dependencies tests
uv run pytest tests/mcp_proxy/tools/test_task_dependencies.py -v

# Full test suite
uv run pytest --tb=short
```

### 4. Performance Tests

```bash
# create_task should be fast (< 100ms, no LLM)
time gobby tasks create "Test task" --type task

# parse_spec should be fast (< 500ms for typical spec, no LLM)
time gobby tasks parse-spec docs/plans/memory-v3.md

# enrich_task involves LLM (expect 5-30s depending on task)
time gobby tasks enrich #42

# expand_task involves LLM (expect 5-30s depending on task)
time gobby tasks expand #42

# apply_tdd should be fast (< 100ms per task, no LLM)
time gobby tasks apply-tdd #42
```

### 5. Deprecated Code Verification (Phase 10)

**Before final cleanup, verify no references remain to deprecated code:**

```bash
# Search for auto_decompose references
rg -l "auto_decompose" --type py --type yaml --type md
# Expected: Only in tests/mocks, deprecation warnings, or migration comments

# Search for detect_multi_step usage
rg -l "detect_multi_step" --type py
# Expected: None after cleanup (file deleted)

# Search for old auto_decompose.py imports
rg "from gobby.tasks.auto_decompose" --type py
rg "from gobby.tasks import auto_decompose" --type py
# Expected: None

# Search for tdd_mode workflow variable (if deprecated)
rg "tdd_mode" --type yaml --type py
# Expected: Only in migration comments or explicit documentation

# Search for test_strategy field (renamed to category)
rg "test_strategy" --type py --type sql
# Expected: Only in migration code

# Search for stealth mode references
rg -l "stealth" --type py --type yaml --type md
rg -l "tasks_stealth" --type py --type json
# Expected: None after cleanup

# Search for old expansion patterns in docs
rg -l "expand_from_spec|expand_task" docs/ skills/
# Expected: Updated to reference new workflow

# Search for deprecated field names in code
rg "\.test_strategy" --type py
# Expected: None (renamed to category)
```

**Files to check manually:**

- `CLAUDE.md` - Update task workflow documentation
- `GEMINI.md` - Update task expansion references (if exists)
- `AGENTS.md` - Update task expansion references (if exists)
- `docs/guides/tasks.md` - Remove auto_decompose mentions, document new workflow
- `docs/architecture/` - Update any architecture docs
- `.gobby/workflows/` - Remove deprecated variables
- `src/gobby/config/` - Remove deprecated config options
- `skills/*.toml` - Update task-related skill definitions
- `docs/skills/SKILL.md` files - Update task expansion documentation

**Cleanup verification script:**

```bash
#!/bin/bash
# scripts/verify_deprecation_cleanup.sh

echo "Checking for deprecated references..."

DEPRECATED_TERMS=(
    "auto_decompose"
    "detect_multi_step"
    "extract_steps"
    "test_strategy"  # should be category now
    "stealth"        # stealth mode removed
    "tasks_stealth"
    "gt-"            # old task ID format
)

ERRORS=0
for term in "${DEPRECATED_TERMS[@]}"; do
    count=$(rg -c "$term" --type py --type yaml 2>/dev/null | wc -l)
    if [ "$count" -gt 0 ]; then
        echo "ERROR: Found $count files with '$term'"
        rg -l "$term" --type py --type yaml
        ERRORS=$((ERRORS + 1))
    fi
done

if [ $ERRORS -eq 0 ]; then
    echo "All deprecated references cleaned up!"
    exit 0
else
    echo "Found $ERRORS deprecated terms still in use"
    exit 1
fi
```
