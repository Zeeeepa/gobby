"""Tests for path_cache auto-computation on task insert.

These tests verify that when a new task is created:
1. Its seq_num is assigned (tested in test_task_seq_num.py)
2. Its path_cache is computed and stored automatically
3. The path_cache correctly reflects the task's hierarchy
"""

import pytest

from gobby.storage.tasks import LocalTaskManager


@pytest.fixture
def task_manager(temp_db):
    """Create a LocalTaskManager with a temporary database."""
    return LocalTaskManager(temp_db)


@pytest.fixture
def project_id(sample_project):
    """Get the project ID from the sample project fixture."""
    return sample_project["id"]


@pytest.mark.integration
class TestPathCacheOnInsert:
    """Test path_cache is computed and stored when tasks are inserted."""

    def test_root_task_gets_path_cache_on_insert(self, task_manager, project_id):
        """Test that a root task gets path_cache computed immediately on insert."""
        task = task_manager.create_task(project_id=project_id, title="Root Task")

        # Path should be the task's seq_num (which is 1 for first task)
        assert task.path_cache == "1"

    def test_second_root_task_gets_correct_path(self, task_manager, project_id):
        """Test second root task gets its seq_num as path."""
        task1 = task_manager.create_task(project_id=project_id, title="Task 1")
        task2 = task_manager.create_task(project_id=project_id, title="Task 2")

        assert task1.path_cache == "1"
        assert task2.path_cache == "2"

    def test_child_task_gets_hierarchical_path(self, task_manager, project_id):
        """Test that a child task gets parent.child path on insert."""
        parent = task_manager.create_task(project_id=project_id, title="Parent")
        child = task_manager.create_task(
            project_id=project_id, title="Child", parent_task_id=parent.id
        )

        # Parent is seq 1, child is seq 2
        assert parent.path_cache == "1"
        assert child.path_cache == "1.2"

    def test_grandchild_task_gets_deep_path(self, task_manager, project_id):
        """Test path computation for deeply nested tasks."""
        root = task_manager.create_task(project_id=project_id, title="Root")
        child = task_manager.create_task(
            project_id=project_id, title="Child", parent_task_id=root.id
        )
        grandchild = task_manager.create_task(
            project_id=project_id, title="Grandchild", parent_task_id=child.id
        )

        assert root.path_cache == "1"
        assert child.path_cache == "1.2"
        assert grandchild.path_cache == "1.2.3"

    def test_sibling_tasks_have_distinct_paths(self, task_manager, project_id):
        """Test that sibling tasks have distinct paths."""
        parent = task_manager.create_task(project_id=project_id, title="Parent")
        child1 = task_manager.create_task(
            project_id=project_id, title="Child 1", parent_task_id=parent.id
        )
        child2 = task_manager.create_task(
            project_id=project_id, title="Child 2", parent_task_id=parent.id
        )

        assert parent.path_cache == "1"
        assert child1.path_cache == "1.2"
        assert child2.path_cache == "1.3"

    def test_path_cache_preserved_in_database(self, task_manager, project_id, temp_db):
        """Test that path_cache is stored in database and retrievable."""
        task = task_manager.create_task(project_id=project_id, title="Task")
        task_id = task.id

        # Retrieve directly from database
        row = temp_db.fetchone("SELECT path_cache FROM tasks WHERE id = ?", (task_id,))
        assert row["path_cache"] == "1"

        # Retrieve via get_task
        retrieved = task_manager.get_task(task_id)
        assert retrieved.path_cache == "1"

    def test_path_cache_in_to_dict(self, task_manager, project_id):
        """Test that path_cache is included in to_dict() output."""
        task = task_manager.create_task(project_id=project_id, title="Task")
        data = task.to_dict()

        assert "path_cache" in data
        assert data["path_cache"] == "1"

    def test_path_cache_in_to_brief(self, task_manager, project_id):
        """Test that path_cache is included in to_brief() output."""
        task = task_manager.create_task(project_id=project_id, title="Task")
        brief = task.to_brief()

        assert "path_cache" in brief
        assert brief["path_cache"] == "1"

    def test_complex_hierarchy_paths(self, task_manager, project_id):
        """Test path computation in a complex hierarchy."""
        # Create:
        #   task1 (seq 1)
        #   task2 (seq 2)
        #     task2a (seq 3)
        #     task2b (seq 4)
        #       task2b1 (seq 5)
        #   task3 (seq 6)

        task1 = task_manager.create_task(project_id=project_id, title="Task 1")
        task2 = task_manager.create_task(project_id=project_id, title="Task 2")
        task2a = task_manager.create_task(
            project_id=project_id, title="Task 2a", parent_task_id=task2.id
        )
        task2b = task_manager.create_task(
            project_id=project_id, title="Task 2b", parent_task_id=task2.id
        )
        task2b1 = task_manager.create_task(
            project_id=project_id, title="Task 2b1", parent_task_id=task2b.id
        )
        task3 = task_manager.create_task(project_id=project_id, title="Task 3")

        assert task1.path_cache == "1"
        assert task2.path_cache == "2"
        assert task2a.path_cache == "2.3"
        assert task2b.path_cache == "2.4"
        assert task2b1.path_cache == "2.4.5"
        assert task3.path_cache == "6"

    def test_multiple_projects_independent_paths(self, task_manager, temp_db):
        """Test that each project has independent path sequences."""
        # Create two projects
        temp_db.execute(
            "INSERT INTO projects (id, name, created_at, updated_at) VALUES (?, ?, datetime('now'), datetime('now'))",
            ("proj-a", "Project A"),
        )
        temp_db.execute(
            "INSERT INTO projects (id, name, created_at, updated_at) VALUES (?, ?, datetime('now'), datetime('now'))",
            ("proj-b", "Project B"),
        )

        # Create tasks in each project
        task_a1 = task_manager.create_task(project_id="proj-a", title="A1")
        task_a2 = task_manager.create_task(project_id="proj-a", title="A2")
        task_b1 = task_manager.create_task(project_id="proj-b", title="B1")

        # Each project starts fresh with seq 1
        assert task_a1.path_cache == "1"
        assert task_a2.path_cache == "2"
        assert task_b1.path_cache == "1"  # Independent from project A
