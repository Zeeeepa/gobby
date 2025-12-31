import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from gobby.mcp_proxy.tools.tasks import create_task_registry
from gobby.storage.tasks import LocalTaskManager, Task
from gobby.tasks.validation import TaskValidator, ValidationResult


@pytest.fixture
def mock_task_manager():
    manager = MagicMock(spec=LocalTaskManager)
    manager.db = MagicMock()  # Needed for dep_manager init
    return manager


@pytest.fixture
def mock_task_validator():
    validator = AsyncMock(spec=TaskValidator)
    return validator


@pytest.mark.asyncio
async def test_validate_task_tool_success(mock_task_manager, mock_task_validator):
    # Setup
    task = Task(
        id="t1",
        title="Task 1",
        project_id="p1",
        status="open",
        original_instruction="Do it",
        priority=2,
        task_type="task",
        created_at="now",
        updated_at="now",
    )
    mock_task_manager.get_task.return_value = task
    mock_task_manager.list_tasks.return_value = []  # No children - use leaf task validation

    mock_task_validator.validate_task.return_value = ValidationResult(
        status="valid", feedback="Good job"
    )

    # Create registry
    # We need to patch TaskDependencyManager since create_task_registry instantiates it
    with (
        patch("gobby.mcp_proxy.tools.tasks.TaskDependencyManager") as MockDepManager,
        patch("gobby.mcp_proxy.tools.tasks.SessionTaskManager"),
    ):
        registry = create_task_registry(
            task_manager=mock_task_manager,
            sync_manager=MagicMock(),
            task_validator=mock_task_validator,
        )

        # Execute
        result = await registry.call("validate_task", {"task_id": "t1", "changes_summary": "Done"})

        # Verify
        assert result["is_valid"] is True
        assert result["status"] == "valid"
        mock_task_manager.close_task.assert_called_with("t1", reason="Completed via validation")


@pytest.mark.asyncio
async def test_validate_task_tool_failure_retry(mock_task_manager, mock_task_validator):
    # Setup
    task = Task(
        id="t1",
        title="Task 1",
        project_id="p1",
        status="open",
        original_instruction="Do it",
        validation_fail_count=0,
        priority=2,
        task_type="task",
        created_at="now",
        updated_at="now",
    )
    mock_task_manager.get_task.return_value = task
    mock_task_manager.list_tasks.return_value = []  # No children - use leaf task validation

    mock_task_validator.validate_task.return_value = ValidationResult(
        status="invalid", feedback="Bad job"
    )

    fix_subtask = Task(
        id="fix1",
        title="Fix validation",
        project_id="p1",
        status="open",
        priority=1,
        task_type="bug",
        created_at="now",
        updated_at="now",
    )
    mock_task_manager.create_task.return_value = fix_subtask

    with (
        patch("gobby.mcp_proxy.tools.tasks.TaskDependencyManager"),
        patch("gobby.mcp_proxy.tools.tasks.SessionTaskManager"),
    ):
        registry = create_task_registry(
            task_manager=mock_task_manager,
            sync_manager=MagicMock(),
            task_validator=mock_task_validator,
        )

        # Execute
        result = await registry.call("validate_task", {"task_id": "t1", "changes_summary": "Done"})

        # Verify
        assert result["is_valid"] is False
        assert result["fail_count"] == 1

        # Check subtask creation
        mock_task_manager.create_task.assert_called_once()
        args = mock_task_manager.create_task.call_args.kwargs
        assert args["parent_task_id"] == "t1"
        assert args["task_type"] == "bug"
        assert "Bad job" in args["description"]

        # Check task update
        mock_task_manager.update_task.assert_called_once()
        update_args = mock_task_manager.update_task.call_args.kwargs
        assert update_args["validation_fail_count"] == 1
        assert "fix1" in update_args["validation_feedback"]


@pytest.mark.asyncio
async def test_validate_task_tool_failure_max_retries(mock_task_manager, mock_task_validator):
    # Setup -> already failed 2 times (max is 3, so failing one more time makes 3 -> failed?)

    task = Task(
        id="t1",
        title="Task 1",
        project_id="p1",
        status="open",
        original_instruction="Do it",
        validation_fail_count=2,
        priority=2,
        task_type="task",
        created_at="now",
        updated_at="now",
    )
    mock_task_manager.get_task.return_value = task
    mock_task_manager.list_tasks.return_value = []  # No children - use leaf task validation

    mock_task_validator.validate_task.return_value = ValidationResult(
        status="invalid", feedback="Still bad"
    )

    with (
        patch("gobby.mcp_proxy.tools.tasks.TaskDependencyManager"),
        patch("gobby.mcp_proxy.tools.tasks.SessionTaskManager"),
    ):
        registry = create_task_registry(
            task_manager=mock_task_manager,
            sync_manager=MagicMock(),
            task_validator=mock_task_validator,
        )

        # Execute
        result = await registry.call("validate_task", {"task_id": "t1", "changes_summary": "Done"})

        # Verify
        assert result["is_valid"] is False
        assert result["fail_count"] == 3

        # Verify NO subtask created
        mock_task_manager.create_task.assert_not_called()

        # Verify task marked as failed
        mock_task_manager.update_task.assert_called_once()
        update_args = mock_task_manager.update_task.call_args.kwargs
        assert update_args["status"] == "failed"
        assert "Exceeded max retries" in update_args["validation_feedback"]
