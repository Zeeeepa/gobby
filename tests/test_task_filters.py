import pytest
from gobby.storage.tasks import LocalTaskManager
from gobby.storage.database import LocalDatabase


@pytest.fixture
def task_manager():
    db = LocalDatabase(":memory:")
    # Initialize schema
    with db.transaction() as conn:
        conn.execute("""
            CREATE TABLE tasks (
                id TEXT PRIMARY KEY,
                project_id TEXT,
                title TEXT,
                description TEXT,
                parent_task_id TEXT,
                discovered_in_session_id TEXT,
                priority INTEGER,
                type TEXT,
                assignee TEXT,
                labels TEXT, -- JSON list
                status TEXT,
                created_at TEXT,
                updated_at TEXT,
                closed_reason TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE task_dependencies (
                task_id TEXT,
                depends_on TEXT,
                dep_type TEXT,
                created_at TEXT,
                PRIMARY KEY (task_id, depends_on)
            )
        """)
    return LocalTaskManager(db)


def test_list_tasks_filter_by_type(task_manager):
    task_manager.create_task("p1", "Task 1", task_type="bug")
    task_manager.create_task("p1", "Task 2", task_type="feature")
    task_manager.create_task("p1", "Task 3", task_type="bug")

    bugs = task_manager.list_tasks(task_type="bug")
    assert len(bugs) == 2
    assert all(t.task_type == "bug" for t in bugs)

    features = task_manager.list_tasks(task_type="feature")
    assert len(features) == 1
    assert features[0].title == "Task 2"


def test_list_tasks_filter_by_label(task_manager):
    task_manager.create_task("p1", "Task 1", labels=["frontend", "urgent"])
    task_manager.create_task("p1", "Task 2", labels=["backend"])
    task_manager.create_task("p1", "Task 3", labels=["frontend", "bug"])

    frontend_tasks = task_manager.list_tasks(label="frontend")
    assert len(frontend_tasks) == 2
    titles = {t.title for t in frontend_tasks}
    assert "Task 1" in titles
    assert "Task 3" in titles

    urgent_tasks = task_manager.list_tasks(label="urgent")
    assert len(urgent_tasks) == 1
    assert urgent_tasks[0].title == "Task 1"


def test_list_ready_tasks_filter_by_type(task_manager):
    # Setup: Task 1 (bug) blocks Task 2 (feature). Task 3 (bug) is independent.
    t1 = task_manager.create_task("p1", "Task 1", task_type="bug")
    t2 = task_manager.create_task("p1", "Task 2", task_type="feature")
    t3 = task_manager.create_task("p1", "Task 3", task_type="bug")

    with task_manager.db.transaction() as conn:
        conn.execute(
            "INSERT INTO task_dependencies (task_id, depends_on, dep_type) VALUES (?, ?, ?)",
            (t2.id, t1.id, "blocks"),
        )

    # Ready tasks should be T1 and T3. T2 is blocked.
    # Filter by task_type=bug -> T1, T3
    ready_bugs = task_manager.list_ready_tasks(task_type="bug")
    assert len(ready_bugs) == 2
    ids = {t.id for t in ready_bugs}
    assert t1.id in ids
    assert t3.id in ids

    # Filter by task_type=feature -> Empty (T2 is feature but blocked)
    ready_features = task_manager.list_ready_tasks(task_type="feature")
    assert len(ready_features) == 0

    # Close T1 to unblock T2
    task_manager.close_task(t1.id)

    # Now T2 is ready
    ready_features_after = task_manager.list_ready_tasks(task_type="feature")
    assert len(ready_features_after) == 1
    assert ready_features_after[0].id == t2.id
