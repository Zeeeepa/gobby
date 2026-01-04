from unittest.mock import patch

import pytest

from gobby.storage.task_dependencies import TaskDependencyManager
from gobby.storage.tasks import LocalTaskManager, TaskIDCollisionError


@pytest.fixture
def dep_manager(temp_db):
    return TaskDependencyManager(temp_db)


@pytest.fixture
def task_manager(temp_db):
    return LocalTaskManager(temp_db)


@pytest.fixture
def project_id(sample_project):
    return sample_project["id"]


@pytest.mark.integration
class TestLocalTaskManager:
    def test_create_task(self, task_manager, project_id):
        task = task_manager.create_task(
            project_id=project_id,
            title="Fix bug",
            description="Fix the critical bug",
            priority=1,
            task_type="bug",
            labels=["urgent", "backend"],
        )

        assert task.title == "Fix bug"
        assert task.project_id == project_id
        assert task.status == "open"
        assert task.labels == ["urgent", "backend"]
        assert task.priority == 1
        assert task.task_type == "bug"
        assert task.id.startswith("gt-")
        assert task.created_at is not None
        assert task.updated_at is not None

    def test_get_task(self, task_manager, project_id):
        created = task_manager.create_task(project_id=project_id, title="Find me")
        fetched = task_manager.get_task(created.id)
        assert fetched == created

    def test_update_task(self, task_manager, project_id):
        task = task_manager.create_task(project_id=project_id, title="Original Title")
        updated = task_manager.update_task(task.id, title="New Title", status="in_progress")
        assert updated.title == "New Title"
        assert updated.status == "in_progress"
        assert updated.updated_at > task.updated_at

    def test_close_task(self, task_manager, project_id):
        task = task_manager.create_task(project_id=project_id, title="To Close")
        closed = task_manager.close_task(task.id, reason="Done")
        assert closed.status == "closed"
        assert closed.closed_reason == "Done"

    def test_delete_task(self, task_manager, project_id):
        task = task_manager.create_task(project_id=project_id, title="To Delete")
        task_manager.delete_task(task.id)

        with pytest.raises(ValueError, match="not found"):
            task_manager.get_task(task.id)

    def test_list_tasks(self, task_manager, project_id):
        t1 = task_manager.create_task(project_id=project_id, title="Task 1", priority=1)
        _ = task_manager.create_task(project_id=project_id, title="Task 2", priority=2)

        tasks = task_manager.list_tasks(project_id=project_id)
        assert len(tasks) == 2

        # Test filtering
        tasks_p1 = task_manager.list_tasks(project_id=project_id, priority=1)
        assert len(tasks_p1) == 1
        assert tasks_p1[0].id == t1.id

    def test_id_collision_retry(self, task_manager, project_id):
        # Create a task to occupy an ID
        existing_task = task_manager.create_task(project_id=project_id, title="Existing")

        # Mock generate_task_id to return existing ID once, then a new one
        with patch(
            "gobby.storage.tasks.generate_task_id", side_effect=[existing_task.id, "gt-newunique"]
        ) as mock_gen:
            new_task = task_manager.create_task(project_id=project_id, title="New Task")
            assert new_task.id == "gt-newunique"
            # Should have called it twice (initial attempt + retry)
            # Actually create_task calls generate_task_id in a loop, passing salt.
            # Side_effect replaces the return value of ALL calls.
            # We assume logic calls generate_task_id.
            assert mock_gen.call_count == 2

    def test_id_collision_failure(self, task_manager, project_id):
        existing_task = task_manager.create_task(project_id=project_id, title="Existing")

        # Mock to always return existing ID
        with patch("gobby.storage.tasks.generate_task_id", return_value=existing_task.id):
            with pytest.raises(TaskIDCollisionError):
                task_manager.create_task(project_id=project_id, title="Doom")

    def test_delete_with_children_fails_without_cascade(self, task_manager, project_id):
        parent = task_manager.create_task(project_id=project_id, title="Parent")
        _ = task_manager.create_task(project_id=project_id, title="Child", parent_task_id=parent.id)

        with pytest.raises(ValueError, match="has children"):
            task_manager.delete_task(parent.id)

    def test_delete_with_cascade(self, task_manager, project_id):
        parent = task_manager.create_task(project_id=project_id, title="Parent")
        child = task_manager.create_task(
            project_id=project_id, title="Child", parent_task_id=parent.id
        )

        task_manager.delete_task(parent.id, cascade=True)

        with pytest.raises(ValueError):
            task_manager.get_task(parent.id)
        with pytest.raises(ValueError):
            task_manager.get_task(child.id)

    def test_list_ready_tasks(self, task_manager, dep_manager, project_id):
        # T1 -> T2 (blocks)
        t1 = task_manager.create_task(project_id, "T1", priority=2)
        t2 = task_manager.create_task(project_id, "T2", priority=1)

        dep_manager.add_dependency(t1.id, t2.id, "blocks")

        # T3, independent
        t3 = task_manager.create_task(project_id, "T3", priority=2)

        # ready tasks: T2, T3. T1 is blocked.
        ready = task_manager.list_ready_tasks(project_id=project_id)
        ids = {t.id for t in ready}
        assert len(ready) == 2
        assert t2.id in ids
        assert t3.id in ids
        assert t1.id not in ids

        # Check sorting: priority ASC (1 before 2). So T2 first (priority 1)
        # Note: t3 is priority 2.
        assert ready[0].id == t2.id

        # Close T2. Now T1 should be ready?
        task_manager.close_task(t2.id)
        ready = task_manager.list_ready_tasks(project_id=project_id)
        ids = {t.id for t in ready}
        assert len(ready) == 2  # T1 and T3
        assert t1.id in ids
        assert t3.id in ids

    def test_list_blocked_tasks(self, task_manager, dep_manager, project_id):
        t1 = task_manager.create_task(project_id, "T1")
        t2 = task_manager.create_task(project_id, "T2")

        dep_manager.add_dependency(t1.id, t2.id, "blocks")

        blocked = task_manager.list_blocked_tasks(project_id=project_id)
        assert len(blocked) == 1
        assert blocked[0].id == t1.id

        task_manager.close_task(t2.id)
        blocked = task_manager.list_blocked_tasks(project_id=project_id)
        # T1 is no longer blocked by OPEN task

    def test_parent_blocked_by_children_is_still_ready(self, task_manager, dep_manager, project_id):
        """Parent tasks blocked by their own children should still be considered 'ready'.

        This is because 'blocked by children' means 'cannot close until children done',
        not 'cannot start working'. The parent should still appear in list_ready_tasks.
        """
        # Create parent and child
        parent = task_manager.create_task(project_id, "Parent Epic")
        child = task_manager.create_task(
            project_id, "Child Task", parent_task_id=parent.id
        )

        # Create the dependency: parent depends_on child with type "blocks"
        # This means child blocks parent (parent can't close until child is done)
        dep_manager.add_dependency(parent.id, child.id, "blocks")

        # Both parent and child should be ready (the child->parent block is a completion block)
        ready = task_manager.list_ready_tasks(project_id=project_id)
        ready_ids = {t.id for t in ready}
        assert parent.id in ready_ids, "Parent should be ready despite being blocked by its child"
        assert child.id in ready_ids, "Child should be ready (no blockers)"

        # Parent should NOT appear in list_blocked_tasks
        blocked = task_manager.list_blocked_tasks(project_id=project_id)
        blocked_ids = {t.id for t in blocked}
        assert parent.id not in blocked_ids, "Parent should not be 'blocked' by its own child"

        # Now add an external blocker (a task that is NOT a child)
        external_blocker = task_manager.create_task(project_id, "External Blocker")
        dep_manager.add_dependency(parent.id, external_blocker.id, "blocks")

        # Now parent should be blocked by the external task
        ready = task_manager.list_ready_tasks(project_id=project_id)
        ready_ids = {t.id for t in ready}
        assert parent.id not in ready_ids, "Parent should NOT be ready (blocked by external task)"

        blocked = task_manager.list_blocked_tasks(project_id=project_id)
        blocked_ids = {t.id for t in blocked}
        assert parent.id in blocked_ids, "Parent should be blocked by external task"

        # Close the external blocker
        task_manager.close_task(external_blocker.id)

        # Parent should be ready again (only blocked by its own child)
        ready = task_manager.list_ready_tasks(project_id=project_id)
        ready_ids = {t.id for t in ready}
        assert parent.id in ready_ids, "Parent should be ready again"

    def test_labels_management(self, task_manager, project_id):
        task = task_manager.create_task(project_id, "Label Task", labels=["a"])

        # Add label
        task = task_manager.add_label(task.id, "b")
        assert set(task.labels) == {"a", "b"}

        # Add existing label (no-op)
        task = task_manager.add_label(task.id, "a")
        assert set(task.labels) == {"a", "b"}

        # Remove label
        task = task_manager.remove_label(task.id, "a")
        assert task.labels == ["b"]

        # Remove non-existent label (no-op)
        task = task_manager.remove_label(task.id, "c")
        assert task.labels == ["b"]

    def test_find_by_prefix(self, task_manager, project_id):
        t1 = task_manager.create_task(project_id, "Find Me")
        # ID is like gt-123456

        # Test exact match
        found = task_manager.find_task_by_prefix(t1.id)
        assert found.id == t1.id

        # Test prefix match
        prefix = t1.id[:6]  # gt-123
        found = task_manager.find_task_by_prefix(prefix)
        assert found.id == t1.id

        # Test multiple matches returns None
        # We need another task with same prefix. Hard to force with random hash.
        # But we can mock or just test the logic that calls fetchall.
        # Actually generate_task_id uses timestamp + random, so very unlikely to clash prefix unless specifically crafted.

        # Test no match
        assert task_manager.find_task_by_prefix("gt-nomatch") is None

    def test_find_tasks_by_prefix(self, task_manager, project_id):
        t1 = task_manager.create_task(project_id, "T1")
        prefix = t1.id[:5]  # gt-12

        tasks = task_manager.find_tasks_by_prefix(prefix)
        assert len(tasks) >= 1
        assert t1.id in [t.id for t in tasks]

    def test_hierarchical_ordering(self, task_manager, project_id):
        # Root 1
        r1 = task_manager.create_task(project_id, "R1", priority=1)
        # Root 2
        r2 = task_manager.create_task(project_id, "R2", priority=2)

        # Children of R1
        c1_1 = task_manager.create_task(project_id, "C1.1", parent_task_id=r1.id, priority=2)
        c1_2 = task_manager.create_task(project_id, "C1.2", parent_task_id=r1.id, priority=1)

        # Child of C1.2
        c1_2_1 = task_manager.create_task(project_id, "C1.2.1", parent_task_id=c1_2.id)

        tasks = task_manager.list_tasks(project_id)
        ids = [t.id for t in tasks]

        # Expected: R1 -> C1.2 (prio 1) -> C1.2.1 -> C1.1 (prio 2) -> R2
        current_indices = {tid: idx for idx, tid in enumerate(ids)}

        # Verify relative ordering
        assert current_indices[r1.id] < current_indices[r2.id]
        assert current_indices[r1.id] < current_indices[c1_2.id]
        assert current_indices[c1_2.id] < current_indices[c1_2_1.id]
        assert current_indices[c1_2.id] < current_indices[c1_1.id]  # Priority 1 vs 2

    def test_update_all_fields(self, task_manager, project_id):
        task = task_manager.create_task(project_id, "T1")

        updated = task_manager.update_task(
            task.id,
            description="desc",
            priority=5,
            task_type="chore",
            assignee="me",
            labels=["l1"],
            test_strategy="strat",
            complexity_score=10,
            estimated_subtasks=5,
            expansion_context="ctx",
            validation_criteria="crit",
            use_external_validator=True,
            validation_fail_count=2,
            validation_status="valid",
            validation_feedback="good",
        )

        assert updated.description == "desc"
        assert updated.priority == 5
        assert updated.task_type == "chore"
        assert updated.assignee == "me"
        assert updated.labels == ["l1"]
        assert updated.test_strategy == "strat"
        assert updated.complexity_score == 10
        assert updated.estimated_subtasks == 5
        assert updated.expansion_context == "ctx"
        assert updated.validation_criteria == "crit"
        assert updated.use_external_validator is True
        assert updated.validation_fail_count == 2
        assert updated.validation_status == "valid"
        assert updated.validation_feedback == "good"

    def test_clear_parent_task(self, task_manager, project_id):
        parent = task_manager.create_task(project_id, "P")
        child = task_manager.create_task(project_id, "C", parent_task_id=parent.id)

        assert child.parent_task_id == parent.id

        # Explicit None should clear it
        updated = task_manager.update_task(child.id, parent_task_id=None)
        assert updated.parent_task_id is None

    def test_close_task_with_many_children(self, task_manager, project_id):
        parent = task_manager.create_task(project_id, "P")
        for i in range(5):
            task_manager.create_task(project_id, f"C{i}", parent_task_id=parent.id)

        with pytest.raises(ValueError) as exc:
            task_manager.close_task(parent.id)

        msg = str(exc.value)
        assert "has 5 open child task(s)" in msg
        assert "and 2 more" in msg

    # =========================================================================
    # Commit Linking Tests
    # =========================================================================

    def test_link_commit_adds_sha_to_empty_task(self, task_manager, project_id):
        """Test linking a commit to a task with no commits."""
        task = task_manager.create_task(project_id, "Task with commits")
        assert task.commits is None or task.commits == []

        updated = task_manager.link_commit(task.id, "abc123def456")

        assert updated.commits == ["abc123def456"]

    def test_link_commit_appends_to_existing(self, task_manager, project_id):
        """Test linking adds to existing commits array."""
        task = task_manager.create_task(project_id, "Task with commits")
        task_manager.link_commit(task.id, "commit1")
        updated = task_manager.link_commit(task.id, "commit2")

        assert "commit1" in updated.commits
        assert "commit2" in updated.commits
        assert len(updated.commits) == 2

    def test_link_commit_ignores_duplicate(self, task_manager, project_id):
        """Test linking same commit twice doesn't duplicate."""
        task = task_manager.create_task(project_id, "Task with commits")
        task_manager.link_commit(task.id, "abc123")
        updated = task_manager.link_commit(task.id, "abc123")

        assert updated.commits == ["abc123"]

    def test_link_commit_invalid_task(self, task_manager):
        """Test linking commit to non-existent task raises error."""
        with pytest.raises(ValueError, match="not found"):
            task_manager.link_commit("gt-nonexistent", "abc123")

    def test_unlink_commit_removes_sha(self, task_manager, project_id):
        """Test unlinking removes commit from array."""
        task = task_manager.create_task(project_id, "Task with commits")
        task_manager.link_commit(task.id, "commit1")
        task_manager.link_commit(task.id, "commit2")

        updated = task_manager.unlink_commit(task.id, "commit1")

        assert updated.commits == ["commit2"]

    def test_unlink_commit_handles_nonexistent(self, task_manager, project_id):
        """Test unlinking non-existent commit is a no-op."""
        task = task_manager.create_task(project_id, "Task with commits")
        task_manager.link_commit(task.id, "commit1")

        # Should not raise, just return unchanged
        updated = task_manager.unlink_commit(task.id, "nonexistent")

        assert updated.commits == ["commit1"]

    def test_unlink_commit_from_empty_task(self, task_manager, project_id):
        """Test unlinking from task with no commits is a no-op."""
        task = task_manager.create_task(project_id, "Empty task")

        updated = task_manager.unlink_commit(task.id, "abc123")

        assert updated.commits is None or updated.commits == []

    def test_unlink_commit_invalid_task(self, task_manager):
        """Test unlinking from non-existent task raises error."""
        with pytest.raises(ValueError, match="not found"):
            task_manager.unlink_commit("gt-nonexistent", "abc123")

    def test_commits_persist_after_update(self, task_manager, project_id):
        """Test that commits array persists through other updates."""
        task = task_manager.create_task(project_id, "Task")
        task_manager.link_commit(task.id, "commit1")

        # Update another field
        updated = task_manager.update_task(task.id, title="Updated Title")

        assert updated.commits == ["commit1"]
        assert updated.title == "Updated Title"
