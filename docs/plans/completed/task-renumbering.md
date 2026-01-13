# Task ID Redesign Spec

## Problem Statement

Current task IDs (`gt-abc123`) are:
- Hard to type (6 random hex chars)
- Hard to remember
- Don't convey hierarchy
- Short enough to risk collisions at scale

## Proposed Solution

Three-tier identification system:

| Purpose | Format | Example |
|---------|--------|---------|
| Internal ID (DB) | Raw UUID | `550e8400-e29b-41d4-a716-446655440000` |
| Human reference | `#N` | `#47` |
| Hierarchy display | Dotted path | `1.3.47` |

## Schema Changes

### New Columns

```sql
ALTER TABLE tasks ADD COLUMN seq_num INTEGER;
ALTER TABLE tasks ADD COLUMN path_cache TEXT;

CREATE UNIQUE INDEX idx_tasks_seq_num ON tasks(project_id, seq_num);
CREATE INDEX idx_tasks_path ON tasks(path_cache);
```

### Column Definitions

| Column | Type | Purpose |
|--------|------|---------|
| `id` | TEXT (UUID) | Primary key, full UUID |
| `seq_num` | INTEGER | Project-scoped sequential number (1, 2, 3...) |
| `path_cache` | TEXT | Computed hierarchy path ("1.3.47") |

### Path Computation (Recursive CTE)

```sql
WITH RECURSIVE task_path AS (
  SELECT id, seq_num, parent_task_id,
         CAST(seq_num AS TEXT) as path,
         0 as depth
  FROM tasks
  WHERE parent_task_id IS NULL AND project_id = ?

  UNION ALL

  SELECT t.id, t.seq_num, t.parent_task_id,
         tp.path || '.' || t.seq_num,
         tp.depth + 1
  FROM tasks t
  JOIN task_path tp ON t.parent_task_id = tp.id
)
SELECT id, path, depth FROM task_path;
```

## Migration Strategy

The existing `run_migrations()` is called on the database at startup (`runner.py:275-276`).

### Phase 1: Add New Columns + Convert IDs

1. Add `seq_num`, `path_cache` columns
2. Convert existing `gt-*` IDs to full UUIDs
3. Update all foreign key references (parent_task_id, task_dependencies, etc.)
4. Backfill `seq_num` with sequential numbers per project
5. Compute and cache `path_cache` for all tasks

### Phase 2: Update ID Generation

1. New tasks get UUID as `id`
2. New tasks get next `seq_num` (auto-increment per project)
3. Path cache updated on insert/reparent

### Phase 3: Update References

1. Update CLI to accept `#N` format
2. Update MCP tools to resolve `#N` → UUID
3. Update commit patterns to recognize `#N` format
4. Remove `gt-*` pattern support (clean break, no legacy users)

## Files to Modify

### Database & Storage

| File | Changes |
|------|---------|
| `src/gobby/storage/migrations.py` | New migration for columns |
| `src/gobby/storage/tasks.py` | Update `generate_task_id()` to use UUID, add `get_next_seq_num()`, add path cache logic |

### ID Resolution

| File | Changes |
|------|---------|
| `src/gobby/storage/tasks.py` | Update `find_task_by_prefix()` to resolve `#N` format |
| `src/gobby/cli/tasks/_utils.py` | Update `resolve_task_id()` for `#N` support |

### Commit Parsing

| File | Changes |
|------|---------|
| `src/gobby/tasks/commits.py` | Add `#N` patterns to `TASK_ID_PATTERNS`, update `extract_task_ids_from_message()` |

### Display

| File | Changes |
|------|---------|
| `src/gobby/storage/tasks.py` | Update `to_brief()` and `to_dict()` to include `seq_num` and `path_cache` |
| `src/gobby/cli/tasks/_utils.py` | Update `format_task_row()` to show `#N` + path; add project column support |
| `src/gobby/cli/tasks/crud.py` | Add `--all-projects` flag; update column headers |

### Sync Format

| File | Changes |
|------|---------|
| `src/gobby/sync/tasks.py` | Add `seq_num` and `path_cache` to JSONL export |

### MCP Tools

| File | Changes |
|------|---------|
| `src/gobby/mcp_proxy/tools/task_*.py` | Update all task_id parameters to accept `#N` format |

## Reference Resolution Logic

```python
def resolve_task_reference(ref: str, project_id: str) -> str | None:
    """Resolve a task reference to UUID.

    Accepts:
      - #47 → lookup by seq_num
      - project#47 → cross-project lookup
      - 1.3.47 → lookup by path_cache
      - full-uuid → direct lookup
    """
    # Cross-project: gobby#47
    if "#" in ref and not ref.startswith("#"):
        project_name, seq = ref.split("#", 1)
        proj_id = lookup_project_by_name(project_name)
        return lookup_by_seq(proj_id, int(seq))

    # Local project: #47
    if ref.startswith("#"):
        seq = int(ref[1:])
        return db.fetchone(
            "SELECT id FROM tasks WHERE project_id = ? AND seq_num = ?",
            (project_id, seq)
        )["id"]

    # Path: 1.3.47
    if "." in ref and ref.replace(".", "").isdigit():
        return db.fetchone(
            "SELECT id FROM tasks WHERE project_id = ? AND path_cache = ?",
            (project_id, ref)
        )["id"]

    # Assume UUID
    return ref
```

## Commit Message Patterns

```python
TASK_ID_PATTERNS = [
    r"\[#(\d+)\]",              # [#47] - bracket format (recommended)
    r"#(\d+)\b",                # #47 - inline reference
    r"(?:implements|fixes|closes)\s+#(\d+)",  # Fixes #47
]
```

Examples:
- `[#47] feat: add login form` (recommended)
- `Fix validation bug #47`
- `Closes #47, #48`

## Display Format

### CLI List Output (Single Project)

Before:
```
[STATUS] [PRIORITY] [ID]       TITLE
○        🟡         gt-abc123  ├── Parent Task
●        🔴         gt-def456  │   └── Child Task
```

After:
```
[STATUS] [PRIORITY] [#]   [PATH]    TITLE
○        🟡         #12   1.2       ├── Parent Task
●        🔴         #47   1.2.47    │   └── Child Task
```

### CLI List Output (Multi-Project)

When `--all-projects` flag is used:
```
[STATUS] [PRIORITY] [PROJECT]  [#]   [PATH]    TITLE
○        🟡         gobby      #12   1.2       ├── Parent Task
●        🔴         gobby      #47   1.2.47    │   └── Child Task
○        🔵         other-proj #3    1         Some Task
```

### Cross-Project References

Format: `project#N` (e.g., `gobby#47`)

```python
def resolve_task_reference(ref: str, default_project_id: str) -> str | None:
    # Cross-project: gobby#47
    if "#" in ref and not ref.startswith("#"):
        project_name, seq = ref.split("#", 1)
        project_id = lookup_project_by_name(project_name)
        return lookup_by_seq(project_id, int(seq))

    # Local project: #47
    if ref.startswith("#"):
        return lookup_by_seq(default_project_id, int(ref[1:]))
    # ... legacy and UUID handling
```

## Depth Handling

- Storage: Unlimited depth (recursive CTE)
- Display: Show full path or truncate with `...` for deep nesting
- `seq_num` is flat (no hierarchy in the number itself)
- `path_cache` shows full hierarchy

Example deep nesting:
```
#47 → path: 1.2.3.4.5.47
Display options:
  - Full: 1.2.3.4.5.47
  - Truncated: 1...5.47
  - Depth indicator: #47 (d6)
```

## Backwards Compatibility

**Clean break** - no legacy users, so no `gt-*` support needed.

| Reference Type | Status |
|----------------|--------|
| `#N` in commit messages | Primary format |
| `#N` in CLI | Primary format |
| `project#N` | Cross-project reference |
| `1.2.3` path | Supported |
| UUID | Always supported (internal/API) |
| `gt-*` | **Removed** |

## Design Decisions

1. **seq_num gaps**: Leave gaps after deletion (stable references)
2. **Path cache invalidation**: Immediate cascade on reparent
3. **CLI display**: Show `#N` + path columns (supports multi-project views)
4. **Cross-project references**: `project#N` format (e.g., `gobby#47`)

## Verification Plan

1. Create migration, run on test database
2. Verify backfill populates seq_num and path_cache correctly
3. Verify existing `gt-*` IDs converted to UUIDs
4. Test `#N` resolution in CLI commands
5. Test `project#N` cross-project resolution
6. Test commit parsing with new `#N` patterns
7. Run full test suite
8. Manual test: create task, reference by `#N`, close with commit `[#N]`

## Implementation Order

1. Migration: Add columns, convert IDs to UUID, backfill seq_num/path
2. Storage: Update Task model, `generate_task_id()` → UUID, add `get_next_seq_num()`
3. Resolution: Add `resolve_task_reference()` helper
4. CLI: Update display (`#N` + path), input parsing, add `--all-projects`
5. Commits: Replace patterns with `#N` format
6. MCP tools: Update parameter handling to use resolver
7. Sync: Update JSONL format
8. Tests: Update fixtures, remove `gt-*` references, add new tests
