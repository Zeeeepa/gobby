---
name: source-control
description: Commit message format, task close workflow, and release PR process. Use when ready to commit, closing tasks, or pushing a release.
category: core
triggers: commit, git commit, commit changes, close task, close, release, push release, create pr, pull request
metadata:
  gobby:
    audience: all
    format_overrides:
      autonomous: full
---

# Source Control - Commits, Closes, and Releases

This skill covers commit message format, task close workflow, and the release PR process.

---

## Part 1: Commit and Close Workflow

### Step 1: Stage Changes

```bash
git add <specific-files>
```

Prefer staging specific files over `git add -A`.

### Step 2: Commit with Task ID

```bash
git commit -m "[project-#N] type: description"
```

Use the `project-#N` format (e.g., `[gobby-#123]`) — the hyphen before `#` is required.

### Step 3: Close the Task

**If your agent instructions specify a different post-commit procedure** (e.g., `mark_task_needs_review` instead of `close_task`), **follow your agent instructions** — they take priority over this skill.

Otherwise, for standard sessions:

```python
call_tool("gobby-tasks", "close_task", {
    "task_id": "<task-id>",
    "commit_sha": "<commit-sha>"
})
```

## Commit Message Format

```
[<project>-#<N>] <type>: <description>

<optional body>
```

### Valid Commit Types

| Type | Use For |
|------|---------|
| `feat` | New feature |
| `fix` | Bug fix |
| `refactor` | Code restructuring |
| `test` | Adding tests |
| `docs` | Documentation |
| `chore` | Maintenance |

### Examples

```
[gobby-#123] feat: add user authentication
[gobby-#789] fix: resolve password reset bug
[gobby-#456] refactor: extract auth logic to service
[gobby-#12] test: add unit tests for auth module
```

## Closing Without Commits

For tasks that don't require code changes (research, planning, obsolete tasks):

```python
call_tool("gobby-tasks", "close_task", {
    "task_id": "<task-id>",
    "reason": "obsolete"  # or "already_implemented", "duplicate", "wont_fix", "out_of_repo"
})
```

## Common Mistakes

### Wrong: Close Before Commit

```python
# This will fail — no commit_sha
call_tool("gobby-tasks", "close_task", {"task_id": "abc"})
```

### Right: Commit First, Then Close

```bash
git commit -m "[gobby-#42] feat: implement feature"
```

```python
call_tool("gobby-tasks", "close_task", {
    "task_id": "#42",
    "commit_sha": "a1b2c3d"
})
```

## Task Lifecycle

```
open → in_progress → review → closed
```

Tasks may enter `review` status instead of `closed` when:
- Task has `requires_user_review=true`
- Validation criteria fail

User must explicitly close reviewed tasks.

---

## Part 2: Release PR Workflow

When you're ready to cut a release from a working branch (e.g., `0.3.1`):

### Step 1: Version Bump

Update all version files on the working branch:

1. `pyproject.toml` — `version` field
2. `src/gobby/__init__.py` — `__version__` variable
3. `CHANGELOG.md` — add new `[version]` section
4. Run `uv sync` to update `uv.lock`

Commit: `[gobby-#N] chore: bump version to X.Y.Z`

### Step 2: Push and Create PR

```bash
git push origin <branch>
gh pr create --base main --head <branch> --title "Release vX.Y.Z"
```

This triggers the `claude-code-review.yml` workflow — Claude reviews the PR automatically.

### Step 3: Address Review Feedback

Fix anything flagged by the Claude review, push updates. The review re-runs on `synchronize`.

### Step 4: Merge and Tag

```bash
# Merge the PR (via GitHub UI or CLI)
gh pr merge <number> --merge

# Tag from main
git checkout main && git pull
git tag vX.Y.Z
git push origin vX.Y.Z
```

The `v*` tag triggers the release workflow: test → build → PyPI publish → GitHub Release.

### Step 5: Start Next Version

```bash
git checkout -b X.Y.(Z+1)
# Bump version files to next patch
# Commit and push
```

### Release Checklist

- [ ] Version files updated (pyproject.toml, __init__.py, CHANGELOG.md, uv.lock)
- [ ] PR created to `main`
- [ ] Claude review passed
- [ ] PR merged
- [ ] Tag pushed (`vX.Y.Z`)
- [ ] Release workflow completed (check GitHub Actions)
- [ ] Next version branch created and bumped
