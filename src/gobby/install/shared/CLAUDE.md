# Template Library

Everything in this directory is a **template**, not active enforcement.

- Templates are bundled with Gobby and synced to the `workflow_definitions` DB table by
  `src/gobby/workflows/sync.py`
- All templates have `enabled: false` by design — this is intentional, not a bug
- A rule/pipeline/agent must be **installed AND enabled** in the database to be active
- The `deprecated/` subdirectories are excluded from sync entirely
- The database is the source of truth for what's active, not these YAML files
- DO NOT treat disabled templates as "the enforcement system is inert" — check the DB
