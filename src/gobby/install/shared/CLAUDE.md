# Template Library

Everything in this directory is a **template**, not active enforcement.

- Templates are bundled with Gobby and synced to the `workflow_definitions` DB table by
  the sync modules (`sync_rules.py`, `sync_pipelines.py`, etc.)
- Templates have `enabled: true` by default — the template's `enabled` value is used
  directly when creating the installed DB row on first sync
- Existing DB rows are never overwritten by sync — drift is detected via hash comparison
- The `deprecated/` subdirectories are excluded from sync entirely
- The database is the source of truth for what's active, not these YAML files
