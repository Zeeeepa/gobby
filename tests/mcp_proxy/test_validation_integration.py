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
        description="Do it",
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
        description="Do it",
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
        description="Do it",
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


# ============================================================================
# Parent Task Validation Tests
# ============================================================================


@pytest.mark.asyncio
async def test_validate_parent_task_all_children_closed(mock_task_manager, mock_task_validator):
    """Test that parent task validates successfully when all children are closed."""
    parent_task = Task(
        id="parent1",
        title="Parent Task",
        project_id="p1",
        status="open",
        priority=2,
        task_type="epic",
        created_at="now",
        updated_at="now",
    )

    child1 = Task(
        id="child1",
        title="Child 1",
        project_id="p1",
        status="closed",
        priority=2,
        task_type="task",
        parent_task_id="parent1",
        created_at="now",
        updated_at="now",
    )
    child2 = Task(
        id="child2",
        title="Child 2",
        project_id="p1",
        status="closed",
        priority=2,
        task_type="task",
        parent_task_id="parent1",
        created_at="now",
        updated_at="now",
    )

    mock_task_manager.get_task.return_value = parent_task
    mock_task_manager.list_tasks.return_value = [child1, child2]  # Has children

    with (
        patch("gobby.mcp_proxy.tools.tasks.TaskDependencyManager"),
        patch("gobby.mcp_proxy.tools.tasks.SessionTaskManager"),
    ):
        registry = create_task_registry(
            task_manager=mock_task_manager,
            sync_manager=MagicMock(),
            task_validator=mock_task_validator,
        )

        result = await registry.call("validate_task", {"task_id": "parent1"})

        assert result["is_valid"] is True
        assert result["status"] == "valid"
        assert "2 child tasks" in result["feedback"]
        # Parent task should be closed
        mock_task_manager.close_task.assert_called_with("parent1", reason="Completed via validation")


@pytest.mark.asyncio
async def test_validate_parent_task_some_children_open(mock_task_manager, mock_task_validator):
    """Test that parent task validation fails when some children are still open."""
    parent_task = Task(
        id="parent1",
        title="Parent Task",
        project_id="p1",
        status="open",
        priority=2,
        task_type="epic",
        created_at="now",
        updated_at="now",
    )

    child1 = Task(
        id="child1",
        title="Completed Child",
        project_id="p1",
        status="closed",
        priority=2,
        task_type="task",
        parent_task_id="parent1",
        created_at="now",
        updated_at="now",
    )
    child2 = Task(
        id="child2",
        title="Open Child",
        project_id="p1",
        status="open",
        priority=2,
        task_type="task",
        parent_task_id="parent1",
        created_at="now",
        updated_at="now",
    )
    child3 = Task(
        id="child3",
        title="In Progress Child",
        project_id="p1",
        status="in_progress",
        priority=2,
        task_type="task",
        parent_task_id="parent1",
        created_at="now",
        updated_at="now",
    )

    mock_task_manager.get_task.return_value = parent_task
    mock_task_manager.list_tasks.return_value = [child1, child2, child3]  # Has children

    with (
        patch("gobby.mcp_proxy.tools.tasks.TaskDependencyManager"),
        patch("gobby.mcp_proxy.tools.tasks.SessionTaskManager"),
    ):
        registry = create_task_registry(
            task_manager=mock_task_manager,
            sync_manager=MagicMock(),
            task_validator=mock_task_validator,
        )

        result = await registry.call("validate_task", {"task_id": "parent1"})

        assert result["is_valid"] is False
        assert result["status"] == "invalid"
        assert "2 of 3 child tasks still open" in result["feedback"]
        # LLM validator should NOT have been called for parent task
        mock_task_validator.validate_task.assert_not_called()
        # Parent task should NOT be closed
        mock_task_manager.close_task.assert_not_called()


# ============================================================================
# LLM Failure Simulation Tests
# ============================================================================


@pytest.mark.asyncio
async def test_validate_task_llm_returns_pending(mock_task_manager, mock_task_validator):
    """Test handling when LLM validation returns pending status (error case)."""
    task = Task(
        id="t1",
        title="Task 1",
        project_id="p1",
        status="open",
        description="Do it",
        validation_fail_count=0,
        priority=2,
        task_type="task",
        created_at="now",
        updated_at="now",
    )
    mock_task_manager.get_task.return_value = task
    mock_task_manager.list_tasks.return_value = []

    # LLM returns pending (e.g., due to parsing error)
    mock_task_validator.validate_task.return_value = ValidationResult(
        status="pending", feedback="Failed to parse LLM response"
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

        result = await registry.call("validate_task", {"task_id": "t1", "changes_summary": "Done"})

        # Pending is not valid, but also doesn't increment fail count (it's an error, not rejection)
        assert result["is_valid"] is False
        assert result["status"] == "pending"
        # Task should NOT be closed
        mock_task_manager.close_task.assert_not_called()


@pytest.mark.asyncio
async def test_validate_task_llm_exception(mock_task_manager, mock_task_validator):
    """Test handling when LLM throws an exception during validation."""
    task = Task(
        id="t1",
        title="Task 1",
        project_id="p1",
        status="open",
        description="Do it",
        priority=2,
        task_type="task",
        created_at="now",
        updated_at="now",
    )
    mock_task_manager.get_task.return_value = task
    mock_task_manager.list_tasks.return_value = []

    # LLM throws exception
    mock_task_validator.validate_task.side_effect = Exception("API rate limited")

    with (
        patch("gobby.mcp_proxy.tools.tasks.TaskDependencyManager"),
        patch("gobby.mcp_proxy.tools.tasks.SessionTaskManager"),
    ):
        registry = create_task_registry(
            task_manager=mock_task_manager,
            sync_manager=MagicMock(),
            task_validator=mock_task_validator,
        )

        # Should raise the exception
        with pytest.raises(Exception, match="API rate limited"):
            await registry.call("validate_task", {"task_id": "t1", "changes_summary": "Done"})


# ============================================================================
# Subtask Creation Flow Tests
# ============================================================================


@pytest.mark.asyncio
async def test_validate_task_failure_creates_fix_subtask_with_correct_fields(
    mock_task_manager, mock_task_validator
):
    """Test that validation failure creates a properly configured fix subtask."""
    task = Task(
        id="t1",
        title="Implement feature X",
        project_id="proj123",
        status="open",
        description="Feature description",
        validation_fail_count=0,
        priority=2,
        task_type="feature",
        created_at="now",
        updated_at="now",
    )
    mock_task_manager.get_task.return_value = task
    mock_task_manager.list_tasks.return_value = []

    mock_task_validator.validate_task.return_value = ValidationResult(
        status="invalid",
        feedback="Missing error handling for edge case X. Tests for Y are incomplete.",
    )

    fix_subtask = Task(
        id="fix-abc",
        title="Fix validation failures for Implement feature X",
        project_id="proj123",
        status="open",
        priority=1,
        task_type="bug",
        parent_task_id="t1",
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

        result = await registry.call("validate_task", {"task_id": "t1", "changes_summary": "Done"})

        # Verify subtask creation call
        mock_task_manager.create_task.assert_called_once()
        create_args = mock_task_manager.create_task.call_args.kwargs

        # Verify all expected fields
        assert create_args["project_id"] == "proj123"
        assert "Fix validation failures" in create_args["title"]
        assert "Implement feature X" in create_args["title"]
        assert create_args["parent_task_id"] == "t1"
        assert create_args["priority"] == 1  # High priority for fix
        assert create_args["task_type"] == "bug"

        # Verify description contains feedback
        assert "Missing error handling" in create_args["description"]
        assert "Tests for Y are incomplete" in create_args["description"]
        assert "re-validate" in create_args["description"]

        # Verify feedback references the fix task (it's in validation_feedback which is stored in update_task)
        update_args = mock_task_manager.update_task.call_args.kwargs
        assert "fix-abc" in update_args["validation_feedback"]


@pytest.mark.asyncio
async def test_validate_task_second_failure_creates_second_subtask(
    mock_task_manager, mock_task_validator
):
    """Test that second validation failure also creates a fix subtask."""
    task = Task(
        id="t1",
        title="Task 1",
        project_id="p1",
        status="open",
        description="Do it",
        validation_fail_count=1,  # Already failed once
        priority=2,
        task_type="task",
        created_at="now",
        updated_at="now",
    )
    mock_task_manager.get_task.return_value = task
    mock_task_manager.list_tasks.return_value = []

    mock_task_validator.validate_task.return_value = ValidationResult(
        status="invalid", feedback="Still has issues"
    )

    fix_subtask = Task(
        id="fix2",
        title="Fix 2",
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

        result = await registry.call("validate_task", {"task_id": "t1", "changes_summary": "Done"})

        # This is the 2nd failure (fail_count goes from 1 to 2)
        # Should still create subtask since count < MAX_RETRIES (3)
        assert result["fail_count"] == 2
        mock_task_manager.create_task.assert_called_once()


# ============================================================================
# Max Validation Fails Tests
# ============================================================================


@pytest.mark.asyncio
async def test_validate_task_exactly_at_max_retries(mock_task_manager, mock_task_validator):
    """Test behavior when validation fails exactly at max retries (3)."""
    task = Task(
        id="t1",
        title="Problematic Task",
        project_id="p1",
        status="open",
        description="Cannot be completed",
        validation_fail_count=2,  # 2 previous failures
        priority=2,
        task_type="task",
        created_at="now",
        updated_at="now",
    )
    mock_task_manager.get_task.return_value = task
    mock_task_manager.list_tasks.return_value = []

    mock_task_validator.validate_task.return_value = ValidationResult(
        status="invalid", feedback="Third failure"
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

        result = await registry.call("validate_task", {"task_id": "t1", "changes_summary": "Done"})

        # 3rd failure hits MAX_RETRIES
        assert result["fail_count"] == 3
        assert result["is_valid"] is False

        # NO subtask should be created at max retries
        mock_task_manager.create_task.assert_not_called()

        # Task should be marked as failed
        update_args = mock_task_manager.update_task.call_args.kwargs
        assert update_args["status"] == "failed"
        assert update_args["validation_fail_count"] == 3
        assert "Exceeded max retries (3)" in update_args["validation_feedback"]


@pytest.mark.asyncio
async def test_validate_task_beyond_max_retries(mock_task_manager, mock_task_validator):
    """Test behavior when task already has max failures and fails again."""
    task = Task(
        id="t1",
        title="Already Failed Task",
        project_id="p1",
        status="open",  # Somehow reopened
        description="Was already at max failures",
        validation_fail_count=3,  # Already at max
        priority=2,
        task_type="task",
        created_at="now",
        updated_at="now",
    )
    mock_task_manager.get_task.return_value = task
    mock_task_manager.list_tasks.return_value = []

    mock_task_validator.validate_task.return_value = ValidationResult(
        status="invalid", feedback="Fourth failure"
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

        result = await registry.call("validate_task", {"task_id": "t1", "changes_summary": "Done"})

        # 4th failure is beyond max
        assert result["fail_count"] == 4
        assert result["is_valid"] is False

        # Still no subtask (already past max)
        mock_task_manager.create_task.assert_not_called()

        # Task should be marked as failed again
        update_args = mock_task_manager.update_task.call_args.kwargs
        assert update_args["status"] == "failed"


# ============================================================================
# Smart Context Gathering Tests
# ============================================================================


@pytest.mark.asyncio
async def test_validate_task_without_changes_summary_uses_smart_context(
    mock_task_manager, mock_task_validator
):
    """Test that validation without changes_summary uses smart context gathering."""
    task = Task(
        id="t1",
        title="Task 1",
        project_id="p1",
        status="open",
        description="Do it",
        validation_criteria="Must have tests",
        priority=2,
        task_type="task",
        created_at="now",
        updated_at="now",
    )
    mock_task_manager.get_task.return_value = task
    mock_task_manager.list_tasks.return_value = []

    mock_task_validator.validate_task.return_value = ValidationResult(
        status="valid", feedback="OK"
    )

    with (
        patch("gobby.mcp_proxy.tools.tasks.TaskDependencyManager"),
        patch("gobby.mcp_proxy.tools.tasks.SessionTaskManager"),
        patch(
            "gobby.tasks.validation.get_validation_context_smart"
        ) as mock_smart_context,
    ):
        mock_smart_context.return_value = "Smart context from git diff"

        registry = create_task_registry(
            task_manager=mock_task_manager,
            sync_manager=MagicMock(),
            task_validator=mock_task_validator,
        )

        # Call without changes_summary
        result = await registry.call("validate_task", {"task_id": "t1"})

        assert result["is_valid"] is True
        # Smart context should have been called
        mock_smart_context.assert_called_once()
        # Validator should have received the smart context
        validator_call = mock_task_validator.validate_task.call_args
        assert "Smart context from git diff" in validator_call.kwargs["changes_summary"]


@pytest.mark.asyncio
async def test_validate_task_no_context_available_raises_error(
    mock_task_manager, mock_task_validator
):
    """Test that validation fails gracefully when no context is available."""
    task = Task(
        id="t1",
        title="Task 1",
        project_id="p1",
        status="open",
        description="Do it",
        validation_criteria="Must have tests",
        priority=2,
        task_type="task",
        created_at="now",
        updated_at="now",
    )
    mock_task_manager.get_task.return_value = task
    mock_task_manager.list_tasks.return_value = []

    with (
        patch("gobby.mcp_proxy.tools.tasks.TaskDependencyManager"),
        patch("gobby.mcp_proxy.tools.tasks.SessionTaskManager"),
        patch(
            "gobby.tasks.validation.get_validation_context_smart"
        ) as mock_smart_context,
    ):
        # No context available
        mock_smart_context.return_value = None

        registry = create_task_registry(
            task_manager=mock_task_manager,
            sync_manager=MagicMock(),
            task_validator=mock_task_validator,
        )

        # Should raise ValueError
        with pytest.raises(ValueError, match="No changes found"):
            await registry.call("validate_task", {"task_id": "t1"})


# ============================================================================
# Generate Validation Criteria Tests
# ============================================================================


@pytest.mark.asyncio
async def test_generate_criteria_for_leaf_task(mock_task_manager, mock_task_validator):
    """Test generating validation criteria for a leaf task (no children)."""
    task = Task(
        id="t1",
        title="Implement login",
        project_id="p1",
        status="open",
        description="Add login functionality",
        priority=2,
        task_type="feature",
        created_at="now",
        updated_at="now",
        validation_criteria=None,  # No existing criteria
    )
    mock_task_manager.get_task.return_value = task
    mock_task_manager.list_tasks.return_value = []  # No children

    mock_task_validator.generate_criteria.return_value = (
        "- [ ] Login form renders\n- [ ] Password validation works"
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

        result = await registry.call("generate_validation_criteria", {"task_id": "t1"})

        assert result["generated"] is True
        assert result["is_parent_task"] is False
        assert "Login form renders" in result["validation_criteria"]

        # Verify criteria was saved to task
        mock_task_manager.update_task.assert_called()


@pytest.mark.asyncio
async def test_generate_criteria_for_parent_task(mock_task_manager, mock_task_validator):
    """Test generating validation criteria for a parent task (has children)."""
    parent_task = Task(
        id="parent1",
        title="Epic task",
        project_id="p1",
        status="open",
        priority=2,
        task_type="epic",
        created_at="now",
        updated_at="now",
        validation_criteria=None,
    )
    child_task = Task(
        id="child1",
        title="Child",
        project_id="p1",
        status="open",
        priority=2,
        task_type="task",
        created_at="now",
        updated_at="now",
    )

    mock_task_manager.get_task.return_value = parent_task
    mock_task_manager.list_tasks.return_value = [child_task]  # Has children

    with (
        patch("gobby.mcp_proxy.tools.tasks.TaskDependencyManager"),
        patch("gobby.mcp_proxy.tools.tasks.SessionTaskManager"),
    ):
        registry = create_task_registry(
            task_manager=mock_task_manager,
            sync_manager=MagicMock(),
            task_validator=mock_task_validator,
        )

        result = await registry.call("generate_validation_criteria", {"task_id": "parent1"})

        assert result["generated"] is True
        assert result["is_parent_task"] is True
        assert "All child tasks must be completed" in result["validation_criteria"]

        # LLM should NOT have been called for parent tasks
        mock_task_validator.generate_criteria.assert_not_called()


@pytest.mark.asyncio
async def test_generate_criteria_skips_existing(mock_task_manager, mock_task_validator):
    """Test that criteria generation is skipped if criteria already exists."""
    task = Task(
        id="t1",
        title="Task with criteria",
        project_id="p1",
        status="open",
        priority=2,
        task_type="task",
        created_at="now",
        updated_at="now",
        validation_criteria="Existing criteria here",  # Already has criteria
    )
    mock_task_manager.get_task.return_value = task
    mock_task_manager.list_tasks.return_value = []

    with (
        patch("gobby.mcp_proxy.tools.tasks.TaskDependencyManager"),
        patch("gobby.mcp_proxy.tools.tasks.SessionTaskManager"),
    ):
        registry = create_task_registry(
            task_manager=mock_task_manager,
            sync_manager=MagicMock(),
            task_validator=mock_task_validator,
        )

        result = await registry.call("generate_validation_criteria", {"task_id": "t1"})

        assert result["generated"] is False
        assert "already has validation criteria" in result["message"]
        mock_task_validator.generate_criteria.assert_not_called()


# ============================================================================
# Reset Validation Count Tests
# ============================================================================


@pytest.mark.asyncio
async def test_reset_validation_count(mock_task_manager, mock_task_validator):
    """Test resetting validation failure count."""
    task = Task(
        id="t1",
        title="Failed Task",
        project_id="p1",
        status="failed",
        priority=2,
        task_type="task",
        created_at="now",
        updated_at="now",
        validation_fail_count=3,
    )
    mock_task_manager.get_task.return_value = task
    mock_task_manager.update_task.return_value = Task(
        id="t1",
        title="Failed Task",
        project_id="p1",
        status="failed",
        priority=2,
        task_type="task",
        created_at="now",
        updated_at="now",
        validation_fail_count=0,  # Reset
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

        result = await registry.call("reset_validation_count", {"task_id": "t1"})

        assert result["validation_fail_count"] == 0
        assert "reset to 0" in result["message"]
        mock_task_manager.update_task.assert_called_with("t1", validation_fail_count=0)
