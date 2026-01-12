import pytest
from unittest.mock import MagicMock
from gobby.tasks.tdd_repair import TDDRepair
from gobby.storage.tasks import LocalTaskManager, Task


class TestTDDRepair:
    def test_upgrade_pairs_to_triplets(self):
        # Setup
        task_manager = MagicMock(spec=LocalTaskManager)
        task_manager.db = MagicMock()

        # Mock Data:
        # 1. Test Task (Legacy)
        test_task = MagicMock(spec=Task)
        test_task.id = "test-1"
        test_task.title = "Write tests for: User Login"
        test_task.parent_task_id = "epic-1"

        # 2. Impl Task (Legacy Child of Test)
        impl_task = MagicMock(spec=Task)
        impl_task.id = "impl-1"
        impl_task.title = "User Login"  # Legacy title was just the feature
        impl_task.parent_task_id = "test-1"
        impl_task.priority = 1

        # 3. Unrelated Task
        other_task = MagicMock(spec=Task)
        other_task.id = "other-1"
        other_task.title = "Documentation"
        other_task.parent_task_id = "epic-1"

        all_tasks = [test_task, impl_task, other_task]
        task_manager.list_tasks.return_value = all_tasks

        # Mock create_task
        created_refactor = MagicMock(spec=Task)
        created_refactor.id = "refactor-1"
        task_manager.create_task.return_value = created_refactor

        # Mock dep manager
        mock_dep_manager = MagicMock()

        repair = TDDRepair(task_manager)
        repair.dep_manager = mock_dep_manager

        # Act
        new_ids = repair.upgrade_pairs_to_triplets("p1")

        # Assert
        assert len(new_ids) == 1
        assert new_ids[0] == "refactor-1"

        # Check create_task call
        task_manager.create_task.assert_called_once()
        kwargs = task_manager.create_task.call_args.kwargs
        assert kwargs["title"] == "Refactor: User Login"
        assert kwargs["parent_task_id"] == "test-1"  # Kept as child of Test
        assert kwargs["priority"] == 1

        # Check dependency
        mock_dep_manager.add_dependency.assert_called_once_with(
            task_id="refactor-1", depends_on="impl-1", dep_type="blocks"
        )
