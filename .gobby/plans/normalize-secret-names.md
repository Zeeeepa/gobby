# Plan: Normalize Secret Names for Case-Insensitive Upsert

## Problem

Secret names are case-sensitive, so `ELEVENLABS_API_KEY` and `elevenlabs_api_key` are stored as separate rows. This causes:
- Duplicate secrets that confuse users
- Silent resolution failures when the `$secret:NAME` ref doesn't match the stored casing
- Wasted encrypted storage

Currently in your DB:
```
ELEVENLABS_API_KEY  (integration, Feb 17)  ← orphaned
elevenlabs_api_key  (general, Feb 25)      ← active
```

## Approach: Normalize to Lowercase at the Storage Layer

Normalize all secret names to lowercase at the `SecretStore` boundary. This is the simplest, safest approach — one internal normalization point, everything downstream just works.

### Why lowercase?
- `config_key_to_secret_name()` already produces lowercase names from dotted keys (`voice.elevenlabs_api_key` → `elevenlabs_api_key`)
- The `$secret:NAME` regex pattern allows mixed case, so resolution still matches
- SQLite `UNIQUE` constraint will naturally prevent duplicates once names are normalized

## Files to Modify

### 1. `src/gobby/storage/secrets.py` — Core normalization

Add a `_normalize_name()` helper and apply it in every public method:

```python
def _normalize_name(name: str) -> str:
    """Normalize secret name to lowercase for case-insensitive matching."""
    return name.strip().lower()
```

Apply in:
- `set()` — normalize `name` param before lookup/insert
- `get()` — normalize before SELECT
- `delete()` — normalize before SELECT/DELETE
- `exists()` — normalize before SELECT
- `resolve()` — normalize the captured group in `_replace()`

**Do NOT** normalize the `name` column value stored in the DB — store the normalized form directly. This means the `SecretInfo.name` returned will be lowercase.

### 2. `src/gobby/servers/routes/configuration.py` — HTTP endpoint

In `save_secret()`: normalize `request.name` before passing to `store.set()`. This ensures secrets created via the REST API (`POST /api/config/secrets`) also go through normalization.

In `delete_secret()`: normalize the path param `name` before passing to `store.delete()`.

### 3. `src/gobby/storage/config_store.py` — No changes needed

`config_key_to_secret_name()` already produces lowercase from dotted keys. The `set_secret()` and `clear_secret()` methods call through to `SecretStore.set()` and `.delete()`, which will normalize internally. No changes here.

### 4. `src/gobby/storage/migrations.py` — Migration to deduplicate existing rows

Add a new migration (next version) that:
1. Finds duplicate secret names (case-insensitive)
2. Keeps the most recently updated row, deletes the rest
3. Lowercases all remaining `name` values
4. Updates any `$secret:` references in `config_store` to use the lowercase name

```sql
-- Pseudocode for the migration:
-- 1. Find groups with case-insensitive duplicates
-- 2. For each group, keep the row with MAX(updated_at), delete others
-- 3. UPDATE secrets SET name = LOWER(name)
-- 4. UPDATE config_store SET value = REPLACE(value, old_ref, new_ref) WHERE value LIKE '"$secret:%'
```

### 5. `tests/storage/test_secrets_store.py` — New tests

Add test cases:
- `test_set_normalizes_name_case` — set with `"API_KEY"`, get with `"api_key"`, verify round-trip
- `test_upsert_case_insensitive` — set `"API_KEY"` then `"api_key"`, verify single row with updated value
- `test_delete_case_insensitive` — set `"API_KEY"`, delete `"api_key"`, verify gone
- `test_exists_case_insensitive` — set `"API_KEY"`, exists `"api_key"` returns True
- `test_resolve_case_insensitive` — store `"API_KEY"`, resolve `$secret:api_key`, verify success
- `test_name_stored_lowercase` — set `"MY_KEY"`, verify `SecretInfo.name == "my_key"`

### 6. `tests/servers/routes/test_configuration_routes.py` — Update existing tests

Update any assertions that check for uppercase secret names in `SecretInfo` responses.

## Implementation Order

1. **Migration first** — deduplicate existing data and lowercase all names
2. **`secrets.py`** — add `_normalize_name()`, apply everywhere
3. **`configuration.py`** — normalize in HTTP handlers
4. **Tests** — add new cases, update existing assertions
5. **Verify** — run full test suite

## Verification

```bash
# Run secret store tests
pytest tests/storage/test_secrets_store.py -v

# Run config route tests
pytest tests/servers/routes/test_configuration_routes.py -v

# Run MCP config tool tests
pytest tests/mcp_proxy/tools/test_config.py -v

# Full suite
pytest --tb=short
```

## Edge Cases

- **`$secret:` regex** — the pattern `[A-Za-z_][A-Za-z0-9_]*` already accepts both cases, and `resolve()` will lowercase the captured name before lookup. No regex change needed.
- **Existing `$secret:` references in config_store** — the migration normalizes these too
- **`config_key_to_secret_name()`** — already returns lowercase, no change needed
- **`SecretInfo.name`** — will now always be lowercase. If anything in the web UI or API responses relied on the original casing, it'll shift. This is fine — the name is an identifier, not a display label.
