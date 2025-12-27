import json
import time
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from gobby.sync.tasks import TaskSyncManager
from gobby.storage.tasks import LocalTaskManager


@pytest.fixture
def sync_manager(temp_db, tmp_path):
    export_path = tmp_path / ".gobby" / "tasks.jsonl"
    task_manager = LocalTaskManager(temp_db)
    return TaskSyncManager(task_manager, str(export_path))


@pytest.fixture
def task_manager(temp_db):
    return LocalTaskManager(temp_db)


class TestTaskSyncManager:
    def test_export_to_jsonl(self, sync_manager, task_manager, sample_project):
        # Create tasks
        t1 = task_manager.create_task(sample_project["id"], "Task 1")
        t2 = task_manager.create_task(sample_project["id"], "Task 2")

        # Add dependency: Task 2 depends on Task 1
        # task_id = t2.id (the one with dependency), depends_on = t1.id (the dependency)
        # Note: In schema, unique constraint includes dep_type
        now = "2023-01-01T00:00:00"
        sync_manager.db.execute(
            "INSERT INTO task_dependencies (task_id, depends_on, dep_type, created_at) VALUES (?, ?, ?, ?)",
            (t2.id, t1.id, "blocking", now),
        )

        sync_manager.export_to_jsonl()

        assert sync_manager.export_path.exists()

        lines = sync_manager.export_path.read_text().strip().split("\n")
        assert len(lines) == 2

        data = [json.loads(line) for line in lines]

        # Verify Task 1
        task1_data = next(d for d in data if d["id"] == t1.id)
        assert task1_data["title"] == "Task 1"
        assert task1_data["deps_on"] == []

        # Verify Task 2
        task2_data = next(d for d in data if d["id"] == t2.id)
        assert task2_data["title"] == "Task 2"
        assert task2_data["deps_on"] == [t1.id]

    def test_trigger_export_debounced(self, sync_manager):
        # Mock export_to_jsonl
        # We need to patch the method on the instance or class
        # Using a safer approach with a mock side_effect check in a real scenario would be better,
        # but for threading, we just want to ensure it runs eventually.

        # Reduce interval for test
        sync_manager._debounce_interval = 0.1

        with patch.object(sync_manager, "export_to_jsonl") as mock_export:
            sync_manager.trigger_export()
            sync_manager.trigger_export()
            sync_manager.trigger_export()

            assert mock_export.call_count == 0

            time.sleep(0.2)

            assert mock_export.call_count == 1

        sync_manager.stop()

    def test_mutation_triggers_export(self, task_manager, tmp_path, sample_project):
        """Test that task mutations trigger export."""
        export_path = tmp_path / "tasks.jsonl"
        sync_manager = TaskSyncManager(task_manager, str(export_path))

        # Mock trigger_export to verify call
        sync_manager.trigger_export = MagicMock()

        # Wire up listener
        task_manager.add_change_listener(sync_manager.trigger_export)

        # Create task -> should trigger
        task = task_manager.create_task(sample_project["id"], "Task 1")
        assert sync_manager.trigger_export.call_count == 1

        # Update task -> should trigger
        task_manager.update_task(task.id, title="Updated Task 1")
        assert sync_manager.trigger_export.call_count == 2

        # Close task -> should trigger
        task_manager.close_task(task.id)
        assert sync_manager.trigger_export.call_count == 3

        # Delete task -> should trigger
        # Delete task -> should trigger
        task_manager.delete_task(task.id)
        assert sync_manager.trigger_export.call_count == 4

    def test_import_from_jsonl(self, sync_manager, task_manager, sample_project):
        """Test importing tasks from JSONL."""
        # Create JSONL file content
        now = "2023-01-02T00:00:00+00:00"
        later = "2023-01-03T00:00:00+00:00"

        tasks_data = [
            {
                "id": "task-imported-1",
                "title": "Imported Task",
                "description": "Desc",
                "status": "todo",
                "created_at": now,
                "updated_at": now,
                "project_id": sample_project["id"],
                "parent_id": None,
                "deps_on": [],
            },
            {
                "id": "task-imported-2",
                "title": "Imported Task with Dep",
                "description": "Desc",
                "status": "todo",
                "created_at": now,
                "updated_at": later,
                "project_id": sample_project["id"],
                "parent_id": None,
                "deps_on": ["task-imported-1"],
            },
        ]

        # Write export file
        sync_manager.export_path.parent.mkdir(parents=True, exist_ok=True)
        with open(sync_manager.export_path, "w") as f:
            for task in tasks_data:
                f.write(json.dumps(task) + "\n")

        # Run import
        sync_manager.import_from_jsonl()

        # Verify tasks in DB
        t1 = task_manager.get_task("task-imported-1")
        assert t1 is not None
        assert t1.title == "Imported Task"

        t2 = task_manager.get_task("task-imported-2")
        assert t2 is not None
        assert t2.title == "Imported Task with Dep"

        # Verify Dependency
        deps = task_manager.db.fetchall(
            "SELECT * FROM task_dependencies WHERE task_id = ?", (t2.id,)
        )
        assert len(deps) == 1
        assert deps[0]["depends_on"] == t1.id

    def test_import_conflict_resolution(self, sync_manager, task_manager, sample_project):
        """Test LWW conflict resolution during import."""
        # 1. Local Task is NEWER (should keep local)
        t1 = task_manager.create_task(sample_project["id"], "Local Newer")
        # Force updated_at to future
        future = "2025-01-01T00:00:00+00:00"
        task_manager.db.execute("UPDATE tasks SET updated_at = ? WHERE id = ?", (future, t1.id))

        # File has older version
        past = "2020-01-01T00:00:00+00:00"
        file_data = {
            "id": t1.id,
            "title": "File Older",
            "description": "",
            "status": "todo",
            "created_at": past,
            "updated_at": past,
            "project_id": sample_project["id"],
            "parent_id": None,
        }

        # Write file
        sync_manager.export_path.parent.mkdir(parents=True, exist_ok=True)
        with open(sync_manager.export_path, "w") as f:
            f.write(json.dumps(file_data) + "\n")

        sync_manager.import_from_jsonl()

        # Verify DB unchanged
        t1_fresh = task_manager.get_task(t1.id)
        assert t1_fresh.title == "Local Newer"

        # 2. File is NEWER (should overwrite local)
        t2 = task_manager.create_task(sample_project["id"], "Local Older")
        task_manager.db.execute("UPDATE tasks SET updated_at = ? WHERE id = ?", (past, t2.id))

        file_data_2 = {
            "id": t2.id,
            "title": "File Newer",
            "description": "",
            "status": "todo",
            "created_at": past,
            "updated_at": future,
            "project_id": sample_project["id"],
            "parent_id": None,
        }

        # Append to file
        with open(sync_manager.export_path, "w") as f:
            f.write(json.dumps(file_data_2) + "\n")

        sync_manager.import_from_jsonl()

        # Verify DB updated
        t2_fresh = task_manager.get_task(t2.id)
        assert t2_fresh.title == "File Newer"
