"""Tests for memory embedding persistence layer."""

import struct

import pytest

from gobby.storage.database import LocalDatabase
from gobby.storage.memory_embeddings import MemoryEmbedding, MemoryEmbeddingManager
from gobby.storage.migrations import run_migrations

pytestmark = pytest.mark.unit


def _make_embedding(dim: int = 4) -> list[float]:
    """Create a simple test embedding vector."""
    return [float(i) / dim for i in range(dim)]


def _setup_db(tmp_path, name: str = "test.db") -> LocalDatabase:
    """Create a fresh database with migrations applied."""
    db_path = tmp_path / name
    db = LocalDatabase(db_path)
    run_migrations(db)
    return db


def _create_project_and_memory(
    db: LocalDatabase,
    project_id: str = "test-project",
    memory_id: str = "mem-1",
    content: str = "User prefers dark mode",
) -> None:
    """Create prerequisite project and memory records."""
    db.execute(
        "INSERT OR IGNORE INTO projects (id, name, created_at, updated_at) "
        "VALUES (?, ?, datetime('now'), datetime('now'))",
        (project_id, f"Project {project_id}"),
    )
    db.execute(
        "INSERT INTO memories (id, project_id, memory_type, content, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))",
        (memory_id, project_id, "fact", content),
    )


# =============================================================================
# store_embedding / get_embedding
# =============================================================================


def test_store_and_get_embedding(tmp_path) -> None:
    """Test storing an embedding and retrieving it by memory_id."""
    db = _setup_db(tmp_path)
    mgr = MemoryEmbeddingManager(db)
    _create_project_and_memory(db)

    embedding = _make_embedding(4)
    result = mgr.store_embedding(
        memory_id="mem-1",
        project_id="test-project",
        embedding=embedding,
        embedding_model="text-embedding-3-small",
        text_hash="abc123",
    )

    assert result is not None
    assert isinstance(result, MemoryEmbedding)
    assert result.memory_id == "mem-1"
    assert result.project_id == "test-project"
    assert result.embedding == embedding
    assert result.embedding_model == "text-embedding-3-small"
    assert result.embedding_dim == 4
    assert result.text_hash == "abc123"
    assert result.created_at is not None
    assert result.updated_at is not None


def test_get_embedding_returns_none_for_missing(tmp_path) -> None:
    """Test that get_embedding returns None for a non-existent memory_id."""
    db = _setup_db(tmp_path)
    mgr = MemoryEmbeddingManager(db)

    assert mgr.get_embedding("nonexistent") is None


def test_store_embedding_upserts_on_conflict(tmp_path) -> None:
    """Test that storing an embedding for the same memory_id updates it."""
    db = _setup_db(tmp_path)
    mgr = MemoryEmbeddingManager(db)
    _create_project_and_memory(db)

    embedding_v1 = _make_embedding(4)
    mgr.store_embedding(
        memory_id="mem-1",
        project_id="test-project",
        embedding=embedding_v1,
        embedding_model="text-embedding-3-small",
        text_hash="hash_v1",
    )

    embedding_v2 = [9.0, 8.0, 7.0, 6.0]
    result = mgr.store_embedding(
        memory_id="mem-1",
        project_id="test-project",
        embedding=embedding_v2,
        embedding_model="text-embedding-3-large",
        text_hash="hash_v2",
    )

    assert result.embedding == embedding_v2
    assert result.embedding_model == "text-embedding-3-large"
    assert result.text_hash == "hash_v2"

    # Should still be only one row
    rows = db.fetchall("SELECT * FROM memory_embeddings WHERE memory_id = ?", ("mem-1",))
    assert len(rows) == 1


# =============================================================================
# delete_embedding
# =============================================================================


def test_delete_embedding(tmp_path) -> None:
    """Test deleting an embedding by memory_id."""
    db = _setup_db(tmp_path)
    mgr = MemoryEmbeddingManager(db)
    _create_project_and_memory(db)

    mgr.store_embedding(
        memory_id="mem-1",
        project_id="test-project",
        embedding=_make_embedding(),
        embedding_model="text-embedding-3-small",
        text_hash="abc",
    )

    assert mgr.delete_embedding("mem-1") is True
    assert mgr.get_embedding("mem-1") is None


def test_delete_embedding_returns_false_for_missing(tmp_path) -> None:
    """Test that deleting a non-existent embedding returns False."""
    db = _setup_db(tmp_path)
    mgr = MemoryEmbeddingManager(db)

    assert mgr.delete_embedding("nonexistent") is False


def test_cascade_delete_from_memory(tmp_path) -> None:
    """Test that deleting a memory cascades to its embedding."""
    db = _setup_db(tmp_path)
    mgr = MemoryEmbeddingManager(db)
    _create_project_and_memory(db)

    db.execute("PRAGMA foreign_keys = ON")

    mgr.store_embedding(
        memory_id="mem-1",
        project_id="test-project",
        embedding=_make_embedding(),
        embedding_model="text-embedding-3-small",
        text_hash="abc",
    )

    # Delete the memory itself
    db.execute("DELETE FROM memories WHERE id = ?", ("mem-1",))

    # Embedding should be gone via FK cascade
    assert mgr.get_embedding("mem-1") is None


# =============================================================================
# get_embeddings_by_project
# =============================================================================


def test_get_embeddings_by_project(tmp_path) -> None:
    """Test filtering embeddings by project_id."""
    db = _setup_db(tmp_path)
    mgr = MemoryEmbeddingManager(db)

    _create_project_and_memory(db, "proj-a", "mem-a1", "Memory A1")
    _create_project_and_memory(db, "proj-a", "mem-a2", "Memory A2")
    _create_project_and_memory(db, "proj-b", "mem-b1", "Memory B1")

    mgr.store_embedding("mem-a1", "proj-a", _make_embedding(), "model", "h1")
    mgr.store_embedding("mem-a2", "proj-a", _make_embedding(), "model", "h2")
    mgr.store_embedding("mem-b1", "proj-b", _make_embedding(), "model", "h3")

    results_a = mgr.get_embeddings_by_project("proj-a")
    assert len(results_a) == 2
    assert all(e.project_id == "proj-a" for e in results_a)

    results_b = mgr.get_embeddings_by_project("proj-b")
    assert len(results_b) == 1
    assert results_b[0].memory_id == "mem-b1"


def test_get_embeddings_by_project_empty(tmp_path) -> None:
    """Test that get_embeddings_by_project returns empty list for no matches."""
    db = _setup_db(tmp_path)
    mgr = MemoryEmbeddingManager(db)

    assert mgr.get_embeddings_by_project("nonexistent") == []


# =============================================================================
# get_all_embeddings
# =============================================================================


def test_get_all_embeddings(tmp_path) -> None:
    """Test retrieving all embeddings."""
    db = _setup_db(tmp_path)
    mgr = MemoryEmbeddingManager(db)

    _create_project_and_memory(db, "proj-a", "mem-1", "Content 1")
    _create_project_and_memory(db, "proj-a", "mem-2", "Content 2")

    mgr.store_embedding("mem-1", "proj-a", _make_embedding(), "model", "h1")
    mgr.store_embedding("mem-2", "proj-a", _make_embedding(), "model", "h2")

    results = mgr.get_all_embeddings()
    assert len(results) == 2


# =============================================================================
# get_embeddings_needing_update
# =============================================================================


def test_get_embeddings_needing_update(tmp_path) -> None:
    """Test finding embeddings where text_hash doesn't match current content."""
    db = _setup_db(tmp_path)
    mgr = MemoryEmbeddingManager(db)

    _create_project_and_memory(db, "proj", "mem-1", "Content 1")
    _create_project_and_memory(db, "proj", "mem-2", "Content 2")
    _create_project_and_memory(db, "proj", "mem-3", "Content 3")

    mgr.store_embedding("mem-1", "proj", _make_embedding(), "model", "stale_hash")
    mgr.store_embedding("mem-2", "proj", _make_embedding(), "model", "current_hash")
    mgr.store_embedding("mem-3", "proj", _make_embedding(), "model", "also_stale")

    # Pass current hashes - mem-1 and mem-3 are stale
    current_hashes = {
        "mem-1": "new_hash",
        "mem-2": "current_hash",  # matches
        "mem-3": "different_hash",
    }

    stale = mgr.get_embeddings_needing_update(current_hashes)
    stale_ids = {e.memory_id for e in stale}
    assert stale_ids == {"mem-1", "mem-3"}


# =============================================================================
# batch_store_embeddings
# =============================================================================


def test_batch_store_embeddings(tmp_path) -> None:
    """Test batch storing multiple embeddings at once."""
    db = _setup_db(tmp_path)
    mgr = MemoryEmbeddingManager(db)

    _create_project_and_memory(db, "proj", "mem-1", "Content 1")
    _create_project_and_memory(db, "proj", "mem-2", "Content 2")

    items = [
        {
            "memory_id": "mem-1",
            "project_id": "proj",
            "embedding": _make_embedding(),
            "embedding_model": "model-a",
            "text_hash": "h1",
        },
        {
            "memory_id": "mem-2",
            "project_id": "proj",
            "embedding": _make_embedding(8),
            "embedding_model": "model-b",
            "text_hash": "h2",
        },
    ]

    count = mgr.batch_store_embeddings(items)
    assert count == 2

    e1 = mgr.get_embedding("mem-1")
    assert e1 is not None
    assert e1.embedding_model == "model-a"

    e2 = mgr.get_embedding("mem-2")
    assert e2 is not None
    assert e2.embedding_dim == 8


# =============================================================================
# MemoryEmbedding dataclass
# =============================================================================


def test_memory_embedding_from_row(tmp_path) -> None:
    """Test MemoryEmbedding.from_row deserializes BLOB correctly."""
    db = _setup_db(tmp_path)
    _create_project_and_memory(db)

    embedding = [1.0, 2.0, 3.0]
    blob = struct.pack(f"{len(embedding)}f", *embedding)

    db.execute(
        """INSERT INTO memory_embeddings
           (memory_id, project_id, embedding, embedding_model, embedding_dim, text_hash, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
        ("mem-1", "test-project", blob, "test-model", 3, "testhash"),
    )

    row = db.fetchone("SELECT * FROM memory_embeddings WHERE memory_id = ?", ("mem-1",))
    me = MemoryEmbedding.from_row(row)

    assert me.embedding == pytest.approx(embedding)
    assert me.embedding_dim == 3
    assert me.embedding_model == "test-model"


def test_memory_embedding_to_dict(tmp_path) -> None:
    """Test MemoryEmbedding.to_dict excludes embedding vector."""
    db = _setup_db(tmp_path)
    mgr = MemoryEmbeddingManager(db)
    _create_project_and_memory(db)

    mgr.store_embedding("mem-1", "test-project", _make_embedding(), "model", "hash")

    result = mgr.get_embedding("mem-1")
    d = result.to_dict()

    assert "memory_id" in d
    assert "embedding_model" in d
    assert "embedding" not in d  # excluded for serialization
