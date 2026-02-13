"""Mem0 synchronization service for dual-mode memory storage.

Extracted from manager.py as part of Strangler Fig decomposition (Wave 2).
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from gobby.memory.mem0_client import Mem0ConnectionError

if TYPE_CHECKING:
    from gobby.memory.mem0_client import Mem0Client
    from gobby.storage.database import DatabaseProtocol
    from gobby.storage.memories import Memory

logger = logging.getLogger(__name__)


class Mem0Service:
    """Handles Mem0 indexing, deletion, search, and lazy sync."""

    def __init__(
        self,
        get_mem0_client: Callable[[], Mem0Client | None],
        db: DatabaseProtocol,
        get_memory_fn: Callable[[str], Memory | None],
        recall_with_search_fn: Callable[..., list[Memory]],
    ):
        self._get_mem0_client = get_mem0_client
        self._db = db
        self._get_memory = get_memory_fn
        self._recall_with_search = recall_with_search_fn

    @property
    def _mem0_client(self) -> Mem0Client | None:
        """Dynamically resolve the Mem0 client (supports test monkey-patching)."""
        return self._get_mem0_client()

    async def _index_in_mem0(self, memory_id: str, content: str, project_id: str | None) -> None:
        """Index a memory in Mem0 after local storage. Non-blocking on failure."""
        if not self._mem0_client:
            return

        try:
            result = await self._mem0_client.create(
                content=content,
                project_id=project_id,
                metadata={"gobby_id": memory_id},
            )
            # Extract mem0_id from response and store it
            mem0_id = self._extract_mem0_id(result)
            if mem0_id:
                self._db.execute(
                    "UPDATE memories SET mem0_id = ? WHERE id = ?",
                    (mem0_id, memory_id),
                )
        except Mem0ConnectionError as e:
            logger.warning(f"Mem0 unreachable during index for {memory_id}: {e}")
        except Exception as e:
            logger.warning(f"Failed to index memory {memory_id} in Mem0: {e}")

    @staticmethod
    def _extract_mem0_id(response: Any) -> str | None:
        """Extract the mem0 memory ID from a create response."""
        if isinstance(response, dict):
            results = response.get("results", [])
            if results and isinstance(results[0], dict):
                return results[0].get("id")
        return None

    async def _delete_from_mem0(self, memory_id: str) -> None:
        """Delete a memory from Mem0 if it has a mem0_id. Non-blocking on failure."""
        memory = self._get_memory(memory_id)
        if not memory or not memory.mem0_id:
            return

        try:
            await self._mem0_client.delete(memory.mem0_id)  # type: ignore[union-attr]
        except Mem0ConnectionError as e:
            logger.warning(f"Mem0 unreachable during delete for {memory_id}: {e}")
        except Exception as e:
            logger.warning(f"Failed to delete memory {memory_id} from Mem0: {e}")

    def _search_mem0(self, query: str, project_id: str | None, limit: int) -> list[Memory] | None:
        """Search Mem0 and return local memories enriched by results.

        Returns None if Mem0 is unavailable (caller should fall back to local search).

        Warning: This method blocks the calling thread. When called from an
        async context, it spawns a thread pool to run the async Mem0 search.
        """
        if self._mem0_client is None:
            raise RuntimeError("Mem0 client is not initialized")

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        try:
            if loop and loop.is_running():
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    result = pool.submit(
                        asyncio.run,
                        self._mem0_client.search(query=query, project_id=project_id, limit=limit),
                    ).result()
            else:
                result = asyncio.run(
                    self._mem0_client.search(query=query, project_id=project_id, limit=limit)
                )
        except Mem0ConnectionError as e:
            logger.warning(f"Mem0 unreachable during search, falling back to local: {e}")
            return None
        except Exception as e:
            logger.warning(f"Mem0 search failed, falling back to local: {e}")
            return None

        # Enrich mem0 results with local memory data
        memories: list[Memory] = []
        for item in result.get("results", []):
            gobby_id = (item.get("metadata") or {}).get("gobby_id")
            if gobby_id:
                local = self._get_memory(gobby_id)
                if local:
                    memories.append(local)

        return memories

    def _get_unsynced_memories(
        self, query: str, project_id: str | None, limit: int
    ) -> list[Memory]:
        """Get local memories not yet synced to Mem0 that match the query.

        Uses the local search backend for ranking rather than raw SQL LIKE,
        filtering results to only those with mem0_id IS NULL.
        """
        # Use local search to find matching memories
        local_results = self._recall_with_search(
            query=query, project_id=project_id, limit=limit * 2
        )
        # Filter to only unsynced ones
        unsynced_ids: set[str] = set()
        try:
            rows = self._db.fetchall("SELECT id FROM memories WHERE mem0_id IS NULL", ())
            unsynced_ids = {row["id"] for row in rows}
        except Exception as e:
            logger.warning(f"Failed to query unsynced memories: {e}")
            return []

        return [m for m in local_results if m.id in unsynced_ids][:limit]

    async def _lazy_sync(self) -> int:
        """Sync memories that have mem0_id IS NULL to Mem0.

        Returns the number of memories successfully synced.
        """
        if not self._mem0_client:
            return 0

        batch_size = 100
        synced = 0
        offset = 0

        while True:
            rows = self._db.fetchall(
                "SELECT id, content, project_id FROM memories "
                "WHERE mem0_id IS NULL LIMIT ? OFFSET ?",
                (batch_size, offset),
            )
            if not rows:
                break

            for row in rows:
                try:
                    result = await self._mem0_client.create(
                        content=row["content"],
                        project_id=row["project_id"],
                        metadata={"gobby_id": row["id"]},
                    )
                    mem0_id = self._extract_mem0_id(result)
                    if mem0_id:
                        self._db.execute(
                            "UPDATE memories SET mem0_id = ? WHERE id = ?",
                            (mem0_id, row["id"]),
                        )
                        synced += 1
                except Mem0ConnectionError as e:
                    logger.warning(f"Mem0 unreachable during lazy sync for {row['id']}: {e}")
                    return synced  # Stop on connection errors
                except Exception as e:
                    logger.warning(f"Failed to sync memory {row['id']} to Mem0: {e}")

            offset += batch_size

        return synced
