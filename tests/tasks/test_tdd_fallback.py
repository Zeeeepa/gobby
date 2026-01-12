import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from gobby.tasks.expansion import TaskExpander, SubtaskSpec
from gobby.storage.tasks import LocalTaskManager, Task
from gobby.config.app import TaskExpansionConfig


@pytest.fixture
def mock_task_manager():
    manager = MagicMock(spec=LocalTaskManager)
    manager.db = MagicMock()

    # Mock create_task to return a fake task
    created_tasks = []

    def create_task_side_effect(**kwargs):
        task = MagicMock()
        task.id = f"task-{len(created_tasks)}"
        task.title = kwargs.get("title")
        created_tasks.append(task)
        return task

    manager.create_task.side_effect = create_task_side_effect
    return manager


@pytest.mark.asyncio
async def test_tdd_fallback_expands_to_triplet(mock_task_manager):
    # Setup
    config = TaskExpansionConfig(enabled=True, tdd_mode=True)
    llm_service = MagicMock()

    expander = TaskExpander(config, llm_service, mock_task_manager)

    # Input specs: Single coding task "Implement Auth"
    specs = [SubtaskSpec(title="Implement Auth", task_type="task", priority=1)]

    # Mock dependency manager
    with patch("gobby.tasks.expansion.TaskDependencyManager") as MockDepManager:
        mock_dep_manager = MockDepManager.return_value

        # Act
        created_ids = await expander._create_subtasks(
            parent_task_id="parent-1",
            project_id="p1",
            subtask_specs=specs,
            tdd_mode=True,
        )

        # Assert
        assert len(created_ids) == 3

        # Verify tasks created
        calls = mock_task_manager.create_task.call_args_list
        assert len(calls) == 3

        titles = [c.kwargs["title"] for c in calls]
        assert "Write tests for: Implement Auth" in titles[0]
        assert "Implement: Implement Auth" in titles[1]
        assert "Refactor: Implement Auth" in titles[2]

        # Verify dependencies
        # IDs are generated starting from 0 by the mock side effect.
        # But wait, create_task is called inside a loop or sequentially.
        # calls[0] -> task-0 (Test)
        # calls[1] -> task-1 (Impl)
        # calls[2] -> task-2 (Refactor)

        mock_dep_manager.add_dependency.assert_any_call("task-1", "task-0", "blocks")
        mock_dep_manager.add_dependency.assert_any_call("task-2", "task-1", "blocks")


@pytest.mark.asyncio
async def test_tdd_fallback_respects_existing_tests(mock_task_manager):
    # Setup
    config = TaskExpansionConfig(enabled=True, tdd_mode=True)
    llm_service = MagicMock()
    expander = TaskExpander(config, llm_service, mock_task_manager)

    # Input specs: "Write tests" and "Implement" already present
    specs = [
        SubtaskSpec(title="Write tests for Auth", task_type="task"),
        SubtaskSpec(title="Implement Auth", task_type="task", depends_on=[0]),
    ]

    with patch("gobby.tasks.expansion.TaskDependencyManager") as MockDepManager:
        mock_dep = MockDepManager.return_value

        created_ids = await expander._create_subtasks(
            parent_task_id="p-1", project_id="p1", subtask_specs=specs, tdd_mode=True
        )

        # Should NOT expand "Implement Auth" because it depends on a test task
        # Should create exactly 2 tasks
        assert len(created_ids) == 2

        calls = mock_task_manager.create_task.call_args_list
        assert len(calls) == 2
        assert calls[0].kwargs["title"] == "Write tests for Auth"
        assert calls[1].kwargs["title"] == "Implement Auth"
