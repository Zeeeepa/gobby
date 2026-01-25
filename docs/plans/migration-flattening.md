# Migration Flattening Plan

This plan outlines the process to flatten the existing `migrations.py` and `migrations_legacy.py` into a single, clean baseline schema. This involves capturing the current database state, updating the code to use it as the new ground truth, and removing legacy migration logic.

## Goal
Establish a new `BASELINE_SCHEMA` in `src/gobby/storage/migrations.py` that reflects the current production state (v67+), and delete `src/gobby/storage/migrations_legacy.py`.

## 1. Safety: Backup and Snapshot
Before any code changes, we must ensure data safety.
*   **Backup Command**:
    ```bash
    cp ~/.gobby/gobby-hub.db ~/.gobby/gobby-hub.db.bak.$(date +%s)
    ```
*   **Data Export** (Optional but recommended):
    Use `sqlite3` to dump data if we plan to rebuild the DB file entirely, although the goal here is primarily *code* flattening. If the user wants to "import from backup snapshot", we might need a script to re-populate a fresh DB if we choose to delete the old file.
    *   *Plan*: We will assume the physical DB file stays valid if the schema matches, but providing a "dump and restore" script is a good contingency.

## 2. Capture Current Schema
We need the exact DDL of the current database to replace the hardcoded strings in `migrations.py`.
*   **Command**: `sqlite3 ~/.gobby/gobby-hub.db .schema > current_schema.sql`
*   **Action**: Review `current_schema.sql` to ensure it is clean and correct.

## 3. Code Actions

### A. Update `src/gobby/storage/migrations.py`
1.  **Replace `BASELINE_SCHEMA`**: Paste the content of `current_schema.sql` into the `BASELINE_SCHEMA` constant.
2.  **Reset Versioning**:
    *   If we are keeping the current version number (e.g. 67), ensure the new `BASELINE_SCHEMA` creates the `schema_version` table with that version pre-inserted.
    *   *Alternative*: Reset version to "1" of the new era (e.g. v100) to distinguish old vs new.
3.  **Remove Legacy Imports**: Remove imports of `migrations_legacy`.

### B. Delete `src/gobby/storage/migrations_legacy.py`
1.  **Delete File**: `rm src/gobby/storage/migrations_legacy.py`.
2.  **Clean Up**: usage in `migrations.py` (already handled in A).

## 4. Verification
1.  **New Install Test**:
    *   Move existing DB: `mv ~/.gobby/gobby-hub.db ~/.gobby/gobby-hub.db.old`
    *   Start Daemon: `gobby start` (should create new DB with new baseline)
    *   Verify Schema: Check table structure matches expectation.
2.  **Existing DB Test**:
    *   Restore DB: `mv ~/.gobby/gobby-hub.db.old ~/.gobby/gobby-hub.db`
    *   Start Daemon: Ensure it starts without attempting to re-apply migrations or failing on version check.

## 5. Script: `scripts/flatten_migrations.sh`
Create a helper script to automate the backup and schema dump to minimize human error.

```bash
#!/bin/bash
set -e
DB_PATH="$HOME/.gobby/gobby-hub.db"
BACKUP_PATH="$DB_PATH.pre-flatten.bak"
echo "Backing up DB to $BACKUP_PATH..."
cp "$DB_PATH" "$BACKUP_PATH"
echo "Dumping schema..."
sqlite3 "$DB_PATH" .schema > src/gobby/storage/schema_dump.sql
echo "Ready to copy schema_dump.sql into migrations.py"
```

## Execution Order
1.  Run Backup.
2.  Dump Schema.
3.  Update `migrations.py`.
4.  Delete `migrations_legacy.py`.
5.  Verify new install.
