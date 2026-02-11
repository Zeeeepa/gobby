# Drawbridge Import Enhancement Plan

**Status:** Planned
**Created:** 2026-02-11
**Task:** #8038
**Rationale:** Drawbridge annotations live in `.moat/moat-tasks-detail.json` as flat JSON objects with no dependencies, session linking, or validation. By importing them as gobby tasks, they gain the full task lifecycle: dependency graphs, session tracking, validation gates, and the expand/close workflow. The `/bridge` skill becomes a focused importer rather than a parallel task system.

---

## Overview

The current `/bridge` skill (286 lines) and `drawbridge-workflow.md` (802 lines) implement a standalone task processing system that duplicates gobby's own task management. This plan replaces that with an import flow: read `.moat/` annotations, create gobby tasks, and let the existing task system handle the rest.

**Total scope:**

- **1 file to rewrite** (`bridge.md` ~150 lines replacing 286)
- **1 file to trim** (`drawbridge-workflow.md` ~200 lines replacing 802)
- **0 new source files** (import logic lives entirely in the skill prompt)

---

## Context: Drawbridge Data Model

Each annotation in `moat-tasks-detail.json` is a JSON object:

```json
{
  "id": "d9c69e4d-4d2e-4b74-83c3-c81c8f9de990",
  "title": "Freeform Rectangle Task",
  "comment": "Remove the lines between Workflows and Cron Jobs",
  "selector": "freeform",
  "boundingRect": { "x": 8, "y": 12, "w": 372, "h": 691 },
  "screenshotPath": "./screenshots/moat-1770769416084-swqxu5mqu.png",
  "status": "to do",
  "timestamp": 1770769416104,
  "boundingBox": { "xyxy": {...}, "xywh": {...}, "normalized": {...}, "viewport": {...}, "type": "freeform" }
}
```

Key observations:
- `title` is often generic ("Freeform Rectangle Task") — `comment` carries the real intent
- `status` uses Drawbridge values: `"to do"`, `"doing"`, `"done"`, `"failed"`
- `selector` is either a CSS selector or `"freeform"` for region annotations
- `screenshotPath` is relative to `.moat/` (needs resolution)
- `id` is a UUID assigned by the Chrome extension

---

## Phase 1: Field Mapping

### Drawbridge JSON -> Gobby Task

| Drawbridge Field | Gobby Task Field | Transformation |
| --- | --- | --- |
| `comment` | `title` | First line (truncated to 120 chars) |
| `comment` | `description` | Full multi-line comment, plus metadata block (see below) |
| `id` | label: `drawbridge:{id}` | For deduplication (see Phase 3) |
| `status` | `status` | `"to do"` / `"doing"` -> `"open"`, `"done"` -> skip import |
| `screenshotPath` | appended to `description` | Resolved path: `.moat/screenshots/...` |
| `selector` | appended to `description` | CSS selector context |
| `boundingRect` | appended to `description` | Viewport region context |
| `timestamp` | appended to `description` | Original annotation time |
| (inferred) | `task_type` | `"task"` for all (default) |
| (inferred) | `category` | `"code"` for all (UI implementation) |
| (inferred) | `priority` | `2` (medium) for all; user can override post-import |

### Description Template

```markdown
{full comment text}

---
**Drawbridge annotation**
- Selector: `{selector}`
- Screenshot: `{resolved_screenshot_path}`
- Region: {x},{y} {w}x{h} (viewport: {viewport.width}x{viewport.height})
- Annotated: {ISO timestamp from epoch ms}
```

### Status Mapping

| Drawbridge Status | Import Action |
| --- | --- |
| `"to do"` | Create as `open` gobby task |
| `"doing"` | Create as `open` gobby task (agent will claim when ready) |
| `"done"` | **Skip** — already completed, no import needed |
| `"failed"` | Create as `open` gobby task (retry) |

---

## Phase 2: Import Flow

The import is a prompt-driven workflow executed by the agent when the user runs `/bridge`. No new Python code is required — the agent reads files and calls existing MCP tools.

### Step-by-step

```
1. LOCATE .moat/moat-tasks-detail.json
   ├─ Check: .moat/moat-tasks-detail.json (current dir)
   ├─ Check: moat-tasks-detail.json (legacy location)
   └─ Check: ../.moat/moat-tasks-detail.json (parent dir)
   → Error if not found (show setup instructions)

2. READ + PARSE annotations
   └─ Parse JSON array, filter out status="done"

3. CHECK for existing epic
   └─ list_tasks(label="drawbridge:epic")
   → If found, reuse as parent
   → If not found, create epic (see below)

4. CREATE EPIC (if needed)
   └─ create_task(
        title="Drawbridge UI Annotations",
        task_type="epic",
        labels=["drawbridge:epic"],
        description="Imported from .moat/moat-tasks-detail.json\n\nParent epic for Drawbridge Chrome extension annotations.",
        session_id="#current"
      )

5. DEDUPLICATE (for each annotation)
   └─ list_tasks(label="drawbridge:{annotation.id}")
   → If task exists: skip (already imported)
   → If not: proceed to create

6. CREATE CHILD TASKS (for each new annotation)
   └─ create_task(
        title=first_line(annotation.comment),
        description=format_description(annotation),
        parent_task_id=epic.ref,
        task_type="task",
        category="code",
        labels=["drawbridge:{annotation.id}", "drawbridge"],
        session_id="#current"
      )

7. REPORT results
   └─ Print summary:
      "Imported N new tasks (M skipped as duplicates, K already done)"
      List each created task with #ref
```

### Screenshot Handling

Screenshots are **not** copied or moved. The resolved path (e.g., `.moat/screenshots/moat-1770769416084-swqxu5mqu.png`) is included in the task description. Agents working on the task can read the screenshot directly from that path.

---

## Phase 3: Deduplication

Deduplication uses the `labels` field with a `drawbridge:{uuid}` convention.

### Why labels?

- Labels are queryable via `list_tasks(label="drawbridge:...")` — fast lookup
- No schema changes needed
- Labels survive task updates, renames, and re-parenting
- The `drawbridge:` prefix avoids collision with user labels

### Re-run safety

Running `/bridge` multiple times is safe:

1. **New annotations** (no matching label) -> created
2. **Previously imported** (matching label exists) -> skipped with note
3. **Done annotations** (status="done") -> skipped at parse time
4. **Deleted gobby tasks** (label gone) -> re-imported as new task

### Label convention

| Label | Purpose |
| --- | --- |
| `drawbridge:epic` | Identifies the parent epic (one per project) |
| `drawbridge:{uuid}` | Links gobby task to Drawbridge annotation ID |
| `drawbridge` | Generic tag for filtering all imported tasks |

---

## Phase 4: Changes to bridge.md

**Current:** 286 lines covering MCP setup, file-based fallback, task processing with status lifecycle, three processing modes (step/batch/yolo), error handling.

**New:** ~150 lines focused on import-only. The skill becomes a thin importer that delegates all task management to gobby.

### New structure

```
# Drawbridge Import

## Locate .moat/ data
- Search priority (3 locations)
- Error handling if not found

## Read annotations
- Parse moat-tasks-detail.json
- Filter out done tasks
- Resolve screenshot paths

## Import to gobby
- Find or create parent epic (drawbridge:epic label)
- For each annotation:
  - Check dedup via drawbridge:{id} label
  - Create task with field mapping
- Report summary

## Post-import
- Remind user: use /gobby tasks to manage imported tasks
- Suggest: /gobby expand on complex tasks
- Note: screenshots available at resolved .moat/ paths
```

### What's removed

- MCP connection check/setup (Phase 1 of current skill — Drawbridge MCP server no longer needed)
- Processing modes (step/batch/yolo) — gobby's task system handles execution
- Status lifecycle management (to do -> doing -> done in JSON) — gobby tracks status
- File-based task processing — replaced by gobby task claims and closes
- moat-tasks.md checkbox updates — gobby is the source of truth

### What's kept

- `.moat/` directory detection and error messages
- Screenshot path resolution logic
- Setup instructions for the Chrome extension (in error handling)

---

## Phase 5: Changes to drawbridge-workflow.md

**Current:** 802 lines as an `alwaysApply: true` workflow covering task ingestion, status lifecycle, three processing modes, batching logic, framework detection, UI pattern library, and implementation standards.

**New:** ~200 lines retaining only the implementation standards that apply when an agent is working on a Drawbridge-originated task. The workflow stops being `alwaysApply` and instead activates when the agent claims a task with a `drawbridge` label.

### What's kept (trimmed)

- Implementation standards (design tokens, rem units, modern CSS)
- Screenshot path resolution
- Framework detection & adaptation patterns
- UI change pattern library (colors, layout, typography, effects)
- Accessibility guidelines

### What's removed

- Status lifecycle management (to do -> doing -> done)
- Task ingestion from JSON (now handled by import)
- Processing modes (step/batch/yolo)
- Batching logic and grouping criteria
- Concurrent file update handling
- moat-tasks.md/moat-tasks-detail.json file management
- Standard task announcement template
- Dependency detection (gobby handles dependencies)
- Communication style guidelines (verbose/terse) — handled by gobby workflows

### Frontmatter change

```yaml
# Before
alwaysApply: true

# After
alwaysApply: false
globs:
  - ".moat/**"
```

The workflow content becomes a reference that agents consult when implementing UI changes from Drawbridge annotations, not an always-injected prompt.

---

## Phase 6: Verification

### Manual test steps

1. **Fresh import:**
   - Ensure `.moat/moat-tasks-detail.json` exists with mix of "to do" and "done" tasks
   - Run `/bridge`
   - Verify: epic created with `drawbridge:epic` label
   - Verify: only non-done tasks imported as children
   - Verify: each task has `drawbridge:{uuid}` label
   - Verify: task descriptions include screenshot paths and selector info

2. **Re-run (idempotent):**
   - Run `/bridge` again without changes
   - Verify: all tasks skipped as duplicates
   - Verify: no new epic created
   - Verify: summary shows "0 new, N skipped"

3. **New annotations added:**
   - Add a new entry to `moat-tasks-detail.json`
   - Run `/bridge`
   - Verify: only the new annotation imported
   - Verify: existing tasks untouched

4. **No .moat/ directory:**
   - Run `/bridge` from a directory without `.moat/`
   - Verify: helpful error with Chrome extension setup instructions

5. **Task workflow integration:**
   - Claim an imported task via gobby
   - Verify: screenshot path in description is readable
   - Close the task with a commit
   - Verify: standard gobby close flow works

---

## File Summary

| File | Action | Lines Before | Lines After |
| --- | --- | --- | --- |
| `docs/plans/drawbridge-enhancements.md` | Create | 0 | ~220 |
| `.claude/commands/bridge.md` | Rewrite | 286 | ~150 |
| `.moat/drawbridge-workflow.md` | Trim | 802 | ~200 |
| `drawbridge/.claude/commands/bridge.md` | Rewrite (mirror) | 292 | ~150 |
| `drawbridge/.moat/drawbridge-workflow.md` | Trim (mirror) | 802 | ~200 |

**No new Python source files.** The import logic is entirely prompt-driven, using existing gobby MCP tools (`create_task`, `list_tasks`, `add_label`).

---

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| Large annotation sets (50+) hit MCP rate limits | Import sequentially with brief pauses; report progress |
| Generic titles ("Freeform Rectangle Task") reduce task readability | Use `comment` first line as title; full comment in description |
| Screenshot paths break if `.moat/` moves | Paths are relative to project root; document this in description |
| Users expect `/bridge` to still process tasks directly | Clear messaging: "Tasks imported — use `/gobby tasks` to manage" |
| `alwaysApply: false` means agents miss implementation standards | Add note in imported task descriptions pointing to drawbridge-workflow.md |

---

## Out of Scope

- **Drawbridge MCP server** — no longer needed for import; may be deprecated separately
- **Bidirectional sync** (gobby -> .moat/) — one-way import only; Drawbridge JSON is read-only input
- **Automatic re-import on file change** — manual `/bridge` invocation required
- **Screenshot embedding** — paths are referenced, not copied into gobby storage
- **Task expansion** — users can run `/gobby expand` post-import for complex tasks
