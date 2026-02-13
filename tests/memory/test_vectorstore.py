"""Tests for VectorStore (Qdrant-based vector storage).

Phase 1: Verify qdrant-client dependency is available.
Full VectorStore tests will be added in task #8241.
"""


def test_qdrant_client_importable() -> None:
    """qdrant-client package should be importable after dependency addition."""
    import qdrant_client  # noqa: F401

    assert hasattr(qdrant_client, "QdrantClient")
