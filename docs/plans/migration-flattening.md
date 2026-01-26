# Migration Flattening

## Overview

Flatten the existing `migrations.py` and `migrations_legacy.py` into a single, clean baseline schema. This involves capturing the current database state, updating the code to use it as the new ground truth, and removing legacy migration logic.

**Goal**: Establish a new `BASELINE_SCHEMA` in `src/gobby/storage/migrations.py` that reflects the current production state (v67+), and delete `src/gobby/storage/migrations_legacy.py`.

## Constraints

- Must backup existing DB before any code changes to ensure data safety
- Must support both new installs (create fresh DB) and existing DBs (no re-migration)
- Schema dump must be reviewed for correctness before integration
- Version number decision required: keep v67 or reset to v100 for new era

## Phase 1: Preparation

**Goal**: Safely backup database and capture current schema state.

**Tasks:**
- [ ] Create timestamped backup of gobby-hub.db (category: manual)
- [ ] Dump current schema to src/gobby/storage/schema_dump.sql (category: manual)
- [ ] Review schema_dump.sql for correctness (category: manual)

**Backup Command:**
```bash
cp ~/.gobby/gobby-hub.db ~/.gobby/gobby-hub.db.bak.$(date +%s)
```

**Schema Dump Command:**
```bash
sqlite3 ~/.gobby/gobby-hub.db .schema > src/gobby/storage/schema_dump.sql
```

## Phase 2: Code Migration

**Goal**: Update migrations.py with new baseline and remove legacy code.

**Tasks:**
- [ ] Replace BASELINE_SCHEMA constant with dumped schema content (category: code)
- [ ] Update schema_version table initialization to correct version (category: code)
- [ ] Remove imports of migrations_legacy from migrations.py (category: code)
- [ ] Delete src/gobby/storage/migrations_legacy.py (category: code)

**Version Decision:**
- Option A: Keep current version (e.g., 67) - `schema_version` pre-inserted with that value
- Option B: Reset to v100 to distinguish old vs new era

## Phase 3: Verification

**Goal**: Confirm the migration works for both new installs and existing databases.

**Tasks:**
- [ ] Test new install scenario - move DB, start daemon, verify schema (category: manual)
- [ ] Test existing DB scenario - restore DB, start daemon, verify no errors (category: manual)

**New Install Test:**
```bash
mv ~/.gobby/gobby-hub.db ~/.gobby/gobby-hub.db.old
gobby start  # Should create new DB with new baseline
# Verify table structure matches expectation
```

**Existing DB Test:**
```bash
mv ~/.gobby/gobby-hub.db.old ~/.gobby/gobby-hub.db
gobby start  # Should start without re-applying migrations or failing
```

## Phase 4: Automation (Optional)

**Goal**: Create helper script to minimize human error during execution.

**Tasks:**
- [ ] Create scripts/flatten_migrations.sh with backup and dump logic (category: code)

**Script Template:**
```bash
#!/bin/bash
set -e
DB_PATH="$HOME/.gobby/gobby-hub.db"
BACKUP_PATH="$DB_PATH.pre-flatten.bak"
echo "Backing up DB to $BACKUP_PATH..."
cp "$DB_PATH" "$BACKUP_PATH"
echo "Dumping schema..."
echo ".schema" | sqlite3 "$DB_PATH" > src/gobby/storage/schema_dump.sql
echo "Ready to copy schema_dump.sql into migrations.py"
```

## Execution Order

1. Run Phase 1 (Preparation)
2. Run Phase 2 (Code Migration)
3. Run Phase 3 (Verification)
4. Optionally run Phase 4 (Automation) beforehand to streamline

## Task Mapping

<!-- Updated after task creation -->
| Plan Item | Task Ref | Status |
|-----------|----------|--------|
| Create timestamped backup | | |
| Dump current schema | | |
| Review schema_dump.sql | | |
| Replace BASELINE_SCHEMA | | |
| Update schema_version init | | |
| Remove legacy imports | | |
| Delete migrations_legacy.py | | |
| Test new install | | |
| Test existing DB | | |
| Create flatten script | | |
