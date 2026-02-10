# Gobby Projects V2 - CLI Commands

> Extends project management with rename, delete, update, and repair commands.

## Decisions

- **Delete behavior:** Orphan data to `_orphaned` project (not cascade)
- **Rename:** Auto-update `.gobby/project.json` if accessible
- **Ref format:** Name, UUID, or UUID prefix (like other gobby entities)
- **MCP:** No agent tools - keep project manipulation CLI-only
- **Delete safeguard:** Require `--confirm=<project-name>` to delete
- **Dev safeguard:** Hardcode block on rename/delete for project named "gobby"

## Current State

**CLI exists** (`src/gobby/cli/projects.py`):
- `gobby projects list`
- `gobby projects show <ref>`

**Storage:** `LocalProjectManager` has full CRUD but only create/list/get exposed

## New CLI Commands

```bash
gobby projects rename <old-name> <new-name>  # Rename gobby project name
gobby projects delete <ref> --confirm=<name> # Delete (orphans data, requires name confirmation)
gobby projects update <ref> [--repo-path PATH] [--github-url URL]
gobby projects repair                        # Fix stale repo_path from cwd
```

**Delete safeguard example:**
```bash
gobby projects delete gobby --confirm=gobby  # Must type name to confirm
gobby projects delete gobby                  # Error: "--confirm=gobby" required
```

## Files to Modify

| File | Changes |
|------|---------|
| `src/gobby/cli/projects.py` | Add rename, delete, update, repair |
| `src/gobby/utils/project_init.py` | Add `update_project_json()` |
| `src/gobby/storage/projects.py` | Add `resolve_ref()`, `orphan_data()` |

## Edge Cases

| Scenario | What happens |
|----------|-------------|
| GitHub renamed, dir unchanged | Use `update --github-url` |
| Dir renamed, GitHub unchanged | Use `repair` (detects from cwd) or `update --repo-path` |
| Both renamed | Use `rename` + `update` or just `repair` from new dir |
| `repo_path` stale | `repair` detects and offers fix |

## Implementation Details

### Dev Safeguard

Applied in both rename and delete commands:

```python
PROTECTED_PROJECTS = {"gobby"}  # Cannot rename or delete

if project.name in PROTECTED_PROJECTS:
    raise click.ClickException(f"Cannot modify protected project '{project.name}'")
```

### Rename Flow

1. Resolve old_name to project
2. **Check not protected**
3. Check new_name not taken
4. `project_manager.update(id, name=new_name)`
5. If `repo_path` accessible: update `.gobby/project.json`
6. Warn: "Commits with [old-name-#N] won't auto-link"

### Delete Flow

1. Resolve ref to project
2. **Check not protected**
3. Require `--confirm=<name>`
4. Update all tasks/sessions: `project_id = _orphaned.id`
5. Delete project from DB

### Repair Flow

1. Read `.gobby/project.json` from cwd
2. Get project by name from DB
3. If `repo_path` differs: offer to update

## Verification

```bash
gobby projects list
gobby projects rename myapp new-app
gobby projects update new-app --github-url https://github.com/me/new-app
gobby projects repair  # from renamed directory
gobby projects delete old-proj --confirm=old-proj
```
