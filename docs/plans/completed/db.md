# Dual-Write Database Architecture

## Overview

Implement dual-write to both project-local and global databases:
- `.gobby/gobby.db` - Project-local, portable with repo
- `~/.gobby/gobby-hub.db` - Global hub, cross-project view

## Goals

1. Project isolation - each project has its own database
2. Portability - project db travels with the repo
3. Global view - cross-project queries via hub database
4. Resilience - project works even if hub fails

## Implementation Steps

### 1. Disable WAL mode
**File:** `src/gobby/storage/database.py`

Remove WAL (Write-Ahead Logging) and use default DELETE journal mode for better reliability.

### 2. Create DualWriteDatabase class
**File:** `src/gobby/storage/dual_write.py` (new)

- Wrap two `LocalDatabase` instances (project + hub)
- Write operations go to both (project-local first, hub second)
- Read operations go to project-local only
- Hub write failures are logged but non-fatal
- Expose same interface as `LocalDatabase`

### 3. Add hub_database_path config
**File:** `src/gobby/config/app.py`

Add configuration option for hub database path (default: `~/.gobby/gobby-hub.db`).

### 4. Update daemon initialization
**File:** `src/gobby/runner.py`

- Detect project context (`.gobby/project.json` presence)
- If in project: create `DualWriteDatabase(project_db, hub_db)`
- If no project: use hub_db only (single write)
- Run migrations on both databases
- Pass wrapper to all managers

### 5. Update CLI storage init
**File:** `src/gobby/cli/utils.py`

Same pattern as runner - detect project, dual-write if appropriate.

### 6. Add db sync CLI command
**File:** `src/gobby/cli/db.py` (new)

Add `gobby db sync` command with `--direction` option:
- `to-hub`: Copy project records to hub (default)
- `from-hub`: Import hub records for this project into local

Useful for fresh clones to restore project data from hub.

### 7. Add hub query MCP tools
**File:** `src/gobby/mcp_proxy/tools/hub.py` (new)

Tools for cross-project queries:
- `list_all_projects()` - List all projects in hub
- `list_cross_project_tasks(status?)` - Tasks across all projects
- `list_cross_project_sessions(limit?)` - Recent sessions across projects
- `hub_stats()` - Aggregate stats from hub

## Files to Create/Modify

| File | Change |
|------|--------|
| `src/gobby/storage/database.py` | Remove WAL mode |
| `src/gobby/storage/dual_write.py` | **NEW** - DualWriteDatabase class |
| `src/gobby/config/app.py` | Add hub_database_path |
| `src/gobby/runner.py` | Initialize dual-write |
| `src/gobby/cli/utils.py` | CLI dual-write init |
| `src/gobby/cli/db.py` | **NEW** - db sync command |
| `src/gobby/mcp_proxy/tools/hub.py` | **NEW** - Hub query tools |

## Edge Cases

1. **No project context** - Use hub_db only (backwards compatible)
2. **Hub write fails** - Log warning, continue (project is source of truth)
3. **First run in project** - Create .gobby/gobby.db, run migrations
4. **Project db doesn't exist** - Create it
5. **Hub db doesn't exist** - Create it

## Tasks

### Task 1: Disable WAL mode in LocalDatabase
Remove PRAGMA journal_mode = WAL from database.py line 62. Use default DELETE mode.
**File:** `src/gobby/storage/database.py`

### Task 2: Create DualWriteDatabase class
New file with wrapper that proxies writes to two LocalDatabase instances.
**File:** `src/gobby/storage/dual_write.py`

### Task 3: Add hub_database_path to DaemonConfig
Add Field with default `~/.gobby/gobby-hub.db`.
**File:** `src/gobby/config/app.py`

### Task 4: Update daemon to use dual-write
Detect project context, create DualWriteDatabase if in project, run migrations on both.
**File:** `src/gobby/runner.py`

### Task 5: Update CLI utils for dual-write
Same pattern as runner for CLI commands that need database access.
**File:** `src/gobby/cli/utils.py`

### Task 6: Add gobby db sync CLI command
New command with --direction (to-hub, from-hub) for syncing between databases.
**File:** `src/gobby/cli/db.py`

### Task 7: Add hub query MCP tools
list_all_projects, list_cross_project_tasks, list_cross_project_sessions, hub_stats.
**File:** `src/gobby/mcp_proxy/tools/hub.py`

### Task 8: Integration testing
Verify dual-write works end-to-end, test sync command, test hub tools.

## Verification

1. Start daemon in a project directory
2. Create a task - verify it exists in both `.gobby/gobby.db` and `~/.gobby/gobby-hub.db`
3. Query tasks via MCP - should return project tasks
4. Stop daemon, delete hub db, restart - project tasks still work
5. Test `gobby db sync` in both directions
6. Test hub query tools return cross-project data
