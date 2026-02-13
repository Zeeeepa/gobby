"""Background processor that syncs memories to Mem0.

Follows the CronScheduler dual-loop pattern (scheduler/scheduler.py):
- _sync_loop: polls for mem0_id IS NULL rows every sync_interval seconds
- Uses exponential backoff on Mem0 connection failures
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gobby.memory.manager import MemoryManager

from gobby.memory.mem0_client import Mem0ConnectionError

logger = logging.getLogger(__name__)


class Mem0SyncProcessor:
    """Background processor that syncs memories to Mem0.

    Dual-loop pattern:
    - _sync_loop: polls for mem0_id IS NULL rows every sync_interval seconds
    - Uses exponential backoff on Mem0 connection failures
    """

    def __init__(
        self,
        memory_manager: MemoryManager,
        sync_interval: float = 10.0,
        max_backoff: float = 300.0,
    ):
        self.memory_manager = memory_manager
        self.sync_interval = sync_interval
        self.max_backoff = max_backoff
        self._running = False
        self._sync_task: asyncio.Task[None] | None = None

        # Observability state
        self._last_sync_at: datetime | None = None
        self._last_sync_count: int = 0
        self._backoff_active: bool = False

    @property
    def stats(self) -> dict[str, object]:
        """Return current sync stats for observability."""
        pending = 0
        try:
            rows = self.memory_manager.db.fetchall(
                "SELECT COUNT(*) as cnt FROM memories WHERE mem0_id IS NULL", ()
            )
            if rows:
                pending = rows[0]["cnt"]
        except Exception:
            pass

        return {
            "pending": pending,
            "last_sync_at": self._last_sync_at.isoformat() if self._last_sync_at else None,
            "last_sync_count": self._last_sync_count,
            "backoff_active": self._backoff_active,
        }

    async def start(self) -> None:
        """Start the sync loop."""
        if self._running:
            return
        if not self.memory_manager._mem0_client:
            logger.debug("Mem0SyncProcessor not started: no Mem0 client configured")
            return

        self._running = True
        self._sync_task = asyncio.create_task(self._sync_loop(), name="mem0-sync")
        logger.info(
            f"Mem0SyncProcessor started (interval={self.sync_interval}s, "
            f"max_backoff={self.max_backoff}s)"
        )

    async def stop(self) -> None:
        """Stop gracefully, letting in-flight sync complete."""
        self._running = False
        if self._sync_task:
            self._sync_task.cancel()
            await asyncio.gather(self._sync_task, return_exceptions=True)
            self._sync_task = None
        logger.info("Mem0SyncProcessor stopped")

    async def _sync_loop(self) -> None:
        """Poll for unsynced memories and push to Mem0."""
        backoff = self.sync_interval
        while self._running:
            try:
                synced = await self.memory_manager._lazy_sync()
                self._last_sync_at = datetime.now(UTC)
                self._last_sync_count = synced
                if synced > 0:
                    logger.info(f"Mem0 sync: pushed {synced} memories")
                backoff = self.sync_interval  # reset on success
                self._backoff_active = False
            except Mem0ConnectionError:
                backoff = min(backoff * 2, self.max_backoff)
                self._backoff_active = True
                logger.warning(f"Mem0 unreachable, backing off to {backoff}s")
            except Exception as e:
                logger.error(f"Mem0 sync error: {e}", exc_info=True)
            try:
                await asyncio.sleep(backoff)
            except asyncio.CancelledError:
                break
