"""Embedding generation and storage service for memories.

Extracted from manager.py as part of Strangler Fig decomposition (Wave 2).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Any

from gobby.config.persistence import MemoryConfig
from gobby.search.embeddings import generate_embedding, generate_embeddings, is_embedding_available
from gobby.storage.memories import LocalMemoryManager
from gobby.storage.memory_embeddings import MemoryEmbeddingManager

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Handles embedding generation and storage for memories."""

    def __init__(
        self,
        config: MemoryConfig,
        embedding_mgr: MemoryEmbeddingManager,
        storage: LocalMemoryManager,
        embedding_api_key: str | None = None,
        background_tasks: set[asyncio.Task[Any]] | None = None,
    ):
        self._config = config
        self._embedding_mgr = embedding_mgr
        self._storage = storage
        self._embedding_api_key = embedding_api_key
        self._background_tasks = background_tasks or set()

    def _store_embedding_sync(self, memory_id: str, content: str, project_id: str | None) -> None:
        """Generate and store an embedding for a memory (sync, non-blocking).

        Failures are logged but never propagated — CRUD operations must not
        be blocked by embedding generation errors.
        """
        if not is_embedding_available(
            model=self._config.embedding_model, api_key=self._embedding_api_key
        ):
            return

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # We are in an event loop. Schedule as background task to avoid blocking/crashing.
            task = loop.create_task(self._store_embedding_async(memory_id, content, project_id))
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
            return

        try:
            embedding = asyncio.run(generate_embedding(content, model=self._config.embedding_model))

            text_hash = hashlib.sha256(content.encode()).hexdigest()
            self._embedding_mgr.store_embedding(
                memory_id=memory_id,
                project_id=project_id,
                embedding=embedding,
                embedding_model=self._config.embedding_model,
                text_hash=text_hash,
            )
        except Exception as e:
            logger.warning(f"Failed to generate embedding for memory {memory_id}: {e}")

    async def _store_embedding_async(
        self, memory_id: str, content: str, project_id: str | None
    ) -> None:
        """Generate and store an embedding for a memory (async, non-blocking)."""
        if not is_embedding_available(
            model=self._config.embedding_model, api_key=self._embedding_api_key
        ):
            return

        try:
            embedding = await generate_embedding(content, model=self._config.embedding_model)
            text_hash = hashlib.sha256(content.encode()).hexdigest()
            self._embedding_mgr.store_embedding(
                memory_id=memory_id,
                project_id=project_id,
                embedding=embedding,
                embedding_model=self._config.embedding_model,
                text_hash=text_hash,
            )
        except Exception as e:
            logger.warning(f"Failed to generate embedding for memory {memory_id}: {e}")

    async def reindex_embeddings(self) -> dict[str, Any]:
        """Generate embeddings for all memories in batch.

        Returns:
            Dict with success status, total_memories, embeddings_generated.
        """
        if not is_embedding_available(
            model=self._config.embedding_model, api_key=self._embedding_api_key
        ):
            return {
                "success": False,
                "error": "Embedding unavailable — no API key configured",
            }

        batch_size = 500
        total_memories = 0
        total_generated = 0
        offset = 0
        truncated = False

        while True:
            memories = self._storage.list_memories(limit=batch_size, offset=offset)
            if not memories:
                break

            total_memories += len(memories)
            if total_memories > 10000:
                truncated = True
                break

            texts = [m.content for m in memories]
            try:
                embeddings = await generate_embeddings(texts, model=self._config.embedding_model)
            except Exception as e:
                logger.error(f"Batch embedding generation failed at offset {offset}: {e}")
                return {"success": False, "error": str(e)}

            items = []
            for memory, embedding in zip(memories, embeddings, strict=True):
                items.append(
                    {
                        "memory_id": memory.id,
                        "project_id": memory.project_id,
                        "embedding": embedding,
                        "embedding_model": self._config.embedding_model,
                        "text_hash": hashlib.sha256(memory.content.encode()).hexdigest(),
                    }
                )

            total_generated += self._embedding_mgr.batch_store_embeddings(items)
            offset += batch_size

            if len(memories) < batch_size:
                break

        return {
            "success": True,
            "total_memories": total_memories,
            "embeddings_generated": total_generated,
            "truncated": truncated,
        }
