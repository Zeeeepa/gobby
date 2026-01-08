"""
Benchmark: Semantic vs Text Search for Memory Recall.

Compares performance and accuracy of:
- Text search: SQL LIKE pattern matching
- Semantic search: Embedding-based cosine similarity

Run with: uv run pytest tests/memory/test_search_benchmark.py -v -s
"""

import statistics
import time
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from gobby.config.app import MemoryConfig
from gobby.memory.manager import MemoryManager
from gobby.storage.database import LocalDatabase
from gobby.storage.migrations import run_migrations

# Test corpus: memories with known content for accuracy testing
TEST_MEMORIES = [
    # Programming facts
    {
        "content": "Python uses indentation for code blocks instead of braces",
        "type": "fact",
        "topics": ["python", "syntax"],
    },
    {
        "content": "JavaScript is a dynamically typed programming language",
        "type": "fact",
        "topics": ["javascript", "types"],
    },
    {
        "content": "Rust provides memory safety without garbage collection",
        "type": "fact",
        "topics": ["rust", "memory"],
    },
    {
        "content": "Go has built-in concurrency with goroutines and channels",
        "type": "fact",
        "topics": ["go", "concurrency"],
    },
    {
        "content": "TypeScript adds static types to JavaScript",
        "type": "fact",
        "topics": ["typescript", "javascript", "types"],
    },
    # Testing preferences
    {
        "content": "Always write unit tests before integration tests",
        "type": "preference",
        "topics": ["testing"],
    },
    {
        "content": "Use pytest fixtures for test setup and teardown",
        "type": "preference",
        "topics": ["testing", "pytest"],
    },
    {
        "content": "Mock external APIs in unit tests to avoid flakiness",
        "type": "preference",
        "topics": ["testing", "mocking"],
    },
    # Architecture patterns
    {
        "content": "Use dependency injection for loose coupling between components",
        "type": "pattern",
        "topics": ["architecture", "di"],
    },
    {
        "content": "Prefer composition over inheritance in object-oriented design",
        "type": "pattern",
        "topics": ["architecture", "oop"],
    },
    {
        "content": "Apply the single responsibility principle to keep functions focused",
        "type": "pattern",
        "topics": ["architecture", "solid"],
    },
    # Database facts
    {
        "content": "SQLite is a serverless embedded database engine",
        "type": "fact",
        "topics": ["database", "sqlite"],
    },
    {
        "content": "PostgreSQL supports JSON columns for semi-structured data",
        "type": "fact",
        "topics": ["database", "postgresql", "json"],
    },
    {
        "content": "Redis is an in-memory data structure store used for caching",
        "type": "fact",
        "topics": ["database", "redis", "caching"],
    },
    # Git workflows
    {
        "content": "Always create feature branches from main for new work",
        "type": "preference",
        "topics": ["git", "branching"],
    },
    {
        "content": "Use conventional commits for clear commit message format",
        "type": "preference",
        "topics": ["git", "commits"],
    },
]

# Test queries with expected relevant memory indices
# Mix of exact substring matches (for text search) and semantic queries
TEST_QUERIES = [
    # Exact matches that text search can find
    {"query": "indentation", "expected_indices": [0], "topic": "python"},
    {"query": "pytest fixtures", "expected_indices": [6], "topic": "testing"},
    {"query": "SQLite", "expected_indices": [11], "topic": "database"},
    {"query": "TypeScript", "expected_indices": [4], "topic": "types"},
    # Semantic queries that require understanding
    {"query": "memory safety without GC", "expected_indices": [2], "topic": "memory"},
    {
        "query": "loose coupling design patterns",
        "expected_indices": [8, 9],
        "topic": "architecture",
    },
    {"query": "branch workflow", "expected_indices": [14], "topic": "git"},
    {"query": "parallel execution", "expected_indices": [3], "topic": "concurrency"},
]


def create_mock_embedding(content: str) -> list[float]:
    """
    Create a deterministic mock embedding based on content.
    Uses simple hashing to create pseudo-embeddings that cluster similar content.
    """
    import hashlib

    # Create base embedding from content hash
    content_hash = hashlib.sha256(content.encode()).hexdigest()
    base = [int(content_hash[i : i + 2], 16) / 255.0 for i in range(0, 64, 2)]

    # Add topic-based components for semantic clustering
    topic_vectors = {
        "python": [0.9, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "javascript": [0.8, 0.2, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "typescript": [0.8, 0.2, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0],
        "rust": [0.7, 0.0, 0.3, 0.0, 0.0, 0.0, 0.0, 0.0],
        "go": [0.7, 0.0, 0.0, 0.3, 0.0, 0.0, 0.0, 0.0],
        "testing": [0.0, 0.0, 0.0, 0.0, 0.9, 0.1, 0.0, 0.0],
        "database": [0.0, 0.0, 0.0, 0.0, 0.0, 0.9, 0.1, 0.0],
        "architecture": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.9, 0.1],
        "git": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.1, 0.9],
        "types": [0.5, 0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "memory": [0.0, 0.0, 0.5, 0.0, 0.0, 0.0, 0.0, 0.0],
        "concurrency": [0.0, 0.0, 0.0, 0.5, 0.0, 0.0, 0.0, 0.0],
    }

    # Check for topic keywords in content
    content_lower = content.lower()
    topic_component = [0.0] * 8
    for topic, vec in topic_vectors.items():
        if topic in content_lower:
            topic_component = [max(a, b) for a, b in zip(topic_component, vec, strict=False)]

    # Combine base and topic embeddings, pad to 1536 dimensions
    combined = base + topic_component
    # Pad with zeros to reach 1536 dimensions
    embedding = combined + [0.0] * (1536 - len(combined))

    # Normalize
    norm = sum(x * x for x in embedding) ** 0.5
    if norm > 0:
        embedding = [x / norm for x in embedding]

    return embedding


@pytest.fixture
def benchmark_db(tmp_path):
    """Create a test database with migrations."""
    database = LocalDatabase(tmp_path / "benchmark.db")
    run_migrations(database)
    yield database
    database.close()


@pytest.fixture
def memory_manager(benchmark_db):
    """Create memory manager with semantic search enabled."""
    config = MemoryConfig(semantic_search_enabled=True)
    return MemoryManager(benchmark_db, config, openai_api_key="test-key")


@pytest.fixture
async def populated_manager(memory_manager):
    """Create and populate memory manager with test corpus and embeddings."""
    # Insert test memories
    memories = []
    for mem_data in TEST_MEMORIES:
        memory = await memory_manager.remember(
            content=mem_data["content"],
            memory_type=mem_data["type"],
            importance=0.7,
        )
        memories.append(memory)

    # Generate mock embeddings for all memories
    with patch.object(
        memory_manager.semantic_search, "embed_text", new_callable=AsyncMock
    ) as mock_embed:
        # Set up mock to return deterministic embeddings
        async def mock_embed_fn(text):
            return create_mock_embedding(text)

        mock_embed.side_effect = mock_embed_fn

        # Embed all memories
        for i, memory in enumerate(memories):
            embedding = create_mock_embedding(TEST_MEMORIES[i]["content"])
            memory_manager.semantic_search.store_embedding(memory.id, embedding)

    return memory_manager, memories


class TestSearchBenchmark:
    """Benchmark tests comparing semantic and text search."""

    @pytest.mark.asyncio
    async def test_text_search_latency(self, populated_manager):
        """Measure text search latency across all queries."""
        manager, _ = populated_manager
        latencies = []

        for query_data in TEST_QUERIES:
            start = time.perf_counter()
            manager.storage.search_memories(
                query_text=query_data["query"],
                limit=5,
            )
            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies.append(elapsed_ms)

        avg_latency = statistics.mean(latencies)
        max_latency = max(latencies)
        min_latency = min(latencies)

        print("\n=== Text Search Latency ===")
        print(f"  Average: {avg_latency:.3f} ms")
        print(f"  Min: {min_latency:.3f} ms")
        print(f"  Max: {max_latency:.3f} ms")
        print(f"  Queries: {len(latencies)}")

        # Text search should be very fast (< 10ms typically)
        assert avg_latency < 100, f"Text search too slow: {avg_latency:.3f} ms"

    @pytest.mark.asyncio
    async def test_semantic_search_latency(self, populated_manager):
        """Measure semantic search latency across all queries (mocked embeddings)."""
        manager, _ = populated_manager
        latencies = []

        with patch.object(
            manager.semantic_search, "embed_text", new_callable=AsyncMock
        ) as mock_embed:

            async def mock_embed_fn(text):
                return create_mock_embedding(text)

            mock_embed.side_effect = mock_embed_fn

            for query_data in TEST_QUERIES:
                start = time.perf_counter()
                await manager.semantic_search.search(
                    query=query_data["query"],
                    top_k=5,
                )
                elapsed_ms = (time.perf_counter() - start) * 1000
                latencies.append(elapsed_ms)

        avg_latency = statistics.mean(latencies)
        max_latency = max(latencies)
        min_latency = min(latencies)

        print("\n=== Semantic Search Latency (mocked embedding) ===")
        print(f"  Average: {avg_latency:.3f} ms")
        print(f"  Min: {min_latency:.3f} ms")
        print(f"  Max: {max_latency:.3f} ms")
        print(f"  Queries: {len(latencies)}")
        print("  Note: Real latency includes ~100-500ms API call for embedding")

        # Mocked semantic search should be reasonably fast
        assert avg_latency < 500, f"Semantic search too slow: {avg_latency:.3f} ms"

    @pytest.mark.asyncio
    async def test_text_search_accuracy(self, populated_manager):
        """Measure text search precision and recall."""
        manager, memories = populated_manager

        precision_scores = []
        recall_scores = []

        for query_data in TEST_QUERIES:
            results = manager.storage.search_memories(
                query_text=query_data["query"],
                limit=5,
            )

            result_indices = []
            for result in results:
                for i, memory in enumerate(memories):
                    if result.id == memory.id:
                        result_indices.append(i)
                        break

            expected = set(query_data["expected_indices"])
            retrieved = set(result_indices)

            # Precision: correct results / total retrieved
            if retrieved:
                precision = len(expected & retrieved) / len(retrieved)
            else:
                precision = 0.0

            # Recall: correct results / total expected
            if expected:
                recall = len(expected & retrieved) / len(expected)
            else:
                recall = 1.0

            precision_scores.append(precision)
            recall_scores.append(recall)

        avg_precision = statistics.mean(precision_scores)
        avg_recall = statistics.mean(recall_scores)

        print("\n=== Text Search Accuracy ===")
        print(f"  Average Precision: {avg_precision:.2%}")
        print(f"  Average Recall: {avg_recall:.2%}")
        print(f"  Queries tested: {len(TEST_QUERIES)}")

        # Store for comparison
        return {"precision": avg_precision, "recall": avg_recall}

    @pytest.mark.asyncio
    async def test_semantic_search_accuracy(self, populated_manager):
        """Measure semantic search precision and recall."""
        manager, memories = populated_manager

        precision_scores = []
        recall_scores = []

        with patch.object(
            manager.semantic_search, "embed_text", new_callable=AsyncMock
        ) as mock_embed:

            async def mock_embed_fn(text):
                return create_mock_embedding(text)

            mock_embed.side_effect = mock_embed_fn

            for query_data in TEST_QUERIES:
                results = await manager.semantic_search.search(
                    query=query_data["query"],
                    top_k=5,
                )

                result_indices = []
                for result in results:
                    for i, memory in enumerate(memories):
                        if result.memory.id == memory.id:
                            result_indices.append(i)
                            break

                expected = set(query_data["expected_indices"])
                retrieved = set(result_indices)

                # Precision: correct results / total retrieved
                if retrieved:
                    precision = len(expected & retrieved) / len(retrieved)
                else:
                    precision = 0.0

                # Recall: correct results / total expected
                if expected:
                    recall = len(expected & retrieved) / len(expected)
                else:
                    recall = 1.0

                precision_scores.append(precision)
                recall_scores.append(recall)

        avg_precision = statistics.mean(precision_scores)
        avg_recall = statistics.mean(recall_scores)

        print("\n=== Semantic Search Accuracy ===")
        print(f"  Average Precision: {avg_precision:.2%}")
        print(f"  Average Recall: {avg_recall:.2%}")
        print(f"  Queries tested: {len(TEST_QUERIES)}")

        # Store for comparison
        return {"precision": avg_precision, "recall": avg_recall}

    @pytest.mark.asyncio
    async def test_benchmark_summary(self, populated_manager):
        """Run complete benchmark and print summary comparison."""
        manager, memories = populated_manager

        results: dict[str, dict[str, Any]] = {
            "text": {"latencies": [], "precision": [], "recall": []},
            "semantic": {"latencies": [], "precision": [], "recall": []},
        }

        # Mock embedding for semantic search
        with patch.object(
            manager.semantic_search, "embed_text", new_callable=AsyncMock
        ) as mock_embed:

            async def mock_embed_fn(text):
                return create_mock_embedding(text)

            mock_embed.side_effect = mock_embed_fn

            for query_data in TEST_QUERIES:
                expected = set(query_data["expected_indices"])

                # Text search
                start = time.perf_counter()
                text_results = manager.storage.search_memories(
                    query_text=query_data["query"],
                    limit=5,
                )
                results["text"]["latencies"].append((time.perf_counter() - start) * 1000)

                text_indices = set()
                for result in text_results:
                    for i, memory in enumerate(memories):
                        if result.id == memory.id:
                            text_indices.add(i)
                            break

                if text_indices:
                    results["text"]["precision"].append(
                        len(expected & text_indices) / len(text_indices)
                    )
                else:
                    results["text"]["precision"].append(0.0)
                if expected:
                    results["text"]["recall"].append(len(expected & text_indices) / len(expected))
                else:
                    results["text"]["recall"].append(1.0)

                # Semantic search
                start = time.perf_counter()
                semantic_results = await manager.semantic_search.search(
                    query=query_data["query"],
                    top_k=5,
                )
                results["semantic"]["latencies"].append((time.perf_counter() - start) * 1000)

                semantic_indices = set()
                for result in semantic_results:
                    for i, memory in enumerate(memories):
                        if result.memory.id == memory.id:
                            semantic_indices.add(i)
                            break

                if semantic_indices:
                    results["semantic"]["precision"].append(
                        len(expected & semantic_indices) / len(semantic_indices)
                    )
                else:
                    results["semantic"]["precision"].append(0.0)
                if expected:
                    results["semantic"]["recall"].append(
                        len(expected & semantic_indices) / len(expected)
                    )
                else:
                    results["semantic"]["recall"].append(1.0)

        # Print summary
        print("\n" + "=" * 60)
        print("BENCHMARK SUMMARY: Semantic vs Text Search")
        print("=" * 60)
        print(f"\nDataset: {len(TEST_MEMORIES)} memories, {len(TEST_QUERIES)} queries")
        print("\n" + "-" * 60)
        print(f"{'Metric':<25} {'Text Search':<15} {'Semantic Search':<15}")
        print("-" * 60)

        text_latency = statistics.mean(results["text"]["latencies"])
        semantic_latency = statistics.mean(results["semantic"]["latencies"])
        print(f"{'Avg Latency (ms)':<25} {text_latency:<15.3f} {semantic_latency:<15.3f}")

        text_precision = statistics.mean(results["text"]["precision"])
        semantic_precision = statistics.mean(results["semantic"]["precision"])
        print(f"{'Avg Precision':<25} {text_precision:<15.2%} {semantic_precision:<15.2%}")

        text_recall = statistics.mean(results["text"]["recall"])
        semantic_recall = statistics.mean(results["semantic"]["recall"])
        print(f"{'Avg Recall':<25} {text_recall:<15.2%} {semantic_recall:<15.2%}")

        print("-" * 60)
        print("\nNotes:")
        print("  - Semantic search latency excludes API embedding time (~100-500ms)")
        print("  - Text search uses SQL LIKE substring matching")
        print("  - Semantic search uses cosine similarity on embeddings")
        print("  - Higher precision = fewer irrelevant results")
        print("  - Higher recall = finds more relevant results")
        print("=" * 60)

        # Assertions to ensure tests provide meaningful results
        assert len(results["text"]["latencies"]) == len(TEST_QUERIES)
        assert len(results["semantic"]["latencies"]) == len(TEST_QUERIES)
