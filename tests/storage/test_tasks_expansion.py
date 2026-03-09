import pytest

from gobby.storage.database import LocalDatabase
from gobby.storage.migrations import run_migrations
from gobby.storage.tasks import LocalTaskManager

pytestmark = pytest.mark.unit


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test.db"
    return path


@pytest.fixture
def db(db_path):
    database = LocalDatabase(str(db_path))
    run_migrations(database)
    with database.transaction() as conn:
        conn.execute("INSERT INTO projects (id, name) VALUES (?, ?)", ("p1", "test_project"))
    return database


@pytest.fixture
def manager(db):
    return LocalTaskManager(db)


@pytest.mark.slow
@pytest.mark.integration
@pytest.mark.e2e
def test_create_task_with_expansion_fields(manager):
    task = manager.create_task(
        project_id="p1",
        title="Test Expansion",
        description="Rich details here",
        category="Unit tests",
        expansion_context='{"foo": "bar"}',
    )

    assert task.description == "Rich details here"
    assert task.category == "Unit tests"
    assert task.expansion_context == '{"foo": "bar"}'

    # Verify persistence
    fetched = manager.get_task(task.id)
    assert fetched.description == "Rich details here"
    assert fetched.expansion_context == '{"foo": "bar"}'


@pytest.mark.slow
@pytest.mark.integration
@pytest.mark.e2e
def test_update_task_expansion_fields(manager):
    task = manager.create_task(project_id="p1", title="Update Me")
    assert task.description is None

    updated = manager.update_task(task.id, description="Updated details")

    assert updated.description == "Updated details"

    fetched = manager.get_task(task.id)
    assert fetched.description == "Updated details"


@pytest.mark.slow
@pytest.mark.integration
@pytest.mark.e2e
def test_to_dict_includes_expansion_fields(manager):
    task = manager.create_task(project_id="p1", title="Dict Test", description="Secret details")

    d = task.to_dict()
    assert d["description"] == "Secret details"
    assert "expansion_context" in d
