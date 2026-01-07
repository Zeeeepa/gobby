"""
Tests for task_readiness.py MCP tools module.

This file tests the readiness tools that will be extracted from tasks.py
into task_readiness.py using Strangler Fig pattern.

RED PHASE: These tests will fail initially because task_readiness.py
does not exist yet. The module will be created in the green phase.
"""

from unittest.mock import MagicMock, patch

import pytest


class TestListReadyTasks:
    """Tests for list_ready_tasks MCP tool."""

    def test_list_ready_tasks_basic(self, mock_readiness_registry):
        """Test basic list_ready_tasks call."""
        from gobby.mcp_proxy.tools.task_readiness import create_readiness_registry

        task_manager = MagicMock()
        mock_task = MagicMock()
        mock_task.to_brief.return_value = {
            "id": "task-1",
            "title": "Ready task",
            "status": "open",
        }
        task_manager.list_ready_tasks.return_value = [mock_task]

        registry = create_readiness_registry(task_manager=task_manager)
        list_ready = registry.get_tool("list_ready_tasks")

        result = list_ready()

        assert result["count"] == 1
        assert len(result["tasks"]) == 1
        task_manager.list_ready_tasks.assert_called_once()

    def test_list_ready_tasks_with_filters(self, mock_readiness_registry):
        """Test list_ready_tasks with priority and type filters."""
        from gobby.mcp_proxy.tools.task_readiness import create_readiness_registry

        task_manager = MagicMock()
        task_manager.list_ready_tasks.return_value = []

        registry = create_readiness_registry(task_manager=task_manager)
        list_ready = registry.get_tool("list_ready_tasks")

        list_ready(priority=1, task_type="bug", assignee="dev1", limit=5)

        task_manager.list_ready_tasks.assert_called_once_with(
            priority=1,
            task_type="bug",
            assignee="dev1",
            parent_task_id=None,
            limit=5,
            project_id="test-project-id",
        )

    def test_list_ready_tasks_parent_filter(self, mock_readiness_registry):
        """Test filtering ready tasks by parent_task_id."""
        from gobby.mcp_proxy.tools.task_readiness import create_readiness_registry

        task_manager = MagicMock()
        task_manager.list_ready_tasks.return_value = []

        registry = create_readiness_registry(task_manager=task_manager)
        list_ready = registry.get_tool("list_ready_tasks")

        list_ready(parent_task_id="parent-123")

        task_manager.list_ready_tasks.assert_called_once()
        call_args = task_manager.list_ready_tasks.call_args
        assert call_args.kwargs["parent_task_id"] == "parent-123"

    def test_list_ready_tasks_all_projects(self, mock_readiness_registry):
        """Test list_ready_tasks with all_projects=True."""
        from gobby.mcp_proxy.tools.task_readiness import create_readiness_registry

        task_manager = MagicMock()
        task_manager.list_ready_tasks.return_value = []

        registry = create_readiness_registry(task_manager=task_manager)
        list_ready = registry.get_tool("list_ready_tasks")

        list_ready(all_projects=True)

        task_manager.list_ready_tasks.assert_called_once()
        call_args = task_manager.list_ready_tasks.call_args
        assert call_args.kwargs["project_id"] is None

    def test_list_ready_tasks_empty_result(self, mock_readiness_registry):
        """Test list_ready_tasks when no tasks are ready."""
        from gobby.mcp_proxy.tools.task_readiness import create_readiness_registry

        task_manager = MagicMock()
        task_manager.list_ready_tasks.return_value = []

        registry = create_readiness_registry(task_manager=task_manager)
        list_ready = registry.get_tool("list_ready_tasks")

        result = list_ready()

        assert result["count"] == 0
        assert result["tasks"] == []


class TestListBlockedTasks:
    """Tests for list_blocked_tasks MCP tool."""

    def test_list_blocked_tasks_basic(self, mock_readiness_registry):
        """Test basic list_blocked_tasks call."""
        from gobby.mcp_proxy.tools.task_readiness import create_readiness_registry

        task_manager = MagicMock()
        mock_task = MagicMock()
        mock_task.to_brief.return_value = {
            "id": "task-1",
            "title": "Blocked task",
            "status": "open",
        }
        task_manager.list_blocked_tasks.return_value = [mock_task]

        registry = create_readiness_registry(task_manager=task_manager)
        list_blocked = registry.get_tool("list_blocked_tasks")

        result = list_blocked()

        assert result["count"] == 1
        assert len(result["tasks"]) == 1
        task_manager.list_blocked_tasks.assert_called_once()

    def test_list_blocked_tasks_parent_filter(self, mock_readiness_registry):
        """Test list_blocked_tasks with parent_task_id filter."""
        from gobby.mcp_proxy.tools.task_readiness import create_readiness_registry

        task_manager = MagicMock()
        task_manager.list_blocked_tasks.return_value = []

        registry = create_readiness_registry(task_manager=task_manager)
        list_blocked = registry.get_tool("list_blocked_tasks")

        list_blocked(parent_task_id="parent-123", limit=10)

        task_manager.list_blocked_tasks.assert_called_once_with(
            parent_task_id="parent-123",
            limit=10,
            project_id="test-project-id",
        )

    def test_list_blocked_tasks_all_projects(self, mock_readiness_registry):
        """Test list_blocked_tasks with all_projects=True."""
        from gobby.mcp_proxy.tools.task_readiness import create_readiness_registry

        task_manager = MagicMock()
        task_manager.list_blocked_tasks.return_value = []

        registry = create_readiness_registry(task_manager=task_manager)
        list_blocked = registry.get_tool("list_blocked_tasks")

        list_blocked(all_projects=True)

        task_manager.list_blocked_tasks.assert_called_once()
        call_args = task_manager.list_blocked_tasks.call_args
        assert call_args.kwargs["project_id"] is None

    def test_list_blocked_tasks_empty_result(self, mock_readiness_registry):
        """Test list_blocked_tasks when no tasks are blocked."""
        from gobby.mcp_proxy.tools.task_readiness import create_readiness_registry

        task_manager = MagicMock()
        task_manager.list_blocked_tasks.return_value = []

        registry = create_readiness_registry(task_manager=task_manager)
        list_blocked = registry.get_tool("list_blocked_tasks")

        result = list_blocked()

        assert result["count"] == 0
        assert result["tasks"] == []


class TestSuggestNextTask:
    """Tests for suggest_next_task MCP tool."""

    def test_suggest_next_task_basic(self, mock_readiness_registry):
        """Test basic suggest_next_task call."""
        from gobby.mcp_proxy.tools.task_readiness import create_readiness_registry

        task_manager = MagicMock()
        mock_task = MagicMock()
        mock_task.id = "task-1"
        mock_task.priority = 1
        mock_task.complexity_score = 3
        mock_task.test_strategy = "Unit tests"
        mock_task.to_dict.return_value = {"id": "task-1", "title": "High priority task"}

        task_manager.list_ready_tasks.return_value = [mock_task]
        task_manager.list_tasks.return_value = []  # No children = leaf task

        registry = create_readiness_registry(task_manager=task_manager)
        suggest = registry.get_tool("suggest_next_task")

        result = suggest()

        assert result["suggestion"] is not None
        assert result["suggestion"]["id"] == "task-1"
        assert "reason" in result

    def test_suggest_next_task_no_ready_tasks(self, mock_readiness_registry):
        """Test suggest_next_task when no tasks are ready."""
        from gobby.mcp_proxy.tools.task_readiness import create_readiness_registry

        task_manager = MagicMock()
        task_manager.list_ready_tasks.return_value = []

        registry = create_readiness_registry(task_manager=task_manager)
        suggest = registry.get_tool("suggest_next_task")

        result = suggest()

        assert result["suggestion"] is None
        assert "No ready tasks" in result["reason"]

    def test_suggest_next_task_prefers_leaf_tasks(self, mock_readiness_registry):
        """Test that suggest_next_task prefers leaf tasks over parent tasks."""
        from gobby.mcp_proxy.tools.task_readiness import create_readiness_registry

        task_manager = MagicMock()

        # Parent task (has children)
        parent_task = MagicMock()
        parent_task.id = "parent-1"
        parent_task.priority = 1
        parent_task.complexity_score = None
        parent_task.test_strategy = None
        parent_task.to_dict.return_value = {"id": "parent-1", "title": "Parent task"}

        # Leaf task (no children)
        leaf_task = MagicMock()
        leaf_task.id = "leaf-1"
        leaf_task.priority = 2  # Lower priority than parent
        leaf_task.complexity_score = 3
        leaf_task.test_strategy = "Unit tests"
        leaf_task.to_dict.return_value = {"id": "leaf-1", "title": "Leaf task"}

        task_manager.list_ready_tasks.return_value = [parent_task, leaf_task]

        # Mock list_tasks to indicate parent has children, leaf doesn't
        def mock_list_tasks(parent_task_id=None, status=None, limit=None):
            if parent_task_id == "parent-1":
                return [MagicMock()]  # Has children
            return []  # No children

        task_manager.list_tasks.side_effect = mock_list_tasks

        registry = create_readiness_registry(task_manager=task_manager)
        suggest = registry.get_tool("suggest_next_task")

        result = suggest(prefer_subtasks=True)

        # Should prefer leaf task despite lower priority
        assert result["suggestion"]["id"] == "leaf-1"

    def test_suggest_next_task_with_type_filter(self, mock_readiness_registry):
        """Test suggest_next_task with task_type filter."""
        from gobby.mcp_proxy.tools.task_readiness import create_readiness_registry

        task_manager = MagicMock()
        task_manager.list_ready_tasks.return_value = []

        registry = create_readiness_registry(task_manager=task_manager)
        suggest = registry.get_tool("suggest_next_task")

        suggest(task_type="bug")

        task_manager.list_ready_tasks.assert_called_once_with(
            task_type="bug",
            limit=50,
            project_id="test-project-id",
        )

    def test_suggest_next_task_scoring(self, mock_readiness_registry):
        """Test that suggest_next_task uses correct scoring algorithm."""
        from gobby.mcp_proxy.tools.task_readiness import create_readiness_registry

        task_manager = MagicMock()

        # Low priority task with good attributes
        task_low_priority = MagicMock()
        task_low_priority.id = "low-priority"
        task_low_priority.priority = 3
        task_low_priority.complexity_score = 2
        task_low_priority.test_strategy = "Unit tests"
        task_low_priority.to_dict.return_value = {"id": "low-priority"}

        # High priority task with no extra attributes
        task_high_priority = MagicMock()
        task_high_priority.id = "high-priority"
        task_high_priority.priority = 1
        task_high_priority.complexity_score = None
        task_high_priority.test_strategy = None
        task_high_priority.to_dict.return_value = {"id": "high-priority"}

        task_manager.list_ready_tasks.return_value = [task_low_priority, task_high_priority]
        task_manager.list_tasks.return_value = []  # Both are leaf tasks

        registry = create_readiness_registry(task_manager=task_manager)
        suggest = registry.get_tool("suggest_next_task")

        result = suggest()

        # High priority should win (30 points) over low priority (10 + 15 + 10 = 35, but both get leaf bonus)
        # Actually with leaf bonus: high = 30 + 25 = 55, low = 10 + 25 + 15 + 10 = 60
        # So low priority with better attributes should win
        assert result["suggestion"]["id"] == "low-priority"


class TestReadinessEdgeCases:
    """Tests for edge cases in readiness detection."""

    def test_completed_dependencies_make_task_ready(self, mock_readiness_registry):
        """Test that tasks become ready when all blocking deps are completed."""
        from gobby.mcp_proxy.tools.task_readiness import create_readiness_registry

        task_manager = MagicMock()

        # Task with completed blockers should be ready
        ready_task = MagicMock()
        ready_task.to_brief.return_value = {"id": "task-1", "status": "open"}
        task_manager.list_ready_tasks.return_value = [ready_task]

        registry = create_readiness_registry(task_manager=task_manager)
        list_ready = registry.get_tool("list_ready_tasks")

        result = list_ready()

        # Task should appear in ready list
        assert result["count"] == 1

    def test_multiple_blockers_all_must_complete(self, mock_readiness_registry):
        """Test that a task with multiple blockers needs all to complete."""
        from gobby.mcp_proxy.tools.task_readiness import create_readiness_registry

        task_manager = MagicMock()

        # Task is still blocked if any blocker is not complete
        blocked_task = MagicMock()
        blocked_task.to_brief.return_value = {"id": "task-1", "status": "open"}
        task_manager.list_blocked_tasks.return_value = [blocked_task]

        registry = create_readiness_registry(task_manager=task_manager)
        list_blocked = registry.get_tool("list_blocked_tasks")

        result = list_blocked()

        assert result["count"] == 1

    def test_circular_dependency_handling(self, mock_readiness_registry):
        """Test handling of circular dependencies."""
        from gobby.mcp_proxy.tools.task_readiness import create_readiness_registry

        task_manager = MagicMock()

        # Tasks in a cycle should be blocked
        task_a = MagicMock()
        task_a.to_brief.return_value = {"id": "task-a", "status": "open"}
        task_b = MagicMock()
        task_b.to_brief.return_value = {"id": "task-b", "status": "open"}

        task_manager.list_blocked_tasks.return_value = [task_a, task_b]

        registry = create_readiness_registry(task_manager=task_manager)
        list_blocked = registry.get_tool("list_blocked_tasks")

        result = list_blocked()

        # Both tasks should appear as blocked
        assert result["count"] == 2

    def test_missing_dependency_task(self, mock_readiness_registry):
        """Test handling when a dependency references a non-existent task."""
        from gobby.mcp_proxy.tools.task_readiness import create_readiness_registry

        task_manager = MagicMock()
        # Task with missing dependency should still be in blocked list
        # or treated as ready depending on implementation
        task_manager.list_blocked_tasks.return_value = []
        task_manager.list_ready_tasks.return_value = []

        registry = create_readiness_registry(task_manager=task_manager)
        list_ready = registry.get_tool("list_ready_tasks")
        list_blocked = registry.get_tool("list_blocked_tasks")

        ready_result = list_ready()
        blocked_result = list_blocked()

        # Should handle gracefully without errors
        assert "count" in ready_result
        assert "count" in blocked_result

    def test_default_limit_values(self, mock_readiness_registry):
        """Test default limit values for listing functions."""
        from gobby.mcp_proxy.tools.task_readiness import create_readiness_registry

        task_manager = MagicMock()
        task_manager.list_ready_tasks.return_value = []
        task_manager.list_blocked_tasks.return_value = []

        registry = create_readiness_registry(task_manager=task_manager)

        list_ready = registry.get_tool("list_ready_tasks")
        list_ready()
        # Default limit for ready tasks is 10
        assert task_manager.list_ready_tasks.call_args.kwargs["limit"] == 10

        list_blocked = registry.get_tool("list_blocked_tasks")
        list_blocked()
        # Default limit for blocked tasks is 20
        assert task_manager.list_blocked_tasks.call_args.kwargs["limit"] == 20


class TestSuggestNextTaskWithParentId:
    """Tests for suggest_next_task with parent_id filtering."""

    def test_suggest_next_task_with_parent_id(self, mock_readiness_registry):
        """Test suggest_next_task filters to descendants when parent_id is set."""
        from gobby.mcp_proxy.tools.task_readiness import create_readiness_registry

        task_manager = MagicMock()

        # Create parent task
        parent_task = MagicMock()
        parent_task.id = "epic-1"
        parent_task.parent_task_id = None

        # Create child tasks (descendants of epic-1)
        child_task = MagicMock()
        child_task.id = "child-1"
        child_task.parent_task_id = "epic-1"
        child_task.priority = 2
        child_task.complexity_score = None
        child_task.test_strategy = None
        child_task.to_dict.return_value = {"id": "child-1", "title": "Child task"}

        # Create unrelated task (not a descendant)
        other_task = MagicMock()
        other_task.id = "other-1"
        other_task.parent_task_id = "other-epic"
        other_task.priority = 1  # Higher priority but outside scope
        other_task.to_dict.return_value = {"id": "other-1"}

        # list_ready_tasks returns both tasks
        task_manager.list_ready_tasks.return_value = [child_task, other_task]

        # list_tasks is called multiple times:
        # 1. Building descendant set: children of epic-1
        # 2. Building descendant set: children of child-1 (empty = leaf)
        # 3. Scoring: children of child-1 (to check if leaf)
        def list_tasks_side_effect(**kwargs):
            parent_id = kwargs.get("parent_task_id")
            if parent_id == "epic-1":
                return [child_task]
            return []  # No children for child-1

        task_manager.list_tasks.side_effect = list_tasks_side_effect

        registry = create_readiness_registry(task_manager=task_manager)
        suggest = registry.get_tool("suggest_next_task")

        result = suggest(parent_id="epic-1")

        # Should only suggest child task, not other-1
        assert result["suggestion"] is not None
        assert result["suggestion"]["id"] == "child-1"

    def test_suggest_next_task_with_parent_id_no_descendants(self, mock_readiness_registry):
        """Test suggest_next_task returns no suggestion when no descendants are ready."""
        from gobby.mcp_proxy.tools.task_readiness import create_readiness_registry

        task_manager = MagicMock()

        # No ready tasks are descendants of the specified parent
        other_task = MagicMock()
        other_task.id = "other-1"
        other_task.parent_task_id = "other-epic"

        task_manager.list_ready_tasks.return_value = [other_task]
        task_manager.list_tasks.return_value = []  # No children of epic-1

        registry = create_readiness_registry(task_manager=task_manager)
        suggest = registry.get_tool("suggest_next_task")

        result = suggest(parent_id="epic-1")

        assert result["suggestion"] is None
        assert "No ready tasks" in result["reason"]


class TestIsDescendantOf:
    """Tests for is_descendant_of helper function."""

    def test_is_descendant_of_direct_child(self):
        """Test is_descendant_of for direct parent-child relationship."""
        from gobby.mcp_proxy.tools.task_readiness import is_descendant_of

        task_manager = MagicMock()

        # Child task
        child_task = MagicMock()
        child_task.parent_task_id = "parent-1"

        task_manager.get_task.return_value = child_task

        result = is_descendant_of(task_manager, "child-1", "parent-1")
        assert result is True

    def test_is_descendant_of_grandchild(self):
        """Test is_descendant_of for grandparent-grandchild relationship."""
        from gobby.mcp_proxy.tools.task_readiness import is_descendant_of

        task_manager = MagicMock()

        # Grandchild -> Child -> Parent
        grandchild = MagicMock()
        grandchild.parent_task_id = "child-1"

        child = MagicMock()
        child.parent_task_id = "parent-1"

        task_manager.get_task.side_effect = [grandchild, child]

        result = is_descendant_of(task_manager, "grandchild-1", "parent-1")
        assert result is True

    def test_is_descendant_of_self(self):
        """Test is_descendant_of returns True for same task."""
        from gobby.mcp_proxy.tools.task_readiness import is_descendant_of

        task_manager = MagicMock()

        result = is_descendant_of(task_manager, "task-1", "task-1")
        assert result is True

    def test_is_descendant_of_unrelated(self):
        """Test is_descendant_of returns False for unrelated tasks."""
        from gobby.mcp_proxy.tools.task_readiness import is_descendant_of

        task_manager = MagicMock()

        # Task with different parent
        task = MagicMock()
        task.parent_task_id = "other-parent"

        other_parent = MagicMock()
        other_parent.parent_task_id = None

        task_manager.get_task.side_effect = [task, other_parent]

        result = is_descendant_of(task_manager, "task-1", "not-my-parent")
        assert result is False

    def test_is_descendant_of_not_found(self):
        """Test is_descendant_of returns False when task not found."""
        from gobby.mcp_proxy.tools.task_readiness import is_descendant_of

        task_manager = MagicMock()
        task_manager.get_task.return_value = None

        result = is_descendant_of(task_manager, "missing-task", "parent-1")
        assert result is False


@pytest.fixture
def mock_readiness_registry():
    """Fixture providing mock dependencies for registry creation."""
    with patch("gobby.mcp_proxy.tools.task_readiness.get_current_project_id") as mock_proj:
        mock_proj.return_value = "test-project-id"
        yield mock_proj
