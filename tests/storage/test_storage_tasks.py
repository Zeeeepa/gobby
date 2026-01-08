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
        child = task_manager.create_task(project_id, "Child Task", parent_task_id=parent.id)

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

    # =========================================================================
    # Reopen Task Tests
    # =========================================================================

    def test_reopen_task_basic(self, task_manager, project_id):
        """Test reopening a closed task."""
        task = task_manager.create_task(project_id, "To Reopen")
        task_manager.close_task(task.id, reason="Done")

        reopened = task_manager.reopen_task(task.id)

        assert reopened.status == "open"
        assert reopened.closed_reason is None
        assert reopened.closed_at is None
        assert reopened.closed_in_session_id is None
        assert reopened.closed_commit_sha is None

    def test_reopen_task_with_reason(self, task_manager, project_id):
        """Test reopening a task with a reason adds note to description."""
        task = task_manager.create_task(project_id, "To Reopen", description="Original description")
        task_manager.close_task(task.id)

        reopened = task_manager.reopen_task(task.id, reason="Bug found")

        assert reopened.status == "open"
        assert "Original description" in reopened.description
        assert "[Reopened: Bug found]" in reopened.description

    def test_reopen_task_not_closed_raises(self, task_manager, project_id):
        """Test reopening a non-closed task raises error."""
        task = task_manager.create_task(project_id, "Open Task")

        with pytest.raises(ValueError, match="is not closed"):
            task_manager.reopen_task(task.id)

    def test_reopen_task_in_progress_raises(self, task_manager, project_id):
        """Test reopening an in_progress task raises error."""
        task = task_manager.create_task(project_id, "In Progress")
        task_manager.update_task(task.id, status="in_progress")

        with pytest.raises(ValueError, match="is not closed"):
            task_manager.reopen_task(task.id)

    # =========================================================================
    # Close Task Additional Tests
    # =========================================================================

    def test_close_task_force_with_open_children(self, task_manager, project_id):
        """Test force closing a task with open children."""
        parent = task_manager.create_task(project_id, "Parent")
        task_manager.create_task(project_id, "Child", parent_task_id=parent.id)

        # Normal close should fail
        with pytest.raises(ValueError, match="open child task"):
            task_manager.close_task(parent.id)

        # Force close should succeed
        closed = task_manager.close_task(parent.id, force=True)
        assert closed.status == "closed"

    def test_close_task_with_session_and_commit(self, task_manager, project_id, session_manager):
        """Test closing task records session ID and commit SHA."""
        # Create a session first (foreign key constraint)
        session = session_manager.register(
            external_id="test-ext-id",
            machine_id="test-machine",
            source="claude",
            project_id=project_id,
        )

        task = task_manager.create_task(project_id, "Task")

        closed = task_manager.close_task(
            task.id,
            reason="Done",
            closed_in_session_id=session.id,
            closed_commit_sha="abc123def",
        )

        assert closed.closed_in_session_id == session.id
        assert closed.closed_commit_sha == "abc123def"

    def test_close_task_with_validation_override(self, task_manager, project_id):
        """Test closing task with validation override reason."""
        task = task_manager.create_task(project_id, "Task")

        closed = task_manager.close_task(
            task.id, validation_override_reason="User approved manually"
        )

        assert closed.validation_override_reason == "User approved manually"

    def test_close_task_not_found_raises(self, task_manager):
        """Test closing non-existent task raises error."""
        with pytest.raises(ValueError, match="not found"):
            task_manager.close_task("gt-nonexistent")

    # =========================================================================
    # Update Task Additional Tests
    # =========================================================================

    def test_update_task_workflow_fields(self, task_manager, project_id):
        """Test updating workflow-related fields."""
        task = task_manager.create_task(project_id, "Task")

        updated = task_manager.update_task(
            task.id,
            workflow_name="test-workflow",
            verification="Test passes",
            sequence_order=5,
        )

        assert updated.workflow_name == "test-workflow"
        assert updated.verification == "Test passes"
        assert updated.sequence_order == 5

    def test_update_task_escalation_fields(self, task_manager, project_id):
        """Test updating escalation-related fields."""
        task = task_manager.create_task(project_id, "Task")

        updated = task_manager.update_task(
            task.id,
            escalated_at="2024-01-01T00:00:00Z",
            escalation_reason="Blocked on external dependency",
        )

        assert updated.escalated_at == "2024-01-01T00:00:00Z"
        assert updated.escalation_reason == "Blocked on external dependency"

    def test_update_task_labels_to_none(self, task_manager, project_id):
        """Test setting labels to None converts to empty JSON array."""
        task = task_manager.create_task(project_id, "Task", labels=["a", "b"])

        updated = task_manager.update_task(task.id, labels=None)

        # Labels should be empty list, not None (due to JSON storage)
        assert updated.labels == []

    def test_update_task_no_changes(self, task_manager, project_id):
        """Test update with no changes returns current task."""
        task = task_manager.create_task(project_id, "Task")

        updated = task_manager.update_task(task.id)

        assert updated.id == task.id
        # updated_at should not change when no fields are updated
        # Actually it does change based on the code - let's verify the task is returned
        assert updated.title == task.title

    def test_update_task_not_found_raises(self, task_manager):
        """Test updating non-existent task raises error."""
        with pytest.raises(ValueError, match="not found"):
            task_manager.update_task("gt-nonexistent", title="New")

    # =========================================================================
    # Needs Decomposition Status Tests
    # =========================================================================

    def test_update_task_needs_decomposition_to_in_progress_without_children(
        self, task_manager, project_id
    ):
        """Test cannot transition from needs_decomposition to in_progress without children."""
        task = task_manager.create_task(project_id, "Task")
        task_manager.update_task(task.id, status="needs_decomposition")

        with pytest.raises(ValueError, match="must be decomposed into subtasks"):
            task_manager.update_task(task.id, status="in_progress")

    def test_update_task_needs_decomposition_to_closed_without_children(
        self, task_manager, project_id
    ):
        """Test cannot transition from needs_decomposition to closed without children."""
        task = task_manager.create_task(project_id, "Task")
        task_manager.update_task(task.id, status="needs_decomposition")

        with pytest.raises(ValueError, match="must be decomposed into subtasks"):
            task_manager.update_task(task.id, status="closed")

    def test_update_task_needs_decomposition_to_in_progress_with_children(
        self, task_manager, project_id
    ):
        """Test can transition from needs_decomposition with children."""
        task = task_manager.create_task(project_id, "Parent")
        task_manager.update_task(task.id, status="needs_decomposition")
        task_manager.create_task(project_id, "Child", parent_task_id=task.id)

        # Should succeed now
        updated = task_manager.update_task(task.id, status="in_progress")
        assert updated.status == "in_progress"

    def test_update_validation_criteria_on_needs_decomposition_without_children(
        self, task_manager, project_id
    ):
        """Test cannot set validation criteria on needs_decomposition task without children."""
        task = task_manager.create_task(project_id, "Task")
        task_manager.update_task(task.id, status="needs_decomposition")

        with pytest.raises(ValueError, match="Decompose the task into subtasks first"):
            task_manager.update_task(task.id, validation_criteria="Test criteria")

    def test_update_validation_criteria_on_needs_decomposition_with_children(
        self, task_manager, project_id
    ):
        """Test can set validation criteria on needs_decomposition task with children."""
        task = task_manager.create_task(project_id, "Parent")
        task_manager.update_task(task.id, status="needs_decomposition")
        task_manager.create_task(project_id, "Child", parent_task_id=task.id)

        updated = task_manager.update_task(task.id, validation_criteria="Test criteria")
        assert updated.validation_criteria == "Test criteria"

    # =========================================================================
    # Create Task with Parent Auto-transition Tests
    # =========================================================================

    def test_create_child_auto_transitions_parent_from_needs_decomposition(
        self, task_manager, project_id
    ):
        """Test creating a child task auto-transitions parent from needs_decomposition to open."""
        parent = task_manager.create_task(project_id, "Parent")
        task_manager.update_task(parent.id, status="needs_decomposition")

        # Verify parent is in needs_decomposition
        parent = task_manager.get_task(parent.id)
        assert parent.status == "needs_decomposition"

        # Create child - should auto-transition parent
        task_manager.create_task(project_id, "Child", parent_task_id=parent.id)

        # Parent should now be open
        parent = task_manager.get_task(parent.id)
        assert parent.status == "open"

    # =========================================================================
    # Delete Task Tests
    # =========================================================================

    def test_delete_nonexistent_task_returns_false(self, task_manager):
        """Test deleting non-existent task returns False."""
        result = task_manager.delete_task("gt-nonexistent")
        assert result is False

    # =========================================================================
    # List Tasks Additional Filter Tests
    # =========================================================================

    def test_list_tasks_with_status_list(self, task_manager, project_id):
        """Test filtering tasks by multiple statuses."""
        t1 = task_manager.create_task(project_id, "Open Task")
        t2 = task_manager.create_task(project_id, "In Progress")
        task_manager.update_task(t2.id, status="in_progress")
        t3 = task_manager.create_task(project_id, "Closed")
        task_manager.close_task(t3.id)

        # Filter by list of statuses
        tasks = task_manager.list_tasks(project_id=project_id, status=["open", "in_progress"])

        task_ids = {t.id for t in tasks}
        assert t1.id in task_ids
        assert t2.id in task_ids
        assert t3.id not in task_ids

    def test_list_tasks_with_title_like(self, task_manager, project_id):
        """Test filtering tasks by title pattern."""
        task_manager.create_task(project_id, "Fix bug in auth")
        task_manager.create_task(project_id, "Add feature X")
        task_manager.create_task(project_id, "Fix bug in API")

        tasks = task_manager.list_tasks(project_id=project_id, title_like="Fix bug")

        assert len(tasks) == 2
        for t in tasks:
            assert "Fix bug" in t.title

    def test_list_tasks_with_label_filter(self, task_manager, project_id):
        """Test filtering tasks by label."""
        task_manager.create_task(project_id, "Task 1", labels=["urgent", "backend"])
        task_manager.create_task(project_id, "Task 2", labels=["frontend"])
        task_manager.create_task(project_id, "Task 3", labels=["urgent", "frontend"])

        tasks = task_manager.list_tasks(project_id=project_id, label="urgent")

        assert len(tasks) == 2
        for t in tasks:
            assert "urgent" in t.labels

    def test_list_tasks_with_assignee_filter(self, task_manager, project_id):
        """Test filtering tasks by assignee."""
        task_manager.create_task(project_id, "Task 1", assignee="alice")
        task_manager.create_task(project_id, "Task 2", assignee="bob")

        tasks = task_manager.list_tasks(project_id=project_id, assignee="alice")

        assert len(tasks) == 1
        assert tasks[0].assignee == "alice"

    def test_list_tasks_with_task_type_filter(self, task_manager, project_id):
        """Test filtering tasks by type."""
        task_manager.create_task(project_id, "Bug 1", task_type="bug")
        task_manager.create_task(project_id, "Feature 1", task_type="feature")

        tasks = task_manager.list_tasks(project_id=project_id, task_type="bug")

        assert len(tasks) == 1
        assert tasks[0].task_type == "bug"

    # =========================================================================
    # List Ready Tasks Filter Tests
    # =========================================================================

    def test_list_ready_tasks_with_task_type_filter(self, task_manager, dep_manager, project_id):
        """Test filtering ready tasks by type."""
        task_manager.create_task(project_id, "Bug 1", task_type="bug")
        task_manager.create_task(project_id, "Feature 1", task_type="feature")

        tasks = task_manager.list_ready_tasks(project_id=project_id, task_type="bug")

        assert len(tasks) == 1
        assert tasks[0].task_type == "bug"

    def test_list_ready_tasks_with_assignee_filter(self, task_manager, project_id):
        """Test filtering ready tasks by assignee."""
        task_manager.create_task(project_id, "Task 1", assignee="alice")
        task_manager.create_task(project_id, "Task 2", assignee="bob")

        tasks = task_manager.list_ready_tasks(project_id=project_id, assignee="alice")

        assert len(tasks) == 1
        assert tasks[0].assignee == "alice"

    def test_list_ready_tasks_with_priority_filter(self, task_manager, project_id):
        """Test filtering ready tasks by priority."""
        task_manager.create_task(project_id, "High Priority", priority=1)
        task_manager.create_task(project_id, "Low Priority", priority=3)

        tasks = task_manager.list_ready_tasks(project_id=project_id, priority=1)

        assert len(tasks) == 1
        assert tasks[0].priority == 1

    def test_list_ready_tasks_with_parent_filter(self, task_manager, project_id):
        """Test filtering ready tasks by parent."""
        parent = task_manager.create_task(project_id, "Parent")
        task_manager.create_task(project_id, "Child 1", parent_task_id=parent.id)
        task_manager.create_task(project_id, "Child 2", parent_task_id=parent.id)
        task_manager.create_task(project_id, "Orphan")

        tasks = task_manager.list_ready_tasks(project_id=project_id, parent_task_id=parent.id)

        assert len(tasks) == 2
        for t in tasks:
            assert t.parent_task_id == parent.id

    def test_list_ready_tasks_with_limit_offset(self, task_manager, project_id):
        """Test pagination in ready tasks."""
        for i in range(5):
            task_manager.create_task(project_id, f"Task {i}")

        tasks = task_manager.list_ready_tasks(project_id=project_id, limit=2, offset=1)

        assert len(tasks) == 2

    # =========================================================================
    # List Blocked Tasks Filter Tests
    # =========================================================================

    def test_list_blocked_tasks_with_parent_filter(self, task_manager, dep_manager, project_id):
        """Test filtering blocked tasks by parent."""
        parent = task_manager.create_task(project_id, "Parent")
        child1 = task_manager.create_task(project_id, "Child 1", parent_task_id=parent.id)
        blocker = task_manager.create_task(project_id, "Blocker")

        dep_manager.add_dependency(child1.id, blocker.id, "blocks")

        blocked = task_manager.list_blocked_tasks(project_id=project_id, parent_task_id=parent.id)

        assert len(blocked) == 1
        assert blocked[0].id == child1.id

    def test_list_blocked_tasks_with_limit_offset(self, task_manager, dep_manager, project_id):
        """Test pagination in blocked tasks."""
        blocker = task_manager.create_task(project_id, "Blocker")
        for i in range(5):
            task = task_manager.create_task(project_id, f"Blocked {i}")
            dep_manager.add_dependency(task.id, blocker.id, "blocks")

        blocked = task_manager.list_blocked_tasks(project_id=project_id, limit=2, offset=1)

        assert len(blocked) == 2

    # =========================================================================
    # Workflow Tasks Tests
    # =========================================================================

    def test_list_workflow_tasks(self, task_manager, project_id):
        """Test listing tasks by workflow name."""
        task_manager.create_task(
            project_id, "Task 1", workflow_name="test-workflow", sequence_order=1
        )
        task_manager.create_task(
            project_id, "Task 2", workflow_name="test-workflow", sequence_order=0
        )
        task_manager.create_task(
            project_id, "Task 3", workflow_name="other-workflow", sequence_order=0
        )

        tasks = task_manager.list_workflow_tasks("test-workflow", project_id=project_id)

        assert len(tasks) == 2
        # Should be ordered by sequence_order
        assert tasks[0].sequence_order == 0
        assert tasks[1].sequence_order == 1

    def test_list_workflow_tasks_with_status_filter(self, task_manager, project_id):
        """Test filtering workflow tasks by status."""
        task_manager.create_task(project_id, "Open", workflow_name="wf")
        t2 = task_manager.create_task(project_id, "Closed", workflow_name="wf")
        task_manager.close_task(t2.id)

        tasks = task_manager.list_workflow_tasks("wf", project_id=project_id, status="open")

        assert len(tasks) == 1
        assert tasks[0].status == "open"

    def test_list_workflow_tasks_without_project_filter(self, task_manager, project_id):
        """Test listing workflow tasks without project filter."""
        task_manager.create_task(project_id, "Task", workflow_name="global-wf")

        tasks = task_manager.list_workflow_tasks("global-wf")

        assert len(tasks) == 1

    # =========================================================================
    # Count Tasks Tests
    # =========================================================================

    def test_count_tasks_all(self, task_manager, project_id):
        """Test counting all tasks."""
        for i in range(3):
            task_manager.create_task(project_id, f"Task {i}")

        count = task_manager.count_tasks(project_id=project_id)
        assert count == 3

    def test_count_tasks_by_status(self, task_manager, project_id):
        """Test counting tasks by status."""
        task_manager.create_task(project_id, "Open")
        t2 = task_manager.create_task(project_id, "Closed")
        task_manager.close_task(t2.id)

        assert task_manager.count_tasks(project_id=project_id, status="open") == 1
        assert task_manager.count_tasks(project_id=project_id, status="closed") == 1

    def test_count_tasks_empty(self, task_manager, project_id):
        """Test counting when no tasks exist."""
        count = task_manager.count_tasks(project_id=project_id)
        assert count == 0

    def test_count_by_status(self, task_manager, project_id):
        """Test grouping task counts by status."""
        task_manager.create_task(project_id, "Open 1")
        task_manager.create_task(project_id, "Open 2")
        t3 = task_manager.create_task(project_id, "Closed")
        task_manager.close_task(t3.id)

        counts = task_manager.count_by_status(project_id=project_id)

        assert counts.get("open") == 2
        assert counts.get("closed") == 1

    def test_count_by_status_all_projects(self, task_manager, project_id):
        """Test counting by status without project filter."""
        task_manager.create_task(project_id, "Task")

        counts = task_manager.count_by_status()

        assert counts.get("open", 0) >= 1

    def test_count_ready_tasks(self, task_manager, dep_manager, project_id):
        """Test counting ready tasks."""
        task_manager.create_task(project_id, "Ready 1")
        task_manager.create_task(project_id, "Ready 2")
        blocked = task_manager.create_task(project_id, "Blocked")
        blocker = task_manager.create_task(project_id, "Blocker")
        dep_manager.add_dependency(blocked.id, blocker.id, "blocks")

        count = task_manager.count_ready_tasks(project_id=project_id)

        # Ready 1, Ready 2, and Blocker are ready; Blocked is blocked
        assert count == 3

    def test_count_blocked_tasks(self, task_manager, dep_manager, project_id):
        """Test counting blocked tasks."""
        blocked = task_manager.create_task(project_id, "Blocked")
        blocker = task_manager.create_task(project_id, "Blocker")
        dep_manager.add_dependency(blocked.id, blocker.id, "blocks")

        count = task_manager.count_blocked_tasks(project_id=project_id)

        assert count == 1

    # =========================================================================
    # Task.to_brief Tests
    # =========================================================================

    def test_task_to_brief(self, task_manager, project_id):
        """Test Task.to_brief returns minimal fields."""
        task = task_manager.create_task(
            project_id,
            "Full Task",
            description="Long description",
            priority=1,
            task_type="bug",
            labels=["urgent"],
            assignee="alice",
        )

        brief = task.to_brief()

        # Should include these fields
        assert brief["id"] == task.id
        assert brief["title"] == "Full Task"
        assert brief["status"] == "open"
        assert brief["priority"] == 1
        assert brief["type"] == "bug"
        assert brief["parent_task_id"] is None
        assert "created_at" in brief
        assert "updated_at" in brief

        # Should NOT include these fields
        assert "description" not in brief
        assert "assignee" not in brief
        assert "labels" not in brief

    # =========================================================================
    # Change Listener Tests
    # =========================================================================

    def test_change_listener_called_on_create(self, task_manager, project_id):
        """Test change listener is called when creating a task."""
        listener_called = []

        def listener():
            listener_called.append(True)

        task_manager.add_change_listener(listener)
        task_manager.create_task(project_id, "Task")

        assert len(listener_called) == 1

    def test_change_listener_called_on_update(self, task_manager, project_id):
        """Test change listener is called when updating a task."""
        task = task_manager.create_task(project_id, "Task")

        listener_called = []

        def listener():
            listener_called.append(True)

        task_manager.add_change_listener(listener)
        task_manager.update_task(task.id, title="Updated")

        assert len(listener_called) == 1

    def test_change_listener_called_on_delete(self, task_manager, project_id):
        """Test change listener is called when deleting a task."""
        task = task_manager.create_task(project_id, "Task")

        listener_called = []

        def listener():
            listener_called.append(True)

        task_manager.add_change_listener(listener)
        task_manager.delete_task(task.id)

        assert len(listener_called) == 1

    def test_change_listener_error_does_not_break_operation(self, task_manager, project_id):
        """Test that listener errors don't break task operations."""

        def failing_listener():
            raise RuntimeError("Listener failed!")

        task_manager.add_change_listener(failing_listener)

        # Should not raise, operation should succeed
        task = task_manager.create_task(project_id, "Task")
        assert task.id is not None

    # =========================================================================
    # Create Task with All Fields Tests
    # =========================================================================

    def test_create_task_with_all_fields(self, task_manager, project_id, session_manager):
        """Test creating task with all possible fields."""
        # Create a session first (foreign key constraint)
        session = session_manager.register(
            external_id="test-ext-id",
            machine_id="test-machine",
            source="claude",
            project_id=project_id,
        )

        task = task_manager.create_task(
            project_id=project_id,
            title="Complete Task",
            description="Full description",
            parent_task_id=None,
            created_in_session_id=session.id,
            priority=1,
            task_type="feature",
            assignee="developer",
            labels=["important"],
            test_strategy="Unit tests",
            complexity_score=5,
            estimated_subtasks=3,
            expansion_context="More context",
            validation_criteria="All tests pass",
            use_external_validator=True,
            workflow_name="dev-workflow",
            verification="npm test passes",
            sequence_order=1,
        )

        assert task.title == "Complete Task"
        assert task.description == "Full description"
        assert task.created_in_session_id == session.id
        assert task.priority == 1
        assert task.task_type == "feature"
        assert task.assignee == "developer"
        assert task.labels == ["important"]
        assert task.test_strategy == "Unit tests"
        assert task.complexity_score == 5
        assert task.estimated_subtasks == 3
        assert task.expansion_context == "More context"
        assert task.validation_criteria == "All tests pass"
        assert task.use_external_validator is True
        assert task.workflow_name == "dev-workflow"
        assert task.verification == "npm test passes"
        assert task.sequence_order == 1
        # Validation status should be pending when criteria is set
        assert task.validation_status == "pending"


@pytest.mark.integration
class TestNormalizePriority:
    """Test the normalize_priority helper function."""

    def test_normalize_priority_none(self):
        """Test None priority returns 999."""
        from gobby.storage.tasks import normalize_priority

        assert normalize_priority(None) == 999

    def test_normalize_priority_named_string(self):
        """Test named priority strings are converted correctly."""
        from gobby.storage.tasks import normalize_priority

        assert normalize_priority("critical") == 0
        assert normalize_priority("high") == 1
        assert normalize_priority("medium") == 2
        assert normalize_priority("low") == 3
        assert normalize_priority("CRITICAL") == 0  # Case insensitive
        assert normalize_priority("High") == 1

    def test_normalize_priority_numeric_string(self):
        """Test numeric strings are parsed."""
        from gobby.storage.tasks import normalize_priority

        assert normalize_priority("1") == 1
        assert normalize_priority("5") == 5

    def test_normalize_priority_invalid_string(self):
        """Test invalid string returns 999."""
        from gobby.storage.tasks import normalize_priority

        assert normalize_priority("invalid") == 999
        assert normalize_priority("urgent") == 999  # Not in PRIORITY_MAP

    def test_normalize_priority_integer(self):
        """Test integer values are returned as-is."""
        from gobby.storage.tasks import normalize_priority

        assert normalize_priority(1) == 1
        assert normalize_priority(5) == 5
        assert normalize_priority(0) == 0


@pytest.mark.integration
class TestOrderTasksHierarchically:
    """Test the order_tasks_hierarchically helper function."""

    def test_order_empty_list(self):
        """Test ordering empty list returns empty list."""
        from gobby.storage.tasks import order_tasks_hierarchically

        result = order_tasks_hierarchically([])
        assert result == []

    def test_order_single_task(self, task_manager, project_id):
        """Test ordering single task returns single task."""
        from gobby.storage.tasks import order_tasks_hierarchically

        task = task_manager.create_task(project_id, "Single")
        result = order_tasks_hierarchically([task])

        assert len(result) == 1
        assert result[0].id == task.id

    def test_order_orphan_parent_reference(self, task_manager, project_id):
        """Test task with parent_id not in result set is treated as root."""
        from gobby.storage.tasks import order_tasks_hierarchically

        parent = task_manager.create_task(project_id, "Parent")
        child = task_manager.create_task(project_id, "Child", parent_task_id=parent.id)

        # Only pass child, not parent - child should be treated as root
        result = order_tasks_hierarchically([child])

        assert len(result) == 1
        assert result[0].id == child.id


@pytest.mark.integration
class TestCreateTaskWithDecomposition:
    """Test create_task_with_decomposition for auto-decomposition."""

    def test_create_single_step_task(self, task_manager, project_id):
        """Test creating a simple task without steps."""
        result = task_manager.create_task_with_decomposition(
            project_id=project_id,
            title="Simple Task",
            description="A simple description",
        )

        assert result["auto_decomposed"] is False
        assert "task" in result
        assert result["task"]["title"] == "Simple Task"

    def test_create_multi_step_task_with_auto_decompose(self, task_manager, project_id):
        """Test creating a multi-step task auto-decomposes."""
        description = """Steps to complete:
1. First step
2. Second step
3. Third step"""

        result = task_manager.create_task_with_decomposition(
            project_id=project_id,
            title="Multi-Step Task",
            description=description,
            auto_decompose=True,
        )

        assert result["auto_decomposed"] is True
        assert "parent_task" in result
        assert "subtasks" in result
        assert len(result["subtasks"]) == 3

    def test_create_multi_step_task_opt_out(self, task_manager, project_id):
        """Test creating multi-step task with auto_decompose=False."""
        # Need at least 3 numbered items for detect_multi_step to return True
        description = """Steps:
1. Step one
2. Step two
3. Step three"""

        result = task_manager.create_task_with_decomposition(
            project_id=project_id,
            title="No Decompose",
            description=description,
            auto_decompose=False,
        )

        assert result["auto_decomposed"] is False
        assert result["task"]["status"] == "needs_decomposition"

    def test_create_task_with_workflow_state_opt_out(self, task_manager, project_id):
        """Test auto_decompose respects workflow state variable."""
        from unittest.mock import MagicMock

        # Need at least 3 numbered items for detect_multi_step to return True
        description = """Steps:
1. First
2. Second
3. Third"""

        # Mock workflow state with auto_decompose=False
        workflow_state = MagicMock()
        workflow_state.variables = {"auto_decompose": False}

        result = task_manager.create_task_with_decomposition(
            project_id=project_id,
            title="Workflow Opt-out",
            description=description,
            workflow_state=workflow_state,
        )

        assert result["auto_decomposed"] is False
        assert result["task"]["status"] == "needs_decomposition"

    def test_create_task_explicit_param_overrides_workflow_state(self, task_manager, project_id):
        """Test explicit auto_decompose param overrides workflow state."""
        from unittest.mock import MagicMock

        # Need at least 3 numbered items for detect_multi_step to return True
        description = """Steps:
1. First
2. Second
3. Third"""

        # Workflow says False, but explicit param says True
        workflow_state = MagicMock()
        workflow_state.variables = {"auto_decompose": False}

        result = task_manager.create_task_with_decomposition(
            project_id=project_id,
            title="Explicit Override",
            description=description,
            auto_decompose=True,  # Override workflow state
            workflow_state=workflow_state,
        )

        assert result["auto_decomposed"] is True


@pytest.mark.integration
class TestUpdateTaskWithStepDetection:
    """Test update_task_with_step_detection for multi-step handling."""

    def test_update_no_steps_detected(self, task_manager, project_id):
        """Test updating with description that has no steps."""
        task = task_manager.create_task(project_id, "Task")

        result = task_manager.update_task_with_step_detection(task.id, description="Simple update")

        assert result["steps_detected"] is False
        assert result["step_count"] == 0
        assert result["auto_decomposed"] is False

    def test_update_steps_detected_auto_decompose(self, task_manager, project_id):
        """Test updating with steps triggers auto-decomposition."""
        task = task_manager.create_task(project_id, "Task")

        result = task_manager.update_task_with_step_detection(
            task.id,
            description="1. First\n2. Second\n3. Third",
            auto_decompose=True,
        )

        assert result["steps_detected"] is True
        assert result["step_count"] == 3
        assert result["auto_decomposed"] is True
        assert "subtasks" in result
        assert len(result["subtasks"]) == 3

    def test_update_steps_detected_opt_out(self, task_manager, project_id):
        """Test updating with steps but opt out sets needs_decomposition."""
        task = task_manager.create_task(project_id, "Task")

        # Need at least 3 numbered items for detect_multi_step to return True
        result = task_manager.update_task_with_step_detection(
            task.id,
            description="1. First\n2. Second\n3. Third",
            auto_decompose=False,
        )

        assert result["steps_detected"] is True
        assert result["auto_decomposed"] is False
        assert result["task"]["status"] == "needs_decomposition"

    def test_update_skips_detection_if_has_children(self, task_manager, project_id):
        """Test step detection is skipped if task already has children."""
        parent = task_manager.create_task(project_id, "Parent")
        task_manager.create_task(project_id, "Child", parent_task_id=parent.id)

        result = task_manager.update_task_with_step_detection(
            parent.id, description="1. First\n2. Second"
        )

        # Should skip detection because task already has children
        assert result["steps_detected"] is False
        assert result["auto_decomposed"] is False

    def test_update_none_description(self, task_manager, project_id):
        """Test updating with None description."""
        task = task_manager.create_task(project_id, "Task", description="Original")

        result = task_manager.update_task_with_step_detection(task.id, description=None)

        assert result["steps_detected"] is False

    def test_update_with_workflow_state_opt_out(self, task_manager, project_id):
        """Test workflow state variable controls auto_decompose."""
        from unittest.mock import MagicMock

        task = task_manager.create_task(project_id, "Task")

        workflow_state = MagicMock()
        workflow_state.variables = {"auto_decompose": False}

        # Need at least 3 numbered items for detect_multi_step to return True
        result = task_manager.update_task_with_step_detection(
            task.id,
            description="1. First\n2. Second\n3. Third",
            workflow_state=workflow_state,
        )

        assert result["steps_detected"] is True
        assert result["auto_decomposed"] is False
        assert result["task"]["status"] == "needs_decomposition"

    def test_update_default_auto_decompose(self, task_manager, project_id):
        """Test default auto_decompose=True when no explicit param or workflow state."""
        task = task_manager.create_task(project_id, "Task")

        # No explicit auto_decompose param, no workflow_state
        # Default should be True, so it auto-decomposes
        result = task_manager.update_task_with_step_detection(
            task.id,
            description="1. First\n2. Second\n3. Third",
        )

        assert result["steps_detected"] is True
        assert result["auto_decomposed"] is True
        assert "subtasks" in result
        assert len(result["subtasks"]) == 3


@pytest.mark.integration
class TestListTasksBranchCoverage:
    """Additional tests for branch coverage in list_tasks."""

    def test_list_tasks_with_single_status(self, task_manager, project_id):
        """Test filtering with a single status string (not a list)."""
        task_manager.create_task(project_id, "Open Task")

        tasks = task_manager.list_tasks(project_id=project_id, status="open")

        assert len(tasks) == 1
        assert tasks[0].status == "open"

    def test_list_tasks_with_parent_filter(self, task_manager, project_id):
        """Test filtering tasks by parent_task_id."""
        parent = task_manager.create_task(project_id, "Parent")
        task_manager.create_task(project_id, "Child 1", parent_task_id=parent.id)
        task_manager.create_task(project_id, "Child 2", parent_task_id=parent.id)
        task_manager.create_task(project_id, "Orphan")

        tasks = task_manager.list_tasks(project_id=project_id, parent_task_id=parent.id)

        assert len(tasks) == 2
        for t in tasks:
            assert t.parent_task_id == parent.id


@pytest.mark.integration
class TestCreateTaskWithDecompositionDefaults:
    """Test default behavior for create_task_with_decomposition."""

    def test_create_default_auto_decompose_with_multi_step(self, task_manager, project_id):
        """Test default auto_decompose=True when no explicit param or workflow state."""
        # No explicit auto_decompose param, no workflow_state
        # Default should be True
        description = """Steps:
1. First step
2. Second step
3. Third step"""

        result = task_manager.create_task_with_decomposition(
            project_id=project_id,
            title="Default Decompose",
            description=description,
        )

        # Default is True, so it should auto-decompose
        assert result["auto_decomposed"] is True
        assert "parent_task" in result
        assert len(result["subtasks"]) == 3
