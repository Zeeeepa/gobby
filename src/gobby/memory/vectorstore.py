"""Qdrant-based vector store for memory embeddings.

Wraps qdrant-client with async support via asyncio.to_thread().
Supports embedded mode (on-disk, zero Docker) or remote Qdrant server.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PointIdsList,
    PointStruct,
    VectorParams,
)

logger = logging.getLogger(__name__)


class VectorStore:
    """Async wrapper around Qdrant for memory vector storage.

    Uses embedded mode (path) for local operation or remote mode (url) for
    external Qdrant servers. All blocking qdrant-client calls are wrapped
    in asyncio.to_thread() for async compatibility.

    Args:
        path: Directory path for embedded Qdrant storage.
        url: URL for remote Qdrant server.
        api_key: API key for remote Qdrant server.
        collection_name: Name of the Qdrant collection.
        embedding_dim: Dimensionality of embedding vectors.
    """

    def __init__(
        self,
        path: str | None = None,
        url: str | None = None,
        api_key: str | None = None,
        collection_name: str = "memories",
        embedding_dim: int = 1536,
    ) -> None:
        self._path = path
        self._url = url
        self._api_key = api_key
        self._collection_name = collection_name
        self._embedding_dim = embedding_dim
        self._client: QdrantClient | None = None

    async def initialize(self) -> None:
        """Create the Qdrant client and ensure the collection exists."""
        if self._client is None:
            if self._url:
                self._client = await asyncio.to_thread(
                    QdrantClient, url=self._url, api_key=self._api_key
                )
            else:
                self._client = await asyncio.to_thread(QdrantClient, path=self._path)

        # Check if collection exists; create if not
        client = self._client
        assert client is not None
        exists = await asyncio.to_thread(client.collection_exists, self._collection_name)
        if not exists:
            await asyncio.to_thread(
                client.create_collection,
                collection_name=self._collection_name,
                vectors_config=VectorParams(size=self._embedding_dim, distance=Distance.COSINE),
            )
            logger.info(
                f"Created Qdrant collection '{self._collection_name}' "
                f"(dim={self._embedding_dim}, distance=cosine)"
            )
        else:
            # Check for dimension mismatch between config and existing collection
            try:
                info = await asyncio.to_thread(client.get_collection, self._collection_name)
                existing_dim = info.config.params.vectors.size  # type: ignore[union-attr]
                if existing_dim != self._embedding_dim:
                    logger.error(
                        f"Embedding dimension mismatch for collection '{self._collection_name}': "
                        f"configured={self._embedding_dim}, existing={existing_dim}. "
                        f"Either change embedding_dim in config to {existing_dim}, "
                        f"or run 'gobby memory rebuild' to re-embed with the new model."
                    )
            except Exception as e:
                logger.warning(
                    f"Could not verify collection dimensions for '{self._collection_name}': {e}"
                )

    def _ensure_client(self) -> QdrantClient:
        """Return the client, raising if not initialized."""
        if self._client is None:
            raise RuntimeError("VectorStore not initialized. Call initialize() first.")
        return self._client

    async def upsert(
        self,
        memory_id: str,
        embedding: list[float],
        payload: dict[str, Any] | None = None,
        collection_name: str | None = None,
    ) -> None:
        """Insert or update a single point."""
        client = self._ensure_client()
        point = PointStruct(
            id=memory_id,
            vector=embedding,
            payload=payload or {},
        )
        await asyncio.to_thread(
            client.upsert,
            collection_name=collection_name or self._collection_name,
            points=[point],
        )

    async def search(
        self,
        query_embedding: list[float],
        limit: int = 10,
        filters: dict[str, str] | None = None,
        collection_name: str | None = None,
    ) -> list[tuple[str, float]]:
        """Search for similar vectors.

        Args:
            query_embedding: Query vector.
            limit: Maximum number of results.
            filters: Optional field filters (e.g. {"project_id": "proj-A"}).
            collection_name: Optional collection name override.

        Returns:
            List of (memory_id, score) tuples sorted by relevance (desc).
        """
        client = self._ensure_client()

        query_filter = None
        if filters:
            conditions = [
                FieldCondition(key=k, match=MatchValue(value=v)) for k, v in filters.items()
            ]
            query_filter = Filter(must=conditions)

        results = await asyncio.to_thread(
            client.query_points,
            collection_name=collection_name or self._collection_name,
            query=query_embedding,
            query_filter=query_filter,
            limit=limit,
        )

        return [(str(point.id), point.score) for point in results.points]

    async def set_payload(
        self,
        memory_id: str,
        payload: dict[str, Any],
        collection_name: str | None = None,
    ) -> None:
        """Update payload fields on a point without re-embedding.

        Args:
            memory_id: The point ID to update.
            payload: Payload fields to set/overwrite.
            collection_name: Optional collection name override.
        """
        client = self._ensure_client()
        await asyncio.to_thread(
            client.set_payload,
            collection_name=collection_name or self._collection_name,
            payload=payload,
            points=[memory_id],
        )

    async def delete(
        self,
        memory_id: str | None = None,
        filters: dict[str, str] | None = None,
        collection_name: str | None = None,
    ) -> None:
        """Delete a point by memory ID or filter."""
        client = self._ensure_client()

        selector: PointIdsList | FilterSelector
        if memory_id:
            selector = PointIdsList(points=[memory_id])
        elif filters:
            conditions = [
                FieldCondition(key=k, match=MatchValue(value=v)) for k, v in filters.items()
            ]
            selector = FilterSelector(filter=Filter(must=conditions))
        else:
            raise ValueError("Must provide either memory_id or filters to delete")

        await asyncio.to_thread(
            client.delete,
            collection_name=collection_name or self._collection_name,
            points_selector=selector,
        )

    async def batch_upsert(
        self,
        items: list[tuple[str, list[float], dict[str, Any]]],
        collection_name: str | None = None,
    ) -> None:
        """Insert or update multiple points at once.

        Args:
            items: List of (memory_id, embedding, payload) tuples.
            collection_name: Optional collection name override.
        """
        if not items:
            return
        client = self._ensure_client()
        points = [
            PointStruct(id=memory_id, vector=embedding, payload=payload)
            for memory_id, embedding, payload in items
        ]
        await asyncio.to_thread(
            client.upsert,
            collection_name=collection_name or self._collection_name,
            points=points,
        )

    async def ensure_collection(
        self, collection_name: str, embedding_dim: int | None = None
    ) -> None:
        """Ensure a named collection exists, creating it if needed.

        Args:
            collection_name: Collection to ensure
            embedding_dim: Vector dimension (defaults to instance's _embedding_dim)
        """
        client = self._ensure_client()
        dim = embedding_dim or self._embedding_dim
        exists = await asyncio.to_thread(client.collection_exists, collection_name)
        if not exists:
            await asyncio.to_thread(
                client.create_collection,
                collection_name=collection_name,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            )
            logger.info(f"Created Qdrant collection '{collection_name}' (dim={dim})")
        else:
            try:
                info = await asyncio.to_thread(client.get_collection, collection_name)
                existing_dim = info.config.params.vectors.size  # type: ignore[union-attr]
                if existing_dim != dim:
                    # Auto-recreate with correct dimensions
                    await asyncio.to_thread(
                        client.delete_collection, collection_name=collection_name
                    )
                    await asyncio.to_thread(
                        client.create_collection,
                        collection_name=collection_name,
                        vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
                    )
                    logger.info(
                        f"Recreated Qdrant collection '{collection_name}' "
                        f"(dim changed {existing_dim}→{dim})"
                    )
            except Exception as e:
                logger.warning(f"Could not verify collection '{collection_name}': {e}")

    async def delete_collection(self, collection_name: str) -> None:
        """Delete a collection by name."""
        client = self._ensure_client()
        await asyncio.to_thread(
            client.delete_collection,
            collection_name=collection_name,
        )

    async def count(self) -> int:
        """Return the number of points in the collection."""
        client = self._ensure_client()
        result = await asyncio.to_thread(client.count, collection_name=self._collection_name)
        count: int = result.count
        return count

    def count_sync(self) -> int:
        """Return the number of points in the collection (synchronous).

        Safe to call from sync code running inside an async event loop.
        """
        client = self._ensure_client()
        result = client.count(collection_name=self._collection_name)
        return result.count

    async def rebuild(
        self,
        memories: list[dict[str, Any]],
        embed_fn: Callable[[str], Awaitable[list[float]]],
    ) -> None:
        """Rebuild the collection from a list of memories.

        Deletes all existing points and re-embeds from the provided memory list.

        Args:
            memories: List of dicts with at least 'id' and 'content' keys.
                      Other keys are stored as payload.
            embed_fn: Async function that takes content text and returns embedding.
        """
        client = self._ensure_client()

        # Delete and recreate collection for clean rebuild
        await asyncio.to_thread(client.delete_collection, collection_name=self._collection_name)
        await asyncio.to_thread(
            client.create_collection,
            collection_name=self._collection_name,
            vectors_config=VectorParams(size=self._embedding_dim, distance=Distance.COSINE),
        )

        if not memories:
            return

        # Embed and upsert in batches
        items: list[tuple[str, list[float], dict[str, Any]]] = []
        for mem in memories:
            content = mem["content"]
            embedding = await embed_fn(content)
            payload = {k: v for k, v in mem.items() if k not in ("id",)}
            items.append((mem["id"], embedding, payload))

        await self.batch_upsert(items)
        logger.info(f"Rebuilt {len(items)} vectors in '{self._collection_name}'")

    async def close(self) -> None:
        """Close the Qdrant client connection."""
        if self._client is not None:
            await asyncio.to_thread(self._client.close)
            self._client = None
