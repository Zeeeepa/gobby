"""Tests for workflow-task integration module."""

import pytest

from gobby.storage.database import LocalDatabase
from gobby.storage.migrations import run_migrations
from gobby.storage.projects import LocalProjectManager
from gobby.storage.tasks import LocalTaskManager
from gobby.workflows.task_actions import (
    get_next_workflow_task,
    get_workflow_tasks,
    mark_workflow_task_complete,
    persist_decomposed_tasks,
    update_task_from_workflow,
)


@pytest.fixture
def db(tmp_path):
    """Create a test database with migrations."""
    db_path = tmp_path / "test.db"
    database = LocalDatabase(db_path)
    run_migrations(database)
    return database


@pytest.fixture
def project_id(db):
    """Create a test project and return its ID."""
    project_manager = LocalProjectManager(db)
    project = project_manager.create(
        name="test-project",
        repo_path="/tmp/test",
    )
    return project.id


class TestPersistDecomposedTasks:
    """Tests for persist_decomposed_tasks function."""

    def test_persist_basic_tasks(self, db, project_id):
        """Test persisting a basic list of tasks."""
        tasks_data = [
            {"id": 1, "title": "First task", "verification": "Check logs"},
            {"id": 2, "title": "Second task", "verification": "Run tests"},
            {"id": 3, "title": "Third task"},
        ]

        id_mapping = persist_decomposed_tasks(
            db=db,
            project_id=project_id,
            tasks_data=tasks_data,
            workflow_name="test-workflow",
        )

        # Should create 3 tasks
        assert len(id_mapping) == 3
        assert "1" in id_mapping
        assert "2" in id_mapping
        assert "3" in id_mapping

        # All IDs should be valid task IDs
        for _original_id, task_id in id_mapping.items():
            assert task_id.startswith("gt-")

    def test_persist_with_description_key(self, db, project_id):
        """Test that 'description' key works as title."""
        tasks_data = [
            {"id": 1, "description": "Task using description key"},
        ]

        id_mapping = persist_decomposed_tasks(
            db=db,
            project_id=project_id,
            tasks_data=tasks_data,
            workflow_name="test-workflow",
        )

        assert len(id_mapping) == 1

        # Verify task was created with correct title
        task_manager = LocalTaskManager(db)
        task = task_manager.get_task(id_mapping["1"])
        assert task.title == "Task using description key"

    def test_persist_sets_workflow_name(self, db, project_id):
        """Test that tasks are created with workflow_name."""
        tasks_data = [{"id": 1, "title": "Test task"}]

        id_mapping = persist_decomposed_tasks(
            db=db,
            project_id=project_id,
            tasks_data=tasks_data,
            workflow_name="my-workflow",
        )

        task_manager = LocalTaskManager(db)
        task = task_manager.get_task(id_mapping["1"])
        assert task.workflow_name == "my-workflow"

    def test_persist_sets_sequence_order(self, db, project_id):
        """Test that tasks get sequence_order based on position."""
        tasks_data = [
            {"id": "a", "title": "First"},
            {"id": "b", "title": "Second"},
            {"id": "c", "title": "Third"},
        ]

        id_mapping = persist_decomposed_tasks(
            db=db,
            project_id=project_id,
            tasks_data=tasks_data,
            workflow_name="test-workflow",
        )

        task_manager = LocalTaskManager(db)
        task_a = task_manager.get_task(id_mapping["a"])
        task_b = task_manager.get_task(id_mapping["b"])
        task_c = task_manager.get_task(id_mapping["c"])

        assert task_a.sequence_order == 0
        assert task_b.sequence_order == 1
        assert task_c.sequence_order == 2

    def test_persist_sets_verification(self, db, project_id):
        """Test that verification field is stored."""
        tasks_data = [
            {"id": 1, "title": "Task", "verification": "Run pytest -v"},
        ]

        id_mapping = persist_decomposed_tasks(
            db=db,
            project_id=project_id,
            tasks_data=tasks_data,
            workflow_name="test-workflow",
        )

        task_manager = LocalTaskManager(db)
        task = task_manager.get_task(id_mapping["1"])
        assert task.verification == "Run pytest -v"

    def test_persist_with_parent_task(self, db, project_id):
        """Test creating tasks under a parent."""
        # Create parent task first
        task_manager = LocalTaskManager(db)
        parent = task_manager.create_task(
            project_id=project_id,
            title="Parent task",
        )

        tasks_data = [
            {"id": 1, "title": "Child 1"},
            {"id": 2, "title": "Child 2"},
        ]

        id_mapping = persist_decomposed_tasks(
            db=db,
            project_id=project_id,
            tasks_data=tasks_data,
            workflow_name="test-workflow",
            parent_task_id=parent.id,
        )

        # Verify children have parent set
        child1 = task_manager.get_task(id_mapping["1"])
        child2 = task_manager.get_task(id_mapping["2"])
        assert child1.parent_task_id == parent.id
        assert child2.parent_task_id == parent.id

    def test_persist_skips_empty_titles(self, db, project_id):
        """Test that tasks without title/description are skipped."""
        tasks_data = [
            {"id": 1, "title": "Valid task"},
            {"id": 2},  # No title
            {"id": 3, "title": ""},  # Empty title
            {"id": 4, "title": "Another valid"},
        ]

        id_mapping = persist_decomposed_tasks(
            db=db,
            project_id=project_id,
            tasks_data=tasks_data,
            workflow_name="test-workflow",
        )

        # Should only create 2 valid tasks
        assert len(id_mapping) == 2
        assert "1" in id_mapping
        assert "4" in id_mapping

    def test_persist_empty_list_raises(self, db, project_id):
        """Test that empty task list raises ValueError."""
        with pytest.raises(ValueError, match="No tasks provided"):
            persist_decomposed_tasks(
                db=db,
                project_id=project_id,
                tasks_data=[],
                workflow_name="test-workflow",
            )

    def test_persist_uses_index_as_id(self, db, project_id):
        """Test that index is used when id is missing."""
        tasks_data = [
            {"title": "No ID task 1"},
            {"title": "No ID task 2"},
        ]

        id_mapping = persist_decomposed_tasks(
            db=db,
            project_id=project_id,
            tasks_data=tasks_data,
            workflow_name="test-workflow",
        )

        # Should use 1-based index as ID
        assert "1" in id_mapping
        assert "2" in id_mapping


class TestUpdateTaskFromWorkflow:
    """Tests for update_task_from_workflow function."""

    def test_update_status(self, db, project_id):
        """Test updating task status."""
        task_manager = LocalTaskManager(db)
        task = task_manager.create_task(
            project_id=project_id,
            title="Test task",
            workflow_name="test-workflow",
        )

        updated = update_task_from_workflow(
            db=db,
            task_id=task.id,
            status="in_progress",
        )

        assert updated is not None
        assert updated.status == "in_progress"

    def test_update_verification(self, db, project_id):
        """Test updating verification field."""
        task_manager = LocalTaskManager(db)
        task = task_manager.create_task(
            project_id=project_id,
            title="Test task",
            workflow_name="test-workflow",
        )

        updated = update_task_from_workflow(
            db=db,
            task_id=task.id,
            verification="Completed successfully",
        )

        assert updated is not None
        assert updated.verification == "Completed successfully"

    def test_update_validation_status(self, db, project_id):
        """Test updating validation status."""
        task_manager = LocalTaskManager(db)
        task = task_manager.create_task(
            project_id=project_id,
            title="Test task",
            workflow_name="test-workflow",
        )

        updated = update_task_from_workflow(
            db=db,
            task_id=task.id,
            validation_status="valid",
            validation_feedback="All tests passed",
        )

        assert updated is not None
        assert updated.validation_status == "valid"
        assert updated.validation_feedback == "All tests passed"

    def test_update_nonexistent_task(self, db, project_id):
        """Test updating a task that doesn't exist."""
        result = update_task_from_workflow(
            db=db,
            task_id="gt-nonexistent",
            status="closed",
        )

        assert result is None

    def test_update_no_changes(self, db, project_id):
        """Test update with no fields returns current task."""
        task_manager = LocalTaskManager(db)
        task = task_manager.create_task(
            project_id=project_id,
            title="Test task",
            workflow_name="test-workflow",
        )

        result = update_task_from_workflow(
            db=db,
            task_id=task.id,
        )

        assert result is not None
        assert result.id == task.id


class TestGetWorkflowTasks:
    """Tests for get_workflow_tasks function."""

    def test_get_tasks_by_workflow(self, db, project_id):
        """Test retrieving tasks by workflow name."""
        # Create tasks for different workflows
        persist_decomposed_tasks(
            db=db,
            project_id=project_id,
            tasks_data=[
                {"id": 1, "title": "Workflow A Task 1"},
                {"id": 2, "title": "Workflow A Task 2"},
            ],
            workflow_name="workflow-a",
        )

        persist_decomposed_tasks(
            db=db,
            project_id=project_id,
            tasks_data=[
                {"id": 1, "title": "Workflow B Task"},
            ],
            workflow_name="workflow-b",
        )

        tasks_a = get_workflow_tasks(db=db, workflow_name="workflow-a")
        tasks_b = get_workflow_tasks(db=db, workflow_name="workflow-b")

        assert len(tasks_a) == 2
        assert len(tasks_b) == 1
        assert all(t.workflow_name == "workflow-a" for t in tasks_a)

    def test_get_tasks_ordered_by_sequence(self, db, project_id):
        """Test that tasks are returned in sequence order."""
        persist_decomposed_tasks(
            db=db,
            project_id=project_id,
            tasks_data=[
                {"id": "a", "title": "First"},
                {"id": "b", "title": "Second"},
                {"id": "c", "title": "Third"},
            ],
            workflow_name="test-workflow",
        )

        tasks = get_workflow_tasks(db=db, workflow_name="test-workflow")

        assert len(tasks) == 3
        assert tasks[0].title == "First"
        assert tasks[1].title == "Second"
        assert tasks[2].title == "Third"

    def test_get_tasks_excludes_closed(self, db, project_id):
        """Test that closed tasks are excluded by default."""
        id_mapping = persist_decomposed_tasks(
            db=db,
            project_id=project_id,
            tasks_data=[
                {"id": 1, "title": "Open task"},
                {"id": 2, "title": "To be closed"},
            ],
            workflow_name="test-workflow",
        )

        # Close one task
        task_manager = LocalTaskManager(db)
        task_manager.close_task(id_mapping["2"])

        tasks = get_workflow_tasks(db=db, workflow_name="test-workflow")

        assert len(tasks) == 1
        assert tasks[0].title == "Open task"

    def test_get_tasks_includes_closed(self, db, project_id):
        """Test include_closed parameter."""
        id_mapping = persist_decomposed_tasks(
            db=db,
            project_id=project_id,
            tasks_data=[
                {"id": 1, "title": "Open task"},
                {"id": 2, "title": "Closed task"},
            ],
            workflow_name="test-workflow",
        )

        # Close one task
        task_manager = LocalTaskManager(db)
        task_manager.close_task(id_mapping["2"])

        tasks = get_workflow_tasks(
            db=db,
            workflow_name="test-workflow",
            include_closed=True,
        )

        assert len(tasks) == 2

    def test_get_tasks_empty_workflow(self, db, project_id):
        """Test getting tasks for nonexistent workflow."""
        tasks = get_workflow_tasks(db=db, workflow_name="nonexistent")
        assert tasks == []


class TestGetNextWorkflowTask:
    """Tests for get_next_workflow_task function."""

    def test_get_next_task(self, db, project_id):
        """Test getting the next open task."""
        persist_decomposed_tasks(
            db=db,
            project_id=project_id,
            tasks_data=[
                {"id": 1, "title": "First task"},
                {"id": 2, "title": "Second task"},
            ],
            workflow_name="test-workflow",
        )

        next_task = get_next_workflow_task(db=db, workflow_name="test-workflow")

        assert next_task is not None
        assert next_task.title == "First task"

    def test_get_next_skips_closed(self, db, project_id):
        """Test that next task skips closed tasks."""
        id_mapping = persist_decomposed_tasks(
            db=db,
            project_id=project_id,
            tasks_data=[
                {"id": 1, "title": "Already done"},
                {"id": 2, "title": "Next to do"},
            ],
            workflow_name="test-workflow",
        )

        # Close first task
        task_manager = LocalTaskManager(db)
        task_manager.close_task(id_mapping["1"])

        next_task = get_next_workflow_task(db=db, workflow_name="test-workflow")

        assert next_task is not None
        assert next_task.title == "Next to do"

    def test_get_next_all_complete(self, db, project_id):
        """Test returns None when all tasks are complete."""
        id_mapping = persist_decomposed_tasks(
            db=db,
            project_id=project_id,
            tasks_data=[
                {"id": 1, "title": "Task 1"},
            ],
            workflow_name="test-workflow",
        )

        task_manager = LocalTaskManager(db)
        task_manager.close_task(id_mapping["1"])

        next_task = get_next_workflow_task(db=db, workflow_name="test-workflow")
        assert next_task is None


class TestMarkWorkflowTaskComplete:
    """Tests for mark_workflow_task_complete function."""

    def test_mark_complete(self, db, project_id):
        """Test marking a task as complete."""
        id_mapping = persist_decomposed_tasks(
            db=db,
            project_id=project_id,
            tasks_data=[
                {"id": 1, "title": "Test task"},
            ],
            workflow_name="test-workflow",
        )

        result = mark_workflow_task_complete(
            db=db,
            task_id=id_mapping["1"],
            verification_result="All tests passed",
        )

        assert result is not None
        assert result.status == "closed"
        assert result.verification == "All tests passed"
        assert result.validation_status == "valid"

    def test_mark_complete_nonexistent(self, db, project_id):
        """Test marking nonexistent task."""
        result = mark_workflow_task_complete(
            db=db,
            task_id="gt-nonexistent",
        )
        assert result is None


class TestIntegration:
    """Integration tests for workflow-task cycle."""

    def test_full_workflow_cycle(self, db, project_id):
        """Test complete workflow: persist -> get -> update -> complete."""
        # 1. Persist decomposed tasks
        id_mapping = persist_decomposed_tasks(
            db=db,
            project_id=project_id,
            tasks_data=[
                {"id": 1, "title": "Step 1", "verification": "Check step 1"},
                {"id": 2, "title": "Step 2", "verification": "Check step 2"},
                {"id": 3, "title": "Step 3", "verification": "Check step 3"},
            ],
            workflow_name="integration-test",
        )

        assert len(id_mapping) == 3

        # 2. Get workflow tasks
        tasks = get_workflow_tasks(db=db, workflow_name="integration-test")
        assert len(tasks) == 3

        # 3. Get next task (should be first)
        next_task = get_next_workflow_task(db=db, workflow_name="integration-test")
        assert next_task.title == "Step 1"

        # 4. Mark in progress
        update_task_from_workflow(
            db=db,
            task_id=next_task.id,
            status="in_progress",
        )

        # 5. Complete first task
        mark_workflow_task_complete(
            db=db,
            task_id=next_task.id,
            verification_result="Step 1 done",
        )

        # 6. Next task should now be Step 2
        next_task = get_next_workflow_task(db=db, workflow_name="integration-test")
        assert next_task.title == "Step 2"

        # 7. Complete remaining tasks
        mark_workflow_task_complete(db=db, task_id=next_task.id)

        next_task = get_next_workflow_task(db=db, workflow_name="integration-test")
        assert next_task.title == "Step 3"

        mark_workflow_task_complete(db=db, task_id=next_task.id)

        # 8. No more tasks
        next_task = get_next_workflow_task(db=db, workflow_name="integration-test")
        assert next_task is None

        # 9. All tasks closed
        all_tasks = get_workflow_tasks(
            db=db,
            workflow_name="integration-test",
            include_closed=True,
        )
        assert all(t.status == "closed" for t in all_tasks)
