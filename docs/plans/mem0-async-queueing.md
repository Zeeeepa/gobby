# Async Mem0 Queueing: Write-Ahead with Background Sync

## Context

`MemoryManager.remember()` calls `_index_in_mem0()` synchronously (line 329 of `memory/manager.py`), which blocks the MCP tool call for 17-25 seconds while Mem0 generates embeddings and stores them. The architecture is already 90% ready for async decoupling:

- **`mem0_id IS NULL` column** — memories created locally get `mem0_id = NULL` until synced
- **`_lazy_sync()`** (line 1057) — batch syncs all `mem0_id IS NULL` rows, already handles connection errors gracefully
- **`Mem0Client`** — fully async httpx client with configurable timeout

The only missing piece is removing the blocking `await _index_in_mem0()` from `remember()` and replacing it with a background processor.

## Phase 1: Core Async Decoupling

### 1.1 Remove blocking call from `remember()`

**File:** `src/gobby/memory/manager.py`

In `remember()` (line 329), replace:
```python
# Mem0 dual-mode: index in Mem0 after local storage
await self._index_in_mem0(memory.id, content, project_id)
```

With a no-op comment — the `Mem0SyncProcessor` handles it:
```python
# Mem0 sync handled by background Mem0SyncProcessor (mem0_id IS NULL queue)
```

`remember()` returns immediately after local storage + embedding. Mem0 sync happens out-of-band.

### 1.2 Create `Mem0SyncProcessor`

**New file:** `src/gobby/memory/mem0_sync.py`

Follows the `CronScheduler` dual-loop pattern (`scheduler/scheduler.py`):

```python
class Mem0SyncProcessor:
    """Background processor that syncs memories to Mem0.

    Dual-loop pattern:
    - _sync_loop: polls for mem0_id IS NULL rows every sync_interval seconds
    - Uses exponential backoff on Mem0 connection failures
    """

    def __init__(self, memory_manager: MemoryManager, config: Mem0SyncConfig):
        self.memory_manager = memory_manager
        self.config = config
        self._running = False
        self._sync_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the sync loop."""
        if self._running or not self.config.enabled:
            return
        self._running = True
        self._sync_task = asyncio.create_task(
            self._sync_loop(), name="mem0-sync"
        )

    async def stop(self) -> None:
        """Stop gracefully, letting in-flight sync complete."""
        self._running = False
        if self._sync_task:
            self._sync_task.cancel()
            await asyncio.gather(self._sync_task, return_exceptions=True)

    async def _sync_loop(self) -> None:
        backoff = self.config.sync_interval
        while self._running:
            try:
                synced = await self.memory_manager._lazy_sync()
                if synced > 0:
                    logger.info(f"Mem0 sync: pushed {synced} memories")
                backoff = self.config.sync_interval  # reset on success
            except Mem0ConnectionError:
                backoff = min(backoff * 2, self.config.max_backoff)
                logger.warning(f"Mem0 unreachable, backing off to {backoff}s")
            except Exception as e:
                logger.error(f"Mem0 sync error: {e}", exc_info=True)
            try:
                await asyncio.sleep(backoff)
            except asyncio.CancelledError:
                break
```

### 1.3 Config fields

**File:** `src/gobby/config/persistence.py`

Add to `MemoryConfig`:

```python
mem0_sync_interval: float = Field(
    default=10.0,
    description="Seconds between Mem0 background sync attempts",
)
mem0_sync_max_backoff: float = Field(
    default=300.0,
    description="Maximum backoff seconds on Mem0 connection failure",
)
```

Or introduce a nested `Mem0SyncConfig` model if preferred for clarity.

### 1.4 Runner wiring

**File:** `src/gobby/runner.py`

Wire `Mem0SyncProcessor` into `GobbyRunner`:
- Instantiate after `MemoryManager` init
- `await mem0_sync.start()` after lifecycle manager start
- `await mem0_sync.stop()` during shutdown (before memory manager cleanup)

## Phase 2: Search Resilience

### Problem

Memories with `mem0_id IS NULL` (not yet synced) won't appear in Mem0 search results. If the user creates a memory and searches immediately, Mem0 returns nothing.

### Fix: Merge local + Mem0 results

**File:** `src/gobby/memory/manager.py` — `search()` / `_search_in_mem0()`

When Mem0 search returns results, also query local memories with `mem0_id IS NULL` and merge:

```sql
SELECT id, content, project_id FROM memories
WHERE mem0_id IS NULL
  AND content LIKE '%' || ? || '%'
ORDER BY created_at DESC
LIMIT 20
```

Merge by deduplicating on `memory.id` (local always wins). This ensures freshly-created memories surface in search even before Mem0 sync completes.

The existing local search index (`_search_service`) already covers these memories, so this may be as simple as falling back to local search when Mem0 results are sparse.

## Phase 3: Observability

### `memory_stats` endpoint

**File:** `src/gobby/memory/manager.py` — `get_stats()`

Add to the stats dict:

```python
{
    "mem0_sync": {
        "pending": count_of_mem0_id_is_null,
        "last_sync_at": timestamp_or_null,
        "last_sync_count": int,
        "backoff_active": bool,
    }
}
```

Query: `SELECT COUNT(*) FROM memories WHERE mem0_id IS NULL`

This gives operators visibility into sync lag and backoff state.

## Files Summary

| File | Change | Phase |
|------|--------|-------|
| `src/gobby/memory/manager.py` | Remove blocking `_index_in_mem0()` from `remember()` | 1 |
| `src/gobby/memory/mem0_sync.py` | New: `Mem0SyncProcessor` (dual-loop, backoff) | 1 |
| `src/gobby/config/persistence.py` | Add `mem0_sync_interval`, `mem0_sync_max_backoff` | 1 |
| `src/gobby/runner.py` | Wire `Mem0SyncProcessor` start/stop | 1 |
| `src/gobby/memory/manager.py` | Merge unsynced local memories into search | 2 |
| `src/gobby/memory/manager.py` | Add `mem0_sync` to `get_stats()` | 3 |

## Verification

- [ ] `create_memory` MCP call returns in <1s (was 17-25s)
- [ ] Memories appear in local search immediately after creation
- [ ] Mem0 receives the memory within `sync_interval` seconds
- [ ] Stopping Mem0 container triggers backoff (visible in logs)
- [ ] Restarting Mem0 container resumes sync (backoff resets)
- [ ] `memory_stats` shows accurate `pending` count
- [ ] No data loss: all memories eventually get `mem0_id` populated
- [ ] Graceful shutdown waits for in-flight sync before exit
