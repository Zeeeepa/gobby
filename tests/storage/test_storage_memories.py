import pytest

from gobby.storage.database import LocalDatabase
from gobby.storage.memories import LocalMemoryManager
from gobby.storage.migrations import run_migrations


@pytest.fixture
def db(tmp_path):
    database = LocalDatabase(tmp_path / "gobby.db")
    run_migrations(database)
    yield database
    database.close()


@pytest.fixture
def memory_manager(db):
    return LocalMemoryManager(db)


def test_create_memory(memory_manager):
    memory = memory_manager.create_memory(
        content="Test memory",
        memory_type="fact",
        tags=["test"],
    )
    assert memory.id.startswith("mm-")
    assert memory.content == "Test memory"
    assert memory.memory_type == "fact"
    assert memory.tags == ["test"]
    assert memory.importance == 0.5


def test_get_memory(memory_manager):
    created = memory_manager.create_memory(content="Test get")
    retrieved = memory_manager.get_memory(created.id)
    assert retrieved == created


def test_update_memory(memory_manager):
    created = memory_manager.create_memory(content="Original", importance=0.1)
    updated = memory_manager.update_memory(
        created.id,
        content="Updated",
        importance=0.9,
    )
    assert updated.content == "Updated"
    assert updated.importance == 0.9
    assert updated.updated_at >= created.updated_at


def test_delete_memory(memory_manager):
    created = memory_manager.create_memory(content="To delete")
    assert memory_manager.delete_memory(created.id)
    with pytest.raises(ValueError, match="not found"):
        memory_manager.get_memory(created.id)


def test_list_memories(memory_manager, db):
    # Seed projects for foreign keys
    db.execute("INSERT INTO projects (id, name) VALUES ('p1', 'Project 1')")
    db.execute("INSERT INTO projects (id, name) VALUES ('p2', 'Project 2')")

    memory_manager.create_memory(content="Global", project_id=None, importance=0.8)
    memory_manager.create_memory(content="Project A", project_id="p1", importance=0.5)
    memory_manager.create_memory(content="Project B", project_id="p2", importance=0.2)

    # List all global + project A
    # Wait, implementation logic: (project_id = ? OR project_id IS NULL)

    # 1. List with project_id="p1"
    memories = memory_manager.list_memories(project_id="p1")
    contents = {m.content for m in memories}
    assert "Global" in contents
    assert "Project A" in contents
    assert "Project B" not in contents

    # 2. List global only (if no project_id passed? Filter logic is currently conditional)
    # If project_id is None, query doesn't filter by project_id, so returns all?
    # Logic in manager: "if project_id: ...". So if None, returns all.
    all_memories = memory_manager.list_memories()
    assert len(all_memories) == 3

    # 3. Filter by importance
    high_imp = memory_manager.list_memories(min_importance=0.6)
    assert len(high_imp) == 1
    assert high_imp[0].content == "Global"


def test_search_memories(memory_manager):
    memory_manager.create_memory(content="The quick brown fox")
    memory_manager.create_memory(content="The lazy dog")

    results = memory_manager.search_memories(query_text="fox")
    assert len(results) == 1
    assert results[0].content == "The quick brown fox"

    results = memory_manager.search_memories(query_text="The")
    assert len(results) == 2
