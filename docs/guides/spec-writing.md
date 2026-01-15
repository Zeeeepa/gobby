# Writing Specification Documents

Gobby can parse structured specification documents into tasks. This guide explains how to write specs that work well with the task system.

## Quick Start

```bash
# Parse a spec into tasks
gobby tasks parse-spec docs/plans/feature.md

# Or import via AI expansion
gobby tasks import-spec docs/plans/feature.md --type prd
```

## Document Structure

### Heading Hierarchy

Headings create task hierarchy:

| Heading Level | Task Structure |
|---------------|----------------|
| `# Title` | Epic (root task) |
| `## Phase N` | Phase grouping |
| `### Section` | Subtask group |

### Checkbox Format

Tasks are parsed from checkboxes:

```markdown
- [ ] Unchecked = open task
- [x] Checked = completed (skipped during parse)
```

Each checkbox becomes a task. The text after the checkbox becomes the task title.

**Good task titles:**
- Start with action verb (Add, Create, Implement, Update, Remove)
- Reference specific files when possible
- Be completable in one session

```markdown
## Phase 1: Foundation

- [ ] Add TaskEnricher class to src/gobby/tasks/enrich.py
- [ ] Create database migration for category field
- [ ] Update CLAUDE.md with new task workflow
```

### Dependency Notation

Specify dependencies inline:

| Notation | Meaning |
|----------|---------|
| `(depends: #1)` | Blocked by task 1 |
| `(depends: #1, #2)` | Blocked by tasks 1 and 2 |
| `(depends: Phase 1)` | Blocked by entire phase |
| No annotation | Can run in parallel |

```markdown
- [ ] Create JWT utility module
- [ ] Add auth middleware (depends: #1)
- [ ] Create login endpoint (depends: #1)
- [ ] Add integration tests (depends: #2, #3)
```

Task numbers refer to sequential order in the spec. After parsing, these become actual task references.

## Recommended Structure

```markdown
---
title: 'Feature Name'
status: 'draft'
---

# Feature Name

## Overview

Brief description of what this feature does.

## Architecture

How it fits into the system.

## Phase 1: Foundation

**Goal**: One sentence outcome.

**Files:**
- `path/to/file.py` - What it does

**Tasks:**
- [ ] First task
- [ ] Second task (depends: #1)

**Acceptance Criteria:**
- [ ] Measurable outcome

## Phase 2: Enhancement

...

## Task Mapping

| Task # | Checkbox | Status |
|--------|----------|--------|

## Completion Instructions

When completing a task:
1. Make code changes
2. Run tests
3. Commit with task reference: `git commit -m "[#N] description"`
4. Close task: `gobby tasks close #N --commit-sha <sha>`
```

## Parallel Work Tracks

Group independent work that can happen simultaneously:

```markdown
**Track A: Backend**
- [ ] API endpoint
- [ ] Database layer

**Track B: Frontend (parallel with Track A)**
- [ ] UI component
- [ ] State management
```

## After Writing Your Spec

1. **Parse into tasks**: `gobby tasks parse-spec docs/plans/feature.md`
2. **Verify structure**: `gobby tasks list --tree`
3. **Enrich with AI**: `gobby tasks enrich #N --cascade`
4. **Expand complex tasks**: `gobby tasks expand #N`
5. **Apply TDD**: `gobby tasks apply-tdd #N --cascade`

## Best Practices

### Task Granularity

Each task should be:
- **Atomic**: Completable in one session (< 2 hours)
- **Testable**: Has clear pass/fail criteria
- **Scoped**: References specific files/functions

### Spec Location

Write specs to: `docs/plans/{feature-name}.md`

### Spec Status Tracking

Use frontmatter to track progress:

```yaml
---
status: 'draft'  # draft, in-progress, complete
stepsCompleted: ['Phase 1']
---
```

## See Also

- [Task Management Guide](./tasks.md) - Full task system documentation
- [MCP Tools Reference](./mcp-tools.md) - Tool API documentation
- `.gobby/docs/spec-planning.md` - Detailed spec template (installed per-project)
